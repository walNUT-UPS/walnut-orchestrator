import React, { useState } from 'react';
import { SecondaryToolbar } from '../SecondaryToolbar';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Switch } from '../ui/switch';
import { 
  Play, 
  Pause, 
  Settings, 
  Plus, 
  Clock, 
  Zap,
  CheckCircle2,
  XCircle,
  AlertTriangle
} from 'lucide-react';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '../ui/sheet';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../ui/table';

interface Policy {
  id: string;
  name: string;
  enabled: boolean;
  trigger: string;
  targetCount: number;
  lastExecution?: string;
  status: 'success' | 'failed' | 'pending' | 'never';
  description: string;
}

interface Action {
  id: string;
  policyId: string;
  policyName: string;
  action: string;
  target: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  startTime: string;
  endTime?: string;
  error?: string;
}

const mockPolicies: Policy[] = [
  {
    id: '1',
    name: 'Emergency Shutdown - Proxmox',
    enabled: true,
    trigger: 'ups.status == "LowBattery"',
    targetCount: 2,
    lastExecution: '2024-01-15T12:45:00Z',
    status: 'success',
    description: 'Gracefully shut down Proxmox VMs when UPS battery is low'
  },
  {
    id: '2',
    name: 'TrueNAS Backup Alert',
    enabled: true,
    trigger: 'ups.status == "OnBattery" && duration > 60s',
    targetCount: 1,
    lastExecution: '2024-01-15T14:30:00Z',
    status: 'success',
    description: 'Send alert to stop active backups when on battery for >60s'
  },
  {
    id: '3',
    name: 'Smart Plug Control',
    enabled: false,
    trigger: 'ups.battery < 50%',
    targetCount: 3,
    status: 'never',
    description: 'Turn off non-essential devices via Tapo smart plugs'
  }
];

const mockActions: Action[] = [
  {
    id: '1',
    policyId: '1',
    policyName: 'Emergency Shutdown - Proxmox',
    action: 'SSH Shutdown',
    target: 'srv-pbs-01',
    status: 'completed',
    startTime: '2024-01-15T12:45:30Z',
    endTime: '2024-01-15T12:46:15Z'
  },
  {
    id: '2',
    policyId: '2',
    policyName: 'TrueNAS Backup Alert',
    action: 'Webhook',
    target: 'https://truenas.local/api/backup/pause',
    status: 'completed',
    startTime: '2024-01-15T14:30:15Z',
    endTime: '2024-01-15T14:30:18Z'
  }
];

export function OrchestrationScreen() {
  const [searchValue, setSearchValue] = useState('');
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards');
  const [activeFilters, setActiveFilters] = useState<string[]>([]);
  const [selectedPolicy, setSelectedPolicy] = useState<Policy | null>(null);

  const availableFilters = ['Enabled', 'Disabled', 'Success', 'Failed', 'Pending'];

  const handleFilterToggle = (filter: string) => {
    setActiveFilters(prev => 
      prev.includes(filter) 
        ? prev.filter(f => f !== filter)
        : [...prev, filter]
    );
  };

  const togglePolicy = (policyId: string) => {
    // Handle policy enable/disable
    console.log('Toggle policy:', policyId);
  };

  const testPolicy = (policyId: string) => {
    // Handle policy test
    console.log('Test policy:', policyId);
  };

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'success':
        return <CheckCircle2 className="w-4 h-4 text-status-ok" />;
      case 'failed':
        return <XCircle className="w-4 h-4 text-status-error" />;
      case 'pending':
        return <Clock className="w-4 h-4 text-status-warn" />;
      default:
        return <AlertTriangle className="w-4 h-4 text-muted-foreground" />;
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
            <h1 className="text-display">Orchestration Policies</h1>
            <p className="text-micro text-muted-foreground mt-1">
              Automate UPS event responses and system protection
            </p>
          </div>
          <Button className="bg-status-info hover:bg-status-info/90">
            <Plus className="w-4 h-4 mr-2" />
            Create Policy
          </Button>
        </div>

        {/* Policies Grid */}
        {viewMode === 'cards' && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {mockPolicies.map((policy) => (
              <Card 
                key={policy.id} 
                className="bg-card hover:bg-accent/50 transition-colors cursor-pointer"
                style={{ boxShadow: 'var(--shadow-card)' }}
              >
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <CardTitle className="text-title">{policy.name}</CardTitle>
                      <p className="text-micro text-muted-foreground mt-1">
                        {policy.description}
                      </p>
                    </div>
                    <div className="flex items-center space-x-2">
                      {getStatusIcon(policy.status)}
                      <Switch 
                        checked={policy.enabled} 
                        onCheckedChange={() => togglePolicy(policy.id)}
                      />
                    </div>
                  </div>
                </CardHeader>
                
                <CardContent className="space-y-4">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between text-micro">
                      <span className="text-muted-foreground">Trigger</span>
                      <Badge variant="outline" className="text-xs">
                        {policy.trigger.split(' ')[0]}
                      </Badge>
                    </div>
                    
                    <div className="flex items-center justify-between text-micro">
                      <span className="text-muted-foreground">Targets</span>
                      <span className="font-medium">{policy.targetCount} hosts</span>
                    </div>
                    
                    {policy.lastExecution && (
                      <div className="flex items-center justify-between text-micro">
                        <span className="text-muted-foreground">Last Run</span>
                        <span className="font-medium">
                          {formatTimestamp(policy.lastExecution)}
                        </span>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center space-x-2 pt-3 border-t border-border">
                    <Sheet>
                      <SheetTrigger asChild>
                        <Button 
                          variant="outline" 
                          size="sm" 
                          className="flex-1"
                          onClick={() => setSelectedPolicy(policy)}
                        >
                          <Settings className="w-3 h-3 mr-1" />
                          Edit
                        </Button>
                      </SheetTrigger>
                      <SheetContent className="w-[600px] max-w-[90vw]">
                        <SheetHeader>
                          <SheetTitle>Edit Policy: {selectedPolicy?.name}</SheetTitle>
                          <SheetDescription>
                            Configure automation rules and actions
                          </SheetDescription>
                        </SheetHeader>
                        <div className="mt-6 space-y-4">
                          <div className="p-4 bg-muted/20 rounded-lg">
                            <p className="text-micro text-muted-foreground">
                              Policy editor would be implemented here with form fields for:
                            </p>
                            <ul className="text-micro text-muted-foreground mt-2 list-disc list-inside space-y-1">
                              <li>Trigger conditions (UPS status, battery level, etc.)</li>
                              <li>Action types (SSH shutdown, webhook, script execution)</li>
                              <li>Target selection (hosts, services, devices)</li>
                              <li>Delays and retry configuration</li>
                            </ul>
                          </div>
                          <div className="flex items-center space-x-2 pt-4">
                            <Button>Save Policy</Button>
                            <Button variant="outline">Test Policy</Button>
                          </div>
                        </div>
                      </SheetContent>
                    </Sheet>

                    <Button 
                      variant="outline" 
                      size="sm"
                      onClick={() => testPolicy(policy.id)}
                    >
                      <Zap className="w-3 h-3 mr-1" />
                      Test
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Recent Actions */}
        <div className="space-y-4">
          <h2 className="text-display">Recent Actions</h2>
          
          <div className="bg-card rounded-lg border border-border overflow-hidden">
            <Table>
              <TableHeader className="bg-muted/30">
                <TableRow className="hover:bg-transparent">
                  <TableHead>Policy</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Target</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Duration</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {mockActions.map((action) => {
                  const duration = action.endTime 
                    ? Math.round((new Date(action.endTime).getTime() - new Date(action.startTime).getTime()) / 1000)
                    : null;

                  return (
                    <TableRow key={action.id} className="hover:bg-accent/50">
                      <TableCell>
                        <div>
                          <div className="font-medium">{action.policyName}</div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{action.action}</Badge>
                      </TableCell>
                      <TableCell className="font-mono text-micro">
                        {action.target}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center space-x-2">
                          {getStatusIcon(action.status)}
                          <span className="capitalize">{action.status}</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-micro tabular-nums">
                        {formatTimestamp(action.startTime)}
                      </TableCell>
                      <TableCell className="text-micro tabular-nums">
                        {duration ? `${duration}s` : '-'}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </div>
      </div>
    </div>
  );
}