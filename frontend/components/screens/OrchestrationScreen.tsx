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
import { formatDateLocal, formatTimeLocal } from '../../utils/time';
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
      const res = await apiService.dryRunPolicyById(p.id);
      setPlan(res.results || []);
      setPlanOpen(true);
    } catch (_) { setPlan(null); setPlanOpen(false); }
  };

  const formatTimestamp = (timestamp: string) => `${formatDateLocal(timestamp, { month: 'short', day: 'numeric' })} ${formatTimeLocal(timestamp)}`;

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

      <div className="max-w-7xl mx-auto p-6 space-y-6 mt-4 md:mt-6">
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
                      {(() => {
                        const s = (policy as any).last_status as string | undefined;
                        const c = s === 'error' || s === 'failed'
                          ? 'bg-status-error'
                          : s === 'warn'
                          ? 'bg-status-warn'
                          : s === 'info' || s === 'ok' || s === 'success'
                          ? 'bg-status-ok'
                          : (policy as any).enabled === true
                          ? 'bg-status-ok'
                          : 'bg-muted';
                        return (
                          <div className="flex items-center gap-2">
                            <span className={`inline-block w-1.5 h-4 rounded ${c}`} aria-hidden />
                            <div className="font-medium">{policy.name}</div>
                          </div>
                        );
                      })()}
                    </TableCell>
                    <TableCell>
                      {(() => {
                        const derived = (policy as any).status || ((policy as any).enabled ? 'enabled' : 'disabled');
                        const variant = derived === 'enabled' ? 'default' : derived === 'disabled' ? 'secondary' : 'destructive';
                        return (
                          <Badge variant={variant}>
                            {derived}
                          </Badge>
                        );
                      })()}
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
            <div className="text-title mb-2">Dry Run Results</div>
            <div className="text-xs text-muted-foreground mb-2">Severity colors indicate driver preflight outcome per target.</div>
            <div className="max-h-[55vh] overflow-auto space-y-2">
              {(plan || []).map((r: any, i: number) => (
                <div key={i} className="border rounded p-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className={`inline-block w-1.5 h-3 rounded ${r.severity==='error'?'bg-status-error':r.severity==='warn'?'bg-status-warn':'bg-status-ok'}`} />
                      <span className="font-medium">{r.capability} • {r.verb}</span>
                      {r.target_id && <span className="text-micro text-muted-foreground">{r.target_id}</span>}
                    </div>
                    {typeof r.ok === 'boolean' && (
                      <Badge variant={r.severity==='error'?'destructive':r.severity==='warn'?'outline':'secondary'} className="text-2xs">{r.severity || (r.ok ? 'info' : 'error')}</Badge>
                    )}
                  </div>
                  {r.effects?.summary && (
                    <div className="text-sm mt-1">{r.effects.summary}</div>
                  )}
                  {r.plan?.preview && (
                    <pre className="bg-muted/30 text-xs p-2 rounded mt-2 overflow-auto">{JSON.stringify(r.plan.preview, null, 2)}</pre>
                  )}
                  {Array.isArray(r.preconditions) && r.preconditions.length > 0 && (
                    <details className="mt-2">
                      <summary className="text-xs cursor-pointer">Preconditions</summary>
                      <ul className="text-xs list-disc ml-5 mt-1">
                        {r.preconditions.map((p: any, idx: number) => (
                          <li key={idx}>{p.check}: {String(p.ok)}{p.details?` – ${JSON.stringify(p.details)}`:''}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              ))}
            </div>
            <div className="text-right mt-3">
              <Button variant="outline" onClick={() => setPlanOpen(false)}>Close</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
