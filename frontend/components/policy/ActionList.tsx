import React from 'react';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Input } from '../ui/input';
import type { CapabilityAction, HostCapability } from './types';
import type { Host } from './types';
import { toast } from 'sonner';
import { apiService } from '../../services/api';
import { TargetSelector } from './TargetSelector';
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip';
import { Info } from 'lucide-react';
import { GripVertical } from 'lucide-react';
// Drag-and-drop support can be enabled by installing react-dnd + backend and wiring here.
const DndProvider: any = null;
const useDrag: any = null;
const useDrop: any = null;
const HTML5Backend: any = null;

export function ActionList({ value, onChange }: { value: CapabilityAction[]; onChange: (a: CapabilityAction[]) => void }) {
  const [hosts, setHosts] = React.useState<Host[]>([]);
  const [capsByHost, setCapsByHost] = React.useState<Record<string, HostCapability[]>>({});
  const [loadingHosts, setLoadingHosts] = React.useState(false);

  React.useEffect(() => {
    (async () => {
      try {
        setLoadingHosts(true);
        const hs = await apiService.getHosts();
        setHosts(hs as any);
      } catch (e) {
        // ignore
      } finally {
        setLoadingHosts(false);
      }
    })();
  }, []);

  // Preload capabilities for hosts referenced by existing actions (edit flow)
  React.useEffect(() => {
    const wanted = Array.from(new Set((value || []).map((a) => (a as any).host_id).filter(Boolean)));
    wanted.forEach((hid) => {
      if (!capsByHost[hid]) {
        void loadCaps(hid);
      }
    });
  }, [value]);

  const loadCaps = async (hostId: string) => {
    try {
      if (capsByHost[hostId]) return;
      const caps = await apiService.getHostCapabilities(hostId);
      setCapsByHost((m) => ({ ...m, [hostId]: caps as any }));
    } catch (e) {
      // ignore
    }
  };
  const add = () => onChange([...value, { host_id: '', capability: '', verb: '', selector: {}, options: {} } as any]);
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
          // Draggable wrapper when DnD available
          const content = (
            <div className="border rounded-md p-3 space-y-3">
              <div className="flex items-center gap-2 text-muted-foreground">
                <GripVertical className="w-3.5 h-3.5" />
                <span className="text-xs">Step {idx + 1}</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <Label>Host</Label>
                  <select
                    value={(a as any).host_id || ''}
                    onChange={async (e) => { const host_id = e.target.value; update(idx, { ...(a as any), selector: a.selector || {}, } as any); update(idx, { ...(a as any), host_id } as any); await loadCaps(host_id); }}
                    className="w-full p-2 border rounded text-sm"
                  >
                    <option value="">Select host</option>
                    {hosts.map((h) => (
                      <option key={h.id} value={h.id}>{h.name || h.id}</option>
                    ))}
                  </select>
                </div>
                {(a as any).host_id && (
                  <>
                    <div>
                      <div className="flex items-center gap-1">
                        <Label>Capability</Label>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="text-muted-foreground inline-flex items-center"><Info className="w-3.5 h-3.5" /></span>
                          </TooltipTrigger>
                          <TooltipContent>Choose what action family to run (e.g., VM Lifecycle, Host Power Control)</TooltipContent>
                        </Tooltip>
                      </div>
                      <select
                        value={a.capability || ''}
                        onChange={(e) => update(idx, { capability: e.target.value, verb: '' })}
                        className="w-full p-2 border rounded text-sm"
                      >
                        <option value="">Select capability</option>
                        {(capsByHost[(a as any).host_id || ''] || []).filter(c => c.id !== 'inventory.list').map((c) => (
                          <option key={c.id} value={c.id}>{friendlyCapLabel(c.id)}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <div className="flex items-center gap-1">
                        <Label>Verb</Label>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="text-muted-foreground inline-flex items-center"><Info className="w-3.5 h-3.5" /></span>
                          </TooltipTrigger>
                          <TooltipContent>Specific action to perform (e.g., start, shutdown, cycle)</TooltipContent>
                        </Tooltip>
                      </div>
                      <select
                        value={a.verb || ''}
                        onChange={(e) => update(idx, { verb: e.target.value })}
                        className="w-full p-2 border rounded text-sm"
                        disabled={!a.capability}
                      >
                        <option value="">Select verb</option>
                        {(capsByHost[(a as any).host_id || ''] || []).find(c => c.id === a.capability)?.verbs?.map((v) => (
                          <option key={v} value={v}>{v}</option>
                        ))}
                      </select>
                    </div>
                  </>
                )}
              </div>

                {(a as any).host_id && a.capability && (
                <div>
                  <div className="flex items-center gap-1">
                    <Label>Target Selector</Label>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="text-muted-foreground inline-flex items-center"><Info className="w-3.5 h-3.5" /></span>
                      </TooltipTrigger>
                      <TooltipContent>
                        Filter by type, then type to search by name or ID. Select one or more targets.
                      </TooltipContent>
                    </Tooltip>
                  </div>
                  {(() => {
                    const cap = (capsByHost[(a as any).host_id || ''] || []).find(c => c.id === a.capability);
                    const targets = cap?.targets || [];
                    const hostOnly = targets.length === 1 && targets[0] === 'host';
                    if (hostOnly) {
                      return <div className="text-xs text-muted-foreground">Operates on host. No target selection required.</div>;
                    }
                    return <TargetSelector hostId={(a as any).host_id!} targetTypes={targets} value={a.selector || {}} onChange={(sel) => update(idx, { selector: sel })} />;
                  })()}
                </div>
              )}

              <div className="flex gap-2">
                <Button size="sm" variant="secondary" onClick={() => move(idx, Math.max(0, idx - 1))} disabled={idx === 0}>Up</Button>
                <Button size="sm" variant="secondary" onClick={() => move(idx, Math.min(value.length - 1, idx + 1))} disabled={idx === value.length - 1}>Down</Button>
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

function friendlyCapLabel(id: string): string {
  switch (id) {
    case 'vm.lifecycle': return 'VM Lifecycle';
    case 'power.control': return 'Host Power Control';
    default:
      return id.split('.').map(s => s.charAt(0).toUpperCase() + s.slice(1)).join(' ');
  }
}
