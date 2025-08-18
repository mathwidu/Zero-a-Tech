#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, io, re, json, time, textwrap, random, base64, argparse
from pathlib import Path
from typing import Tuple, Optional
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
from openai import OpenAI

# ──────────────────────────────────────────────────────────────────────────────
# Paths / Consts
# ──────────────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output"
ASSETS  = ROOT / "assets"
FONTS   = ASSETS / "fonts"

# Ajuste estes caminhos conforme seus arquivos reais
P_JOAO = ASSETS / "personagens" / "joao.png"
P_ZEB  = ASSETS / "personagens" / "zebot.png"
FONT_PATH = FONTS / "LuckiestGuy-Regular.ttf"

MANIFEST = OUT_DIR / "capa_manifest.json"
CAPA_PNG = OUT_DIR / "capa_tiktok.png"
CAPA_JPG = OUT_DIR / "capa_tiktok.jpg"

NOTICIA_ESCOLHIDA = OUT_DIR / "noticia_escolhida.json"
DIALOGO_JSON      = OUT_DIR / "dialogo_estruturado.json"

FINAL_SIZE = (1080, 1920)       # TikTok vertical
BG_SIZE    = (1024, 1536)       # tamanho suportado pela API (vertical)

# ──────────────────────────────────────────────────────────────────────────────
# Setup
# ──────────────────────────────────────────────────────────────────────────────
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Defina OPENAI_API_KEY no .env")
client = OpenAI(api_key=OPENAI_API_KEY)
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def sanitize_topic(s: str) -> str:
    if not s: return ""
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\b(Apple|iPhone|Samsung|Galaxy|PlayStation|Xbox|Nintendo|Netflix|Spotify|Google|YouTube)\b",
               "marca/plataforma genérica", s, flags=re.I)
    return s

def infer_tema_fallback() -> Optional[str]:
    if NOTICIA_ESCOLHIDA.exists():
        try:
            data = json.loads(NOTICIA_ESCOLHIDA.read_text(encoding="utf-8"))
            t = data.get("title") or data.get("titulo")
            if t: return t
        except Exception:
            pass
    if DIALOGO_JSON.exists():
        try:
            arr = json.loads(DIALOGO_JSON.read_text(encoding="utf-8"))
            for it in arr:
                for k in ("tema","topico","assunto","titulo"):
                    if k in it and it[k]:
                        return str(it[k])
            if isinstance(arr, list) and arr:
                maybe = arr[0].get("fala") or arr[0].get("titulo")
                if maybe: return maybe
        except Exception:
            pass
    return None

def choose_palette() -> Tuple[Tuple[int,int,int], Tuple[int,int,int]]:
    # (fill, stroke)
    options = [
        ((255,255,255), (0,0,0)),
        ((255,255,0),   (0,0,0)),
        ((0,0,0),       (255,255,255)),
        ((255,80,80),   (0,0,0)),
        ((80,200,255),  (0,0,0)),
    ]
    return random.choice(options)

def make_shadow(img: Image.Image, blur=10, expand=12, opacity=140) -> Image.Image:
    alpha = img.split()[-1]
    bg = Image.new("RGBA", (img.width + expand*2, img.height + expand*2), (0,0,0,0))
    shadow = Image.new("RGBA", bg.size, (0,0,0,0))
    s = Image.new("L", bg.size, 0)
    s.paste(alpha, (expand, expand))
    s = s.filter(ImageFilter.GaussianBlur(blur))
    shadow.putalpha(s.point(lambda p: min(p, opacity)))
    return shadow

def paste_with_shadow(canvas: Image.Image, sprite: Image.Image, center_xy: Tuple[int,int], scale=1.0, rotate_deg=0):
    sp = sprite.copy()
    if scale != 1.0:
        w = max(1, int(sp.width * scale))
        h = max(1, int(sp.height * scale))
        sp = sp.resize((w,h), Image.LANCZOS)
    if rotate_deg:
        sp = sp.rotate(rotate_deg, expand=True, resample=Image.BICUBIC)
    sh = make_shadow(sp, blur=18, expand=24, opacity=120)
    cx, cy = center_xy
    pos = (cx - sp.width//2, cy - sp.height//2)
    pos_sh = (pos[0]-12, pos[1]+18)
    canvas.alpha_composite(sh,  dest=pos_sh)
    canvas.alpha_composite(sp,  dest=pos)

# — Texto ————————————————————————————————————————————————————————
def wrap_text(text: str, width_chars=20, max_lines=3, add_ellipsis=False) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    lines = textwrap.wrap(text, width=width_chars, break_long_words=False, break_on_hyphens=True)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        if add_ellipsis:
            lines[-1] = (lines[-1] + "…").strip()
    return "\n".join(lines)

def _measure_line(draw: ImageDraw.ImageDraw, line: str, font: ImageFont.FreeTypeFont):
    if hasattr(draw, "textbbox"):
        l, t, r, b = draw.textbbox((0,0), line, font=font)
        return r-l, b-t
    w, h = font.getsize(line)
    return w, h

def measure_multiline(draw: ImageDraw.ImageDraw, txt: str, font: ImageFont.FreeTypeFont, spacing: int):
    lines = txt.split("\n") if txt else [""]
    widths, heights = [], []
    for line in lines:
        w, h = _measure_line(draw, line, font)
        widths.append(w)
        heights.append(h)
    total_h = sum(heights) + spacing * (len(lines)-1 if len(lines) > 1 else 0)
    return (max(widths) if widths else 0), total_h

def draw_multiline_center(canvas: Image.Image, txt: str, top: int,
                          fill=(255,255,0), stroke=(0,0,0), stroke_w=12,
                          max_font=148, min_font=60, max_width_ratio=0.97):
    draw = ImageDraw.Draw(canvas)
    W, H = canvas.size
    chosen_font = None; w = h = 0
    for size in range(max_font, min_font-1, -4):
        font = ImageFont.truetype(str(FONT_PATH), size=size)
        w, h = measure_multiline(draw, txt, font, spacing=int(size*0.12))
        if w <= int(W*max_width_ratio):
            chosen_font = font
            break
    if chosen_font is None:
        chosen_font = ImageFont.truetype(str(FONT_PATH), size=min_font)
        w, h = measure_multiline(draw, txt, chosen_font, spacing=int(min_font*0.12))
    x = (W - w)//2
    draw.multiline_text((x, top), txt, font=chosen_font, fill=fill,
                        stroke_width=stroke_w, stroke_fill=stroke,
                        align="center", spacing=int(chosen_font.size*0.12))
    return x, top, w, h, chosen_font

def draw_tag(canvas: Image.Image, text: str, anchor_xy: Tuple[int,int],
             font: ImageFont.FreeTypeFont, pad_x=26, pad_y=10,
             fill=(0,0,0), text_fill=(255,255,255), radius=28):
    if not text: return
    draw = ImageDraw.Draw(canvas)
    w, h = draw.textbbox((0,0), text, font=font)[2:]
    box_w = w + pad_x*2
    box_h = h + pad_y*2
    x, y = anchor_xy
    capsule = Image.new("RGBA", (box_w, box_h), (0,0,0,0))
    d = ImageDraw.Draw(capsule)
    d.rounded_rectangle([0,0,box_w-1,box_h-1], radius=radius, fill=fill)
    glow = capsule.filter(ImageFilter.GaussianBlur(8))
    canvas.alpha_composite(glow, (x, y))
    canvas.alpha_composite(capsule, (x, y))
    draw.text((x+pad_x, y+pad_y-2), text, font=font, fill=text_fill)

def prompt_background(tema: str) -> str:
    base = sanitize_topic(tema)
    return (
        f"fundo vertical vibrante no tema: {base}. foco em formas abstratas e ícones genéricos do assunto, "
        "sem texto, sem logotipos, sem marcas registradas, estilo editorial moderno, iluminação dramática, "
        "cores chamativas porém equilibradas, profundidade sutil, composição limpa, 1024x1536"
    )

def gen_background_via_openai(prompt: str, tries=3) -> Image.Image:
    last_err = None
    for attempt in range(1, tries+1):
        try:
            resp = client.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                size=f"{BG_SIZE[0]}x{BG_SIZE[1]}",
                background="transparent"
            )
            b64 = resp.data[0].b64_json
            img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA")
            return img
        except Exception as e:
            last_err = e
            time.sleep(1.0 * attempt)
    raise last_err

def resize_cover(img: Image.Image, target_size: Tuple[int,int]) -> Image.Image:
    tw, th = target_size
    iw, ih = img.size
    scale = max(tw/iw, th/ih)
    nw, nh = int(iw*scale), int(ih*scale)
    resized = img.resize((nw, nh), Image.LANCZOS)
    left = max(0, (nw - tw)//2); top = max(0, (nh - th)//2)
    return resized.crop((left, top, left+tw, top+th))

# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Gerador de capa TikTok (João & Zé Bot)")
    ap.add_argument("--tema", type=str, default=None, help="Tema do fundo (se omitido, tenta inferir)")
    ap.add_argument("--titulo", type=str, default=None, help="Título principal")
    ap.add_argument("--subtitulo", type=str, default="", help="Subtítulo (opcional)")
    ap.add_argument("--destaque", type=str, default="", help="Palavra/frase de destaque em cápsula")
    ap.add_argument("--blur", type=int, default=0, help="Blur no fundo (0=sem blur, sugestão 4..8)")
    ap.add_argument("--flipzebot", action="store_true", help="Espelha o Zé Bot")
    ap.add_argument("--flipjoao", action="store_true", help="Espelha o João")
    ap.add_argument("--chars-scale", type=float, default=1.0, help="Escala global dos personagens")
    ap.add_argument("--chars-shift-y", type=int, default=0, help="Deslocamento vertical dos personagens (px)")
    # NOVOS CONTROLES DE TÍTULO
    ap.add_argument("--title-width-chars", type=int, default=20, help="Chars por linha do título (wrap)")
    ap.add_argument("--title-max-lines", type=int, default=3, help="Máximo de linhas do título")
    ap.add_argument("--title-max-width", type=float, default=0.97, help="Largura máx. do título em fração da largura (0..1)")
    ap.add_argument("--ellipsis", action="store_true", help="Adicionar reticências se o título exceder linhas")
    args = ap.parse_args()

    tema = args.tema or infer_tema_fallback() or "Tecnologia em destaque"
    titulo = args.titulo or tema
    subtitulo = args.subtitulo or ""

    # 1) Fundo 1024x1536 → cover 1080x1920 (+blur opcional)
    bg_prompt = prompt_background(tema)
    bg = gen_background_via_openai(bg_prompt)
    bg_cover = resize_cover(bg, FINAL_SIZE)
    if args.blur and args.blur > 0:
        bg_cover = bg_cover.filter(ImageFilter.GaussianBlur(radius=min(25, max(0, args.blur))))
    canvas = Image.new("RGBA", FINAL_SIZE, (0,0,0,255))
    canvas.alpha_composite(bg_cover, (0,0))

    # 2) Personagens (distribuição)
    if not P_JOAO.exists() or not P_ZEB.exists():
        raise FileNotFoundError("PNG dos personagens não encontrado. Verifique os caminhos P_JOAO e P_ZEB.")
    joao = Image.open(P_JOAO).convert("RGBA")
    zeb  = Image.open(P_ZEB).convert("RGBA")
    if args.flipjoao: joao = ImageOps.mirror(joao)
    if args.flipzebot: zeb  = ImageOps.mirror(zeb)

    base_h = int(FINAL_SIZE[1] * 0.56)
    base_h = int(base_h * max(0.6, min(1.6, args.chars_scale)))
    def scale_to_h(img, h):
        r = h / img.height
        return img.resize((max(1,int(img.width*r)), max(1,int(img.height*r))), Image.LANCZOS)
    joao_s = scale_to_h(joao, base_h)
    zeb_s  = scale_to_h(zeb,  base_h)

    cy = int(FINAL_SIZE[1] * 0.66) + args.chars_shift_y
    paste_with_shadow(canvas, joao_s, center_xy=(int(FINAL_SIZE[0]*0.28), cy),
                      scale=1.0, rotate_deg=random.choice([-3,-2,-1,0,1,2,3]))
    paste_with_shadow(canvas, zeb_s,  center_xy=(int(FINAL_SIZE[0]*0.72), cy),
                      scale=1.0, rotate_deg=random.choice([-3,-2,-1,0,1,2,3]))

    # 3) Título (grande) + Subtítulo
    title_wrapped = wrap_text(
        titulo,
        width_chars=max(10, args.title_width_chars),
        max_lines=max(1, args.title_max_lines),
        add_ellipsis=args.ellipsis
    )
    fill_rgb, stroke_rgb = choose_palette()
    tx, ty, tw, th, title_font = draw_multiline_center(
        canvas, title_wrapped, top=int(FINAL_SIZE[1]*0.06),
        fill=fill_rgb, stroke=stroke_rgb, stroke_w=12,
        max_font=148, min_font=60, max_width_ratio=max(0.80, min(1.0, args.title_max_width))
    )

    if subtitulo.strip():
        draw = ImageDraw.Draw(canvas)
        sub_size = max(48, int(title_font.size * 0.52))
        sub_font = ImageFont.truetype(str(FONT_PATH), size=sub_size)
        sub_text = wrap_text(subtitulo, width_chars=22, max_lines=2, add_ellipsis=args.ellipsis)
        sw, sh = measure_multiline(draw, sub_text, sub_font, spacing=int(sub_size*0.10))
        sx = (FINAL_SIZE[0]-sw)//2
        sy = ty + th + int(sub_size*0.3)
        draw.multiline_text((sx, sy), sub_text, font=sub_font,
                            fill=(255,255,255), stroke_width=10, stroke_fill=(0,0,0),
                            align="center", spacing=int(sub_size*0.10))

    # 4) Tag de destaque (opcional)
    if getattr(args, "destaque", "").strip():
        tag_font = ImageFont.truetype(str(FONT_PATH), size=max(44, int(title_font.size*0.55)))
        tag_x = min(FINAL_SIZE[0]-360, tx + tw + 18)
        tag_y = max(20, ty - 12)
        draw_tag(canvas, args.destaque.strip(), (tag_x, tag_y), tag_font,
                 pad_x=22, pad_y=10, fill=(0,0,0,190), text_fill=(255,255,0))

    # 5) Exporta
    canvas.save(CAPA_PNG, "PNG")
    canvas.convert("RGB").save(CAPA_JPG, "JPEG", quality=92)

    meta = {
        "tema": tema,
        "titulo": titulo,
        "subtitulo": subtitulo,
        "destaque": getattr(args, "destaque", ""),
        "blur": args.blur,
        "bg_prompt": bg_prompt,
        "api_bg_size": f"{BG_SIZE[0]}x{BG_SIZE[1]}",
        "final_size": {"w": FINAL_SIZE[0], "h": FINAL_SIZE[1]},
        "title_params": {
            "width_chars": args.title_width_chars,
            "max_lines": args.title_max_lines,
            "max_width_ratio": args.title_max_width,
            "ellipsis": args.ellipsis
        },
        "arquivos": {"png": str(CAPA_PNG), "jpg": str(CAPA_JPG)},
        "personagens": {"joao": str(P_JOAO), "zebot": str(P_ZEB)}
    }
    MANIFEST.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Capa gerada: {CAPA_PNG}")
    print(f"🧾 Manifest: {MANIFEST}")

if __name__ == "__main__":
    main()
