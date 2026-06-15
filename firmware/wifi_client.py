"""
AI Glasses — WebSocket Client
Keeps a persistent connection to the backend.
Receives commands (show text, change mode, etc.) from the companion app
and sends telemetry (IMU, battery, status) back.
"""

import json
import asyncio
import logging
from typing import Optional, Callable, Dict, Any

import websockets
from websockets.exceptions import ConnectionClosed, InvalidURI

log = logging.getLogger(__name__)

RECONNECT_DELAY = 3   # seconds between reconnect attempts


class WiFiClient:
    """Persistent WebSocket connection to the AI Glasses backend."""

    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self._ws = None
        self._running = False
        self._handlers: Dict[str, Callable] = {}

    def on(self, message_type: str, handler: Callable[[dict], None]):
        """Register a handler for an incoming message type."""
        self._handlers[message_type] = handler

    async def start(self):
        self._running = True
        asyncio.create_task(self._connection_loop())
        log.info(f"WiFi client started — target: {self.ws_url}")

    async def stop(self):
        self._running = False
        if self._ws:
            await self._ws.close()

    async def send(self, msg_type: str, payload: dict = None):
        """Send a message to the backend."""
        if not self._ws:
            log.warning("Not connected — dropping message")
            return
        packet = json.dumps({"type": msg_type, "data": payload or {}})
        try:
            await self._ws.send(packet)
        except ConnectionClosed:
            log.warning("Connection closed while sending")

    # ── Telemetry helpers ─────────────────────────────────────────────────────

    async def send_imu(self, heading: float, pitch: float, roll: float):
        await self.send("imu", {"heading": heading, "pitch": pitch, "roll": roll})

    async def send_battery(self, percent: int):
        await self.send("battery", {"percent": percent})

    async def send_status(self, status: str):
        await self.send("status", {"value": status})

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _connection_loop(self):
        while self._running:
            try:
                log.info(f"Connecting to {self.ws_url}...")
                async with websockets.connect(self.ws_url) as ws:
                    self._ws = ws
                    log.info("Connected to backend")
                    await self.send("hello", {"device": "ai-glasses-v01"})
                    await self._receive_loop(ws)
            except (ConnectionRefusedError, OSError, InvalidURI) as e:
                log.warning(f"Connection failed: {e} — retrying in {RECONNECT_DELAY}s")
            except ConnectionClosed:
                log.info("Connection closed — reconnecting...")
            except Exception as e:
                log.error(f"Unexpected error: {e}")
            finally:
                self._ws = None
            if self._running:
                await asyncio.sleep(RECONNECT_DELAY)

    async def _receive_loop(self, ws):
        async for raw in ws:
            try:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")
                handler = self._handlers.get(msg_type) or self._handlers.get("*")
                if handler:
                    await asyncio.ensure_future(
                        handler(msg.get("data", {}))
                        if asyncio.iscoroutinefunction(handler)
                        else asyncio.coroutine(lambda: handler(msg.get("data", {})))()
                    )
                else:
                    log.debug(f"No handler for message type: {msg_type}")
            except json.JSONDecodeError:
                log.warning(f"Invalid JSON received: {raw[:80]}")
