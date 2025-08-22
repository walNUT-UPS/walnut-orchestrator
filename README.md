# walNUT - UPS Management Platform

walNUT is a comprehensive UPS monitoring and power management solution built with FastAPI and Network UPS Tools (NUT) integration. It provides encrypted SQLite storage with SQLCipher, connection pooling, and advanced power event orchestration.

## Features

- **Encrypted Database Storage**: SQLCipher AES-256 encryption for sensitive data
- **UPS Monitoring**: Real-time monitoring of UPS devices via NUT protocol
- **Power Event Management**: Automated shutdown orchestration during power events
- **Integration Support**: Proxmox, Tapo devices, SSH hosts, and more
- **Connection Pooling**: Efficient database connection management with 5-second busy timeout
- **WAL Mode**: Write-Ahead Logging for concurrent access
- **CLI Management**: Comprehensive database management commands
- **Migration Support**: Alembic-based schema migrations

## Database Schema

The walNUT database includes the following core tables:

- **ups_samples**: Rolling 24-hour UPS monitoring data (battery charge, runtime, voltage, load)
- **events**: Power events and system activities with severity levels
- **integrations**: External system configurations (Proxmox, Tapo, SSH, etc.)
- **hosts**: Managed hosts for coordinated shutdown
- **secrets**: Encrypted credential storage
- **policies**: Shutdown policies and automation rules

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

### Prerequisites

- Python 3.12+
- SQLCipher development libraries
- Master encryption key (32+ characters)

### Installation

```bash
# Clone the repository
git clone https://github.com/walNUT-UPS/walnut-orchestrator.git
cd walnut

# Install dependencies
pip install -e .

# Set master key
export WALNUT_DB_KEY="your_32_character_master_key_here"

# Initialize database
walnut-db init

# Check database health
walnut-db health
```

### Database Management

```bash
# Initialize encrypted database
walnut-db init --db-path /path/to/walnut.db

# Check database health and diagnostics
walnut-db health --json

# View database information
walnut-db info

# Reset database (WARNING: deletes all data)
walnut-db reset --yes

# Test encryption setup
walnut-db test-encryption
```

## Configuration

### Environment Variables

- `WALNUT_DB_KEY`: Master encryption key (required, 32+ characters)
- `WALNUT_DB_KEY_DEV`: Development key (not for production)
- `NUT_HOST`: Hostname of the NUT server (default: `localhost`).
- `NUT_PORT`: Port of the NUT server (default: `3493`).
- `NUT_USERNAME`: Username for the NUT server (optional).
- `NUT_PASSWORD`: Password for the NUT server (optional).

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
# Install development dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run database tests only
pytest tests/test_database.py -v

# Run Policy System tests
pytest tests/test_policy_*.py --cov=walnut.policy -v

# Run with coverage
pytest --cov=walnut tests/
```

### Code Quality

```bash
# Format code
black walnut/ tests/
isort walnut/ tests/

# Lint code
ruff walnut/ tests/

# Type checking
mypy walnut/
```

## Architecture

### Core Services
```
walnut/core/
├── services.py        # Service lifecycle management
└── __init__.py
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
├── engine.py          # SQLCipher engine with WAL mode
├── models.py          # SQLAlchemy table definitions  
├── connection.py      # Connection pooling and management
└── __init__.py
```

### CLI Layer

```
walnut/cli/
├── database.py        # Database management commands
└── __init__.py
```

### Migration System

```
alembic/
├── env.py             # Alembic environment configuration
├── versions/          # Database migration files
└── script.py.mako     # Migration template
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
    'Authorization': 'Bearer ' + token,
    'X-CSRF-Token': 'any-value-works'  // Header presence is validated, not content
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
- **API Access**: All `/api/*` endpoints require `X-CSRF-Token` header for POST/PUT/PATCH/DELETE
- **WebSocket Auth**: WebSocket connections authenticate via query parameter, no CSRF needed
- **Header Validation**: Only header presence is checked, any value works

### Example Integration

```javascript
// Complete login and API access flow
async function loginAndFetchData() {
  // 1. Login (no CSRF required)
  const loginResponse = await fetch('/auth/jwt/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'username=user&password=pass'
  });
  
  const { access_token } = await loginResponse.json();
  
  // 2. API call (CSRF required)
  const dataResponse = await fetch('/api/me', {
    headers: {
      'Authorization': `Bearer ${access_token}`,
      'X-CSRF-Token': 'required'  // Any value works
    }
  });
  
  return await dataResponse.json();
}
```

## Security Considerations

1. **Master Key Security**: Store the master key securely using environment variables or Docker secrets
2. **Local Storage Only**: Database validation prevents network filesystem usage
3. **Encrypted Credentials**: All sensitive data stored with SQLCipher encryption
4. **Connection Timeouts**: Prevent connection hanging with busy timeouts
5. **CSRF Protection**: State-changing API endpoints require X-CSRF-Token header
6. **Authentication**: JWT-based authentication with separate login/API token requirements

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