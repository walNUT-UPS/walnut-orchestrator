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
  Puzzle
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

const mockUsers = [
  { id: '1', email: 'admin@walnut.local', role: 'Administrator', status: 'Active', lastLogin: '2024-01-15T15:42:00Z' },
  { id: '2', email: 'ops@company.com', role: 'Operator', status: 'Active', lastLogin: '2024-01-14T09:30:00Z' },
  { id: '3', email: 'monitor@company.com', role: 'Read-Only', status: 'Inactive', lastLogin: '2024-01-10T14:15:00Z' }
];

const mockSystemInfo = {
  version: '2.4.1',
  schemaVersion: '1.2.0',
  uptime: '15d 3h 42m',
  lastBackup: '2024-01-15T02:00:00Z'
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

  const copyDiagnostics = () => {
    const diagnostics = `walNUT System Diagnostics
Generated: ${new Date().toISOString()}
Version: ${mockSystemInfo.version}
Schema: ${mockSystemInfo.schemaVersion}
Uptime: ${mockSystemInfo.uptime}

Health Checks:
${mockHealthChecks.map(check => `- ${check.name}: ${check.status}`).join('\n')}

Last 5 Events:
- 2024-01-15T15:42:00Z: UPS status check completed
- 2024-01-15T15:41:30Z: Integration sync successful  
- 2024-01-15T15:41:00Z: Host connectivity check (1 warning)
- 2024-01-15T15:40:30Z: Policy evaluation completed
- 2024-01-15T15:40:00Z: Database backup completed`;

    navigator.clipboard.writeText(diagnostics);
    alert('Diagnostics copied to clipboard');
  };

  const downloadLogs = () => {
    const logContent = `[2024-01-15 15:30:00] WARN: Host monitoring-pi connection timeout
[2024-01-15 14:45:00] INFO: UPS battery test completed successfully
[2024-01-15 14:30:00] WARN: UPS switched to battery power
[2024-01-15 14:32:15] INFO: Utility power restored
[2024-01-15 13:15:00] INFO: Scheduled policy evaluation completed
[2024-01-15 12:00:00] INFO: Database backup completed
[2024-01-15 11:30:00] DEBUG: Integration sync: Proxmox API call succeeded
[2024-01-15 10:15:00] INFO: System started successfully
[2024-01-14 23:59:00] INFO: Daily maintenance tasks completed
[2024-01-14 22:30:00] WARN: Tapo device temporarily unreachable`;

    const blob = new Blob([logContent], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `walnut-logs-${new Date().toISOString().split('T')[0]}.log`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleKeyRotation = () => {
    if (confirm('This will rotate the database encryption key and require all hosts to be reconfigured. Continue?')) {
      alert('Key rotation feature not yet implemented');
    }
  };

  const handleInviteUser = () => {
    alert('User invitation is currently disabled');
  };

  const handleEditUser = (userId: string) => {
    alert(`Edit user ${userId} - not yet implemented`);
  };

  const testAllConnections = async () => {
    alert('Testing all connections - feature not yet implemented');
  };

  // Handle default route redirect
  React.useEffect(() => {
    if (location.pathname === '/settings' || location.pathname === '/settings/') {
      navigate('/settings/ups', { replace: true });
    }
  }, [location.pathname, navigate]);

  return (
    <div className="flex-1">
      <div className="container-grid py-6">
        <div className="mb-6 mt-6">
          <h1 className="text-display">Settings</h1>
          <p className="text-micro text-muted-foreground mt-1">
            Configure system settings and integrations
          </p>
        </div>

        <Tabs value={activeTab} onValueChange={(value) => {
          setActiveTab(value);
          navigate(`/settings/${value}`);
        }} className="space-y-6">
          <TabsList className="grid w-full grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
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
                  <Button variant="outline" className="mt-2" onClick={handleKeyRotation}>
                    <RotateCcw className="w-4 h-4 mr-2" />
                    Initiate Key Rotation
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
                  <Button variant="outline" onClick={handleInviteUser}>
                    Invite User
                  </Button>
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
                        <TableHead>Last Login</TableHead>
                        <TableHead>Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {mockUsers.map((user) => (
                        <TableRow key={user.id} className="hover:bg-accent/50">
                          <TableCell className="font-mono text-micro">
                            {user.email}
                          </TableCell>
                          <TableCell>
                            <Badge variant={user.role === 'Administrator' ? 'default' : 'outline'}>
                              {user.role}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge variant={user.status === 'Active' ? 'secondary' : 'outline'}>
                              {user.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-micro tabular-nums">
                            {new Date(user.lastLogin).toLocaleDateString()}
                          </TableCell>
                          <TableCell>
                            <Button variant="ghost" size="sm" onClick={() => handleEditUser(user.id)}>
                              Edit
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
                      <div className="font-mono">{mockSystemInfo.version}</div>
                    </div>
                    <div>
                      <Label className="text-micro text-muted-foreground">Schema Version</Label>
                      <div className="font-mono">{mockSystemInfo.schemaVersion}</div>
                    </div>
                  </div>
                  <div className="space-y-3">
                    <div>
                      <Label className="text-micro text-muted-foreground">Uptime</Label>
                      <div className="font-mono">{mockSystemInfo.uptime}</div>
                    </div>
                    <div>
                      <Label className="text-micro text-muted-foreground">Last Backup</Label>
                      <div className="font-mono">
                        {new Date(mockSystemInfo.lastBackup).toLocaleString()}
                      </div>
                    </div>
                  </div>
                </div>
                
                <Separator />
                
                <div className="space-y-2">
                  <Label htmlFor="log-level">Log Level</Label>
                  <Select defaultValue="info">
                    <SelectTrigger className="w-48">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="debug">Debug</SelectItem>
                      <SelectItem value="info">Info</SelectItem>
                      <SelectItem value="warn">Warning</SelectItem>
                      <SelectItem value="error">Error</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Health Checks</CardTitle>
                <CardDescription>
                  System component status and health monitoring
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {mockHealthChecks.map((check, index) => (
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
                        {new Date(check.lastCheck).toLocaleTimeString()}
                      </div>
                    </div>
                  ))}
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
                  Export diagnostic information and view recent errors
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
                
                <div className="space-y-2">
                  <Label>Recent Errors (Last 20)</Label>
                  <Textarea 
                    className="h-48 font-mono text-micro"
                    readOnly
                    value={`[2024-01-15 15:30:00] WARN: Host monitoring-pi connection timeout
[2024-01-15 14:45:00] INFO: UPS battery test completed successfully
[2024-01-15 14:30:00] WARN: UPS switched to battery power
[2024-01-15 14:32:15] INFO: Utility power restored
[2024-01-15 13:15:00] INFO: Scheduled policy evaluation completed
[2024-01-15 12:00:00] INFO: Database backup completed
[2024-01-15 11:30:00] DEBUG: Integration sync: Proxmox API call succeeded
[2024-01-15 10:15:00] INFO: System started successfully
[2024-01-14 23:59:00] INFO: Daily maintenance tasks completed
[2024-01-14 22:30:00] WARN: Tapo device temporarily unreachable`}
                  />
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