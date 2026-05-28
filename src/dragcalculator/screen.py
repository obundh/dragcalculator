from __future__ import annotations

from dataclasses import dataclass

import mss
from PIL import Image


@dataclass(frozen=True)
class CaptureRect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


def capture_region(rect: CaptureRect) -> Image.Image:
    if rect.width <= 0 or rect.height <= 0:
        raise ValueError("Capture region must have positive width and height.")

    monitor = {
        "left": rect.left,
        "top": rect.top,
        "width": rect.width,
        "height": rect.height,
    }

    with mss.mss() as screen_capture:
        shot = screen_capture.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.rgb)

