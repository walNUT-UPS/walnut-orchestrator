# Proxmox VM Lifecycle via walNUT API (cURL)

This guide shows how to check the status of a VM and power it on through the walNUT API using cURL. It uses the existing Proxmox integration instance already configured in walNUT.

## Prerequisites

- walNUT backend is running and reachable (default `http://localhost:8000`).
- A Proxmox VE integration instance exists and is healthy (type_id `walnut.proxmox.ve`).
- A user account with access (example below uses `admin@test.com` / `testpass`).
- Tools: `curl` and `jq`.

## Quick Reference

Environment variables used below:

```bash
BASE="http://localhost:8000"
USER_EMAIL='admin@test.com'
USER_PASSWORD='testpass'
JAR=".tmp/cookies.proxmox.txt"
mkdir -p .tmp
```

### 1) Health check (optional)

```bash
curl -sS "$BASE/api/health" | jq
```

### 2) Authenticate and store session cookies

```bash
curl -sS -c "$JAR" \
  -X POST "$BASE/auth/jwt/login" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data "username=${USER_EMAIL}&password=${USER_PASSWORD}"
```

Notes:
- walNUT uses cookie-based auth. The cookie jar is reused for subsequent requests.

### 3) Get CSRF token (required for POST/PUT/PATCH/DELETE to `/api`)

```bash
CSRF=$(curl -sS -b "$JAR" "$BASE/api/csrf-token" | jq -r .csrf_token)
echo "$CSRF"
```

### 4) Find the Proxmox integration instance id

```bash
INST_ID=$(curl -sS -b "$JAR" "$BASE/api/integrations/instances" \
  | jq -r '.[] | select(.type_id=="walnut.proxmox.ve") | .instance_id' | head -n1)
echo "Proxmox instance: $INST_ID"
```

If you have multiple instances, further filter by config fields (e.g., host):

```bash
INST_ID=$(curl -sS -b "$JAR" "$BASE/api/integrations/instances" \
  | jq -r '.[] | select(.type_id=="walnut.proxmox.ve" and .config.host=="your-pve-host") | .instance_id' | head -n1)
```

### 5) Get VM status (VMID 123)

Endpoint: `GET /api/integrations/instances/{instance_id}/inventory?type=vm`

```bash
curl -sS -b "$JAR" "$BASE/api/integrations/instances/$INST_ID/inventory?type=vm" \
  | jq -r '.items[] | select(.external_id=="123") | {id:.external_id,name:.name,status:.attrs.status,qmp:.attrs.qmpstatus,cpu:.attrs.cpu_usage,mem:.attrs.mem_used}'
```

Example output:

```json
{
  "id": "123",
  "name": "pod1-client",
  "status": "stopped",
  "qmp": null,
  "cpu": null,
  "mem": null
}
```

### 6) Start the VM (vm.lifecycle)

Endpoint: `POST /api/integrations/instances/{instance_id}/vm/{vm_id}/lifecycle`

Body:

```json
{"verb":"start","dry_run":false}
```

Request:

```bash
curl -sS -b "$JAR" -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
  -X POST "$BASE/api/integrations/instances/$INST_ID/vm/123/lifecycle" \
  --data '{"verb":"start","dry_run":false}' | jq
```

Example response (Proxmox task id):

```json
{
  "task_id": "UPID:pve:...:qmstart:123:root@pam!walnut:"
}
```

Supported verbs for `walnut.proxmox.ve`: `start`, `stop`, `shutdown`, `suspend`, `resume`, `reset`.

### 7) Verify VM status again

```bash
curl -sS -b "$JAR" "$BASE/api/integrations/instances/$INST_ID/inventory?type=vm" \
  | jq -r '.items[] | select(.external_id=="123") | {id:.external_id,status:.attrs.status,qmp:.attrs.qmpstatus}'
```

Example:

```json
{
  "id": "123",
  "status": "running",
  "qmp": null
}
```

## Logs

- Backend log stream used during development: `.tmp/back.log`
- You can tail it to observe Proxmox API calls and lifecycle actions:

```bash
tail -f .tmp/back.log
```

## Error Handling Tips

- `401 Unauthorized`: ensure you logged in and are sending cookies (`-b "$JAR"`).
- `403 Forbidden`: missing `X-CSRF-Token` header on state-changing requests; call `/api/csrf-token` first.
- `404 Not Found` on lifecycle: verify the endpoint path and that the backend has this route available (restart if you just updated backend code).
- VM not listed: confirm the VMID exists on the Proxmox node configured in the instance (inventory endpoint returns all VMs visible to the configured node and token).

## Other Lifecycle Actions (snippets)

Replace `start` below with the desired verb. Supported: `start`, `stop`, `shutdown`, `suspend`, `resume`, `reset`.

Stop (force-off):

```bash
curl -sS -b "$JAR" -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
  -X POST "$BASE/api/integrations/instances/$INST_ID/vm/123/lifecycle" \
  --data '{"verb":"stop","dry_run":false}' | jq
```

Shutdown (graceful if guest agent available, else ACPI):

```bash
curl -sS -b "$JAR" -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
  -X POST "$BASE/api/integrations/instances/$INST_ID/vm/123/lifecycle" \
  --data '{"verb":"shutdown","dry_run":false}' | jq
```

Suspend (pause):

```bash
curl -sS -b "$JAR" -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
  -X POST "$BASE/api/integrations/instances/$INST_ID/vm/123/lifecycle" \
  --data '{"verb":"suspend","dry_run":false}' | jq
```

Resume:

```bash
curl -sS -b "$JAR" -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
  -X POST "$BASE/api/integrations/instances/$INST_ID/vm/123/lifecycle" \
  --data '{"verb":"resume","dry_run":false}' | jq
```

Reset (reboot the VM process):

```bash
curl -sS -b "$JAR" -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
  -X POST "$BASE/api/integrations/instances/$INST_ID/vm/123/lifecycle" \
  --data '{"verb":"reset","dry_run":false}' | jq
```
