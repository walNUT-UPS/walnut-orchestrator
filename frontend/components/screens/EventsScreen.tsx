import React, { useState } from 'react';
import { SecondaryToolbar } from '../SecondaryToolbar';
import { EventsTable, Event } from '../EventsTable';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Calendar, Download, CheckCheck } from 'lucide-react';
import { useConfirm } from '../ui/confirm';
import { toast } from 'sonner';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';

// Extended mock events data
const mockEvents: Event[] = [
  {
    id: '1',
    timestamp: '2024-01-15T14:30:00Z',
    type: 'OnBattery',
    source: 'UPS',
    severity: 'Warning',
    message: 'UPS switched to battery power - utility power lost',
    payload: { voltage: 0, frequency: 0, loadWatts: 245, batteryLevel: 87 },
    relatedHost: 'srv-pbs-01'
  },
  {
    id: '2',
    timestamp: '2024-01-15T14:32:15Z',
    type: 'Recovered',
    source: 'UPS',
    severity: 'Info',
    message: 'Utility power restored, UPS back online',
    payload: { voltage: 230, frequency: 50, loadWatts: 245, batteryLevel: 87 }
  },
  {
    id: '3',
    timestamp: '2024-01-15T13:15:00Z',
    type: 'Test',
    source: 'Policy',
    severity: 'Info',
    message: 'Scheduled battery test completed successfully',
    payload: { testDuration: 30, batteryHealth: 'Good', testResult: 'PASS' }
  },
  {
    id: '4',
    timestamp: '2024-01-15T12:45:00Z',
    type: 'LowBattery',
    source: 'UPS',
    severity: 'Critical',
    message: 'Battery level critical - 15% remaining',
    payload: { batteryLevel: 15, estimatedRuntime: 8, loadWatts: 245 },
    relatedHost: 'srv-pbs-01'
  },
  {
    id: '5',
    timestamp: '2024-01-15T11:20:00Z',
    type: 'Shutdown',
    source: 'Host',
    severity: 'Warning',
    message: 'Host srv-pbs-01 initiated graceful shutdown',
    payload: { hostname: 'srv-pbs-01', shutdownReason: 'UPS_LOW_BATTERY', exitCode: 0 },
    relatedHost: 'srv-pbs-01'
  },
  {
    id: '6',
    timestamp: '2024-01-15T09:00:00Z',
    type: 'ConnectionLost',
    source: 'UPS',
    severity: 'Critical',
    message: 'Lost communication with UPS device',
    payload: { lastSeen: '2024-01-15T08:58:32Z', retryAttempts: 3 }
  }
];

export function EventsScreen() {
  const confirmDialog = useConfirm();
  const [searchValue, setSearchValue] = useState('');
  // Events is always table view
  const [viewMode] = useState<'cards' | 'table'>('table');
  const [activeFilters, setActiveFilters] = useState<string[]>([]);
  const [showFilters, setShowFilters] = useState<boolean>(false);
  const [selectedType, setSelectedType] = useState<string>('all');
  const [selectedSource, setSelectedSource] = useState<string>('all');
  const [selectedSeverity, setSelectedSeverity] = useState<string>('all');
  const [dateRange, setDateRange] = useState<string>('24h');
  const [customStart, setCustomStart] = useState<string>('');
  const [customEnd, setCustomEnd] = useState<string>('');

  const handleExportCSV = () => {
    // Create CSV content from filtered events
    const csvHeaders = ['Timestamp', 'Type', 'Source', 'Severity', 'Message'];
    const csvRows = filteredEvents.map(event => [
      new Date(event.timestamp).toISOString(),
      event.type,
      event.source,
      event.severity,
      `"${event.message.replace(/"/g, '""')}"`
    ]);
    
    const csvContent = [csvHeaders, ...csvRows]
      .map(row => row.join(','))
      .join('\n');
    
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `walnut-events-${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleAcknowledgeAll = async () => {
    const criticalEvents = filteredEvents.filter(event => event.severity === 'Critical').length;
    const warningEvents = filteredEvents.filter(event => event.severity === 'Warning').length;
    if (criticalEvents === 0 && warningEvents === 0) {
      toast.info('No events to acknowledge');
      return;
    }
    const ok = await confirmDialog({
      title: 'Acknowledge events?',
      description: `Acknowledge ${criticalEvents} critical and ${warningEvents} warning events?`,
      confirmText: 'Acknowledge',
    });
    if (ok) {
      toast.info('Event acknowledgment is not implemented yet');
    }
  };

  const availableFilters = ['OnBattery', 'LowBattery', 'Recovered', 'Shutdown', 'Test', 'ConnectionLost'];

  const handleFilterToggle = (filter: string) => {
    setActiveFilters(prev => 
      prev.includes(filter) 
        ? prev.filter(f => f !== filter)
        : [...prev, filter]
    );
  };

  const filteredEvents = mockEvents.filter(event => {
    // Search filter
    if (searchValue && !event.message.toLowerCase().includes(searchValue.toLowerCase()) &&
        !event.type.toLowerCase().includes(searchValue.toLowerCase()) &&
        !event.source.toLowerCase().includes(searchValue.toLowerCase())) {
      return false;
    }

    // Type filter
    if (selectedType !== 'all' && event.type !== selectedType) return false;
    if (selectedSource !== 'all' && event.source !== selectedSource) return false;
    if (selectedSeverity !== 'all' && event.severity !== selectedSeverity) return false;

    // Active filters
    if (activeFilters.length > 0 && !activeFilters.includes(event.type)) return false;

    // Date range
    const ts = new Date(event.timestamp).getTime();
    const now = Date.now();
    let within = true;
    if (dateRange === '1h') within = ts >= now - 3600_000;
    else if (dateRange === '24h') within = ts >= now - 24 * 3600_000;
    else if (dateRange === '7d') within = ts >= now - 7 * 24 * 3600_000;
    else if (dateRange === '30d') within = ts >= now - 30 * 24 * 3600_000;
    else if (dateRange === 'custom') {
      const start = customStart ? new Date(customStart).getTime() : -Infinity;
      const end = customEnd ? new Date(customEnd).getTime() : Infinity;
      within = ts >= start && ts <= end;
    }
    if (!within) return false;

    return true;
  });

  return (
    <div className="flex-1">
      <SecondaryToolbar
        searchValue={searchValue}
        onSearchChange={setSearchValue}
        viewMode={viewMode}
        onViewModeChange={() => {}}
        activeFilters={activeFilters}
        onFilterToggle={handleFilterToggle}
        availableFilters={availableFilters}
        showFilters={showFilters}
        onToggleFilters={() => setShowFilters((s) => !s)}
        showViewToggle={false}
      />

      <div className="max-w-7xl mx-auto p-6 space-y-6">
        {/* Advanced Filters (revealed by Filters toggle) */}
        {showFilters && (
        <div className="bg-card rounded-lg border border-border p-4">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-4">
            <h3 className="text-title">Filters</h3>
            <div className="flex flex-wrap items-center gap-2">
              {/* Date range selection moved below */}
              <Button 
                variant="outline" 
                size="sm" 
                className="shrink-0"
                onClick={handleExportCSV}
              >
                <Download className="w-4 h-4 mr-2" />
                Export CSV
              </Button>
              <Button 
                variant="outline" 
                size="sm" 
                className="shrink-0"
                onClick={handleAcknowledgeAll}
              >
                <CheckCheck className="w-4 h-4 mr-2" />
                Acknowledge All
              </Button>
            </div>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="space-y-2">
              <label className="text-micro text-muted-foreground">Type</label>
              <Select value={selectedType} onValueChange={setSelectedType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Types</SelectItem>
                  <SelectItem value="OnBattery">On Battery</SelectItem>
                  <SelectItem value="LowBattery">Low Battery</SelectItem>
                  <SelectItem value="Recovered">Recovered</SelectItem>
                  <SelectItem value="Shutdown">Shutdown</SelectItem>
                  <SelectItem value="Test">Test</SelectItem>
                  <SelectItem value="ConnectionLost">Connection Lost</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <label className="text-micro text-muted-foreground">Source</label>
              <Select value={selectedSource} onValueChange={setSelectedSource}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Sources</SelectItem>
                  <SelectItem value="UPS">UPS</SelectItem>
                  <SelectItem value="Host">Host</SelectItem>
                  <SelectItem value="Policy">Policy</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <label className="text-micro text-muted-foreground">Severity</label>
              <Select value={selectedSeverity} onValueChange={setSelectedSeverity}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Severities</SelectItem>
                  <SelectItem value="Info">Info</SelectItem>
                  <SelectItem value="Warning">Warning</SelectItem>
                  <SelectItem value="Critical">Critical</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <label className="text-micro text-muted-foreground">Date Range</label>
              <Select value={dateRange} onValueChange={setDateRange}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1h">Last Hour</SelectItem>
                  <SelectItem value="24h">Last 24 Hours</SelectItem>
                  <SelectItem value="7d">Last 7 Days</SelectItem>
                  <SelectItem value="30d">Last 30 Days</SelectItem>
                  <SelectItem value="custom">Custom Range</SelectItem>
                </SelectContent>
              </Select>
              {dateRange === 'custom' && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2">
                  <div className="space-y-1">
                    <label className="text-micro text-muted-foreground">Start</label>
                    <input
                      type="datetime-local"
                      className="border rounded-md px-2 py-1 bg-input-background border-input text-sm"
                      value={customStart}
                      onChange={(e) => setCustomStart(e.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-micro text-muted-foreground">End</label>
                    <input
                      type="datetime-local"
                      className="border rounded-md px-2 py-1 bg-input-background border-input text-sm"
                      value={customEnd}
                      onChange={(e) => setCustomEnd(e.target.value)}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>

          {(selectedType !== 'all' || selectedSource !== 'all' || selectedSeverity !== 'all' || dateRange !== '24h') && (
            <div className="flex items-center space-x-2 mt-4 pt-4 border-t border-border">
              <span className="text-micro text-muted-foreground">Active filters:</span>
              {selectedType !== 'all' && (
                <Badge variant="secondary">Type: {selectedType}</Badge>
              )}
              {selectedSource !== 'all' && (
                <Badge variant="secondary">Source: {selectedSource}</Badge>
              )}
              {selectedSeverity !== 'all' && (
                <Badge variant="secondary">Severity: {selectedSeverity}</Badge>
              )}
              {dateRange !== '24h' && (
                <Badge variant="secondary">Range: {dateRange}</Badge>
              )}
              <Button 
                variant="ghost" 
                size="sm" 
                onClick={() => {
                  setSelectedType('all');
                  setSelectedSource('all');
                  setSelectedSeverity('all');
                  setDateRange('24h');
                }}
                className="h-6 text-xs text-muted-foreground hover:text-foreground"
              >
                Clear all
              </Button>
            </div>
          )}
        </div>
        )}

        {/* Events Table */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-display">Events</h2>
            <div className="text-micro text-muted-foreground">
              Showing {filteredEvents.length} of {mockEvents.length} events
            </div>
          </div>
          
          <EventsTable events={filteredEvents} />
        </div>
      </div>
    </div>
  );
}
