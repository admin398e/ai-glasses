"""
AI Glasses -- AI Engine
Sends requests to the backend's Claude bridge.
All Claude API calls happen on the backend server so the Pi never
holds the API key directly.
"""

import json
import logging
import asyncio
import aiohttp
from typing import Optional, Callable

log = logging.getLogger(__name__)


class AIEngine:
    """
    Lightweight AI client that runs on the Pi.
    Heavy lifting (Claude API calls) happens on the backend.
    """

    def __init__(self, backend_http_url: str):
        self.base_url = backend_http_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None
        self._on_response: Optional[Callable] = None

    def on_response(self, callback: Callable[[str, str], None]):
        """Register callback: fn(feature, text) -- called when AI replies."""
        self._on_response = callback

    async def start(self):
        self._session = aiohttp.ClientSession()
        log.info("AI engine started")

    async def stop(self):
        if self._session:
            await self._session.close()

    async def ask(self, question: str) -> str:
        """General AI assistant query."""
        return await self._call("/ai/ask", {"question": question})

    async def translate(self, text: str, target_lang: str = "English") -> str:
        """Translate text and return the result."""
        return await self._call("/ai/translate", {
            "text": text,
            "target_language": target_lang,
        })

    async def summarise_notification(self, raw: str) -> str:
        """Summarise a long notification to a short HUD-friendly string."""
        return await self._call("/ai/summarise", {"text": raw, "max_words": 12})

    async def navigation_prompt(self, instruction: str) -> str:
        """Convert a navigation instruction to a short, glanceable string."""
        return await self._call("/ai/navigate", {"instruction": instruction})

    async def describe_scene(self, image_b64: str) -> str:
        """
        Send a camera frame (base64 JPEG) for AI scene description.
        Requires a Pi camera module (optional).
        """
        return await self._call("/ai/describe", {"image_b64": image_b64})

    async def _call(self, endpoint: str, payload: dict) -> str:
        if not self._session:
            log.warning("AI engine not started")
            return ""
        url = self.base_url + endpoint
        try:
            async with self._session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=8)
            ) as resp:
                data = await resp.json()
                result = data.get("result", "")
                if self._on_response:
                    feature = endpoint.split("/")[-1]
                    self._on_response(feature, result)
                return result
        except aiohttp.ClientConnectorError:
            log.error(f"Cannot reach backend at {url} -- is it running?")
            return "[offline]"
        except asyncio.TimeoutError:
            log.warning(f"AI request timed out: {endpoint}")
            return "[timeout]"
        except Exception as e:
            log.error(f"AI engine error: {e}")
            return "[error]"
