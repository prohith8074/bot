"""
WebSocket routes for real-time updates
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.config.logging_config import get_logger
from typing import List, Optional
import asyncio
import queue
import threading
import json
from datetime import datetime

router = APIRouter()
logger = get_logger(__name__)

def serialize_message(message: dict):
    """Recursively convert datetime objects in message dict"""
    if isinstance(message, dict):
        return {k: serialize_message(v) for k, v in message.items()}
    elif isinstance(message, list):
        return [serialize_message(item) for item in message]
    elif isinstance(message, datetime):
        return message.isoformat()
    return message

# Store active connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.message_queue = queue.Queue()
        self.event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = asyncio.Lock()

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """Set the event loop for broadcasting"""
        self.event_loop = loop

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        
        # Set event loop if not set
        if self.event_loop is None:
            self.event_loop = asyncio.get_event_loop()

    def disconnect(self, websocket: WebSocket):
        # Optimistic removal to avoid locking if possible
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """
        Broadcast message to all connected clients in parallel (Fail-Fast).
        Uses asyncio.gather to ensure one slow client doesn't block others.
        """
        if not self.active_connections:
            return

        # Serialize message once
        serialized_message = serialize_message(message)
        
        # Create send tasks for all connections
        # We start tasks immediately rather than awaiting them sequentially
        tasks = []
        for connection in self.active_connections:
            tasks.append(self._safe_send(connection, serialized_message))
        
        # Run all sends in parallel and ignore errors (fail-fast)
        # return_exceptions=True prevents one error from crashing the gather
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _safe_send(self, connection: WebSocket, message: dict):
        """Send message with individual error handling to prevent blocking"""
        try:
            # Add a short timeout to prevent hanging on a dead connection
            await asyncio.wait_for(connection.send_json(message), timeout=0.5)
        except Exception as e:
            # Log only verbose errors if needed, otherwise silent fail for performance
            # logger.warning(f"⚠️ WS Send Error: {e}")
            self.disconnect(connection)

    def broadcast_sync(self, message: dict):
        """
        Fire-and-forget broadcast from synchronous context.
        Does NOT block the caller. Schedules task on the event loop.
        """
        if self.event_loop and self.event_loop.is_running():
            # Schedule task immediately without waiting
            self.event_loop.create_task(self.broadcast(message))
            logger.debug(f"⚡ Sync broadcast scheduled (fire-and-forget): {message.get('type')}")
        else:
            # Fallback for startup/shutdown scenarios
            logger.debug(f"⚠️ Event loop not ready, queuing: {message.get('type')}")
            self.message_queue.put(message)

# Global connection manager
manager = ConnectionManager()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time dashboard updates"""
    await manager.connect(websocket)
    
    # Set event loop reference
    if manager.event_loop is None:
        manager.set_event_loop(asyncio.get_event_loop())
    
    try:
        # Process queued messages
        while not manager.message_queue.empty():
            try:
                msg = manager.message_queue.get_nowait()
                await websocket.send_json(msg)
            except queue.Empty:
                break
        
        # Keep connection alive and handle client messages
        while True:
            try:
                # Wait for either a message from client or timeout
                data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                logger.debug(f"📨 Received WebSocket message: {data}")
                # Echo back or handle message
                await websocket.send_json({"type": "pong", "data": data})
            except asyncio.TimeoutError:
                # Check for queued messages
                try:
                    msg = manager.message_queue.get_nowait()
                    await websocket.send_json(msg)
                except queue.Empty:
                    continue
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"❌ WebSocket error: {e}")
        manager.disconnect(websocket)

def get_manager():
    """Get the connection manager instance"""
    return manager




