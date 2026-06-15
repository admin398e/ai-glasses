"""
AI Glasses — n8n Integration
Sends outbound webhooks to your n8n instance on Hetzner.
n8n then routes to Slack, GoHighLevel, calendar, etc.

Your n8n flows should POST to /hook/notification or /hook/navigate
to push content to the glasses.
"""

import logging
import aiohttp
from typing import Optional

log = logging.getLogger(__name__)


class N8nHooks:
    """Outbound webhooks to n8n."""

    def __init__(self, base_url: str):
        # e.g. "https://n8n.your-hetzner.com"
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def trigger(self, workflow_name: str, payload: dict) -> bool:
        """
        Trigger an n8n webhook workflow.
        Your n8n webhook URL format: {base_url}/webhook/{workflow_name}
        """
        if not self.base_url:
            log.debug("n8n not configured — skipping trigger")
            return False
        url = f"{self.base_url}/webhook/{workflow_name}"
        session = await self._get_session()
        try:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                ok = resp.status < 300
                if not ok:
                    log.warning(f"n8n webhook {workflow_name} returned {resp.status}")
                return ok
        except Exception as e:
            log.warning(f"n8n trigger failed ({workflow_name}): {e}")
            return False

    # ── Convenience methods ───────────────────────────────────────────────────

    async def glasses_online(self, device_id: str = "glasses-01"):
        """Notify n8n that the glasses have connected."""
        return await self.trigger("glasses-connected", {"device": device_id})

    async def ai_query_logged(self, question: str, answer: str):
        """Log AI queries to n8n for analytics / CRM."""
        return await self.trigger("ai-query-log", {
            "question": question,
            "answer": answer,
        })

    async def voice_command(self, transcript: str):
        """Send a voice command transcript to n8n for routing."""
        return await self.trigger("voice-command", {"transcript": transcript})

    async def battery_low(self, percent: int):
        """Alert n8n (and by extension Slack/phone) when battery is low."""
        return await self.trigger("battery-alert", {"percent": percent})
