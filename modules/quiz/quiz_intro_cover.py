#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gera (uma vez) a imagem de abertura do vídeo por tema+dificuldade e salva em assets/quiz_covers/<topic>/<difficulty>.png.
Atualiza quiz_manifest.json com o caminho em 'intro_cover'.
"""

import os, json, base64
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
import argparse

OUT_DIR = Path("output-quiz")
MANIFEST = OUT_DIR / "quiz_manifest.json"
ASSETS_COVERS = Path("assets/quiz_covers")
FONT_PATH = Path("assets/fonts/LuckiestGuy-Regular.ttf")


def slugify(s: str) -> str:
    import re, unicodedata
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    s = re.sub(r'[^a-zA-Z0-9]+', '-', s).strip('-').lower()
    return s or "tema"


def difficulty_palette(diff: str) -> str:
    d = (diff or "").lower()
    if "fácil" in d or "facil" in d:
        return "paleta fria/azul-esverdeada, tons suaves"
    if "difícil" in d or "dificil" in d:
        return "paleta quente/vermelho-alaranjada intensa"
    return "paleta quente moderada/laranja-amarelada"


def build_prompt(topic: str, difficulty: str) -> str:
    return (
        f"capa abstrata para quiz de '{topic}', ícones/metáforas do tema, sem texto, "
        f"{difficulty_palette(difficulty)}, contraste alto, sem logotipos, 1024x1024, estilo flat moderno"
    )


def generate_cover(prompt: str, dest: Path) -> bool:
    load_dotenv()
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return False
    client = OpenAI(api_key=key)
    try:
        resp = client.images.generate(model="gpt-image-1", prompt=prompt, size="1024x1024")
        b64 = resp.data[0].b64_json
        img_bytes = base64.b64decode(b64)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(img_bytes)
        Image.open(dest).verify()
        return True
    except Exception:
        return False


def _load_font(size: int):
    try:
        return ImageFont.truetype(str(FONT_PATH), size)
    except Exception:
        return ImageFont.load_default()


def _textlen(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    try:
        return draw.textlength(text, font=font)
    except Exception:
        try:
            return font.getlength(text)
        except Exception:
            return len(text) * (font.size * 0.6 if hasattr(font, "size") else 12)


def overlay_intro_text(img_path: Path, topic: str, difficulty: str):
    """Escreve o texto de apresentação diretamente na capa, ajustando tamanhos para não cortar."""
    diff_map = {"fácil": "Nível Iniciante", "facil": "Nível Iniciante", "média": "Nível Intermediário", "media": "Nível Intermediário", "difícil": "Nível Expert", "dificil": "Nível Expert"}
    diff_label = diff_map.get(difficulty.lower(), difficulty)
    line1 = f"Desafio relâmpago de {topic}"
    line2 = f"{diff_label}"
    line3 = "Diz nos comentários quantas você acerta!"

    im = Image.open(img_path).convert("RGBA")
    W, H = im.size
    draw = ImageDraw.Draw(im, "RGBA")

    # área inferior para texto
    pad = int(min(W, H) * 0.04)
    box_w = int(W * 0.90)
    box_h = int(H * 0.40)
    x0 = (W - box_w) // 2
    y0 = H - box_h - pad

    # fontes base
    sz1 = int(H * 0.080)
    sz2 = int(H * 0.065)
    sz3 = int(H * 0.050)
    min_sz = max(14, int(H * 0.030))

    f1 = _load_font(sz1)
    f2 = _load_font(sz2)
    f3 = _load_font(sz3)
    max_line_w = box_w - 2 * pad

    # shrink-to-fit horizontal por linha
    def fit_width(text: str, font, min_size=min_sz):
        size = getattr(font, "size", 24) or 24
        while _textlen(draw, text, font) > max_line_w and size > min_size:
            size = max(min_size, int(size * 0.92))
            font = _load_font(size)
        return font

    f1 = fit_width(line1, f1)
    f2 = fit_width(line2, f2)
    f3 = fit_width(line3, f3)

    # calcula altura total com espaçamento
    line_h1 = int((getattr(f1, "size", 24)) * 1.2)
    line_h2 = int((getattr(f2, "size", 24)) * 1.2)
    line_h3 = int((getattr(f3, "size", 24)) * 1.2)
    total_h = line_h1 + line_h2 + line_h3 + pad * 2

    # se exceder a caixa, aumenta caixa até o limite ou reduz fontes proporcionalmente
    if total_h > box_h:
        # tenta aumentar caixa até 60% da altura
        new_box_h = min(int(H * 0.60), total_h)
        if new_box_h > box_h:
            box_h = new_box_h
            y0 = max(0, H - box_h - pad)
        else:
            # reduz fontes (fallback difícil de acontecer)
            factor = max(0.7, (box_h - pad * 2) / max(1, total_h - pad * 2))
            def resize_font(font):
                s = int(getattr(font, "size", 24) * factor)
                return _load_font(max(min_sz, s))
            f1, f2, f3 = resize_font(f1), resize_font(f2), resize_font(f3)
            line_h1 = int((getattr(f1, "size", 24)) * 1.2)
            line_h2 = int((getattr(f2, "size", 24)) * 1.2)
            line_h3 = int((getattr(f3, "size", 24)) * 1.2)
            total_h = line_h1 + line_h2 + line_h3 + pad * 2

    # fundo semitransparente
    draw.rounded_rectangle([x0, y0, x0 + box_w, y0 + box_h], radius=int(pad*0.6), fill=(0, 0, 0, 150))

    # helper centralizado
    def center_line(text: str, y: int, font, color=(255,255,255,255)):
        tw = _textlen(draw, text, font)
        x = int((W - tw) // 2)
        # contorno leve
        for dx in (-2, 2):
            for dy in (-2, 2):
                draw.text((x+dx, y+dy), text, font=font, fill=(0,0,0,180))
        draw.text((x, y), text, font=font, fill=color)

    # centraliza verticalmente dentro da caixa
    start_y = y0 + (box_h - (line_h1 + line_h2 + line_h3)) // 2
    y = start_y
    center_line(line1, y, f1)
    y += line_h1
    center_line(line2, y, f2, color=(255, 200, 80, 255))
    y += line_h2
    center_line(line3, y, f3)

    im.save(img_path)


def main():
    ap = argparse.ArgumentParser(description="Gera capa de abertura por tema+dificuldade")
    ap.add_argument("--force", action="store_true", help="Regenera mesmo se existir")
    args = ap.parse_args()

    if not MANIFEST.exists():
        raise SystemExit(f"Manifest não encontrado: {MANIFEST}")
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    topic = data.get("topic") or "Conhecimentos Gerais"
    difficulty = data.get("difficulty") or "média"

    topic_slug = slugify(topic)
    diff_slug = slugify(difficulty)
    out_path = ASSETS_COVERS / topic_slug / f"{diff_slug}.png"

    if out_path.exists() and not args.force:
        print(f"ℹ️ Capa já existe: {out_path}")
    else:
        prompt = build_prompt(topic, difficulty)
        ok = generate_cover(prompt, out_path)
        if not ok:
            raise SystemExit("Falha ao gerar capa — verifique OPENAI_API_KEY")
        print(f"✅ Capa gerada: {out_path}")

    # Sobrepõe o texto de apresentação diretamente na capa (idempotente)
    try:
        overlay_intro_text(out_path, topic, difficulty)
        print("🖊️ Texto de introdução desenhado na capa")
    except Exception as e:
        print(f"⚠️ Falha ao desenhar texto na capa: {e}")

    data["intro_cover"] = str(out_path)
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"🧾 Manifest atualizado com intro_cover")


if __name__ == "__main__":
    main()
