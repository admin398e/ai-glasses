"""
AI Glasses -- Framebuffer Display Driver
Writes directly to /dev/fb0 on the Pi Zero 2W.
Falls back to a pygame window for development on a normal machine.
"""

import os
import struct
import logging
import threading
from typing import Optional, Tuple

log = logging.getLogger(__name__)

# Try to import pygame for dev fallback
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class FramebufferDisplay:
    """Direct framebuffer display driver for production (Pi)."""

    def __init__(self, device: str, width: int, height: int):
        self.device = device
        self.width = width
        self.height = height
        self._fb = None
        self._lock = threading.Lock()

    def open(self):
        try:
            self._fb = open(self.device, "wb")
            log.info(f"Framebuffer {self.device} opened ({self.width}x{self.height})")
        except PermissionError:
            raise RuntimeError(
                f"Cannot open {self.device} -- run as root or add user to 'video' group:\n"
                f"  sudo usermod -aG video $USER"
            )

    def write_frame(self, image):
        """Write a PIL Image to the framebuffer (RGB565 format)."""
        if not self._fb:
            return
        rgb = image.convert("RGB").resize((self.width, self.height))
        pixels = []
        for r, g, b in rgb.getdata():
            # Pack as RGB565 little-endian
            pixel = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            pixels.append(struct.pack("<H", pixel))
        with self._lock:
            self._fb.seek(0)
            self._fb.write(b"".join(pixels))
            self._fb.flush()

    def close(self):
        if self._fb:
            self._fb.close()


class PygameDisplay:
    """Pygame-based display for development on Mac/Linux desktop."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self._screen = None

    def open(self):
        if not PYGAME_AVAILABLE:
            raise RuntimeError("pygame not installed -- run: pip install pygame")
        pygame.init()
        self._screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("AI Glasses -- HUD Preview")
        log.info(f"Pygame display opened ({self.width}x{self.height})")

    def write_frame(self, image):
        if not self._screen:
            return
        # Handle pygame events so the window doesn't freeze
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.close()
                return
        rgb = image.convert("RGB").resize((self.width, self.height))
        raw = rgb.tobytes()
        surf = pygame.image.fromstring(raw, (self.width, self.height), "RGB")
        self._screen.blit(surf, (0, 0))
        pygame.display.flip()

    def close(self):
        if PYGAME_AVAILABLE:
            pygame.quit()


def get_display(width: int, height: int, fb_device=None):
    """
    Return the appropriate display driver.
    - On Pi (fb_device exists): use FramebufferDisplay
    - Otherwise: fall back to PygameDisplay for dev
    """
    if fb_device is None:
        fb_device = "/dev/fb0"
    if fb_device and os.path.exists(fb_device):
        d = FramebufferDisplay(fb_device, width, height)
    else:
        log.warning(f"{fb_device} not found -- using pygame preview mode")
        d = PygameDisplay(width, height)
    d.open()
    return d
