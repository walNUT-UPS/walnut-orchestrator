"""
WebSocket API endpoints for walNUT real-time updates.

This module provides WebSocket endpoints for real-time communication between
the walNUT server and connected clients.
"""

import json
import logging
from typing import Dict, Any, Optional

from fastapi import WebSocket, WebSocketDisconnect, HTTPException, Query, Depends
from fastapi.routing import APIRoute
from jose import jwt, JWTError

from walnut.auth.deps import current_active_user, get_user_manager
from walnut.auth.models import User
from walnut.config import settings
from walnut.core.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)


async def authenticate_websocket_token(token: str) -> Optional[User]:
    """
    Authenticate a WebSocket connection using JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        User object if authentication successful, None otherwise
    """
    try:
        # Decode the JWT token
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"]
        )
        
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        
        # Get user from database
        # Note: This is a simplified approach. In production, you might want
        # to implement proper user lookup similar to fastapi-users
        from walnut.database.connection import get_db_session
        from walnut.auth.models import User
        from sqlalchemy import select
        
        import anyio
        async with get_db_session() as session:
            result = await anyio.to_thread.run_sync(session.execute, select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            return user if user and user.is_active else None
            
    except JWTError:
        return None
    except Exception as e:
        logger.error(f"WebSocket authentication error: {e}")
        return None


async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="JWT authentication token")
):
    """
    WebSocket endpoint for real-time updates.
    
    Accepts WebSocket connections with JWT authentication and handles
    real-time communication for UPS status updates and events.
    
    Query Parameters:
        token: JWT authentication token (required)
    
    Message Types Sent to Client:
        - connection_status: Connection established/status
        - ups_status: Real-time UPS status updates
        - event: Power events and notifications  
        - system_notification: System-level notifications
        - ping/pong: Keepalive messages
        - history: Historical message data
    
    Message Types Received from Client:
        - ping: Client ping (server responds with pong)
        - get_history: Request message history
    """
    client_id = None
    
    try:
        # Connect to WebSocket manager
        client_id = await websocket_manager.connect(websocket)
        
        # Authenticate the client
        if not token:
            await websocket.send_text(json.dumps({
                "type": "error",
                "data": {"message": "Authentication token required"}
            }))
            await websocket.close(code=4001)
            return
        
        user = await authenticate_websocket_token(token)
        if not user:
            await websocket.send_text(json.dumps({
                "type": "error", 
                "data": {"message": "Invalid authentication token"}
            }))
            await websocket.close(code=4001)
            return
        
        # Mark client as authenticated
        websocket_manager.authenticate_client(client_id, str(user.id))
        
        logger.info(f"WebSocket client {client_id} authenticated as user {user.id}")
        
        # Send authentication success
        await websocket.send_text(json.dumps({
            "type": "auth_success",
            "data": {
                "user_id": str(user.id),
                "client_id": client_id
            }
        }))
        
        # Main message handling loop
        while True:
            try:
                # Wait for messages from client
                message_text = await websocket.receive_text()
                
                try:
                    message_data = json.loads(message_text)
                    await websocket_manager.handle_client_message(client_id, message_data)
                    
                except json.JSONDecodeError:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "data": {"message": "Invalid JSON format"}
                    }))
                    
            except WebSocketDisconnect:
                logger.info(f"WebSocket client {client_id} disconnected")
                break
                
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")
        
    finally:
        # Clean up connection
        if client_id:
            await websocket_manager.disconnect(client_id)


# Helper function to get WebSocket connection info (for debugging/monitoring)
async def get_websocket_info(_user: User = Depends(current_active_user)) -> Dict[str, Any]:
    """
    Get WebSocket connection information (for admin/debugging).
    
    Returns information about active WebSocket connections.
    Requires authentication.
    """
    return {
        "total_connections": websocket_manager.get_connection_count(),
        "authenticated_connections": websocket_manager.get_authenticated_count(),
        "connections": [info.dict() for info in websocket_manager.get_connection_info()]
    }


# Create router-like structure for WebSocket
class WebSocketRoute(APIRoute):
    """Custom route class for WebSocket endpoints."""
    pass


# Export the WebSocket endpoint function for app.py
__all__ = ["websocket_endpoint", "get_websocket_info"]