"""
AI Glasses — Main Firmware Entry Point
Runs on Raspberry Pi Zero 2W.

Usage:
    python main.py

Architecture:
    ┌─────────────┐     WebSocket     ┌─────────────────┐
    │   Pi Zero   │ ◄────────────────► │  Backend server │
    │  (this file)│                   │  (Hetzner VPS)  │
    │             │     REST /ai/*    │                  │
    │  display.py │ ────────────────► │  ai_bridge.py   │
    │  hud.py     │                   │  (Claude API)   │
    │  wifi_client│                   └─────────────────┘
    │  ai_engine  │
    └─────────────┘
"""

import asyncio
import logging
import signal
import sys
import time

# ── Local imports ─────────────────────────────────────────────────────────────
from config import (
    BACKEND_WS_URL, BACKEND_HTTP_URL,
    FRAMEBUFFER_DEVICE, DISPLAY_WIDTH, DISPLAY_HEIGHT,
    IMU_ENABLED, MIC_ENABLED, TOUCH_PIN,
    FEATURE_NOTIFICATIONS, FEATURE_VOICE_AI,
    DEBUG, LOG_LEVEL,
)
from display import get_display
from hud import HUDRenderer, HUDOverlay, GREEN, AMBER, RED
from ai_engine import AIEngine
from wifi_client import WiFiClient

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("main")

# ── Target frame rate ─────────────────────────────────────────────────────────
TARGET_FPS = 30
FRAME_TIME = 1.0 / TARGET_FPS


class AIGlassesFirmware:
    """Top-level coordinator for all subsystems."""

    def __init__(self):
        self.display = get_display(DISPLAY_WIDTH, DISPLAY_HEIGHT, FRAMEBUFFER_DEVICE)
        self.hud = HUDRenderer(DISPLAY_WIDTH, DISPLAY_HEIGHT)
        self.ai = AIEngine(BACKEND_HTTP_URL)
        self.ws = WiFiClient(BACKEND_WS_URL)
        self._running = False

    async def start(self):
        log.info("AI Glasses firmware starting...")

        # Start network subsystems
        await self.ai.start()
        await self.ws.start()

        # Register AI response → HUD
        self.ai.on_response(self._on_ai_response)

        # Register WebSocket message handlers
        self.ws.on("show_text", self._cmd_show_text)
        self.ws.on("notify",    self._cmd_notify)
        self.ws.on("clear",     self._cmd_clear)
        self.ws.on("ask_ai",   self._cmd_ask_ai)
        self.ws.on("translate", self._cmd_translate)
        self.ws.on("navigate",  self._cmd_navigate)

        # Boot splash
        self.hud.push(HUDOverlay("AI Glasses", position=(20, 60), color=GREEN, duration=3.0))
        self.hud.notify("Connected to backend", color=GREEN, duration=3.0)

        # Optional subsystems
        if IMU_ENABLED:
            asyncio.create_task(self._imu_loop())
        if MIC_ENABLED and FEATURE_VOICE_AI:
            asyncio.create_task(self._mic_loop())

        self._running = True
        log.info("Firmware running -- press Ctrl+C to stop")
        await self._render_loop()

    async def stop(self):
        log.info("Shutting down...")
        self._running = False
        await self.ai.stop()
        await self.ws.stop()
        self.display.close()

    # ── Render loop ───────────────────────────────────────────────────────────

    async def _render_loop(self):
        """Main render loop -- composites HUD and writes to display."""
        while self._running:
            t0 = time.monotonic()
            try:
                frame = self.hud.render()
                self.display.write_frame(frame)
            except Exception as e:
                log.error(f"Render error: {e}")

            # Maintain target FPS
            elapsed = time.monotonic() - t0
            sleep = max(0.0, FRAME_TIME - elapsed)
            await asyncio.sleep(sleep)

    # ── WebSocket command handlers ────────────────────────────────────────────

    async def _cmd_show_text(self, data: dict):
        """Show arbitrary text at a position on the HUD."""
        self.hud.push(HUDOverlay(
            text=data.get("text", ""),
            position=tuple(data.get("position", [20, 80])),
            color=tuple(data.get("color", GREEN)),
            size=data.get("size", 24),
            duration=data.get("duration", 8.0),
            tag=data.get("tag", ""),
        ))

    async def _cmd_notify(self, data: dict):
        self.hud.notify(data.get("text", ""), duration=data.get("duration", 6.0))

    async def _cmd_clear(self, data: dict):
        tag = data.get("tag")
        if tag:
            self.hud.clear_tag(tag)
        else:
            self.hud.clear_all()

    async def _cmd_ask_ai(self, data: dict):
        question = data.get("question", "")
        self.hud.notify("Thinking...", color=AMBER, duration=15.0)
        result = await self.ai.ask(question)
        self.hud.ai_response(result)

    async def _cmd_translate(self, data: dict):
        text = data.get("text", "")
        lang = data.get("language", "English")
        self.hud.notify(f"Translating...", color=AMBER, duration=10.0)
        result = await self.ai.translate(text, lang)
        self.hud.ai_response(result)

    async def _cmd_navigate(self, data: dict):
        instruction = data.get("instruction", "")
        result = await self.ai.navigation_prompt(instruction)
        self.hud.push(HUDOverlay(
            text=f"^ {result}",
            position=(20, DISPLAY_HEIGHT // 3),
            color=GREEN,
            size=28,
            duration=15.0,
            tag="nav",
        ))

    # ── AI response callback ──────────────────────────────────────────────────

    def _on_ai_response(self, feature: str, text: str):
        log.debug(f"AI [{feature}]: {text[:60]}")
        # Telemetry back to backend/companion
        asyncio.create_task(self.ws.send("ai_result", {"feature": feature, "text": text}))

    # ── Optional subsystems ───────────────────────────────────────────────────

    async def _imu_loop(self):
        """Read BNO055 IMU and stream to backend every 200ms."""
        try:
            import board, busio
            from adafruit_bno055 import BNO055_I2C
            i2c = busio.I2C(board.SCL, board.SDA)
            imu = BNO055_I2C(i2c)
            log.info("IMU (BNO055) ready")
            while self._running:
                euler = imu.euler
                if euler and euler[0] is not None:
                    await self.ws.send_imu(euler[0], euler[1] or 0, euler[2] or 0)
                    self.hud.set_status("imu", f"{euler[0]:.0f}")
                await asyncio.sleep(0.2)
        except Exception as e:
            log.warning(f"IMU not available: {e}")
            self.hud.set_status("imu", "--")

    async def _mic_loop(self):
        """
        Listen for wake word then stream audio to backend for transcription.
        Requires: pip install pyaudio webrtcvad
        """
        try:
            import pyaudio
            from config import MIC_SAMPLE_RATE, MIC_CHANNELS, MIC_CHUNK_SIZE, WAKE_WORD
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=MIC_CHANNELS,
                rate=MIC_SAMPLE_RATE,
                input=True,
                frames_per_buffer=MIC_CHUNK_SIZE,
            )
            log.info(f"Microphone ready -- wake word: '{WAKE_WORD}'")
            import base64
            while self._running:
                chunk = stream.read(MIC_CHUNK_SIZE, exception_on_overflow=False)
                # Send raw audio to backend for wake-word + STT processing
                await self.ws.send("audio_chunk", {
                    "data": base64.b64encode(chunk).decode(),
                    "rate": MIC_SAMPLE_RATE,
                })
                await asyncio.sleep(0)
        except Exception as e:
            log.warning(f"Microphone not available: {e}")


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    firmware = AIGlassesFirmware()

    # Graceful shutdown on Ctrl+C / SIGTERM
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(firmware.stop()))

    await firmware.start()


if __name__ == "__main__":
    asyncio.run(main())
