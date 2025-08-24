import React from 'react';
import { Label } from '../ui/label';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { Textarea } from '../ui/textarea';
import type { TargetSelector } from './types';

export function TargetSelector({ value, onChange }: { value: TargetSelector; onChange: (sel: TargetSelector) => void }) {
  const [labelKey, setLabelKey] = React.useState('');
  const [labelVal, setLabelVal] = React.useState('');

  const labels = value.labels || {};
  const identifiers = React.useMemo(() => (value.names || value.external_ids || []), [value.names, value.external_ids]);

  const addLabel = () => {
    if (!labelKey) return;
    onChange({ ...value, labels: { ...(value.labels || {}), [labelKey]: labelVal } });
    setLabelKey('');
    setLabelVal('');
  };

  const removeLabel = (k: string) => {
    const clone = { ...(value.labels || {}) };
    delete clone[k];
    onChange({ ...value, labels: clone });
  };

  return (
    <div className="space-y-4">
      <div>
        <Label>Labels</Label>
        <div className="flex gap-2 mt-1">
          <Input placeholder="key" value={labelKey} onChange={(e) => setLabelKey(e.target.value)} className="w-40" />
          <Input placeholder="value" value={labelVal} onChange={(e) => setLabelVal(e.target.value)} className="w-60" />
          <Button variant="outline" onClick={addLabel}>Add</Button>
        </div>
        {Object.keys(labels).length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            {Object.entries(labels).map(([k, v]) => (
              <span key={k} className="px-2 py-1 border rounded">
                {k}:{String(v)}
                <button className="ml-2 text-muted-foreground" onClick={() => removeLabel(k)}>×</button>
              </span>
            ))}
          </div>
        )}
      </div>

      <div>
        <Label>Identifiers (names or IDs, comma-separated)</Label>
        <Input
          value={(identifiers || []).join(',')}
          onChange={(e) => {
            const arr = e.target.value.split(',').map((s) => s.trim()).filter(Boolean);
            onChange({ ...value, names: arr, external_ids: arr });
          }}
          placeholder="vm-01,104,vm-02"
        />
      </div>

      <div>
        <Label>Attributes (JSON, optional)</Label>
        <Textarea
          rows={4}
          value={JSON.stringify(value.attrs || {}, null, 2)}
          onChange={(e) => {
            try {
              const obj = JSON.parse(e.target.value || '{}');
              onChange({ ...value, attrs: obj });
            } catch {
              // ignore invalid JSON
            }
          }}
          className="font-mono"
        />
      </div>
    </div>
  );
}
