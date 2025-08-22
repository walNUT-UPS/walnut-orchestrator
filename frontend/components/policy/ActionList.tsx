import React from 'react';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Label } from '../ui/label';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../ui/select';
import { Textarea } from '../ui/textarea';
import type { CapabilityAction } from './types';
import type { IntegrationType, IntegrationInstance } from '../../services/api';
import { toast } from 'sonner';
import { apiService } from '../../services/api';
import { TargetSelector } from './TargetSelector';
import { GripVertical } from 'lucide-react';
// Drag-and-drop support can be enabled by installing react-dnd + backend and wiring here.
const DndProvider: any = null;
const useDrag: any = null;
const useDrop: any = null;
const HTML5Backend: any = null;

export function ActionList({ value, onChange, types, instances }: { value: CapabilityAction[]; onChange: (a: CapabilityAction[]) => void; types: IntegrationType[]; instances: IntegrationInstance[] }) {
  const add = () => onChange([...value, { capability: '', verb: '', selector: {}, options: {}, concurrency: 1, backoff_ms: 500, timeout_s: 30 }]);
  const remove = (idx: number) => onChange(value.filter((_, i) => i !== idx));
  const update = (idx: number, patch: Partial<CapabilityAction>) => onChange(value.map((a, i) => (i === idx ? { ...a, ...patch } : a)));
  const move = (from: number, to: number) => {
    if (from === to) return;
    const clone = value.slice();
    const [item] = clone.splice(from, 1);
    clone.splice(to, 0, item);
    onChange(clone);
  };

  const testOne = async (idx: number) => {
    try {
      const plan = await apiService.testPolicy({
        version: '2.0', name: 'tmp', enabled: true, priority: 128,
        trigger: { type: 'status_transition' }, conditions: { all: [], any: [] }, safeties: {}, actions: [value[idx]],
      } as any);
      toast.success(`Dry run planned ${plan.plan?.length || 0} steps`);
    } catch (e: any) {
      toast.error(e?.message || 'Dry run failed');
    }
  };

  const ListBody = (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Actions</CardTitle>
          <Button size="sm" onClick={add}>Add Action</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {value.length === 0 && <div className="text-sm text-muted-foreground">No actions defined yet.</div>}
        {value.map((a, idx) => {
          const selectedType = a.type_id ? types.find((t) => t.id === a.type_id) : undefined;
          const verbs = selectedType?.capabilities.find((c) => c.id === a.capability)?.verbs || [];
          // Draggable wrapper when DnD available
          const content = (
            <div className="border rounded-md p-3 space-y-3">
              <div className="flex items-center gap-2 text-muted-foreground">
                <GripVertical className="w-3.5 h-3.5" />
                <span className="text-xs">Step {idx + 1}</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <Label>Integration Type</Label>
                  <Select value={a.type_id || ''} onValueChange={(v) => update(idx, { type_id: v, capability: '', verb: '' })}>
                    <SelectTrigger className="mt-1"><SelectValue placeholder="Select type" /></SelectTrigger>
                    <SelectContent>
                      {types.filter(t => t.status === 'valid').map((t) => (
                        <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Capability</Label>
                  <Select value={a.capability || ''} onValueChange={(v) => update(idx, { capability: v, verb: '' })}>
                    <SelectTrigger className="mt-1"><SelectValue placeholder="Select capability" /></SelectTrigger>
                    <SelectContent>
                      {selectedType?.capabilities.map((c) => (
                        <SelectItem key={c.id} value={c.id}>{c.id}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Verb</Label>
                  <Select value={a.verb || ''} onValueChange={(v) => update(idx, { verb: v })}>
                    <SelectTrigger className="mt-1"><SelectValue placeholder="Select verb" /></SelectTrigger>
                    <SelectContent>
                      {verbs.map((v) => <SelectItem key={v} value={v}>{v}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* Instance and target type */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <Label>Instance</Label>
                  <Select value={String(a.instance_id || '')} onValueChange={(v) => update(idx, { instance_id: Number(v) })}>
                    <SelectTrigger className="mt-1"><SelectValue placeholder="Select instance" /></SelectTrigger>
                    <SelectContent>
                      {instances.filter(inst => !a.type_id || inst.type_id === a.type_id).map(inst => (
                        <SelectItem key={inst.instance_id} value={String(inst.instance_id)}>{inst.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="md:col-span-2">
                  <Label>Target Selector</Label>
                  <TargetSelector
                    instance={instances.find(i => i.instance_id === a.instance_id)}
                    targetType={selectedType?.capabilities.find(c => c.id === a.capability)?.targets?.[0]}
                    value={a.selector || {}}
                    onChange={(sel) => update(idx, { selector: sel })}
                  />
                </div>
              </div>

              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => testOne(idx)}>Dry Run</Button>
                <Button size="sm" variant="outline" onClick={() => remove(idx)}>Remove</Button>
              </div>
            </div>
          );

          if (DndProvider && useDrag && useDrop) {
            // DnD item wrapper
            const ActionRow = () => {
              const ref = React.useRef<HTMLDivElement>(null);
              const [{ isDragging }, drag] = useDrag({
                type: 'policy-action',
                item: { index: idx },
                collect: (monitor: any) => ({ isDragging: monitor.isDragging() }),
              });
              const [, drop] = useDrop({
                accept: 'policy-action',
                hover: (item: any) => {
                  const dragIndex = item.index;
                  const hoverIndex = idx;
                  if (dragIndex === hoverIndex) return;
                  move(dragIndex, hoverIndex);
                  item.index = hoverIndex;
                },
              });
              drag(drop(ref));
              return <div ref={ref} className={isDragging ? 'opacity-60' : ''}>{content}</div>;
            };
            return <ActionRow key={idx} />;
          }
          return <div key={idx}>{content}</div>;
        })}
      </CardContent>
    </Card>
  );

  return DndProvider ? (
    <DndProvider backend={HTML5Backend}>{ListBody}</DndProvider>
  ) : (
    ListBody
  );
}
