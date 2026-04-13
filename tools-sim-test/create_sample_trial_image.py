from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def create_sample(path: Path) -> None:
    width, height = 1280, 720
    canvas = np.zeros((height, width, 3), dtype=np.uint8)

    # Base healthy field color.
    canvas[:, :, 1] = 205
    canvas[:, :, 0] = 45
    canvas[:, :, 2] = 38

    image = Image.fromarray(canvas, mode="RGB")
    draw = ImageDraw.Draw(image)

    # Draw irrigation-style horizontal bands to resemble rows.
    for y in range(30, height, 48):
        draw.line((0, y, width, y), fill=(62, 170, 36), width=2)

    # Stressed patches: more red and less green.
    stressed = [
        (260, 220, 95),
        (580, 260, 120),
        (880, 410, 85),
        (1020, 220, 70),
    ]

    for cx, cy, radius in stressed:
        draw.ellipse(
            (cx - radius, cy - radius, cx + radius, cy + radius),
            fill=(125, 175, 45),
            outline=(185, 90, 30),
            width=3,
        )

    image.save(path)


if __name__ == "__main__":
    output = Path(".runtime/image-trial/sample_field_input.png")
    output.parent.mkdir(parents=True, exist_ok=True)
    create_sample(output)
    print(output.resolve())
