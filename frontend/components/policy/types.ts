// Policy Schema v2 types (aligned with backend pydantic models)

export type Trigger = {
  type: 'status_transition' | 'duration' | 'schedule';
  from?: string; // alias for from_status
  to?: string;   // alias for to_status
  stable_for?: string; // e.g., "60s"
};

export type Conditions = {
  all: Array<Record<string, any>>;
  any: Array<Record<string, any>>;
};

export type TargetSelector = {
  labels?: Record<string, any>;
  attrs?: Record<string, any>;
  names?: string[];
  external_ids?: string[];
};

export interface CapabilityAction {
  host_id?: string;
  capability: string;
  verb: string;
  selector: TargetSelector;
  options?: Record<string, any>;
}

export type Safeties = {
  suppression_window?: string | null;
  global_lock?: string | null;
  never_hosts?: string[];
};

export type PolicySpec = {
  version: '2.0';
  name: string;
  enabled: boolean;
  priority: number; // 0-255
  trigger: Trigger;
  conditions: Conditions;
  safeties: Safeties;
  actions: CapabilityAction[];
};

export const defaultPolicy = (): PolicySpec => ({
  version: '2.0',
  name: '',
  enabled: true,
  priority: 128,
  trigger: { type: 'status_transition', from: '', to: '' },
  conditions: { all: [], any: [] },
  safeties: { suppression_window: '10m', global_lock: null, never_hosts: [] },
  actions: [],
});

// Legacy host/inventory types (kept for compatibility if needed elsewhere)
export interface Host {
  id: string;
  name: string;
  ip_address: string;
  os_type: string;
  status: string;
}

export interface HostCapability {
  id: string;
  verbs: string[];
  targets?: string[];
  invertible?: Record<string, { inverse: string }>;
  idempotency?: { key_fields: string[] };
  dry_run: 'required' | 'optional';
  params_schema?: Record<string, any>;
}

export interface InventoryItem {
  id: string;
  name: string;
  type: string;
  labels: Record<string, any>;
}

export interface ValidationResult {
  ok: boolean;
  schema: { path: string; message: string }[];
  compile: { path: string; message: string }[];
  ir?: any;
  hash?: string;
}

export interface DryRunResult {
  severity: 'info' | 'warn' | 'error';
  results: {
    target_id: string;
    capability: string;
    verb: string;
    driver: string;
    ok: boolean;
    severity: 'info' | 'warn' | 'error';
    idempotency_key: string;
    preconditions: { check: string; ok: boolean; details?: any }[];
    plan: { kind: string; preview: any[] };
    effects: { summary: string; per_target: any[] };
    reason: string | null;
  }[];
  transcript_id: string;
  used_inventory: { refreshed: boolean; ts: string };
}
