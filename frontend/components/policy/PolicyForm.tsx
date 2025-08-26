import React from 'react';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Switch } from '../ui/switch';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { toast } from 'sonner';
import { apiService } from '../../services/api';
import { defaultPolicy, PolicySpec, ValidationResult, DryRunResult } from './types';
import { TriggerEditor } from './TriggerEditor';
import { ActionList } from './ActionList';
import { ChevronLeft, ChevronRight, Copy, Download } from 'lucide-react';

export function PolicyForm({ initial, onSaved, onCancel }: { initial?: { id?: number; spec?: PolicySpec }; onSaved?: () => void; onCancel?: () => void }) {
  const [step, setStep] = React.useState(0);
  const [spec, setSpec] = React.useState<PolicySpec>(initial?.spec || defaultPolicy());
  const [originalSpec] = React.useState<PolicySpec | null>(initial?.spec || null);
  const [validation, setValidation] = React.useState<ValidationResult>({ ok: true, schema: [], compile: [] });
  const [dryRunResults, setDryRunResults] = React.useState<DryRunResult | null>(null);
  const [dryPlan, setDryPlan] = React.useState<any[] | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [validating, setValidating] = React.useState(false);

  const steps = [
    { name: 'Basics', key: 'basics' },
    { name: 'Trigger', key: 'trigger' },
    { name: 'Conditions', key: 'conditions' },
    { name: 'Actions', key: 'actions' },
    { name: 'Review', key: 'review' },
  ];

  // Reinitialize when switching to edit a different policy
  React.useEffect(() => {
    const nextSpec = initial?.spec ? (initial.spec as PolicySpec) : defaultPolicy();
    setSpec(nextSpec);
    setStep(0);
    setDryRunResults(null);
    setDryPlan(null);
    setValidation({ ok: true, schema: [], compile: [] });
  }, [initial?.id]);

  React.useEffect(() => {
    const timer = setTimeout(async () => {
      try {
        setValidating(true);
        const result = await apiService.validatePolicy(spec);
        const schemaErrors = Array.isArray((result as any).errors)
          ? (result as any).errors.map((msg: string) => ({ path: 'root', message: String(msg) }))
          : [];
        setValidation({ ok: schemaErrors.length === 0, schema: schemaErrors, compile: [] });
      } catch (e: any) {
        setValidation({ ok: false, schema: [{ path: 'root', message: e?.message || 'Validation error' }], compile: [] });
      } finally {
        setValidating(false);
      }
    }, 450);
    return () => clearTimeout(timer);
  }, [spec]);

  const runValidation = async () => {
    try {
      setValidating(true);
      const result = await apiService.validatePolicy(spec) as any;
      const schemaErrors = Array.isArray(result.errors)
        ? result.errors.map((msg: string) => ({ path: 'root', message: String(msg) }))
        : [];
      const mapped: ValidationResult = { ok: schemaErrors.length === 0, schema: schemaErrors, compile: [] };
      setValidation(mapped);
      setDryRunResults(null);
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

  const hasBlockingErrors = validation.schema.length > 0;
  const hasErrors = hasBlockingErrors || validation.compile.length > 0;
  const canSave = !hasBlockingErrors;
  const canEnable = canSave && !hasErrors;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 h-full">
      <div className="xl:col-span-2 space-y-6">
        <div className="flex items-center space-x-4 overflow-x-auto pb-2">
          {steps.map((s, i) => (
            <Button key={s.key} variant={i === step ? 'default' : 'outline'} size="sm" onClick={() => setStep(i)} className="whitespace-nowrap">
              {i + 1}. {s.name}
            </Button>
          ))}
        </div>

        <Card className="min-h-[500px]">
          <CardHeader>
            <CardTitle>{steps[step].name}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {step === 0 && <BasicStep spec={spec} setSpec={setSpec} validation={validation} />}
            {step === 1 && <TriggerStep spec={spec} setSpec={setSpec} />}
            {step === 2 && <ConditionsStep spec={spec} setSpec={setSpec} />}
            {step === 3 && <ActionsStep spec={spec} setSpec={setSpec} />}
            {step === 4 && (
              <ReviewStep spec={spec} originalSpec={originalSpec} validation={validation} dryRunResults={dryRunResults} onValidate={runValidation} validating={validating} />
            )}
          </CardContent>
        </Card>

        <div className="flex items-center justify-between">
          <Button variant="outline" onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0}>
            <ChevronLeft className="w-4 h-4 mr-2" />
            Previous
          </Button>
          <div className="flex gap-2">
            {step === steps.length - 1 ? (
              <>
                <Button variant="outline" onClick={() => save(false)} disabled={saving || !canSave}>Save Disabled</Button>
                <Button onClick={() => save(true)} disabled={saving || !canEnable}>Save & Enable</Button>
              </>
            ) : (
              <Button onClick={() => setStep(Math.min(steps.length - 1, step + 1))} disabled={step === steps.length - 1}>
                Next
                <ChevronRight className="w-4 h-4 ml-2" />
              </Button>
            )}
            <Button variant="ghost" onClick={onCancel}>Cancel</Button>
          </div>
        </div>
      </div>

      <div className="space-y-4">
        <ValidationConsole validation={validation} validating={validating} />
        <CompileConsole validation={validation} />
        <PreflightConsole dryRunResults={dryRunResults} />
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">Dry Run</CardTitle>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={runValidation} disabled={validating}>Validate</Button>
                <Button size="sm" onClick={async () => { try { setValidating(true); const res = await apiService.testPolicy(spec as any); (window as any)._lastDryPlan = res; setDryPlan((res as any)?.plan || []); } catch (e: any) { toast.error(e?.message || 'Dry run failed'); } finally { setValidating(false); } }}>Run</Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {!dryPlan || dryPlan.length === 0 ? (
              <div className="text-sm text-muted-foreground">No plan yet.</div>
            ) : (
              <div className="text-xs max-h-64 overflow-auto">
                {dryPlan.map((p: any, i: number) => (
                  <div key={i} className="mb-2 p-2 border rounded">
                    <div>Step {p.step}: {p.capability}.{p.verb} {p.host_only ? '(host)' : ''}</div>
                    {Array.isArray(p.targets) && p.targets.length > 0 && (
                      <div className="mt-1">Targets: {p.targets.map((t: any) => t.target).join(', ')}</div>
                    )}
                    {p.result && p.result.plan && (
                      <div className="mt-1">Preview: {JSON.stringify(p.result.plan.preview)}</div>
                    )}
                    {p.error && (<div className="text-destructive">Error: {p.error}</div>)}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
        <JsonMirror
          spec={spec}
          originalSpec={originalSpec}
          onCopy={() => { navigator.clipboard.writeText(JSON.stringify(spec, null, 2)); toast.success('JSON copied to clipboard'); }}
          onDownload={() => {
            const blob = new Blob([JSON.stringify(spec, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${spec.name || 'policy'}.json`;
            a.click();
            URL.revokeObjectURL(url);
          }}
        />
      </div>
    </div>
  );
}

function BasicStep({ spec, setSpec, validation }: { spec: PolicySpec; setSpec: (spec: PolicySpec) => void; validation: ValidationResult }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <Label>Name</Label>
          <Input value={spec.name} onChange={(e) => setSpec({ ...spec, name: e.target.value })} placeholder="Enter policy name" />
          {validation.schema.find(e => e.path.includes('name')) && (
            <div className="text-sm text-destructive mt-1">{validation.schema.find(e => e.path.includes('name'))?.message}</div>
          )}
        </div>
        <div>
          <Label>Priority (0 = highest)</Label>
          <Input type="number" value={spec.priority} onChange={(e) => setSpec({ ...spec, priority: parseInt(e.target.value) || 0 })} />
        </div>
      </div>

      <div className="flex items-center space-x-4">
        <div className="flex items-center space-x-2">
          <Switch checked={spec.enabled} onCheckedChange={(enabled) => setSpec({ ...spec, enabled })} />
          <Label>Enabled</Label>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <Label>Suppression Window</Label>
          <Input value={spec.safeties.suppression_window || ''} onChange={(e) => setSpec({ ...spec, safeties: { ...spec.safeties, suppression_window: e.target.value || undefined } })} placeholder="10m" />
        </div>
        <div>
          <Label>Global Lock (optional)</Label>
          <Input value={spec.safeties.global_lock || ''} onChange={(e) => setSpec({ ...spec, safeties: { ...spec.safeties, global_lock: e.target.value || undefined } })} placeholder="lock-name" />
        </div>
      </div>
    </div>
  );
}

function TriggerStep({ spec, setSpec }: { spec: PolicySpec; setSpec: (spec: PolicySpec) => void }) {
  return (
    <div className="space-y-4">
      <TriggerEditor value={spec.trigger as any} onChange={(t: any) => setSpec({ ...spec, trigger: t })} />
    </div>
  );
}

function ConditionsStep({ spec, setSpec }: { spec: PolicySpec; setSpec: (spec: PolicySpec) => void }) {
  type FieldType = 'number' | 'string' | 'boolean' | 'enum';
  const FIELD_DEFS: Record<string, { type: FieldType; options?: string[] }> = {
    // ups
    'ups.runtime_minutes': { type: 'number' },
    'ups.charge_pct': { type: 'number' },
    'ups.load_pct': { type: 'number' },
    'ups.status': { type: 'enum', options: ['on_mains', 'on_battery', 'charging', 'discharging', 'low_battery'] },
    // host
    'host.reachable': { type: 'boolean' },
    'host.latency_ms': { type: 'number' },
    'host.os_type': { type: 'string' },
    // metric
    'metric.charge_pct': { type: 'number' },
    'metric.load': { type: 'number' },
    'metric.runtime_seconds': { type: 'number' },
    // vm
    'vm.count_matching': { type: 'number' },
    'vm.state': { type: 'enum', options: ['running', 'stopped', 'paused'] },
  };

  const SCOPE_OPTIONS = ['ups', 'host', 'metric', 'vm'] as const;
  const allFields = Object.keys(FIELD_DEFS);
  const fieldsForScope = (scope: string) => allFields.filter((f) => f.startsWith(scope + '.')).map((f) => f.split('.')[1]);
  const opsForType = (t: FieldType) => t === 'number' ? ['>', '>=', '<', '<=', '=', '!='] : ['=', '!='];

  const add = (group: 'all' | 'any') => {
    const arr = [...((spec.conditions as any)[group] || [])];
    arr.push({ scope: 'ups', field: 'runtime_minutes', op: '>=', value: 1 });
    setSpec({ ...spec, conditions: { ...(spec.conditions as any), [group]: arr } as any });
  };
  const update = (group: 'all' | 'any', idx: number, patch: any) => {
    const arr = [...((spec.conditions as any)[group] || [])];
    arr[idx] = { ...arr[idx], ...patch };
    // If scope changes, reset field/op/value
    if (patch.scope) {
      const firstField = fieldsForScope(patch.scope)[0] || '';
      arr[idx].field = firstField;
      const t = FIELD_DEFS[`${patch.scope}.${firstField}`]?.type || 'string';
      arr[idx].op = opsForType(t)[0];
      arr[idx].value = t === 'boolean' ? false : '';
    }
    if (patch.field) {
      const key = `${arr[idx].scope}.${patch.field}`;
      const t = FIELD_DEFS[key]?.type || 'string';
      arr[idx].op = opsForType(t)[0];
      arr[idx].value = t === 'boolean' ? false : '';
    }
    setSpec({ ...spec, conditions: { ...(spec.conditions as any), [group]: arr } as any });
  };
  const remove = (group: 'all' | 'any', idx: number) => {
    const arr = ((spec.conditions as any)[group] || []).filter((_: any, i: number) => i !== idx);
    setSpec({ ...spec, conditions: { ...(spec.conditions as any), [group]: arr } as any });
  };

  const Group = ({ group }: { group: 'all' | 'any' }) => (
    <div>
      <div className="flex items-center justify-between mb-2"><Label>{group === 'all' ? 'All conditions (AND)' : 'Any conditions (OR)'}</Label><Button size="sm" variant="outline" onClick={() => add(group)}>Add</Button></div>
      <div className="space-y-2">
        {(((spec.conditions as any)[group] || []) as any[]).map((c, i) => {
          const key = `${c.scope}.${c.field}`;
          const def = FIELD_DEFS[key] || { type: 'string' as FieldType };
          const ops = opsForType(def.type);
          const fieldOptions = fieldsForScope(c.scope);
          return (
            <div key={`${group}-${i}`} className="grid grid-cols-1 md:grid-cols-6 gap-2 items-end">
              <div>
                <Label>Scope</Label>
                <select value={c.scope} onChange={(e) => update(group, i, { scope: e.target.value })} className="w-full p-2 border rounded text-sm">
                  {SCOPE_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <Label>Field</Label>
                <select value={c.field} onChange={(e) => update(group, i, { field: e.target.value })} className="w-full p-2 border rounded text-sm">
                  {fieldOptions.map((f) => <option key={f} value={f}>{f}</option>)}
                </select>
              </div>
              <div>
                <Label>Op</Label>
                <select value={c.op} onChange={(e) => update(group, i, { op: e.target.value })} className="w-full p-2 border rounded text-sm">
                  {ops.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              </div>
              <div className="md:col-span-2">
                <Label>Value</Label>
                {def.type === 'enum' && (
                  <select value={c.value || ''} onChange={(e) => update(group, i, { value: e.target.value })} className="w-full p-2 border rounded text-sm">
                    {(def.options || []).map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                  </select>
                )}
                {def.type === 'boolean' && (
                  <select value={String(c.value ?? false)} onChange={(e) => update(group, i, { value: e.target.value === 'true' })} className="w-full p-2 border rounded text-sm">
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                )}
                {def.type === 'number' && (
                  <Input type="number" value={c.value ?? 0} onChange={(e) => update(group, i, { value: Number(e.target.value) })} />
                )}
                {def.type === 'string' && (
                  <Input value={c.value ?? ''} onChange={(e) => update(group, i, { value: e.target.value })} />
                )}
              </div>
              <div className="flex"><Button size="sm" variant="ghost" onClick={() => remove(group, i)}>Remove</Button></div>
            </div>
          );
        })}
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <Group group="all" />
      <Group group="any" />
    </div>
  );
}

function ActionsStep({ spec, setSpec }: { spec: PolicySpec; setSpec: (spec: PolicySpec) => void }) {
  return (
    <div className="space-y-4">
      <ActionList value={spec.actions} onChange={(a) => setSpec({ ...spec, actions: a })} />
    </div>
  );
}

function ReviewStep({ spec, originalSpec, validation, dryRunResults, onValidate, validating }: { spec: PolicySpec; originalSpec: PolicySpec | null; validation: ValidationResult; dryRunResults: DryRunResult | null; onValidate: () => void; validating: boolean; }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Button size="sm" onClick={onValidate} disabled={validating}>Validate</Button>
        {validation.ok ? <span className="text-green-600 text-sm">OK</span> : <span className="text-destructive text-sm">Issues found</span>}
      </div>
      <div className="text-xs text-muted-foreground">Name: {spec.name || '(unnamed)'} • Priority: {spec.priority} • Enabled: {String(spec.enabled)}</div>
    </div>
  );
}

function ValidationConsole({ validation, validating }: { validation: ValidationResult; validating: boolean }) {
  const hasErrors = validation.schema.length > 0 || validation.compile.length > 0;
  return (
    <Card>
      <CardHeader className="pb-3"><CardTitle className="text-sm">Validation</CardTitle></CardHeader>
      <CardContent className="text-sm">
        {validating ? 'Validating…' : hasErrors ? (
          <ul className="list-disc pl-5 space-y-1">
            {validation.schema.map((e, i) => <li key={i}>{e.message}</li>)}
            {validation.compile.map((e, i) => <li key={i}>{e.message}</li>)}
          </ul>
        ) : 'OK'}
      </CardContent>
    </Card>
  );
}

function CompileConsole({ validation }: { validation: ValidationResult }) {
  return (
    <Card>
      <CardHeader className="pb-3"><CardTitle className="text-sm">Compile</CardTitle></CardHeader>
      <CardContent className="text-sm">
        {validation.compile.length === 0 ? 'No compile issues' : (
          <ul className="list-disc pl-5 space-y-1">
            {validation.compile.map((e, i) => <li key={i}>{e.message}</li>)}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function PreflightConsole({ dryRunResults }: { dryRunResults: DryRunResult | null }) {
  return (
    <Card>
      <CardHeader className="pb-3"><CardTitle className="text-sm">Preflight</CardTitle></CardHeader>
      <CardContent className="text-sm">{dryRunResults ? 'Planned actions available' : 'Run validation to view plan'}</CardContent>
    </Card>
  );
}

function JsonMirror({ spec, originalSpec, onCopy, onDownload }: { spec: PolicySpec; originalSpec: PolicySpec | null; onCopy: () => void; onDownload: () => void; }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">JSON</CardTitle>
          <div className="flex gap-1">
            <Button variant="ghost" size="sm" onClick={onCopy}><Copy className="w-3 h-3" /></Button>
            <Button variant="ghost" size="sm" onClick={onDownload}><Download className="w-3 h-3" /></Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <pre className="bg-muted/30 border rounded p-2 text-xs overflow-auto max-h-60 whitespace-pre-wrap">{JSON.stringify(spec, null, 2)}</pre>
      </CardContent>
    </Card>
  );
}
