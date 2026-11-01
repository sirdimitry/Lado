#!/usr/bin/env python3
"""Render the tray/application icons that ship in windows/assets/icons.

The macOS build draws its status item at runtime; on Windows the notification
area is DPI dependent, so a small multi-size .ico per state is both crisper and
simpler than re-rendering GDI text for every DPI change.

Requires Pillow (already used by the macOS build scripts).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
ASSETS = Path(__file__).resolve().parents[1] / "assets"
ICONS = ASSETS / "icons"
FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\segoeuib.ttf"),
    Path(r"C:\Windows\Fonts\seguisb.ttf"),
]
SIZES = (16, 20, 24, 32, 40, 48, 64)
SUPERSAMPLE = 8

INK = (245, 241, 232, 255)      # #F5F1E8 brand cream
DARK = (24, 35, 34, 255)        # #182322 brand ink
ORANGE = (240, 100, 54, 255)    # #F06436 brand accent
MUTED = (124, 138, 135, 255)
PAUSED_BG = (32, 44, 42, 255)
SECURE_BG = (16, 24, 23, 255)


def pick_font() -> Path:
    for candidate in FONT_CANDIDATES:
        if candidate.exists():
            return candidate
    raise SystemExit("Segoe UI Bold was not found; install it or edit FONT_CANDIDATES")


def rounded_rect(size: int, radius_ratio: float) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    radius = max(2, int(round(size * radius_ratio)))
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=DARK)
    return canvas


def fit_text(draw: ImageDraw.ImageDraw, text: str, font_path: Path, box: int):
    size = int(box * 0.62)
    while size > 4:
        font = ImageFont.truetype(str(font_path), size)
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        if right - left <= box and bottom - top <= box:
            return font
        size -= 1
    return ImageFont.truetype(str(font_path), 4)


def draw_label(text: str, font_path: Path, color, background=DARK,
               accent: bool = True, lock: bool = False) -> Image.Image:
    px = 32 * SUPERSAMPLE
    image = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    radius = int(px * 0.22)
    draw.rounded_rectangle((0, 0, px - 1, px - 1), radius=radius, fill=background)

    font = fit_text(draw, text, font_path, int(px * 0.74))
    draw.text((px / 2, px * 0.47), text, font=font, fill=color, anchor="mm")

    if accent:
        width, height = int(px * 0.30), max(1, int(px * 0.055))
        y = int(px * 0.815)
        draw.rounded_rectangle(
            (px / 2 - width / 2, y, px / 2 + width / 2, y + height),
            radius=max(1, height // 2), fill=ORANGE)

    if lock:
        # A compact padlock, drawn rather than a font glyph so it stays legible.
        body_w, body_h = int(px * 0.17), int(px * 0.13)
        x = int(px * 0.74)
        y = int(px * 0.74)
        draw.rounded_rectangle((x, y, x + body_w, y + body_h),
                               radius=max(1, body_h // 4), fill=ORANGE)
        shackle_w = int(body_w * 0.62)
        draw.arc((x + (body_w - shackle_w) // 2, y - int(body_h * 0.75),
                  x + (body_w + shackle_w) // 2, y + int(body_h * 0.35)),
                 start=180, end=360, fill=ORANGE, width=max(1, int(px * 0.022)))
    return image


def draw_paused(font_path: Path) -> Image.Image:
    px = 32 * SUPERSAMPLE
    image = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, px - 1, px - 1), radius=int(px * 0.22), fill=PAUSED_BG)
    bar_w, bar_h = int(px * 0.13), int(px * 0.40)
    gap = int(px * 0.10)
    x = px / 2 - bar_w - gap / 2
    y = px / 2 - bar_h / 2
    draw.rounded_rectangle((x, y, x + bar_w, y + bar_h), radius=max(1, bar_w // 3), fill=MUTED)
    x2 = px / 2 + gap / 2
    draw.rounded_rectangle((x2, y, x2 + bar_w, y + bar_h), radius=max(1, bar_w // 3), fill=MUTED)
    return image


def save_icon(image: Image.Image, path: Path, sizes=SIZES) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    variants = [image.resize((size, size), Image.LANCZOS) for size in sizes]
    variants[-1].save(path, format="ICO", sizes=[(s, s) for s in sizes],
                      append_images=variants[:-1])


def build_app_icon(font_path: Path) -> None:
    source = ROOT / "assets" / "brand" / "icon.png"
    if not source.exists():
        return
    image = Image.open(source).convert("RGBA")
    save_icon(image, ICONS / "app.ico", sizes=(16, 24, 32, 48, 64, 128, 256))


def main() -> int:
    font_path = pick_font()
    save_icon(draw_label("RU", font_path, INK), ICONS / "ru.ico")
    save_icon(draw_label("EN", font_path, INK), ICONS / "en.ico")
    save_icon(draw_label("RU", font_path, MUTED, SECURE_BG, accent=False, lock=True),
              ICONS / "ru_secure.ico")
    save_icon(draw_label("EN", font_path, MUTED, SECURE_BG, accent=False, lock=True),
              ICONS / "en_secure.ico")
    save_icon(draw_label("—", font_path, MUTED, PAUSED_BG, accent=False),
              ICONS / "other.ico")
    save_icon(draw_paused(font_path), ICONS / "paused.ico")
    build_app_icon(font_path)
    print(f"icons written to {ICONS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
