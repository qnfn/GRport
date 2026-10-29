# SPDX-License-Identifier: GPL-2.0-or-later
"""Draws the GRport icons: the app icon and one badge per game, in yellow and black.

    python tools/make_icons.py

Everything is drawn here from shapes and a system font, so no game artwork is used. Writes
assets/grport.ico (the exe and window icon), assets/grport.png, assets/game_gr1.png and
assets/game_gr2.png (the game cards).
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

YELLOW = (255, 196, 0)
YELLOW_DEEP = (232, 150, 0)
BLACK = (14, 14, 16)
INK = (34, 34, 38)
SIZE = 1024
ASSETS = Path(__file__).resolve().parent.parent / "assets"
FONT = Path("C:/Windows/Fonts/seguibl.ttf")  # Segoe UI Black


def font(px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT), px)


def rounded_square(size: int, radius: int, fill) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, size - 1, size - 1), radius, fill=fill)
    return img


def vertical_gradient(size: int, top, bottom) -> Image.Image:
    img = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        t = y / (size - 1)
        draw.line((0, y, size, y), fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return img


def orbit(draw: ImageDraw.ImageDraw, box, width: int, color, start: float, end: float) -> None:
    """A tilted ring segment: the 'gravity' swoosh."""
    draw.arc(box, start, end, fill=color, width=width)


def star(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color) -> None:
    """A four-point sparkle."""
    pts = []
    for i in range(8):
        angle = math.pi / 4 * i - math.pi / 2
        radius = r if i % 2 == 0 else r * 0.28
        pts.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    draw.polygon(pts, fill=color)


def centered_text(draw: ImageDraw.ImageDraw, cx: float, cy: float, text: str, size: int, fill):
    f = font(size)
    l, t, r, b = draw.textbbox((0, 0), text, font=f)
    draw.text((cx - (l + r) / 2, cy - (t + b) / 2), text, font=f, fill=fill)


def swoosh_layer(color, width: int, tilt: float, inner: float = 0.0) -> Image.Image:
    """An ellipse ring rotated by `tilt` degrees, cut open at the top right."""
    layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    pad = 120 + inner
    box = (pad, SIZE * 0.30 + inner * 0.4, SIZE - pad, SIZE * 0.70 - inner * 0.4)
    orbit(draw, box, width, color, 200, 500)
    return layer.rotate(tilt, resample=Image.BICUBIC, center=(SIZE / 2, SIZE / 2))


def app_icon() -> Image.Image:
    """Black tile, yellow 'GR' with an orbit swinging through it and a sparkle."""
    base = rounded_square(SIZE, 210, BLACK + (255,))
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((170, 170, SIZE - 170, SIZE - 170), fill=YELLOW + (70,))
    base.alpha_composite(glow.filter(ImageFilter.GaussianBlur(120)))

    back = swoosh_layer(YELLOW_DEEP + (255,), 46, -24)
    base.alpha_composite(back)

    text = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    centered_text(ImageDraw.Draw(text), SIZE / 2, SIZE / 2 + 10, "GR", 470, YELLOW + (255,))
    # The orbit passes in front of the letters on its lower half.
    base.alpha_composite(text)
    front = swoosh_layer(YELLOW + (255,), 46, -24)
    cut = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(cut).rectangle((0, SIZE * 0.52, SIZE, SIZE), fill=255)
    front.putalpha(Image.composite(front.getchannel("A"), Image.new("L", (SIZE, SIZE), 0), cut))
    base.alpha_composite(front)

    draw = ImageDraw.Draw(base)
    star(draw, SIZE * 0.80, SIZE * 0.20, 70, YELLOW + (255,))
    star(draw, SIZE * 0.70, SIZE * 0.12, 26, YELLOW + (255,))
    return base


def game_badge(number: str, subtitle: str) -> Image.Image:
    """Yellow tile with a black number and an orbit: one per game."""
    base = rounded_square(SIZE, 210, (0, 0, 0, 255))
    fill = vertical_gradient(SIZE, YELLOW, YELLOW_DEEP)
    mask = rounded_square(SIZE, 210, (255, 255, 255, 255)).getchannel("A")
    base.paste(fill, (0, 0), mask)

    draw = ImageDraw.Draw(base)
    centered_text(draw, SIZE / 2, SIZE * 0.47, number, 640, BLACK + (255,))
    base.alpha_composite(swoosh_layer(INK + (255,), 34, -24, inner=40))
    centered_text(draw, SIZE / 2, SIZE * 0.86, subtitle, 92, BLACK + (255,))
    star(draw, SIZE * 0.82, SIZE * 0.18, 60, BLACK + (255,))
    # Thin black frame so the tile reads on a yellow-accented UI.
    draw.rounded_rectangle((14, 14, SIZE - 15, SIZE - 15), 196, outline=BLACK + (255,), width=18)
    return base


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    icon = app_icon()
    icon.save(ASSETS / "grport.png")
    icon.save(ASSETS / "grport.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    game_badge("1", "GRAVITY RUSH").resize((512, 512), Image.LANCZOS).save(ASSETS / "game_gr1.png")
    game_badge("2", "GRAVITY RUSH").resize((512, 512), Image.LANCZOS).save(ASSETS / "game_gr2.png")
    print("wrote", *sorted(p.name for p in ASSETS.iterdir()))


if __name__ == "__main__":
    main()
