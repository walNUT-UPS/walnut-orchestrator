Policy System Specification (walNUT)

0. Glossary
	•	Host: An instance created from an integration (e.g., a Proxmox node, an AOS-S switch). Hosts own child targets (VMs, ports, etc.).
	•	Integration/Driver: Code + metadata (plugin.yaml + driver.py) exposing capabilities, discovery, and dry-run/execute.
	•	Policy Spec: User-authored JSON, human-first; versioned.
	•	IR: Compiled intermediate representation used by the engine for deterministic execution.
	•	Event: Normalized stimulus emitted onto the internal bus.
	•	Dry-run/Preflight: Read-only driver calls validating permissions/state and previewing actions.

⸻

1. Event Model (normalized backend contract)

All trigger sources (UPS, metrics, timer, webhook) normalize to:

{
  "type": "ups|metric|timer|webhook",
  "kind": "ups.state|metric.threshold|timer.at|timer.after|webhook.custom",
  "subject": { "kind": "ups|host|vm|integration", "id": "uuid-or-provider-id" },
  "attrs": { "state":"on_battery", "metric":"load","op":">","value":60, "cron":"0 1 * * 0", "name":"deploy" },
  "ts": "2025-08-22T11:30:00Z",
  "correlation_id": "uuid"
}

	•	correlation_id groups related events (optional).
	•	Stability “for N” applies only to specific kinds (e.g., ups.state, metric.threshold) and is enforced by the event source before publishing.

⸻

2. Policy Spec (user JSON, v1)

Human-driven, compiled server-side. All fields required unless noted.

{
  "version": 1,
  "name": "String >= 3",
  "enabled": true,
  "priority": 0,
  "stop_on_match": false,
  "dynamic_resolution": true,

  "trigger_group": {
    "logic": "ALL",                  // "ALL" | "ANY"; default "ANY" if omitted
    "triggers": [
      { "type": "ups.state", "equals": "on_battery" },                // Bounded list per trigger kind
      { "type": "metric.threshold", "metric": "load", "op": ">", "value": 60, "for": "120s" },
      { "type": "timer.at", "schedule": { "repeat": "weekly", "at": "01:00", "days": ["sun"] } },
      { "type": "timer.after", "after": "10m", "since_event": { "type":"ups.state", "equals":"on_mains" } }
    ]
  },

  "conditions": {                    // flat AND list
    "all": [
      { "scope":"ups",   "field":"runtime_minutes", "op":">=", "value": 5 },
      { "scope":"host",  "field":"reachable", "op":"=", "value": true },
      { "scope":"metric","field":"charge_pct", "op":">", "value": 40 },
      { "scope":"vm",    "field":"count_matching", "op":">=", "value": 1 }
    ]
  },

  "targets": {                       // host-first selection
    "host_id": "uuid-of-host",
    "target_type": "vm|poe-port|interface|switch|..." ,
    "selector": {
      "mode": "list|range|query",
      "value": "104,204,311-318"     // examples; see grammar below
    }
  },

  "actions": [
    {
      "capability_id": "proxmox.vm",
      "verb": "shutdown",            // drivers declare invertible pairs
      "params": { "grace_s": 60, "confirm": true },
      "idempotency": { "key_hint": null }   // optional override; driver can compute
    },
    {
      "capability_id": "aoss.poe.port",
      "verb": "set",
      "params": { "state": "off", "confirm": true }
    }
  ],

  "suppression_window": "5m",        // engine-level suppression
  "idempotency_window": "10m",       // engine dedupe
  "notes": "free text"
}

Selector grammar
	•	VMs: 104,204,311-318
	•	Ports (AOS-S): 1/1-1/4,1/A1-1/B4
	•	Mixed allowed. Backend expands to canonical IDs at compile; if dynamic_resolution=true, the engine re-resolves at execute.

⸻

3. Compiled IR (engine contract)

Produced by POST /api/policies/validate or on Save. Stable, deterministic.

{
  "policy_id": "uuid",
  "hash": "sha256(normalized-spec)",
  "version_int": 1,
  "priority": 0,
  "stop_on_match": false,
  "dynamic_resolution": true,

  "match": {
    "trigger_group": { "logic":"ALL", "triggers":[ /* normalized triggers */ ] },
    "conditions": [ /* normalized AND clauses with bound scopes/fields */ ]
  },

  "targets": {
    "host_id": "uuid",
    "target_type": "vm",
    "selector": { "mode":"range", "value":"104-108" },
    "resolved_ids": ["vm:104","vm:105","vm:106","vm:107","vm:108"],   // may be empty at compile and re-resolved on execute if dynamic
    "resolved_at": "ts-or-null"
  },

  "plan": [                          // per action, per target computed at preflight
    { "capability":"proxmox.vm", "verb":"shutdown", "params":{"grace_s":60,"confirm":true} },
    { "capability":"aoss.poe.port", "verb":"set", "params":{"state":"off","confirm":true} }
  ],

  "windows": {
    "suppression_s": 300,
    "idempotency_s": 600
  }
}


⸻

4. Severity taxonomy (validation + dry-run)
	•	info: Valid; would be a no-op because targets already match desired state or were suppressed (e.g., VM already off).
	•	warn: Valid but with context caveats: stale inventory used, selector resolved to empty set, or partial refresh failure.
	•	error: Driver/preflight failures: permissions/auth denied, host unreachable, capability runtime error. Blocks Enable, not Save.
	•	blocker: Schema/compile failures: missing required fields, unknown capability/target type, bad selector grammar. Blocks Save.

⸻

5. Validation & Dry-run pipeline

Frontend (live)
	•	Schema validation: runs on each step; Save button stays disabled until schema passes (no blocker).
	•	Shows per-field errors (JSON pointer path).

Backend endpoints
	1.	POST /api/policies/validate
	•	Input: spec
	•	Steps: Schema → Compile (selector expand, capability existence, IR build)
	•	Output:

{ "ok": true|false,
  "schema": [{path,message}],
  "compile": [{path,message}],
  "ir": { ... },
  "hash": "..." }


	2.	POST /api/policies/:id/dry-run
	•	Refresh inventory for the selected host (fast path SLA = 5s default, per-driver override allowed via plugin.yaml).
	•	Per action/target call driver with dry_run=true.
	•	Output:

{
  "severity": "info|warn|error",
  "results": [
    {
      "target_id": "vm:104",
      "capability": "proxmox.vm",
      "verb": "shutdown",
      "driver": "com.proxmox.ve",
      "ok": true,
      "severity": "info",
      "idempotency_key": "proxmox.vm:shutdown:vm:104",
      "preconditions": [
        {"check":"vm_exists","ok":true},
        {"check":"vm_state","ok":true,"details":{"from":"running","to":"stopped"}}
      ],
      "plan": {"kind":"api","preview":[{"endpoint":"/nodes/x/qemu/104/status/shutdown","method":"POST"}]},
      "effects": {"summary":"VM would stop","per_target":[{"id":"vm:104","from":"running","to":"stopped"}]},
      "reason": null
    }
  ],
  "transcript_id": "uuid",
  "used_inventory": { "refreshed": true, "ts": "..." }
}



Persistence
	•	Store last_dry_run transcript summary + last_30_executions per policy for the Policies table: last_run_ts, last_status (info/warn/error).

⸻

6. Execution engine (runtime order of operations)
	1.	Receive event → shortlist candidate policies by trigger kind.
	2.	Sort by priority asc, tie-break by UUID asc.
	3.	For each policy:
	•	Idempotency: if identical action/target within idempotency_window → info: suppressed-idempotent.
	•	Suppression: if policy matched within suppression_window → info: suppressed-window.
	•	Dynamic resolution: if true, re-resolve selector to current target IDs; if empty → warn: empty-selection and continue.
	•	Engine preflight (cheap guards): skip targets already at desired state (info), ensure capability present (should always be), ensure host reachable (error).
	•	Driver execute (not dry run): call per action with resolved targets.
	•	Record run ledger entry.
	•	If stop_on_match=true, stop processing further policies for this event after any action is scheduled.

Concurrency: per-host execution queue (single flight) to avoid stepping on each other; per-policy runs can still parallelize across different hosts.

⸻

7. Driver contracts (execute + dry-run)

7.1 Driver execute(...) (current style retained)

def execute(capability_id: str, verb: str, target: dict, params: dict, connection: dict, dry_run: bool = False) -> dict

7.2 Dry-run response (standardized)

Drivers must not change state when dry_run=True and must return:

{
  "ok": bool,
  "severity": "info|warn|error",           # driver’s best view; engine can upgrade/downgrade
  "idempotency_key": "string",             # capability+verb+resolved-target+param-fingerprint
  "preconditions": [ { "check":"string", "ok":bool, "details": {...}? } ],
  "plan": { "kind":"cli|api|ssh", "preview": [ "configure", "..." ] or [{...}] },
  "effects": { "summary":"string", "per_target":[{"id":"...", "from": {...}, "to": {...}}] },
  "reason": "string|null"
}

7.3 Inverse registry (capability metadata)

Extend plugin.yaml capabilities with invertibility and idempotency hints:

capabilities:
  - id: proxmox.vm
    verbs: [start, shutdown, reset]
    invertible:
      start:   { inverse: shutdown }
      shutdown:{ inverse: start }
    idempotency:
      key_fields: [verb, target_id]   # optional hint if driver wants the engine to build keys
    dry_run: required

Driver-side can override idempotency_key in response if it needs more context.

7.4 Refresh SLA override (plugin.yaml)

defaults:
  dry_run_refresh_sla_s: 5   # engine default can be overridden per integration


⸻

8. Inventory & discovery
	•	Hosts own child targets produced by discovery: each child has stable canonical IDs, name/label, and searchable labels.
	•	Discovery runs periodically (backend task) and on-demand:
	•	Fast refresh: limited to critical queries for preflight (respect SLA).
	•	Full discovery: background to hydrate DB.

Search index for selector UI merges id, name, and driver-provided labels. Backend builds and serves this index; UI does not talk to drivers directly.

⸻

9. API Surface (minimal + sufficient)
	•	GET /api/hosts/:host_id/capabilities → from plugin schema/driver.
	•	GET /api/hosts/:host_id/inventory?refresh=true|false → returns children + ts + stale flag.
	•	POST /api/policies/validate → Schema + Compile + IR + hash.
	•	POST /api/policies → Save spec; on blocker → 400; on error → saved with status="disabled".
	•	PUT /api/policies/:id → Update spec (bumps version_int).
	•	POST /api/policies/:id/dry-run → transcript.
	•	GET /api/policies/:id/executions?limit=30 → run ledger.
	•	POST /api/policies/:id/inverse → returns unsaved inverse spec with needs_input: [paths].

Status codes
	•	400: schema/compile blocker
	•	409: duplicate hash (identical spec exists)
	•	422: driver reports structurally invalid action (capability mismatch)

⸻

10. Storage & versioning

Per policy row stores:

{
  "id":"uuid",
  "spec":{...},
  "version_int": 3,
  "hash":"sha256",
  "compiled_ir":{...},
  "status":"enabled|disabled|invalid",
  "last_validation":{ "ts":"...", "schema":[], "compile":[] },
  "last_dry_run":{ "ts":"...","severity":"info|warn|error" },
  "executions":[ /* last 30 summaries */ ]
}

Hash collision policy: identical hash on Save → 409 Conflict with pointer to existing policy.

⸻

11. UX (Wizard + Console)
	•	Step 1 Basics: name, enabled, priority, stop_on_match.
	•	Step 2 Trigger: single trigger by default; “Add trigger” reveals group with ALL/ANY toggle. Human phrases; JSON mirror shows cron/durations.
	•	Step 3 Conditions: flat list in human phrasing; scopes: ups, host, vm, metric.
	•	Step 4 Targets & Actions: pick Host → target type → searchable multi-select or range input; actions built from host capabilities; params editors from capability schema.
	•	Step 5 Review: Read-only Spec JSON with diff (if editing). Buttons:
	•	Validate (runs compile+preflight, shows Console)
	•	Save Disabled (if errors)
	•	Save & Enable (if no errors)
	•	Create Inverse (opens inverse spec with enabled=false, highlights needs_input)

Console layout (sections, not tabs):
	•	Schema (inline per-field)
	•	Compile (selector resolution table + IR hash)
	•	Preflight (per action/target table: severity, preconditions, plan preview, effects)

Policies table shows last_run_ts and last_status chip.

⸻

12. Ranges & resolvers (backend)
	•	Parser supports integers, hyphen ranges, CSV, and hierarchical slot/member/port patterns.
	•	Normalization returns canonical target IDs + friendly labels.
	•	If dynamic: store selector and re-resolve at execute; keep last resolution for diffing.

⸻

13. Safety & failure semantics
	•	Suppression: matching within window → info: suppressed-window (recorded).
	•	Idempotency: same action/target within window → info: suppressed-idempotent.
	•	Host unreachable: error, blocks enable; VM already off: info.
	•	Capability missing after compile (shouldn’t happen): engine upgrades to error and suggests re-validate.

⸻

14. Example snippets

14.1 Inverse creation response

{
  "spec_inverse": { "... flipped actions/triggers ..." },
  "enabled": false,
  "needs_input": ["trigger_group.triggers[0].schedule.at"],
  "notes": "Inverse of policy 2d4a..."
}

14.2 Proxmox VM shutdown dry-run (driver)

{
  "ok": true,
  "severity": "info",
  "idempotency_key": "proxmox.vm:shutdown:vm:104",
  "preconditions": [
    {"check":"auth_scope","ok":true},
    {"check":"vm_state","ok":true,"details":{"state":"running"}}
  ],
  "plan": {"kind":"api","preview":[{"method":"POST","endpoint":"/nodes/pve/qemu/104/status/shutdown"}]},
  "effects": {"summary":"VM would stop","per_target":[{"id":"vm:104","from":"running","to":"stopped"}]},
  "reason": null
}

14.3 AOS-S POE off dry-run (driver)

{
  "ok": true,
  "severity": "warn",
  "idempotency_key": "aoss.poe.port:set:1/1-1/4:off",
  "preconditions": [
    {"check":"poe_supported","ok":true},
    {"check":"protected_ports","ok":true}
  ],
  "plan": {"kind":"cli","preview":["configure","interface 1/1-1/4","no power-over-ethernet","exit","exit"]},
  "effects": {"summary":"Ports would power off","per_target":[{"id":"1/1","from":{"draw_w":7.5},"to":{"draw_w":0}}]},
  "reason":"inventory stale; fast refresh failed"
}


⸻

15. Non-functional constraints
	•	Timeouts: Dry-run refresh SLA 5s default; per-driver override via plugin.yaml.
	•	Isolation: Engine queues per host to avoid conflicting ops; global concurrency cap configurable.
	•	Audit: All validations, dry-runs, and executions emit an event to the audit log with correlation IDs.
	•	Security: Frontend must include CSRF header on /api/*; JWT auth as per your existing flow.

⸻

16. Minimal driver changes needed
	•	Implement standardized dry-run response (shape above).
	•	Populate invertible map and optional idempotency hint in plugin.yaml.
	•	Expose capabilities and target catalogs (names + IDs + labels) through discovery so backend can build the searchable index.
	•	Add optional defaults.dry_run_refresh_sla_s if slower than 5s.

⸻

17. Done means done checklist
	•	Backend: schema (Pydantic), compile pipeline, IR, hash, storage.
	•	Backend: endpoints (validate, save, dry-run, executions, inverse).
	•	Engine: event matcher, suppression+idempotency, per-host queue, execution.
	•	Inventory service: periodic + fast refresh; searchable index per host.
	•	Drivers: dry-run compliance; inverse metadata; SLA override (if needed).
	•	UI: wizard, live schema validation, selector/range editor, searchable targets, Review pane, Console, inverse button, Policies table chips.
	•	Tests: unit (parser, compile), integration (dry-run), e2e (create→validate→inverse→enable→simulate event).
