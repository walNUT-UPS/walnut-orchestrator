# walNUT Integration Validation & Requirements — Audit
- Repo commit/date: 1a3a090 (2025-08-26 17:05:43 +0000)
- Summary of installed integration types (filesystem):
  - com.aruba.aoss (0.1.0) — status: not queried (DB encrypted)
  - walnut.proxmox.ve (1.0.1) — status: not queried (DB encrypted)

## 1. Validation Pipeline (by phase)
- Upload/Install:
  - Extension: rejects non-.int uploads (walnut/api/integrations.py:190–193). Failure: 400 {"error": "File must have .int extension"}.
  - Size: limit 10MB (walnut/api/integrations.py:195–211). Failure: 413 {"error": "File too large (max 10MB)"}.
  - ZIP validity: `zipfile.is_zipfile` (walnut/api/integrations.py:215–218). Failure: 400 {"error": "Invalid ZIP file"}.
  - Zip-slip guard: denies paths escaping staging (.. or absolute) (walnut/api/integrations.py:221–227). Failure: 400 {"error": "Unsafe file path in archive"}.
  - Manifest presence: requires `plugin.yaml` (walnut/api/integrations.py:233–237). Failure: 400 {"error": "No plugin.yaml found in package"}.
  - Manifest load/type: YAML → dict (walnut/api/integrations.py:242–248). Failure: 400 {"error": "Invalid plugin.yaml content"}.
  - Manifest id: requires `id` (walnut/api/integrations.py:250–253). Failure: 400 {"error": "Missing 'id' field in plugin.yaml"}.
  - Duplicate type: conflicts by id (walnut/api/integrations.py:257–268). Failure: 409 with guidance to remove existing.
  - Install: moves extracted folder to `./integrations/{id}` (walnut/api/integrations.py:270–276). Prior folder removed if exists.
  - Registry seed: creates/updates DB type record status=checking (walnut/core/integration_registry.py:61–106 `ensure_type_record`). WS: `integration_type.updated` with status=checking (walnut/core/integration_registry.py:96–106).
  - Validation (single type): invokes `validate_single_type` (walnut/api/integrations.py:281–295; walnut/core/integration_registry.py:566–640).
  - Streaming upload job (async variant): emits WS `integration_job.event` messages with phases upload/unpack/manifest/install/registry/final and a final `integration_job.done` (walnut/api/integrations.py:336–418, 420–493).

- Rescan:
  - Discovery: iterates `./integrations/*/plugin.yaml`, seeds/updates types to status=checking, stores absolute `path` (walnut/core/integration_registry.py:164–223). WS: `integration_type.updated` status=checking (walnut/core/integration_registry.py:246–258).
  - Missing folders: marks previously known types as status=unavailable if not rediscovered (walnut/core/integration_registry.py:210–217).
  - Validation: runs per type concurrently (walnut/core/integration_registry.py:206–247, 262–355). Summary counts returned by `discover_and_validate_all`.

- Load/Run (validation internals):
  - Manifest schema: JSON Schema validation (walnut/core/integration_registry.py:285–291) using schema at walnut/core/plugin_schema.py.
  - Driver presence: requires `driver.py` (walnut/core/integration_registry.py:292–297).
  - Entrypoint import: loads `module:Class` from integration folder with isolated module name (walnut/core/integration_registry.py:357–420). Failures recorded under `import_error`.
  - Capability conformance (Option A): every capability `id` must have driver method `id.replace('.', '_')` (walnut/core/plugin_schema.py:324–352). Failures recorded under `capability_mismatch` (walnut/core/integration_registry.py:306–313).
  - test_connection: driver must implement `test_connection()` method (walnut/core/integration_registry.py:315–319).
  - Core version gate: compares manifest `min_core_version` vs `walnut.__version__` (walnut/core/integration_registry.py:328–343). On mismatch: `core_version_incompatible` error, status=invalid.
  - Registry write: persists status/errors/capabilities/schema/defaults/test/driver_entrypoint; sets `last_validated_at`; WS `integration_type.updated` with status/errors (walnut/core/integration_registry.py:422–477).

- Instances:
  - Creation: requires type exists and status in [valid, checking]; unique instance `name` enforced (walnut/api/integrations.py:720–745, 748–756). State initialized to `configured`, and `last_test` set to now (walnut/api/integrations.py:741–744, 757–770).
  - Secrets storage: writes each secret as `IntegrationSecret` with raw bytes (placeholder “encryption”) (walnut/api/integrations.py:731–740).
  - Update: optional rename and `config` update. Config validation: prunes secret fields from JSON Schema then validates with `jsonschema` if available; otherwise basic dict type check (walnut/api/integrations.py:820–864). On config change: instance.state → `needs_review` (walnut/api/integrations.py:868–873).
  - Test connection: dynamically imports driver; builds secrets map; instantiates transports manager; calls `driver.test_connection()`. Persists `last_test`, `latency_ms`, and sets instance.state by result status: connected|degraded|error (walnut/api/integrations.py:1368–1519). On exception, sets state=error and last_test.
  - Type removed: endpoints block inventory/summary when instance.state == `type_unavailable` (walnut/api/integrations.py:963–966, 1016–1018). Note: removal path marks type status=unavailable but does not set per-instance state or flags (see Gaps).

- Inventory & caching:
  - Endpoints: list items with pagination (walnut/api/integrations.py:934–992) and summary counts (walnut/api/integrations.py:995–1034).
  - Cache schema: `InventoryCache(instance_id, target_type, active_only)` with TTL seconds, payload, fetched_at, counters (walnut/database/models.py:912–960).
  - Cache policy: default TTL 180s; returns fresh if age < ttl; otherwise returns stale if `cached_only=True` or until refresh finishes; for active_only=True can fallback to inactive cache with API-side filter (walnut/api/integrations.py:1168–1239, 1245–1345).
  - Active port filter: a port is “active” if link=="up" OR poe_power_w>0 OR poe_status=="delivering" (walnut/api/integrations.py:1213–1221).
  - Driver call: imports driver and calls `inventory_list(target_type=<normalized>, active_only=bool, options={})`, then upserts cache (walnut/api/integrations.py:1240–1345).

## 2. Manifest Schema (current truth)
- Source: walnut/core/plugin_schema.py (Draft 2020-12). Enforced at validation.
- Required top-level: `id`, `name`, `version`, `min_core_version`, `category`, `schema`, `capabilities`, `driver` (walnut/core/plugin_schema.py:12–20, 62–69, 142–169).
- driver.entrypoint: `^[A-Za-z_][A-Za-z0-9_]*:[A-Za-z_][A-Za-z0-9_]*$` (walnut/core/plugin_schema.py:142–153).
- schema.connection: arbitrary JSON Schema; UI forms built from `properties`, `required`. Secret fields indicated by `secret: true` metadata (carried through to DB field `schema_connection`) (walnut/core/plugin_schema.py:85–112; walnut/core/integration_registry.py:460–463).
- capabilities items:
  - Fields: `id` (dots allowed), `verbs` (strings), `targets` (strings), `dry_run` enum in {required, optional, not_supported}, optional `invertible`, `idempotency` (walnut/core/plugin_schema.py:169–288).
- defaults: free-form; notable `dry_run_refresh_sla_s` int 1–60 (walnut/core/plugin_schema.py:213–247).
- test: `method` enum {http, tcp, driver}; if http, requires request.method/path and success_when expression (walnut/core/plugin_schema.py:248–287).

Minimal example (excerpt):
```
id: example.id
driver: { entrypoint: driver:ExampleDriver }
schema: { connection: { type: object, required: [...], properties: { ... } } }
capabilities: [ { id: inventory.list, verbs: [list], targets: [vm], dry_run: optional } ]
```

Secret fields: any property with `secret: true`. API treats them as secrets at creation (stored in `integration_secrets`); updates exclude them from `config` validation.

Known optional sections: `defaults`, `test` (method http|tcp|driver). No `requires` section is defined/enforced in current JSON Schema.

## 3. Driver Contract (Option A — current enforcement)
- Capability→method mapping:
  - Rule: for each manifest capability `id`, driver must expose a method named `id.replace('.', '_')` (walnut/core/plugin_schema.py:324–352; checked during validation at walnut/core/integration_registry.py:306–313).
  - Signatures: not validated at install time. Runtime enforcement depends on API call sites.
- Required base methods:
  - `test_connection(self) -> dict` required (walnut/core/integration_registry.py:315–319). API maps `status` and `latency_ms` to instance state and metrics (walnut/api/integrations.py:1438–1472).
- Inventory contract:
  - Method: `inventory_list(self, target_type: str, active_only: bool = True, options: dict = None) -> list` (called by API; walnut/api/integrations.py:1276–1299).
  - Target normalization: API maps `stack-member`→`stack_member`, `poe-port`→`port` before driver call (walnut/api/integrations.py:1106–1116).
  - Active-only: API may filter ports for active-only from cached inactive data when needed (walnut/api/integrations.py:1207–1239).
  - Target shapes observed:
    - vm: { type: "vm", external_id: str, name: str, attrs: { status|node|... }, labels: {} }
    - stack-member: { type: "stack_member", external_id: str, name: str, attrs: { model|status|role... }, labels: {} }
    - port: { type: "port", external_id: str, name: str, attrs: { link, media, speed_mbps?, poe_class?, poe_power_w?, poe_status? }, labels: {} }
- Action endpoints (runtime dispatch examples):
  - VM Lifecycle: endpoint checks capability presence in type manifest then calls `driver.vm_lifecycle(verb, target, dry_run)` (walnut/api/integrations.py:1045–1051, 1039–1048). Unsupported capability → 400.
  - Aruba PoE and net ops: driver exposes `poe_port`, `poe_priority`, `net_interface`, `switch_*` methods; manifest capabilities map to these names (integrations/com.aruba.aoss/plugin.yaml and driver).

## 4. Instance Lifecycle
- Creation validation:
  - Type exists and status ∈ {valid, checking}; unique name (walnut/api/integrations.py:720–756).
  - Config/secrets accepted; secrets stored in `integration_secrets` (unencrypted placeholder) (walnut/api/integrations.py:731–740).
  - State transitions: on creation `state = configured`, `last_test = now` (walnut/api/integrations.py:741–744).
- Update:
  - Config validation vs non-secret subset of schema via `jsonschema` (if present). Failures return 400 with per-path messages (walnut/api/integrations.py:820–864).
  - Sets `state = needs_review` on config change (walnut/api/integrations.py:868–873).
- Test Connection:
  - Loads driver, builds secrets map, calls `test_connection()`. Updates: `last_test` timestamp, `latency_ms`, and `state` mapping: connected|degraded|error (walnut/api/integrations.py:1438–1472). On error: sets `state=error` and returns details.
- type_unavailable:
  - Removal marks type as `unavailable` only (walnut/core/integration_registry.py:526–555). API checks instance.state == `type_unavailable` to block inventory operations (walnut/api/integrations.py:963–966, 1016–1018) but there is no automatic propagation changing instance state/flags on type removal.

Source of truth for Last Test/latency: IntegrationInstance.last_test and latency_ms (DB), updated on test; creation sets a timestamp even before first real test (placeholder-y but real timestamp) (walnut/api/integrations.py:741–744, 1438–1472).

## 5. Inventory & Caching
- Endpoints:
  - `GET /integrations/instances/{id}/inventory` with params `type`, `active_only`, `refresh`, `cached_only`, `page`, `page_size` (walnut/api/integrations.py:934–992). Returns `{ items: [...] }` or paginated `{ items, next_page }`.
  - `GET /integrations/instances/{id}/inventory/summary` returns counts for vm, stack_member, port_active (walnut/api/integrations.py:995–1034).
- Cache/TTL:
  - Cache fetch with TTL check and fallbacks (walnut/api/integrations.py:1168–1244). New cache entries set `ttl_seconds=180` (walnut/api/integrations.py:1279–1291, 1308–1315).
  - Background refresh helper when serving stale or inactive fallback (walnut/api/integrations.py:1224–1231, 1346–1360).
- Active-only filter semantics:
  - For ports, API applies `link == "up" or poe_power_w > 0 or poe_status == "delivering"` (walnut/api/integrations.py:1213–1221).

## 6. Error Taxonomy & Statuses
- Type statuses (DB model): `checking|valid|invalid|superseded|unavailable` (walnut/database/models.py:175–199). Set at:
  - `checking`: discovery/ensure_type_record (walnut/core/integration_registry.py:61–106, 184–217).
  - `valid|invalid`: validation result (walnut/core/integration_registry.py:352–355, 422–477).
  - `unavailable`: missing folder on rescan or on remove (walnut/core/integration_registry.py:210–217, 526–555).
- Instance statuses (DB model): `connected|degraded|error|unknown|needs_review|type_unavailable` (walnut/database/models.py:231–246).
  - `configured` also used at creation (not in the enum comment but set in code) (walnut/api/integrations.py:741–744).
  - Mapped from `test_connection`: connected|degraded|error (walnut/api/integrations.py:1438–1472).
- Validation error keys during type validation: `schema_error`, `driver_missing`, `capability_mismatch`, `missing_test_connection`, `import_error`, `core_version_incompatible`, `validation_error` (walnut/core/integration_registry.py:285–349).
- Upload errors (sync endpoint): 400/409/413/500 with `logs` and message (walnut/api/integrations.py:190–296, 298–323).
- Upload job WS stream payloads:
  - `integration_job.event`: { job_id, ts, phase, level, message, meta } (walnut/api/integrations.py:360–378).
  - `integration_job.done`: success flag plus `type_id`, `installed_path`, `result` or `error` (walnut/api/integrations.py:420–493).
  - Also broadcasts `integration_upload.log` for non-job-scoped logs (walnut/api/integrations.py:338–356).

## 7. Gaps vs Target Model (Actionable)
- Method signature enforcement:
  - Gap: validation only checks presence of method names, not signatures. Runtime calls assume specific signatures: e.g., `vm_lifecycle(verb, target, dry_run)` and `inventory_list(target_type, active_only, options)` (walnut/api/integrations.py:1039–1051, 1276–1299). Recommendation: add signature introspection in validation (inspect.signature) and surface errors (walnut/core/integration_registry.py:300–319).
- Capability→method vs verbs/targets:
  - Gap: no enforcement that declared verbs/targets are actually handled by driver methods; only name presence. Recommendation: extend validation to optionally probe method parameters (verb, target, params, dry_run) and check for supported verbs per capability (walnut/core/plugin_schema.py, walnut/core/integration_registry.py).
- Manifest `requires` block:
  - Gap: No schema for runtime/platform/python/deps/permissions gates. Recommendation: add optional `requires` section in JSON Schema and enforce in validation with clear error keys.
- Core/python/platform gates:
  - Only core version is checked; Python version or OS constraints are not. Recommendation: add checks once `requires` is formalized (walnut/core/integration_registry.py:328–343).
- Atomic install semantics:
  - Install uses `shutil.move` after extraction; no rollback if validation later fails. Recommendation: keep temp until validation completes, then swap or mark status accordingly. Consider cleaning moved folder on fatal `import_error` (walnut/api/integrations.py:270–283).
- Type removal → instance state propagation:
  - Docstring states instances are marked `type_unavailable` (walnut/api/integrations.py:558 comment), but code only marks type `unavailable` and deletes folder (walnut/core/integration_registry.py:526–555). Recommendation: add a DB update to set instance.state='type_unavailable' for affected instances.
- Hardcoded UI placeholders:
  - Backend sets `last_test` at creation to now without an actual test (walnut/api/integrations.py:741–744). Frontend placeholders exist for “Last Test” rendering, but backend uses real timestamps on test. Consider leaving `last_test=None` until first test.
- Inventory TTL constant:
  - TTL fixed at 180s in API (walnut/api/integrations.py:1279–1291). Consider reading from type `defaults` (e.g., `heartbeat_interval_s` or dedicated cache TTL) and/or per-target overrides.

## 8. Appendix
- Integration inventory (filesystem):
  - integrations/com.aruba.aoss/
    - plugin.yaml, driver.py, requirements.txt, README.md, __init__.py, submodules (utils/, parsers/)
  - integrations/walnut.proxmox.ve/
    - plugin.yaml, driver.py, README.md

- Parsed manifest summaries

  - com.aruba.aoss
    - id: com.aruba.aoss
    - name: ArubaOS-S Switches
    - version: 0.1.0
    - min_core_version: 0.10.0
    - category: network-device
    - driver.entrypoint: driver:ArubaOSSwitchDriver
    - schema.connection.required: [hostname, username, password, snmp_community]
    - schema.connection.secrets: password, enable_password, snmp_community
    - defaults: transports.ssh(timeout_s:30,port:22), transports.snmp(timeout_s:5), heartbeat_interval_s:60, dry_run_refresh_sla_s:8
    - test: method=driver
    - capabilities:
      - switch.inventory: verbs=[read], targets=[switch], dry_run=not_supported
      - switch.health: verbs=[read], targets=[switch], dry_run=not_supported
      - poe.status: verbs=[read], targets=[switch], dry_run=not_supported
      - poe.port: verbs=[set], targets=[poe_port], dry_run=required
      - poe.priority: verbs=[set], targets=[poe_port], dry_run=required
      - net.interface: verbs=[set], targets=[interface], dry_run=required
      - switch.config: verbs=[save, backup], targets=[switch], dry_run=optional
      - switch.reboot: verbs=[exec], targets=[switch], dry_run=required
      - inventory.list: verbs=[list], targets=[stack_member, port], dry_run=optional

  - walnut.proxmox.ve
    - id: walnut.proxmox.ve
    - name: Proxmox VE
    - version: 1.0.1
    - min_core_version: 0.10.0
    - category: host-orchestrator
    - driver.entrypoint: driver:ProxmoxVeDriver
    - schema.connection.required: [host, port, node, api_token]
    - schema.connection.secrets: api_token
    - defaults.http: { timeout_s:5, retries:2, backoff_ms_start:250, verify_tls:true }
    - defaults: heartbeat_interval_s:120, dry_run_refresh_sla_s:5
    - test: method=http (GET /version; success_when: status == 200)
    - capabilities:
      - vm.lifecycle: verbs=[shutdown, start, stop, suspend, resume, reset], targets=[vm], dry_run=required
      - power.control: verbs=[shutdown, cycle], targets=[host], dry_run=required
      - inventory.list: verbs=[list], targets=[vm, host], dry_run=optional

- Capability matrices

  - com.aruba.aoss

    | capability       | verbs             | targets             | dry_run       |
    |------------------|-------------------|---------------------|---------------|
    | switch.inventory | read              | switch              | not_supported |
    | switch.health    | read              | switch              | not_supported |
    | poe.status       | read              | switch              | not_supported |
    | poe.port         | set               | poe_port            | required      |
    | poe.priority     | set               | poe_port            | required      |
    | net.interface    | set               | interface           | required      |
    | switch.config    | save, backup      | switch              | optional      |
    | switch.reboot    | exec              | switch              | required      |
    | inventory.list   | list              | stack_member, port  | optional      |

  - walnut.proxmox.ve

    | capability     | verbs                                  | targets | dry_run  |
    |----------------|----------------------------------------|---------|----------|
    | vm.lifecycle   | shutdown, start, stop, suspend, resume, reset | vm      | required |
    | power.control  | shutdown, cycle                         | host    | required |
    | inventory.list | list                                    | vm, host| optional |

- Endpoint catalog (integration framework):
  - Types: GET `/integrations/types`; POST `/integrations/types/upload`; POST `/integrations/types/upload/` (alias); POST `/integrations/types/upload/stream`; GET `/integrations/types/{id}/manifest`; POST `/integrations/types/{id}/validate`; DELETE `/integrations/types/{id}`.
  - Instances: GET `/integrations/instances`; POST `/integrations/instances`; PATCH `/integrations/instances/{id}`; DELETE `/integrations/instances/{id}`; POST `/integrations/instances/{id}/test`.
  - Inventory: GET `/integrations/instances/{id}/inventory`; GET `/integrations/instances/{id}/inventory/summary`.
  - Actions: POST `/integrations/instances/{id}/vm/{vm_id}/lifecycle` (vm.lifecycle).
  - Upload WS stream: messages `integration_job.event` and `integration_job.done` via WebSocketManager job subscriptions.

- Hardcoded UI artifacts
  - Backend: none observed for “Last Test”; uses DB timestamps. At instance creation, `last_test` is set to now even before a real test (walnut/api/integrations.py:741–744). Frontend contains placeholder rendering, outside this scope.

## Notes on repository structure and discovery
- Repo root detected (contains `walnut/`, `frontend/`, `integrations/`).
- Integration folders under `integrations/*`:
  - `com.aruba.aoss`: plugin.yaml, driver.py, README.md, requirements.txt, utils/, parsers/.
  - `walnut.proxmox.ve`: plugin.yaml, driver.py, README.md.
