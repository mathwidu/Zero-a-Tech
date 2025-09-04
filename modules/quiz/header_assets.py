#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Header assets helpers
- ensure_topic_icon: tenta gerar um ícone via gpt-image-1 (cache em assets/icons/<slug>.png)
  e, se não possível, cai no fallback desenhado em PIL (topic_icons.ensure_topic_icon).
"""

from pathlib import Path
from typing import Optional
from PIL import Image
import base64
import os

ICONS_DIR = Path("assets/icons")
ICONS_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(s: str) -> str:
    import re, unicodedata
    s = (s or "topic").strip()
    s2 = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    s2 = re.sub(r'[^a-zA-Z0-9]+', '-', s2).strip('-').lower()
    return s2 or 'topic'


def _openai_generate_icon(topic: str, dest: Path, size: int = 256) -> bool:
    try:
        from dotenv import load_dotenv
        load_dotenv()
        from openai import OpenAI
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            return False
        client = OpenAI(api_key=key)
        prompt = (
            f"flat cartoon sticker icon of '{topic}', high-contrast, bold thick outline, "
            "centered subject, no text, no watermark, transparent or solid simple background, "
            "fun and friendly style, 1:1, minimal details"
        )
        size_str = f"{size}x{size}"
        resp = client.images.generate(model="gpt-image-1", prompt=prompt, size=size_str)
        b64 = resp.data[0].b64_json
        img_bytes = base64.b64decode(b64)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(img_bytes)
        # valida
        Image.open(dest).verify()
        return True
    except Exception:
        return False


def ensure_topic_icon(topic: str, size: int = 256) -> Path:
    from . import topic_icons  # fallback local
    slug = _slugify(topic)
    dest = ICONS_DIR / f"{slug}.png"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    if _openai_generate_icon(topic, dest, size=size):
        return dest
    # fallback
    p = topic_icons.ensure_topic_icon(topic, size=size)
    if Path(p).exists():
        return Path(p)
    # último recurso: cria um PNG vazio para não quebrar
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)
    return dest

