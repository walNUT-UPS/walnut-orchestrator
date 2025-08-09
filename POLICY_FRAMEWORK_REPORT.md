# Policy Frameworks – P1+P2 Report

This report summarizes the work completed for the Policy Editor Foundations sprint. The goal was to build the frameworks for the policy system, including the schema, CRUD APIs, linter, planner, and the basic structure for action adapters and the frontend UI.

## Scaffolded Components

### Backend

-   **Database Models (`walnut/database/models.py`):**
    -   New tables for `Policy`, `PolicyRun`, `PolicyAction`, `EventBus`, and `Lock` have been defined.
    -   The old `Policy` and `Event` tables have been renamed to `LegacyPolicy` and `LegacyEvent` to avoid conflicts.
    -   *Note: An Alembic migration has not been generated yet due to issues with the custom database engine.*
-   **FastAPI Application (`walnut/app.py`):**
    -   A new FastAPI application has been created to serve the API.
-   **Policy Modules (`walnut/policies/`):**
    -   `schemas.py`: Pydantic schemas for policy JSON and compiled plans.
    -   `linter.py`: A linter to validate policies for errors and warnings.
    -   `plan.py`: A pure planner to compile policies into a structured plan.
    -   `priority.py`: Logic to recompute policy priorities based on order.
-   **Action Adapters (`walnut/actions/`):**
    -   A `base.py` with a `BaseAction` abstract class.
    -   Skeleton implementations for `ssh`, `proxmox`, `webhook`, `notify`, and `sleep` actions. These support `probe` and `dry_run` modes and raise `NotImplementedError` for `execute` mode.
-   **Target Resolver (`walnut/targets/resolve.py`):**
    -   A placeholder target resolver that returns a hardcoded list of hosts.
-   **API Endpoints (`walnut/api/`):**
    -   `policies.py`: CRUD endpoints for policies, plus reordering, linting, and planning.
    -   `policy_runs.py`: Endpoints for listing and retrieving policy runs.
    -   `admin_events.py`: An admin-only endpoint for injecting events.
-   **Tests:**
    -   Unit tests for schemas, linter, and API endpoints have been created.

### Frontend (`frontend/walnut-ui/`)

-   The basic directory structure for a React + TypeScript application has been created.
-   A `package.json` with initial dependencies has been added.
-   Placeholder (empty) files have been created for all the required components, pages, services, and types as per the user's instructions.

## API Endpoints

-   `GET /api/policies`: List policies.
-   `POST /api/policies`: Create a new policy.
-   `GET /api/policies/{id}`: Get a single policy.
-   `PUT /api/policies/{id}`: Update a policy.
-   `DELETE /api/policies/{id}`: Delete a policy.
-   `POST /api/policies/reorder`: Reorder policies and recompute priorities.
-   `POST /api/policies/{id}/lint`: Lint a policy.
-   `POST /api/policies/{id}/plan`: Generate a plan for a policy.
-   `GET /api/policy-runs`: List policy runs.
-   `GET /api/policy-runs/{run_id}`: Get a single policy run.
-   `POST /api/admin/events/inject`: Inject a simulation event (admin only).

## Demo Flow

Since the database is not yet migrated and the frontend is not implemented, a full end-to-end demo is not possible. However, the backend API can be tested with a tool like `curl` or Postman.

1.  **Start the backend server:**
    ```bash
    uvicorn walnut.app:app --reload
    ```
2.  **Create a policy:**
    Send a `POST` request to `/api/policies` with a valid policy JSON body.
3.  **Test the plan endpoint:**
    Send a `POST` request to `/api/policies/{id}/plan` to see the compiled plan.
4.  **Inject an event:**
    Send a `POST` request to `/api/admin/events/inject` to simulate an event.

## Intentionally Stubbed for Next Sprint

-   **Database Migration:** An Alembic migration needs to be generated and run to apply the new schema. This was blocked by issues with the custom database engine.
-   **Real I/O:** All I/O operations are currently placeholders. The action adapters, target resolver, and API endpoints do not interact with a database or external services.
-   **`execute` Mode:** The `execute` mode in all action adapters is not implemented.
-   **Suppression Window Logic:** The suppression window logic is just a placeholder in the planner.
-   **Frontend Implementation:** The frontend consists of empty placeholder files.
-   **Authentication:** The admin endpoint uses a dummy dependency for authentication.
-   **Full Test Coverage:** While basic tests are in place, more comprehensive tests, especially for the dry-run and validation logic (P2), are needed.
