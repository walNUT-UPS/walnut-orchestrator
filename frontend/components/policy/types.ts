export type Trigger = {
  type: 'status_transition' | 'duration' | 'schedule';
  from?: string | null;
  to?: string | null;
  stable_for?: string | null;
};

export type TargetSelector = {
  labels?: Record<string, any>;
  attrs?: Record<string, any>;
  names?: string[];
  external_ids?: string[];
};

export type CapabilityAction = {
  capability: string;
  verb: string;
  selector: TargetSelector;
  options?: Record<string, any>;
  instance_id?: number; // UI helper (not in schema)
  type_id?: string; // UI helper
  concurrency?: number;
  backoff_ms?: number;
  timeout_s?: number;
};

export type PolicySpec = {
  version: string;
  name: string;
  enabled: boolean;
  priority: number;
  trigger: Trigger;
  conditions: { all: Array<Record<string, any>>; any: Array<Record<string, any>> };
  safeties: { suppression_window?: string | null; global_lock?: string | null; never_hosts?: string[] };
  actions: CapabilityAction[];
};

export const defaultPolicy = (): PolicySpec => ({
  version: '2.0',
  name: '',
  enabled: true,
  priority: 128,
  trigger: { type: 'status_transition', from: null, to: null, stable_for: null },
  conditions: { all: [], any: [] },
  safeties: { suppression_window: null, global_lock: null, never_hosts: [] },
  actions: [],
});

