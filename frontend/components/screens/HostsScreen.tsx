import React, { useState, useEffect } from 'react';
import { SecondaryToolbar } from '../SecondaryToolbar';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { 
  Plus, 
  Server,
  TestTube,
  Settings,
  Trash2,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Loader2,
  RefreshCw,
  Calendar,
  Clock,
  Zap,
  Eye
} from 'lucide-react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../ui/table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu';
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Switch } from '../ui/switch';
import { Textarea } from '../ui/textarea';
import { apiService, IntegrationType, IntegrationInstance } from '../../services/api';
import { toast } from 'sonner';
import { useConfirm } from '../ui/confirm';
import { DetailsDrawer } from '../hosts/DetailsDrawer';

// Schema field component for rendering form fields from JSON Schema
interface SchemaFieldProps {
  field: any;
  value: any;
  onChange: (value: any) => void;
  isSecret?: boolean;
}

function SchemaField({ field, value, onChange, isSecret = false }: SchemaFieldProps) {
  const fieldType = field.type || 'string';
  const isRequired = field.required || false;
  const title = field.title || field.name || 'Field';
  const placeholder = field.placeholder || field.default?.toString() || '';

  switch (fieldType) {
    case 'string':
      return (
        <div className="space-y-2">
          <Label htmlFor={field.name}>
            {title}
            {isRequired && <span className="text-destructive ml-1">*</span>}
          </Label>
          <Input
            id={field.name}
            type={isSecret ? 'password' : 'text'}
            placeholder={placeholder}
            value={value || ''}
            onChange={(e) => onChange(e.target.value)}
            required={isRequired}
          />
          {field.description && (
            <p className="text-xs text-muted-foreground">{field.description}</p>
          )}
        </div>
      );
    
    case 'integer':
    case 'number':
      return (
        <div className="space-y-2">
          <Label htmlFor={field.name}>
            {title}
            {isRequired && <span className="text-destructive ml-1">*</span>}
          </Label>
          <Input
            id={field.name}
            type="number"
            placeholder={placeholder}
            value={value || ''}
            onChange={(e) => onChange(fieldType === 'integer' ? parseInt(e.target.value) || 0 : parseFloat(e.target.value) || 0)}
            required={isRequired}
          />
          {field.description && (
            <p className="text-xs text-muted-foreground">{field.description}</p>
          )}
        </div>
      );
    
    case 'boolean':
      return (
        <div className="space-y-2">
          <div className="flex items-center space-x-2">
            <Switch
              id={field.name}
              checked={typeof value === 'boolean' ? value : (field.default ?? false)}
              onCheckedChange={(checked) => onChange(checked)}
            />
            <Label htmlFor={field.name}>
              {title}
              {isRequired && <span className="text-destructive ml-1">*</span>}
            </Label>
          </div>
          {field.description && (
            <p className="text-xs text-muted-foreground">{field.description}</p>
          )}
        </div>
      );
    
    default:
      return (
        <div className="space-y-2">
          <Label htmlFor={field.name}>
            {title} (unsupported type: {fieldType})
            {isRequired && <span className="text-destructive ml-1">*</span>}
          </Label>
          <Input
            id={field.name}
            placeholder={placeholder}
            value={value || ''}
            onChange={(e) => onChange(e.target.value)}
            disabled
          />
        </div>
      );
  }
}

export function HostsScreen() {
  const [searchValue, setSearchValue] = useState('');
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('table');
  const [activeFilters, setActiveFilters] = useState<string[]>([]);
  const confirmDialog = useConfirm();
  
  // Data state
  const [integrationTypes, setIntegrationTypes] = useState<IntegrationType[]>([]);
  const [integrationInstances, setIntegrationInstances] = useState<IntegrationInstance[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsInstance, setSettingsInstance] = useState<IntegrationInstance | null>(null);
  const [isEditingConfig, setIsEditingConfig] = useState(false);
  const [editConfigText, setEditConfigText] = useState('');
  const [editError, setEditError] = useState<string | null>(null);
  
  // New Host dialog state
  const [newHostDialogOpen, setNewHostDialogOpen] = useState(false);
  const [selectedType, setSelectedType] = useState<IntegrationType | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    config: {} as Record<string, any>,
    secrets: {} as Record<string, string>
  });

  // Details drawer state
  const [detailsDrawerOpen, setDetailsDrawerOpen] = useState(false);
  const [detailsInstance, setDetailsInstance] = useState<IntegrationInstance | null>(null);

  const availableFilters = ['Connected', 'Disconnected', 'Error', 'Degraded'];

  // Load data and return latest arrays for callers that need them
  const loadData = async (): Promise<{ types: IntegrationType[]; instances: IntegrationInstance[] }> => {
    try {
      setIsLoading(true);
      setError(null);
      
      const [types, instances] = await Promise.all([
        apiService.getIntegrationTypes(),
        apiService.getIntegrationInstances()
      ]);
      
      // Only allow creating instances for VALID types
      setIntegrationTypes(types.filter(t => t.status === 'valid'));
      setIntegrationInstances(instances);
      return { types, instances };
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
      return { types: [], instances: [] };
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

  // Filter instances based on active filters and search
  const filteredInstances = integrationInstances.filter(instance => {
    // Search filter
    if (searchValue && !instance.name.toLowerCase().includes(searchValue.toLowerCase()) &&
        !instance.type_id.toLowerCase().includes(searchValue.toLowerCase()) &&
        !(instance.type_name || '').toLowerCase().includes(searchValue.toLowerCase())) {
      return false;
    }
    
    // Status filters
    if (activeFilters.includes('Connected') && instance.state !== 'connected') return false;
    if (activeFilters.includes('Disconnected') && instance.state !== 'disconnected') return false;
    if (activeFilters.includes('Error') && instance.state !== 'error') return false;
    if (activeFilters.includes('Degraded') && instance.state !== 'degraded') return false;
    
    return true;
  });

  const handleCreateHost = async () => {
    if (!selectedType) return;
    
    try {
      setIsCreating(true);
      
      // Merge defaults for any non-secret fields not explicitly set
      let mergedConfig: Record<string, any> = { ...formData.config };
      const props = (selectedType as any)?.schema_connection?.properties as Record<string, any> | undefined;
      if (props) {
        Object.entries(props).forEach(([name, schema]: [string, any]) => {
          if (schema.secret === true) return;
          if (mergedConfig[name] === undefined && schema.default !== undefined) {
            mergedConfig[name] = schema.default;
          }
        });
      }

      const instanceData = {
        type_id: selectedType.id,
        name: formData.name,
        config: mergedConfig,
        secrets: formData.secrets
      };
      
      await apiService.createIntegrationInstance(instanceData);
      
      toast.success(`Host "${formData.name}" created successfully`);
      setNewHostDialogOpen(false);
      resetForm();
      await loadData(); // Reload to show new instance
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to create host');
    } finally {
      setIsCreating(false);
    }
  };

  const resetForm = () => {
    setSelectedType(null);
    setFormData({
      name: '',
      config: {},
      secrets: {}
    });
  };

  const handleTypeChange = (typeId: string) => {
    const type = integrationTypes.find(t => t.id === typeId) || null;
    setSelectedType(type);
    let seededConfig: Record<string, any> = {};
    const props = (type as any)?.schema_connection?.properties as Record<string, any> | undefined;
    if (props) {
      Object.entries(props).forEach(([name, schema]: [string, any]) => {
        if (schema.secret === true) return;
        if (schema.default !== undefined) {
          seededConfig[name] = schema.default;
        }
      });
    }
    setFormData(prev => ({ ...prev, config: seededConfig, secrets: {} }));
  };

  const handleConfigChange = (fieldName: string, value: any) => {
    setFormData(prev => ({
      ...prev,
      config: {
        ...prev.config,
        [fieldName]: value
      }
    }));
  };

  const handleSecretChange = (fieldName: string, value: string) => {
    setFormData(prev => ({
      ...prev,
      secrets: {
        ...prev.secrets,
        [fieldName]: value
      }
    }));
  };

  const handleTestInstance = async (instanceId: number) => {
    try {
      setTestingId(instanceId);
      const result = await apiService.testIntegrationInstance(instanceId);
      if (result.success) {
        toast.success(`Connection test successful (${result.latency_ms}ms)`);
      } else {
        toast.error(`Connection test failed: ${result.message}`);
      }
      const { instances } = await loadData(); // Refresh list and get latest
      // If settings dialog is open for this instance, refresh it with latest data
      if (settingsOpen) {
        const refreshed = instances.find(i => i.instance_id === instanceId);
        if (refreshed) setSettingsInstance(refreshed);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Test failed');
    } finally {
      setTestingId(null);
    }
  };

  const handleDeleteInstance = async (instanceId: number, instanceName: string) => {
    const ok = await confirmDialog({
      title: 'Delete host?',
      description: `Delete host "${instanceName}"? This action cannot be undone.`,
      confirmText: 'Delete',
      destructive: true,
    });
    if (!ok) return;
    
    try {
      await apiService.deleteIntegrationInstance(instanceId);
      toast.success(`Host "${instanceName}" deleted`);
      await loadData(); // Refresh list
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to delete host');
    }
  };

  const handleShowDetails = (instance: IntegrationInstance) => {
    setDetailsInstance(instance);
    setDetailsDrawerOpen(true);
  };

  const openEditConfig = (instance: IntegrationInstance) => {
    setIsEditingConfig(true);
    setEditError(null);
    setEditConfigText(JSON.stringify(instance.config ?? {}, null, 2));
  };

  const cancelEditConfig = () => {
    setIsEditingConfig(false);
    setEditError(null);
    setEditConfigText('');
  };

  const saveEditedConfig = async () => {
    if (!settingsInstance) return;
    try {
      setEditError(null);
      // Validate JSON
      const parsed = JSON.parse(editConfigText);
      const updated = await apiService.updateIntegrationInstance(settingsInstance.instance_id, { config: parsed });
      toast.success('Configuration updated');
      // Update local dialog state and list
      setSettingsInstance(updated);
      setIsEditingConfig(false);
      await loadData();
    } catch (err: any) {
      if (err instanceof SyntaxError) {
        setEditError('Invalid JSON: ' + err.message);
      } else {
        setEditError(err?.message || 'Failed to update configuration');
      }
    }
  };

  const getStatusIcon = (state: string) => {
    switch (state) {
      case 'connected':
        return <CheckCircle2 className="w-4 h-4 text-status-ok" />;
      case 'degraded':
        return <AlertTriangle className="w-4 h-4 text-status-warn" />;
      case 'error':
        return <XCircle className="w-4 h-4 text-status-error" />;
      default:
        return <XCircle className="w-4 h-4 text-muted-foreground" />;
    }
  };

  const getStatusBadge = (state: string) => {
    switch (state) {
      case 'connected':
        return <Badge className="bg-status-ok/10 text-status-ok border-status-ok">Connected</Badge>;
      case 'degraded':
        return <Badge className="bg-status-warn/10 text-status-warn border-status-warn">Degraded</Badge>;
      case 'error':
        return <Badge className="bg-status-error/10 text-status-error border-status-error">Error</Badge>;
      case 'unknown':
        return <Badge variant="outline">Unknown</Badge>;
      case 'needs_review':
        return <Badge className="bg-status-warn/10 text-status-warn border-status-warn">Needs Review</Badge>;
      case 'type_unavailable':
        return <Badge variant="outline">Type Unavailable</Badge>;
      default:
        return <Badge variant="outline">{state}</Badge>;
    }
  };

  const formatTimestamp = (timestamp?: string) => {
    if (!timestamp) return 'Never';
    
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / (1000 * 60));
    
    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`;
    return `${Math.floor(diffMins / 1440)}d ago`;
  };

  // Render form fields from schema
  const renderSchemaFields = (schema: any, isSecret: boolean = false) => {
    if (!schema || !schema.properties) return null;

    const entries = Object.entries(schema.properties).filter(([_, fieldSchema]: [string, any]) => {
      const isFieldSecret = fieldSchema && fieldSchema.secret === true;
      return isSecret ? isFieldSecret : !isFieldSecret;
    });

    return entries.map(([name, fieldSchema]: [string, any]) => {
      const fieldWithName = { ...fieldSchema, name };
      const currentValue = isSecret ? formData.secrets[name] : formData.config[name];
      return (
        <SchemaField
          key={name}
          field={fieldWithName}
          value={currentValue}
          onChange={(value) => isSecret ? handleSecretChange(name, value) : handleConfigChange(name, value)}
          isSecret={isSecret}
        />
      );
    });
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
            <h1 className="text-display">Hosts</h1>
            <p className="text-micro text-muted-foreground mt-1">
              Manage host connections using integration types
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={loadData} disabled={isLoading}>
              <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            <Dialog open={newHostDialogOpen} onOpenChange={setNewHostDialogOpen}>
              <DialogTrigger asChild>
                <Button onClick={() => resetForm()}>
                  <Plus className="w-4 h-4 mr-2" />
                  New Host
                </Button>
              </DialogTrigger>
            </Dialog>
          </div>
        </div>

        {/* Loading State */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
            <span className="ml-2 text-muted-foreground">Loading hosts...</span>
          </div>
        )}
        
        {/* Error State */}
        {error && (
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <XCircle className="w-12 h-12 text-status-error mx-auto mb-4" />
              <h3 className="text-lg font-semibold mb-2">Error Loading Hosts</h3>
              <p className="text-muted-foreground mb-4">{error}</p>
              <Button onClick={loadData} variant="outline">
                <RefreshCw className="w-4 h-4 mr-2" />
                Try Again
              </Button>
            </div>
          </div>
        )}
        
        {/* Empty State */}
        {!isLoading && !error && filteredInstances.length === 0 && (
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <div className="w-12 h-12 rounded-lg bg-muted flex items-center justify-center mx-auto mb-4">
                <Server className="w-6 h-6 text-muted-foreground" />
              </div>
              <h3 className="text-lg font-semibold mb-2">No Hosts</h3>
              <p className="text-muted-foreground mb-4">
                {integrationInstances.length === 0 
                  ? 'Get started by creating your first host connection.'
                  : 'No hosts match your current filters.'}
              </p>
              {integrationInstances.length === 0 && integrationTypes.length > 0 && (
                <Button onClick={() => setNewHostDialogOpen(true)}>
                  <Plus className="w-4 h-4 mr-2" />
                  New Host
                </Button>
              )}
              {integrationTypes.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  No valid integration types available. Add integration types in Settings → Integrations.
                </p>
              )}
            </div>
          </div>
        )}
        
        {/* Hosts Table */}
        {!isLoading && !error && filteredInstances.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Server className="w-5 h-5" />
                <span>Hosts</span>
                <Badge variant="outline">{filteredInstances.length}</Badge>
              </CardTitle>
              <CardDescription>
                Integration instances configured as host connections
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="rounded-lg border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Last Test</TableHead>
                      <TableHead>Latency</TableHead>
                      <TableHead>Created</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredInstances.map((instance) => (
                      <TableRow key={instance.instance_id} className="hover:bg-muted/50">
                        <TableCell>
                          <div className="space-y-1">
                            <div className="font-medium">{instance.name}</div>
                            <div className="font-mono text-xs text-muted-foreground">
                              ID: {instance.instance_id}
                            </div>
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="space-y-1">
                            <div className="font-medium">{instance.type_name || instance.type_id}</div>
                            <div className="text-xs text-muted-foreground">
                              {instance.type_category && (
                                <Badge variant="outline" className="text-xs">
                                  {instance.type_category}
                                </Badge>
                              )}
                            </div>
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            {getStatusIcon(instance.state)}
                            {getStatusBadge(instance.state)}
                          </div>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {formatTimestamp(instance.last_test)}
                        </TableCell>
                        <TableCell>
                          {instance.latency_ms ? (
                            <div className="flex items-center gap-1">
                              <Zap className="w-3 h-3" />
                              <span className="text-sm">{instance.latency_ms}ms</span>
                            </div>
                          ) : (
                            <span className="text-sm text-muted-foreground">—</span>
                          )}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          <div className="flex items-center gap-1">
                            <Calendar className="w-3 h-3" />
                            {new Date(instance.created_at).toLocaleDateString()}
                          </div>
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleTestInstance(instance.instance_id)}
                              disabled={testingId === instance.instance_id}
                              title="Test connection"
                            >
                              {testingId === instance.instance_id ? (
                                <Loader2 className="w-3 h-3 animate-spin" />
                              ) : (
                                <TestTube className="w-3 h-3" />
                              )}
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleShowDetails(instance)}
                              title="View details"
                            >
                              <Eye className="w-3 h-3" />
                            </Button>
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button data-testid="instance-actions-trigger" variant="ghost" size="sm">
                                  <Settings className="w-3 h-3" />
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                <DropdownMenuItem onClick={() => { setSettingsInstance(instance); setSettingsOpen(true); }}>
                                  <Settings className="w-4 h-4 mr-2" />
                                  Configure
                                </DropdownMenuItem>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem 
                                  className="text-destructive"
                                  onClick={() => handleDeleteInstance(instance.instance_id, instance.name)}
                                >
                                  <Trash2 className="w-4 h-4 mr-2" />
                                  Delete
                                </DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        )}

        {/* New Host Dialog */}
        <Dialog open={newHostDialogOpen} onOpenChange={setNewHostDialogOpen}>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>New Host</DialogTitle>
              <DialogDescription>
                Create a new host connection from an integration type
              </DialogDescription>
            </DialogHeader>
            
            <div className="space-y-6 py-4">
              {/* Step 1: Select Integration Type */}
              <div className="space-y-2">
                <Label>Integration Type</Label>
                <Select value={selectedType?.id || ''} onValueChange={handleTypeChange}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select an integration type" />
                  </SelectTrigger>
                  <SelectContent>
                    {integrationTypes.map((type) => (
                      <SelectItem key={type.id} value={type.id}>
                        <div className="flex items-center justify-between w-full">
                          <span>{type.name}</span>
                          <Badge variant="outline" className="ml-2 text-xs">
                            {type.category}
                          </Badge>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {integrationTypes.length === 0 && (
                  <p className="text-xs text-muted-foreground">
                    No valid integration types available. Add integration types in Settings → Integrations.
                  </p>
                )}
              </div>
              
              {selectedType && (
                <>
                  {/* Step 2: Host Name */}
                  <div className="space-y-2">
                    <Label htmlFor="host-name">
                      Host Name
                      <span className="text-destructive ml-1">*</span>
                    </Label>
                    <Input
                      id="host-name"
                      value={formData.name}
                      onChange={(e) => setFormData(prev => ({...prev, name: e.target.value}))}
                      placeholder="e.g., pve-01, truenas-main"
                      required
                    />
                    <p className="text-xs text-muted-foreground">
                      Unique identifier for this host connection
                    </p>
                  </div>
                  
                  {/* Step 3: Configuration Fields from Schema */}
                  {selectedType.schema_connection && selectedType.schema_connection.properties && (
                    <div className="space-y-4">
                      <div className="border-t pt-4">
                        <Label className="text-base">Configuration</Label>
                        <p className="text-xs text-muted-foreground mb-4">
                          Configure connection settings for {selectedType.name}
                        </p>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          {renderSchemaFields(selectedType.schema_connection, false)}
                        </div>
                      </div>
                      
                      {/* Secrets section - check for secret fields in schema */}
                      {Object.entries(selectedType.schema_connection.properties || {}).some(([_n, field]: [string, any]) => field.secret === true) && (
                        <div className="border-t pt-4">
                          <Label className="text-base">Secrets</Label>
                          <p className="text-xs text-muted-foreground mb-4">
                            Secure credentials and sensitive information
                          </p>
                          <div className="grid grid-cols-1 gap-4">
                            {renderSchemaFields(selectedType.schema_connection, true)}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                  
                  {/* Integration Type Info */}
                  <div className="bg-muted/20 p-4 rounded-lg">
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">Integration Type</span>
                        <Badge variant="outline">v{selectedType.version}</Badge>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        <div>Category: {selectedType.category}</div>
                        <div>Capabilities: {selectedType.capabilities.length} available</div>
                        <div>Min Core Version: {selectedType.min_core_version}</div>
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>

            <DialogFooter>
              <Button 
                variant="outline" 
                onClick={() => {
                  setNewHostDialogOpen(false);
                  resetForm();
                }}
              >
                Cancel
              </Button>
              <Button 
                onClick={handleCreateHost} 
                disabled={!selectedType || !formData.name.trim() || isCreating}
              >
                {isCreating ? (
                  <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Creating...</>
                ) : (
                  <>Create Host</>
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Host Settings / Details Dialog */}
        <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Host Settings</DialogTitle>
              <DialogDescription>View and edit configuration; re-test connection</DialogDescription>
            </DialogHeader>
            {settingsInstance ? (
              <div className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <Label className="text-micro text-muted-foreground">Name</Label>
                    <div className="font-mono">{settingsInstance.name}</div>
                  </div>
                  <div>
                    <Label className="text-micro text-muted-foreground">Type</Label>
                    <div className="font-mono">{settingsInstance.type_name || settingsInstance.type_id}</div>
                  </div>
                  <div>
                    <Label className="text-micro text-muted-foreground">State</Label>
                    <div>{getStatusBadge(settingsInstance.state)}</div>
                  </div>
                  <div>
                    <Label className="text-micro text-muted-foreground">Last Test</Label>
                    <div className="font-mono">{formatTimestamp(settingsInstance.last_test)}</div>
                  </div>
                </div>
                <div className="border-t pt-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <Label className="text-micro text-muted-foreground">Configuration (JSON)</Label>
                    {!isEditingConfig ? (
                      <Button variant="outline" size="sm" onClick={() => openEditConfig(settingsInstance)}>
                        Edit JSON
                      </Button>
                    ) : (
                      <div className="flex items-center gap-2">
                        <Button variant="ghost" size="sm" onClick={cancelEditConfig}>Cancel</Button>
                        <Button size="sm" onClick={saveEditedConfig}>Save</Button>
                      </div>
                    )}
                  </div>
                  {!isEditingConfig ? (
                    <pre className="bg-muted/30 border rounded p-3 text-xs overflow-auto max-h-64">
{JSON.stringify(settingsInstance.config, null, 2)}
                    </pre>
                  ) : (
                    <div className="space-y-2">
                      <Textarea
                        className="font-mono text-xs min-h-[220px]"
                        value={editConfigText}
                        onChange={(e) => setEditConfigText(e.target.value)}
                      />
                      {editError && <div className="text-xs text-destructive">{editError}</div>}
                      <p className="text-xs text-muted-foreground">Secrets are not displayed or editable here.</p>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="text-muted-foreground">No instance selected.</div>
            )}
            <DialogFooter>
              <Button variant="outline" onClick={() => setSettingsOpen(false)}>Close</Button>
              {settingsInstance && (
                <Button onClick={() => settingsInstance && handleTestInstance(settingsInstance.instance_id)} disabled={testingId === settingsInstance?.instance_id}>
                  {testingId === settingsInstance?.instance_id ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Testing...</>
                  ) : (
                    <><TestTube className="w-4 h-4 mr-2" />Test Connection</>
                  )}
                </Button>
              )}
            </DialogFooter>
          </DialogContent>
        </Dialog>
        
        <DetailsDrawer
          instance={detailsInstance}
          open={detailsDrawerOpen}
          onClose={() => setDetailsDrawerOpen(false)}
        />
      </div>
    </div>
  );
}
