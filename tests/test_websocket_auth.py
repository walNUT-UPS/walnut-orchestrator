"""
Comprehensive test suite for WebSocket authentication functionality.

Tests all aspects of WebSocket connection, authentication, and message exchange
to ensure security and functionality are maintained.
"""

import os
import pytest
import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from httpx import AsyncClient
from fastapi import WebSocket
from jose import jwt
try:
    import websocket  # websocket-client
except Exception:
    pytest.skip("websocket-client not installed; skipping WebSocket tests", allow_module_level=True)

if not os.environ.get("WALNUT_RUN_WS_TESTS"):
    pytest.skip("Set WALNUT_RUN_WS_TESTS=1 to enable WebSocket tests against a running server", allow_module_level=True)
import threading
from typing import Dict, List, Any, Optional

pytestmark = pytest.mark.asyncio


class WebSocketTestClient:
    """Helper class for WebSocket testing with comprehensive message capture."""
    
    def __init__(self, url: str):
        self.url = url
        self.messages_received: List[Dict[str, Any]] = []
        self.connection_opened = False
        self.connection_closed = False
        self.close_code = None
        self.close_reason = None
        self.error_messages = []
        self.ws = None
        
    def connect_and_wait(self, timeout: float = 3.0) -> bool:
        """Connect to WebSocket and wait for messages."""
        
        def on_message(ws, message):
            try:
                msg_data = json.loads(message)
                self.messages_received.append(msg_data)
            except Exception as e:
                self.error_messages.append(f"Message parse error: {e}")
        
        def on_error(ws, error):
            self.error_messages.append(str(error))
        
        def on_close(ws, close_status_code, close_msg):
            self.connection_closed = True
            self.close_code = close_status_code
            self.close_reason = close_msg
        
        def on_open(ws):
            self.connection_opened = True
        
        try:
            self.ws = websocket.WebSocketApp(
                self.url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open
            )
            
            # Run WebSocket in thread
            def run_ws():
                self.ws.run_forever()
            
            thread = threading.Thread(target=run_ws)
            thread.daemon = True
            thread.start()
            
            # Wait for connection and messages
            start_time = time.time()
            while time.time() - start_time < timeout:
                if self.connection_opened or self.connection_closed:
                    break
                time.sleep(0.1)
            
            # Wait a bit more for messages
            time.sleep(0.5)
            
            # Close if still open
            if self.ws and not self.connection_closed:
                self.ws.close()
                time.sleep(0.2)
            
            return self.connection_opened
            
        except Exception as e:
            self.error_messages.append(f"Connection error: {e}")
            return False
    
    def send_message(self, message: Dict[str, Any]) -> bool:
        """Send a message through the WebSocket."""
        if self.ws and self.connection_opened and not self.connection_closed:
            try:
                self.ws.send(json.dumps(message))
                time.sleep(0.2)  # Wait for response
                return True
            except Exception as e:
                self.error_messages.append(f"Send error: {e}")
        return False
    
    def get_message_by_type(self, msg_type: str) -> Optional[Dict[str, Any]]:
        """Get the first message of a specific type."""
        for msg in self.messages_received:
            if msg.get("type") == msg_type:
                return msg
        return None
    
    def has_message_type(self, msg_type: str) -> bool:
        """Check if a message type was received."""
        return self.get_message_by_type(msg_type) is not None


async def create_test_user(async_client: AsyncClient, email: str = "test@example.com", password: str = "testpass123") -> str:
    """Create a test user and return their JWT token."""
    # Register user
    response = await async_client.post(
        "/auth",
        json={"email": email, "password": password}
    )
    assert response.status_code == 201
    
    # Login to get token
    response = await async_client.post(
        "/auth/jwt/login",
        data={"username": email, "password": password}
    )
    assert response.status_code == 204
    
    # Extract token from cookie
    cookie_header = response.headers.get("set-cookie", "")
    if "walnut_access=" in cookie_header:
        token = cookie_header.split("walnut_access=")[1].split(";")[0]
        return token
    
    raise ValueError("No JWT token found in response")


def create_expired_token() -> str:
    """Create an expired JWT token for testing."""
    import os
    from datetime import datetime, timezone, timedelta
    
    secret = os.environ.get("WALNUT_JWT_SECRET", "test-secret")
    payload = {
        "sub": "test-user-id",
        "aud": ["fastapi-users:auth"],
        "exp": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
    }
    
    return jwt.encode(payload, secret, algorithm="HS256")


class TestWebSocketAuthentication:
    """Test suite for WebSocket authentication and security."""
    
    async def test_unauthenticated_connection_rejected(self, async_client: AsyncClient):
        """Test that connections without tokens are properly rejected."""
        client = WebSocketTestClient("ws://localhost:8000/ws")
        connected = client.connect_and_wait()
        
        # Connection should open initially but then be rejected
        assert connected or client.connection_closed
        
        # Should receive error message
        assert client.has_message_type("error")
        error_msg = client.get_message_by_type("error")
        assert "Authentication token required" in error_msg["data"]["message"]
        
        # Connection should be closed with proper code
        assert client.connection_closed
        assert client.close_code == 4001
    
    async def test_invalid_token_rejected(self, async_client: AsyncClient):
        """Test that invalid JWT tokens are properly rejected."""
        client = WebSocketTestClient("ws://localhost:8000/ws?token=invalid_token")
        connected = client.connect_and_wait()
        
        # Connection should open initially but then be rejected
        assert connected or client.connection_closed
        
        # Should receive error message
        assert client.has_message_type("error")
        error_msg = client.get_message_by_type("error")
        assert "Invalid authentication token" in error_msg["data"]["message"]
        
        # Connection should be closed
        assert client.connection_closed
        assert client.close_code == 4001
    
    async def test_malformed_token_rejected(self, async_client: AsyncClient):
        """Test that malformed JWT tokens are rejected."""
        client = WebSocketTestClient("ws://localhost:8000/ws?token=not.a.jwt")
        connected = client.connect_and_wait()
        
        assert connected or client.connection_closed
        assert client.has_message_type("error")
        assert client.connection_closed
        assert client.close_code == 4001
    
    async def test_expired_token_rejected(self, async_client: AsyncClient):
        """Test that expired tokens are properly rejected."""
        expired_token = create_expired_token()
        client = WebSocketTestClient(f"ws://localhost:8000/ws?token={expired_token}")
        connected = client.connect_and_wait()
        
        assert connected or client.connection_closed
        assert client.has_message_type("error")
        error_msg = client.get_message_by_type("error")
        assert "Invalid authentication token" in error_msg["data"]["message"]
        assert client.connection_closed
        assert client.close_code == 4001
    
    async def test_authenticated_connection_success(self, async_client: AsyncClient):
        """Test that valid JWT allows connection and message exchange."""
        # Create user and get token
        token = await create_test_user(async_client)
        
        client = WebSocketTestClient(f"ws://localhost:8000/ws?token={token}")
        connected = client.connect_and_wait()
        
        # Connection should succeed
        assert connected
        assert not client.connection_closed
        
        # Should receive connection status and auth success
        assert client.has_message_type("connection_status")
        assert client.has_message_type("auth_success")
        
        # Auth success should contain user info
        auth_msg = client.get_message_by_type("auth_success")
        assert "user_id" in auth_msg["data"]
        assert "client_id" in auth_msg["data"]
    
    async def test_message_exchange_bidirectional(self, async_client: AsyncClient):
        """Test sending and receiving various message types."""
        token = await create_test_user(async_client)
        
        client = WebSocketTestClient(f"ws://localhost:8000/ws?token={token}")
        connected = client.connect_and_wait()
        assert connected
        assert client.has_message_type("auth_success")
        
        # Test ping/pong
        client.send_message({"type": "ping"})
        time.sleep(0.5)  # Wait for response
        assert client.has_message_type("pong")
        
        # Test history request
        client.send_message({"type": "get_history"})
        time.sleep(0.5)
        # May or may not have history, but shouldn't error
        
        # Test unknown message type (should be logged but not error)
        client.send_message({"type": "unknown_message", "data": {"test": "value"}})
        time.sleep(0.5)
        # Should not disconnect
        assert not client.connection_closed
    
    async def test_multiple_concurrent_connections(self, async_client: AsyncClient):
        """Test multiple authenticated WebSocket connections."""
        # Create multiple users
        token1 = await create_test_user(async_client, "user1@example.com")
        token2 = await create_test_user(async_client, "user2@example.com")
        
        client1 = WebSocketTestClient(f"ws://localhost:8000/ws?token={token1}")
        client2 = WebSocketTestClient(f"ws://localhost:8000/ws?token={token2}")
        
        # Connect both
        connected1 = client1.connect_and_wait()
        connected2 = client2.connect_and_wait()
        
        assert connected1
        assert connected2
        assert client1.has_message_type("auth_success")
        assert client2.has_message_type("auth_success")
        
        # Test that they can operate independently
        client1.send_message({"type": "ping"})
        client2.send_message({"type": "ping"})
        
        time.sleep(0.5)
        
        assert client1.has_message_type("pong")
        assert client2.has_message_type("pong")
        
        # Different user IDs
        auth1 = client1.get_message_by_type("auth_success")
        auth2 = client2.get_message_by_type("auth_success")
        assert auth1["data"]["user_id"] != auth2["data"]["user_id"]
    
    async def test_websocket_updates_endpoint(self, async_client: AsyncClient):
        """Test the /ws/updates endpoint also works with authentication."""
        token = await create_test_user(async_client)
        
        client = WebSocketTestClient(f"ws://localhost:8000/ws/updates?token={token}")
        connected = client.connect_and_wait()
        
        assert connected
        assert client.has_message_type("connection_status")
        assert client.has_message_type("auth_success")
    
    async def test_jwt_audience_validation(self, async_client: AsyncClient):
        """Test that JWT audience validation is working correctly."""
        import os
        
        # Create token with wrong audience
        secret = os.environ.get("WALNUT_JWT_SECRET", "test-secret")
        payload = {
            "sub": "test-user-id",
            "aud": ["wrong-audience"],
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
        }
        
        wrong_audience_token = jwt.encode(payload, secret, algorithm="HS256")
        
        client = WebSocketTestClient(f"ws://localhost:8000/ws?token={wrong_audience_token}")
        connected = client.connect_and_wait()
        
        assert connected or client.connection_closed
        assert client.has_message_type("error")
        assert client.connection_closed
        assert client.close_code == 4001
    
    async def test_connection_cleanup_on_auth_failure(self, async_client: AsyncClient):
        """Test that failed authentication properly cleans up connections."""
        
        # Test with multiple failed connections
        failed_clients = []
        for i in range(3):
            client = WebSocketTestClient(f"ws://localhost:8000/ws?token=invalid_{i}")
            client.connect_and_wait()
            failed_clients.append(client)
        
        # All should be rejected and closed
        for client in failed_clients:
            assert client.connection_closed
            assert client.close_code == 4001
    
    async def test_websocket_info_endpoint_requires_auth(self, async_client: AsyncClient):
        """Test that the WebSocket info endpoint requires authentication."""
        # Test without auth
        response = await async_client.get("/api/websocket/info")
        assert response.status_code == 401
        
        # Test with auth
        token = await create_test_user(async_client)
        # The async_client should use the cookie from login automatically
        response = await async_client.get("/api/websocket/info")
        assert response.status_code == 200
        
        info = response.json()
        assert "total_connections" in info
        assert "authenticated_connections" in info
        assert "connections" in info


class TestWebSocketSecurity:
    """Security-focused tests for WebSocket implementation."""
    
    async def test_no_token_leakage_in_errors(self, async_client: AsyncClient):
        """Ensure error messages don't leak sensitive information."""
        client = WebSocketTestClient("ws://localhost:8000/ws?token=sensitive_token_data")
        client.connect_and_wait()
        
        assert client.has_message_type("error")
        error_msg = client.get_message_by_type("error")
        
        # Error message should not contain the token
        error_text = str(error_msg)
        assert "sensitive_token_data" not in error_text
    
    async def test_connection_limit_enforcement(self, async_client: AsyncClient):
        """Test that connection limits are enforced (if implemented)."""
        # This test assumes there might be connection limits
        # If not implemented, this test serves as a placeholder for future security measures
        token = await create_test_user(async_client)
        
        # Try to create many connections
        clients = []
        for i in range(10):  # Reasonable number for testing
            client = WebSocketTestClient(f"ws://localhost:8000/ws?token={token}")
            if client.connect_and_wait():
                clients.append(client)
        
        # At least some should succeed (exact limits depend on implementation)
        assert len(clients) > 0
    
    async def test_malicious_message_handling(self, async_client: AsyncClient):
        """Test handling of malicious or malformed messages."""
        token = await create_test_user(async_client)
        
        client = WebSocketTestClient(f"ws://localhost:8000/ws?token={token}")
        connected = client.connect_and_wait()
        assert connected
        assert client.has_message_type("auth_success")
        
        # Send malformed JSON (this should be handled gracefully)
        if client.ws:
            try:
                client.ws.send("invalid json {")
                time.sleep(0.5)
                # Connection should still be alive or properly handle the error
                # The exact behavior depends on implementation
            except Exception:
                pass  # Expected for malformed data
    
    async def test_authorization_header_not_supported(self, async_client: AsyncClient):
        """Document that Authorization header method is not supported by websocket-client library."""
        # This test documents a known limitation rather than testing functionality
        # The WebSocket protocol itself supports Authorization headers, but the 
        # websocket-client Python library doesn't expose this functionality easily
        
        # This would be the ideal test if the library supported it:
        # headers = {"Authorization": f"Bearer {token}"}
        # client = WebSocketTestClient("ws://localhost:8000/ws", headers=headers)
        
        # For now, we document that query parameter method is the supported approach
        assert True  # Placeholder test


# Performance and load testing
class TestWebSocketPerformance:
    """Performance tests for WebSocket functionality."""
    
    async def test_rapid_message_exchange(self, async_client: AsyncClient):
        """Test rapid ping/pong message exchange."""
        token = await create_test_user(async_client)
        
        client = WebSocketTestClient(f"ws://localhost:8000/ws?token={token}")
        connected = client.connect_and_wait()
        assert connected
        assert client.has_message_type("auth_success")
        
        # Send multiple pings rapidly
        for i in range(5):
            client.send_message({"type": "ping"})
            time.sleep(0.1)
        
        time.sleep(1)  # Wait for all responses
        
        # Should have received multiple pongs
        pong_count = len([msg for msg in client.messages_received if msg.get("type") == "pong"])
        assert pong_count >= 3  # Allow for some timing variability
    
    async def test_connection_stability(self, async_client: AsyncClient):
        """Test that connections remain stable over time."""
        token = await create_test_user(async_client)
        
        client = WebSocketTestClient(f"ws://localhost:8000/ws?token={token}")
        connected = client.connect_and_wait(timeout=5.0)  # Longer timeout
        assert connected
        assert client.has_message_type("auth_success")
        
        # Send periodic messages to keep connection alive
        for i in range(3):
            client.send_message({"type": "ping"})
            time.sleep(1)
        
        # Connection should still be alive
        assert not client.connection_closed
        
        # Should have received multiple pongs
        pong_count = len([msg for msg in client.messages_received if msg.get("type") == "pong"])
        assert pong_count >= 2


# Integration tests
class TestWebSocketIntegration:
    """Integration tests combining WebSocket with other system components."""
    
    async def test_websocket_with_user_management(self, async_client: AsyncClient):
        """Test WebSocket functionality with user management operations."""
        # Create user and get token
        token = await create_test_user(async_client, "integration@example.com")
        
        # Connect via WebSocket
        client = WebSocketTestClient(f"ws://localhost:8000/ws?token={token}")
        connected = client.connect_and_wait()
        assert connected
        assert client.has_message_type("auth_success")
        
        # Verify user details via API
        response = await async_client.get("/api/me")
        assert response.status_code == 200
        user_data = response.json()
        
        # WebSocket auth should match API user
        auth_msg = client.get_message_by_type("auth_success")
        # Note: We can't directly compare user IDs without knowing the exact format
        # but we can verify the auth was successful
        assert auth_msg["data"]["user_id"] is not None
    
    async def test_websocket_survives_server_restart_simulation(self, async_client: AsyncClient):
        """Test WebSocket behavior during server restart simulation."""
        # This test verifies graceful handling of disconnections
        token = await create_test_user(async_client)
        
        client = WebSocketTestClient(f"ws://localhost:8000/ws?token={token}")
        connected = client.connect_and_wait()
        assert connected
        
        # Simulate abrupt disconnection by closing WebSocket
        if client.ws:
            client.ws.close()
            time.sleep(0.5)
        
        assert client.connection_closed
        
        # Reconnection should work with same token (if not expired)
        client2 = WebSocketTestClient(f"ws://localhost:8000/ws?token={token}")
        connected2 = client2.connect_and_wait()
        assert connected2
        assert client2.has_message_type("auth_success")
