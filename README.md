# walNUT - Smart UPS Management & Power Orchestration

**Protect your infrastructure from power outages with intelligent, automated responses.**

walNUT monitors your UPS devices and automatically manages your servers, VMs, and network equipment during power events. Instead of scrambling to manually shut down systems when the power goes out, walNUT does it for you - safely and in the right order.

## What walNUT Does

🔋 **Monitors your UPS** - Connects to any UPS that supports Network UPS Tools (NUT)  
🤖 **Automates power events** - Automatically shuts down VMs, servers, and network equipment  
⚡ **Prevents data loss** - Graceful shutdowns with configurable timeouts and confirmations  
🛡️ **Keeps you safe** - Dry-run testing, suppression windows, and safety checks  
📊 **Shows you everything** - Real-time dashboard with power charts and event history  

## Quick Start (5 minutes)

**Prerequisites:** Docker and a UPS with NUT server running

```bash
# 1. Clone and setup
git clone https://github.com/walNUT-UPS/walnut-orchestrator.git
cd walnut-orchestrator

# 2. Create configuration
cat > .env << EOF
WALNUT_DB_KEY=your_secure_32_character_master_key_here
WALNUT_JWT_SECRET=your_secure_32_character_jwt_secret_here
NUT_HOST=your-nut-server-ip
NUT_USERNAME=monitor
NUT_PASSWORD=your_nut_password
EOF

# 3. Start walNUT (builds containers locally)
docker compose -f docker-full/docker-compose.yml up --build -d

# 4. Setup admin account
docker exec walnut-api-full-backend python -m walnut.cli.main db init
docker exec walnut-api-full-backend python -m walnut.cli.main auth create-admin \
  --email admin@your-domain.com --password secure_password
```

**That's it!** Open http://localhost:3333 and login to see your UPS status.

## What You Get

### 📱 **Modern Web Interface**
- **Live UPS monitoring** with battery status, runtime, and power charts
- **Event timeline** showing power outages, restorations, and automated actions  
- **Policy builder** for creating custom automation rules with drag-and-drop
- **Integration management** for connecting your infrastructure

### ⚙️ **Smart Automation** 
- **Custom policies** - "When UPS goes on battery for 2 minutes, shut down non-critical VMs"
- **Dry-run testing** - Test your policies safely before enabling them
- **Gradual shutdowns** - Shut down systems in priority order with proper delays
- **Recovery policies** - Automatically start systems back up when power returns

### 🔌 **Works With Everything**
- **Any UPS** that supports Network UPS Tools (APC, Eaton, CyberPower, etc.)
- **Virtualization** platforms (VMware, Proxmox, OpenStack, etc.)  
- **Network equipment** (switches, routers, POE devices)
- **Servers and workstations** via SSH, IPMI, or other protocols

---

## Technical Overview

walNUT is a comprehensive UPS monitoring and intelligent power management solution built with FastAPI and Network UPS Tools (NUT) integration. It provides encrypted SQLite storage with SQLCipher, advanced policy-driven automation, multi-protocol integrations, and enterprise-grade authentication.

## Features

### Core Infrastructure
- **Encrypted Database Storage**: SQLCipher AES-256 encryption for sensitive data
- **Connection Pooling**: Efficient database connection management with 5-second busy timeout  
- **WAL Mode**: Write-Ahead Logging for concurrent access
- **Migration Support**: Alembic-based schema migrations with version control

### Power Management
- **UPS Monitoring**: Real-time monitoring of UPS devices via NUT protocol
- **Policy System v1**: Advanced rule-based automation with dry-run capabilities
- **Event-Driven Architecture**: Normalized event bus for triggers and actions
- **Smart Orchestration**: Coordinated shutdown sequences with safety checks

## Policy Systems

walNUT implements multiple policy engines for different automation needs:

### Policy System v1 (Advanced Rules Engine)

**Core Functionality:**
- **Event Processing**: Receives normalized events and matches them against compiled policy rules
- **Multi-Level Matching**: Trigger groups (ANY/ALL logic) + condition evaluation  
- **Dynamic Target Resolution**: Re-resolves target selectors at execution time
- **Per-Host Execution Queues**: Prevents conflicting operations on same infrastructure
- **Suppression & Idempotency**: Configurable windows to prevent duplicate executions
- **Comprehensive Dry-Run**: Tests policies with real driver calls (read-only)
- **Execution Ordering**: Priority-based with deterministic tie-breaking

**Safety Features:**
- **Inventory Refresh**: Fast refresh with 5-second SLA before execution
- **Precondition Checks**: Driver-level validation before actions
- **Global Concurrency Limits**: Prevents system overload (default: 10 concurrent)
- **Stop-on-Match**: Optional early termination after first policy triggers
- **Audit Trail**: Complete execution history with correlation IDs

### Policy Structure
```json
{
  "version": 1,
  "name": "Emergency VM Shutdown",
  "enabled": true,
  "priority": 100,
  "trigger_group": {
    "logic": "ANY",
    "triggers": [
      { "type": "ups.state", "equals": "on_battery" }
    ]
  },
  "conditions": {
    "all": [
      { "scope": "ups", "field": "runtime_minutes", "op": ">=", "value": 5 }
    ]
  },
  "targets": {
    "host_id": "proxmox-cluster-01",
    "target_type": "vm",
    "selector": { "mode": "range", "value": "100-109" }
  },
  "actions": [
    {
      "capability_id": "proxmox.vm",
      "verb": "shutdown",
      "params": { "grace_s": 60, "confirm": true }
    }
  ],
  "suppression_window": "5m",
  "idempotency_window": "10m"
}
```

### Policy v2 (Simplified Capability-Based)
Streamlined format for simpler automation scenarios:

```json
{
  "version": "2.0",
  "name": "Emergency Infrastructure Shutdown",
  "enabled": true,
  "priority": 100,
  "trigger": {
    "type": "status_transition",
    "from": "OL",
    "to": "OB",
    "stable_for": "30s"
  },
  "conditions": {
    "all": [
      {"scope": "ups", "field": "runtime_minutes", "op": ">=", "value": 5}
    ]
  },
  "actions": [
    {
      "host_id": "infrastructure-host-id",
      "capability": "vm.lifecycle",
      "verb": "shutdown",
      "selector": {
        "labels": {"tier": "non-critical"},
        "names": ["test-vm-01", "dev-vm-02"]
      },
      "options": {"timeout": 60}
    }
  ],
  "safeties": {
    "suppression_window": "5m",
    "global_lock": "emergency_shutdown"
  }
}
```

**Key Differences from v1:**
- **Simplified Structure**: Single trigger instead of trigger groups
- **Capability-Centric**: Actions directly reference driver capabilities
- **Label-Based Selection**: More intuitive target selection
- **Embedded Targeting**: Each action specifies its own targets
- **Tolerant Linting**: More forgiving validation for easier authoring

See [POLICY.md](POLICY.md) for complete Policy System v1 specification.

### Integrations & Protocols
- **Multi-Protocol Support**: HTTP, SSH, SNMP, MQTT, WebSocket, NETCONF, gNMI
- **Infrastructure Platforms**: Virtualization platforms, container orchestrators, cloud providers
- **Network Devices**: Managed switches, routers, POE management, VLAN control
- **Discovery & Inventory**: Automatic target discovery with caching
- **Plugin Architecture**: Extensible driver system with manifest validation

### Authentication & Security
- **JWT Authentication**: Secure token-based authentication
- **OAuth/OIDC Support**: Enterprise SSO integration (configurable)
- **RBAC**: Role-based access control with admin/user roles
- **CSRF Protection**: Double-submit cookie pattern for state-changing requests
- **Encrypted Secrets**: Secure credential storage for integrations

### User Experience  
- **Modern Web UI**: React-based frontend with real-time updates
- **CLI Management**: Comprehensive command-line interface
- **WebSocket API**: Real-time event streaming and live updates
- **RESTful API**: Complete programmatic access to all functionality

## Frontend Application

The walNUT web interface is built with React, TypeScript, and Tailwind CSS:

### Key Features
- **Real-Time Dashboard**: Live UPS monitoring with WebSocket updates
- **Policy Management**: Visual policy editor with drag-and-drop capabilities  
- **Integration Management**: Configure and monitor external integrations
- **Host & Inventory**: Discover and manage infrastructure targets
- **Event Timeline**: Historical view of power events and system activities
- **Authentication**: Login/logout with JWT and OAuth/OIDC support
- **Responsive Design**: Mobile-friendly interface

### Main Screens
- **Overview**: UPS status, power charts, recent events
- **Policies**: Create, edit, and test power management policies
- **Integrations**: Configure Proxmox, AOS-S, and other integrations  
- **Hosts**: Manage infrastructure hosts and view inventory
- **Events**: Event timeline with filtering and search
- **Settings**: System configuration and user preferences

## Database Schema

The walNUT database includes the following table groups:

### Core Monitoring
- **ups_samples**: Rolling 24-hour UPS monitoring data (battery charge, runtime, voltage, load)
- **events**: Power events and system activities with severity levels
- **event_bus**: Internal event routing and correlation

### Integration Management
- **integration_types**: Available integration driver definitions
- **integration_instances**: Configured integration instances
- **integration_secrets**: Encrypted credential storage
- **integration_health**: Health monitoring and diagnostics
- **integration_events**: Integration-specific event logging
- **inventory_cache**: Discovered targets and capabilities

### Policy & Automation
- **policies_v1**: Advanced rule-based policies (JSON schema)
- **policy_executions**: Execution history and audit trail
- **policy_actions**: Individual action definitions and results
- **legacy_policies**: Simple shutdown policies (deprecated)

### Host & Target Management
- **hosts**: Managed infrastructure hosts
- **targets**: Discovered targets (VMs, ports, interfaces, etc.)
- **locks**: Distributed locking for coordinated operations

### Authentication & Users
- **users**: User accounts and profiles
- **oauth_accounts**: OAuth/OIDC linked accounts
- **secrets**: System secrets and encrypted storage
- **app_settings**: Application configuration settings

## NUT Integration

The core of walNUT is its ability to monitor UPS devices using the Network UPS Tools (NUT) protocol. This is handled by a background polling service that connects to a NUT server, fetches UPS data at regular intervals, and stores it in the database.

### Features

- **Asynchronous Polling**: The polling service runs as a non-blocking asyncio task.
- **Real-time Data**: Fetches UPS data every 5 seconds (configurable).
- **Event Detection**: Detects power state changes (e.g., mains power lost/restored, low battery) and records them as events.
- **Heartbeat Monitoring**: Detects if the connection to the NUT server is lost with a 30-second timeout.
- **Data Retention**: Stores a 24-hour rolling window of UPS data samples.
- **Graceful Shutdown**: The polling service can be started and stopped gracefully with the main application.

### Configuration

The NUT integration is configured via the following environment variables:

- `NUT_HOST`: The hostname or IP address of the NUT server (default: `localhost`).
- `NUT_PORT`: The port of the NUT server (default: `3493`).
- `NUT_USERNAME`: The username for authentication (optional).
- `NUT_PASSWORD`: The password for authentication (optional).

## Quick Start

### Development Setup

```bash
# Start backend server
export WALNUT_DB_KEY="dev_dev_dev_dev_dev_dev_dev_dev_32chars"
export WALNUT_JWT_SECRET="test_jwt_secret_32_characters_long_12345"
export WALNUT_SECURE_COOKIES=false
export WALNUT_ALLOWED_ORIGINS='["http://localhost:3000"]'
export WALNUT_POLICY_V1_ENABLED=true

# Initialize database and create admin user
python -m walnut.cli.main db init
python -m walnut.cli.main auth create-admin --email admin@test.com --password testpass

# Start backend
uvicorn walnut.app:app --host 0.0.0.0 --port 8000 --reload
```

```bash
# In a separate terminal, start frontend
cd frontend
npm install
npm run dev
```

Then open http://localhost:3000 and login with admin@test.com / testpass.

## API Documentation

### REST Endpoints

| Category | Endpoint | Description |
|----------|----------|-------------|
| **Authentication** | `POST /auth/jwt/login` | User login |
| | `POST /auth/jwt/logout` | User logout |
| | `GET /auth/users/me` | Current user profile |
| **UPS & Events** | `GET /api/ups/samples` | Recent UPS monitoring data |
| | `GET /api/events` | System events and alerts |
| | `POST /api/admin/events` | Inject test events (admin) |
| **Policies** | `GET /api/policies` | List all policies |
| | `POST /api/policies` | Create new policy |
| | `POST /api/policies/validate` | Validate policy spec |
| | `POST /api/policies/{id}/dry-run` | Test policy execution |
| | `GET /api/policies/{id}/executions` | Policy execution history |
| **Integrations** | `GET /api/integrations` | List integrations |
| | `POST /api/integrations` | Create integration |
| | `GET /api/integrations/{id}/health` | Integration health status |
| **Hosts & Inventory** | `GET /api/hosts` | List managed hosts |
| | `GET /api/hosts/{id}/inventory` | Host target inventory |
| | `GET /api/hosts/{id}/capabilities` | Available capabilities |
| **System** | `GET /health` | System health check |
| | `GET /api/system/status` | Detailed system status |
| | `GET /api/csrf-token` | Get CSRF token |

### WebSocket Endpoints

- **`/ws`**: Real-time UPS data, events, and system updates
- **`/ws/events`**: Event stream subscription  
- **Authentication**: Via query parameter `?token=<jwt>` or cookie

### Production Deployment

#### Docker Deployment (Recommended)

walNUT is designed for Docker deployment with a multi-service architecture:

```bash
# Create environment file
cat > .env << EOF
WALNUT_DB_KEY=your_secure_32_character_master_key_here
WALNUT_JWT_SECRET=your_secure_32_character_jwt_secret_here
WALNUT_SECURE_COOKIES=true
WALNUT_ALLOWED_ORIGINS=["https://your-domain.com"]
WALNUT_POLICY_V1_ENABLED=true
# NUT configuration
NUT_HOST=your-nut-server
NUT_PORT=3493
NUT_USERNAME=monitor
NUT_PASSWORD=your_nut_password
# Optional OAuth/OIDC
WALNUT_OIDC_ENABLED=false
EOF

# Deploy with Docker Compose (builds containers)
docker compose -f docker-full/docker-compose.yml up --build -d

# Initialize database and create admin user
docker exec walnut-api-full-backend python -m walnut.cli.main db init
docker exec walnut-api-full-backend python -m walnut.cli.main auth create-admin \
  --email admin@your-domain.com --password secure_admin_password
```

The application will be available at http://localhost:3333.

#### Manual Installation Prerequisites

- Python 3.12+
- SQLCipher development libraries (`sudo apt install libsqlcipher-dev` on Ubuntu/Debian)
- Master encryption key (32+ characters)
- JWT signing secret (32+ characters)
- Node.js 18+ and npm (for frontend development)"

### Installation

```bash
# Clone the repository
git clone https://github.com/walNUT-UPS/walnut-orchestrator.git
cd walnut-orchestrator

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -e .

# Set required environment variables
export WALNUT_DB_KEY="your_32_character_master_key_here_abcdef"
export WALNUT_JWT_SECRET="your_32_character_jwt_secret_here_123456"

# Initialize database
python -m walnut.cli.main db init

# Create admin user
python -m walnut.cli.main auth create-admin --email admin@example.com --password secure_password

# Check database health
python -m walnut.cli.main db health
```

### Database Management

```bash
# Initialize encrypted database
python -m walnut.cli.main db init

# Check database health and diagnostics  
python -m walnut.cli.main db health

# View database statistics
python -m walnut.cli.main db stats

# Reset database (WARNING: deletes all data)
python -m walnut.cli.main db reset --yes

# Vacuum database to reclaim space
python -m walnut.cli.main db vacuum

# Show version information
python -m walnut.cli.main db version
```

## Configuration

### Environment Variables

#### Required
- `WALNUT_DB_KEY`: Master encryption key (required, 32+ characters)
- `WALNUT_JWT_SECRET`: JWT signing secret (required, 32+ characters)

#### NUT Configuration
- `NUT_HOST`: Hostname of the NUT server (default: `localhost`)
- `NUT_PORT`: Port of the NUT server (default: `3493`)
- `NUT_USERNAME`: Username for the NUT server (optional)
- `NUT_PASSWORD`: Password for the NUT server (optional)

#### Security & CORS
- `WALNUT_SECURE_COOKIES`: Enable secure cookies for production (default: `true`)
- `WALNUT_ALLOWED_ORIGINS`: JSON array of allowed origins for CORS (default: `["http://localhost:3000"]`)

#### Features
- `WALNUT_POLICY_V1_ENABLED`: Enable Policy System v1 (default: `false`)

#### OAuth/OIDC (Optional)
- `WALNUT_OIDC_ENABLED`: Enable OAuth/OIDC authentication (default: `false`)
- `WALNUT_OIDC_CLIENT_ID`: OAuth client ID
- `WALNUT_OIDC_CLIENT_SECRET`: OAuth client secret  
- `WALNUT_OIDC_DISCOVERY_URL`: OIDC discovery endpoint URL

#### Development
- `WALNUT_DB_KEY_DEV`: Development key (not for production)

### Docker Secrets

For production deployments, mount the master key as a Docker secret:

```bash
echo "your_secure_master_key" | docker secret create walnut_db_key -
```

The key will be automatically loaded from `/run/secrets/walnut_db_key`.

## Database Engine Features

### SQLCipher Encryption
- AES-256-CBC cipher with 64,000 PBKDF2 iterations
- Encrypted storage of all sensitive data
- Master key management from environment or Docker secrets

### WAL Mode Configuration
- Write-Ahead Logging for concurrent access
- 5-second busy timeout for connection conflicts
- Optimized pragma settings for performance

### Connection Pooling
- Static connection pool with configurable size (default: 20)
- Connection recycling every hour
- Health monitoring with automatic recovery

### Local Disk Validation
- Prevents network filesystem issues
- File locking tests to ensure SQLite compatibility
- Automatic parent directory creation

## Development

### Running Tests

For comprehensive testing instructions including Policy System tests, see [docs/TESTING.md](docs/TESTING.md).

```bash
# Set required environment variables
export WALNUT_DB_KEY="test_key_32_characters_minimum_length"
export WALNUT_JWT_SECRET="test_jwt_secret_32_characters_long_12345"
export WALNUT_POLICY_V1_ENABLED=true

# Install development dependencies
pip install -e ".[dev]"

# Initialize test database
python -m walnut.cli.main db reset --yes
python -m walnut.cli.main db init
python -m walnut.cli.main auth create-admin --email test@example.com --password testpass

# Run all tests with coverage
pytest --cov=walnut --cov-report=term-missing tests/

# Run database tests only
pytest tests/test_database.py -v

# Run Policy System v1 tests
pytest tests/test_policy_*.py --cov=walnut.policy --cov=walnut.inventory -v

# Run integration tests
pytest tests/test_*integration*.py -v

# Run authentication tests
pytest tests/auth/ -v
```

### Code Quality

```bash
# Format code
black walnut/ tests/
isort walnut/ tests/

# Lint code  
ruff check walnut/ tests/
ruff format walnut/ tests/

# Type checking
mypy walnut/

# Pre-commit hooks (recommended)
pre-commit install
pre-commit run --all-files
```

## Architecture

### Core Services
```
walnut/core/
├── services.py             # Service lifecycle management
├── app_settings.py         # Dynamic configuration management
├── bus.py                  # Internal event bus
├── health.py               # System health monitoring
├── integration_registry.py # Plugin discovery and management
├── manifests.py            # Plugin manifest validation
├── nut_service.py          # UPS monitoring service
├── plugin_schema.py        # Plugin schema definitions
├── registry.py             # Component registry
├── secrets.py              # Credential management
├── venv_isolation.py       # Python environment isolation
└── websocket_manager.py    # Real-time connection management
```

### Authentication & Security
```
walnut/auth/
├── auth.py            # FastAPI-Users integration
├── csrf.py            # CSRF protection middleware
├── deps.py            # Authentication dependencies
├── models.py          # User and OAuth models
├── router.py          # Authentication endpoints
├── schemas.py         # Pydantic schemas
└── sync_user_db.py    # User synchronization utilities
```

### Policy System v1
```
walnut/policy/
├── compile.py         # Policy compilation to IR
├── engine.py          # Execution engine
└── models.py          # Policy data models

walnut/policies/       # Legacy policy support
├── linter.py          # Policy validation
├── priority.py        # Priority management
└── schemas.py         # Policy schemas
```

### Integration Framework
```
walnut/transports/
├── base.py            # Transport interface
├── http_adapter.py    # HTTP/REST transport
├── ssh_adapter.py     # SSH transport
├── snmp_adapter.py    # SNMP transport
├── mqtt_adapter.py    # MQTT transport
├── websocket_adapter.py  # WebSocket transport
├── netconf_adapter.py    # NETCONF transport
├── gnmi_adapter.py       # gNMI transport
├── manager.py            # Transport management
└── registry.py           # Transport registry

walnut/inventory/
├── index.py           # Target discovery and indexing
└── __init__.py

integrations/
├── walnut.proxmox.ve/ # Proxmox VE integration
│   ├── driver.py      # Proxmox driver implementation
│   └── plugin.yaml    # Plugin manifest
└── com.aruba.aoss/    # Aruba AOS-S integration
    ├── driver.py      # AOS-S driver implementation
    ├── plugin.yaml    # Plugin manifest
    └── parsers/       # Protocol parsers
```

### NUT Integration
```
walnut/nut/
├── client.py          # Asynchronous NUT client
├── poller.py          # Background polling service
├── models.py          # Pydantic data models for UPS data
├── events.py          # Power event detection logic
└── __init__.py
```

### Database Layer
```
walnut/database/
├── engine.py              # SQLCipher engine with WAL mode
├── models.py              # SQLAlchemy table definitions  
├── connection.py          # Connection pooling and management
├── sqlcipher_dialect.py   # Custom SQLCipher dialect
└── __init__.py
```

### API Layer
```
walnut/api/
├── admin_events.py    # Admin event injection
├── events.py          # Event management
├── hosts.py           # Host management
├── integrations.py    # Integration management
├── policies.py        # Policy management
├── policy_runs.py     # Policy execution history
├── system.py          # System status
├── ups.py             # UPS data endpoints
├── websocket.py       # Real-time WebSocket endpoints
└── workers.py         # Background task management
```

### CLI Layer
```
walnut/cli/
├── main.py            # CLI entry point
├── auth.py            # User management commands
├── backup.py          # Backup/restore commands
├── database.py        # Database management commands
├── hosts.py           # Host management commands
├── keys.py            # Key management commands
├── system.py          # System commands
├── test.py            # Testing commands
└── utils.py           # CLI utilities
```

### Frontend (React + TypeScript)
```
frontend/
├── App.tsx            # Main application
├── main.tsx           # Entry point
├── components/        # UI components
│   ├── auth/          # Authentication components
│   ├── policy/        # Policy management UI
│   ├── hosts/         # Host management UI
│   ├── screens/       # Main application screens
│   └── ui/            # Reusable UI components
├── contexts/          # React contexts
├── hooks/             # Custom React hooks
├── services/          # API client services
└── styles/            # CSS and styling
```

## API Security & CSRF Protection

walNUT implements selective CSRF protection to balance security and usability:

### CSRF Requirements by Endpoint Type

| Endpoint Type | Path Pattern | CSRF Required | Notes |
|---------------|--------------|---------------|-------|
| **Authentication** | `/auth/*` | ❌ No | Login, logout, registration |
| **API Endpoints** | `/api/*` | ✅ Yes | All data operations |
| **WebSocket** | `/ws*` | ❌ No | Real-time connections |

### Using CSRF-Protected API Endpoints

For all API calls to `/api/*` endpoints, include the `X-CSRF-Token` header:

```javascript
// Example API call with CSRF protection
fetch('/api/me', {
  method: 'GET',
  headers: {
    'Authorization': 'Bearer ' + token
  }
})
```

```bash
# cURL example
curl -X GET /api/me \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-CSRF-Token: required"
```

### CSRF Behavior Details

- **Login Flow**: `/auth/jwt/login` works without CSRF token for initial authentication
- **State-Changing Requests**: When using cookie-based auth, POST/PUT/PATCH/DELETE to `/api/*` require a valid CSRF token
- **How It Works**: Call `/api/csrf-token` after login to get a token and set a `walnut_csrf` cookie. Echo the returned value in the `X-CSRF-Token` header. The header must match the cookie value.
- **Bearer Exemption**: Requests authenticated via `Authorization: Bearer <token>` are exempt from CSRF checks
- **WebSocket Auth**: WebSocket connections authenticate via query parameter or cookie; CSRF does not apply

### Example Integration

```javascript
// Complete login and API access flow (cookie auth + CSRF)
async function loginAndFetchData() {
  // 1) Login (sets auth cookie)
  await fetch('/auth/jwt/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'username=user&password=pass',
    credentials: 'include'
  });

  // 2) Get CSRF token (sets walnut_csrf cookie and returns token)
  const csrfResp = await fetch('/api/csrf-token', { credentials: 'include' });
  const { csrf_token } = await csrfResp.json();

  // 3) Make state-changing request with matching header
  const res = await fetch('/api/policies', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf_token },
    body: JSON.stringify({
      version: 1,
      name: 'Emergency Shutdown Policy',
      enabled: true,
      priority: 100,
      trigger_group: {
        logic: 'ANY',
        triggers: [{ type: 'ups.state', equals: 'on_battery' }]
      },
      conditions: { all: [] },
      targets: {
        host_id: 'uuid-of-infrastructure-host',
        target_type: 'vm',
        selector: { mode: 'list', value: '100,101,102' }
      },
      actions: [{
        capability_id: 'infrastructure.vm',
        verb: 'shutdown',
        params: { grace_s: 60, confirm: true }
      }],
      suppression_window: '5m',
      idempotency_window: '10m'
    }),
    credentials: 'include'
  });
  return await res.json();
}
```

## Security Considerations

1. **Encryption at Rest**: All sensitive data encrypted with SQLCipher AES-256
2. **Master Key Security**: Store encryption keys securely using environment variables or Docker secrets
3. **JWT Security**: Secure token-based authentication with configurable expiration
4. **CSRF Protection**: Double-submit cookie pattern for state-changing requests (Bearer-auth exempt)
5. **OAuth/OIDC**: Enterprise SSO integration for centralized authentication
6. **Local Storage Only**: Database validation prevents network filesystem usage
7. **Connection Timeouts**: Prevent connection hanging with busy timeouts
8. **Role-Based Access**: Admin and user roles with appropriate permissions
9. **Secure Defaults**: Production-ready security settings by default
10. **Integration Secrets**: Encrypted credential storage for external system access

## Performance Optimizations

- WAL mode for concurrent read/write access
- Connection pooling with configurable limits
- Optimized SQLite pragma settings
- Efficient indexing on frequently queried columns
- Memory-based temporary storage

## Error Handling

The database layer includes comprehensive error handling for:

- Encryption key validation and loading
- Connection pool exhaustion
- Database locking conflicts
- Migration failures
- Network filesystem detection

## Monitoring and Diagnostics

Built-in health checks provide:

- Connection status and latency
- Pool utilization metrics
- Database file size and growth
- Encryption status verification
- WAL mode confirmation

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## Support

For issues and feature requests, please use the GitHub issue tracker.
