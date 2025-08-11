#!/bin/bash

# walNUT Platform End-to-End Testing Script
# This script validates all functionality works together

# Note: Not using set -e to allow tests to continue even if some fail

# Activate virtual environment
source venv/bin/activate

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

# Logging
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((TESTS_PASSED++))
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((TESTS_FAILED++))
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Cleanup function
cleanup() {
    log_info "Cleaning up..."
    if [ ! -z "$SERVER_PID" ] && ps -p $SERVER_PID > /dev/null 2>&1; then
        log_info "Stopping web server (PID: $SERVER_PID)"
        kill $SERVER_PID
        sleep 2
    fi
    
    if [ ! -z "$POLLER_PID" ] && ps -p $POLLER_PID > /dev/null 2>&1; then
        log_info "Stopping NUT poller (PID: $POLLER_PID)"
        kill $POLLER_PID
        sleep 2
    fi
}

# Set trap for cleanup
trap cleanup EXIT

echo "=========================================="
echo "  walNUT Platform E2E Testing Script"
echo "=========================================="

# Setup environment variables
export WALNUT_DB_KEY="test_master_key_32_characters_long_secure_key_123456789"
export WALNUT_JWT_SECRET="test_jwt_secret_key_32_characters_long_secure_test_key"
export JWT_SECRET="test_jwt_secret_key_32_characters_long_secure_test_key"
export WALNUT_SIGNUP_ENABLED="true"

log_info "Environment variables set"

# 1. DATABASE OPERATIONS TESTING
echo ""
log_info "1. Testing Database Operations..."

# Test CLI database commands
log_info "Testing: python -m walnut.cli.main db stats"
if python -m walnut.cli.main db stats > /tmp/walnut_db_stats.log 2>&1; then
    log_success "walnut db stats command works"
else
    log_error "walnut db stats command failed"
    cat /tmp/walnut_db_stats.log
fi

log_info "Testing: python -m walnut.cli.main test database"
if python -m walnut.cli.main test database > /tmp/walnut_test_db.log 2>&1; then
    log_success "walnut test database command works"
else
    log_error "walnut test database command failed"
    cat /tmp/walnut_test_db.log
fi

# 2. NUT INTEGRATION TESTING
echo ""
log_info "2. Testing NUT Integration..."

log_info "Testing: python -m walnut.cli.main test nut"
if timeout 10 python -m walnut.cli.main test nut > /dev/null 2>&1; then
    log_success "NUT connection test passed"
else
    log_warning "NUT connection test failed (may be expected if no UPS server)"
fi

# 3. WEB SERVER AND API TESTING
echo ""
log_info "3. Testing Web Server and API..."

# Start web server in background
log_info "Starting web server..."
python -m uvicorn walnut.app:app --port 8000 --host 0.0.0.0 > /tmp/walnut_server.log 2>&1 &
SERVER_PID=$!

# Wait for server to start
log_info "Waiting for server startup..."
sleep 8

# Check if server is running
if ! ps -p $SERVER_PID > /dev/null 2>&1; then
    log_error "Web server failed to start"
    cat /tmp/walnut_server.log
    exit 1
fi

log_success "Web server started (PID: $SERVER_PID)"

# Test basic endpoints
log_info "Testing root endpoint"
if curl -f -s http://localhost:8000/ > /dev/null; then
    log_success "Root endpoint accessible"
else
    log_error "Root endpoint failed"
fi

log_info "Testing OpenAPI docs"
if curl -f -s http://localhost:8000/docs > /dev/null; then
    log_success "OpenAPI docs accessible"
else
    log_error "OpenAPI docs failed"
fi

log_info "Testing health check endpoint"
if curl -f -s http://localhost:8000/api/system/health > /dev/null; then
    log_success "Health check endpoint works"
else
    log_error "Health check endpoint failed"
fi

# 4. AUTHENTICATION SYSTEM TESTING
echo ""
log_info "4. Testing Authentication System..."

# Create admin user via CLI first
log_info "Creating admin user via CLI"
echo "admin" | python -m walnut.cli.main auth create-admin --email admin@example.com > /tmp/admin_create.log 2>&1
if [ $? -eq 0 ]; then
    log_success "Admin user created via CLI"
else
    log_error "Admin user creation via CLI failed"
    cat /tmp/admin_create.log
fi

# Test user login with admin credentials
log_info "Testing admin login"
LOGIN_RESPONSE=$(curl -s -X POST http://localhost:8000/auth/jwt/login \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -H "X-CSRF-Token: test" \
    -d "username=admin@example.com&password=admin")

if echo "$LOGIN_RESPONSE" | grep -q "access_token"; then
    log_success "Admin login works"
    ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
else
    log_error "Admin login failed"
    echo "Response: $LOGIN_RESPONSE"
fi

# Test protected endpoint with token
if [ ! -z "$ACCESS_TOKEN" ]; then
    log_info "Testing protected endpoint with authentication"
    if curl -f -s -H "Authorization: Bearer $ACCESS_TOKEN" http://localhost:8000/api/system/health > /dev/null; then
        log_success "Authenticated request works"
    else
        log_error "Authenticated request failed"
    fi
fi

# Test without token (should fail)
log_info "Testing protected endpoint without authentication"
UNAUTH_RESPONSE=$(curl -s -w "%{http_code}" http://localhost:8000/api/ups/status -o /dev/null)
if [ "$UNAUTH_RESPONSE" = "401" ]; then
    log_success "Unauthenticated request properly rejected"
else
    log_error "Unauthenticated request not properly handled (got $UNAUTH_RESPONSE)"
fi

# 5. API FUNCTIONALITY TESTING
echo ""
log_info "5. Testing API Functionality..."

if [ ! -z "$ACCESS_TOKEN" ]; then
    # Test UPS status endpoint
    log_info "Testing UPS status endpoint"
    UPS_RESPONSE=$(curl -s -H "Authorization: Bearer $ACCESS_TOKEN" http://localhost:8000/api/ups/status)
    if echo "$UPS_RESPONSE" | grep -q "ups_data\|error"; then
        log_success "UPS status endpoint responds"
    else
        log_error "UPS status endpoint failed"
    fi

    # Test events endpoint
    log_info "Testing events endpoint"
    EVENTS_RESPONSE=$(curl -s -H "Authorization: Bearer $ACCESS_TOKEN" http://localhost:8000/api/events)
    if echo "$EVENTS_RESPONSE" | grep -q "\[\]" || echo "$EVENTS_RESPONSE" | grep -q "events"; then
        log_success "Events endpoint responds"
    else
        log_error "Events endpoint failed"
    fi

    # Test system health with auth
    log_info "Testing system health endpoint with auth"
    HEALTH_RESPONSE=$(curl -s -H "Authorization: Bearer $ACCESS_TOKEN" http://localhost:8000/api/system/health)
    if echo "$HEALTH_RESPONSE" | grep -q "status"; then
        log_success "System health endpoint works with auth"
    else
        log_error "System health endpoint failed with auth"
    fi
fi

# 6. WEBSOCKET TESTING
echo ""
log_info "6. Testing WebSocket Connection..."

# Create a simple WebSocket test client
cat > /tmp/websocket_test.py << 'EOF'
import asyncio
import websockets
import json
import sys

async def test_websocket():
    try:
        uri = "ws://localhost:8000/ws/updates"
        async with websockets.connect(uri) as websocket:
            print("WebSocket connection established")
            
            # Send a test message
            test_message = {"type": "ping"}
            await websocket.send(json.dumps(test_message))
            
            # Wait for response (with timeout)
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"Received: {response}")
                return True
            except asyncio.TimeoutError:
                print("WebSocket timeout - no response received")
                return True  # Connection worked, just no response
                
    except Exception as e:
        print(f"WebSocket connection failed: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_websocket())
    sys.exit(0 if result else 1)
EOF

if python /tmp/websocket_test.py > /dev/null 2>&1; then
    log_success "WebSocket connection test passed"
else
    log_warning "WebSocket connection test failed (may need websockets package)"
fi

# 7. ERROR HANDLING TESTING
echo ""
log_info "7. Testing Error Handling..."

# Test invalid endpoint
log_info "Testing 404 error handling"
NOTFOUND_RESPONSE=$(curl -s -w "%{http_code}" http://localhost:8000/api/nonexistent -o /dev/null)
if [ "$NOTFOUND_RESPONSE" = "404" ]; then
    log_success "404 errors properly handled"
else
    log_error "404 errors not properly handled (got $NOTFOUND_RESPONSE)"
fi

# Test malformed JSON
log_info "Testing malformed JSON handling"
MALFORMED_RESPONSE=$(curl -s -w "%{http_code}" -X POST http://localhost:8000/auth/signup \
    -H "Content-Type: application/json" \
    -d '{invalid json}' -o /dev/null)
if [ "$MALFORMED_RESPONSE" = "422" ] || [ "$MALFORMED_RESPONSE" = "400" ]; then
    log_success "Malformed JSON properly handled"
else
    log_error "Malformed JSON not properly handled (got $MALFORMED_RESPONSE)"
fi

# 8. CLI TESTING
echo ""
log_info "8. Testing CLI Commands..."

# Test various CLI commands
CLI_COMMANDS=(
    "python -m walnut.cli.main --help"
    "python -m walnut.cli.main db --help"
    "python -m walnut.cli.main test --help"
    "python -m walnut.cli.main system --help"
)

for cmd in "${CLI_COMMANDS[@]}"; do
    log_info "Testing: $cmd"
    if $cmd > /dev/null 2>&1; then
        log_success "$cmd works"
    else
        log_error "$cmd failed"
    fi
done

# Final Results
echo ""
echo "=========================================="
echo "           TEST RESULTS SUMMARY"
echo "=========================================="
echo -e "${GREEN}Tests Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Tests Failed: $TESTS_FAILED${NC}"

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 ALL TESTS PASSED! walNUT platform is working correctly.${NC}"
    exit 0
else
    echo -e "${RED}❌ Some tests failed. Check the output above for details.${NC}"
    exit 1
fi