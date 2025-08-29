import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { MetricCard } from '../MetricCard';
import { EventsTable, Event } from '../EventsTable';
import { StatusPill } from '../StatusPill';
import { LinePower24h, PowerSegment } from '../LinePower24h';
import { HealthBar, useHealthData } from '../HealthBar';
import { cn } from '../ui/utils';
import { useWalnutApi } from '../../hooks/useWalnutApi';
import { apiService, IntegrationInstance, IntegrationType } from '../../services/api';

// Mock data
const mockUPSMetrics = [
  { label: 'Battery', value: 87, max: 100, unit: '%', status: 'ok' as const },
  { label: 'Load', value: 245, max: 650, unit: 'W' },
  { label: 'Runtime', value: 15, max: 30, unit: 'min' }
];

const mockEvents: Event[] = [
  {
    id: '1',
    timestamp: '2024-01-15T14:30:00Z',
    type: 'OnBattery',
    source: 'UPS',
    severity: 'Warning',
    message: 'UPS switched to battery power - utility power lost',
    payload: { voltage: 0, frequency: 0, loadWatts: 245 }
  },
  {
    id: '2',
    timestamp: '2024-01-15T14:32:15Z',
    type: 'Recovered',
    source: 'UPS',
    severity: 'Info',
    message: 'Utility power restored, UPS back online',
    payload: { voltage: 230, frequency: 50, loadWatts: 245 }
  },
  {
    id: '3',
    timestamp: '2024-01-15T13:15:00Z',
    type: 'Test',
    source: 'Policy',
    severity: 'Info',
    message: 'Scheduled battery test completed successfully',
    payload: { testDuration: 30, batteryHealth: 'Good' }
  }
];

// Build a simple 24h power timeline from events (OnBattery/Recovered)
function buildTimelineFromEvents(events: Event[], hours: 6 | 12 | 24 = 24): PowerSegment[] {
  const now = Date.now();
  const startWindow = now - hours * 3600_000;
  const within = events
    .map(e => ({ ...e, ts: new Date(e.timestamp).getTime() }))
    .filter(e => e.ts >= startWindow)
    .sort((a, b) => a.ts - b.ts);

  const segments: PowerSegment[] = [];
  let cursor = startWindow;
  let status: 'online' | 'on-battery' = 'online';

  for (const e of within) {
    const segEnd = e.ts;
    if (segEnd > cursor) {
      segments.push({ start: new Date(cursor), end: new Date(segEnd), status });
      cursor = segEnd;
    }
    if (e.type === 'OnBattery') status = 'on-battery';
    if (e.type === 'Recovered') status = 'online';
  }
  // Tail
  if (cursor < now) {
    segments.push({ start: new Date(cursor), end: new Date(now), status });
  }
  return segments;
}

export function OverviewScreen() {
  const { upsStatus, systemHealth, events, isLoading, error, wsConnected } = useWalnutApi();
  
  // Determine UPS availability based on stale timestamp and NUT health
  const HEARTBEAT_TIMEOUT_MS = 120_000; // sync with backend /ups/telemetry
  const nowMs = Date.now();
  const upsLastTsMs = upsStatus ? new Date(upsStatus.timestamp).getTime() : 0;
  const upsStale = !!upsStatus && (nowMs - upsLastTsMs > HEARTBEAT_TIMEOUT_MS);
  const nutUnhealthy = !!systemHealth && (systemHealth as any).components && (systemHealth as any).components.nut_connection && (systemHealth as any).components.nut_connection.status !== 'healthy';
  const upsUnavailable = upsStale || nutUnhealthy;
  
  // Derive a brief issue summary for banner when degraded/critical
  const issueSummary = React.useMemo(() => {
    if (!systemHealth || !(systemHealth as any).components) return '';
    const comps: any = (systemHealth as any).components;
    const firstCritical = Object.entries(comps).find(([, c]: any) => c && c.status === 'critical');
    const firstDegraded = Object.entries(comps).find(([, c]: any) => c && c.status === 'degraded');
    const entry = (firstCritical || firstDegraded);
    if (!entry) return '';
    const key = entry[0];
    const details: any = entry[1];
    if (key === 'nut_connection') return 'NUT Unreachable';
    if (key === 'ups_polling') return 'UPS Polling Stopped';
    if (key === 'database') return 'Database Unavailable';
    if (key === 'system_resources') return 'High System Resource Usage';
    return details?.message || 'Service Issue';
  }, [systemHealth]);
  const [searchParams, setSearchParams] = useSearchParams();
  const [viewMode] = useState<'cards' | 'table'>('cards');
  
  // Get timeline duration from URL params (with fallback)
  const timelineDuration = (searchParams.get('range') as '6h' | '12h' | '24h') || '24h';
  
  const [types, setTypes] = useState<IntegrationType[]>([]);
  const [instances, setInstances] = useState<IntegrationInstance[]>([]);
  
  // UPS Health Data for the new timeline
  const { segments: healthSegments, loading: healthLoading, error: healthError } = useHealthData({
    duration: timelineDuration,
    enabled: true,
  });
  
  // Update URL params when range changes
  const setTimelineDuration = (duration: '6h' | '12h' | '24h') => {
    const newParams = new URLSearchParams(searchParams);
    newParams.set('range', duration);
    setSearchParams(newParams);
  };

  // Convert API events to frontend format
  const convertedEvents: Event[] = events.map(event => ({
    id: event.id.toString(),
    timestamp: event.timestamp,
    type: event.event_type,
    source: 'UPS', // Default source - could be enhanced based on event metadata
    severity: event.severity,
    message: event.description,
    payload: event.metadata || {}
  }));

  const filteredEvents = convertedEvents;

  // Load integration summary for real counts
  useEffect(() => {
    (async () => {
      try {
        const [t, i] = await Promise.all([
          apiService.getIntegrationTypes().catch(() => []),
          apiService.getIntegrationInstances().catch(() => []),
        ]);
        setTypes(t);
        setInstances(i);
      } catch (_) {}
    })();
  }, []);

  const integrationMetrics = useMemo(() => {
    const totalTypes = types.length;
    const totalInstances = instances.length;
    const connected = instances.filter(x => x.state === 'connected').length;
    const degraded = instances.filter(x => x.state === 'degraded').length;
    
    // If no instances exist, don't treat it as an error - it's just empty
    if (totalInstances === 0) {
      return [
        { label: 'Instances', value: 0, max: 1, unit: '', status: 'ok' as const },
        { label: 'Connected', value: 0, max: 1, unit: '', status: 'ok' as const },
        { label: 'Degraded', value: 0, max: 1, unit: '', status: 'ok' as const },
      ];
    }
    
    return [
      { label: 'Instances', value: totalInstances, max: totalInstances, unit: '', inverse: true },
      { label: 'Connected', value: connected, max: totalInstances, unit: '', inverse: true },
      { label: 'Degraded', value: degraded, max: totalInstances, unit: '' }, // Lower is better for degraded
    ];
  }, [types, instances]);

  // Convert UPS status to metrics format (empty when UPS is unavailable)
  const upsMetrics = (!upsUnavailable && upsStatus) ? [
    { 
      label: 'Battery', 
      value: upsStatus.battery_percent || 0, 
      max: 100, 
      unit: '%', 
      inverse: true  // Higher battery percentage is better
    },
    { 
      label: 'Load', 
      value: upsStatus.load_percent ? Math.round((upsStatus.load_percent / 100) * 650) : 0, 
      max: 650, 
      unit: 'W' 
    },
    { 
      label: 'Runtime', 
      value: upsStatus.runtime_seconds ? Math.round(upsStatus.runtime_seconds / 60) : 0, 
      max: upsStatus.runtime_seconds ? Math.max(30, Math.round(upsStatus.runtime_seconds / 60)) : 30, 
      unit: 'min',
      inverse: true  // Higher runtime is better
    }
  ] : [];

  return (
    <div className="flex-1">
      {/* No secondary toolbar on Overview */}

      <div className="container-grid py-6 space-y-6 mt-4 md:mt-6">
        <div className="grid-12">
          {/* Status Banner */}
          <div className="col-span-12">
            <div className="card-standard p-4">
              <div className="flex items-center space-x-4">
                <StatusPill 
                  status={
                    isLoading ? 'ok' : 
                    error ? 'error' : 
                    !systemHealth ? 'warn' :
                    systemHealth.status === 'healthy' ? 'ok' : 
                    systemHealth.status === 'degraded' ? 'warn' : 'error'
                  } 
                  size="md" 
                />
                <div>
                  <div className="text-title">
                    {isLoading ? 'Connecting to walNUT' : 
                     error ? 'Connection Error' : 
                     !systemHealth ? 'Initializing System' :
                     systemHealth.status === 'healthy' ? 'System Online' : 
                     systemHealth.status === 'degraded' ? `System Degraded${issueSummary ? ': ' + issueSummary : ''}` : `System Issues Detected${issueSummary ? ': ' + issueSummary : ''}`}
                  </div>
                  <div className="text-micro text-muted-foreground tabular-nums">
                    {isLoading ? 'Establishing secure connection...' : 
                     error ? 'Check network connection and try refreshing' : ''}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* UPS Health Timeline */}
          <div className="col-span-12">
            <div className="space-y-4">
              {/* Header with title and zoom controls */}
              <div className="flex items-center justify-between">
                <h3 className="text-title">UPS Health Status — Last {timelineDuration.replace('h', ' hours')}</h3>
                
                <div className="flex items-center bg-muted rounded-md p-1 space-x-1">
                  {(['24h', '12h', '6h'] as const).map((d) => (
                    <button
                      key={d}
                      onClick={() => setTimelineDuration(d)}
                      className={cn(
                        'px-3 py-1 rounded text-micro font-medium transition-colors',
                        timelineDuration === d 
                          ? 'bg-background text-foreground shadow-sm' 
                          : 'text-muted-foreground hover:text-foreground'
                      )}
                    >
                      {d}
                    </button>
                  ))}
                </div>
              </div>

              {/* Health Status Legend */}
              <div className="flex items-center flex-wrap gap-4 text-micro">
                <div className="flex items-center space-x-2">
                  <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: 'var(--health-green)' }} />
                  <span className="text-muted-foreground">Online</span>
                </div>
                <div className="flex items-center space-x-2">
                  <div className="w-3 h-3 rounded-sm health-pattern-amber" style={{ backgroundColor: 'var(--health-amber)' }} />
                  <span className="text-muted-foreground">Degraded</span>
                </div>
                <div className="flex items-center space-x-2">
                  <div className="w-3 h-3 rounded-sm health-pattern-red" style={{ backgroundColor: 'var(--health-red)' }} />
                  <span className="text-muted-foreground">Critical</span>
                </div>
                <div className="flex items-center space-x-2">
                  <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: 'var(--health-grey)' }} />
                  <span className="text-muted-foreground">No Data</span>
                </div>
              </div>

              {/* Health Timeline */}
              {healthLoading ? (
                <div className="h-3 bg-muted rounded-md animate-pulse" />
              ) : healthError ? (
                <div className="h-3 bg-muted rounded-md flex items-center justify-center">
                  <span className="text-micro text-muted-foreground">Failed to load health data</span>
                </div>
              ) : (
                <HealthBar 
                  segments={healthSegments}
                  duration={timelineDuration}
                  height={12}
                  showTimeAxis={true}
                  enableTooltips={true}
                  className="mb-6"
                />
              )}
            </div>
          </div>
        </div>

        {/* Metrics Grid */}
        {viewMode === 'cards' && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
              {/* Top row - 3 responsive cards */}
              <div className="min-h-[280px]">
                <MetricCard
                  title="UPS Status"
                  status={upsUnavailable ? 'error' : (upsStatus?.status?.includes('OB') ? 'warn' : 'ok')}
                  metrics={upsMetrics}
                  meta={{
                    uptime: systemHealth && systemHealth.uptime_seconds ? 
                      `${Math.floor(systemHealth.uptime_seconds / 86400)}d ${Math.floor((systemHealth.uptime_seconds % 86400) / 3600)}h` : 
                      isLoading ? 'Loading...' : '—',
                    lastUpdate: wsConnected ? 'Live data' : 
                      upsStatus ? new Date(upsStatus.timestamp).toLocaleString() : 
                      isLoading ? 'Connecting...' : 'Waiting for data',
                    driver: upsUnavailable ? 'No Data' : (
                      upsStatus?.status ? 
                        upsStatus.status.replace('OL', 'Online').replace('OB', 'On Battery').replace('CHRG', 'Charging') : 
                        isLoading ? 'Detecting...' : 'Not connected'
                    )
                  }}
                />
              </div>
              
              <div className="min-h-[280px]">
                <MetricCard
                  title="Event Summary (24h)"
                  status={convertedEvents.filter(e => e.type === 'OnBattery').length > 0 ? 'warn' : 'ok'}
                  metrics={[
                    { label: 'OnBattery Events', value: convertedEvents.filter(e => e.type === 'OnBattery').length, max: 10, unit: '' },
                    { label: 'Recoveries', value: convertedEvents.filter(e => e.type === 'Recovered').length, max: 10, unit: '' },
                    { label: 'Low Battery', value: convertedEvents.filter(e => e.type === 'LowBattery').length, max: 5, unit: '' }
                  ]}
                  meta={{
                    lastUpdate: convertedEvents.length > 0 ? 
                      `${Math.round((Date.now() - new Date(convertedEvents[0].timestamp).getTime()) / 60000)}m ago` : 
                      'No events'
                  }}
                />
              </div>

              <div className="min-h-[280px] md:col-span-2 xl:col-span-1">
                <MetricCard
                  title="Orchestration State"
                  status="ok"
                  metrics={[
                    { label: 'Active Policies', value: 0, max: 1, unit: '' },
                    { label: 'Pending Actions', value: 0, max: 1, unit: '' },
                    { label: 'Success Rate', value: 100, max: 100, unit: '%', inverse: true }
                  ]}
                  meta={{
                    lastUpdate: wsConnected ? 'Live' : '1m ago'
                  }}
                />
              </div>
            </div>
            
            {/* Bottom row - Integration status */}
            <div className="mt-8">
              <div className="min-h-[180px]">
                <MetricCard
                  title="Integration Status"
                  status="ok"
                  metrics={integrationMetrics}
                  size="L"
                />
              </div>
            </div>
          </>
        )}

        {/* Events Table */}
        <div className="grid-12">
          <div className="col-span-12 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-display">Recent Events</h2>
              <div className="text-micro text-muted-foreground tabular-nums">
                Showing {filteredEvents.length} of {convertedEvents.length} events
              </div>
            </div>
            
            <EventsTable events={filteredEvents} />
          </div>
        </div>
      </div>
    </div>
  );
}
