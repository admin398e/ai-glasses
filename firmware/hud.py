"""
AI Glasses — HUD Renderer
Composites overlays (text, icons, status) onto a PIL Image frame
that is then sent to the display driver.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

# ── Colour palette ────────────────────────────────────────────────────────────
GREEN   = (0, 255, 100)
WHITE   = (255, 255, 255)
AMBER   = (255, 180, 0)
RED     = (255, 60, 60)
DIM     = (120, 120, 120)
BLACK   = (0, 0, 0)


@dataclass
class HUDOverlay:
    """A single item rendered on the HUD."""
    text: str
    position: Tuple[int, int] = (20, 20)
    color: Tuple[int, int, int] = GREEN
    size: int = 24
    duration: float = 5.0          # seconds, 0 = permanent
    tag: str = ""                  # unique id — set to overwrite
    _born: float = field(default_factory=time.time, init=False)

    def is_expired(self) -> bool:
        return self.duration > 0 and (time.time() - self._born) > self.duration


class HUDRenderer:
    """
    Manages a stack of HUD overlays and renders them to a PIL Image
    each frame.
    """

    def __init__(self, width: int, height: int, font_path: Optional[str] = None):
        self.width = width
        self.height = height
        self._overlays: List[HUDOverlay] = []
        self._font_cache: dict = {}
        self._font_path = font_path  # e.g. "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

        # Status bar items (always visible)
        self._status = {
            "time": "",
            "battery": "100%",
            "wifi": "●",
            "ai": "●",
        }

    # ── Public API ────────────────────────────────────────────────────────────

    def push(self, overlay: HUDOverlay):
        """Add or replace an overlay (matched by tag if set)."""
        if overlay.tag:
            self._overlays = [o for o in self._overlays if o.tag != overlay.tag]
        self._overlays.append(overlay)

    def notify(self, text: str, color=AMBER, duration=6.0):
        """Quick notification banner at the bottom of the HUD."""
        self.push(HUDOverlay(
            text=text,
            position=(20, self.height - 60),
            color=color,
            size=22,
            duration=duration,
            tag="__notify__",
        ))

    def ai_response(self, text: str):
        """Show an AI response in the centre of the HUD."""
        # Wrap long text
        lines = self._wrap(text, max_chars=40)
        y = self.height // 2 - (len(lines) * 28) // 2
        for i, line in enumerate(lines):
            self.push(HUDOverlay(
                text=line,
                position=(20, y + i * 30),
                color=GREEN,
                size=22,
                duration=10.0,
                tag=f"__ai_{i}__",
            ))

    def set_status(self, key: str, value: str):
        self._status[key] = value

    def clear_tag(self, tag: str):
        self._overlays = [o for o in self._overlays if o.tag != tag]

    def clear_all(self):
        self._overlays.clear()

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self) -> Image.Image:
        """Render all overlays to a PIL Image. Call this every frame."""
        # Prune expired overlays
        self._overlays = [o for o in self._overlays if not o.is_expired()]

        frame = Image.new("RGB", (self.width, self.height), BLACK)
        draw = ImageDraw.Draw(frame)

        # Status bar (top strip)
        self._draw_status_bar(draw)

        # All active overlays
        for overlay in self._overlays:
            font = self._get_font(overlay.size)
            draw.text(overlay.position, overlay.text, font=font, fill=overlay.color)

        return frame

    # ── Internals ─────────────────────────────────────────────────────────────

    def _draw_status_bar(self, draw: ImageDraw.ImageDraw):
        import datetime
        self._status["time"] = datetime.datetime.now().strftime("%H:%M")
        bar_text = "  ".join(self._status.values())
        font = self._get_font(18)
        draw.rectangle([(0, 0), (self.width, 28)], fill=(0, 0, 0))
        draw.text((8, 4), bar_text, font=font, fill=DIM)

    def _get_font(self, size: int) -> ImageFont.FreeTypeFont:
        if size not in self._font_cache:
            try:
                if self._font_path:
                    self._font_cache[size] = ImageFont.truetype(self._font_path, size)
                else:
                    # Try common Pi/Linux font locations
                    for path in [
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                        "/System/Library/Fonts/Helvetica.ttc",  # Mac dev
                    ]:
                        try:
                            self._font_cache[size] = ImageFont.truetype(path, size)
                            break
                        except OSError:
                            continue
                    else:
                        self._font_cache[size] = ImageFont.load_default()
            except Exception:
                self._font_cache[size] = ImageFont.load_default()
        return self._font_cache[size]

    @staticmethod
    def _wrap(text: str, max_chars: int = 40) -> List[str]:
        words = text.split()
        lines, current = [], ""
        for word in words:
            if len(current) + len(word) + 1 <= max_chars:
                current = (current + " " + word).strip()
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines or [""]
