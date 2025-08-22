import React from 'react';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Switch } from '../ui/switch';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { Separator } from '../ui/separator';
import { toast } from 'sonner';
import { apiService, IntegrationType, IntegrationInstance } from '../../services/api';
import { 
  defaultPolicy, 
  PolicySpec, 
  TriggerType, 
  TriggerGroup, 
  Condition,
  PolicyAction,
  Host,
  HostCapability,
  InventoryItem,
  ValidationResult,
  DryRunResult
} from './types';
import { JsonPreviewDrawer } from './JsonPreviewDrawer';
import { TriggerEditor } from './TriggerEditor';
import { ActionList } from './ActionList';
import { TargetSelector } from './TargetSelector';
import { ChevronLeft, ChevronRight, Copy, Download, RotateCcw, CheckCircle2, AlertTriangle, XCircle } from 'lucide-react';

export function PolicyForm({ initial, onSaved, onCancel }: { initial?: { id?: number; spec?: PolicySpec }; onSaved?: () => void; onCancel?: () => void }) {
  const [step, setStep] = React.useState(0);
  const [spec, setSpec] = React.useState<PolicySpec>(initial?.spec || defaultPolicy());
  const [originalSpec, setOriginalSpec] = React.useState<PolicySpec | null>(initial?.spec || null);
  const [validation, setValidation] = React.useState<ValidationResult>({ ok: true, schema: [], compile: [] });
  const [dryRunResults, setDryRunResults] = React.useState<DryRunResult | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [validating, setValidating] = React.useState(false);
  const [hosts, setHosts] = React.useState<Host[]>([]);
  const [capabilities, setCapabilities] = React.useState<Record<string, HostCapability[]>>({});
  const [inventory, setInventory] = React.useState<Record<string, InventoryItem[]>>({});
  const [refreshingInventory, setRefreshingInventory] = React.useState<Record<string, boolean>>({});

  const steps = [
    { name: 'Basics', key: 'basics' },
    { name: 'Triggers', key: 'triggers' },
    { name: 'Conditions', key: 'conditions' },
    { name: 'Targets & Actions', key: 'targets' },
    { name: 'Review', key: 'review' }
  ];

  React.useEffect(() => {
    loadHosts();
  }, []);

  React.useEffect(() => {
    if (spec.targets.host_id) {
      loadHostCapabilities(spec.targets.host_id);
      loadHostInventory(spec.targets.host_id, true); // Start with refresh
    }
  }, [spec.targets.host_id]);

  // Live schema validation with debounce
  React.useEffect(() => {
    const timer = setTimeout(async () => {
      try {
        setValidating(true);
        const result = await apiService.validatePolicy(spec);
        setValidation(result as ValidationResult);
      } catch (e: any) {
        setValidation({ 
          ok: false, 
          schema: [{ path: 'root', message: e?.message || 'Validation error' }], 
          compile: [] 
        });
      } finally {
        setValidating(false);
      }
    }, 450);
    return () => clearTimeout(timer);
  }, [spec]);

  const loadHosts = async () => {
    try {
      const hosts = await apiService.getHosts();
      setHosts(hosts);
    } catch (e: any) {
      toast.error(e?.message || 'Failed to load hosts');
    }
  };

  const loadHostCapabilities = async (hostId: string) => {
    try {
      const caps = await apiService.getHostCapabilities(hostId);
      setCapabilities(prev => ({ ...prev, [hostId]: caps }));
    } catch (e: any) {
      toast.error(e?.message || 'Failed to load capabilities');
    }
  };

  const loadHostInventory = async (hostId: string, refresh = false) => {
    if (refresh) {
      setRefreshingInventory(prev => ({ ...prev, [hostId]: true }));
    }
    
    try {
      const items = await apiService.getHostInventory(hostId, refresh);
      setInventory(prev => ({ ...prev, [hostId]: items }));
    } catch (e: any) {
      toast.error(`Failed to ${refresh ? 'refresh' : 'load'} inventory: ${e?.message}`);
    } finally {
      if (refresh) {
        setRefreshingInventory(prev => ({ ...prev, [hostId]: false }));
      }
    }
  };

  const runValidation = async () => {
    try {
      setValidating(true);
      const result = await apiService.validatePolicy(spec);
      setValidation(result as ValidationResult);
      
      if (result.ok && initial?.id) {
        const dryRun = await apiService.dryRunPolicy(initial.id);
        setDryRunResults(dryRun as DryRunResult);
      }
    } catch (e: any) {
      toast.error(e?.message || 'Validation failed');
    } finally {
      setValidating(false);
    }
  };

  const save = async (enablePolicy = false) => {
    try {
      setSaving(true);
      const policyToSave = { ...spec, enabled: enablePolicy };
      
      if (initial?.id) {
        await apiService.updatePolicy(initial.id, policyToSave);
      } else {
        await apiService.createPolicy(policyToSave);
      }
      toast.success('Policy saved');
      onSaved?.();
    } catch (e: any) {
      toast.error(e?.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const createInverse = async () => {
    try {
      if (!initial?.id) {
        toast.error('Must save policy first');
        return;
      }
      const inverse = await apiService.createInversePolicy(initial.id);
      // Open new policy form with inverse spec
      toast.success('Inverse policy created');
    } catch (e: any) {
      toast.error(e?.message || 'Failed to create inverse');
    }
  };

  const downloadJson = () => {
    const blob = new Blob([JSON.stringify(spec, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${spec.name || 'policy'}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyJson = () => {
    navigator.clipboard.writeText(JSON.stringify(spec, null, 2));
    toast.success('JSON copied to clipboard');
  };

  const hasBlocingErrors = validation.schema.length > 0;
  const hasErrors = hasBlocingErrors || validation.compile.length > 0;
  const canSave = !hasBlocingErrors;
  const canEnable = canSave && !hasErrors;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 h-full">
      {/* Left: Wizard */}
      <div className="xl:col-span-2 space-y-6">
        {/* Step Navigation */}
        <div className="flex items-center space-x-4 overflow-x-auto pb-2">
          {steps.map((s, i) => (
            <Button
              key={s.key}
              variant={i === step ? 'default' : 'outline'}
              size="sm"
              onClick={() => setStep(i)}
              className="whitespace-nowrap"
            >
              {i + 1}. {s.name}
            </Button>
          ))}
        </div>

        {/* Step Content */}
        <Card className="min-h-[500px]">
          <CardHeader>
            <CardTitle>{steps[step].name}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {step === 0 && <BasicStep spec={spec} setSpec={setSpec} validation={validation} />}
            {step === 1 && <TriggersStep spec={spec} setSpec={setSpec} />}
            {step === 2 && <ConditionsStep spec={spec} setSpec={setSpec} />}
            {step === 3 && (
              <TargetsActionsStep 
                spec={spec} 
                setSpec={setSpec} 
                hosts={hosts}
                capabilities={capabilities[spec.targets.host_id] || []}
                inventory={inventory[spec.targets.host_id] || []}
                refreshingInventory={refreshingInventory[spec.targets.host_id] || false}
                onRefreshInventory={(hostId) => loadHostInventory(hostId, true)}
              />
            )}
            {step === 4 && (
              <ReviewStep 
                spec={spec}
                originalSpec={originalSpec}
                validation={validation}
                dryRunResults={dryRunResults}
                onValidate={runValidation}
                validating={validating}
              />
            )}
          </CardContent>
        </Card>

        {/* Navigation */}
        <div className="flex items-center justify-between">
          <Button
            variant="outline"
            onClick={() => setStep(Math.max(0, step - 1))}
            disabled={step === 0}
          >
            <ChevronLeft className="w-4 h-4 mr-2" />
            Previous
          </Button>

          <div className="flex gap-2">
            {step === steps.length - 1 ? (
              <>
                <Button variant="outline" onClick={() => save(false)} disabled={saving || !canSave}>
                  Save Disabled
                </Button>
                <Button onClick={() => save(true)} disabled={saving || !canEnable}>
                  Save & Enable
                </Button>
                {initial?.id && (
                  <Button variant="outline" onClick={createInverse}>
                    Create Inverse
                  </Button>
                )}
              </>
            ) : (
              <Button
                onClick={() => setStep(Math.min(steps.length - 1, step + 1))}
                disabled={step === steps.length - 1}
              >
                Next
                <ChevronRight className="w-4 h-4 ml-2" />
              </Button>
            )}
            <Button variant="ghost" onClick={onCancel}>Cancel</Button>
          </div>
        </div>
      </div>

      {/* Right: Console */}
      <div className="space-y-4">
        <ValidationConsole validation={validation} validating={validating} />
        <CompileConsole validation={validation} />
        <PreflightConsole dryRunResults={dryRunResults} />
        <JsonMirror spec={spec} originalSpec={originalSpec} onCopy={copyJson} onDownload={downloadJson} />
      </div>
    </div>
  );
}

// Step Components
function BasicStep({ spec, setSpec, validation }: { spec: PolicySpec; setSpec: (spec: PolicySpec) => void; validation: ValidationResult }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <Label>Name</Label>
          <Input 
            value={spec.name} 
            onChange={(e) => setSpec({ ...spec, name: e.target.value })} 
            placeholder="Enter policy name"
          />
          {validation.schema.find(e => e.path.includes('name')) && (
            <div className="text-sm text-destructive mt-1">
              {validation.schema.find(e => e.path.includes('name'))?.message}
            </div>
          )}
        </div>
        <div>
          <Label>Priority (0 = highest)</Label>
          <Input 
            type="number" 
            value={spec.priority} 
            onChange={(e) => setSpec({ ...spec, priority: parseInt(e.target.value) || 0 })} 
          />
        </div>
      </div>
      
      <div className="flex items-center space-x-4">
        <div className="flex items-center space-x-2">
          <Switch 
            checked={spec.enabled} 
            onCheckedChange={(enabled) => setSpec({ ...spec, enabled })} 
          />
          <Label>Enabled</Label>
        </div>
        <div className="flex items-center space-x-2">
          <Switch 
            checked={spec.stop_on_match} 
            onCheckedChange={(stop_on_match) => setSpec({ ...spec, stop_on_match })} 
          />
          <Label>Stop on Match</Label>
        </div>
        <div className="flex items-center space-x-2">
          <Switch 
            checked={spec.dynamic_resolution} 
            onCheckedChange={(dynamic_resolution) => setSpec({ ...spec, dynamic_resolution })} 
          />
          <Label>Dynamic Resolution</Label>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <Label>Suppression Window</Label>
          <Input 
            value={spec.suppression_window || ''} 
            onChange={(e) => setSpec({ ...spec, suppression_window: e.target.value || undefined })} 
            placeholder="5m"
          />
        </div>
        <div>
          <Label>Idempotency Window</Label>
          <Input 
            value={spec.idempotency_window || ''} 
            onChange={(e) => setSpec({ ...spec, idempotency_window: e.target.value || undefined })} 
            placeholder="10m"
          />
        </div>
      </div>

      <div>
        <Label>Notes</Label>
        <Input 
          value={spec.notes || ''} 
          onChange={(e) => setSpec({ ...spec, notes: e.target.value || undefined })} 
          placeholder="Optional description"
        />
      </div>
    </div>
  );
}

function TriggersStep({ spec, setSpec }: { spec: PolicySpec; setSpec: (spec: PolicySpec) => void }) {
  const addTrigger = () => {
    const newTrigger: TriggerType = { type: 'ups.state', equals: 'on_battery' };
    setSpec({
      ...spec,
      trigger_group: {
        ...spec.trigger_group,
        triggers: [...spec.trigger_group.triggers, newTrigger]
      }
    });
  };

  const removeTrigger = (index: number) => {
    setSpec({
      ...spec,
      trigger_group: {
        ...spec.trigger_group,
        triggers: spec.trigger_group.triggers.filter((_, i) => i !== index)
      }
    });
  };

  const updateTrigger = (index: number, trigger: TriggerType) => {
    const triggers = [...spec.trigger_group.triggers];
    triggers[index] = trigger;
    setSpec({
      ...spec,
      trigger_group: { ...spec.trigger_group, triggers }
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Label>Trigger Logic</Label>
        <div className="flex gap-2">
          <Button
            variant={spec.trigger_group.logic === 'ANY' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setSpec({ ...spec, trigger_group: { ...spec.trigger_group, logic: 'ANY' }})}
          >
            ANY
          </Button>
          <Button
            variant={spec.trigger_group.logic === 'ALL' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setSpec({ ...spec, trigger_group: { ...spec.trigger_group, logic: 'ALL' }})}
          >
            ALL
          </Button>
        </div>
      </div>

      <div className="space-y-3">
        {spec.trigger_group.triggers.map((trigger, index) => (
          <Card key={index}>
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-2">
                <Label>Trigger {index + 1}</Label>
                {spec.trigger_group.triggers.length > 1 && (
                  <Button variant="ghost" size="sm" onClick={() => removeTrigger(index)}>
                    Remove
                  </Button>
                )}
              </div>
              <TriggerEditor 
                trigger={trigger} 
                onChange={(t) => updateTrigger(index, t)}
              />
            </CardContent>
          </Card>
        ))}
      </div>

      <Button variant="outline" onClick={addTrigger} className="w-full">
        Add Trigger
      </Button>
    </div>
  );
}

function ConditionsStep({ spec, setSpec }: { spec: PolicySpec; setSpec: (spec: PolicySpec) => void }) {
  const addCondition = () => {
    const newCondition: Condition = {
      scope: 'ups',
      field: 'runtime_minutes',
      op: '>=',
      value: 5
    };
    setSpec({
      ...spec,
      conditions: {
        ...spec.conditions,
        all: [...spec.conditions.all, newCondition]
      }
    });
  };

  const removeCondition = (index: number) => {
    setSpec({
      ...spec,
      conditions: {
        ...spec.conditions,
        all: spec.conditions.all.filter((_, i) => i !== index)
      }
    });
  };

  const updateCondition = (index: number, condition: Condition) => {
    const conditions = [...spec.conditions.all];
    conditions[index] = condition;
    setSpec({
      ...spec,
      conditions: { ...spec.conditions, all: conditions }
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Label>Conditions (All must be true)</Label>
      </div>

      <div className="space-y-3">
        {spec.conditions.all.map((condition, index) => (
          <Card key={index}>
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-2">
                <Label>Condition {index + 1}</Label>
                <Button variant="ghost" size="sm" onClick={() => removeCondition(index)}>
                  Remove
                </Button>
              </div>
              <ConditionEditor 
                condition={condition} 
                onChange={(c) => updateCondition(index, c)}
              />
            </CardContent>
          </Card>
        ))}
      </div>

      <Button variant="outline" onClick={addCondition} className="w-full">
        Add Condition
      </Button>
    </div>
  );
}

function TargetsActionsStep({ 
  spec, 
  setSpec, 
  hosts,
  capabilities,
  inventory,
  refreshingInventory,
  onRefreshInventory 
}: { 
  spec: PolicySpec; 
  setSpec: (spec: PolicySpec) => void; 
  hosts: Host[];
  capabilities: HostCapability[];
  inventory: InventoryItem[];
  refreshingInventory: boolean;
  onRefreshInventory: (hostId: string) => void;
}) {
  const addAction = () => {
    const newAction: PolicyAction = {
      capability_id: '',
      verb: '',
      params: {}
    };
    setSpec({
      ...spec,
      actions: [...spec.actions, newAction]
    });
  };

  const removeAction = (index: number) => {
    setSpec({
      ...spec,
      actions: spec.actions.filter((_, i) => i !== index)
    });
  };

  const updateAction = (index: number, action: PolicyAction) => {
    const actions = [...spec.actions];
    actions[index] = action;
    setSpec({ ...spec, actions });
  };

  return (
    <div className="space-y-4">
      <TargetSelector
        targets={spec.targets}
        hosts={hosts}
        inventory={inventory}
        refreshingInventory={refreshingInventory}
        onChange={(targets) => setSpec({ ...spec, targets })}
        onRefreshInventory={onRefreshInventory}
      />

      <Separator />

      <div className="space-y-3">
        <Label>Actions</Label>
        {spec.actions.map((action, index) => (
          <Card key={index}>
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-2">
                <Label>Action {index + 1}</Label>
                <Button variant="ghost" size="sm" onClick={() => removeAction(index)}>
                  Remove
                </Button>
              </div>
              <ActionEditor 
                action={action} 
                capabilities={capabilities}
                onChange={(a) => updateAction(index, a)}
              />
            </CardContent>
          </Card>
        ))}
      </div>

      <Button variant="outline" onClick={addAction} className="w-full">
        Add Action
      </Button>
    </div>
  );
}

function ReviewStep({ 
  spec, 
  originalSpec, 
  validation, 
  dryRunResults, 
  onValidate, 
  validating 
}: { 
  spec: PolicySpec; 
  originalSpec: PolicySpec | null; 
  validation: ValidationResult; 
  dryRunResults: DryRunResult | null; 
  onValidate: () => void; 
  validating: boolean; 
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Label>Policy Specification</Label>
        <Button onClick={onValidate} disabled={validating}>
          {validating ? 'Validating...' : 'Validate'}
        </Button>
      </div>

      <div className="bg-muted/30 border rounded p-3 max-h-[400px] overflow-auto">
        <pre className="text-xs whitespace-pre-wrap">
          {JSON.stringify(spec, null, 2)}
        </pre>
      </div>

      {originalSpec && (
        <div>
          <Label>Changes from Original</Label>
          <div className="bg-muted/30 border rounded p-3 max-h-[200px] overflow-auto text-xs">
            <div className="text-green-600">+ New values</div>
            <div className="text-red-600">- Original values</div>
            {/* Simplified diff - in real app would use a proper diff library */}
          </div>
        </div>
      )}
    </div>
  );
}

// Console Components
function ValidationConsole({ validation, validating }: { validation: ValidationResult; validating: boolean }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <CardTitle className="text-sm">Schema</CardTitle>
          {validating && <div className="w-4 h-4 border-2 border-muted border-t-foreground rounded-full animate-spin" />}
        </div>
      </CardHeader>
      <CardContent className="text-sm">
        {validation.schema.length === 0 ? (
          <div className="flex items-center gap-2 text-green-600">
            <CheckCircle2 className="w-4 h-4" />
            Schema valid
          </div>
        ) : (
          <div className="space-y-1">
            {validation.schema.map((error, i) => (
              <div key={i} className="flex items-center gap-2 text-red-600">
                <XCircle className="w-4 h-4" />
                <span>{error.path}: {error.message}</span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function CompileConsole({ validation }: { validation: ValidationResult }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">Compile</CardTitle>
      </CardHeader>
      <CardContent className="text-sm">
        {validation.compile.length === 0 ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-green-600">
              <CheckCircle2 className="w-4 h-4" />
              Compile successful
            </div>
            {validation.hash && (
              <div className="text-xs text-muted-foreground">
                IR Hash: {validation.hash.substring(0, 8)}...
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-1">
            {validation.compile.map((error, i) => (
              <div key={i} className="flex items-center gap-2 text-red-600">
                <XCircle className="w-4 h-4" />
                <span>{error.path}: {error.message}</span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PreflightConsole({ dryRunResults }: { dryRunResults: DryRunResult | null }) {
  if (!dryRunResults) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Preflight</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Run validation to see preflight results
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">Preflight</CardTitle>
      </CardHeader>
      <CardContent className="text-sm space-y-2">
        <div className="flex items-center gap-2">
          {dryRunResults.severity === 'info' ? (
            <CheckCircle2 className="w-4 h-4 text-green-600" />
          ) : dryRunResults.severity === 'warn' ? (
            <AlertTriangle className="w-4 h-4 text-yellow-600" />
          ) : (
            <XCircle className="w-4 h-4 text-red-600" />
          )}
          <span>Severity: {dryRunResults.severity}</span>
        </div>
        
        <div className="space-y-1 max-h-40 overflow-auto">
          {dryRunResults.results.map((result, i) => (
            <div key={i} className="text-xs border-l-2 border-muted pl-2">
              <div>{result.target_id}: {result.capability}.{result.verb}</div>
              <div className="text-muted-foreground">{result.effects.summary}</div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function JsonMirror({ 
  spec, 
  originalSpec, 
  onCopy, 
  onDownload 
}: { 
  spec: PolicySpec; 
  originalSpec: PolicySpec | null; 
  onCopy: () => void; 
  onDownload: () => void; 
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">JSON</CardTitle>
          <div className="flex gap-1">
            <Button variant="ghost" size="sm" onClick={onCopy}>
              <Copy className="w-3 h-3" />
            </Button>
            <Button variant="ghost" size="sm" onClick={onDownload}>
              <Download className="w-3 h-3" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <pre className="bg-muted/30 border rounded p-2 text-xs overflow-auto max-h-60 whitespace-pre-wrap">
          {JSON.stringify(spec, null, 2)}
        </pre>
      </CardContent>
    </Card>
  );
}

// Helper Components
function TriggerEditor({ trigger, onChange }: { trigger: TriggerType; onChange: (trigger: TriggerType) => void }) {
  const [type, setType] = React.useState(trigger.type);

  const handleTypeChange = (newType: TriggerType['type']) => {
    setType(newType);
    // Reset trigger with new type
    switch (newType) {
      case 'ups.state':
        onChange({ type: 'ups.state', equals: 'on_battery' });
        break;
      case 'metric.threshold':
        onChange({ type: 'metric.threshold', metric: 'load', op: '>', value: 60 });
        break;
      case 'timer.at':
        onChange({ type: 'timer.at', schedule: { repeat: 'daily', at: '01:00' } });
        break;
      case 'timer.after':
        onChange({ type: 'timer.after', after: '10m', since_event: { type: 'ups.state', equals: 'on_mains' } });
        break;
    }
  };

  return (
    <div className="space-y-3">
      <div>
        <Label>Type</Label>
        <div className="flex gap-2 mt-1">
          {['ups.state', 'metric.threshold', 'timer.at', 'timer.after'].map((t) => (
            <Button
              key={t}
              variant={type === t ? 'default' : 'outline'}
              size="sm"
              onClick={() => handleTypeChange(t as TriggerType['type'])}
            >
              {t.split('.')[1]}
            </Button>
          ))}
        </div>
      </div>

      {trigger.type === 'ups.state' && (
        <div>
          <Label>State</Label>
          <Input
            value={trigger.equals}
            onChange={(e) => onChange({ ...trigger, equals: e.target.value })}
            placeholder="on_battery"
          />
        </div>
      )}

      {trigger.type === 'metric.threshold' && (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2">
            <div>
              <Label>Metric</Label>
              <select
                value={trigger.metric}
                onChange={(e) => onChange({ ...trigger, metric: e.target.value })}
                className="w-full p-2 border rounded text-sm"
              >
                <option value="load">Load</option>
                <option value="charge_pct">Battery Charge %</option>
                <option value="runtime_seconds">Runtime</option>
                <option value="temperature">Temperature</option>
              </select>
            </div>
            <div>
              <Label>Operator</Label>
              <select
                value={trigger.op}
                onChange={(e) => onChange({ ...trigger, op: e.target.value })}
                className="w-full p-2 border rounded text-sm"
              >
                <option value=">">Greater than</option>
                <option value=">=">Greater or equal</option>
                <option value="<">Less than</option>
                <option value="<=">Less or equal</option>
                <option value="=">Equal to</option>
                <option value="!=">Not equal to</option>
              </select>
            </div>
            <div>
              <Label>Value</Label>
              <Input
                type="number"
                value={trigger.value}
                onChange={(e) => onChange({ ...trigger, value: parseFloat(e.target.value) || 0 })}
                placeholder="60"
              />
            </div>
          </div>
          
          {trigger.for && (
            <div>
              <Label>For Duration</Label>
              <DurationPicker
                value={trigger.for}
                onChange={(duration) => onChange({ ...trigger, for: duration })}
              />
            </div>
          )}
          
          <div className="flex items-center space-x-2">
            <Switch
              checked={!!trigger.for}
              onCheckedChange={(checked) => {
                if (checked) {
                  onChange({ ...trigger, for: '60s' });
                } else {
                  const { for: _, ...rest } = trigger;
                  onChange(rest as any);
                }
              }}
            />
            <Label>Require stable duration</Label>
          </div>
        </div>
      )}

      {trigger.type === 'timer.at' && (
        <TimerAtEditor
          schedule={trigger.schedule}
          onChange={(schedule) => onChange({ ...trigger, schedule })}
        />
      )}

      {trigger.type === 'timer.after' && (
        <TimerAfterEditor
          after={trigger.after}
          sinceEvent={trigger.since_event}
          onChange={(after, since_event) => onChange({ ...trigger, after, since_event })}
        />
      )}
    </div>
  );
}

function ConditionEditor({ condition, onChange }: { condition: Condition; onChange: (condition: Condition) => void }) {
  return (
    <div className="grid grid-cols-4 gap-2">
      <div>
        <Label>Scope</Label>
        <select
          value={condition.scope}
          onChange={(e) => onChange({ ...condition, scope: e.target.value as Condition['scope'] })}
          className="w-full p-2 border rounded text-sm"
        >
          <option value="ups">UPS</option>
          <option value="host">Host</option>
          <option value="metric">Metric</option>
          <option value="vm">VM</option>
        </select>
      </div>
      <div>
        <Label>Field</Label>
        <Input
          value={condition.field}
          onChange={(e) => onChange({ ...condition, field: e.target.value })}
          placeholder="runtime_minutes"
        />
      </div>
      <div>
        <Label>Operator</Label>
        <select
          value={condition.op}
          onChange={(e) => onChange({ ...condition, op: e.target.value })}
          className="w-full p-2 border rounded text-sm"
        >
          <option value="=">=</option>
          <option value="!=">!=</option>
          <option value=">">></option>
          <option value=">=">>=</option>
          <option value="<">&lt;</option>
          <option value="<=">&lt;=</option>
        </select>
      </div>
      <div>
        <Label>Value</Label>
        <Input
          value={condition.value}
          onChange={(e) => onChange({ ...condition, value: e.target.value })}
          placeholder="5"
        />
      </div>
    </div>
  );
}

function ActionEditor({ 
  action, 
  capabilities, 
  onChange 
}: { 
  action: PolicyAction; 
  capabilities: HostCapability[]; 
  onChange: (action: PolicyAction) => void; 
}) {
  const selectedCapability = capabilities.find(c => c.id === action.capability_id);
  const availableVerbs = selectedCapability?.verbs || [];

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label>Capability</Label>
          <select
            value={action.capability_id}
            onChange={(e) => onChange({ ...action, capability_id: e.target.value, verb: '' })}
            className="w-full p-2 border rounded text-sm"
          >
            <option value="">Select capability</option>
            {capabilities.map(cap => (
              <option key={cap.id} value={cap.id}>{cap.id}</option>
            ))}
          </select>
        </div>
        <div>
          <Label>Verb</Label>
          <select
            value={action.verb}
            onChange={(e) => onChange({ ...action, verb: e.target.value })}
            className="w-full p-2 border rounded text-sm"
            disabled={!action.capability_id}
          >
            <option value="">Select verb</option>
            {availableVerbs.map(verb => (
              <option key={verb} value={verb}>{verb}</option>
            ))}
          </select>
        </div>
      </div>

      {selectedCapability?.invertible?.[action.verb] && (
        <div className="text-xs text-blue-600">
          ↔️ Can be inverted to: {selectedCapability.invertible[action.verb].inverse}
        </div>
      )}

      <div>
        <Label>Parameters (JSON)</Label>
        <textarea
          value={JSON.stringify(action.params, null, 2)}
          onChange={(e) => {
            try {
              const params = JSON.parse(e.target.value);
              onChange({ ...action, params });
            } catch {
              // Invalid JSON, ignore
            }
          }}
          className="w-full p-2 border rounded text-sm font-mono"
          rows={3}
          placeholder="{}"
        />
      </div>
    </div>
  );
}

// Timer and Duration Components
function DurationPicker({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [amount, setAmount] = React.useState(1);
  const [unit, setUnit] = React.useState('s');

  React.useEffect(() => {
    // Parse existing duration like "120s", "5m", "1h"
    const match = value.match(/^(\d+)([smhd])$/);
    if (match) {
      setAmount(parseInt(match[1]));
      setUnit(match[2]);
    }
  }, [value]);

  React.useEffect(() => {
    onChange(`${amount}${unit}`);
  }, [amount, unit, onChange]);

  const presets = [
    { label: '30 seconds', value: '30s' },
    { label: '1 minute', value: '60s' },
    { label: '2 minutes', value: '120s' },
    { label: '5 minutes', value: '5m' },
    { label: '10 minutes', value: '10m' },
    { label: '30 minutes', value: '30m' },
    { label: '1 hour', value: '1h' },
  ];

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Input
          type="number"
          value={amount}
          onChange={(e) => setAmount(parseInt(e.target.value) || 1)}
          className="w-20"
          min={1}
        />
        <select
          value={unit}
          onChange={(e) => setUnit(e.target.value)}
          className="p-2 border rounded text-sm"
        >
          <option value="s">seconds</option>
          <option value="m">minutes</option>
          <option value="h">hours</option>
          <option value="d">days</option>
        </select>
      </div>
      
      <div className="flex flex-wrap gap-1">
        {presets.map((preset) => (
          <Button
            key={preset.value}
            variant="outline"
            size="sm"
            onClick={() => onChange(preset.value)}
            className="text-xs"
          >
            {preset.label}
          </Button>
        ))}
      </div>
      
      <div className="text-xs text-muted-foreground">
        Human readable: {formatDuration(value)}
      </div>
    </div>
  );
}

function TimerAtEditor({
  schedule,
  onChange
}: {
  schedule: { repeat: string; at: string; days?: string[] };
  onChange: (schedule: { repeat: string; at: string; days?: string[] }) => void;
}) {
  const [cronPreview, setCronPreview] = React.useState('');

  React.useEffect(() => {
    // Generate cron expression preview
    const cron = scheduleToCron(schedule);
    setCronPreview(cron);
  }, [schedule]);

  const timePresets = [
    { label: 'Midnight', value: '00:00' },
    { label: '1 AM', value: '01:00' },
    { label: '6 AM', value: '06:00' },
    { label: 'Noon', value: '12:00' },
    { label: '6 PM', value: '18:00' },
    { label: '11 PM', value: '23:00' },
  ];

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label>Repeat</Label>
          <select
            value={schedule.repeat}
            onChange={(e) => onChange({ ...schedule, repeat: e.target.value })}
            className="w-full p-2 border rounded text-sm"
          >
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
            <option value="hourly">Hourly</option>
          </select>
        </div>
        <div>
          <Label>At Time</Label>
          <Input
            type="time"
            value={schedule.at}
            onChange={(e) => onChange({ ...schedule, at: e.target.value })}
          />
        </div>
      </div>
      
      <div className="flex flex-wrap gap-1">
        {timePresets.map((preset) => (
          <Button
            key={preset.value}
            variant="outline"
            size="sm"
            onClick={() => onChange({ ...schedule, at: preset.value })}
            className="text-xs"
          >
            {preset.label}
          </Button>
        ))}
      </div>

      {schedule.repeat === 'weekly' && (
        <div>
          <Label>Days of Week</Label>
          <div className="flex flex-wrap gap-1 mt-1">
            {['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'].map((day) => (
              <Button
                key={day}
                variant={schedule.days?.includes(day) ? 'default' : 'outline'}
                size="sm"
                onClick={() => {
                  const days = schedule.days || [];
                  const newDays = days.includes(day)
                    ? days.filter(d => d !== day)
                    : [...days, day];
                  onChange({ ...schedule, days: newDays });
                }}
                className="text-xs capitalize"
              >
                {day}
              </Button>
            ))}
          </div>
        </div>
      )}

      <div className="text-xs text-muted-foreground bg-muted/30 p-2 rounded">
        Cron: {cronPreview}
      </div>
    </div>
  );
}

function TimerAfterEditor({
  after,
  sinceEvent,
  onChange
}: {
  after: string;
  sinceEvent: { type: string; equals: string };
  onChange: (after: string, sinceEvent: { type: string; equals: string }) => void;
}) {
  return (
    <div className="space-y-3">
      <div>
        <Label>After Duration</Label>
        <DurationPicker
          value={after}
          onChange={(duration) => onChange(duration, sinceEvent)}
        />
      </div>

      <div>
        <Label>Since Event</Label>
        <div className="grid grid-cols-2 gap-2">
          <select
            value={sinceEvent.type}
            onChange={(e) => onChange(after, { ...sinceEvent, type: e.target.value })}
            className="p-2 border rounded text-sm"
          >
            <option value="ups.state">UPS State</option>
            <option value="metric.threshold">Metric Threshold</option>
            <option value="host.state">Host State</option>
          </select>
          <Input
            value={sinceEvent.equals}
            onChange={(e) => onChange(after, { ...sinceEvent, equals: e.target.value })}
            placeholder={sinceEvent.type === 'ups.state' ? 'on_mains' : 'event_value'}
          />
        </div>
      </div>

      <div className="text-xs text-muted-foreground">
        Will trigger {formatDuration(after)} after {sinceEvent.type} becomes "{sinceEvent.equals}"
      </div>
    </div>
  );
}

// Utility functions
function formatDuration(duration: string): string {
  const match = duration.match(/^(\d+)([smhd])$/);
  if (!match) return duration;
  
  const amount = parseInt(match[1]);
  const unit = match[2];
  
  const units = {
    s: amount === 1 ? 'second' : 'seconds',
    m: amount === 1 ? 'minute' : 'minutes', 
    h: amount === 1 ? 'hour' : 'hours',
    d: amount === 1 ? 'day' : 'days'
  };
  
  return `${amount} ${units[unit as keyof typeof units]}`;
}

function scheduleToCron(schedule: { repeat: string; at: string; days?: string[] }): string {
  const [hour, minute] = schedule.at.split(':').map(n => parseInt(n));
  
  const dayMap: Record<string, number> = {
    sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6
  };
  
  switch (schedule.repeat) {
    case 'hourly':
      return `${minute} * * * *`;
    case 'daily':
      return `${minute} ${hour} * * *`;
    case 'weekly':
      const days = (schedule.days || ['sun']).map(d => dayMap[d]).sort().join(',');
      return `${minute} ${hour} * * ${days}`;
    case 'monthly':
      return `${minute} ${hour} 1 * *`;
    default:
      return `${minute} ${hour} * * *`;
  }
}
