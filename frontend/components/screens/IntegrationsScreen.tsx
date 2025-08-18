import { useState, useEffect } from 'react';
import { SecondaryToolbar } from '../SecondaryToolbar';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { StatusPill } from '../StatusPill';
import { IntegrationFlyout } from '../IntegrationFlyout';
import { 
  Settings, 
  Plus, 
  TestTube,
  ExternalLink,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Link,
  Loader2,
  RefreshCw
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
import { 
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../ui/table';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { apiService, IntegrationType, IntegrationInstance } from '../../services/api';

interface CombinedIntegrationItem {
  id: string;
  name: string;
  display_name: string;
  type_name: string;
  status: 'connected' | 'disconnected' | 'error';
  lastCheck: string;
  version?: string;
  endpoint: string;
  enabled: boolean;
  description: string;
  isInstance: boolean;
  instanceId?: number;
  state?: string;
  capabilities?: string[];
}

// Integration icons mapping
const integrationIcons: Record<string, string> = {
  'walnut.proxmox.ve': '🏗️',
  'walnut.truenas.scale': '💾', 
  'walnut.tapo.smartplug': '🔌',
  'walnut.webhook.slack': '📢',
  'proxmox': '🏗️',
  'truenas': '💾',
  'tapo': '🔌',
  'webhook': '📢'
};

export function IntegrationsScreen() {
  const [searchValue, setSearchValue] = useState('');
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards');
  const [activeFilters, setActiveFilters] = useState<string[]>([]);
  
  // Data state
  const [integrationTypes, setIntegrationTypes] = useState<IntegrationType[]>([]);
  const [integrationInstances, setIntegrationInstances] = useState<IntegrationInstance[]>([]);
  const [combinedItems, setCombinedItems] = useState<CombinedIntegrationItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Dialog state
  const [selectedIntegration, setSelectedIntegration] = useState<CombinedIntegrationItem | null>(null);
  const [addIntegrationDialogOpen, setAddIntegrationDialogOpen] = useState(false);
  const [newConnectionDialogOpen, setNewConnectionDialogOpen] = useState(false);
  const [selectedType, setSelectedType] = useState<IntegrationType | null>(null);
  
  // Integration Flyout state - basic implementation
  const [isFlyoutOpen, setIsFlyoutOpen] = useState(false);
  const [selectedIntegrationForFlyout, setSelectedIntegrationForFlyout] = useState<any>(null);
  const [flyoutMode, setFlyoutMode] = useState<'create' | 'edit'>('create');
  
  // Test function to open Integration Flyout
  const handleTestFlyout = () => {
    const mockIntegration = {
      name: 'walnut.proxmox.ve',
      displayName: 'Proxmox VE',
      fields: [
        { name: 'host', label: 'Host', type: 'text' as const, required: true, placeholder: 'Enter Proxmox host' },
        { name: 'port', label: 'Port', type: 'number' as const, defaultValue: 8006 },
        { name: 'username', label: 'Username', type: 'text' as const, required: true, placeholder: 'root' },
        { name: 'password', label: 'Password', type: 'password' as const, required: true },
        { name: 'node', label: 'Node', type: 'text' as const, required: true, placeholder: 'pve' },
        { name: 'verifySSL', label: 'Verify SSL Certificate', type: 'boolean' as const, defaultValue: true },
        { name: 'timeout', label: 'Connection Timeout (seconds)', type: 'number' as const, defaultValue: 30 },
        { name: 'retries', label: 'Retry Attempts', type: 'number' as const, defaultValue: 3 },
        { name: 'heartbeatInterval', label: 'Heartbeat Interval (seconds)', type: 'number' as const, defaultValue: 60 },
      ]
    };
    
    setSelectedIntegrationForFlyout(mockIntegration);
    setFlyoutMode('create');
    setIsFlyoutOpen(true);
  };
  
  // Form state
  const [testResult, setTestResult] = useState<{ status: 'success' | 'error'; message: string } | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [newInstanceForm, setNewInstanceForm] = useState({
    name: '',
    display_name: '',
    config: {} as Record<string, any>,
    secrets: {} as Record<string, string>
  });

  const availableFilters = ['Connected', 'Disconnected', 'Error', 'Instances Only', 'Types Only'];

  // Load data from API
  const loadData = async () => {
    try {
      setIsLoading(true);
      setError(null);
      
      const [types, instances] = await Promise.all([
        apiService.getIntegrationTypes().catch(() => []),
        apiService.getIntegrationInstances().catch(() => [])
      ]);
      
      setIntegrationTypes(types);
      setIntegrationInstances(instances);
      
      // Combine types and instances into a unified view
      const combined: CombinedIntegrationItem[] = [];
      
      // Add integration instances (configured connections)
      for (const instance of instances) {
        const type = types.find(t => t.name === instance.type_name);
        combined.push({
          id: `instance-${instance.id}`,
          name: instance.display_name,
          display_name: instance.display_name,
          type_name: instance.type_name,
          status: instance.health_status === 'healthy' ? 'connected' : 
                 instance.health_status === 'unhealthy' ? 'error' : 'disconnected',
          lastCheck: new Date().toISOString(), // TODO: get from health tracking
          version: type?.version,
          endpoint: instance.config.host ? `${instance.config.host}:${instance.config.port || ''}` : 'Configured',
          enabled: instance.enabled,
          description: type?.description || 'Integration instance',
          isInstance: true,
          instanceId: instance.id,
          state: instance.state,
          capabilities: type?.capabilities.map((c: any) => c.id) || []
        });
      }
      
      setCombinedItems(combined);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load integrations');
    } finally {
      setIsLoading(false);
    }
  };
  
  useEffect(() => {
    loadData();
  }, []);
  
  const handleFilterToggle = (filter: string) => {
    setActiveFilters(prev => 
      prev.includes(filter) 
        ? prev.filter(f => f !== filter)
        : [...prev, filter]
    );
  };
  
  // Filter combined items based on active filters and search
  const filteredItems = combinedItems.filter(item => {
    // Search filter
    if (searchValue && !item.name.toLowerCase().includes(searchValue.toLowerCase()) && 
        !item.type_name.toLowerCase().includes(searchValue.toLowerCase())) {
      return false;
    }
    
    // Status filters
    if (activeFilters.includes('Connected') && item.status !== 'connected') return false;
    if (activeFilters.includes('Disconnected') && item.status !== 'disconnected') return false;
    if (activeFilters.includes('Error') && item.status !== 'error') return false;
    if (activeFilters.includes('Instances Only') && !item.isInstance) return false;
    if (activeFilters.includes('Types Only') && item.isInstance) return false;
    
    return true;
  });

  const testConnection = async (integration: CombinedIntegrationItem) => {
    if (!integration.isInstance || !integration.instanceId) return;
    
    setTestResult(null);
    try {
      const result = await apiService.testIntegrationInstance(integration.instanceId);
      setTestResult({
        status: result.status === 'success' ? 'success' : 'error',
        message: result.message
      });
    } catch (error) {
      setTestResult({
        status: 'error',
        message: error instanceof Error ? error.message : 'Failed to test connection'
      });
    }
  };

  const openIntegrationUrl = (integration: CombinedIntegrationItem) => {
    if (!integration.isInstance) return;
    
    const instance = integrationInstances.find(i => i.id === integration.instanceId);
    if (!instance) return;
    
    const config = instance.config;
    let url = '';
    
    if (config.host) {
      const protocol = config.verify_ssl !== false ? 'https' : 'http';
      const port = config.port ? `:${config.port}` : '';
      url = `${protocol}://${config.host}${port}`;
    }
    
    if (url) {
      window.open(url, '_blank');
    } else {
      alert(`No web interface configured for ${integration.name}`);
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

  const handleAddIntegration = async () => {
    try {
      await apiService.syncIntegrationTypes();
      await loadData();
      setAddIntegrationDialogOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sync integration types');
    }
  };
  
  const handleCreateInstance = async () => {
    if (!selectedType) return;
    
    try {
      setIsCreating(true);
      await apiService.createIntegrationInstance({
        type_name: selectedType.name,
        name: newInstanceForm.name,
        display_name: newInstanceForm.display_name,
        config: newInstanceForm.config,
        secrets: newInstanceForm.secrets,
        enabled: true
      });
      
      await loadData();
      setNewConnectionDialogOpen(false);
      setNewInstanceForm({ name: '', display_name: '', config: {}, secrets: {} });
      setSelectedType(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create integration instance');
    } finally {
      setIsCreating(false);
    }
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
  
  const getIntegrationIcon = (typeName: string) => {
    return integrationIcons[typeName] || integrationIcons[typeName.replace('walnut.', '').split('.')[0]] || '🔧';
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
              Manage integration types and configured connections
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={loadData} disabled={isLoading}>
              <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            <Dialog open={addIntegrationDialogOpen} onOpenChange={setAddIntegrationDialogOpen}>
              <DialogTrigger asChild>
                <Button className="bg-status-info hover:bg-status-info/90">
                  <Plus className="w-4 h-4 mr-2" />
                  Add Integration
                </Button>
              </DialogTrigger>
            </Dialog>
            <Dialog open={newConnectionDialogOpen} onOpenChange={setNewConnectionDialogOpen}>
              <DialogTrigger asChild>
                <Button variant="outline">
                  <Link className="w-4 h-4 mr-2" />
                  New Target
                </Button>
              </DialogTrigger>
            </Dialog>
          </div>
        </div>

        {/* Loading State */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
            <span className="ml-2 text-muted-foreground">Loading integrations...</span>
          </div>
        )}
        
        {/* Error State */}
        {error && (
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <XCircle className="w-12 h-12 text-status-error mx-auto mb-4" />
              <h3 className="text-lg font-semibold mb-2">Error Loading Integrations</h3>
              <p className="text-muted-foreground mb-4">{error}</p>
              <Button onClick={loadData} variant="outline">
                <RefreshCw className="w-4 h-4 mr-2" />
                Try Again
              </Button>
            </div>
          </div>
        )}
        
        {/* Empty State */}
        {!isLoading && !error && filteredItems.length === 0 && (
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <div className="w-12 h-12 rounded-lg bg-muted flex items-center justify-center mx-auto mb-4">
                <Plus className="w-6 h-6 text-muted-foreground" />
              </div>
              <h3 className="text-lg font-semibold mb-2">No Integrations</h3>
              <p className="text-muted-foreground mb-4">
                {combinedItems.length === 0 
                  ? 'Get started by adding your first integration type or creating a connection.'
                  : 'No integrations match your current filters.'}
              </p>
              {combinedItems.length === 0 && (
                <div className="flex gap-2 justify-center">
                  <Button onClick={handleTestFlyout}>
                    <Plus className="w-4 h-4 mr-2" />
                    Add Integration
                  </Button>
                </div>
              )}
            </div>
          </div>
        )}
        
        {/* Cards View */}
        {!isLoading && !error && filteredItems.length > 0 && viewMode === 'cards' && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredItems.map((integration) => (
              <Card 
                key={integration.id} 
                className="bg-card hover:bg-accent/50 transition-colors"
                style={{ boxShadow: 'var(--shadow-card)' }}
              >
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center space-x-2">
                      <div className="text-lg">
                        {getIntegrationIcon(integration.type_name)}
                      </div>
                      <div className="min-w-0 flex-1">
                        <CardTitle className="text-title truncate">{integration.name}</CardTitle>
                        <div className="flex items-center gap-2 mt-1">
                          {integration.version && (
                            <Badge variant="outline" className="text-xs">
                              v{integration.version}
                            </Badge>
                          )}
                          {integration.isInstance && (
                            <Badge variant="secondary" className="text-xs">
                              Instance
                            </Badge>
                          )}
                        </div>
                      </div>
                    </div>
                    {getStatusIcon(integration.status)}
                  </div>
                  <p className="text-micro text-muted-foreground line-clamp-2">
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

                  {/* Type and Endpoint */}
                  <div className="space-y-2">
                    <div className="space-y-1">
                      <div className="text-micro text-muted-foreground">Type</div>
                      <div className="text-micro font-medium">
                        {integration.type_name}
                      </div>
                    </div>
                    {integration.endpoint && (
                      <div className="space-y-1">
                        <div className="text-micro text-muted-foreground">Endpoint</div>
                        <div className="font-mono text-micro bg-muted/20 px-2 py-1 rounded truncate">
                          {integration.endpoint}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Capabilities */}
                  {integration.capabilities && integration.capabilities.length > 0 && (
                    <div className="space-y-1">
                      <div className="text-micro text-muted-foreground">Capabilities</div>
                      <div className="flex flex-wrap gap-1">
                        {integration.capabilities.slice(0, 3).map((cap, index) => (
                          <Badge key={index} variant="outline" className="text-xs">
                            {cap.replace('.', ' ')}
                          </Badge>
                        ))}
                        {integration.capabilities.length > 3 && (
                          <Badge variant="outline" className="text-xs">
                            +{integration.capabilities.length - 3} more
                          </Badge>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Actions */}
                  {integration.isInstance && (
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
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
        
        {/* Table View */}
        {!isLoading && !error && filteredItems.length > 0 && viewMode === 'table' && (
          <div className="border rounded-lg">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12"></TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Endpoint</TableHead>
                  <TableHead>Version</TableHead>
                  <TableHead>Capabilities</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredItems.map((integration) => (
                  <TableRow key={integration.id} className="hover:bg-muted/50">
                    <TableCell>
                      <div className="text-lg">
                        {getIntegrationIcon(integration.type_name)}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="space-y-1">
                        <div className="font-medium">{integration.name}</div>
                        <div className="flex items-center gap-1">
                          {integration.isInstance && (
                            <Badge variant="secondary" className="text-xs">
                              Instance
                            </Badge>
                          )}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="font-mono text-sm">{integration.type_name}</div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {getStatusIcon(integration.status)}
                        <StatusPill 
                          status={integration.status === 'connected' ? 'ok' : 
                                  integration.status === 'disconnected' ? 'warn' : 'error'} 
                        >
                          {integration.status === 'connected' ? 'Connected' : 
                           integration.status === 'disconnected' ? 'Disconnected' : 'Error'}
                        </StatusPill>
                      </div>
                    </TableCell>
                    <TableCell>
                      {integration.endpoint && (
                        <div className="font-mono text-sm max-w-48 truncate">
                          {integration.endpoint}
                        </div>
                      )}
                    </TableCell>
                    <TableCell>
                      {integration.version && (
                        <Badge variant="outline" className="text-xs">
                          v{integration.version}
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      {integration.capabilities && (
                        <div className="flex flex-wrap gap-1 max-w-48">
                          {integration.capabilities.slice(0, 2).map((cap, index) => (
                            <Badge key={index} variant="outline" className="text-xs">
                              {cap.replace('.', ' ')}
                            </Badge>
                          ))}
                          {integration.capabilities.length > 2 && (
                            <Badge variant="outline" className="text-xs">
                              +{integration.capabilities.length - 2}
                            </Badge>
                          )}
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      {integration.isInstance ? (
                        <div className="flex items-center justify-end gap-1">
                          <Button 
                            variant="ghost" 
                            size="sm"
                            onClick={() => testConnection(integration)}
                          >
                            <TestTube className="w-3 h-3" />
                          </Button>
                          <Button 
                            variant="ghost" 
                            size="sm"
                            onClick={() => openIntegrationUrl(integration)}
                          >
                            <ExternalLink className="w-3 h-3" />
                          </Button>
                          <Button 
                            variant="ghost" 
                            size="sm"
                            onClick={() => setSelectedIntegration(integration)}
                          >
                            <Settings className="w-3 h-3" />
                          </Button>
                        </div>
                      ) : (
                        <div className="text-muted-foreground text-sm">-</div>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {/* Add Integration Dialog */}
        <Dialog open={addIntegrationDialogOpen} onOpenChange={setAddIntegrationDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Integration Type</DialogTitle>
              <DialogDescription>
                Sync integration types from manifest files to make them available for connections.
              </DialogDescription>
            </DialogHeader>
            
            <div className="py-4">
              <div className="space-y-4">
                <div className="bg-muted/20 p-4 rounded-lg">
                  <h4 className="font-medium mb-2">What this does:</h4>
                  <ul className="text-sm text-muted-foreground space-y-1">
                    <li>• Scans the integrations/manifests directory</li>
                    <li>• Registers new integration types (like Proxmox VE, TrueNAS)</li>
                    <li>• Updates existing types to latest versions</li>
                    <li>• Makes them available for creating connections</li>
                  </ul>
                </div>
                
                {integrationTypes.length > 0 && (
                  <div>
                    <h4 className="font-medium mb-2">Currently Available Types:</h4>
                    <div className="space-y-2 max-h-32 overflow-y-auto">
                      {integrationTypes.map((type) => (
                        <div key={type.name} className="flex items-center justify-between text-sm">
                          <span>{type.name}</span>
                          <Badge variant="outline">v{type.version}</Badge>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setAddIntegrationDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleAddIntegration}>
                Sync Integration Types
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        
        {/* New Connection Dialog */}
        <Dialog open={newConnectionDialogOpen} onOpenChange={setNewConnectionDialogOpen}>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Create New Target</DialogTitle>
              <DialogDescription>
                Create a configured target instance of an integration type.
              </DialogDescription>
            </DialogHeader>
            
            <div className="space-y-4 py-4">
              {/* Step 1: Select Integration Type */}
              <div className="space-y-2">
                <Label>Integration Type</Label>
                <Select value={selectedType?.name || ''} onValueChange={(value) => {
                  const type = integrationTypes.find(t => t.name === value);
                  setSelectedType(type || null);
                }}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select an integration type" />
                  </SelectTrigger>
                  <SelectContent>
                    {integrationTypes.map((type) => (
                      <SelectItem key={type.name} value={type.name}>
                        <div className="flex items-center gap-2">
                          <span>{getIntegrationIcon(type.name)}</span>
                          <span>{type.name}</span>
                          <Badge variant="outline" className="ml-auto text-xs">
                            v{type.version}
                          </Badge>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              
              {selectedType && (
                <>
                  {/* Step 2: Basic Info */}
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="instance-name">Instance Name</Label>
                      <Input 
                        id="instance-name"
                        value={newInstanceForm.name}
                        onChange={(e) => setNewInstanceForm(prev => ({...prev, name: e.target.value}))}
                        placeholder="e.g., pve-01, lab-truenas"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="display-name">Display Name</Label>
                      <Input 
                        id="display-name"
                        value={newInstanceForm.display_name}
                        onChange={(e) => setNewInstanceForm(prev => ({...prev, display_name: e.target.value}))}
                        placeholder="e.g., Lab Proxmox, Main TrueNAS"
                      />
                    </div>
                  </div>
                  
                  {/* Step 3: Configuration Fields */}
                  {selectedType.config_fields.length > 0 && (
                    <div className="space-y-2">
                      <Label>Configuration</Label>
                      <div className="grid grid-cols-2 gap-4">
                        {selectedType.config_fields.map((field) => (
                          <div key={field.name} className="space-y-1">
                            <Label htmlFor={`config-${field.name}`}>
                              {field.title || field.name}
                              {field.required && <span className="text-destructive">*</span>}
                            </Label>
                            <Input 
                              id={`config-${field.name}`}
                              type={field.type === 'integer' ? 'number' : 'text'}
                              placeholder={field.default?.toString() || ''}
                              value={newInstanceForm.config[field.name] || ''}
                              onChange={(e) => {
                                const value = field.type === 'integer' ? parseInt(e.target.value) : e.target.value;
                                setNewInstanceForm(prev => ({
                                  ...prev, 
                                  config: {...prev.config, [field.name]: value}
                                }));
                              }}
                            />
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {/* Step 4: Secret Fields */}
                  {selectedType.secret_fields.length > 0 && (
                    <div className="space-y-2">
                      <Label>Secrets</Label>
                      <div className="grid grid-cols-1 gap-4">
                        {selectedType.secret_fields.map((field) => (
                          <div key={field.name} className="space-y-1">
                            <Label htmlFor={`secret-${field.name}`}>
                              {field.title || field.name}
                            </Label>
                            <Input 
                              id={`secret-${field.name}`}
                              type="password"
                              placeholder="Enter secret value"
                              value={newInstanceForm.secrets[field.name] || ''}
                              onChange={(e) => setNewInstanceForm(prev => ({
                                ...prev, 
                                secrets: {...prev.secrets, [field.name]: e.target.value}
                              }))}
                            />
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => {
                setNewConnectionDialogOpen(false);
                setSelectedType(null);
                setNewInstanceForm({ name: '', display_name: '', config: {}, secrets: {} });
              }}>
                Cancel
              </Button>
              <Button 
                onClick={handleCreateInstance} 
                disabled={!selectedType || !newInstanceForm.name || !newInstanceForm.display_name || isCreating}
              >
                {isCreating ? (
                  <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Creating...</>
                ) : (
                  <>Create Target</>
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        
        {/* Integration Flyout - Basic Implementation */}
        <IntegrationFlyout
          isOpen={isFlyoutOpen}
          onClose={() => setIsFlyoutOpen(false)}
          integration={selectedIntegrationForFlyout}
          mode={flyoutMode}
          initialData={undefined}
        />
        
      </div>
    </div>
  );
}