import React from 'react';
import { Label } from '../ui/label';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import type { TargetSelector as TSel } from './types';
import { apiService } from '../../services/api';

type Props = {
  hostId: string;
  targetTypes: string[];
  value: TSel;
  onChange: (sel: TSel) => void;
};

export function TargetSelector({ hostId, targetTypes, value, onChange }: Props) {
  const [type, setType] = React.useState<string>(() => targetTypes[0] || 'vm');
  const [items, setItems] = React.useState<Array<{ external_id: string; name?: string }>>([]);
  const [q, setQ] = React.useState('');
  const [loading, setLoading] = React.useState(false);

  const selected = React.useMemo(() => {
    const ids = new Set([...(value.external_ids || []), ...(value.names || [])]);
    return Array.from(ids);
  }, [value.external_ids, value.names]);

  const refresh = React.useCallback(async () => {
    try {
      setLoading(true);
      const res = await apiService.getInstanceInventory(Number(hostId), type);
      const arr = (res.items || []).map((i: any) => ({ external_id: String(i.external_id), name: i.name }));
      setItems(arr);
    } catch (_) {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [hostId, type]);

  React.useEffect(() => { refresh(); }, [refresh]);

  const filtered = React.useMemo(() => {
    const qq = q.trim().toLowerCase();
    if (!qq) return items;
    return items.filter(i => (i.name || '').toLowerCase().includes(qq) || i.external_id.toLowerCase().includes(qq));
  }, [items, q]);

  const add = (id: string, name?: string) => {
    const nextIds = Array.from(new Set([...(value.external_ids || []), id]));
    const nextNames = name ? Array.from(new Set([...(value.names || []), name])) : (value.names || []);
    onChange({ ...value, external_ids: nextIds, names: nextNames });
  };
  const remove = (idOrName: string) => {
    const nextIds = (value.external_ids || []).filter(x => x !== idOrName);
    const nextNames = (value.names || []).filter(x => x !== idOrName);
    onChange({ ...value, external_ids: nextIds, names: nextNames });
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Label className="shrink-0">Type</Label>
        <select value={type} onChange={(e) => setType(e.target.value)} className="p-2 border rounded text-sm w-40">
          {targetTypes.map(t => (<option key={t} value={t}>{t}</option>))}
        </select>
        <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>{loading ? '...' : 'Refresh'}</Button>
      </div>
      <div>
        <Input placeholder="Type to search by name or ID..." value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="mt-2 border rounded-md max-h-56 overflow-auto divide-y">
          {loading ? (
            <div className="p-2 text-sm text-muted-foreground">Loading…</div>
          ) : filtered.length === 0 ? (
            <div className="p-2 text-sm text-muted-foreground">No results</div>
          ) : (
            filtered.map((it) => (
              <button
                key={`${it.external_id}:${it.name || ''}`}
                type="button"
                onClick={() => add(it.external_id, it.name)}
                className="w-full text-left p-2 hover:bg-accent hover:text-accent-foreground flex items-center justify-between"
              >
                <span className="truncate max-w-[320px]">{it.name || it.external_id}</span>
                <span className="text-xs text-muted-foreground ml-2">ID: {it.external_id}</span>
              </button>
            ))
          )}
        </div>
        {selected.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            {selected.map((s) => (
              <span key={s} className="px-2 py-1 border rounded bg-muted/30">
                {s}
                <button className="ml-2 text-muted-foreground" onClick={() => remove(s)}>×</button>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
