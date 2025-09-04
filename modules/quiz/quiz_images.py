#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gera imagens representativas para cada pergunta do quiz.
- Para simplicidade offline, criamos cards com emoji e gradiente por categoria.
- Saída: output-quiz/images/q_XX.png (uma por pergunta)
"""

import json
from pathlib import Path
from typing import Tuple
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path("output-quiz")
IMAGES_DIR = OUT_DIR / "images"
MANIFEST = OUT_DIR / "quiz_manifest.json"
FONT_PATH = "assets/fonts/LuckiestGuy-Regular.ttf"
ASSETS_QUIZ = Path("assets/quiz")


CATEGORY_STYLE = {
    "casais": {"emoji": "❤️", "bg": ((255, 70, 90), (255, 170, 120))},
    "filmes": {"emoji": "🎬", "bg": ((40, 50, 70), (90, 110, 160))},
    "animes": {"emoji": "🗡️", "bg": ((45, 40, 80), (140, 90, 200))},
    "politica": {"emoji": "🏛️", "bg": ((20, 70, 140), (60, 140, 210))},
}


def ler_manifest():
    if not MANIFEST.exists():
        raise FileNotFoundError(f"Manifest não encontrado: {MANIFEST}")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def ler_fonte(size: int):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def ler_estilo(category: str) -> Tuple[str, Tuple[int, int, int], Tuple[int, int, int]]:
    cat = (category or "").lower()
    cfg = CATEGORY_STYLE.get(cat) or CATEGORY_STYLE["casais"]
    emoji = cfg["emoji"]
    c1, c2 = cfg["bg"]
    return emoji, c1, c2


def gradiente(size, c1, c2):
    w, h = size
    img = Image.new("RGB", (w, h), c1)
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(c1[0] * (1 - t) + c2[0] * t)
        g = int(c1[1] * (1 - t) + c2[1] * t)
        b = int(c1[2] * (1 - t) + c2[2] * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    return img


def desenhar_card(path: Path, category: str, idx: int, texto_curto: str, size=(720, 720)):
    emoji, c1, c2 = ler_estilo(category)
    img = gradiente(size, c1, c2).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Moldura e título
    w, h = size
    draw.rectangle([10, 10, w - 10, h - 10], outline=(255, 255, 255, 180), width=6)
    font_title = ler_fonte(int(min(w, h) * 0.10))
    title = f"Pergunta {idx}"
    tw = draw.textlength(title, font=font_title)
    draw.text(((w - tw) // 2, int(h * 0.06)), title, font=font_title, fill=(255, 255, 255))

    # Emoji central
    font_emoji = ler_fonte(int(min(w, h) * 0.36))
    ew = draw.textlength(emoji, font=font_emoji)
    draw.text(((w - ew) // 2, int(h * 0.28)), emoji, font=font_emoji, fill=(255, 255, 255))

    # Subtítulo curto (resumo da pergunta)
    font_sub = ler_fonte(int(min(w, h) * 0.07))
    txt = texto_curto
    if len(txt) > 28:
        txt = txt[:27] + "…"
    sw = draw.textlength(txt, font=font_sub)
    draw.text(((w - sw) // 2, int(h * 0.72)), txt, font=font_sub, fill=(0, 0, 0))

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def resumo_pergunta(texto: str) -> str:
    # remove prefixo "Pergunta X:"
    t = texto
    if ":" in t:
        t = t.split(":", 1)[1].strip()
    # pega até a primeira interrogação, se houver
    if "?" in t:
        t = t.split("?", 1)[0] + "?"
    return t


def main():
    data = ler_manifest()
    cat = data.get("category", "casais")
    segs = data.get("segments", [])
    # tenta usar imagens pré-existentes no host: assets/quiz/<categoria>/*
    asset_dir = ASSETS_QUIZ / cat
    asset_files = []
    if asset_dir.exists():
        asset_files = sorted([p for p in asset_dir.glob("*.*") if p.suffix.lower() in {".png", ".jpg", ".jpeg"}])
    q_idx = 0
    for seg in segs:
        if seg.get("type") == "Q":
            q_idx += 1
            txt = seg.get("text", "Pergunta")
            # prioridade: usar imagem do assets/quiz/<categoria>
            if q_idx <= len(asset_files):
                seg["image_path"] = str(asset_files[q_idx - 1])
            else:
                short = resumo_pergunta(txt)
                out = IMAGES_DIR / f"q_{q_idx:02d}.png"
                desenhar_card(out, cat, q_idx, short)
                seg["image_path"] = str(out)

    # salva manifest atualizado com image_path
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Imagens geradas em {IMAGES_DIR}")


if __name__ == "__main__":
    main()
