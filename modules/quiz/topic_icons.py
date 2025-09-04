#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Geração simples de ícones por tema (cartoon) via PIL.
Geramos uma vez em assets/icons/<slug>.png e reutilizamos.
"""

from pathlib import Path
from PIL import Image, ImageDraw

ASSETS_DIR = Path("assets/icons")
ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def _slug(s: str) -> str:
    import re, unicodedata
    s2 = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode('ascii')
    s2 = re.sub(r'[^a-zA-Z0-9]+', '-', s2).strip('-').lower()
    return s2 or 'topic'


def _canvas(size: int = 256) -> Image.Image:
    return Image.new("RGBA", (size, size), (0, 0, 0, 0))


def _draw_outline_circle(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, fill, outline=(0, 0, 0, 255), w: int = 8):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=outline, width=w)


def _icon_geografia(img: Image.Image):
    d = ImageDraw.Draw(img)
    cx, cy, r = 128, 128, 96
    _draw_outline_circle(d, cx, cy, r, (120, 200, 255, 255))
    # continentes simples
    d.polygon([(110, 80), (150, 90), (140, 130), (100, 120)], fill=(60, 160, 90, 255), outline=(0, 0, 0, 255))
    d.polygon([(150, 150), (180, 170), (160, 200), (130, 190)], fill=(60, 160, 90, 255), outline=(0, 0, 0, 255))


def _icon_programacao(img: Image.Image):
    d = ImageDraw.Draw(img)
    # engrenagens simples
    cx1, cy1, r1 = 95, 120, 50
    cx2, cy2, r2 = 160, 160, 38
    _draw_outline_circle(d, cx1, cy1, r1, (200, 220, 255, 255))
    _draw_outline_circle(d, cx2, cy2, r2, (220, 230, 255, 255))
    # dentes simplificados
    for cx, cy, r in [(cx1, cy1, r1), (cx2, cy2, r2)]:
        for i in range(8):
            ang = i * 360 / 8
            import math
            x0 = int(cx + (r + 6) * math.cos(math.radians(ang)))
            y0 = int(cy + (r + 6) * math.sin(math.radians(ang)))
            x1 = int(cx + (r + 16) * math.cos(math.radians(ang)))
            y1 = int(cy + (r + 16) * math.sin(math.radians(ang)))
            d.line([(x0, y0), (x1, y1)], fill=(0, 0, 0, 255), width=6)


def _icon_cultura(img: Image.Image):
    d = ImageDraw.Draw(img)
    # livro aberto
    d.rectangle([40, 70, 216, 186], fill=(250, 250, 255, 255), outline=(0, 0, 0, 255), width=8)
    d.line([(128, 70), (128, 186)], fill=(0, 0, 0, 255), width=6)
    d.line([(52, 86), (104, 86)], fill=(180, 180, 180, 255), width=5)
    d.line([(150, 86), (204, 86)], fill=(180, 180, 180, 255), width=5)


ICON_BUILDERS = {
    'geografia': _icon_geografia,
    'cultura': _icon_cultura,
    'programacao': _icon_programacao,
}


def ensure_topic_icon(topic: str, size: int = 256) -> Path:
    slug = _slug(topic or 'topic')
    dest = ASSETS_DIR / f"{slug}.png"
    if dest.exists():
        return dest
    img = _canvas(size)
    key = slug
    if key not in ICON_BUILDERS:
        # fallback: globo genérico
        _icon_geografia(img)
    else:
        ICON_BUILDERS[key](img)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)
    return dest

