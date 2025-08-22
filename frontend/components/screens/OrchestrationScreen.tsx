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
import { PolicyFlyout } from '../policy/PolicyFlyout';
import { apiService } from '../../services/api';
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
  id: number; 
  name: string; 
  enabled: boolean; 
  priority: number; 
  status: 'enabled' | 'disabled' | 'invalid';
  last_run_ts?: string;
  last_status?: 'info' | 'warn' | 'error';
  json?: any;
}

// Recent actions feed is not implemented yet; show empty table without mocks

export function OrchestrationScreen() {
  const [searchValue, setSearchValue] = useState('');
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards');
  const [activeFilters, setActiveFilters] = useState<string[]>([]);
  const [selectedPolicy, setSelectedPolicy] = useState<Policy | null>(null);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [flyoutOpen, setFlyoutOpen] = useState(false);
  const [edit, setEdit] = useState<{ id?: number; spec?: any } | undefined>(undefined);

  const reloadPolicies = async () => {
    try { const list = await apiService.listPolicies(); setPolicies(list as any); } catch (_) {}
  };
  React.useEffect(() => { reloadPolicies(); }, []);

  const availableFilters = ['Enabled', 'Disabled', 'Success', 'Failed', 'Pending'];

  const handleFilterToggle = (filter: string) => {
    setActiveFilters(prev => 
      prev.includes(filter) 
        ? prev.filter(f => f !== filter)
        : [...prev, filter]
    );
  };

  const togglePolicy = async (policyId: number | string) => {
    try {
      const p = policies.find(p => p.id === Number(policyId));
      if (!p) return;
      const next = { ...(p.json || {}), name: p.name, enabled: !p.enabled, priority: p.priority };
      await apiService.updatePolicy(p.id, next);
      await reloadPolicies();
    } catch (_) {}
  };

  const [planOpen, setPlanOpen] = useState(false);
  const [plan, setPlan] = useState<any[] | null>(null);
  const testPolicy = async (policyId: number | string) => {
    try {
      const p = policies.find(p => p.id === Number(policyId));
      if (!p) return;
      const res = await apiService.testPolicy(p.json);
      setPlan(res.plan || []);
      setPlanOpen(true);
    } catch (_) { setPlan(null); setPlanOpen(false); }
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
          <Button className="bg-status-info hover:bg-status-info/90" onClick={() => { setEdit(undefined); setFlyoutOpen(true); }}>
            <Plus className="w-4 h-4 mr-2" />
            Create Policy
          </Button>
        </div>

        {/* Policies Table */}
        <div className="bg-card rounded-lg border border-border overflow-hidden">
          <Table>
            <TableHeader className="bg-muted/30">
              <TableRow className="hover:bg-transparent">
                <TableHead>Name</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Priority</TableHead>
                <TableHead>Last Run</TableHead>
                <TableHead className="w-24">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {policies.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground py-6">
                    No policies configured yet
                  </TableCell>
                </TableRow>
              ) : (
                policies.map((policy) => (
                  <TableRow key={policy.id} className="hover:bg-muted/20">
                    <TableCell>
                      <div className="font-medium">{policy.name}</div>
                    </TableCell>
                    <TableCell>
                      <Badge variant={
                        policy.status === 'enabled' ? 'default' : 
                        policy.status === 'disabled' ? 'secondary' : 
                        'destructive'
                      }>
                        {policy.status}
                      </Badge>
                    </TableCell>
                    <TableCell>{policy.priority}</TableCell>
                    <TableCell>
                      {policy.last_run_ts ? (
                        <div className="flex items-center gap-2">
                          <span className="text-sm">{formatTimestamp(policy.last_run_ts)}</span>
                          <Badge 
                            variant={
                              policy.last_status === 'info' ? 'secondary' :
                              policy.last_status === 'warn' ? 'outline' :
                              'destructive'
                            }
                            className="text-xs"
                          >
                            {policy.last_status}
                          </Badge>
                        </div>
                      ) : (
                        <span className="text-muted-foreground">Never</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button 
                          variant="ghost" 
                          size="sm"
                          onClick={() => { setEdit({ id: policy.id, spec: policy.json }); setFlyoutOpen(true); }}
                        >
                          <Settings className="w-4 h-4" />
                        </Button>
                        <Button 
                          variant="ghost" 
                          size="sm"
                          onClick={() => testPolicy(policy.id)}
                        >
                          <Zap className="w-4 h-4" />
                        </Button>
                        <Switch 
                          size="sm"
                          checked={policy.enabled} 
                          onCheckedChange={() => togglePolicy(policy.id)}
                        />
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>

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
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground py-6">
                    No actions recorded yet
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </div>
        </div>
      </div>

      {/* Modals */}
      <PolicyFlyout open={flyoutOpen} onOpenChange={setFlyoutOpen} initial={edit} onSaved={reloadPolicies} />
      
      {planOpen && (
        <div className="fixed inset-0 bg-background/70 backdrop-blur z-50 p-6" onClick={() => setPlanOpen(false)}>
          <div className="max-w-2xl mx-auto bg-card border rounded-md p-4" onClick={e => e.stopPropagation()}>
            <div className="text-title mb-2">Dry Run Plan</div>
            <ol className="text-sm list-decimal ml-5 max-h-[50vh] overflow-auto">
              {(plan || []).map((s, i) => (
                <li key={i} className="mb-1">{s.capability} • {s.verb}</li>
              ))}
            </ol>
            <div className="text-right mt-3">
              <Button variant="outline" onClick={() => setPlanOpen(false)}>Close</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
