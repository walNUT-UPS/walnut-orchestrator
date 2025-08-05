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

## Quick Start

### Prerequisites

- Python 3.12+
- SQLCipher development libraries
- Master encryption key (32+ characters)

### Installation

```bash
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

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run database tests only
pytest tests/test_database.py -v

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

## Security Considerations

1. **Master Key Security**: Store the master key securely using environment variables or Docker secrets
2. **Local Storage Only**: Database validation prevents network filesystem usage
3. **Encrypted Credentials**: All sensitive data stored with SQLCipher encryption
4. **Connection Timeouts**: Prevent connection hanging with busy timeouts

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
