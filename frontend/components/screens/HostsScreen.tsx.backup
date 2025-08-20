import React, { useState } from 'react';
import { SecondaryToolbar } from '../SecondaryToolbar';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { 
  Plus, 
  Play, 
  Terminal,
  Eye,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Server,
  HardDrive,
  Laptop
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
import { Textarea } from '../ui/textarea';

interface Host {
  id: string;
  name: string;
  type: 'linux' | 'truenas' | 'proxmox' | 'other';
  ip: string;
  port: number;
  authMethod: 'key' | 'password';
  lastContact: string;
  lastActionResult: 'success' | 'failed' | 'pending' | 'never';
  status: 'online' | 'offline' | 'unknown';
  osInfo?: string;
  uptime?: string;
  description?: string;
}

const mockHosts: Host[] = [
  {
    id: '1',
    name: 'srv-pbs-01',
    type: 'linux',
    ip: '192.168.1.10',
    port: 22,
    authMethod: 'key',
    lastContact: '2024-01-15T15:42:00Z',
    lastActionResult: 'success',
    status: 'online',
    osInfo: 'Ubuntu 22.04.3 LTS',
    uptime: '15d 3h 42m',
    description: 'Proxmox Backup Server'
  },
  {
    id: '2',
    name: 'truenas-main',
    type: 'truenas',
    ip: '192.168.1.20',
    port: 22,
    authMethod: 'password',
    lastContact: '2024-01-15T15:41:30Z',
    lastActionResult: 'success',
    status: 'online',
    osInfo: 'TrueNAS Scale 24.04',
    uptime: '22d 8h 15m',
    description: 'Main NAS storage'
  },
  {
    id: '3',
    name: 'pve-node1',
    type: 'proxmox',
    ip: '192.168.1.30',
    port: 22,
    authMethod: 'key',
    lastContact: '2024-01-15T15:40:00Z',
    lastActionResult: 'failed',
    status: 'online',
    osInfo: 'Proxmox VE 8.1.4',
    uptime: '8d 14h 22m',
    description: 'Proxmox hypervisor node'
  },
  {
    id: '4',
    name: 'monitoring-pi',
    type: 'linux',
    ip: '192.168.1.100',
    port: 22,
    authMethod: 'key',
    lastContact: '2024-01-15T14:30:00Z',
    lastActionResult: 'never',
    status: 'offline',
    osInfo: 'Raspberry Pi OS',
    description: 'Monitoring and alerts'
  }
];

const hostTypeIcons = {
  linux: <Server className="w-4 h-4" />,
  truenas: <HardDrive className="w-4 h-4" />,
  proxmox: <Server className="w-4 h-4" />,
  other: <Laptop className="w-4 h-4" />
};

const hostTypeLabels = {
  linux: 'Linux Server',
  truenas: 'TrueNAS',
  proxmox: 'Proxmox',
  other: 'Other'
};

export function HostsScreen() {
  const [searchValue, setSearchValue] = useState('');
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('table');
  const [activeFilters, setActiveFilters] = useState<string[]>([]);
  const [selectedHost, setSelectedHost] = useState<Host | null>(null);
  const [showAddDialog, setShowAddDialog] = useState(false);

  const availableFilters = ['Online', 'Offline', 'Linux', 'TrueNAS', 'Proxmox', 'Key Auth', 'Password Auth'];

  const handleFilterToggle = (filter: string) => {
    setActiveFilters(prev => 
      prev.includes(filter) 
        ? prev.filter(f => f !== filter)
        : [...prev, filter]
    );
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
      case 'online':
        return <CheckCircle2 className="w-4 h-4 text-status-ok" />;
      case 'offline':
        return <XCircle className="w-4 h-4 text-status-error" />;
      default:
        return <AlertTriangle className="w-4 h-4 text-status-warn" />;
    }
  };

  const getActionResultBadge = (result: string) => {
    switch (result) {
      case 'success':
        return <Badge variant="secondary" className="bg-status-ok/10 text-status-ok border-0">Success</Badge>;
      case 'failed':
        return <Badge variant="secondary" className="bg-status-error/10 text-status-error border-0">Failed</Badge>;
      case 'pending':
        return <Badge variant="secondary" className="bg-status-warn/10 text-status-warn border-0">Pending</Badge>;
      default:
        return <Badge variant="outline">Never</Badge>;
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
            <h1 className="text-display">Managed Hosts</h1>
            <p className="text-micro text-muted-foreground mt-1">
              Servers and devices configured for UPS orchestration
            </p>
          </div>
          <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
            <DialogTrigger asChild>
              <Button className="bg-status-info hover:bg-status-info/90">
                <Plus className="w-4 h-4 mr-2" />
                Add Host
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-md">
              <DialogHeader>
                <DialogTitle>Add New Host</DialogTitle>
                <DialogDescription>
                  Configure a new host for UPS orchestration
                </DialogDescription>
              </DialogHeader>
              
              <div className="space-y-4 py-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="host-name">Name</Label>
                    <Input id="host-name" placeholder="srv-example-01" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="host-type">Type</Label>
                    <Select>
                      <SelectTrigger>
                        <SelectValue placeholder="Select type" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="linux">Linux Server</SelectItem>
                        <SelectItem value="truenas">TrueNAS</SelectItem>
                        <SelectItem value="proxmox">Proxmox</SelectItem>
                        <SelectItem value="other">Other</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                
                <div className="grid grid-cols-3 gap-4">
                  <div className="space-y-2 col-span-2">
                    <Label htmlFor="host-ip">IP Address</Label>
                    <Input id="host-ip" placeholder="192.168.1.10" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="host-port">Port</Label>
                    <Input id="host-port" placeholder="22" defaultValue="22" />
                  </div>
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="host-user">Username</Label>
                  <Input id="host-user" placeholder="root" />
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="host-auth">Authentication</Label>
                  <Select>
                    <SelectTrigger>
                      <SelectValue placeholder="Select method" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="key">SSH Key</SelectItem>
                      <SelectItem value="password">Password</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="host-description">Description (optional)</Label>
                  <Textarea 
                    id="host-description" 
                    placeholder="Brief description of this host"
                    className="h-16"
                  />
                </div>
              </div>

              <DialogFooter>
                <Button variant="outline" onClick={() => setShowAddDialog(false)}>
                  Cancel
                </Button>
                <Button>
                  <CheckCircle2 className="w-4 h-4 mr-2" />
                  Add & Test
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>

        {/* Hosts Table */}
        <div className="bg-card rounded-lg border border-border overflow-hidden">
          <Table>
            <TableHeader className="bg-muted/30">
              <TableRow className="hover:bg-transparent">
                <TableHead>Host</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Address</TableHead>
                <TableHead>Auth</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last Contact</TableHead>
                <TableHead>Last Action</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {mockHosts.map((host) => (
                <TableRow key={host.id} className="hover:bg-accent/50">
                  <TableCell>
                    <div>
                      <div className="flex items-center space-x-2">
                        {hostTypeIcons[host.type]}
                        <span className="font-medium">{host.name}</span>
                      </div>
                      {host.description && (
                        <div className="text-micro text-muted-foreground mt-1">
                          {host.description}
                        </div>
                      )}
                      {host.osInfo && (
                        <div className="text-micro text-muted-foreground">
                          {host.osInfo}
                        </div>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">
                      {hostTypeLabels[host.type]}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="font-mono text-micro">
                      <div>{host.ip}:{host.port}</div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant={host.authMethod === 'key' ? 'secondary' : 'outline'}>
                      {host.authMethod === 'key' ? 'SSH Key' : 'Password'}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center space-x-2">
                      {getStatusIcon(host.status)}
                      <span className="capitalize">{host.status}</span>
                    </div>
                    {host.uptime && (
                      <div className="text-micro text-muted-foreground">
                        Up: {host.uptime}
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="text-micro tabular-nums">
                    {formatTimestamp(host.lastContact)}
                  </TableCell>
                  <TableCell>
                    {getActionResultBadge(host.lastActionResult)}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center space-x-1">
                      <Button variant="ghost" size="sm">
                        <CheckCircle2 className="w-3 h-3 mr-1" />
                        Test
                      </Button>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="sm">
                            <Terminal className="w-3 h-3 mr-1" />
                            Run
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem>
                            <Play className="w-3 h-3 mr-2" />
                            Test Connection
                          </DropdownMenuItem>
                          <DropdownMenuItem>
                            <Terminal className="w-3 h-3 mr-2" />
                            Shell Access
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem>
                            Graceful Shutdown
                          </DropdownMenuItem>
                          <DropdownMenuItem>
                            Restart Services
                          </DropdownMenuItem>
                          <DropdownMenuItem>
                            Check System Status
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                      <Button variant="ghost" size="sm">
                        <Eye className="w-3 h-3" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}