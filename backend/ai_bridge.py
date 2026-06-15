"""
AI Glasses — Claude API Bridge
All Claude API calls go through here.
The Pi never holds the API key — only the backend does.
"""

import logging
import anthropic

log = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-6"   # Fast, cost-effective for HUD features
MAX_TOKENS = 256                       # Keep responses short — they appear on tiny HUD


PROMPTS = {
    "ask": (
        "You are an AI assistant built into AR glasses. "
        "Answer in under 20 words. Be direct and clear — the user is reading while walking."
    ),
    "translate": (
        "Translate the following text to {target_language}. "
        "Return ONLY the translation, no explanation."
    ),
    "summarise": (
        "Summarise the following in {max_words} words or fewer. "
        "Return only the summary, no preamble."
    ),
    "navigate": (
        "Convert this navigation instruction into a short, glanceable phrase "
        "(max 6 words, imperative, no punctuation)."
    ),
    "describe": (
        "Describe what you see in this image in 15 words or fewer. "
        "Focus on what's most useful to someone who can see the real world around them."
    ),
}


class AIBridge:
    """Wraps the Anthropic SDK and provides feature-specific methods."""

    def __init__(self, api_key: str):
        self._client = anthropic.Anthropic(api_key=api_key)

    async def ask(self, question: str) -> str:
        return await self._complete(
            system=PROMPTS["ask"],
            user=question,
        )

    async def translate(self, text: str, target_language: str = "English") -> str:
        system = PROMPTS["translate"].format(target_language=target_language)
        return await self._complete(system=system, user=text)

    async def summarise(self, text: str, max_words: int = 12) -> str:
        system = PROMPTS["summarise"].format(max_words=max_words)
        return await self._complete(system=system, user=text)

    async def navigation_prompt(self, instruction: str) -> str:
        return await self._complete(
            system=PROMPTS["navigate"],
            user=instruction,
        )

    async def describe_image(self, image_b64: str) -> str:
        """Vision-enabled description — uses Claude's image input."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._describe_sync, image_b64)

    def _describe_sync(self, image_b64: str) -> str:
        try:
            msg = self._client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=64,
                system=PROMPTS["describe"],
                messages=[{
                    "role": "user",
                    "content": [{
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64,
                        },
                    }],
                }],
            )
            return msg.content[0].text.strip()
        except Exception as e:
            log.error(f"Vision describe error: {e}")
            return "[vision error]"

    async def _complete(self, system: str, user: str) -> str:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._complete_sync, system, user)

    def _complete_sync(self, system: str, user: str) -> str:
        try:
            msg = self._client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return msg.content[0].text.strip()
        except anthropic.AuthenticationError:
            log.error("Invalid Anthropic API key — check ANTHROPIC_API_KEY env var")
            return "[auth error]"
        except anthropic.RateLimitError:
            log.warning("Claude rate limit hit")
            return "[rate limit]"
        except Exception as e:
            log.error(f"Claude API error: {e}")
            return "[error]"
