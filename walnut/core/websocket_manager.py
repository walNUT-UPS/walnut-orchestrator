"""
WebSocket connection management for walNUT real-time updates.

This module manages WebSocket connections for broadcasting real-time UPS data
and events to connected clients.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set
from weakref import WeakSet

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class WebSocketMessage(BaseModel):
    """Base model for WebSocket messages."""
    type: str
    timestamp: str
    data: Dict[str, Any]


class ConnectionInfo(BaseModel):
    """Information about a WebSocket connection."""
    client_id: str
    user_id: Optional[str] = None
    connected_at: str
    last_ping: Optional[str] = None


class WebSocketManager:
    """
    Manages WebSocket connections for real-time updates.
    
    Handles client connections, message broadcasting, and connection cleanup.
    """
    
    def __init__(self):
        # Store active connections
        self._connections: Dict[str, WebSocket] = {}
        self._connection_info: Dict[str, ConnectionInfo] = {}
        
        # Keep track of user authentication
        self._authenticated_clients: Dict[str, str] = {}  # client_id -> user_id
        
        # Message queue for disconnected clients (simple in-memory queue)
        self._message_history: List[Dict[str, Any]] = []
        self._max_history_size = 100
        
        # Background task for ping/pong
        self._ping_task: Optional[asyncio.Task] = None
        
    async def connect(self, websocket: WebSocket, client_id: Optional[str] = None) -> str:
        """
        Accept a new WebSocket connection.
        
        Args:
            websocket: The WebSocket connection
            client_id: Optional client ID, will generate if not provided
            
        Returns:
            The client ID for this connection
        """
        await websocket.accept()
        
        if client_id is None:
            client_id = str(uuid.uuid4())
        
        self._connections[client_id] = websocket
        self._connection_info[client_id] = ConnectionInfo(
            client_id=client_id,
            connected_at=datetime.now(timezone.utc).isoformat()
        )
        
        logger.info(f"WebSocket client {client_id} connected")
        
        # Send connection status message
        await self._send_to_client(client_id, {
            "type": "connection_status",
            "data": {
                "status": "connected",
                "client_id": client_id
            }
        })
        
        # Start ping task if this is the first connection
        if len(self._connections) == 1 and self._ping_task is None:
            self._ping_task = asyncio.create_task(self._ping_clients())
        
        return client_id
    
    async def disconnect(self, client_id: str):
        """
        Handle client disconnection.
        
        Args:
            client_id: The client ID to disconnect
        """
        if client_id in self._connections:
            del self._connections[client_id]
        
        if client_id in self._connection_info:
            del self._connection_info[client_id]
        
        if client_id in self._authenticated_clients:
            del self._authenticated_clients[client_id]
        
        logger.info(f"WebSocket client {client_id} disconnected")
        
        # Stop ping task if no connections remain
        if len(self._connections) == 0 and self._ping_task:
            self._ping_task.cancel()
            self._ping_task = None
    
    def authenticate_client(self, client_id: str, user_id: str):
        """
        Mark a client as authenticated.
        
        Args:
            client_id: The client ID
            user_id: The authenticated user ID
        """
        if client_id in self._connection_info:
            self._authenticated_clients[client_id] = user_id
            self._connection_info[client_id].user_id = user_id
            logger.info(f"WebSocket client {client_id} authenticated as user {user_id}")
    
    def is_client_authenticated(self, client_id: str) -> bool:
        """
        Check if a client is authenticated.
        
        Args:
            client_id: The client ID to check
            
        Returns:
            True if client is authenticated, False otherwise
        """
        return client_id in self._authenticated_clients
    
    async def broadcast_ups_status(self, ups_data: Dict[str, Any]):
        """
        Broadcast UPS status update to all authenticated clients.
        
        Args:
            ups_data: UPS status data to broadcast
        """
        message = {
            "type": "ups_status",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": ups_data
        }
        
        await self._broadcast_to_authenticated(message)
        self._add_to_history(message)
    
    async def broadcast_event(self, event_type: str, event_data: Dict[str, Any], severity: str = "INFO"):
        """
        Broadcast an event to all authenticated clients.
        
        Args:
            event_type: Type of event
            event_data: Event data
            severity: Event severity level
        """
        message = {
            "type": "event",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "event_type": event_type,
                "severity": severity,
                **event_data
            }
        }
        
        await self._broadcast_to_authenticated(message)
        self._add_to_history(message)
    
    async def send_system_notification(self, notification: Dict[str, Any]):
        """
        Send a system notification to all authenticated clients.
        
        Args:
            notification: Notification data
        """
        message = {
            "type": "system_notification",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": notification
        }
        
        await self._broadcast_to_authenticated(message)
    
    async def handle_client_message(self, client_id: str, message_data: Dict[str, Any]):
        """
        Handle incoming message from client.
        
        Args:
            client_id: The client ID
            message_data: The message data received
        """
        message_type = message_data.get("type")
        
        if message_type == "ping":
            # Respond to ping with pong
            await self._send_to_client(client_id, {
                "type": "pong",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            # Update last ping time
            if client_id in self._connection_info:
                self._connection_info[client_id].last_ping = datetime.now(timezone.utc).isoformat()
        
        elif message_type == "get_history":
            # Send recent message history
            await self._send_history_to_client(client_id)
        
        else:
            logger.warning(f"Unknown message type '{message_type}' from client {client_id}")
    
    def get_connection_info(self) -> List[ConnectionInfo]:
        """
        Get information about all active connections.
        
        Returns:
            List of connection information
        """
        return list(self._connection_info.values())
    
    def get_connection_count(self) -> int:
        """
        Get the number of active connections.
        
        Returns:
            Number of active connections
        """
        return len(self._connections)
    
    def get_authenticated_count(self) -> int:
        """
        Get the number of authenticated connections.
        
        Returns:
            Number of authenticated connections
        """
        return len(self._authenticated_clients)
    
    async def _broadcast_to_authenticated(self, message: Dict[str, Any]):
        """
        Broadcast a message to all authenticated clients.
        
        Args:
            message: The message to broadcast
        """
        if not self._authenticated_clients:
            return
        
        # Create list of clients to send to (to avoid modification during iteration)
        authenticated_clients = list(self._authenticated_clients.keys())
        
        # Send to all authenticated clients
        tasks = []
        for client_id in authenticated_clients:
            tasks.append(self._send_to_client(client_id, message))
        
        # Execute all sends concurrently
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _send_to_client(self, client_id: str, message: Dict[str, Any]) -> bool:
        """
        Send a message to a specific client.
        
        Args:
            client_id: The client ID
            message: The message to send
            
        Returns:
            True if message was sent successfully, False otherwise
        """
        if client_id not in self._connections:
            return False
        
        websocket = self._connections[client_id]
        
        try:
            message_json = json.dumps(message, separators=(',', ':'))
            await websocket.send_text(message_json)
            return True
            
        except WebSocketDisconnect:
            # Client disconnected
            await self.disconnect(client_id)
            return False
            
        except Exception as e:
            logger.error(f"Failed to send message to client {client_id}: {e}")
            # Remove problematic connection
            await self.disconnect(client_id)
            return False
    
    async def _send_history_to_client(self, client_id: str):
        """
        Send message history to a specific client.
        
        Args:
            client_id: The client ID
        """
        if not self._message_history:
            return
        
        history_message = {
            "type": "history",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "messages": self._message_history[-50:]  # Send last 50 messages
            }
        }
        
        await self._send_to_client(client_id, history_message)
    
    def _add_to_history(self, message: Dict[str, Any]):
        """
        Add a message to the history queue.
        
        Args:
            message: The message to add
        """
        self._message_history.append(message)
        
        # Keep history size limited
        if len(self._message_history) > self._max_history_size:
            self._message_history = self._message_history[-self._max_history_size:]
    
    async def _ping_clients(self):
        """
        Background task to ping clients periodically.
        """
        while True:
            try:
                await asyncio.sleep(30)  # Ping every 30 seconds
                
                if not self._connections:
                    break
                
                # Send ping to all clients
                ping_message = {
                    "type": "ping",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
                # Send to all clients (not just authenticated ones for ping)
                client_ids = list(self._connections.keys())
                tasks = []
                for client_id in client_ids:
                    tasks.append(self._send_to_client(client_id, ping_message))
                
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in ping task: {e}")


# Global WebSocket manager instance
websocket_manager = WebSocketManager()