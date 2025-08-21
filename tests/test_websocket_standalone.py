"""
Standalone WebSocket authentication tests that don't rely on conftest.py fixtures.

These tests run against a live server and validate WebSocket authentication functionality.
Run with: pytest tests/test_websocket_standalone.py -v
Requires: walNUT server running on localhost:8000
"""

import pytest
import json
import time
import subprocess
import websocket
import threading
from typing import Dict, List, Any, Optional


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


def get_valid_jwt_token() -> str:
    """Get a valid JWT token by logging in with existing admin user."""
    # Use the admin user that should already exist (created in manual testing)
    cmd = [
        "curl", "-s", "-X", "POST", "http://localhost:8000/auth/jwt/login",
        "-H", "Content-Type: application/x-www-form-urlencoded",
        "-d", "username=test@example.com&password=testpass123",
        "-v"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Extract token from set-cookie header
    for line in result.stderr.split('\n'):
        if 'set-cookie: walnut_access=' in line:
            token = line.split('walnut_access=')[1].split(';')[0]
            return token
    
    raise ValueError("Could not obtain JWT token - make sure admin user exists")


@pytest.mark.skip(reason="Standalone WebSocket tests are disabled in CI")
class TestWebSocketAuthenticationStandalone:
    """Standalone WebSocket authentication tests."""
    
    def test_server_is_running(self):
        """Verify the walNUT server is running before testing."""
        result = subprocess.run([
            "curl", "-s", "http://localhost:8000/"
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        assert "Welcome to walNUT" in result.stdout
    
    def test_unauthenticated_connection_rejected(self):
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
    
    def test_invalid_token_rejected(self):
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
    
    def test_authenticated_connection_success(self):
        """Test that valid JWT allows connection and message exchange."""
        try:
            token = get_valid_jwt_token()
        except ValueError as e:
            pytest.skip(f"Could not get valid token: {e}")
        
        client = WebSocketTestClient(f"ws://localhost:8000/ws?token={token}")
        connected = client.connect_and_wait(timeout=5.0)  # Longer timeout
        
        # Connection should succeed
        assert connected
        
        # Should receive connection status and auth success
        assert client.has_message_type("connection_status")
        assert client.has_message_type("auth_success")
        
        # Auth success should contain user info
        auth_msg = client.get_message_by_type("auth_success")
        assert "user_id" in auth_msg["data"]
        assert "client_id" in auth_msg["data"]
        
        # Connection may close after authentication - this is normal for this test
    
    def test_bidirectional_message_exchange(self):
        """Test sending and receiving messages."""
        try:
            token = get_valid_jwt_token()
        except ValueError as e:
            pytest.skip(f"Could not get valid token: {e}")
        
        client = WebSocketTestClient(f"ws://localhost:8000/ws?token={token}")
        connected = client.connect_and_wait(timeout=5.0)
        assert connected
        assert client.has_message_type("auth_success")
        
        # Wait a bit after auth before sending ping
        time.sleep(1.0)
        
        # Test ping/pong
        success = client.send_message({"type": "ping"})
        assert success, "Failed to send ping message"
        
        time.sleep(1.0)  # Wait longer for response
        assert client.has_message_type("pong"), f"No pong received. Messages: {client.messages_received}"
    
    def test_websocket_updates_endpoint(self):
        """Test the /ws/updates endpoint also works with authentication."""
        try:
            token = get_valid_jwt_token()
        except ValueError as e:
            pytest.skip(f"Could not get valid token: {e}")
        
        client = WebSocketTestClient(f"ws://localhost:8000/ws/updates?token={token}")
        connected = client.connect_and_wait()
        
        assert connected
        assert client.has_message_type("connection_status")
        assert client.has_message_type("auth_success")
    
    def test_multiple_concurrent_connections(self):
        """Test multiple authenticated WebSocket connections."""
        try:
            token = get_valid_jwt_token()
        except ValueError as e:
            pytest.skip(f"Could not get valid token: {e}")
        
        client1 = WebSocketTestClient(f"ws://localhost:8000/ws?token={token}")
        client2 = WebSocketTestClient(f"ws://localhost:8000/ws?token={token}")
        
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
    
    def test_websocket_info_endpoint_accessible(self):
        """Test that the WebSocket info endpoint is accessible (with proper auth)."""
        try:
            token = get_valid_jwt_token()
        except ValueError as e:
            pytest.skip(f"Could not get valid token: {e}")
        
        # Extract the actual token value to use in a cookie
        # For this test, we'll just verify the endpoint exists
        result = subprocess.run([
            "curl", "-s", "-w", "%{http_code}", 
            "http://localhost:8000/api/websocket/info"
        ], capture_output=True, text=True)
        
        # Should return 401 (unauthorized) rather than 404 (not found)
        # This confirms the endpoint exists and requires authentication
        assert "401" in result.stdout


if __name__ == "__main__":
    # Run tests directly
    import sys
    sys.exit(pytest.main([__file__, "-v"]))