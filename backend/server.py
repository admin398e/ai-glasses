"""
AI Glasses — Backend Server
FastAPI + WebSocket server. Runs on your Hetzner VPS.

Handles:
  - WebSocket connections from the Pi firmware
  - REST endpoints used by the Pi AI engine (/ai/*)
  - WebSocket connections from the companion web app
  - Forwarding messages between companion ↔ glasses
  - n8n webhook integration

Start with:
    uvicorn server:app --host 0.0.0.0 --port 8765 --reload
"""

import asyncio
import logging
import os
from typing import Dict, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ai_bridge import AIBridge
from n8n_hooks import N8nHooks

log = logging.getLogger(__name__)

app = FastAPI(title="AI Glasses Backend", version="0.1.0")

# Allow companion web app (served from same origin or separate port)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singleton instances
ai = AIBridge(api_key=os.environ["ANTHROPIC_API_KEY"])
n8n = N8nHooks(base_url=os.getenv("N8N_URL", ""))

# ── Connected clients ─────────────────────────────────────────────────────────
glasses_connections: Set[WebSocket] = set()
companion_connections: Set[WebSocket] = set()


# ── WebSocket: Glasses ────────────────────────────────────────────────────────

@app.websocket("/ws")
async def glasses_ws(websocket: WebSocket):
    """WebSocket endpoint for the Pi firmware."""
    await websocket.accept()
    glasses_connections.add(websocket)
    log.info(f"Glasses connected — {len(glasses_connections)} active")
    try:
        async for raw in websocket.iter_text():
            import json
            msg = json.loads(raw)
            msg_type = msg.get("type", "")
            data = msg.get("data", {})

            # Forward telemetry to all companion connections
            if msg_type in ("imu", "battery", "status", "ai_result"):
                await broadcast_companions(msg_type, data)

            # Log hello
            elif msg_type == "hello":
                log.info(f"Glasses hello: {data}")

            # Audio chunk → wake-word + STT (optional)
            elif msg_type == "audio_chunk":
                asyncio.create_task(handle_audio(websocket, data))

    except WebSocketDisconnect:
        pass
    finally:
        glasses_connections.discard(websocket)
        log.info(f"Glasses disconnected — {len(glasses_connections)} remaining")


# ── WebSocket: Companion app ──────────────────────────────────────────────────

@app.websocket("/companion")
async def companion_ws(websocket: WebSocket):
    """WebSocket endpoint for the companion web app."""
    await websocket.accept()
    companion_connections.add(websocket)
    log.info(f"Companion connected — {len(companion_connections)} active")
    try:
        async for raw in websocket.iter_text():
            import json
            msg = json.loads(raw)
            # Forward commands from companion → glasses
            await broadcast_glasses(msg.get("type", ""), msg.get("data", {}))
    except WebSocketDisconnect:
        pass
    finally:
        companion_connections.discard(websocket)


# ── REST: AI endpoints (called by Pi ai_engine.py) ───────────────────────────

class AskRequest(BaseModel):
    question: str

class TranslateRequest(BaseModel):
    text: str
    target_language: str = "English"

class SummariseRequest(BaseModel):
    text: str
    max_words: int = 12

class NavigateRequest(BaseModel):
    instruction: str

class DescribeRequest(BaseModel):
    image_b64: str


@app.post("/ai/ask")
async def ai_ask(req: AskRequest):
    result = await ai.ask(req.question)
    return {"result": result}

@app.post("/ai/translate")
async def ai_translate(req: TranslateRequest):
    result = await ai.translate(req.text, req.target_language)
    return {"result": result}

@app.post("/ai/summarise")
async def ai_summarise(req: SummariseRequest):
    result = await ai.summarise(req.text, req.max_words)
    return {"result": result}

@app.post("/ai/navigate")
async def ai_navigate(req: NavigateRequest):
    result = await ai.navigation_prompt(req.instruction)
    return {"result": result}

@app.post("/ai/describe")
async def ai_describe(req: DescribeRequest):
    result = await ai.describe_image(req.image_b64)
    return {"result": result}


# ── REST: n8n inbound webhooks ────────────────────────────────────────────────

@app.post("/hook/notification")
async def hook_notification(body: dict):
    """
    n8n sends notifications here.
    We summarise them with Claude and push to the glasses.
    """
    raw = body.get("text", body.get("message", ""))
    if not raw:
        raise HTTPException(400, "No text field")
    short = await ai.summarise(raw, max_words=10)
    await broadcast_glasses("notify", {"text": short, "duration": 8.0})
    return {"status": "sent", "summary": short}

@app.post("/hook/navigate")
async def hook_navigate(body: dict):
    instruction = body.get("instruction", "")
    short = await ai.navigation_prompt(instruction)
    await broadcast_glasses("navigate", {"instruction": short})
    return {"status": "sent"}


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "glasses": len(glasses_connections),
        "companions": len(companion_connections),
    }


# ── Serve companion app ───────────────────────────────────────────────────────

import pathlib
COMPANION_DIR = pathlib.Path(__file__).parent.parent / "companion"
if COMPANION_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(COMPANION_DIR), html=True), name="companion")


# ── Helpers ───────────────────────────────────────────────────────────────────

async def broadcast_glasses(msg_type: str, data: dict):
    import json
    packet = json.dumps({"type": msg_type, "data": data})
    dead = set()
    for ws in glasses_connections:
        try:
            await ws.send_text(packet)
        except Exception:
            dead.add(ws)
    glasses_connections -= dead

async def broadcast_companions(msg_type: str, data: dict):
    import json
    packet = json.dumps({"type": msg_type, "data": data})
    dead = set()
    for ws in companion_connections:
        try:
            await ws.send_text(packet)
        except Exception:
            dead.add(ws)
    companion_connections -= dead

async def handle_audio(websocket: WebSocket, data: dict):
    """Process audio chunk — wake word detection + STT."""
    import base64
    chunk = base64.b64decode(data.get("data", ""))
    # Future: run wake-word model (e.g. openWakeWord) then STT
    # For now just log
    log.debug(f"Audio chunk received: {len(chunk)} bytes")
