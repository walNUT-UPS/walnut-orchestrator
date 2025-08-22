import React from 'react';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Switch } from '../ui/switch';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Separator } from '../ui/separator';
import { toast } from 'sonner';
import { apiService, IntegrationType, IntegrationInstance } from '../../services/api';
import { defaultPolicy, PolicySpec } from './types';
import { TriggerEditor } from './TriggerEditor';
import { ActionList } from './ActionList';

export function PolicyForm({ initial, onSaved, onCancel }: { initial?: { id?: number; spec?: PolicySpec }; onSaved?: () => void; onCancel?: () => void }) {
  const [spec, setSpec] = React.useState<PolicySpec>(initial?.spec || defaultPolicy());
  const [valid, setValid] = React.useState<{ errors: string[]; warnings: string[] }>({ errors: [], warnings: [] });
  const [saving, setSaving] = React.useState(false);
  const [types, setTypes] = React.useState<IntegrationType[]>([]);
  const [instances, setInstances] = React.useState<IntegrationInstance[]>([]);

  React.useEffect(() => {
    (async () => {
      try {
        const [t, inst] = await Promise.all([
          apiService.getIntegrationTypes(false),
          apiService.getIntegrationInstances(),
        ]);
        setTypes(t);
        setInstances(inst);
      } catch (e: any) {
        toast.error(e?.message || 'Failed to load integrations');
      }
    })();
  }, []);

  React.useEffect(() => {
    const id = setTimeout(async () => {
      try { const res = await apiService.validatePolicy(spec); setValid(res); }
      catch (e: any) { setValid({ errors: [e?.message || 'Validation error'], warnings: [] }); }
    }, 450);
    return () => clearTimeout(id);
  }, [spec]);

  const save = async () => {
    try {
      setSaving(true);
      if (initial?.id) {
        await apiService.updatePolicy(initial.id, spec);
      } else {
        await apiService.createPolicy(spec);
      }
      toast.success('Policy saved');
      onSaved?.();
    } catch (e: any) {
      toast.error(e?.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Basics */}
      <Card>
        <CardHeader>
          <CardTitle>Basics</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="md:col-span-2">
              <Label>Name</Label>
              <Input value={spec.name} onChange={(e) => setSpec({ ...spec, name: e.target.value })} />
            </div>
            <div className="flex items-end gap-2">
              <Switch checked={spec.enabled} onCheckedChange={(v) => setSpec({ ...spec, enabled: v })} />
              <span className="text-sm">Enabled</span>
            </div>
          </div>
          {valid.errors.length > 0 && (
            <div className="text-sm text-status-error">{valid.errors[0]}</div>
          )}
        </CardContent>
      </Card>

      {/* Trigger */}
      <TriggerEditor value={spec.trigger} onChange={(v) => setSpec({ ...spec, trigger: v })} />

      <Separator />

      {/* Actions */}
      <ActionList
        value={spec.actions}
        onChange={(actions) => setSpec({ ...spec, actions })}
        types={types}
        instances={instances}
      />

      <div className="flex gap-3 pt-2">
        <Button onClick={save} disabled={saving || valid.errors.length > 0}>Save</Button>
        <Button variant="outline" onClick={onCancel}>Cancel</Button>
      </div>
    </div>
  );
}
