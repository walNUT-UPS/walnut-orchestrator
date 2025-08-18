import React, { useState } from 'react';
import { SecondaryToolbar } from '../SecondaryToolbar';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { StatusPill } from '../StatusPill';
import { 
  Settings, 
  Plus, 
  TestTube,
  ExternalLink,
  CheckCircle2,
  AlertTriangle,
  XCircle
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter
} from '../ui/dialog';
import { Input } from '../ui/input';
import { Label } from '../ui/label';

interface Integration {
  id: string;
  name: string;
  type: 'proxmox' | 'truenas' | 'nut-server' | 'tapo' | 'webhook';
  status: 'connected' | 'disconnected' | 'error';
  lastCheck: string;
  version?: string;
  endpoint: string;
  metrics?: {
    label: string;
    value: string;
  }[];
  description: string;
}

const mockIntegrations: Integration[] = [
  {
    id: '1',
    name: 'Proxmox VE',
    type: 'proxmox',
    status: 'connected',
    lastCheck: '2024-01-15T15:42:00Z',
    version: '8.1.4',
    endpoint: 'https://pve.local:8006',
    metrics: [
      { label: 'Nodes', value: '1' },
      { label: 'VMs Running', value: '8' },
      { label: 'Storage', value: '2.1TB free' }
    ],
    description: 'Virtualization platform for VM management and graceful shutdowns'
  },
  {
    id: '2',
    name: 'TrueNAS Scale',
    type: 'truenas',
    status: 'connected',
    lastCheck: '2024-01-15T15:41:30Z',
    version: '24.04',
    endpoint: 'https://truenas.local',
    metrics: [
      { label: 'Pools', value: '2 healthy' },
      { label: 'Datasets', value: '12' },
      { label: 'Services', value: '6 running' }
    ],
    description: 'Network attached storage for backup pause/resume operations'
  },
  {
    id: '3',
    name: 'NUT Server',
    type: 'nut-server',
    status: 'connected',
    lastCheck: '2024-01-15T15:42:15Z',
    endpoint: 'ups.local:3493',
    metrics: [
      { label: 'UPS Devices', value: '1' },
      { label: 'Clients', value: '3' },
      { label: 'Uptime', value: '15d 3h' }
    ],
    description: 'Network UPS Tools daemon providing UPS monitoring data'
  },
  {
    id: '4',
    name: 'Tapo Smart Plugs',
    type: 'tapo',
    status: 'connected',
    lastCheck: '2024-01-15T15:41:45Z',
    endpoint: 'Local Network',
    metrics: [
      { label: 'Devices', value: '3 online' },
      { label: 'Power Draw', value: '145W total' },
      { label: 'Last Action', value: '2h ago' }
    ],
    description: 'Smart plugs for automated device power management'
  },
  {
    id: '5',
    name: 'Webhook Alerts',
    type: 'webhook',
    status: 'error',
    lastCheck: '2024-01-15T15:00:00Z',
    endpoint: 'https://hooks.slack.com/...',
    description: 'Slack webhook for critical event notifications'
  }
];

const integrationIcons = {
  proxmox: '🏗️',
  truenas: '💾',
  'nut-server': '🔋',
  tapo: '🔌',
  webhook: '📢'
};

export function IntegrationsScreen() {
  const [searchValue, setSearchValue] = useState('');
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards');
  const [activeFilters, setActiveFilters] = useState<string[]>([]);
  const [selectedIntegration, setSelectedIntegration] = useState<Integration | null>(null);
  const [testResult, setTestResult] = useState<{ status: 'success' | 'error'; message: string } | null>(null);

  const availableFilters = ['Connected', 'Disconnected', 'Error', 'Proxmox', 'TrueNAS', 'Tapo'];

  const handleFilterToggle = (filter: string) => {
    setActiveFilters(prev => 
      prev.includes(filter) 
        ? prev.filter(f => f !== filter)
        : [...prev, filter]
    );
  };

  const testConnection = async (integration: Integration) => {
    // Simulate API call
    setTestResult(null);
    await new Promise(resolve => setTimeout(resolve, 1500));
    
    const success = Math.random() > 0.3; // 70% success rate
    setTestResult({
      status: success ? 'success' : 'error',
      message: success 
        ? `Successfully connected to ${integration.name}` 
        : `Failed to connect: Connection timeout`
    });
  };

  const openIntegrationUrl = (integration: Integration) => {
    // Open integration web interface if available
    const urls: Record<string, string> = {
      'proxmox': 'https://proxmox.local:8006',
      'truenas': 'https://truenas.local',
      'tapo': 'https://tapo.local',
      'nut-server': 'http://ups.local:3493'
    };
    
    const url = urls[integration.type];
    if (url) {
      window.open(url, '_blank');
    } else {
      alert(`No web interface available for ${integration.name}`);
    }
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / (1000 * 60));
    
    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`;
    return `${Math.floor(diffMins / 1440)}d ago`;
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'connected':
        return <CheckCircle2 className="w-4 h-4 text-status-ok" />;
      case 'disconnected':
        return <AlertTriangle className="w-4 h-4 text-status-warn" />;
      case 'error':
        return <XCircle className="w-4 h-4 text-status-error" />;
      default:
        return null;
    }
  };

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
      />

      <div className="max-w-7xl mx-auto p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-display">Integrations</h1>
            <p className="text-micro text-muted-foreground mt-1">
              Manage external service connections and API endpoints
            </p>
          </div>
          <Button className="bg-status-info hover:bg-status-info/90">
            <Plus className="w-4 h-4 mr-2" />
            Add Integration
          </Button>
        </div>

        {/* Integrations Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {mockIntegrations.map((integration) => (
            <Card 
              key={integration.id} 
              className="bg-card hover:bg-accent/50 transition-colors"
              style={{ boxShadow: 'var(--shadow-card)' }}
            >
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center space-x-2">
                    <div className="text-lg">
                      {integrationIcons[integration.type]}
                    </div>
                    <div>
                      <CardTitle className="text-title">{integration.name}</CardTitle>
                      {integration.version && (
                        <Badge variant="outline" className="mt-1">
                          v{integration.version}
                        </Badge>
                      )}
                    </div>
                  </div>
                  {getStatusIcon(integration.status)}
                </div>
                <p className="text-micro text-muted-foreground">
                  {integration.description}
                </p>
              </CardHeader>
              
              <CardContent className="space-y-4">
                {/* Status */}
                <div className="flex items-center justify-between">
                  <StatusPill 
                    status={integration.status === 'connected' ? 'ok' : 
                            integration.status === 'disconnected' ? 'warn' : 'error'} 
                  >
                    {integration.status === 'connected' ? 'Connected' : 
                     integration.status === 'disconnected' ? 'Disconnected' : 'Error'}
                  </StatusPill>
                  <span className="text-micro text-muted-foreground">
                    {formatTimestamp(integration.lastCheck)}
                  </span>
                </div>

                {/* Endpoint */}
                <div className="space-y-1">
                  <div className="text-micro text-muted-foreground">Endpoint</div>
                  <div className="font-mono text-micro bg-muted/20 px-2 py-1 rounded">
                    {integration.endpoint}
                  </div>
                </div>

                {/* Metrics */}
                {integration.metrics && (
                  <div className="grid grid-cols-3 gap-2 text-micro">
                    {integration.metrics.map((metric, index) => (
                      <div key={index} className="text-center">
                        <div className="text-muted-foreground">{metric.label}</div>
                        <div className="font-medium">{metric.value}</div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Actions */}
                <div className="flex items-center space-x-2 pt-3 border-t border-border">
                  <Dialog>
                    <DialogTrigger asChild>
                      <Button 
                        variant="outline" 
                        size="sm" 
                        className="flex-1"
                        onClick={() => setSelectedIntegration(integration)}
                      >
                        <Settings className="w-3 h-3 mr-1" />
                        Configure
                      </Button>
                    </DialogTrigger>
                    <DialogContent>
                      <DialogHeader>
                        <DialogTitle>Configure {selectedIntegration?.name}</DialogTitle>
                        <DialogDescription>
                          Update connection settings and credentials
                        </DialogDescription>
                      </DialogHeader>
                      
                      <div className="space-y-4 py-4">
                        <div className="space-y-2">
                          <Label htmlFor="endpoint">Endpoint URL</Label>
                          <Input 
                            id="endpoint" 
                            defaultValue={selectedIntegration?.endpoint}
                            placeholder="https://example.com"
                          />
                        </div>
                        
                        <div className="space-y-2">
                          <Label htmlFor="username">Username</Label>
                          <Input id="username" placeholder="admin" />
                        </div>
                        
                        <div className="space-y-2">
                          <Label htmlFor="password">Password/Token</Label>
                          <Input id="password" type="password" placeholder="••••••••" />
                        </div>

                        {testResult && (
                          <div className={`p-3 rounded-lg border ${
                            testResult.status === 'success' 
                              ? 'bg-status-ok/10 border-status-ok text-status-ok'
                              : 'bg-status-error/10 border-status-error text-status-error'
                          }`}>
                            <div className="flex items-center space-x-2">
                              {testResult.status === 'success' ? (
                                <CheckCircle2 className="w-4 h-4" />
                              ) : (
                                <XCircle className="w-4 h-4" />
                              )}
                              <span className="text-sm">{testResult.message}</span>
                            </div>
                          </div>
                        )}
                      </div>

                      <DialogFooter>
                        <Button 
                          variant="outline" 
                          onClick={() => selectedIntegration && testConnection(selectedIntegration)}
                          disabled={!selectedIntegration}
                        >
                          <TestTube className="w-4 h-4 mr-2" />
                          Test Connection
                        </Button>
                        <Button>Save Changes</Button>
                      </DialogFooter>
                    </DialogContent>
                  </Dialog>

                  <Button 
                    variant="outline" 
                    size="sm"
                    onClick={() => testConnection(integration)}
                  >
                    <TestTube className="w-3 h-3 mr-1" />
                    Test
                  </Button>

                  <Button variant="ghost" size="sm" onClick={() => openIntegrationUrl(integration)}>
                    <ExternalLink className="w-3 h-3" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}