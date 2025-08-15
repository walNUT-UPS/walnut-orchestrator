import React, { useState } from 'react';
import { SecondaryToolbar } from '../SecondaryToolbar';
import { MetricCard } from '../MetricCard';
import { EventsTable, Event } from '../EventsTable';
import { StatusPill } from '../StatusPill';
import { LinePower24h, PowerSegment } from '../LinePower24h';
import { cn } from '../ui/utils';
import { useWalnutApi } from '../../hooks/useWalnutApi';

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

// Mock timeline data for 24-hour power status
const mockTimelineSegments: PowerSegment[] = [
  {
    start: new Date(Date.now() - 24 * 60 * 60 * 1000), // 24h ago
    end: new Date(Date.now() - 22 * 60 * 60 * 1000), // 22h ago
    status: 'online' as const,
    meta: { batteryPercent: 100, inputVoltage: 230, loadWatts: 220 }
  },
  {
    start: new Date(Date.now() - 22 * 60 * 60 * 1000), // 22h ago
    end: new Date(Date.now() - 21.8 * 60 * 60 * 1000), // Brief outage
    status: 'on-battery' as const,
    meta: { batteryPercent: 95, inputVoltage: 0, loadWatts: 220 }
  },
  {
    start: new Date(Date.now() - 21.8 * 60 * 60 * 1000),
    end: new Date(Date.now() - 8 * 60 * 60 * 1000), // 8h ago
    status: 'online' as const,
    meta: { batteryPercent: 100, inputVoltage: 230, loadWatts: 245 }
  },
  {
    start: new Date(Date.now() - 8 * 60 * 60 * 1000), // 8h ago
    end: new Date(Date.now() - 7.5 * 60 * 60 * 1000), // 30min outage
    status: 'on-battery' as const,
    meta: { batteryPercent: 87, inputVoltage: 0, loadWatts: 245 }
  },
  {
    start: new Date(Date.now() - 7.5 * 60 * 60 * 1000),
    end: new Date(), // Now
    status: 'online' as const,
    meta: { batteryPercent: 100, inputVoltage: 230, loadWatts: 245 }
  }
];

export function OverviewScreen() {
  const { upsStatus, systemHealth, events, isLoading, error, wsConnected } = useWalnutApi();
  const [searchValue, setSearchValue] = useState('');
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards');
  const [activeFilters, setActiveFilters] = useState<string[]>([]);
  const [timelineDuration, setTimelineDuration] = useState<'6h' | '12h' | '24h'>('24h');
  const availableFilters = ['INFO', 'WARNING', 'CRITICAL', 'UPS', 'Host', 'Policy'];

  const handleFilterToggle = (filter: string) => {
    setActiveFilters(prev => 
      prev.includes(filter) 
        ? prev.filter(f => f !== filter)
        : [...prev, filter]
    );
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

  const filteredEvents = convertedEvents.filter(event => {
    if (activeFilters.length === 0) return true;
    return activeFilters.some(filter => 
      event.severity === filter || event.source === filter
    );
  });

  // Convert UPS status to metrics format
  const upsMetrics = upsStatus ? [
    { 
      label: 'Battery', 
      value: upsStatus.battery_percent || 0, 
      max: 100, 
      unit: '%', 
      status: (upsStatus.battery_percent || 0) > 20 ? 'ok' as const : 'warn' as const 
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
      max: 30, 
      unit: 'min' 
    }
  ] : mockUPSMetrics;

  return (
    <div className="flex-1">
      <SecondaryToolbar
        searchValue={searchValue}
        onSearchChange={setSearchValue}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        activeFilters={activeFilters}
        onFilterToggle={handleFilterToggle}
        availableFilters={availableFilters}
        showCharts={false}
      />

      <div className="container-grid py-6 space-y-6">
        <div className="grid-12">
          {/* Status Banner */}
          <div className="col-span-12">
            <div className="card-standard p-4">
              <div className="flex items-center space-x-4">
                <StatusPill 
                  status={systemHealth?.status === 'healthy' ? 'ok' : systemHealth?.status === 'degraded' ? 'warn' : 'error'} 
                  size="md" 
                />
                <div>
                  <div className="text-title">
                    {isLoading ? 'Loading...' : error ? 'System Error' : systemHealth?.status === 'healthy' ? 'System Online' : 'System Issues Detected'}
                  </div>
                  <div className="text-micro text-muted-foreground tabular-nums">
                    {isLoading ? 'Connecting...' : error ? error : 
                     wsConnected ? 'Live connection active' : 'Last sync: ' + (systemHealth?.timestamp ? new Date(systemHealth.timestamp).toLocaleString() : 'Unknown')}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* 24-Hour Line Power Timeline */}
          <div className="col-span-12">
            <LinePower24h 
              segments={mockTimelineSegments}
              duration={timelineDuration}
              onZoomChange={setTimelineDuration}
              showLegend={true}
            />
          </div>
        </div>

        {/* Metrics Grid */}
        {viewMode === 'cards' && (
          <div className="grid-12">
            <div className="col-span-4">
              <MetricCard
                title="UPS Status"
                status={upsStatus?.status?.includes('OB') ? 'warn' : 'ok'}
                metrics={upsMetrics}
                meta={{
                  uptime: systemHealth ? `${Math.floor(systemHealth.uptime_seconds / 86400)}d ${Math.floor((systemHealth.uptime_seconds % 86400) / 3600)}h` : 'Unknown',
                  lastUpdate: wsConnected ? 'Live' : upsStatus ? new Date(upsStatus.timestamp).toLocaleString() : 'No data',
                  driver: upsStatus?.status || 'Unknown'
                }}
              />
            </div>
            
            <div className="col-span-4">
              <MetricCard
                title="Event Summary (24h)"
                status="warn"
                metrics={[
                  { label: 'OnBattery Events', value: 2, max: 10, unit: '' },
                  { label: 'Recoveries', value: 2, max: 10, unit: '' },
                  { label: 'Low Battery', value: 0, max: 5, unit: '' }
                ]}
                meta={{
                  lastUpdate: '2m ago'
                }}
              />
            </div>

            <div className="col-span-4">
              <MetricCard
                title="Orchestration State"
                status="ok"
                metrics={[
                  { label: 'Active Policies', value: 3, max: 5, unit: '' },
                  { label: 'Pending Actions', value: 0, max: 10, unit: '' },
                  { label: 'Success Rate', value: 98, max: 100, unit: '%', inverse: true }
                ]}
                meta={{
                  lastUpdate: '1m ago'
                }}
              />
            </div>

            <div className="col-span-8">
              <MetricCard
                title="Integration Status"
                status="ok"
                metrics={[
                  { label: 'Proxmox', value: 1, max: 1, unit: ' connected', status: 'ok', inverse: true },
                  { label: 'TrueNAS', value: 1, max: 1, unit: ' connected', status: 'ok', inverse: true },
                  { label: 'Tapo Smart Plugs', value: 3, max: 3, unit: ' connected', status: 'ok', inverse: true }
                ]}
                size="L"
              />
            </div>
          </div>
        )}

        {/* Events Table */}
        <div className="grid-12">
          <div className="col-span-12 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-display">Recent Events</h2>
              <div className="text-micro text-muted-foreground tabular-nums">
                Showing {filteredEvents.length} of {mockEvents.length} events
              </div>
            </div>
            
            <EventsTable events={filteredEvents} />
          </div>
        </div>
      </div>
    </div>
  );
}