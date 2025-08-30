# walNUT Policy System - Testing Guide

This document provides comprehensive instructions for running the test suite for the walNUT Policy System, including unit tests, integration tests, E2E UI tests, and performance tests.

## Overview

The Policy System test suite includes:

- **Unit Tests**: Selector parsing, compilation pipeline, severity mapping, inverse registry
- **Integration Tests**: API endpoints, CRUD operations, dry-run functionality
- **Driver Preflight Tests**: Proxmox and AOS-S driver dry-run depth testing
- **Performance & Concurrency Tests**: Load testing, suppression windows, resource management
- **E2E UI Tests**: Policy wizard, validation UX, inverse creation (Playwright)

## Prerequisites

### Environment Setup

1. **Python Virtual Environment**:
   ```bash
   # Create and activate venv (if not already done)
   python3 -m venv venv
   source venv/bin/activate  # Linux/macOS
   # venv\Scripts\activate   # Windows

   # Install dependencies
   pip install -r requirements.txt
   ```

2. **Required Environment Variables**:
   ```bash
   # Database encryption key (32+ characters)
   export WALNUT_DB_KEY="test_key_32_characters_minimum_length"
   
   # JWT signing secret (32+ characters)
   export WALNUT_JWT_SECRET="test_jwt_secret_32_characters_long_12345"
   
   # CSRF and CORS configuration for testing
   export WALNUT_SECURE_COOKIES=false
   export WALNUT_ALLOWED_ORIGINS='["http://localhost:3000"]'
   
   # Enable Policy v1 system for advanced tests
   export WALNUT_POLICY_V1_ENABLED=true
   ```

3. **Database Initialization**:
   ```bash
   # Reset and initialize test database
   ./venv/bin/python -m walnut.cli.main db reset --yes
   ./venv/bin/python -m walnut.cli.main db init
   
   # Verify database health
   ./venv/bin/python -m walnut.cli.main db health
   ```

4. **Create Admin User**:
   ```bash
   # Create admin user for authentication tests
   ./venv/bin/python -m walnut.cli.main auth create-admin \
     --email admin@test.com --password testpass
   ```

## Running Tests

### Unit Tests

Test individual components in isolation:

```bash
# Selector parsing tests (VM ranges, port selectors, validation)
./venv/bin/python -m pytest tests/test_policy_selector_parser.py -v

# Compilation pipeline tests (IR generation, hashing, errors)
./venv/bin/python -m pytest tests/test_policy_compile_pipeline.py -v

# Severity mapping tests (info/warn/error/blocker transitions)
./venv/bin/python -m pytest tests/test_policy_severity_mapping.py -v

# Inverse registry tests (capability inversions, non-invertible actions)
./venv/bin/python -m pytest tests/test_policy_inverse_registry.py -v
```

### Integration Tests

Test API endpoints and full system integration:

```bash
# API validation endpoint tests
./venv/bin/python -m pytest tests/test_policy_api_integration.py::TestValidateEndpoint -v

# CRUD operations (create, read, update, delete policies)
./venv/bin/python -m pytest tests/test_policy_api_integration.py::TestPolicyCRUDOperations -v

# Dry-run endpoint tests
./venv/bin/python -m pytest tests/test_policy_api_integration.py::TestDryRunEndpoint -v

# Execution history and ledger
./venv/bin/python -m pytest tests/test_policy_api_integration.py::TestExecutionsLedger -v
```

### Driver Preflight Tests

Test driver dry-run capabilities and preflight depth:

```bash
# Proxmox driver preflight tests
./venv/bin/python -m pytest tests/test_policy_driver_preflight.py::TestProxmoxDriverPreflight -v

# AOS-S driver preflight tests  
./venv/bin/python -m pytest tests/test_policy_driver_preflight.py::TestAOSSDriverPreflight -v

# Edge cases and error conditions
./venv/bin/python -m pytest tests/test_policy_driver_preflight.py::TestDriverPreflightEdgeCases -v
```

### Performance & Concurrency Tests

Test system behavior under load and concurrent operations:

```bash
# Concurrent execution tests
./venv/bin/python -m pytest tests/test_policy_performance_concurrency.py::TestConcurrentExecution -v

# Suppression and idempotency window tests
./venv/bin/python -m pytest tests/test_policy_performance_concurrency.py::TestSuppressionAndIdempotency -v

# Performance under load tests
./venv/bin/python -m pytest tests/test_policy_performance_concurrency.py::TestPerformanceUnderLoad -v

# Memory and resource management tests
./venv/bin/python -m pytest tests/test_policy_performance_concurrency.py::TestMemoryAndResourceManagement -v
```

### All Policy Tests with Coverage

Run all policy-related tests with coverage reporting:

```bash
# Full test suite with coverage
./venv/bin/python -m pytest tests/test_policy_*.py \
  --cov=walnut.policy --cov=walnut.inventory \
  --cov-report=term-missing --cov-report=html -v

# Coverage report will be available in htmlcov/index.html
```

## E2E UI Tests (Playwright)

For end-to-end UI testing, you need both backend and frontend running:

### Setup for E2E Tests

1. **Start Backend Server**:
   ```bash
   ./venv/bin/uvicorn walnut.app:app --host 0.0.0.0 --port 8000 --reload
   ```

2. **Start Frontend Development Server**:
   ```bash
   cd frontend
   npm install  # if not already done
   npm run dev  # starts on http://localhost:3000
   ```

3. **E2E Test Scenarios**:
   
   **Login Flow**:
   - Navigate to http://localhost:3000
   - Login with admin@test.com / testpass
   - Verify JWT token and CSRF headers are set

   **Policy Creation Wizard**:
   - Navigate to Policies → Create New Policy
   - Fill out: Basics → Triggers → Conditions → Targets → Actions
   - Test validation with schema/compile errors
   - Save & Enable policy

   **Inverse Policy Creation**:
   - Select existing policy → "Create Inverse"
   - Verify fields are flipped (shutdown → start)
   - Check needs_input prompts for timer schedules
   - Save as disabled until user completes required fields

   **Validation Console**:
   - Create policy with various error types
   - Verify Schema/Compile/Preflight sections render
   - Check severity chips (info/warn/error/blocker)

## Test Configuration Notes

### Database Testing

- Tests use encrypted SQLCipher database with test key
- Database is reset before test runs to ensure clean state
- Test data is automatically cleaned up after tests

### CSRF Token Handling

For API tests that require CSRF protection:

```bash
# Disable CSRF for testing (already set in env vars above)
export WALNUT_SECURE_COOKIES=false
```

For E2E tests with CSRF enabled, the frontend automatically handles CSRF token headers.

### Integration Mocking

Integration tests use mocks for:
- **Driver Managers**: Mock Proxmox/AOS-S responses
- **Inventory Index**: Mock target discovery and capabilities
- **External Services**: Mock integrations to avoid external dependencies

### Performance Test Thresholds

Performance tests validate:
- **Event Processing**: >10 events/second minimum
- **Concurrent Execution**: Proper serialization per host
- **Memory Usage**: <50MB increase under load
- **Response Time**: API endpoints <2s for dry-run operations

## Troubleshooting

### Common Issues

1. **Database Connection Errors**:
   ```bash
   # Check database key length
   echo $WALNUT_DB_KEY | wc -c  # Should be 33+ characters
   
   # Reset database if corrupted
   rm -f data/walnut.db*
   ./venv/bin/python -m walnut.cli.main db init
   ```

2. **Import Errors in Tests**:
   ```bash
   # Ensure policy v1 system is enabled for advanced tests
   export WALNUT_POLICY_V1_ENABLED=true
   
   # Check Python path
   export PYTHONPATH=$PWD:$PYTHONPATH
   ```

3. **Frontend Connection Issues**:
   ```bash
   # Verify backend is running
   curl http://localhost:8000/health
   
   # Check CORS configuration
   echo $WALNUT_ALLOWED_ORIGINS
   ```

4. **Test Coverage Issues**:
   ```bash
   # Install coverage if missing
   pip install pytest-cov
   
   # Run with verbose coverage
   ./venv/bin/python -m pytest --cov-config=.coveragerc \
     --cov=walnut --cov-report=term-missing tests/
   ```

### Test Data Cleanup

Tests automatically clean up, but for manual cleanup:

```bash
# Clear test database
./venv/bin/python -m walnut.cli.main db reset --yes

# Clear any background processes
pkill -f uvicorn
pkill -f "npm run dev"
```

## Continuous Integration

For CI/CD pipelines, use this test script:

```bash
#!/bin/bash
set -e

# Setup environment
export WALNUT_DB_KEY="ci_test_key_32_characters_minimum_length"
export WALNUT_JWT_SECRET="ci_jwt_secret_32_characters_long_test_key"
export WALNUT_SECURE_COOKIES=false
export WALNUT_POLICY_V1_ENABLED=true

# Initialize database
./venv/bin/python -m walnut.cli.main db reset --yes
./venv/bin/python -m walnut.cli.main db init

# Create admin user
./venv/bin/python -m walnut.cli.main auth create-admin \
  --email ci@test.com --password cipass

# Run test suite
./venv/bin/python -m pytest tests/test_policy_*.py \
  --cov=walnut.policy --cov=walnut.inventory \
  --cov-report=xml --cov-report=term \
  --junitxml=test-results.xml \
  -v

# Check coverage threshold (90%+)
coverage report --fail-under=90
```

## Coverage Goals

Target coverage levels:
- **walnut.policy.***: >90%
- **walnut.inventory.***: >85%
- **Policy API endpoints**: >95%
- **Overall system**: >80%

Current coverage status can be viewed in the HTML report: `htmlcov/index.html`

---

For questions about testing or to report test issues, please see the main project README or create an issue in the repository.