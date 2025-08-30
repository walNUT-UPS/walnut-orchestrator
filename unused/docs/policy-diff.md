# Policy System Improvement Plan (Based on POLICY.md)

Note on source: The repository does not contain docs/policy.md. This plan is derived from the root-level POLICY.md, which appears to be the canonical specification referenced by the backend, tests, and drivers.

Date: 2025-08-24 21:54


## Executive Summary

The current Policy System specification (POLICY.md) defines a robust v1 architecture: normalized event model, user JSON Policy Spec, compiled IR, validation and dry-run pipelines, a deterministic execution engine with suppression and idempotency, standardized driver contracts, inventory discovery, minimal API surface, versioned storage, and a UX wizard/console.

This plan translates those goals and constraints into actionable improvements across backend, drivers, inventory, UX, security, observability, testing, and governance. It emphasizes determinism, safety, operator clarity, and developer ergonomics. Each section lists rationale, concrete actions, and measurable outcomes.


## Key Goals Extracted

- Deterministic, stable compilation to an IR with explicit hash/versioning.
- Safety-first operations via suppression windows, idempotency windows, preflight guards, and driver dry-runs.
- Consistent severity taxonomy: info/warn/error/blocker to gate Save/Enable flows.
- Standardized driver dry-run shape with preconditions, plan preview, effects, and idempotency keys.
- Host-first target selection with range/query grammar; optional dynamic resolution at execute time.
- Bounded, minimal API that exposes validate, dry-run, executions, discovery, and inverse creation.
- Inventory that supports fast refresh for preflight and full discovery for hydration; searchable index.
- Per-host execution queues and global concurrency caps for isolation.
- Strong UX with live validation, review/diff, and a unified console for schema/compile/preflight.
- Non-functional constraints: timeouts, audit events, security headers/JWT, and driver SLA overrides.


## Key Constraints Extracted

- Save must be blocked on “blocker” (schema/compile) issues; Enable is blocked on “error” (driver/preflight) issues.
- Dry-run refresh SLA default is 5s, overrideable per driver (plugin.yaml).
- Idempotency and suppression windows must be enforced before driver execution.
- IR must be stable/deterministic and include normalized triggers, conditions, selector expansion metadata, and windows.
- Storage must include spec, compiled IR, hash, status, last_validation, last_dry_run, and a capped executions ledger.
- API error codes: 400 (schema/compile blocker), 409 (duplicate hash), 422 (driver structural mismatch).
- Audit events required for validation, dry-run, and execution; correlation IDs are propagated.
- Security: CSRF header on /api/* and JWT auth per existing flow.


## Theme 1 — Backend Schema, Compile, and IR Pipeline

Rationale: A deterministic IR and clear errors underpin safety and operator trust. Matching POLICY.md exactly reduces ambiguity across services and tests.

Planned changes:
- Align Pydantic models with the exact Policy Spec v1 schema including defaults (e.g., trigger_group.logic default ANY), required fields, and durations/cron validation rules.
- Implement strict compile pipeline steps: normalize triggers, bind field scopes, expand selectors (when possible), compute windows, and produce a stable IR with version_int and content hash.
- Ensure compile-time capability verification against plugin schemas; report blockers for unknown capability/target types.
- Embed resolved_ids and resolved_at in IR; if dynamic_resolution=true and compile-time resolution is partial/empty, record rationale and allow re-resolution at execute-time.
- Compute and persist sha256 hash over normalized spec (stable serialization with key ordering) to support 409 duplicate detection.

Metrics:
- 100% of valid policies produce identical IR/hash across runs (determinism test).
- Compile latency p50/p95 tracked and kept under target (e.g., p95 < 200 ms for typical specs).


## Theme 2 — Severity Taxonomy and Validation/Dry-run Gating

Rationale: Clear gating avoids unsafe activation. Info/warn/error/blocker semantics also drive operator UX and CI/CD policies.

Planned changes:
- Enforce Save disabled on any blocker from schema or compile; Save-Disabled and Save-&-Enable button states reflect backend results.
- Enforce Enable blocked on any error severity from dry-run (per policy or per action/target rolled up).
- Include per-field JSON pointer paths in validation responses for precise UX mapping.
- Standardize warn elevation rules (e.g., stale inventory → warn) and document downgrade/upgrade logic in the engine.

Metrics:
- No policy with compile blockers can be saved (negative integration test).
- Enable attempt with driver error must be rejected (integration test coverage).


## Theme 3 — Driver Contract, Inverse Registry, and SLA Overrides

Rationale: Predictable driver behavior enables safe previews and idempotency across heterogeneous systems.

Planned changes:
- Ensure all included drivers implement the standardized dry-run response shape: ok, severity, idempotency_key, preconditions, plan, effects, reason.
- Populate invertibility metadata and optional idempotency hints in plugin.yaml; add validation that checks for invertibility of verbs referenced in inverse creation.
- Respect defaults.dry_run_refresh_sla_s override during inventory fast refresh.
- Provide helper utilities in walnut.policy.driver_utils for building consistent idempotency keys and plan previews.

Metrics:
- 100% of core drivers pass dry-run shape conformance tests.
- Inverse creation endpoint returns needs_input list and valid inverse spec for supported capabilities.


## Theme 4 — Inventory, Discovery, and Searchable Index

Rationale: Accurate target selection and preflight require timely, searchable inventory data.

Planned changes:
- Implement fast vs full discovery code paths per integration with a toggle and SLA compliance.
- Build a per-host searchable index that merges canonical IDs, names, and driver-provided labels for the selector UI.
- Persist inventory timestamps and a stale flag; expose via /api/hosts/:host_id/inventory and return in dry-run transcripts.
- Provide resilient refresh with partial failure reporting as warn and clear reason messages.

Metrics:
- Fast refresh p95 under the driver SLA; stale flag accuracy validated in tests.
- Search returns expected items by id/name/label (unit tests for indexer).


## Theme 5 — Execution Engine: Ordering, Windows, and Concurrency

Rationale: Correct ordering and isolation prevent conflicting operations and ensure fairness.

Planned changes:
- Implement shortlist by trigger kind and sort by priority asc then UUID asc.
- Enforce idempotency_window and suppression_window before execution, emitting info-level suppressed events.
- If dynamic_resolution=true, re-resolve selectors at execute time; on empty results, downgrade to warn and continue.
- Implement per-host single-flight queues and a global concurrency cap configurable via settings.
- Record a run ledger entry for each execution with outcomes, keys, and effects summaries.

Metrics:
- Concurrency invariants: no overlapping executions for the same host (concurrency tests).
- Suppression/idempotency behavior covered by unit/integration tests.


## Theme 6 — API Surface and Contracts

Rationale: Minimal, predictable endpoints simplify client and automation integration.

Planned changes:
- Verify and harden endpoints: validate, save, update, dry-run, executions, inverse, host capabilities, inventory with refresh flag.
- Enforce HTTP codes per spec: 400 blocker, 409 duplicate hash, 422 driver structural invalid action.
- Return transcript_id and used_inventory metadata in dry-run responses.
- Cap executions history to last 30 with pagination support for future expansion.

Metrics:
- Integration tests assert status codes and response shapes for each endpoint.


## Theme 7 — Storage and Versioning

Rationale: Auditable, reproducible policy evolution and stable IR hashes are critical for change control.

Planned changes:
- Ensure policy rows persist spec, version_int, compiled_ir, hash, status, last_validation, last_dry_run, executions[<=30].
- Implement 409 duplicate detection by hash at Save with pointer to existing policy.
- Bump version_int on updates and compute new IR/hash.

Metrics:
- Duplicate Save returns 409 with existing policy reference (test).
- Version upgrade increments correctly and is reflected in IR.


## Theme 8 — UX Wizard and Console

Rationale: Operators need clarity: live validation, human-readable selector/trigger phrasing, and a transparent console.

Planned changes:
- Implement the 5-step wizard: Basics, Trigger, Conditions, Targets & Actions, Review.
- Add live schema validation on each step; map backend JSON pointer errors to fields.
- Provide selector editor supporting list/range/query grammar with preview of resolved targets.
- Build a Console section with Schema, Compile, and Preflight panes, showing IR hash and dry-run tables (severity, preconditions, plan, effects).
- “Create Inverse” generates a disabled inverse spec and highlights needs_input paths.

Metrics:
- E2E tests: create → validate → inverse → enable → simulate event (Playwright/Cypress).
- UX telemetry: reduction in validation retries and time-to-enable in testing sessions.


## Theme 9 — Security and Compliance

Rationale: Protect API surfaces and ensure auditable operations.

Planned changes:
- Enforce CSRF header checks on /api/* and JWT-based auth; document required headers in README.
- Emit audit events for validation, dry-run, execution with correlation IDs; ensure logs include subject and action details but mask secrets.
- Parameter validation hardening for durations/cron and selector grammar to avoid injection or resource abuse.

Metrics:
- Security tests confirm CSRF/JWT enforcement.
- Audit coverage: 100% of operations generate an audit record with correlation_id.


## Theme 10 — Observability and Diagnostics

Rationale: Faster triage and better SLO compliance.

Planned changes:
- Structured logging for compile, dry-run, execute stages including timings and severity decisions.
- Metrics: compile latency, dry-run latency, execute latency; counts per severity; queue depths; fast refresh SLA compliance.
- Tracing spans with correlation_id propagation.

Metrics:
- Dashboards for p50/p95 latencies and severity counts; alerts for SLA breaches.


## Theme 11 — Performance and Scalability

Rationale: Ensure responsiveness under load and avoid head-of-line blocking.

Planned changes:
- Cache capability schemas and inventory snapshots with staleness guards.
- Tune per-host queues and the global concurrency cap; backpressure on event intake when saturated.
- Optimize selector parsing and resolution with compiled regexes and precomputed indexes.

Metrics:
- Load tests: maintain SLA under N concurrent policies/hosts; no queue overflow in steady-state scenarios.


## Theme 12 — Testing Strategy

Rationale: Confidence to ship and refactor.

Planned changes:
- Unit tests: selector parser, compile normalization, severity mapping, inverse registry.
- Integration tests: API endpoints (validate/save/dry-run/executions/inverse), CRUD flows, suppression/idempotency, dynamic vs static resolution.
- Driver preflight tests: Proxmox and AOS-S dry-run depth testing and SLA behavior.
- E2E UI tests: wizard validation UX, inverse creation, enable gating.
- Performance & concurrency tests: event load, suppression windows, engine queue behavior.

Metrics:
- CI green with code coverage targets per area; periodic performance tests produce baselines.


## Theme 13 — Data Model and Migrations

Rationale: Stable evolution and rollback safety.

Planned changes:
- Alembic migrations for new columns (last_validation, last_dry_run, executions ledger if not present) and indexes (policy hash, policy status, host_id on executions).
- Ensure execution ledger size is capped per policy via DB constraints or pruning jobs.

Metrics:
- Migration apply/rollback tested in dev; DB health command validates indexes and constraints.


## Theme 14 — Edge Cases and Failure Semantics

Rationale: Avoid silent failures and ambiguous states.

Planned changes:
- Empty selector after dynamic re-resolution → warn and continue; record in transcript.
- Capability missing after compile → upgrade to error with guidance to revalidate.
- Partial refresh failures → warn with detailed reason; include used_inventory.stale=true in transcript.
- VM already at desired state → info no-op; compute effects to show no changes.

Metrics:
- Targeted tests for each edge case asserting severity and messaging.


## Theme 15 — Documentation and Governance

Rationale: Keep the team aligned and reduce drift from the spec.

Planned changes:
- Keep POLICY.md as the single source of truth; link this policy-diff.md as the living implementation plan.
- Add developer docs for driver authors covering dry-run shape, invertibility metadata, and SLA overrides.
- Establish a spec change process: PRs must include updates to POLICY.md and tests; track a version_int roadmap.

Metrics:
- All related PRs reference sections in POLICY.md; no undocumented behaviors introduced (review checklist).


## Milestones and Sequencing

1. Backend schema+compile+IR hardening and hash/duplicate detection.
2. Driver contract conformance and inverse registry plumbing.
3. Inventory fast/slow refresh and searchable index.
4. Engine windows, concurrency, and runtime order with ledger.
5. API hardening and status code correctness.
6. UX wizard/console enhancements and inverse workflow.
7. Observability and security hardening.
8. Test suite expansion and performance/concurrency tests.
9. Migrations and storage caps.

Each milestone should land with tests, documentation updates, and metrics instrumentation.


## Risks and Mitigations

- Driver heterogeneity: Some cannot produce rich dry-run plans. Mitigate with adapter utilities and minimal acceptable plan format.
- Inventory staleness: Fast refresh may time out for some devices. Mitigate with SLA overrides and clear warn semantics; allow operator override.
- Determinism drift: Serialization or ordering bugs can change hashes. Mitigate with deterministic encoders and explicit ordering tests.
- Concurrency deadlocks: Queueing logic bugs. Mitigate with timeouts, watchdog metrics, and property-based tests on scheduler.


## Acceptance Criteria

- Endpoints, storage, and engine behavior match POLICY.md, validated by passing unit/integration/E2E tests and by operational metrics within SLA.
- Drivers conform to the dry-run response shape and inverse metadata.
- UX provides live validation and a transparent console with IR hash and dry-run previews.
- policy-diff.md exists with this plan and is kept updated as implementation progresses.
