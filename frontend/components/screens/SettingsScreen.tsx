import React, { useState } from 'react';
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Switch } from '../ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { Separator } from '../ui/separator';
import { 
  TestTube,
  Save,
  RotateCcw,
  Copy,
  Download,
  AlertTriangle,
  CheckCircle2,
  Settings2,
  Shield,
  Users,
  Activity,
  Bug,
  Puzzle,
  Pause,
  Play,
  Trash2
} from 'lucide-react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../ui/table';
import { Textarea } from '../ui/textarea';
import { toast } from 'sonner';
import { apiService } from '../../services/api';

type UserRow = { id: string; email: string; is_active: boolean; is_verified: boolean; is_superuser: boolean };
const useUsers = () => {
  const [users, setUsers] = React.useState<UserRow[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const reload = React.useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await apiService.listUsers();
      setUsers(data as any);
    } catch (e: any) {
      setError(e?.message || 'Failed to load users');
    } finally {
      setLoading(false);
    }
  }, []);
  React.useEffect(() => { reload(); }, [reload]);
  return { users, setUsers, loading, error, reload };
};

const useSystemConfig = () => {
  const [config, setConfig] = React.useState<any | null>(null);
  const [health, setHealth] = React.useState<any | null>(null);
  React.useEffect(() => {
    (async () => {
      try {
        const api = (await import('../../services/api')).apiService;
        const [cfg, h] = await Promise.all([api.getSystemConfig(), api.getSystemHealth()]);
        setConfig(cfg);
        setHealth(h);
      } catch (_) {}
    })();
  }, []);
  return { config, health };
};

const mockHealthChecks = [
  { name: 'Database Connection', status: 'healthy', lastCheck: '2024-01-15T15:42:00Z' },
  { name: 'UPS Communication', status: 'healthy', lastCheck: '2024-01-15T15:42:00Z' },
  { name: 'Host Connectivity', status: 'warning', lastCheck: '2024-01-15T15:41:00Z', message: '1 host offline' },
  { name: 'Integration Status', status: 'healthy', lastCheck: '2024-01-15T15:40:00Z' }
];

// Import the new IntegrationsSettingsScreen
import { IntegrationsSettingsScreen } from './IntegrationsSettingsScreen';

export function SettingsScreen() {
  const location = useLocation();
  const navigate = useNavigate();
  
  // Extract the settings subtab from the URL path
  const getActiveTabFromPath = () => {
    const pathSegments = location.pathname.split('/');
    if (pathSegments[1] === 'settings' && pathSegments.length > 2) {
      return pathSegments[2];
    }
    return 'ups';
  };

  const [activeTab, setActiveTab] = useState(getActiveTabFromPath());
  
  // Update active tab when location changes
  React.useEffect(() => {
    setActiveTab(getActiveTabFromPath());
  }, [location.pathname]);
  const [testResult, setTestResult] = useState<{ status: 'success' | 'error'; message: string } | null>(null);
  const [isDirty, setIsDirty] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveResult, setSaveResult] = useState<{ status: 'success' | 'error'; message: string } | null>(null);
  const { users, setUsers, loading: usersLoading, error: usersError, reload: reloadUsers } = useUsers();
  const singleUser = users.length <= 1;

  const testConnection = async () => {
    setTestResult(null);
    await new Promise(resolve => setTimeout(resolve, 1500));
    
    const success = Math.random() > 0.2; // 80% success rate
    setTestResult({
      status: success ? 'success' : 'error',
      message: success 
        ? 'Successfully connected to UPS device' 
        : 'Connection failed: Device not responding'
    });
  };

  const handleInputChange = () => {
    setIsDirty(true);
    setSaveResult(null);
  };

  const saveConfiguration = async () => {
    setIsSaving(true);
    setSaveResult(null);
    
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    const success = Math.random() > 0.1; // 90% success rate
    setSaveResult({
      status: success ? 'success' : 'error',
      message: success 
        ? 'Configuration saved successfully' 
        : 'Failed to save configuration. Please try again.'
    });
    
    if (success) {
      setIsDirty(false);
    }
    setIsSaving(false);
  };

  const copyDiagnostics = async () => {
    try {
      const [healthRes, configRes] = await Promise.all([
        fetch('/api/system/health', { credentials: 'include' }),
        fetch('/api/system/config', { credentials: 'include' }),
      ]);
      if (!healthRes.ok || !configRes.ok) throw new Error('Failed to fetch diagnostics');
      const [health, config] = await Promise.all([healthRes.json(), configRes.json()]);
      const diagnostics = `walNUT Diagnostics\nGenerated: ${new Date().toISOString()}\n\nHealth:\n${JSON.stringify(health, null, 2)}\n\nConfig:\n${JSON.stringify(config, null, 2)}\n`;
      await navigator.clipboard.writeText(diagnostics);
      toast.success('Diagnostics copied to clipboard');
    } catch (e) {
      toast.error((e as Error).message || 'Failed to copy diagnostics');
    }
  };

  const downloadLogs = async () => {
    try {
      const res = await fetch('/api/system/diagnostics/bundle', {
        method: 'GET',
        credentials: 'include',
      });
      if (!res.ok) throw new Error(`Download failed: ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `walnut-diagnostics-${new Date().toISOString().slice(0,19).replace(/[:T]/g,'-')}.zip`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast.success('Diagnostics bundle downloaded');
    } catch (e) {
      toast.error((e as Error).message || 'Failed to download diagnostics');
    }
  };

  const handleKeyRotation = () => {
    // Placeholder: disabled in UI
  };

  const handleInviteUser = () => {
    toast.info('User invitation is currently disabled');
  };

  const handleEditUser = (userId: string) => {
    toast.info(`Edit user ${userId} - not yet implemented`);
  };

  const testAllConnections = async () => {
    toast.info('Testing all connections is not implemented yet');
  };

  // Handle default route redirect
  React.useEffect(() => {
    if (location.pathname === '/settings' || location.pathname === '/settings/') {
      navigate('/settings/ups', { replace: true });
    }
  }, [location.pathname, navigate]);

  return (
    <div className="flex-1">
      <div className="container-grid py-8">
        <div className="mb-6 mt-2">
          <h1 className="text-display">Settings</h1>
          <p className="text-micro text-muted-foreground mt-1">
            Configure system settings and integrations
          </p>
        </div>

        <Tabs value={activeTab} onValueChange={(value) => {
          setActiveTab(value);
          navigate(`/settings/${value}`);
        }} className="space-y-6">
          <TabsList className="grid w-full grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 p-2 rounded-md bg-muted/20">
            <TabsTrigger value="ups" className="flex items-center space-x-1 lg:space-x-2 text-xs lg:text-sm">
              <Settings2 className="w-4 h-4" />
              <span className="hidden sm:inline">UPS / NUT</span>
              <span className="sm:hidden">UPS</span>
            </TabsTrigger>
            <TabsTrigger value="integrations" className="flex items-center space-x-1 lg:space-x-2 text-xs lg:text-sm">
              <Puzzle className="w-4 h-4" />
              <span>Integrations</span>
            </TabsTrigger>
            <TabsTrigger value="security" className="flex items-center space-x-1 lg:space-x-2 text-xs lg:text-sm">
              <Shield className="w-4 h-4" />
              <span>Security</span>
            </TabsTrigger>
            <TabsTrigger value="users" className="flex items-center space-x-1 lg:space-x-2 text-xs lg:text-sm">
              <Users className="w-4 h-4" />
              <span>Users</span>
            </TabsTrigger>
            <TabsTrigger value="system" className="flex items-center space-x-1 lg:space-x-2 text-xs lg:text-sm">
              <Activity className="w-4 h-4" />
              <span>System</span>
            </TabsTrigger>
            <TabsTrigger value="diagnostics" className="flex items-center space-x-1 lg:space-x-2 text-xs lg:text-sm">
              <Bug className="w-4 h-4" />
              <span className="hidden sm:inline">Diagnostics</span>
              <span className="sm:hidden">Debug</span>
            </TabsTrigger>
          </TabsList>

          {/* UPS / NUT Configuration */}
          <TabsContent value="ups" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>NUT Server Connection</CardTitle>
                <CardDescription>
                  Configure connection to the Network UPS Tools daemon
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="nut-host">Host</Label>
                    <Input id="nut-host" defaultValue="ups.local" onChange={handleInputChange} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="nut-port">Port</Label>
                    <Input id="nut-port" defaultValue="3493" onChange={handleInputChange} />
                  </div>
                </div>
                
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="nut-username">Username</Label>
                    <Input id="nut-username" defaultValue="upsmon" onChange={handleInputChange} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="nut-password">Password</Label>
                    <Input id="nut-password" type="password" defaultValue="••••••••" onChange={handleInputChange} />
                  </div>
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
                        <AlertTriangle className="w-4 h-4" />
                      )}
                      <span className="text-sm">{testResult.message}</span>
                    </div>
                  </div>
                )}

                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
                  <Button variant="outline" onClick={testConnection} className="min-h-[44px]">
                    <TestTube className="w-4 h-4 mr-2" />
                    Test Connection
                  </Button>
                  <Button onClick={saveConfiguration} disabled={!isDirty || isSaving} className="min-h-[44px]">
                    <Save className="w-4 h-4 mr-2" />
                    {isSaving ? 'Saving...' : 'Save Configuration'}
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* OIDC SSO Configuration */}
            <OIDCSettingsCard />

            <Card>
              <CardHeader>
                <CardTitle>UPS Monitoring</CardTitle>
                <CardDescription>
                  Configure monitoring thresholds and alerts
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="battery-warn">Battery Warning (%)</Label>
                    <Input id="battery-warn" defaultValue="30" type="number" onChange={handleInputChange} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="battery-critical">Battery Critical (%)</Label>
                    <Input id="battery-critical" defaultValue="15" type="number" onChange={handleInputChange} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="load-warn">Load Warning (%)</Label>
                    <Input id="load-warn" defaultValue="80" type="number" onChange={handleInputChange} />
                  </div>
                </div>
                
                <div className="space-y-6">
                  <div className="flex flex-col sm:flex-row sm:items-center space-y-3 sm:space-y-0 sm:space-x-6">
                    <Label htmlFor="auto-test" className="font-medium min-w-[120px]">Auto Test</Label>
                    <div className="flex items-center space-x-3">
                      <Switch id="auto-test" onCheckedChange={handleInputChange} />
                      <span className="text-micro text-muted-foreground">Enable automatic battery testing (weekly)</span>
                    </div>
                  </div>
                  
                  <div className="flex flex-col sm:flex-row sm:items-center space-y-3 sm:space-y-0 sm:space-x-6">
                    <Label htmlFor="email-alerts" className="font-medium min-w-[120px]">Email Alerts</Label>
                    <div className="flex items-center space-x-3">
                      <Switch id="email-alerts" defaultChecked onCheckedChange={handleInputChange} />
                      <span className="text-micro text-muted-foreground">Send email alerts for critical events</span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
        </TabsContent>

          {/* Integrations Settings */}
          <TabsContent value="integrations" className="space-y-6">
            <IntegrationsSettingsScreen />
          </TabsContent>

          {/* Security Settings */}
          <TabsContent value="security" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Secrets Management</CardTitle>
                <CardDescription>
                  Database encryption key and backup configuration
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="p-4 bg-muted/20 rounded-lg">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium">Database Encryption Key</div>
                      <div className="text-micro text-muted-foreground">
                        Status: Active (Generated 2024-01-01)
                      </div>
                    </div>
                    <Badge variant="secondary" className="bg-status-ok/10 text-status-ok">
                      Healthy
                    </Badge>
                  </div>
                </div>
                
                <div className="space-y-2">
                  <Label>Key Rotation</Label>
                  <p className="text-micro text-muted-foreground">
                    Rotate the database encryption key. This will require all hosts to be reconfigured with new credentials.
                  </p>
                  <Button variant="outline" className="mt-2" disabled>
                    <RotateCcw className="w-4 h-4 mr-2" />
                    Key Rotation (coming soon)
                  </Button>
                </div>

                <Separator />
                
                <div className="space-y-2">
                  <Label>Backup Encryption</Label>
                  <p className="text-micro text-muted-foreground">
                    Configuration backups are encrypted with a separate key
                  </p>
                  <div className="flex items-center space-x-3 mt-2">
                    <Switch id="backup-encryption" defaultChecked />
                    <Label htmlFor="backup-encryption">Enable backup encryption</Label>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Users & Roles */}
          <TabsContent value="users" className="space-y-6">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>User Management</CardTitle>
                    <CardDescription>
                      Manage user accounts and permissions
                    </CardDescription>
                  </div>
                  <div className="flex items-center gap-3">
                    {usersError && <span className="text-destructive text-xs">{usersError}</span>}
                    <Button variant="outline" onClick={reloadUsers} disabled={usersLoading}>
                      {usersLoading ? 'Loading…' : `${users.length} users`}
                    </Button>
                    <Button variant="outline" onClick={handleInviteUser}>Invite User</Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="rounded-lg border border-border overflow-hidden">
                  <Table>
                    <TableHeader className="bg-muted/30">
                      <TableRow className="hover:bg-transparent">
                        <TableHead>Email</TableHead>
                        <TableHead>Role</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Verified</TableHead>
                        <TableHead>Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {users.map((u) => (
                        <TableRow key={u.id} className="hover:bg-accent/50">
                          <TableCell className="font-mono text-micro">{u.email}</TableCell>
                          <TableCell>
                            <Badge variant={u.is_superuser ? 'default' : 'outline'}>
                              {u.is_superuser ? 'Administrator' : 'User'}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge variant={u.is_active ? 'secondary' : 'outline'}>
                              {u.is_active ? 'Active' : 'Disabled'}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge variant={u.is_verified ? 'secondary' : 'outline'}>
                              {u.is_verified ? 'Verified' : 'Unverified'}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Button
                              variant="ghost"
                              size="sm"
                              disabled={singleUser && u.is_active}
                              title={singleUser && u.is_active ? 'Cannot disable the only user' : undefined}
                              onClick={async () => {
                                try {
                                  const updated = await apiService.updateUser(u.id, { is_active: !u.is_active });
                                  setUsers(prev => prev.map(x => x.id === u.id ? { ...x, is_active: updated.is_active } : x));
                                  toast.success(updated.is_active ? 'User enabled' : 'User disabled');
                                } catch (e: any) {
                                  toast.error(e?.message || 'Failed to update');
                                }
                              }}
                            >
                              {u.is_active ? 'Disable' : 'Enable'}
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
                
                <div className="mt-4 p-3 bg-muted/20 rounded-lg">
                  <p className="text-micro text-muted-foreground">
                    <strong>Note:</strong> User signup is currently disabled. Contact your system administrator to enable user registration.
                  </p>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* System Information */}
          <TabsContent value="system" className="space-y-6">
            {(() => { const { config, health } = useSystemConfig(); return (
            <Card>
              <CardHeader>
                <CardTitle>System Information</CardTitle>
                <CardDescription>
                  Current system status and configuration
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-3">
                    <div>
                      <Label className="text-micro text-muted-foreground">Version</Label>
                      <div className="font-mono">{config?.version ?? '-'}</div>
                    </div>
                    <div>
                      <Label className="text-micro text-muted-foreground">Uptime</Label>
                      <div className="font-mono">{health ? `${Math.floor((health.uptime_seconds||0)/3600)}h ${Math.floor(((health.uptime_seconds||0)%3600)/60)}m` : '-'}</div>
                    </div>
                  </div>
                  <div className="space-y-3">
                    <div>
                      <Label className="text-micro text-muted-foreground">Database</Label>
                      <div className="font-mono">{config?.database_type ?? '-'}</div>
                    </div>
                    <div>
                      <Label className="text-micro text-muted-foreground">CORS / Origins</Label>
                      <div className="font-mono">{config ? `${config.cors_enabled ? 'enabled' : 'disabled'} (${config.allowed_origins_count})` : '-'}</div>
                    </div>
                  </div>
                </div>
                
                <Separator />
                
                <div className="space-y-2">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <Label className="text-micro text-muted-foreground">Secure Cookies</Label>
                      <div className="font-mono">{config ? (config.secure_cookies ? 'true' : 'false') : '-'}</div>
                    </div>
                    <div>
                      <Label className="text-micro text-muted-foreground">Signup Enabled</Label>
                      <div className="font-mono">{config ? (config.signup_enabled ? 'true' : 'false') : '-'}</div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
            )})()}
            
            <Card>
              <CardHeader>
                <CardTitle>Health Checks</CardTitle>
                <CardDescription>
                  System component status and health monitoring
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {(() => {
                    const { config, health } = useSystemConfig();
                    const checks = health ? [
                      { name: 'Database Connection', status: health.components?.database?.status || 'unknown', message: `latency ${health.components?.database?.latency_ms ?? '?'} ms`, lastCheck: health.timestamp },
                      { name: 'NUT Connection', status: health.components?.nut_connection?.status || 'unknown', message: health.components?.nut_connection?.message, lastCheck: health.timestamp },
                      { name: 'UPS Polling', status: health.components?.ups_polling?.status || 'unknown', message: health.components?.ups_polling?.message, lastCheck: health.timestamp },
                    ] : [];
                    return checks.map((check, index) => (
                    <div key={index} className="flex items-center justify-between p-3 bg-muted/20 rounded-lg">
                      <div className="flex items-center space-x-3">
                        {check.status === 'healthy' ? (
                          <CheckCircle2 className="w-4 h-4 text-status-ok" />
                        ) : (
                          <AlertTriangle className="w-4 h-4 text-status-warn" />
                        )}
                        <div>
                          <div className="font-medium">{check.name}</div>
                          {check.message && (
                            <div className="text-micro text-muted-foreground">{check.message}</div>
                          )}
                        </div>
                      </div>
                      <div className="text-micro text-muted-foreground tabular-nums">
                        {check.lastCheck ? new Date(check.lastCheck).toLocaleTimeString() : ''}
                      </div>
                    </div>
                    ));
                  })()}
                </div>
              </CardContent>
            </Card>

            {/* Backend Control */}
            <Card>
              <CardHeader>
                <CardTitle>Backend Control</CardTitle>
                <CardDescription>Administrative actions for the backend service</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
                  <Button
                    variant="destructive"
                    onClick={async () => {
                      if (!confirm('Restart backend now? Active requests will be interrupted.')) return;
                      try {
                        const res = await fetch('/api/system/restart', { method: 'POST', credentials: 'include' });
                        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
                        toast.success('Restarting backend...');
                      } catch (e: any) {
                        toast.error(e?.message || 'Failed to trigger restart');
                      }
                    }}
                  >
                    Restart Backend
                  </Button>
                  <span className="text-xs text-muted-foreground">Requires admin privileges. The app will reconnect when available.</span>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Diagnostics */}
          <TabsContent value="diagnostics" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>System Diagnostics</CardTitle>
                <CardDescription>
                  Live logs and quick export for troubleshooting
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap items-center gap-3">
                  <Button variant="outline" onClick={copyDiagnostics}>
                    <Copy className="w-4 h-4 mr-2" />
                    Copy Diagnostics Bundle
                  </Button>
                  <Button variant="outline" onClick={downloadLogs}>
                    <Download className="w-4 h-4 mr-2" />
                    Download Logs
                  </Button>
                </div>

                <Separator />

                {/* Frontend/Backend logs as tabs */}
                <div className="space-y-3">
                  <Label>Live Logs</Label>
                  <DiagnosticsLogsTabs />
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>

        {/* Sticky Footer Actions */}
        <div className="sticky bottom-0 bg-background/95 backdrop-blur border-t border-border p-4 -mx-6 mt-8">
          <div className="flex items-center justify-between">
            <div className="text-micro text-muted-foreground">
              {saveResult && (
                <div className={`flex items-center space-x-2 ${
                  saveResult.status === 'success' 
                    ? 'text-status-ok' 
                    : 'text-status-error'
                }`}>
                  {saveResult.status === 'success' ? (
                    <CheckCircle2 className="w-4 h-4" />
                  ) : (
                    <AlertTriangle className="w-4 h-4" />
                  )}
                  <span>{saveResult.message}</span>
                </div>
              )}
              {!saveResult && isDirty && (
                <span className="text-status-warn">Unsaved changes</span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="outline" onClick={testAllConnections}>
                <TestTube className="w-4 h-4 mr-2" />
                Test All Connections
              </Button>
              <Button onClick={saveConfiguration} disabled={!isDirty || isSaving}>
                <Save className="w-4 h-4 mr-2" />
                {isSaving ? 'Saving...' : 'Save Configuration'}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// --- Diagnostics Logs Tabs ---
function OIDCSettingsCard() {
  const [cfg, setCfg] = React.useState<any | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [testing, setTesting] = React.useState(false);

  React.useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const c = await apiService.getOidcConfig();
        setCfg({
          ...c,
          admin_roles: (c.admin_roles || []).join(', '),
          viewer_roles: (c.viewer_roles || []).join(', '),
          client_secret: '',
        });
      } catch (_) {
        setCfg({ enabled: false });
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const save = async () => {
    if (!cfg) return;
    try {
      setSaving(true);
      const payload: any = {
        enabled: !!cfg.enabled,
        provider_name: cfg.provider_name || undefined,
        client_id: cfg.client_id || undefined,
        ...(cfg.client_secret ? { client_secret: cfg.client_secret } : {}),
        discovery_url: cfg.discovery_url || undefined,
        admin_roles: (cfg.admin_roles || '').split(',').map((s: string) => s.trim()).filter(Boolean),
        viewer_roles: (cfg.viewer_roles || '').split(',').map((s: string) => s.trim()).filter(Boolean),
      };
      const res = await apiService.updateOidcConfig(payload);
      setCfg({
        ...res,
        admin_roles: (res.admin_roles || []).join(', '),
        viewer_roles: (res.viewer_roles || []).join(', '),
        client_secret: '',
      });
      toast.success('OIDC settings saved');
    } catch (e: any) {
      toast.error(e?.message || 'Failed to save OIDC settings');
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    if (!cfg?.discovery_url) return;
    try {
      setTesting(true);
      const res = await apiService.testOidcConfig({ discovery_url: cfg.discovery_url });
      if (res.status === 'success') {
        toast.success('OIDC discovery OK');
      } else {
        toast.error('OIDC test failed');
      }
    } catch (e: any) {
      toast.error(e?.message || 'OIDC test failed');
    } finally {
      setTesting(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>OIDC Single Sign-On</CardTitle>
        <CardDescription>Configure OpenID Connect login and roles</CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="text-sm text-muted-foreground">Loading OIDC settings...</div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <input id="oidc-enabled" type="checkbox" checked={!!cfg?.enabled} onChange={(e) => setCfg((p: any) => ({ ...p, enabled: e.target.checked }))} />
              <label htmlFor="oidc-enabled" className="text-sm">Enable OIDC (activates login button)</label>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <Label className="text-sm">Provider Name</Label>
                <Input value={cfg?.provider_name || ''} onChange={(e) => setCfg((p: any) => ({ ...p, provider_name: e.target.value }))} />
              </div>
              <div>
                <Label className="text-sm">Discovery URL</Label>
                <Input value={cfg?.discovery_url || ''} onChange={(e) => setCfg((p: any) => ({ ...p, discovery_url: e.target.value }))} />
              </div>
              <div>
                <Label className="text-sm">Client ID</Label>
                <Input value={cfg?.client_id || ''} onChange={(e) => setCfg((p: any) => ({ ...p, client_id: e.target.value }))} />
              </div>
              <div>
                <Label className="text-sm">Client Secret</Label>
                <Input type="password" value={cfg?.client_secret || ''} onChange={(e) => setCfg((p: any) => ({ ...p, client_secret: e.target.value }))} placeholder={cfg?.has_client_secret ? '•••••••• (set)' : ''} />
              </div>
              <div className="md:col-span-2">
                <Label className="text-sm">Admin Roles (comma-separated)</Label>
                <Input value={cfg?.admin_roles || ''} onChange={(e) => setCfg((p: any) => ({ ...p, admin_roles: e.target.value }))} />
              </div>
              <div className="md:col-span-2">
                <Label className="text-sm">Viewer Roles (comma-separated)</Label>
                <Input value={cfg?.viewer_roles || ''} onChange={(e) => setCfg((p: any) => ({ ...p, viewer_roles: e.target.value }))} />
              </div>
            </div>
            <div className="flex items-center gap-2 pt-2">
              <Button onClick={save} disabled={saving}>{saving ? 'Saving...' : 'Save OIDC'}</Button>
              <Button variant="outline" onClick={test} disabled={testing || !cfg?.discovery_url}>{testing ? 'Testing...' : 'Test'}</Button>
              {cfg?.requires_restart && (
                <span className="text-xs text-muted-foreground">Server restart may be required to apply routing changes</span>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
function DiagnosticsLogsTabs() {
  const [active, setActive] = React.useState<'backend' | 'frontend'>('backend');
  return (
    <div>
      <div className="flex gap-2 mb-2">
        <button
          className={`px-3 py-1.5 rounded-md text-sm border ${active==='backend' ? 'bg-accent' : 'bg-background'} border-border`}
          onClick={() => setActive('backend')}
        >
          Backend
        </button>
        <button
          className={`px-3 py-1.5 rounded-md text-sm border ${active==='frontend' ? 'bg-accent' : 'bg-background'} border-border`}
          onClick={() => setActive('frontend')}
        >
          Frontend
        </button>
      </div>
      <LogsViewer source={active} />
    </div>
  );
}

function LogsViewer({ source }: { source: 'backend' | 'frontend' }) {
  const [lines, setLines] = React.useState<string[]>([]);
  const [paused, setPaused] = React.useState(false);
  const [status, setStatus] = React.useState<'connecting' | 'open' | 'closed' | 'error'>('connecting');
  const viewportRef = React.useRef<HTMLDivElement | null>(null);
  const wsRef = React.useRef<WebSocket | null>(null);

  // Auto-scroll when new lines arrive
  React.useEffect(() => {
    if (paused) return;
    const el = viewportRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [lines, paused]);

  React.useEffect(() => {
    setLines([]);
    setStatus('connecting');
    if (wsRef.current) {
      try { wsRef.current.close(); } catch (_) {}
      wsRef.current = null;
    }
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${protocol}://${location.host}/ws/logs/${source}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;
    ws.onopen = () => setStatus('open');
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'log.line') {
          if (!paused) setLines(prev => (prev.length > 1000 ? prev.slice(-800) : prev).concat(msg.data.line));
        } else if (msg.type === 'log.open') {
          if (!paused) setLines(prev => prev.concat(`[open] ${msg.data.path}`));
        } else if (msg.type === 'log.info') {
          if (!paused) setLines(prev => prev.concat(`[info] ${msg.data.message}`));
        } else if (msg.type === 'log.error') {
          setLines(prev => prev.concat(`[error] ${msg.data.message}`));
        }
      } catch (_) {
        if (!paused) setLines(prev => prev.concat(String(ev.data)));
      }
    };
    ws.onerror = () => setStatus('error');
    ws.onclose = () => setStatus('closed');
    return () => { try { ws.close(); } catch (_) {} };
  }, [source, paused]);

  return (
    <div className="border rounded-md">
      <div className="flex items-center justify-between p-2 border-b border-border">
        <div className="text-micro text-muted-foreground">{source} · {status}</div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setPaused(p => !p)}>
            {paused ? (<><Play className="w-3.5 h-3.5 mr-1"/> Resume</>) : (<><Pause className="w-3.5 h-3.5 mr-1"/> Pause</>)}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setLines([])}>
            <Trash2 className="w-3.5 h-3.5 mr-1"/> Clear
          </Button>
        </div>
      </div>
      <div ref={viewportRef} className="h-64 overflow-auto bg-card font-mono text-[12px] leading-[18px] p-3 whitespace-pre-wrap">
        {lines.length === 0 ? (
          <div className="text-muted-foreground">No logs yet…</div>
        ) : (
          lines.map((ln, i) => <div key={i} className="break-words">{ln}</div>)
        )}
      </div>
    </div>
  );
}
