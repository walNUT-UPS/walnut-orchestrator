import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/card';
import { Label } from '../ui/label';
import { Input } from '../ui/input';
import type { Trigger } from './types';

export function TriggerEditor({ value, onChange }: { value: Trigger; onChange: (t: Trigger) => void }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Trigger</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <Label>Type</Label>
            <select className="w-full input mt-1" value={value.type} onChange={(e) => onChange({ ...value, type: e.target.value as Trigger['type'] })}>
              <option value="status_transition">Status Transition</option>
              <option value="duration">Duration</option>
              <option value="schedule">Schedule</option>
            </select>
          </div>
          <div>
            <Label>From</Label>
            <Input value={value.from || ''} onChange={(e) => onChange({ ...value, from: e.target.value })} />
          </div>
          <div>
            <Label>To</Label>
            <Input value={value.to || ''} onChange={(e) => onChange({ ...value, to: e.target.value })} />
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <Label>Stable For (e.g., 60s)</Label>
            <Input value={value.stable_for || ''} onChange={(e) => onChange({ ...value, stable_for: e.target.value })} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

