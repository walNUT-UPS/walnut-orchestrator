import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/card';
import { Label } from '../ui/label';
import { Input } from '../ui/input';
import type { Trigger } from './types';

const UPS_STATES: Array<{ value: string; label: string }> = [
  { value: 'on_mains', label: 'On Mains' },
  { value: 'on_battery', label: 'On Battery' },
  { value: 'charging', label: 'Charging' },
  { value: 'discharging', label: 'Discharging' },
  { value: 'low_battery', label: 'Low Battery' },
  { value: 'shutdown_imm', label: 'Shutdown Immediately' },
];

export function TriggerEditor({ value, onChange }: { value: Trigger; onChange: (t: Trigger) => void }) {
  const [source, setSource] = React.useState<'UPS' | 'Metric' | 'Timer'>(value.type === 'schedule' ? 'Timer' : value.type === 'status_transition' ? 'UPS' : 'Metric');

  const setType = (t: Trigger['type']) => {
    if (t === 'status_transition') {
      onChange({ type: 'status_transition', from: value.from || 'on_mains', to: value.to || 'on_battery', stable_for: value.stable_for || '60s' });
    } else if (t === 'duration') {
      onChange({ type: 'duration', stable_for: value.stable_for || '60s' });
    } else if (t === 'schedule') {
      // Keep existing fields; UI for schedule can be added as needed
      onChange({ type: 'schedule', from: undefined, to: undefined, stable_for: undefined });
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Trigger</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div>
            <Label>Source</Label>
            <select className="w-full input mt-1" value={source} onChange={(e) => {
              const s = e.target.value as 'UPS' | 'Metric' | 'Timer';
              setSource(s);
              if (s === 'UPS') setType('status_transition');
              else if (s === 'Timer') setType('schedule');
              else setType('duration');
            }}>
              <option value="UPS">UPS</option>
              <option value="Metric">Metric</option>
              <option value="Timer">Timer</option>
            </select>
          </div>
          <div>
            <Label>Type</Label>
            <select className="w-full input mt-1" value={value.type} onChange={(e) => setType(e.target.value as Trigger['type'])}>
              {source === 'UPS' && <option value="status_transition">Status Transition</option>}
              {source === 'Metric' && <option value="duration">Metric Stable For</option>}
              {source === 'Timer' && <option value="schedule">Schedule</option>}
            </select>
          </div>
          {value.type === 'status_transition' && source === 'UPS' && (
            <>
              <div>
                <Label>From</Label>
                <select className="w-full input mt-1" value={value.from || ''} onChange={(e) => onChange({ ...value, from: e.target.value })}>
                  {UPS_STATES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
              </div>
              <div>
                <Label>To</Label>
                <select className="w-full input mt-1" value={value.to || ''} onChange={(e) => onChange({ ...value, to: e.target.value })}>
                  {UPS_STATES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
              </div>
            </>
          )}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <Label>Stable For (e.g., 60s)</Label>
            <Input value={value.stable_for || ''} onChange={(e) => onChange({ ...value, stable_for: e.target.value })} placeholder="60s" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
