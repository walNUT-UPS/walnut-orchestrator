import React, { useEffect, useMemo, useState } from 'react';
import { MetricCard } from '../MetricCard';
import { EventsTable, Event } from '../EventsTable';
import { StatusPill } from '../StatusPill';
import { LinePower24h, PowerSegment } from '../LinePower24h';
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
  const [viewMode] = useState<'cards' | 'table'>('cards');
  const [timelineDuration, setTimelineDuration] = useState<'6h' | '12h' | '24h'>('24h');
  const [types, setTypes] = useState<IntegrationType[]>([]);
  const [instances, setInstances] = useState<IntegrationInstance[]>([]);
  // Overview has no filters/search controls

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

  // Convert UPS status to metrics format
  const upsMetrics = upsStatus ? [
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
  ] : mockUPSMetrics;

  return (
    <div className="flex-1">
      {/* No secondary toolbar on Overview */}

      <div className="container-grid py-6 space-y-6">
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
                     systemHealth.status === 'degraded' ? 'System Degraded' : 'System Issues Detected'}
                  </div>
                  <div className="text-micro text-muted-foreground tabular-nums">
                    {isLoading ? 'Establishing secure connection...' : 
                     error ? 'Check network connection and try refreshing' : 
                     wsConnected ? 'Live data stream active' : 
                     systemHealth?.timestamp ? `Last sync: ${new Date(systemHealth.timestamp).toLocaleString()}` : 
                     'Waiting for first data sync'}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* 24-Hour Line Power Timeline */}
          <div className="col-span-12">
            <LinePower24h 
              segments={buildTimelineFromEvents(
                filteredEvents,
                timelineDuration === '6h' ? 6 : timelineDuration === '12h' ? 12 : 24
              )}
              duration={timelineDuration}
              onZoomChange={setTimelineDuration}
              showLegend={true}
              className="mb-6"
            />
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
                  status={upsStatus?.status?.includes('OB') ? 'warn' : 'ok'}
                  metrics={upsMetrics}
                  meta={{
                    uptime: systemHealth && systemHealth.uptime_seconds ? 
                      `${Math.floor(systemHealth.uptime_seconds / 86400)}d ${Math.floor((systemHealth.uptime_seconds % 86400) / 3600)}h` : 
                      isLoading ? 'Loading...' : '—',
                    lastUpdate: wsConnected ? 'Live data' : 
                      upsStatus ? new Date(upsStatus.timestamp).toLocaleString() : 
                      isLoading ? 'Connecting...' : 'Waiting for data',
                    driver: upsStatus?.status ? 
                      upsStatus.status.replace('OL', 'Online').replace('OB', 'On Battery').replace('CHRG', 'Charging') : 
                      isLoading ? 'Detecting...' : 'Not connected'
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
