export type TriggerType = 
  | { type: 'ups.state'; equals: string }
  | { type: 'metric.threshold'; metric: string; op: string; value: number; for?: string }
  | { type: 'timer.at'; schedule: { repeat: string; at: string; days?: string[] } }
  | { type: 'timer.after'; after: string; since_event: { type: string; equals: string } };

export type TriggerGroup = {
  logic: 'ALL' | 'ANY';
  triggers: TriggerType[];
};

export type Condition = {
  scope: 'ups' | 'host' | 'metric' | 'vm';
  field: string;
  op: string;
  value: any;
};

export type TargetSpec = {
  host_id: string;
  target_type: string;
  selector: {
    mode: 'list' | 'range' | 'query';
    value: string;
  };
};

export type PolicyAction = {
  capability_id: string;
  verb: string;
  params: Record<string, any>;
  idempotency?: { key_hint?: string | null };
};

export type PolicySpec = {
  version: 1;
  name: string;
  enabled: boolean;
  priority: number;
  stop_on_match: boolean;
  dynamic_resolution: boolean;
  trigger_group: TriggerGroup;
  conditions: {
    all: Condition[];
  };
  targets: TargetSpec;
  actions: PolicyAction[];
  suppression_window?: string;
  idempotency_window?: string;
  notes?: string;
};

export const defaultPolicy = (): PolicySpec => ({
  version: 1,
  name: '',
  enabled: false,
  priority: 0,
  stop_on_match: false,
  dynamic_resolution: true,
  trigger_group: {
    logic: 'ANY',
    triggers: [{ type: 'ups.state', equals: 'on_battery' }]
  },
  conditions: { all: [] },
  targets: {
    host_id: '',
    target_type: '',
    selector: { mode: 'list', value: '' }
  },
  actions: [],
  suppression_window: '5m',
  idempotency_window: '10m',
  notes: ''
});

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

