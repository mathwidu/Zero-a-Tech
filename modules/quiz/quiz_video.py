#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Compositor de vídeo para o módulo de quiz:
- Usa um vídeo de fundo em assets/videos_fundo/*.mp4 (corta/cobre para 1080x1920).
- Sobrepõe textos grandes por segmento (HOOK, Q, CTA) alinhados ao áudio quiz_XX.mp3.
- Exporta output-quiz/quiz_final.mp4.
"""

import os, glob, json, random, math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import VideoFileClip, CompositeVideoClip
import argparse
try:
    from moviepy import AudioFileClip, AudioClip, CompositeAudioClip, ImageClip, VideoClip, concatenate_videoclips, vfx
except Exception:
    from moviepy.editor import AudioFileClip, AudioClip, CompositeAudioClip, ImageClip, VideoClip, concatenate_videoclips, vfx  # compat


OUT_DIR = Path("output-quiz")
MANIFEST = OUT_DIR / "quiz_manifest.json"
FINAL_MP4 = OUT_DIR / "quiz_final.mp4"

TARGET_W, TARGET_H = 1080, 1920
FONT_PATH = "assets/fonts/LuckiestGuy-Regular.ttf"

# Durações-alvo por segmento para ritmo (~1 min com 5 perguntas)
DEFAULT_DURATIONS = {
    "HOOK": 2.5,
    "Q": 3.0,
    "Q_ASK": 1.5,
    "COUNTDOWN": 5.0,
    "CTA_SHORT": 2.0,
    "REVEAL": 4.0,
    "REVEAL_EXPLAIN": 5.0,
    "CTA": 5.0,
}

# Utilidades de cor
def _hex_to_rgb(a: str) -> tuple:
    s = a.strip().lstrip('#')
    if len(s) == 3:
        s = ''.join([c*2 for c in s])
    r = int(s[0:2], 16)
    g = int(s[2:4], 16)
    b = int(s[4:6], 16)
    return (r, g, b)

def _lerp_color(c1: tuple, c2: tuple, t: float) -> tuple:
    t = max(0.0, min(1.0, float(t)))
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )

def _palette_stops(hex_list: list[str]) -> list[tuple]:
    cols = [ _hex_to_rgb(x) for x in hex_list if x.strip() ]
    if not cols:
        cols = [(79,195,247),(255,112,67)]  # frio->quente
    return cols

def _with_start(clip, t):
    return clip.with_start(t) if hasattr(clip, "with_start") else clip.set_start(t)

def _with_end(clip, t):
    return clip.with_end(t) if hasattr(clip, "with_end") else clip.set_end(t)

def _with_duration(clip, d):
    return clip.with_duration(d) if hasattr(clip, "with_duration") else clip.set_duration(d)

def _with_position(clip, pos):
    return clip.with_position(pos) if hasattr(clip, "with_position") else clip.set_position(pos)

def _with_audio(clip, audio_clip):
    return clip.with_audio(audio_clip) if hasattr(clip, "with_audio") else clip.set_audio(audio_clip)

def _subclip(clip, t0, t1):
    return clip.subclipped(t0, t1) if hasattr(clip, "subclipped") else clip.subclip(t0, t1)

def _with_mask(clip, mask_clip):
    try:
        if hasattr(clip, "with_mask"):
            return clip.with_mask(mask_clip)
        return clip.set_mask(mask_clip)
    except Exception:
        try:
            clip.mask = mask_clip
            return clip
        except Exception:
            return clip


def _volumex_clip(clip, gain: float):
    """Compat: aplica ganho em um AudioClip via método ou fx."""
    try:
        return clip.volumex(gain)
    except Exception:
        try:
            from moviepy.audio.fx.volumex import volumex as afx_volumex
            return afx_volumex(clip, gain)
        except Exception:
            return clip


def _resize_clip(clip, factor=None, newsize=None):
    if hasattr(clip, "resized"):
        if factor is not None:
            return clip.resized(factor)
        return clip.resized(newsize=newsize)
    else:
        if factor is not None:
            return clip.resize(factor)
        return clip.resize(newsize=newsize)


def normalize_bg(clip, target_w, target_h, mode: str = "crop"):
    w, h = clip.size
    if mode == "blur":
        # BG: cobre e aplica pequenos ajustes/blur
        scale_bg = max(target_w / w, target_h / h)
        bg = _resize_clip(clip, factor=scale_bg)
        try:
            bg = vfx.gaussian_blur(bg, sigma=12)
        except Exception:
            pass
        try:
            bg = vfx.colorx(bg, 0.92)
        except Exception:
            pass
        # FG: cabe inteiro (fit)
        scale_fit = min(target_w / w, target_h / h)
        fg = _resize_clip(clip, factor=scale_fit)
        fg = _with_position(fg, ("center", "center"))
        comp = CompositeVideoClip([_with_position(bg, ("center", "center")), fg], size=(target_w, target_h))
        return _with_duration(comp, clip.duration)
    # default: crop/cover (preenche sem bordas)
    scale = max(target_w / w, target_h / h)
    scaled = _resize_clip(clip, factor=scale)
    x = int((target_w - scaled.w) / 2)
    y = int((target_h - scaled.h) / 2)
    pos = _with_position(scaled, (x, y))
    comp = CompositeVideoClip([pos], size=(target_w, target_h))
    return _with_duration(comp, clip.duration)


def render_text_box(texto: str, width: int, height: int, kind: str):
    """Gera uma imagem RGBA com texto centralizado. Estilo varia por 'kind'."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        # tamanho relativo por tipo
        base = 72 if kind == "Q" else 64 if kind == "HOOK" else 56
        font = ImageFont.truetype(FONT_PATH, base)
    except Exception:
        font = ImageFont.load_default()

    def _textlength(t: str, f: ImageFont.FreeTypeFont) -> float:
        try:
            return draw.textlength(t, font=f)
        except Exception:
            try:
                return f.getlength(t)
            except Exception:
                return len(t) * (f.size * 0.6 if hasattr(f, "size") else 10)

    def wrap_with_font(fnt):
        words = (texto or "").split()
        lines, cur, cur_w = [], [], 0
        max_w = int(width * 0.85)
        for w in words:
            ww = _textlength(w + " ", fnt)
            if cur_w + ww > max_w and cur:
                lines.append(" ".join(cur))
                cur, cur_w = [w], ww
            else:
                cur.append(w)
                cur_w += ww
        if cur:
            lines.append(" ".join(cur))
        return lines

    # Shrink-to-fit vertical se necessário
    lines = wrap_with_font(font)
    line_h = int((getattr(font, "size", 48)) * 1.3)
    total_h = len(lines) * line_h
    max_h = int(height * 0.98)
    min_size = max(12, int((getattr(font, "size", 48)) * 0.55))
    while total_h > max_h and getattr(font, "size", 48) > min_size:
        new_size = max(min_size, int(getattr(font, "size", 48) * 0.92))
        try:
            font = ImageFont.truetype(FONT_PATH, new_size)
        except Exception:
            font = ImageFont.load_default()
        lines = wrap_with_font(font)
        line_h = int((getattr(font, "size", 48)) * 1.3)
        total_h = len(lines) * line_h

    # caixa vertical
    y0 = max(0, (height - total_h) // 2)

    # cores por tipo
    color = (255, 255, 255)
    stroke = (0, 0, 0)
    if kind == "Q":
        color = (255, 165, 0)  # laranja
    elif kind == "HOOK":
        color = (186, 255, 85)  # verde claro
    else:  # CTA
        color = (255, 255, 255)

    for i, line in enumerate(lines):
        wline = _textlength(line, font)
        x = (width - wline) // 2
        y = y0 + i * line_h
        # contorno p/ legibilidade
        for dx in (-3, 3):
            for dy in (-3, 3):
                draw.text((x + dx, y + dy), line, font=font, fill=stroke)
        draw.text((x, y), line, font=font, fill=color)

    return ImageClip(np.array(img))


def render_question_card(width: int, height: int, text: str):
    """Cartão branco com borda grossa e sombra leve, texto centralizado (2-3 linhas).
    Usa a mesma família de fonte das alternativas para manter consistência visual.
    """
    img = Image.new("RGBA", (width, height), (0,0,0,0))
    base = Image.new("RGBA", (width, height), (0,0,0,0))
    draw = ImageDraw.Draw(base)
    radius = max(28, int(min(width, height) * 0.10))
    # sombra
    shadow = Image.new("RGBA", (width, height), (0,0,0,0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle([6,8,width-2,height-2], radius=radius, fill=(0,0,0,110))
    # cartão
    draw.rounded_rectangle([0,0,width-6,height-6], radius=radius, fill=(255,255,255,255), outline=(0,0,0,255), width=12)

    # cálculo de texto
    # Fonte: mesma estratégia das alternativas
    options_font_path = os.getenv("QUIZ_OPTIONS_FONT", "")
    font = None
    chosen_font_path = None
    for cand in [options_font_path, "DejaVuSans-Bold.ttf", FONT_PATH]:
        if not cand:
            continue
        try:
            # Começa 30% menor para evitar cortes em perguntas longas
            font = ImageFont.truetype(cand, max(28, int(height * 0.336)))
            chosen_font_path = cand
            break
        except Exception:
            font = None
    if font is None:
        font = ImageFont.load_default()
    def textlen(t: str, f):
        try:
            return ImageDraw.Draw(Image.new("RGBA", (1,1))).textlength(t, font=f)
        except Exception:
            return f.getlength(t) if hasattr(f,"getlength") else len(t)* (getattr(f,"size",16)*0.6)
    pad = max(16, int(height*0.16))
    avail_w = width - pad*2
    base_fs = getattr(font,"size",24)
    # Permite reduzir bastante se necessário para sempre caber
    min_fs = max(8, int(height * 0.08))
    # Flexibiliza número de linhas (até 5) para sempre caber
    max_lines = 3
    fcur = font
    def wrap_lines(text: str, f):
        words = (text or "").split()
        lines, cur, cur_w = [], [], 0
        for w in words:
            ww = textlen(w+" ", f)
            if cur_w + ww > avail_w and cur:
                lines.append(" ".join(cur))
                cur, cur_w = [w], ww
            else:
                cur.append(w)
                cur_w += ww
        if cur:
            lines.append(" ".join(cur))
        return lines
    tries = 0
    while True:
        lines = wrap_lines(text, fcur)
        try:
            ascent, descent = fcur.getmetrics()
            line_h = int((ascent + descent) * 1.0)
        except Exception:
            line_h = int((getattr(fcur,"size",16))*1.12)
        total_h = len(lines)*line_h
        if len(lines)<=max_lines and total_h <= height - pad*2:
            break
        next_sz = int(getattr(fcur,"size",base_fs)*0.90)
        if next_sz >= min_fs:
            # mantém a mesma família de fonte encontrada no início
            if chosen_font_path:
                try:
                    fcur = ImageFont.truetype(chosen_font_path, next_sz)
                except Exception:
                    fcur = ImageFont.load_default()
            else:
                try:
                    fcur = ImageFont.truetype(FONT_PATH, next_sz)
                except Exception:
                    fcur = ImageFont.load_default()
            continue
        # aumenta número de linhas gradualmente até 5
        if max_lines < 5:
            max_lines += 1
            try:
                fcur = ImageFont.truetype(chosen_font_path or FONT_PATH, getattr(font, "size", base_fs))
            except Exception:
                fcur = ImageFont.load_default()
            continue
        # último recurso: permitir reduzir abaixo de min_fs (até 8px) sem elipse
        if getattr(fcur, "size", base_fs) > 8:
            tiny = max(8, int(getattr(fcur, "size", base_fs) * 0.9))
            try:
                fcur = ImageFont.truetype(chosen_font_path or FONT_PATH, tiny)
            except Exception:
                fcur = ImageFont.load_default()
            tries += 1
            if tries < 3:
                continue
        # se ainda não coube, aceita mais compactação vertical leve
        try:
            ascent, descent = fcur.getmetrics()
            line_h = max(10, int((ascent + descent) * 0.95))
        except Exception:
            line_h = max(10, int((getattr(fcur,"size",16)) * 1.0))
        break
    try:
        ascent, descent = fcur.getmetrics()
        lh = int((ascent + descent) * 1.0)
        baseline_adjust = max(0, int(descent * 0.2))
        total = len(lines) * lh
        y = (height - total)//2 + baseline_adjust
    except Exception:
        y = (height - len(lines)*int((getattr(fcur,"size",16))*1.12))//2
    for ln in lines:
        lw = textlen(ln, fcur)
        x = (width - lw)//2
        # sem stroke pesado — mesmo estilo das alternativas
        ImageDraw.Draw(base).text((x,y), ln, font=fcur, fill=(0,0,0,255))
        try:
            ascent, descent = fcur.getmetrics()
            y += int((ascent + descent) * 1.0)
        except Exception:
            y += int((getattr(fcur,"size",16))*1.12)

    img = Image.alpha_composite(img, shadow)
    img = Image.alpha_composite(img, base)
    return ImageClip(np.array(img))


def render_header(width: int, height: int, topic: str, duration: float,
                  icon_path: str | None = None,
                  anim: str = "bulb",
                  # Right-side animation (legacy: video_dir)
                  video_dir: str | None = None,
                  right_video: str | None = None,
                  # Left-side topic animation
                  left_video: str | None = None,
                  video_scale: float = 0.9,
                  chroma_thr: int = 60,
                  bg_clip: VideoFileClip | None = None,
                  # Animated border around header (glass frame)
                  header_border: bool = True,
                  header_border_colors: list[str] | None = None,
                  header_border_stroke: int = 8,
                  header_border_mode: str = "spin",
                  header_border_speed: float = 0.8,
                  # Insets to create spacing from video edges (pixels)
                  inset_x: int = 0,
                  inset_y: int = 0,
                  # Glass look tuning
                  glass_alpha: int = 92,
                  blur_sigma: float = 6.0,
                  glass_backdrop: bool = False,
                 ):
    """Header com título central (topic), ícone à esquerda (opcional) e área de animação à direita.
    Retorna um VideoClip RGBA do tamanho (width x height).
    """
    # Título com shrink-to-fit dentro do painel para evitar cortes
    def _load_font(sz: int):
        try:
            return ImageFont.truetype(FONT_PATH, sz)
        except Exception:
            return ImageFont.load_default()
    title_font = _load_font(max(18, int(height * 0.26)))

    # Base: GLASS (backdrop blur do vídeo por trás, se disponível)
    base = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(base)
    # área interna do painel (com margens)
    panel_left = max(0, int(inset_x))
    panel_top = max(0, int(inset_y))
    panel_right = max(panel_left + 4, width - int(inset_x))
    panel_bottom = max(panel_top + 4, height - int(inset_y))
    panel_w = max(4, panel_right - panel_left)
    panel_h = max(4, panel_bottom - panel_top)
    radius = max(8, int(min(panel_w, panel_h) * 0.22))
    # backdrop blur: recorta o topo do bg_clip se fornecido
    glass_layers = []
    try:
        from moviepy import vfx as _vfx
    except Exception:
        from moviepy.editor import vfx as _vfx
    if bg_clip is not None and glass_backdrop:
        try:
            crop = bg_clip.fx(_vfx.crop, x1=0, y1=0, x2=width, y2=height)
            blur = _vfx.gaussian_blur(crop, sigma=max(0.0, float(blur_sigma)))
            glass_layers.append(_with_start(blur, 0))
        except Exception:
            pass
    # Painel do header — agora fundo branco igual ao cartão da pergunta
    panel = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    stroke_w = max(6, int(min(panel_w, panel_h) * 0.035))
    pd.rounded_rectangle([panel_left, panel_top, panel_right, panel_bottom], radius=radius,
                         fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=stroke_w)
    # converte RGBA -> RGB + máscara para preservar transparência corretamente
    _panel_np = np.array(panel)
    # Use RGB branco para evitar halos pretos nas bordas (alpha aplica o formato do painel)
    _panel_rgb = np.full((_panel_np.shape[0], _panel_np.shape[1], 3), 255, dtype=np.uint8)
    _panel_a = (_panel_np[..., 3].astype("float32") / 255.0)
    _panel_clip = ImageClip(_panel_rgb).with_duration(duration)
    try:
        _panel_mask = ImageClip(_panel_a, ismask=True).with_duration(duration)
    except TypeError:
        _panel_mask = ImageClip(_panel_a).with_duration(duration)
        try:
            _panel_mask = _panel_mask.set_is_mask(True)
        except Exception:
            try:
                _panel_mask.ismask = True
            except Exception:
                pass
    _panel_clip = _with_mask(_panel_clip, _panel_mask)
    glass_layers.append(_panel_clip)
    # removi a onda decorativa e linha inferior para um visual mais clean

    pad = max(8, int(panel_h * 0.12))
    # Icone à esquerda (com leve bob e rotação)
    icon_w = icon_h = int(panel_h * 0.70)
    icon_img = None
    if icon_path and Path(icon_path).exists():
        try:
            icon_img = Image.open(icon_path).convert("RGBA").resize((icon_w, icon_h))
        except Exception:
            icon_img = None

    # Título centralizado
    def textbbox_center(txt: str, font) -> tuple:
        try:
            bbox = draw.textbbox((0, 0), txt, font=font)
        except Exception:
            # fallback aproximado
            w = draw.textlength(txt, font=font) if hasattr(draw, "textlength") else len(txt) * int(getattr(font, "size", 24) * 0.6)
            h = int(getattr(font, "size", 24) * 1.0)
            bbox = (0, 0, w, h)
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = int(panel_left + (panel_w - bw) // 2 - bbox[0])
        y = int(panel_top + (panel_h - bh) // 2 - bbox[1])
        return x, y, bw, bh

    txt = str(topic or "Pergunta")
    # Shrink-to-fit com padding interno para não encostar na borda
    pad_x = int(panel_w * 0.06)
    pad_y = int(panel_h * 0.14)
    max_w = max(10, panel_w - 2 * pad_x)
    max_h = max(10, panel_h - 2 * pad_y)
    while True:
        tx, ty, bw, bh = textbbox_center(txt, title_font)
        if bw <= max_w and bh <= max_h:
            break
        new_sz = max(12, int(getattr(title_font, "size", 28) * 0.92))
        if new_sz == getattr(title_font, "size", 28):
            break
        title_font = _load_font(new_sz)
    # Prepara camada de texto separada (para ficar acima da borda animada)
    text_img = Image.new("RGBA", (width, height), (0,0,0,0))
    td = ImageDraw.Draw(text_img)
    for dx in (-2, 2):
        for dy in (-2, 2):
            td.text((tx + dx, ty + dy), txt, font=title_font, fill=(255,255,255,220))
    td.text((tx, ty), txt, font=title_font, fill=(0,0,0,255))
    text_layer_clip = ImageClip(np.array(text_img)).with_duration(duration)

    base_arr = np.array(base)

    # Área das animações (mesma largura/altura do ícone) – direita
    area_x0 = panel_right - pad - icon_w
    area_y0 = int(panel_top + (panel_h - icon_h)//2)
    bulb_cx = area_x0 + icon_w//2
    bulb_cy = area_y0 + icon_h//2
    bulb_r = max(6, int(min(icon_w, icon_h) * 0.22))

    def _make_rgba_frame(t):
        im = Image.fromarray(base_arr).copy()
        # animação do ícone com bob e leve giro (desativada se houver vídeo à esquerda)
        if icon_img is not None and not left_video:
            bob = int(2 + 2*np.sin(2*np.pi*t/max(0.1,duration)))
            angle = 3*np.sin(2*np.pi*t/max(0.1,duration)*0.5)
            try:
                ic_rot = icon_img.rotate(angle, resample=Image.BICUBIC, expand=False)
            except Exception:
                ic_rot = icon_img
            x = panel_left + pad
            y = int(panel_top + (panel_h - icon_h)//2 + bob)
            im.paste(ic_rot, (x, y), ic_rot)
        # animação vetorial padrão à direita apenas se não houver vídeo à direita
        if (not right_video) and anim == "bulb":
            # pulso suave
            phase = (np.sin(2 * np.pi * (t / max(0.1, duration)) * 0.8) + 1.0) / 2.0
            alpha = int(90 + 110 * phase)
            glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            gd = ImageDraw.Draw(glow)
            # halo discreto
            gr = int(bulb_r * (1.4 + 0.15 * phase))
            gd.ellipse([bulb_cx - gr, bulb_cy - gr, bulb_cx + gr, bulb_cy + gr], fill=(255, 210, 70, int(alpha * 0.35)))
            im = Image.alpha_composite(im, glow)
            # bulbo
            d2 = ImageDraw.Draw(im)
            d2.ellipse([bulb_cx - bulb_r, bulb_cy - bulb_r, bulb_cx + bulb_r, bulb_cy + bulb_r], fill=(255, 228, 140, alpha), outline=(0,0,0,220), width=2)
            # base
            base_w = int(bulb_r * 1.1)
            base_h = int(bulb_r * 0.5)
            d2.rectangle([bulb_cx - base_w//2, bulb_cy + bulb_r - base_h//2, bulb_cx + base_w//2, bulb_cy + bulb_r + base_h//2], fill=(70,70,70,220), outline=(0,0,0,230), width=2)
            # filamento
            f_r = int(bulb_r * 0.4)
            d2.arc([bulb_cx - f_r, bulb_cy - f_r, bulb_cx + f_r, bulb_cy + f_r], start=200, end=-20, fill=(180,120,20,220), width=3)
        elif (not right_video) and anim == "globe":
            # globo simplificado com rotação 2D
            rr = int(min(icon_w, icon_h) * 0.42)
            omega = 2*np.pi*(t/duration)
            d2 = ImageDraw.Draw(im)
            d2.ellipse([bulb_cx-rr, bulb_cy-rr, bulb_cx+rr, bulb_cy+rr], fill=(90,180,255,200), outline=(0,0,0,220), width=3)
            # linhas longitudinais animadas
            for k in range(-2,3):
                x = int(np.sin(omega + k*0.6) * rr*0.6)
                d2.ellipse([bulb_cx+x-rr*0.95, bulb_cy-rr*0.95, bulb_cx+x+rr*0.95, bulb_cy+rr*0.95], outline=(0,80,160,180), width=2)
            # linha equatorial
            d2.ellipse([bulb_cx-rr, bulb_cy-rr*0.35, bulb_cx+rr, bulb_cy+rr*0.35], outline=(0,80,160,200), width=3)
        elif (not right_video) and anim == "gear":
            d2 = ImageDraw.Draw(im)
            # engrenagem simples: círculo + dentes
            rr = int(min(icon_w, icon_h) * 0.42)
            steps = 8
            ang = (t/duration) * 2*np.pi
            for i in range(steps):
                a = ang + i*(2*np.pi/steps)
                x0 = int(bulb_cx + (rr+6)*np.cos(a))
                y0 = int(bulb_cy + (rr+6)*np.sin(a))
                x1 = int(bulb_cx + (rr+16)*np.cos(a))
                y1 = int(bulb_cy + (rr+16)*np.sin(a))
                d2.line([(x0,y0),(x1,y1)], fill=(0,0,0,220), width=4)
            d2.ellipse([bulb_cx-rr, bulb_cy-rr, bulb_cx+rr, bulb_cy+rr], outline=(0,0,0,220), width=3, fill=(220,230,255,220))
            d2.ellipse([bulb_cx-rr*0.35, bulb_cy-rr*0.35, bulb_cx+rr*0.35, bulb_cy+rr*0.35], fill=(200,210,245,255), outline=(0,0,0,200), width=2)
        elif (not right_video) and anim == "book":
            d2 = ImageDraw.Draw(im)
            w,h = int(icon_w*0.75), int(icon_h*0.55)
            ox = int(bulb_cx - w//2)
            oy = int(bulb_cy - h//2)
            # bounce leve
            dy = int(3*np.sin(2*np.pi*t/duration))
            rect = [ox, oy+dy, ox+w, oy+h+dy]
            d2.rectangle(rect, fill=(255,255,255,230), outline=(0,0,0,220), width=3)
            d2.line([ (ox+w//2,oy+dy), (ox+w//2,oy+h+dy) ], fill=(0,0,0,200), width=3)
        elif (not right_video) and anim == "atom":
            d2 = ImageDraw.Draw(im)
            rr = int(min(icon_w,icon_h)*0.42)
            for k in range(3):
                ang = k*np.pi/3 + (t/duration)*np.pi
                bbox = [bulb_cx-rr, bulb_cy-rr*0.55, bulb_cx+rr, bulb_cy+rr*0.55]
                d2.arc(bbox, start=int(ang*180/np.pi), end=int(ang*180/np.pi)+180, fill=(255,230,120,220), width=3)
            d2.ellipse([bulb_cx-6, bulb_cy-6, bulb_cx+6, bulb_cy+6], fill=(255,140,0,255))
        elif (not right_video) and anim == "star":
            d2 = ImageDraw.Draw(im)
            # estrela pulsante
            r = int(min(icon_w,icon_h)*0.30)
            phase = 0.15*np.sin(2*np.pi*t/duration)
            r1, r2 = r*(1.0+phase), r*0.5*(1.0+phase)
            pts = []
            for i in range(10):
                ang = i*np.pi/5
                rr = r1 if i%2==0 else r2
                pts.append((int(bulb_cx+rr*np.cos(ang)), int(bulb_cy+rr*np.sin(ang))))
            d2.polygon(pts, fill=(255,215,0,220), outline=(0,0,0,220))
        return np.array(im)

    def _make_rgb_frame(t):
        arr = _make_rgba_frame(t)
        rgb = arr[..., :3].astype('float32')
        a = (arr[..., 3:4].astype('float32') / 255.0)
        # Precompõe sobre branco para evitar halos pretos nas bordas anti-aliased
        rgb = rgb * a + 255.0 * (1.0 - a)
        return rgb.astype('uint8')

    def _make_mask_frame(t):
        arr = _make_rgba_frame(t)
        return (arr[..., 3].astype('float32') / 255.0)

    try:
        base_rgb = VideoClip(_make_rgb_frame, duration=duration)
    except TypeError:
        base_rgb = VideoClip(_make_rgb_frame).set_duration(duration)
    try:
        base_msk = VideoClip(_make_mask_frame, duration=duration)
    except TypeError:
        base_msk = VideoClip(_make_mask_frame).set_duration(duration)
    # marcar como máscara
    try:
        if hasattr(base_msk, "with_is_mask"):
            base_msk = base_msk.with_is_mask(True)
        elif hasattr(base_msk, "set_is_mask"):
            base_msk = base_msk.set_is_mask(True)
        else:
            base_msk.ismask = True
    except Exception:
        try:
            base_msk.ismask = True
        except Exception:
            pass
    base_clip = _with_mask(base_rgb, base_msk)
    # compõe com backdrop blur e painel
    if glass_layers:
        layers = glass_layers + [base_clip]
        base_clip = CompositeVideoClip(layers, size=(width, height))

    # Construtor de animação via arquivo/dir (gif/webm/mp4) com cromakey opcional
    def _load_anim_clip(path_or_dir: str | None, side: str):
        if not path_or_dir:
            return None
        anim_dir = Path(path_or_dir)
        if not anim_dir.exists():
            print(f"[HEADER] anim not found for {side}: {path_or_dir}")
            return None
        try:
            from moviepy import vfx as _vfx
        except Exception:
            from moviepy.editor import vfx as _vfx
        exts = {".mp4",".mov",".webm",".mkv",".gif"}
        # se for arquivo único, usa direto; senão pega primeiro do diretório
        if anim_dir.is_file():
            files = [anim_dir]
        else:
            files = [p for p in anim_dir.iterdir() if p.suffix.lower() in exts]
        if not files:
            print(f"[HEADER] no files in dir for {side}: {anim_dir}")
            return None
        anim_path = str(sorted(files)[0])
        try:
            suffix = Path(anim_path).suffix.lower()
            # Tente sempre via VideoFileClip (robusto para GIF/MP4/WEBM). Para WEBM, tentar alpha nativo.
            try:
                has_alpha_container = suffix in {".webm"}
                anim = VideoFileClip(anim_path, has_mask=has_alpha_container).without_audio()
            except TypeError:
                anim = VideoFileClip(anim_path).without_audio()
            except Exception:
                anim = None
            # Se não houver máscara e não for GIF, permitir chroma key (fundo verde).
            if anim is not None and getattr(anim, 'mask', None) is None and suffix != '.gif':
                try:
                    mask = anim.fx(_vfx.mask_color, color=[0,255,0], thr=int(chroma_thr), s=2)
                    anim = _with_mask(anim, mask)
                except Exception:
                    pass
            # redimensiona para caber no espaço alvo
            target_h = int(icon_h * float(video_scale))
            if target_h > 0:
                scale = target_h / max(1, int(getattr(anim, 'h', target_h)))
                anim = _resize_clip(anim, factor=scale)
            # loop até a duração do header
            try:
                if hasattr(anim, 'loop'):
                    anim = anim.loop(duration=duration)
                else:
                    from moviepy.video.fx.loop import loop as _loop
                    anim = _loop(anim, duration=duration)
            except Exception:
                if anim.duration < duration:
                    reps = int(np.ceil(duration / max(0.01, anim.duration)))
                    anim = concatenate_videoclips([anim] * reps)
                anim = _subclip(anim, 0, duration)
            # posiciona
            if side == 'right':
                x = panel_right - pad - int(getattr(anim, 'w', icon_w))
                y = int(panel_top + (panel_h - int(getattr(anim, 'h', icon_h))) // 2)
            else:  # left
                x = panel_left + pad
                y = int(panel_top + (panel_h - int(getattr(anim, 'h', icon_h))) // 2)
            anim = _with_position(anim, (x, y))
            return anim
        except Exception as e:
            print(f"[HEADER] failed to load anim for {side}: {path_or_dir}: {e}")
            return None

    # Preferência: novos parâmetros; mantém compatibilidade com video_dir (direita)
    right_source = right_video or video_dir
    right_anim = _load_anim_clip(right_source, side='right')
    left_anim = _load_anim_clip(left_video, side='left')

    final_clip = base_clip
    overlays = [final_clip]
    if left_anim is not None:
        overlays.append(left_anim)
    if right_anim is not None:
        overlays.append(right_anim)

    final_clip = CompositeVideoClip(overlays, size=(width, height)) if len(overlays) > 1 else overlays[0]

    # Borda animada (igual ao timer da pergunta)
    if header_border:
        cols = header_border_colors
        if not cols:
            # tenta reaproveitar cores do timer via env
            env_cols = os.getenv("QUIZ_HEADER_BORDER_COLORS")
            if env_cols:
                cols = [c.strip() for c in env_cols.split(',') if c.strip()]
            else:
                # paleta "circo": vermelho, amarelo, verde, azul, roxo
                cols = ["#FF1E1E","#FFD400","#00D26A","#00A3FF","#8A2BE2"]
        # equaliza duração
        seconds = max(1, int(round(duration)))
        border = render_timer_border(panel_w, panel_h, seconds=seconds,
                                     radius=radius, stroke=int(header_border_stroke),
                                     colors=cols, blink=False, mode=str(header_border_mode or "spin"), spin_speed=float(header_border_speed))
        border = _with_start(border, 0)
        border = _with_duration(border, duration)
        border = _with_position(border, (panel_left, panel_top))
        final_clip = CompositeVideoClip([final_clip, border], size=(width, height))
    # Texto por cima de tudo (evita que a borda animada invada o título)
    final_clip = CompositeVideoClip([final_clip, text_layer_clip], size=(width, height))

    return final_clip


def render_timer_bar(width: int, height: int, seconds: int, colors: list[str]):
    """Barra horizontal estilo pílula: contêiner branco com borda escura,
    preenchimento gradiente que esvazia da esquerda para a direita.
    """
    cols = _palette_stops(colors)

    def get_col_at(x_norm: float) -> tuple:
        if len(cols) == 1:
            return cols[0]
        # posiciona ao longo de segmentos iguais
        nseg = len(cols) - 1
        t = max(0.0, min(1.0, x_norm))
        seg = min(nseg - 1, int(t * nseg)) if nseg > 1 else 0
        local_t = (t * nseg) - seg if nseg > 0 else 0.0
        c1 = cols[seg]
        c2 = cols[min(seg + 1, len(cols) - 1)]
        return _lerp_color(c1, c2, local_t)

    radius = max(6, int(height * 0.5))

    def make_frame(t):
        # progresso restante (1..0)
        p = max(0.0, min(1.0, 1.0 - (t / float(max(0.001, seconds)))))
        w_fill = int(width * p)
        # container
        im = Image.new("RGBA", (width, height), (0,0,0,0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0,0,width-1,height-1], radius=radius, fill=(255,255,255,255), outline=(0,0,0,200), width=3)
        # fill
        pad = max(3, int(height*0.18))
        inner = [pad, pad, width-pad-1, height-pad-1]
        if w_fill > 0:
            # desenhar gradiente por colunas
            fill_w = max(1, w_fill - pad*2)
            grad = Image.new("RGBA", (fill_w, max(1, inner[3]-inner[1])), (0,0,0,0))
            garr = np.array(grad)
            gw = garr.shape[1]
            for x in range(gw):
                col = get_col_at(x / max(1, gw - 1))
                garr[:, x, 0:3] = col
                garr[:, x, 3] = 255
            # cap final quente
            cap_w = max(0, min(10, gw))
            if cap_w > 0:
                garr[:, max(0, gw-cap_w):gw, 0:3] = (255, 90, 60)
                garr[:, max(0, gw-cap_w):gw, 3] = 255
            grad = Image.fromarray(garr)
            im.paste(grad, (inner[0], inner[1]))
        arr = np.array(im)
        return arr

    return VideoClip(make_frame, duration=float(seconds))


def render_timer_bar_static(width: int, height: int, colors: list[str]):
    cols = _palette_stops(colors)
    radius = max(6, int(height * 0.5))
    im = Image.new("RGBA", (width, height), (0,0,0,0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0,0,width-1,height-1], radius=radius, fill=(255,255,255,255), outline=(0,0,0,200), width=3)
    pad = max(3, int(height*0.18))
    inner_w = max(1, width - pad*2)
    inner_h = max(1, height - pad*2)
    grad = Image.new("RGBA", (inner_w, inner_h), (0,0,0,0))
    garr = np.array(grad)
    for x in range(inner_w):
        col = cols[0] if len(cols) == 1 else _lerp_color(cols[0], cols[-1], x / max(1, inner_w - 1))
        garr[:, x, 0:3] = col
        garr[:, x, 3] = 255
    grad = Image.fromarray(garr)
    im.paste(grad, (pad, pad))
    return ImageClip(np.array(im))


def render_timer_border(card_w: int, card_h: int, seconds: int, radius: int, stroke: int, colors: list[str], blink: bool=False, mode: str = "drain", spin_speed: float = 0.8):
    """Desenha um progresso animado ao longo da borda de um retângulo arredondado.
    - card_w/card_h: dimensões do cartão (sem incluir a sombra)
    - seconds: duração total
    - radius: raio dos cantos (mesmo do cartão)
    - stroke: espessura do traço
    - colors: gradiente frio->quente
    - blink: pisca nos últimos 2s
    """
    cols = _palette_stops(colors)
    # 15% mais espessa para dar presença
    stroke = max(2, int(stroke * 1.15))
    # perímetro aproximado (sem arcos) — suficiente para progressão
    perim = 2 * (card_w + card_h - 2 * radius)

    def color_at(t: float) -> tuple:
        if len(cols) == 1:
            return cols[0]
        nseg = len(cols) - 1
        t = max(0.0, min(1.0, t))
        seg = min(nseg - 1, int(t * nseg)) if nseg > 1 else 0
        local_t = (t * nseg) - seg if nseg > 0 else 0.0
        return _lerp_color(cols[seg], cols[min(seg + 1, len(cols) - 1)], local_t)

    def make_rgba(t):
        im = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        # trilha fixa (clara para evitar qualquer halo escuro)
        d.rounded_rectangle([stroke//2, stroke//2, card_w - stroke//2 - 1, card_h - stroke//2 - 1], radius=radius, outline=(240,240,240,255), width=stroke)

        # Definição das quatro bordas retas (top,right,bottom,left)
        edges = [
            ((radius, stroke//2), (card_w - radius, stroke//2), card_w - 2*radius),  # top
            ((card_w - stroke//2, radius), (card_w - stroke//2, card_h - radius), card_h - 2*radius),  # right
            ((card_w - radius, card_h - stroke//2), (radius, card_h - stroke//2), card_w - 2*radius),  # bottom (reverso)
            ((stroke//2, card_h - radius), (stroke//2, radius), card_h - 2*radius),  # left (para cima)
        ]

        if mode == "spin":
            parts = 8
            total_parts = parts * 4
            phase = int((t * float(spin_speed) * total_parts)) % max(1, total_parts)
            seg_index = phase
            for ei, (p0, p1, length) in enumerate(edges):
                is_vertical = (ei == 1 or ei == 3)
                if is_vertical:
                    # vertical: uma única faixa de cor (sem segmentar)
                    x0, y0 = p0
                    x1, y1 = p1
                    col = cols[(phase + (2 if ei == 1 else 6)) % len(cols)]  # right/left com offset
                    d.line([(x0, y0), (x1, y1)], fill=col + (255,), width=stroke, joint="curve")
                else:
                    # horizontal: multicores segmentadas
                    for si in range(parts):
                        part_start = length * (si / float(parts))
                        part_end = length * ((si + 1) / float(parts))
                        t0 = part_start / float(length)
                        t1 = part_end / float(length)
                        x0, y0 = p0
                        x1, y1 = p1
                        xa = int(x0 + (x1 - x0) * t0)
                        ya = int(y0 + (y1 - y0) * t0)
                        xb = int(x0 + (x1 - x0) * t1)
                        yb = int(y0 + (y1 - y0) * t1)
                        col = cols[seg_index % len(cols)]
                        d.line([(xa, ya), (xb, yb)], fill=col + (255,), width=stroke, joint="curve")
                        seg_index += 1
            # cantos coloridos seguindo fase
            cap_r = max(2, int(stroke * 0.35))
            corners = [
                (radius, radius),
                (card_w - radius, radius),
                (card_w - radius, card_h - radius),
                (radius, card_h - radius),
            ]
            for ci, (cx, cy) in enumerate(corners):
                cc = cols[(phase + ci) % len(cols)]
                d.ellipse([cx - cap_r, cy - cap_r, cx + cap_r, cy + cap_r], fill=cc + (255,), outline=(255,255,255,160))
            return np.array(im)

        # modos fill/drain
        if mode == "fill":
            p = max(0.0, min(1.0, (t / float(max(0.001, seconds)))))
        else:  # drain
            p = max(0.0, min(1.0, 1.0 - (t / float(max(0.001, seconds)))))
        active_len = int(perim * p)

        edge_offset = 0
        seg_index = 0
        for (p0, p1, length) in edges:
            if active_len <= edge_offset:
                break
            local_draw = min(max(0, active_len - edge_offset), length)
            if local_draw > 0 and length > 0:
                parts = 4
                for si in range(parts):
                    part_start = length * (si / float(parts))
                    part_end = length * ((si + 1) / float(parts))
                    draw_len = max(0.0, min(local_draw - part_start, part_end - part_start))
                    if draw_len <= 0:
                        continue
                    t0 = part_start / float(length)
                    t1 = (part_start + draw_len) / float(length)
                    x0, y0 = p0
                    x1, y1 = p1
                    xa = int(x0 + (x1 - x0) * t0)
                    ya = int(y0 + (y1 - y0) * t0)
                    xb = int(x0 + (x1 - x0) * t1)
                    yb = int(y0 + (y1 - y0) * t1)
                    col = cols[seg_index % len(cols)]
                    d.line([(xa, ya), (xb, yb)], fill=col + (255,), width=stroke, joint="curve")
                    seg_index += 1
            edge_offset += length

        if blink and seconds - t <= 2.0:
            a = int(100 + 100 * abs(((t*4)%2)-1))
            d.rounded_rectangle([0,0,card_w-1,card_h-1], radius=radius, outline=(255,255,255,a), width=max(2, stroke//3))

        return np.array(im)

    def make_rgb(t):
        arr = make_rgba(t)
        rgb = arr[..., :3].astype('float32')
        a = (arr[..., 3:4].astype('float32') / 255.0)
        # Pré-mistura em branco para evitar franjas escuras
        rgb = rgb * a + 255.0 * (1.0 - a)
        return rgb.astype('uint8')

    def make_mask(t):
        arr = make_rgba(t)
        return (arr[..., 3].astype('float32') / 255.0)

    try:
        rgb_clip = VideoClip(make_rgb, duration=float(seconds))
    except TypeError:
        rgb_clip = VideoClip(make_rgb).set_duration(float(seconds))
    try:
        msk_clip = VideoClip(make_mask, duration=float(seconds))
    except TypeError:
        msk_clip = VideoClip(make_mask).set_duration(float(seconds))
    # marcar máscara
    try:
        if hasattr(msk_clip, "with_is_mask"):
            msk_clip = msk_clip.with_is_mask(True)
        elif hasattr(msk_clip, "set_is_mask"):
            msk_clip = msk_clip.set_is_mask(True)
        else:
            msk_clip.ismask = True
    except Exception:
        try:
            msk_clip.ismask = True
        except Exception:
            pass
    return _with_mask(rgb_clip, msk_clip)
def render_caption_band(width: int, height: int, index: int, question_text: str,
                        total_questions: int | None = None, show_dots: bool = True):
    """Renderiza uma faixa (header) com 'Pergunta N' em pill e o enunciado abaixo.
    Pode opcionalmente exibir dots de progresso à direita.
    Retorna um ImageClip RGBA do tamanho (width x height).
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fundo semitransparente com bordas arredondadas discretas
    radius = max(8, int(min(width, height) * 0.12))
    draw.rounded_rectangle([0, 0, width, height], radius=radius, fill=(0, 0, 0, 140))

    pad = max(10, int(height * 0.12))
    inner_left = pad
    inner_right = width - pad

    # Fonts
    try:
        pill_font = ImageFont.truetype(FONT_PATH, max(16, int(height * 0.28)))
        text_font = ImageFont.truetype(FONT_PATH, max(16, int(height * 0.36)))
    except Exception:
        pill_font = ImageFont.load_default()
        text_font = ImageFont.load_default()

    def textlen(t: str, f):
        try:
            return draw.textlength(t, font=f)
        except Exception:
            return f.getlength(t) if hasattr(f, "getlength") else len(t) * (getattr(f, "size", 16) * 0.6)

    # Progresso (dots) à direita
    dots_used_w = 0
    if show_dots and (total_questions or 0) > 0:
        tq = int(max(0, total_questions))
        r = max(3, int(height * 0.10))
        gap = max(6, int(r * 1.4))
        dots_used_w = tq * (2 * r) + (tq - 1) * gap
        x0 = inner_right - dots_used_w
        y = height // 2
        for i in range(1, tq + 1):
            cx = x0 + (i - 1) * (2 * r + gap) + r
            fill = (255, 255, 255, 230) if i <= int(index or 0) else (255, 255, 255, 70)
            draw.ellipse([cx - r, y - r, cx + r, y + r], fill=fill)
        inner_right = max(inner_left + pad, x0 - pad)

    # Pill "Pergunta N" à esquerda
    pill_text = f"Pergunta {int(index)}"
    pill_w = int(textlen(pill_text, pill_font) + pad * 1.4)
    pill_h = int((getattr(pill_font, "size", 24)) * 1.1 + pad * 0.2)
    px = inner_left
    py = max(4, int(height * 0.12))
    draw.rounded_rectangle([px, py, px + pill_w, py + pill_h], radius=int(pill_h * 0.5), fill=(255, 165, 0, 230), outline=(0, 0, 0, 160), width=3)
    ttw = textlen(pill_text, pill_font)
    tx = px + (pill_w - ttw) // 2
    ty = py + max(0, (pill_h - int(getattr(pill_font, "size", 24))) // 2 - 2)
    for dx in (-2, 2):
        for dy in (-2, 2):
            draw.text((tx + dx, ty + dy), pill_text, font=pill_font, fill=(0, 0, 0, 120))
    draw.text((tx, ty), pill_text, font=pill_font, fill=(30, 30, 30, 255))

    # Enunciado: à esquerda, abaixo do pill, com wrap e shrink
    q_top = py + pill_h + max(4, int(pad * 0.4))
    q_left = inner_left
    q_right = inner_right
    avail_w = max(10, q_right - q_left)
    avail_h = max(10, height - q_top - max(4, int(pad * 0.2)))

    base_fs = getattr(text_font, "size", 24)
    min_fs = max(12, int(base_fs * 0.55))
    font_q = text_font

    def wrap_lines(text: str, f):
        words = (text or "").split()
        lines, cur, cur_w = [], [], 0
        for w in words:
            ww = textlen(w + " ", f)
            if cur_w + ww > avail_w and cur:
                lines.append(" ".join(cur))
                cur, cur_w = [w], ww
            else:
                cur.append(w)
                cur_w += ww
        if cur:
            lines.append(" ".join(cur))
        return lines

    max_lines = 2
    while True:
        lines = wrap_lines(question_text, font_q)
        line_h = int((getattr(font_q, "size", 16)) * 1.15)
        total_h = len(lines) * line_h
        if len(lines) <= max_lines and total_h <= avail_h:
            break
        next_sz = int(getattr(font_q, "size", base_fs) * 0.92)
        if next_sz >= min_fs:
            try:
                font_q = ImageFont.truetype(FONT_PATH, next_sz)
            except Exception:
                font_q = ImageFont.load_default()
            continue
        # elipse última linha
        if lines:
            last = lines[-1]
            while textlen(last + "…", font_q) > avail_w and len(last) > 3:
                last = last[:-1]
            lines[-1] = last + "…"
        break

    y = q_top
    for ln in lines:
        lw = textlen(ln, font_q)
        x = q_left + max(0, (avail_w - lw) // 2)
        for dx in (-2, 2):
            for dy in (-2, 2):
                draw.text((x + dx, y + dy), ln, font=font_q, fill=(0, 0, 0, 140))
        draw.text((x, y), ln, font=font_q, fill=(255, 255, 255, 255))
        y += int((getattr(font_q, "size", 16)) * 1.15)

    return ImageClip(np.array(img))


def render_options_box(options, width: int, height: int, reveal: bool=False, answer_index: int=-1):
    """Cria uma imagem com 5 opções em caixas grandes, com quebra de linha e ajuste de fonte.
    Garante que texto caiba horizontalmente sem cortar.
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    def textlen(t: str, f):
        try:
            return draw.textlength(t, font=f)
        except Exception:
            return f.getlength(t) if hasattr(f, "getlength") else len(t) * (getattr(f, "size", 16) * 0.6)

    def loadf(sz: int):
        try:
            return ImageFont.truetype(FONT_PATH, sz)
        except Exception:
            return ImageFont.load_default()

    letters = ["A", "B", "C", "D", "E"]

    box_w = int(width * 0.92)
    box_h = int(height * 0.15)
    gap = int(height * 0.03)
    top = int((height - (box_h * 5 + gap * 4)) / 2)
    left = (width - box_w) // 2

    for i, opt in enumerate(options[:5]):
        y = top + i * (box_h + gap)
        # cores
        if reveal and answer_index >= 0:
            if i == answer_index:
                bg = (35, 180, 120, 230)  # verde
                fg = (255, 255, 255, 255)
            else:
                bg = (220, 60, 60, 210)   # vermelho
                fg = (255, 255, 255, 255)
        else:
            bg = (255, 255, 255, 255)
            fg = (0, 0, 0, 255)

        # caixa com cantos
        draw.rounded_rectangle([left, y, left + box_w, y + box_h], radius=18, fill=bg, outline=(0,0,0,160), width=3)

        # área da letra (largura proporcional, limitada pelo box)
        letter_area = int(min(box_h * 0.9, box_w * 0.14))
        label_fs = max(14, int(box_h * 0.50))
        font_label = loadf(label_fs)
        label = letters[i]
        lw = textlen(label, font_label)
        lx = left + int((letter_area - lw) // 2)
        ly = y + (box_h - int(getattr(font_label, "size", 24))) // 2 - 2
        draw.text((lx, ly), label, font=font_label, fill=fg)

        # texto (wrap com ajuste de fonte)
        inner_pad = max(8, int(box_h * 0.10))
        tx = left + letter_area + inner_pad
        avail_w = left + box_w - tx - inner_pad
        avail_h = box_h - inner_pad * 2

        # define tamanho inicial e mínimo
        base_fs = max(12, int(box_h * 0.30))
        min_fs = max(10, int(box_h * 0.18))

        def wrap_lines(text: str, f):
            words = str(text).split()
            lines, cur, cur_w = [], [], 0
            for w in words:
                ww = textlen(w + " ", f)
                if cur_w + ww > avail_w and cur:
                    lines.append(" ".join(cur))
                    cur, cur_w = [w], ww
                else:
                    cur.append(w)
                    cur_w += ww
            if cur:
                lines.append(" ".join(cur))
            return lines

        # tenta caber em até 2 linhas; se não, reduz fonte; se ainda não, permite 3 linhas
        text = str(opt)
        font_text = loadf(base_fs)
        max_lines = 2
        while True:
            lines = wrap_lines(text, font_text)
            line_h = int((getattr(font_text, "size", 16)) * 1.1)
            total_h = len(lines) * line_h
            if len(lines) <= max_lines and total_h <= avail_h:
                break
            # ajusta: primeiro tenta reduzir fonte até min_fs
            next_sz = int(getattr(font_text, "size", base_fs) * 0.92)
            if next_sz >= min_fs:
                font_text = loadf(next_sz)
                continue
            # se ainda não coube, permite 3 linhas
            if max_lines < 3:
                max_lines = 3
                font_text = loadf(base_fs)
                continue
            # último recurso: elipsar última linha
            while len(lines) > max_lines:
                lines = lines[:max_lines]
            last = lines[-1]
            while textlen(last + "…", font_text) > avail_w and len(last) > 3:
                last = last[:-1]
            lines[-1] = last + "…"
            break

        # desenha linhas centralizadas verticalmente na área de texto
        line_h = int((getattr(font_text, "size", 16)) * 1.1)
        total_h = len(lines) * line_h
        ty = y + inner_pad + max(0, (avail_h - total_h) // 2)
        for k, line in enumerate(lines):
            draw.text((tx, ty + k * line_h), line, font=font_text, fill=fg)

    return ImageClip(np.array(img))


def render_option_row(letter: str, text: str, width: int, box_w: int, box_h: int,
                      reveal: bool = False, is_correct: bool = False):
    """Renderiza um botão de opção (sem o badge), estilo pílula branca com contorno.
    O badge será desenhado separadamente para poder sobressair à esquerda.
    Retorna ImageClip RGBA do tamanho (box_w x box_h).
    """
    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # cores
    if reveal:
        bg = (35, 180, 120, 230) if is_correct else (220, 60, 60, 210)
        fg = (255, 255, 255, 255)
    else:
        bg = (255, 255, 255, 255)
        fg = (0, 0, 0, 255)

    # caixa com gradiente leve quando neutra
    radius = int(box_h * 0.35)
    if not reveal:
        # trilha branca com leve gradiente vertical
        # borda preta mais definida para estilo cartoon
        draw.rounded_rectangle([0, 0, box_w-1, box_h-1], radius=radius, fill=(255,255,255,255), outline=(0,0,0,230), width=4)
        top = Image.new("RGBA", (box_w-8, max(1, int(box_h*0.50))), (0,0,0,0))
        td = ImageDraw.Draw(top)
        for y in range(top.size[1]):
            a = int(255 * (1 - y / max(1, top.size[1]-1)) * 0.10)
            td.rectangle([0,y,top.size[0],y], fill=(0,0,0,a))
        img.paste(top, (4,4), top)
    else:
        draw.rounded_rectangle([0, 0, box_w-1, box_h-1], radius=radius, fill=bg, outline=(0,0,0,200), width=4)

    # fontes
    # Fonte do texto da opção — limpa e fácil de ler
    options_font_path = os.getenv("QUIZ_OPTIONS_FONT", "")
    if hasattr(render_option_row, "_options_font_custom"):
        options_font_path = getattr(render_option_row, "_options_font_custom") or options_font_path
    font_text = None
    for cand in [options_font_path, "DejaVuSans-Bold.ttf", FONT_PATH, None]:
        if not cand:
            continue
        try:
            font_text = ImageFont.truetype(cand, int(box_h * 0.36))
            break
        except Exception:
            font_text = None
    if font_text is None:
        font_text = ImageFont.load_default()

    def textlen(t: str, f):
        try:
            return draw.textlength(t, font=f)
        except Exception:
            return f.getlength(t) if hasattr(f, "getlength") else len(t) * (getattr(f, "size", 16) * 0.6)

    # texto com wrap
    inner_pad = max(8, int(box_h * 0.10))
    # reservar espaço à esquerda para o badge "sticker" externo
    tx = int(box_h * 0.95) + inner_pad
    avail_w = box_w - tx - inner_pad
    avail_h = box_h - inner_pad * 2

    base_fs = max(14, int(box_h * 0.36))
    min_fs = max(12, int(box_h * 0.20))

    def wrap_lines(txt: str, f):
        words = str(txt).split()
        lines, cur, cur_w = [], [], 0
        for w in words:
            ww = textlen(w + " ", f)
            if cur_w + ww > avail_w and cur:
                lines.append(" ".join(cur))
                cur, cur_w = [w], ww
            else:
                cur.append(w)
                cur_w += ww
        if cur:
            lines.append(" ".join(cur))
        return lines

    max_lines = 2
    while True:
        lines = wrap_lines(text, font_text)
        try:
            ascent, descent = font_text.getmetrics()
            line_h = int((ascent + descent) * 1.0)
        except Exception:
            line_h = int((getattr(font_text, "size", 16)) * 1.1)
        total_h = len(lines) * line_h
        if len(lines) <= max_lines and total_h <= avail_h:
            break
        next_sz = int(getattr(font_text, "size", base_fs) * 0.92)
        if next_sz >= min_fs:
            try:
                font_text = ImageFont.truetype(options_font_path or FONT_PATH, next_sz)
            except Exception:
                font_text = ImageFont.load_default()
            continue
        if max_lines < 3:
            max_lines = 3
            try:
                font_text = ImageFont.truetype(options_font_path or FONT_PATH, base_fs)
            except Exception:
                font_text = ImageFont.load_default()
            continue
        # elipse última linha se ainda não coube
        while len(lines) > max_lines:
            lines = lines[:max_lines]
        last = lines[-1]
        while textlen(last + "…", font_text) > avail_w and len(last) > 3:
            last = last[:-1]
        lines[-1] = last + "…"
        break

    try:
        ascent, descent = font_text.getmetrics()
        line_h = int((ascent + descent) * 1.0)
        baseline_adjust = max(0, int(descent * 0.2))
    except Exception:
        line_h = int((getattr(font_text, "size", 16)) * 1.1)
        baseline_adjust = int(getattr(font_text, "size", 16) * 0.08)
    total_h = len(lines) * line_h
    ty = inner_pad + max(0, (avail_h - total_h) // 2) + baseline_adjust
    for k, ln in enumerate(lines):
        # stroke para legibilidade sobre cores intensas
        # Sem stroke para manter o preto limpo como na referência
        draw.text((tx, ty + k * line_h), ln, font=font_text, fill=(0,0,0,255))

    return ImageClip(np.array(img))


def build_option_rows_overlays(width: int, height: int, options, reveal: bool, answer_index: int,
                               animate: bool, duration: float, y_base: int = 0, x_offset: int = 0):
    """Cria clips por linha com slide-in alternado (direita/esquerda) quando animate=True.
    Posiciona cada linha com coordenadas absolutas (incluindo y_base).
    """
    rows = []
    box_w = int(width * 0.92)
    box_h = int(height * 0.15)
    gap = int(height * 0.03)
    top = int((height - (box_h * len(options) + gap * (len(options) - 1))) / 2)
    letters = ["A", "B", "C", "D", "E"]
    # animação 30% mais lenta (antes ~0.18s)
    anim_d = 0.18 * 1.3

    def render_badge(letter: str, size: int) -> ImageClip:
        # canvas com margem para não cortar o stroke
        pad = max(4, int(size * 0.18))
        cw, ch = size + pad * 2, size + pad * 2
        im = Image.new("RGBA", (cw, ch), (0,0,0,0))
        d = ImageDraw.Draw(im)
        # sombra circular discreta
        d.ellipse([pad+6, pad+6, pad+size, pad+size], fill=(0,0,0,70))
        # letra grande com outline vermelho e fill amarelo
        try:
            f = ImageFont.truetype(FONT_PATH, int(size * 0.90))
        except Exception:
            f = ImageFont.load_default()
        stroke_w = max(4, int(size * 0.14))
        # centraliza usando bounding box com stroke
        try:
            bbox = d.textbbox((0,0), letter, font=f, stroke_width=stroke_w)
            bw, bh = bbox[2]-bbox[0], bbox[3]-bbox[1]
            tx = pad + (size - bw)//2 - bbox[0]
            ty = pad + (size - bh)//2 - bbox[1]
        except Exception:
            tw = d.textlength(letter, font=f) if hasattr(d,'textlength') else len(letter)*int(size*0.5)
            tx = pad + (size - tw)//2
            ty = pad + (size - getattr(f,'size',16))//2
        d.text((tx, ty), letter, font=f, fill=(255,213,79,255), stroke_width=stroke_w, stroke_fill=(198,40,40,255))
        # recorta de volta para o tamanho solicitado
        crop = im.crop((pad, pad, pad+size, pad+size))
        return ImageClip(np.array(crop))

    for i, opt in enumerate(options[:5]):
        is_correct = (i == int(answer_index))
        row_clip = render_option_row(letters[i], str(opt), width, box_w, box_h, reveal=reveal, is_correct=is_correct)
        row_clip = _with_duration(row_clip, duration)

        target_x = int((width - box_w) // 2)
        y = y_base + top + i * (box_h + gap)
        if animate:
            from_right = (i % 2 == 0)  # 0-based alterna lados
            dx = int(min(120, width * 0.10))
            start_x = target_x + (dx if from_right else -dx)
            def pos_fn(t, sx=start_x, tx=target_x, yy=y):
                p = 0.0
                if anim_d > 1e-6:
                    p = max(0.0, min(1.0, t / anim_d))
                p = 1.0 - (1.0 - p) ** 3
                x = x_offset + int(sx + (tx - sx) * p)
                return (x, yy)
            row_clip = _with_position(row_clip, pos_fn)
        else:
            row_clip = _with_position(row_clip, (x_offset + target_x, y))

        rows.append(row_clip)

        # Badge separado, sobressaindo à esquerda ~30%
        badge_size = int(box_h * 0.95)
        badge = render_badge(letters[i], badge_size)
        badge = _with_duration(badge, duration)
        # posiciona com centro bem à esquerda do botão (saliência forte)
        badge_target_x = x_offset + int(target_x - badge_size * 0.42)
        badge_y = int(y + (box_h - badge.h)//2)
        if animate:
            from_right = (i % 2 == 0)
            dx = int(min(120, width * 0.10))
            start_badge_x = badge_target_x + (dx if from_right else -dx)
            def pos_fn_badge(t, sx=start_badge_x, tx=badge_target_x, yy=badge_y):
                p = 0.0
                if anim_d > 1e-6:
                    p = max(0.0, min(1.0, t / anim_d))
                p = 1.0 - (1.0 - p) ** 3
                x = int(sx + (tx - sx) * p)
                return (x, yy)
            badge = _with_position(badge, pos_fn_badge)
        else:
            badge = _with_position(badge, (badge_target_x, badge_y))
        rows.append(badge)
    return rows


def render_countdown(width: int, height: int, seconds: int = 5):
    """Gera um contador visual decrescente (5..1), um número por segundo."""
    clips = []
    for i in range(seconds, 0, -1):
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype(FONT_PATH, int(height * 0.7))
        except Exception:
            font = ImageFont.load_default()
        text = str(i)
        try:
            tw = draw.textlength(text, font=font)
        except Exception:
            tw = font.getlength(text) if hasattr(font, "getlength") else len(text) * 40
        th = int(getattr(font, "size", 40) * 0.9)
        x = (width - tw) // 2
        y = (height - th) // 2
        # sombra suave
        for dx in (-4, 4):
            for dy in (-4, 4):
                draw.text((x + dx, y + dy), text, font=font, fill=(0,0,0,180))
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))
        frame = ImageClip(np.array(img))
        frame = _with_duration(frame, 1.0)
        clips.append(frame)
    return concatenate_videoclips(clips)


def render_beep(frequency: float = 1000.0, duration: float = 0.25, fps: int = 44100, volume: float = 0.32):
    """Gera um AudioArrayClip estéreo com envelope para beep confiável."""
    d = max(0.05, float(duration))
    n = int(fps * d)
    t = np.arange(n, dtype=np.float32) / float(fps)
    wave = np.sin(2 * np.pi * float(frequency) * t).astype(np.float32)
    # envelope de ataque/decay para evitar cortes por codec
    a_len = max(1, int(0.02 * fps))
    r_len = max(1, int(0.03 * fps))
    env = np.ones_like(wave)
    env[:a_len] = np.linspace(0.0, 1.0, a_len, dtype=np.float32)
    env[-r_len:] = np.linspace(1.0, 0.0, r_len, dtype=np.float32)
    sig = (volume * wave * env).astype(np.float32)
    stereo = np.stack([sig, sig], axis=1)
    from moviepy.audio.AudioClip import AudioArrayClip
    return AudioArrayClip(stereo, fps=fps)


def _lerp(a: tuple, b: tuple, t: float) -> tuple:
    t = max(0.0, min(1.0, float(t)))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def render_timer_ring(full_w: int, full_h: int, seconds: int = 5, scale: float = 1.0,
                      x_ratio: float = 0.5, y_ratio: float = 0.35):
    """Retorna um VideoClip RGBA do tamanho da tela com um anel de progresso e número central.
    - Cores aquecem de azul (#4FC3F7) -> laranja (#FF7043) ao longo do tempo.
    - O anel ocupa ~45% do menor lado, ajustável por 'scale'.
    """
    seconds = max(1, int(seconds))
    size = int(min(full_w, full_h) * 0.36 * max(0.5, min(1.5, float(scale))))
    thickness = max(8, int(size * 0.10))
    x_ratio = max(0.0, min(1.0, float(x_ratio)))
    y_ratio = max(0.0, min(1.0, float(y_ratio)))
    cx, cy = int(full_w * x_ratio), int(full_h * y_ratio)

    # Cores ajustadas: azul forte -> vermelho
    start_col = (66, 165, 245)   # #42A5F5
    end_col   = (244, 67, 54)    # #F44336

    def make_frame(t):
        import math
        prog = max(0.0, min(1.0, t / seconds))
        col = _lerp(start_col, end_col, prog)
        # base transparente
        im = Image.new("RGBA", (full_w, full_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(im)

        # anel de fundo (trilha)
        bbox = [cx - size//2, cy - size//2, cx + size//2, cy + size//2]
        draw.ellipse(bbox, outline=(255, 255, 255, 70), width=thickness)
        # arco de progresso (inicia no topo, sentido horário)
        start_angle = -90
        end_angle = start_angle + int(360 * prog)
        draw.arc(bbox, start=start_angle, end=end_angle, fill=col + (230,), width=thickness)

        # dígito central com flash em todos os segundos (crescendo ao longo da contagem)
        sec_elapsed = int(math.floor(t))
        remaining = max(1, seconds - sec_elapsed)
        local = t - float(sec_elapsed)  # 0..1 dentro do segundo atual
        # bump suave 0..1..0 no centro do segundo
        flash_unit = max(0.0, min(1.0, local * (1.0 - local) * 4.0))
        # intensidade cresce do primeiro número até o último (5 -> 1)
        flash_scale = (seconds - remaining + 1) / float(max(1, seconds))
        flash = flash_unit * flash_scale
        try:
            font = ImageFont.truetype(FONT_PATH, int(size * (0.55 + 0.10 * flash)))
        except Exception:
            font = ImageFont.load_default()
        text = str(remaining)
        try:
            tw = draw.textlength(text, font=font)
        except Exception:
            tw = font.getlength(text) if hasattr(font, "getlength") else len(text) * 40
        th = int(getattr(font, "size", 40) * 0.9)
        tx = int(cx - tw / 2)
        ty = int(cy - th / 2)
        # contorno leve
        for dx in (-3, 3):
            for dy in (-3, 3):
                draw.text((tx + dx, ty + dy), text, font=font, fill=(0, 0, 0, 180))
        draw.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))

        # glow sutil em todos os números, crescendo até o final
        if flash > 0:
            glow = Image.new("RGBA", (full_w, full_h), (0, 0, 0, 0))
            gdraw = ImageDraw.Draw(glow)
            r = int(size * (0.50 + 0.30 * flash))
            alpha = int(40 + 110 * flash)
            gdraw.ellipse([cx - r//2, cy - r//2, cx + r//2, cy + r//2], fill=(255, 255, 255, alpha))
            im = Image.alpha_composite(im, glow)

        return np.array(im)

    clip = VideoClip(make_frame, duration=float(seconds))
    return clip


def render_flash(full_w: int, full_h: int, duration: float = 0.12, alpha: float = 0.28):
    """Flash branco com decaimento linear de alpha, cobrindo a tela inteira."""
    duration = max(0.04, float(duration))
    a0 = max(0.0, min(1.0, float(alpha)))

    def make_frame(t):
        prog = max(0.0, min(1.0, t / duration))
        a = int(255 * a0 * (1.0 - prog))
        arr = np.zeros((full_h, full_w, 4), dtype=np.uint8)
        arr[:, :, 0:3] = 255
        arr[:, :, 3] = a
        return arr

    return VideoClip(make_frame, duration=duration)


def measure_text_height(texto: str, width: int, kind: str) -> int:
    """Calcula a altura necessária para render_text_box com a mesma lógica de quebra.
    Usa tamanho base de fonte por 'kind'."""
    img = Image.new("RGBA", (width, 100), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    base = 72 if kind == "Q" else 64 if kind == "HOOK" else 56
    try:
        font = ImageFont.truetype(FONT_PATH, base)
    except Exception:
        font = ImageFont.load_default()

    def _textlength(t: str, f: ImageFont.FreeTypeFont) -> float:
        try:
            return draw.textlength(t, font=f)
        except Exception:
            try:
                return f.getlength(t)
            except Exception:
                return len(t) * (f.size * 0.6 if hasattr(f, "size") else 10)

    words = (texto or "").split()
    lines, cur, cur_w = [], [], 0
    max_w = int(width * 0.85)
    for w in words:
        ww = _textlength(w + " ", font)
        if cur_w + ww > max_w and cur:
            lines.append(" ".join(cur))
            cur, cur_w = [w], ww
        else:
            cur.append(w)
            cur_w += ww
    if cur:
        lines.append(" ".join(cur))

    line_h = int((font.size or 48) * 1.3)
    total_h = max(line_h, len(lines) * line_h)
    # padding vertical
    total_h += int(line_h * 0.4)
    return total_h


def main():
    ap = argparse.ArgumentParser(description="Renderizador de vídeo do quiz")
    ap.add_argument("--hook-sec", type=float, default=DEFAULT_DURATIONS["HOOK"]) 
    ap.add_argument("--q-sec", type=float, default=DEFAULT_DURATIONS["Q"]) 
    ap.add_argument("--cta-short-sec", type=float, default=DEFAULT_DURATIONS["CTA_SHORT"]) 
    ap.add_argument("--cta-sec", type=float, default=DEFAULT_DURATIONS["CTA"]) 
    ap.add_argument("--bg-mode", choices=["crop","blur"], default=os.getenv("QUIZ_BG_MODE","crop"))
    ap.add_argument("--fps", type=float, default=float(os.getenv("QUIZ_FPS","0")), help="0 = usar FPS do fundo")
    ap.add_argument("--crf", type=int, default=int(os.getenv("QUIZ_CRF","18")))
    ap.add_argument("--bitrate", type=str, default=os.getenv("QUIZ_BITRATE",""))
    ap.add_argument("--preset", type=str, default=os.getenv("QUIZ_PRESET","medium"))
    ap.add_argument("--beep", action="store_true", default=bool(int(os.getenv("QUIZ_COUNTDOWN_BEEP","1"))), help="Toca beep a cada segundo durante COUNTDOWN")
    ap.add_argument("--beep-freq", type=float, default=float(os.getenv("QUIZ_BEEP_FREQ","1000")))
    ap.add_argument("--beep-sec", type=float, default=float(os.getenv("QUIZ_BEEP_SEC","0.25")))
    ap.add_argument("--beep-vol", type=float, default=float(os.getenv("QUIZ_BEEP_VOL","0.32")))
    ap.add_argument("--timer-style", choices=["border","ring","digits","bar"], default=os.getenv("QUIZ_TIMER_STYLE","border"))
    ap.add_argument("--timer-scale", type=float, default=float(os.getenv("QUIZ_TIMER_SCALE","0.9")))
    ap.add_argument("--timer-dim", type=float, default=float(os.getenv("QUIZ_TIMER_DIM","0.12")))
    ap.add_argument("--timer-flash", action="store_true", default=bool(int(os.getenv("QUIZ_TIMER_FLASH","0"))), help="Flash branco curto a cada segundo durante COUNTDOWN")
    ap.add_argument("--timer-flash-ms", type=int, default=int(os.getenv("QUIZ_TIMER_FLASH_MS","120")))
    ap.add_argument("--timer-flash-alpha", type=float, default=float(os.getenv("QUIZ_TIMER_FLASH_ALPHA","0.28")))
    ap.add_argument("--timer-x-ratio", type=float, default=float(os.getenv("QUIZ_TIMER_X_RATIO","0.5")), help="Posição X do timer (0..1)")
    ap.add_argument("--timer-y-ratio", type=float, default=float(os.getenv("QUIZ_TIMER_Y_RATIO","0.23")), help="Posição Y do timer (0..1) — usado apenas para ring/digits")
    # Margens globais de conteúdo
    ap.add_argument("--content-margin-x-ratio", type=float, default=float(os.getenv("QUIZ_CONTENT_MARGIN_X","0.04")), help="Margem horizontal global (0..0.2)")
    ap.add_argument("--content-margin-y-ratio", type=float, default=float(os.getenv("QUIZ_CONTENT_MARGIN_Y","0.04")), help="Margem vertical global (0..0.2)")
    ap.add_argument("--header-ratio", type=float, default=float(os.getenv("QUIZ_HEADER_RATIO","0.138")), help="Altura do header (0..1)")
    ap.add_argument("--timer-bar-height-ratio", type=float, default=float(os.getenv("QUIZ_TIMER_BAR_H","0.045")), help="Altura da barra de tempo (0..1)")
    ap.add_argument("--timer-bar-colors", type=str, default=os.getenv("QUIZ_TIMER_BAR_COLORS","#4FC3F7,#81D4FA,#FFB74D,#FF7043"), help="Cores do gradiente da barra (csv)")
    ap.add_argument("--timer-border-stroke", type=int, default=int(os.getenv("QUIZ_TIMER_BORDER_STROKE","12")), help="Espessura do traço da borda temporizada (px)" )
    ap.add_argument("--timer-border-colors", type=str, default=os.getenv("QUIZ_TIMER_BORDER_COLORS","#4FC3F7,#81D4FA,#FFB74D,#FF7043"), help="Cores do gradiente do progresso na borda (csv)")
    ap.add_argument("--timer-border-blink", action="store_true", default=bool(int(os.getenv("QUIZ_TIMER_BORDER_BLINK","0"))), help="Piscar nos últimos 2s")
    ap.add_argument("--topic-icon-path", type=str, default=os.getenv("QUIZ_TOPIC_ICON",""), help="Caminho para ícone do tópico no header")
    ap.add_argument("--sfx", action="store_true", default=bool(int(os.getenv("QUIZ_SFX","1"))), help="Usa SFX com cache (tick/ding/whoosh/stinger/chime)")
    ap.add_argument("--header-anim", choices=["auto","bulb","globe","gear","book","atom","star"], default=os.getenv("QUIZ_HEADER_ANIM","auto"))
    ap.add_argument("--topic-icon-auto", action="store_true", default=bool(int(os.getenv("QUIZ_TOPIC_ICON_AUTO","1"))), help="Gera/baixa ícone do tópico automaticamente (cache)")
    # animações do header
    ap.add_argument("--header-anim-video-dir", type=str, default=os.getenv("QUIZ_HEADER_ANIM_DIR","assets/animation"), help="Diretório raiz com animações (usado como fallback geral)")
    ap.add_argument("--header-left-anim-dir", type=str, default=os.getenv("QUIZ_HEADER_LEFT_ANIM_DIR",""), help="Diretório de animações por tópico (se vazio, usa <anim-root>/<slug>")
    ap.add_argument("--header-right-anim-path", type=str, default=os.getenv("QUIZ_HEADER_RIGHT_ANIM","assets/animation/lampada.gif"), help="Animação padrão do lado direito (gif/webm/mp4)")
    ap.add_argument("--header-anim-video-scale", type=float, default=float(os.getenv("QUIZ_HEADER_ANIM_SCALE","1.035")), help="Escala relativa ao espaço das animações (0..1)")
    ap.add_argument("--header-anim-chroma-thr", type=int, default=int(os.getenv("QUIZ_HEADER_ANIM_CHROMA_THR","110")), help="Limiar de chroma key (verde)")
    # borda animada do header
    ap.add_argument("--header-border", action="store_true", default=bool(int(os.getenv("QUIZ_HEADER_BORDER","1"))), help="Habilita borda animada no header")
    ap.add_argument("--header-border-stroke", type=int, default=int(os.getenv("QUIZ_HEADER_BORDER_STROKE","8")))
    ap.add_argument("--header-border-colors", type=str, default=os.getenv("QUIZ_HEADER_BORDER_COLORS",""), help="Cores CSV da borda animada do header (ex.: circo)")
    ap.add_argument("--header-border-mode", choices=["fill","spin"], default=os.getenv("QUIZ_HEADER_BORDER_MODE","spin"))
    ap.add_argument("--header-border-speed", type=float, default=float(os.getenv("QUIZ_HEADER_BORDER_SPEED","0.1")))
    # espaçamento interno do header (vidro) relativo ao tamanho do header
    ap.add_argument("--header-inset-x-ratio", type=float, default=float(os.getenv("QUIZ_HEADER_INSET_X","0.03")), help="Margem interna horizontal do painel de vidro (0..0.2)")
    ap.add_argument("--header-inset-y-ratio", type=float, default=float(os.getenv("QUIZ_HEADER_INSET_Y","0.12")), help="Margem interna vertical do painel de vidro (0..0.4)")
    # glass tuning
    ap.add_argument("--header-glass-alpha", type=int, default=int(os.getenv("QUIZ_HEADER_GLASS_ALPHA","92")), help="Opacidade do painel glass (0..255)")
    ap.add_argument("--header-blur-sigma", type=float, default=float(os.getenv("QUIZ_HEADER_BLUR","6.0")), help="Sigma do blur do fundo sob o header")
    ap.add_argument("--header-backdrop-blur", action="store_true", default=bool(int(os.getenv("QUIZ_HEADER_BACKDROP","0"))), help="Aplica blur do vídeo de fundo sob o header (backdrop simulado)")
    ap.add_argument("--sfx-provider", choices=["eleven","none"], default=os.getenv("QUIZ_SFX_PROVIDER","eleven"))
    ap.add_argument("--sfx-gain", type=float, default=float(os.getenv("QUIZ_SFX_GAIN","0.6")))
    ap.add_argument("--intro-sfx", type=str, default=os.getenv("QUIZ_INTRO_SFX_NAME","melody_intro"), help="Nome do SFX de introdução (melody_intro|message|stinger|...) ")
    ap.add_argument("--intro-sfx-path", type=str, default=os.getenv("QUIZ_INTRO_SFX_PATH",""), help="Caminho de áudio customizado para a introdução")
    ap.add_argument("--outro-sfx", type=str, default=os.getenv("QUIZ_OUTRO_SFX_NAME","melody_outro"), help="Nome do SFX de fechamento (melody_outro|chime|...)")
    ap.add_argument("--outro-sfx-path", type=str, default=os.getenv("QUIZ_OUTRO_SFX_PATH",""), help="Caminho de áudio customizado para o fechamento")
    ap.add_argument("--option-sfx", type=str, default=os.getenv("QUIZ_OPTION_SFX_NAME","solid_in"), help="SFX para chegada de alternativas (solid_in|whoosh|...)")
    ap.add_argument("--countdown-stagger-options", action="store_true", default=bool(int(os.getenv("QUIZ_COUNTDOWN_STAGGER","0"))), help="No COUNTDOWN, mostra 1 opção por segundo sincronizado com os beeps")
    ap.add_argument("--stagger-anim-ms", type=int, default=int(os.getenv("QUIZ_STAGGER_ANIM_MS","240")), help="Duração do slide-in de cada opção (ms)")
    ap.add_argument("--only-q", type=int, default=None, help="Renderiza apenas a questão N (mantém HOOK/CTA salvo flags abaixo)")
    ap.add_argument("--limit-questions", type=int, default=None, help="Renderiza apenas as primeiras K questões")
    ap.add_argument("--no-intro", action="store_true", help="Não renderiza o HOOK (introdução)")
    ap.add_argument("--no-cta", action="store_true", help="Não renderiza o CTA final")
    args = ap.parse_args()

    DURATIONS = {
        "HOOK": args.hook_sec,
        "Q": args.q_sec,
        "CTA_SHORT": args.cta_short_sec,
        "CTA": args.cta_sec,
    }
    if not MANIFEST.exists():
        raise RuntimeError(f"Manifest não encontrado: {MANIFEST}")
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    segments_all = [s for s in data.get("segments", []) if s.get("type")]

    # Mapeia índice de áudio original (1..N) para cada segmento com TTS
    audio_types = {"HOOK","Q","Q_ASK","REVEAL","REVEAL_EXPLAIN","CTA"}
    audio_counter = 0
    for s in segments_all:
        if s.get("type") in audio_types:
            audio_counter += 1
            s["_audio_idx"] = audio_counter

    # Filtro por pergunta
    def filter_segments(seg_all):
        # coleta referência de HOOK e CTA
        hook = next((s for s in seg_all if s.get("type") == "HOOK"), None)
        cta = next((s for s in reversed(seg_all) if s.get("type") == "CTA"), None)
        q_types = {"Q_ASK","COUNTDOWN","REVEAL_EXPLAIN","Q","REVEAL"}

        # Apenas uma questão
        if args.only_q is not None and args.only_q > 0:
            out = []
            if (not args.no_intro) and hook:
                out.append(hook)
            out.extend([s for s in seg_all if s.get("type") in q_types and int(s.get("index", -1)) == args.only_q])
            if (not args.no_cta) and cta:
                out.append(cta)
            return out

        # Limitar primeiras K questões
        if args.limit_questions is not None and args.limit_questions > 0:
            out = []
            if (not args.no_intro) and hook:
                out.append(hook)
            out.extend([s for s in seg_all if s.get("type") in q_types and int(s.get("index", 10**6)) <= args.limit_questions])
            if (not args.no_cta) and cta:
                out.append(cta)
            return out

        # Sem filtro: remove HOOK/CTA conforme flags
        out = list(seg_all)
        if args.no_intro:
            out = [s for s in out if s.get("type") != "HOOK"]
        if args.no_cta:
            # remove últimas ocorrências CTA
            out = [s for s in out if s.get("type") != "CTA"]
        return out

    segments = filter_segments(segments_all)
    # total de perguntas (para dots/progresso na ribbon)
    q_types_for_count = {"Q","Q_ASK","COUNTDOWN","REVEAL","REVEAL_EXPLAIN"}
    total_questions = len(sorted({int(s.get("index", 0)) for s in segments if s.get("type") in q_types_for_count}))

    # Áudios necessários para os segmentos filtrados
    needed_indices = [int(s.get("_audio_idx")) for s in segments if s.get("type") in audio_types]
    unique_needed = sorted(set(needed_indices))
    expected_audios = [str(OUT_DIR / f"quiz_{i:02d}.mp3") for i in unique_needed]
    missing = [p for p in expected_audios if not Path(p).exists()]
    if missing:
        raise RuntimeError(f"Áudios ausentes: {missing}. Rode tts_quiz novamente.")

    # fundo: pega um aleatório
    fundos = glob.glob("assets/videos_fundo/*.mp4")
    if not fundos:
        raise RuntimeError("Nenhum vídeo em assets/videos_fundo/*.mp4")
    fundo_path = random.choice(fundos)

    base = VideoFileClip(fundo_path)
    base = normalize_bg(base, TARGET_W, TARGET_H, mode=args.bg_mode)

    # duração alvo por segmento (usa a duração do áudio quando existir)
    target_durs = []
    for seg in segments:
        kind = seg.get("type", "Q")
        d_audio = 0.0
        if kind in audio_types:
            aidx = int(seg.get("_audio_idx"))
            apath = OUT_DIR / f"quiz_{aidx:02d}.mp3"
            try:
                _tmp_clip = AudioFileClip(str(apath))
                d_audio = float(_tmp_clip.duration)
            finally:
                try:
                    _tmp_clip.close()
                except Exception:
                    pass
        if kind == "COUNTDOWN":
            td = float(seg.get("seconds", 5))
        else:
            td = max(d_audio, DURATIONS.get(kind, d_audio))
        target_durs.append(td)
    total_target = sum(target_durs)

    if base.duration > total_target:
        start = random.uniform(0, max(0.0, base.duration - total_target))
        base = _subclip(base, start, start + total_target)
    else:
        # loop simples se o fundo for curto
        reps = max(1, math.ceil(total_target / max(0.01, base.duration)))
        clips = [base] * reps
        base = _subclip(concatenate_videoclips(clips), 0, total_target)

    # monta cenas (texto + imagem opcional por pergunta)
    t = 0.0
    cenas = []
    # cache simples de SFX em memória (numpy) para evitar muitos arquivos abertos
    from moviepy.audio.AudioClip import AudioArrayClip as _AudioArrayClip
    _sfx_arr_cache: dict[str, tuple[np.ndarray, int]] = {}
    def _arr_clip_for(path: str, fps: int = 44100):
        arr_fps = fps
        if path not in _sfx_arr_cache:
            ext = Path(path).suffix.lower()
            # Prefer leitura direta de WAV para evitar bugs de duração do FFMPEG
            if ext == ".wav":
                import wave, numpy as _np
                with wave.open(path, 'rb') as wf:
                    nchan = wf.getnchannels()
                    arr_fps = wf.getframerate()
                    nframes = wf.getnframes()
                    raw = wf.readframes(nframes)
                data = _np.frombuffer(raw, dtype=_np.int16)
                if nchan > 1:
                    data = data.reshape(-1, nchan)
                else:
                    data = _np.stack([data, data], axis=1)
                arr = (data.astype(_np.float32) / 32767.0)
            else:
                # Fallback para outros formatos
                try:
                    clip = AudioFileClip(path)
                    arr = clip.to_soundarray(fps=fps)
                    arr_fps = clip.fps if hasattr(clip, 'fps') and clip.fps else fps
                finally:
                    try:
                        clip.close()
                    except Exception:
                        pass
            _sfx_arr_cache[path] = (arr, arr_fps)
        arr, arr_fps = _sfx_arr_cache[path]
        return _AudioArrayClip(arr, fps=arr_fps)

    for idx, (seg, target_d) in enumerate(zip(segments, target_durs), start=1):
        kind = seg.get("type", "Q")
        t_end = min(t + target_d, base.duration - 1e-3)
        slice_bg = _subclip(base, t, t_end)
        # áudio (quando houver)
        if kind in audio_types:
            aidx = int(seg.get("_audio_idx"))
            apath = OUT_DIR / f"quiz_{aidx:02d}.mp3"
            audio_clip = AudioFileClip(str(apath))
            slice_bg = _with_audio(slice_bg, audio_clip)

        layers = [slice_bg]
        overlays_after_images = []  # garante texto sempre acima das imagens

        # Margens globais e área interna
        left_margin = int(slice_bg.w * max(0.0, min(0.2, float(args.content_margin_x_ratio))))
        top_margin_glob = int(slice_bg.h * max(0.0, min(0.2, float(args.content_margin_y_ratio))))
        inner_w = max(10, slice_bg.w - 2 * left_margin)

        # Texto principal (HOOK/CTA) só será aplicado após imagens
        texto = seg.get("text", "")
        if kind in ("CTA",):
            overlay = render_text_box(texto, inner_w, int(slice_bg.h * 0.30), kind)
            y_top = int(top_margin_glob + slice_bg.h * 0.04) if kind == "HOOK" else int(slice_bg.h * 0.65)
            overlay = _with_start(overlay, 0)
            overlay = _with_duration(overlay, slice_bg.duration)
            overlay = _with_position(overlay, (left_margin, y_top))
            overlays_after_images.append(overlay)

        # INTRO COVER na HOOK (se existir)
        if kind == "HOOK":
            intro_cover = (json.loads(MANIFEST.read_text(encoding="utf-8")).get("intro_cover") if MANIFEST.exists() else None)
            if intro_cover and Path(intro_cover).exists():
                cov = ImageClip(intro_cover)
                cov_h = int(slice_bg.h * 0.55)
                scale = cov_h / cov.h if getattr(cov, "h", 0) else 1.0
                cov = _resize_clip(cov, factor=scale)
                cov = _with_start(cov, 0)
                cov = _with_duration(cov, slice_bg.duration)
                cov = _with_position(cov, (left_margin + (inner_w - cov.w)//2, int(slice_bg.h * 0.28)))
                layers.insert(1, cov)
            else:
                # Fallback: se não houver capa gerada, mantém texto do HOOK como overlay
                overlay = render_text_box(texto, inner_w, int(slice_bg.h * 0.30), "HOOK")
                overlay = _with_start(overlay, 0)
                overlay = _with_duration(overlay, slice_bg.duration)
                overlay = _with_position(overlay, (left_margin, int(top_margin_glob + slice_bg.h * 0.06)))
                overlays_after_images.append(overlay)

        # Layout dinâmico: calculamos y e alturas conforme conteúdo com margens globais
        top_margin = top_margin_glob
        gap = int(slice_bg.h * 0.02)
        bottom_margin = top_margin_glob
        y_cursor = top_margin

        # Se houver imagem para a pergunta (quiz_images.py), posiciona no topo e avança cursor
        img_path = seg.get("image_path")
        if kind in ("Q", "Q_ASK", "REVEAL", "REVEAL_EXPLAIN") and img_path and Path(img_path).exists():
            img_h = int(slice_bg.h * 0.28)
            img_clip = ImageClip(img_path)
            scale = img_h / img_clip.h if getattr(img_clip, "h", 0) else 1.0
            img_clip = _resize_clip(img_clip, factor=scale)
            pos_y = max(0, y_cursor)
            img_clip = _with_start(img_clip, 0)
            img_clip = _with_duration(img_clip, slice_bg.duration)
            img_clip = _with_position(img_clip, (left_margin + (inner_w - img_clip.w)//2, pos_y))
            layers.insert(1, img_clip)
            y_cursor = pos_y + img_h + gap

        # Pergunta + opções
        if kind in ("Q", "Q_ASK", "COUNTDOWN", "REVEAL", "REVEAL_EXPLAIN"):
            # Header com tópico
            header_h = int(slice_bg.h * max(0.0, min(0.5, float(args.header_ratio))))
            topic_label = (data.get("topic") if isinstance(data, dict) else None) or ""
            # resolve ícone (gera se não existir) com OpenAI fallback
            icon_path = (args.topic_icon_path or "").strip()
            if not icon_path and topic_label and args.topic_icon_auto:
                try:
                    from .header_assets import ensure_topic_icon
                    icon_path = str(ensure_topic_icon(topic_label))
                except Exception:
                    try:
                        from .topic_icons import ensure_topic_icon as ensure_icon_fallback
                        icon_path = str(ensure_icon_fallback(topic_label))
                    except Exception:
                        icon_path = ""
            # animação automática: mapeia por tema se pedida
            anim = (args.header_anim or "auto").lower()
            if anim == "auto":
                slug = (topic_label or "").strip().lower()
                if "geo" in slug:
                    anim = "globe"
                elif "prog" in slug or "c\u00f3d" in slug or "code" in slug:
                    anim = "gear"
                elif "cultura" in slug or "livro" in slug:
                    anim = "book"
                elif "ci\u00eancia" in slug or "science" in slug:
                    anim = "atom"
                else:
                    anim = "star"
            # Seleção de animação por questão (sem repetição)
            def _slugify(s: str) -> str:
                import re, unicodedata
                s = unicodedata.normalize('NFKD', s or '').encode('ascii','ignore').decode('ascii')
                s = re.sub(r'[^a-zA-Z0-9]+','-', s).strip('-').lower()
                return s or 'tema'
            topic_slug = _slugify(topic_label or '')
            anim_root = Path(args.header_anim_video_dir or "assets/animation")
            # diretório para animações do lado esquerdo (por tópico)
            left_dir = Path(args.header_left_anim_dir) if args.header_left_anim_dir else (anim_root / topic_slug)
            print(f"[HEADER] topic='{topic_label}' slug='{topic_slug}' anim_root='{anim_root}' left_dir='{left_dir}'")
            pool_dir = left_dir if left_dir.exists() else anim_root
            try:
                exts = {".gif",".webm",".mp4",".mov",".mkv"}
                anim_pool = [p for p in pool_dir.iterdir() if p.suffix.lower() in exts]
                print(f"[HEADER] pool_dir='{pool_dir}', files={[p.name for p in anim_pool]}")
            except Exception:
                anim_pool = []
            if not hasattr(main, "_header_anim_map"):
                setattr(main, "_header_anim_map", {})
            amap = getattr(main, "_header_anim_map")
            q_index = int(seg.get("index", 0))
            chosen_left_anim = None
            if q_index and anim_pool:
                used = set(amap.values())
                avail = [str(p) for p in anim_pool if str(p) not in used]
                if not avail:
                    avail = [str(p) for p in anim_pool]
                import random as _rnd
                chosen_left_anim = amap.setdefault(q_index, _rnd.choice(avail))
                print(f"[HEADER] chosen_left_anim for Q{q_index}: {chosen_left_anim}")

            # animação padrão da direita (fixa)
            right_anim_path = args.header_right_anim_path if args.header_right_anim_path else ""
            if right_anim_path and not Path(right_anim_path).exists():
                # tenta fallback no anim_root
                cand = anim_root / Path(right_anim_path).name
                if cand.exists():
                    right_anim_path = str(cand)
                else:
                    right_anim_path = ""

            print(f"[HEADER] icon_path='{icon_path}', anim='{anim}', left='{chosen_left_anim}', right='{right_anim_path}'")
            head = render_header(
                inner_w, header_h, topic_label, duration=slice_bg.duration,
                icon_path=(icon_path or None), anim=anim,
                # lado esquerdo = por tópico; lado direito = padrão
                left_video=(chosen_left_anim or None),
                right_video=(right_anim_path or None),
                # compat: se nada for passado, ainda permitir usar diretório raiz
                video_dir=(None),
                video_scale=args.header_anim_video_scale,
                chroma_thr=args.header_anim_chroma_thr,
                bg_clip=slice_bg,
                header_border=bool(args.header_border),
                header_border_colors=[c.strip() for c in (args.header_border_colors or '').split(',') if c.strip()] or None,
                header_border_stroke=int(args.header_border_stroke),
                header_border_mode=str(args.header_border_mode),
                header_border_speed=float(args.header_border_speed),
                inset_x=int(inner_w * max(0.0, min(0.2, float(args.header_inset_x_ratio)))),
                inset_y=int(header_h * max(0.0, min(0.4, float(args.header_inset_y_ratio)))),
                glass_alpha=int(max(0, min(255, args.header_glass_alpha))),
                blur_sigma=float(args.header_blur_sigma),
                glass_backdrop=bool(args.header_backdrop_blur),
            )
            head = _with_start(head, 0)
            head = _with_duration(head, slice_bg.duration)
            head = _with_position(head, (left_margin, top_margin))
            overlays_after_images.append(head)
            y_cursor = max(y_cursor, top_margin + header_h + gap)

            # pergunta: mede altura necessária
            q_needed = measure_text_height(texto, inner_w, "Q")
            # limites para não estourar
            q_min = int(slice_bg.h * 0.12)
            q_max = int(slice_bg.h * 0.34)
            q_h = max(q_min, min(q_needed, q_max))
            # reserva espaço mínimo para as opções
            min_opts_h = int(slice_bg.h * 0.28)
            space_after_q = slice_bg.h - (y_cursor + q_h + gap) - bottom_margin
            if space_after_q < min_opts_h:
                # tenta reduzir a altura da pergunta, mas não abaixo de q_min
                reducible = max(0, q_h - q_min)
                need = min_opts_h - max(0, space_after_q)
                reduce_by = min(reducible, need)
                q_h -= reduce_by
                space_after_q = slice_bg.h - (y_cursor + q_h + gap) - bottom_margin

            # Painel da pergunta (fixo em ambos os casos)
            q_overlay = render_question_card(int(inner_w), q_h, texto)
            q_overlay = _with_start(q_overlay, 0)
            q_overlay = _with_duration(q_overlay, slice_bg.duration)
            q_overlay = _with_position(q_overlay, (left_margin, y_cursor))
            overlays_after_images.append(q_overlay)
            y_after_q = y_cursor + q_h + gap

            # Timer + opções
            if kind == "COUNTDOWN":
                seconds = int(seg.get("seconds", 5))
                if args.timer_style == "border":
                    # timer percorre a borda do cartão (usar largura interna)
                    card_w = int(inner_w)
                    card_h = q_h
                    radius = max(28, int(min(card_w, card_h) * 0.10))
                    tcolors = [c.strip() for c in (args.timer_border_colors or '').split(',') if c.strip()]
                    border = render_timer_border(card_w, card_h, seconds=seconds, radius=radius, stroke=int(args.timer_border_stroke), colors=tcolors, blink=args.timer_border_blink)
                    border = _with_start(border, 0)
                    border = _with_duration(border, slice_bg.duration)
                    border = _with_position(border, (left_margin, y_cursor))
                    overlays_after_images.append(border)
                    after_timer_y = y_after_q  # sem barra abaixo, opções sob o cartão
                    extra_gap = gap
                else:
                    # Timer BAR animada (estilo anterior)
                    bar_h = max(8, int(slice_bg.h * max(0.02, min(0.2, float(args.timer_bar_height_ratio)))))
                    colors = [c.strip() for c in (args.timer_bar_colors or '').split(',') if c.strip()]
                    bar = render_timer_bar(int(inner_w * 0.88), bar_h, seconds=seconds, colors=colors)
                    bar = _with_start(bar, 0)
                    bar = _with_duration(bar, slice_bg.duration)
                    bar = _with_position(bar, (left_margin + int((inner_w - int(inner_w*0.88))//2), y_after_q))
                    overlays_after_images.append(bar)
                    after_timer_y = y_after_q + bar_h
                    extra_gap = gap

                # opções durante COUNTDOWN (estáticas por padrão)
                opts = seg.get("options") or []
                ans_idx = int(seg.get("answer_index", -1))
                space_left = max(0, slice_bg.h - (after_timer_y + extra_gap) - bottom_margin)
                if args.countdown_stagger_options and opts:
                    # sincroniza cada opção com o segundo correspondente
                    letters = ["A","B","C","D","E"]
                    box_w = int(inner_w * 0.92)
                    box_h = int(space_left * 0.15)
                    gap = int(space_left * 0.03)
                    top = int((space_left - (box_h * len(opts) + gap * (len(opts) - 1))) / 2)
                    dx = int(min(120, inner_w * 0.10))
                    anim_d = max(0.08, int(getattr(args, 'stagger_anim_ms', args.stagger_anim_ms)) / 1000.0)
                    for i, opt in enumerate(opts[:5]):
                        target_x = left_margin + int((inner_w - box_w) // 2)
                        y_abs = y_cursor_q_end + top + i * (box_h + gap)
                        # constrói a linha
                        row = render_option_row(letters[i], str(opt), inner_w, box_w, box_h,
                                                reveal=False, is_correct=(i == ans_idx))
                        # duração de cada linha = resto do COUNTDOWN a partir do segundo 'i'
                        row_dur = max(0.05, slice_bg.duration - float(i))
                        row = _with_duration(row, row_dur)
                        row = _with_start(row, float(i))
                        from_right = (i % 2 == 0)
                        start_x = target_x + (dx if from_right else -dx)
                        def pos_fn_row(t, sx=start_x, tx=target_x, yy=y_abs, ad=anim_d):
                            # MoviePy fornece 't' local ao clip (após with_start), então usamos t direto
                            local = max(0.0, t)
                            p = 0.0
                            if ad > 1e-6:
                                p = max(0.0, min(1.0, local / ad))
                            p = 1.0 - (1.0 - p) ** 3
                            x = int(sx + (tx - sx) * p)
                            return (x, yy)
                        row = _with_position(row, pos_fn_row)
                        overlays_after_images.append(row)
                else:
                    rows = build_option_rows_overlays(
                        inner_w, space_left, opts, reveal=False, answer_index=ans_idx,
                        animate=False, duration=slice_bg.duration, y_base=after_timer_y + extra_gap, x_offset=left_margin
                    )
                    overlays_after_images.extend(rows)

                # escurecimento sutil do fundo (mantido)
                dim_a = max(0.0, min(1.0, args.timer_dim))
                if dim_a > 0:
                    dim_arr = np.zeros((slice_bg.h, slice_bg.w, 4), dtype=np.uint8)
                    dim_arr[:, :, 3] = int(255 * dim_a)
                    dim_clip = ImageClip(dim_arr)
                    dim_clip = _with_start(dim_clip, 0)
                    dim_clip = _with_duration(dim_clip, slice_bg.duration)
                    dim_clip = _with_position(dim_clip, ("center", "center"))
                    layers.append(dim_clip)

                # timer alternativo (ring/digits) se escolhido explicitamente
                seconds = int(seg.get("seconds", 5))
                if args.timer_style == "ring":
                    eff_x_ratio = (left_margin + inner_w * max(0.0, min(1.0, float(args.timer_x_ratio)))) / float(slice_bg.w)
                    eff_y_ratio = (top_margin + header_h * 0.5) / float(slice_bg.h)
                    ring = render_timer_ring(
                        slice_bg.w, slice_bg.h, seconds=seconds, scale=args.timer_scale,
                        x_ratio=eff_x_ratio, y_ratio=eff_y_ratio
                    )
                    ring = _with_start(ring, 0)
                    ring = _with_duration(ring, slice_bg.duration)
                    ring = _with_position(ring, ("center", "center"))
                    overlays_after_images.append(ring)
                elif args.timer_style == "digits":
                    cnt_h = max(int(slice_bg.h * 0.28), int(q_h * 0.9))
                    cnt = render_countdown(slice_bg.w, cnt_h, seconds=seconds)
                    cnt = _with_start(cnt, 0)
                    cnt = _with_duration(cnt, slice_bg.duration)
                    cnt = _with_position(cnt, (left_margin, int(top_margin + header_h * 0.5 - cnt_h * 0.5)))
                    overlays_after_images.append(cnt)

                # flashes por segundo (sobre tudo), se ativado
                if args.timer_flash:
                    flash_dur = max(0.05, int(args.timer_flash_ms) / 1000.0)
                    for k in range(seconds):
                        fl = render_flash(slice_bg.w, slice_bg.h, duration=flash_dur, alpha=args.timer_flash_alpha)
                        fl = _with_start(fl, float(k))
                        fl = _with_duration(fl, min(flash_dur, slice_bg.duration))
                        fl = _with_position(fl, ("center", "center"))
                        overlays_after_images.append(fl)

                # áudio opcional: beep curto a cada segundo (ex.: 5 beeps)
                # Preparação de áudio do COUNTDOWN
                countdown_audio_mix = None

                # Beeps programáticos (sempre que --beep estiver ligado), para garantir áudio mesmo sem SFX
                beep_mix = None
                if args.beep:
                    seconds = int(seg.get("seconds", 5))
                    base_freq = float(args.beep_freq)
                    mults = [0.9, 1.05, 1.2, 1.4, 1.6]
                    freqs = [base_freq * mults[min(i, len(mults)-1)] for i in range(seconds)]
                    beeps = []
                    for k, f in enumerate(freqs):
                        b = render_beep(
                            frequency=f,
                            duration=min(args.beep_sec, slice_bg.duration),
                            volume=max(0.02, min(1.0, args.beep_vol))
                        )
                        b = _with_start(b, float(k))
                        beeps.append(b)
                    from moviepy.audio.AudioClip import AudioArrayClip
                    n = max(1, int(44100 * slice_bg.duration))
                    silent = np.zeros((n, 2), dtype=np.float32)
                    silence = AudioArrayClip(silent, fps=44100)
                    beep_mix = CompositeAudioClip([silence] + beeps)
                    beep_mix.fps = 44100

                # SFX ElevenLabs (ou cache/fallback) para COUNTDOWN: tick por segundo
                sfx_mix = None
                if args.sfx:
                    from . import sfx as sfxmod
                    seconds = int(seg.get("seconds", 5))
                    tick = sfxmod.get_sfx_path("tick")
                    ticks = []
                    for k in range(seconds):
                        clip = _with_start(_volumex_clip(AudioFileClip(str(tick)), max(0.05, min(1.0, args.sfx_gain))), float(k))
                        ticks.append(clip)
                    from moviepy.audio.AudioClip import AudioArrayClip
                    n = max(1, int(44100 * slice_bg.duration))
                    silent = np.zeros((n, 2), dtype=np.float32)
                    silence = AudioArrayClip(silent, fps=44100)
                    sfx_mix = CompositeAudioClip([silence] + ticks)
                    sfx_mix.fps = 44100
                    print(f"[SFX] COUNTDOWN ticks applied: {seconds}x from {tick}")

                # Combina mixagem (beep + sfx) se houver ambos; senão usa o que existir
                if beep_mix and sfx_mix:
                    countdown_audio_mix = CompositeAudioClip([beep_mix, sfx_mix])
                    countdown_audio_mix.fps = 44100
                elif beep_mix:
                    countdown_audio_mix = beep_mix
                elif sfx_mix:
                    countdown_audio_mix = sfx_mix
            else:
                # Durante Q/Q_ASK (pré-countdown): anima a borda "enchendo" (fill)
                if args.timer_style == "border":
                    card_w = int(inner_w)
                    card_h = q_h
                    radius = max(28, int(min(card_w, card_h) * 0.10))
                    tcolors = [c.strip() for c in (args.timer_border_colors or '').split(',') if c.strip()]
                    fill_seconds = float(DURATIONS.get("Q", 1.5))
                    fill_border = render_timer_border(card_w, card_h, seconds=fill_seconds, radius=radius, stroke=int(args.timer_border_stroke), colors=tcolors, blink=False, mode="fill")
                    fill_border = _with_start(fill_border, 0)
                    fill_border = _with_duration(fill_border, slice_bg.duration)
                    fill_border = _with_position(fill_border, (left_margin, y_cursor))
                    overlays_after_images.append(fill_border)
                    y_cursor = y_after_q + gap
                else:
                    # fallback para estilos antigos
                    bar_h = max(8, int(slice_bg.h * max(0.02, min(0.2, float(args.timer_bar_height_ratio)))))
                    colors = [c.strip() for c in (args.timer_bar_colors or '').split(',') if c.strip()]
                    bar_static = render_timer_bar_static(int(inner_w * 0.88), bar_h, colors)
                    bar_static = _with_start(bar_static, 0)
                    bar_static = _with_duration(bar_static, slice_bg.duration)
                    bar_static = _with_position(bar_static, (left_margin + int((inner_w - int(inner_w * 0.88))//2), y_after_q))
                    overlays_after_images.append(bar_static)
                    y_cursor = y_after_q + bar_h + gap

            # opções: ocupam o resto até o bottom_margin
            # Opções aparecem somente em Q/REVEAL
            if kind in ("Q", "Q_ASK", "REVEAL", "REVEAL_EXPLAIN"):
                opts = seg.get("options") or []
                ans_idx = int(seg.get("answer_index", -1))
                reveal = (kind in ("REVEAL","REVEAL_EXPLAIN"))
                space_left = max(0, slice_bg.h - y_cursor - bottom_margin)
                rows = build_option_rows_overlays(
                    inner_w, space_left, opts, reveal=reveal, answer_index=ans_idx,
                    animate=(kind in ("Q","Q_ASK")), duration=slice_bg.duration, y_base=y_cursor, x_offset=left_margin
                )
                overlays_after_images.extend(rows)

        # Texto por último (sempre acima)
        layers.extend(overlays_after_images)

        cena = CompositeVideoClip(layers, size=(slice_bg.w, slice_bg.h))
        cena = _with_duration(cena, slice_bg.duration)
        # aplica o áudio do COUNTDOWN diretamente no composite final
        if kind == "COUNTDOWN" and 'countdown_audio_mix' in locals() and countdown_audio_mix is not None:
            cena = _with_audio(cena, countdown_audio_mix)

        # SFX em outros segmentos
        if args.sfx:
            from . import sfx as sfxmod
            sfx_overlays = []
            if kind == "HOOK":
                # prioridade: caminho customizado -> nome escolhido -> fallback 'message' -> 'stinger'
                intro_path = None
                if args.intro_sfx_path:
                    p = Path(args.intro_sfx_path)
                    if p.exists() and p.is_file():
                        intro_path = p
                if intro_path is None:
                    name = (args.intro_sfx or "").strip().lower()
                    try:
                        intro_path = Path(sfxmod.get_sfx_path(name))
                    except Exception:
                        try:
                            intro_path = Path(sfxmod.get_sfx_path("message"))
                        except Exception:
                            intro_path = Path(sfxmod.get_sfx_path("stinger"))
                sfx_overlays.append(_with_start(_volumex_clip(_arr_clip_for(str(intro_path)), max(0.05, min(1.0, args.sfx_gain))), 0.0))
                print(f"[SFX] HOOK intro: {intro_path}")
            if kind in ("REVEAL", "REVEAL_EXPLAIN"):
                dn = sfxmod.get_sfx_path("ding")
                wh = sfxmod.get_sfx_path("whoosh")
                sfx_overlays.append(_with_start(_volumex_clip(_arr_clip_for(str(dn)), max(0.05, min(1.0, args.sfx_gain))), 0.0))
                sfx_overlays.append(_with_start(_volumex_clip(_arr_clip_for(str(wh)), max(0.05, min(1.0, args.sfx_gain*0.85))), 0.2))
                print(f"[SFX] REVEAL sfx: {dn}, {wh}")
            if kind == "CTA":
                # prioridade: caminho customizado -> nome escolhido -> fallback 'melody_outro' -> 'chime'
                outro_path = None
                if args.outro_sfx_path:
                    p = Path(args.outro_sfx_path)
                    if p.exists() and p.is_file():
                        outro_path = p
                if outro_path is None:
                    name = (args.outro_sfx or "").strip().lower()
                    try:
                        outro_path = Path(sfxmod.get_sfx_path(name))
                    except Exception:
                        try:
                            outro_path = Path(sfxmod.get_sfx_path("melody_outro"))
                        except Exception:
                            outro_path = Path(sfxmod.get_sfx_path("chime"))
                sfx_overlays.append(_with_start(_volumex_clip(_arr_clip_for(str(outro_path)), max(0.05, min(1.0, args.sfx_gain*0.9))), 0.0))
                print(f"[SFX] CTA outro: {outro_path}")
            # whoosh por alternativa ao chegar (Q/Q_ASK/COUNTDOWN)
            if kind in ("Q", "Q_ASK", "COUNTDOWN"):
                # usa SFX sólido por padrão
                try:
                    opt_path = sfxmod.get_sfx_path((args.option_sfx or "solid_in").strip().lower())
                except Exception:
                    opt_path = sfxmod.get_sfx_path("solid_in")
                opts_local = seg.get("options") or []
                # escalonamento: se COUNTDOWN + stagger, alinha nos segundos; caso contrário, atrasos curtos
                for i, _ in enumerate(opts_local[:5]):
                    if kind == "COUNTDOWN" and args.countdown_stagger_options:
                        start = float(i)
                    else:
                        start = min(0.22, 0.06 * i)
                    sfx_overlays.append(_with_start(_volumex_clip(_arr_clip_for(str(opt_path)), max(0.05, min(1.0, args.sfx_gain*0.85))), float(start)))
                if opts_local:
                    print(f"[SFX] OPTIONS sfx x{min(5, len(opts_local))}: {opt_path}")
            if sfx_overlays:
                base_audio = cena.audio if hasattr(cena, 'audio') and cena.audio else None
                if base_audio is None:
                    n = max(1, int(44100 * slice_bg.duration))
                    silent = np.zeros((n, 2), dtype=np.float32)
                    from moviepy.audio.AudioClip import AudioArrayClip
                    base_audio = AudioArrayClip(silent, fps=44100)
                mix = CompositeAudioClip([base_audio] + sfx_overlays)
                mix.fps = 44100
                cena = _with_audio(cena, mix)
        cenas.append(cena)
        t += slice_bg.duration

    out = concatenate_videoclips(cenas)
    # escolhe FPS de saída
    out_fps = args.fps if args.fps and args.fps > 0 else getattr(base, "fps", 30) or 30

    ffmpeg_params = ["-pix_fmt","yuv420p","-preset", args.preset]
    extra = {}
    if args.bitrate:
        extra["bitrate"] = args.bitrate
    else:
        ffmpeg_params += ["-crf", str(args.crf)]

    out.write_videofile(
        str(FINAL_MP4),
        codec="libx264",
        audio_codec="aac",
        fps=out_fps,
        temp_audiofile=str(OUT_DIR / "temp-audio.m4a"),
        remove_temp=True,
        ffmpeg_params=ffmpeg_params,
        **extra,
    )
    print(f"✅ Vídeo final: {FINAL_MP4}")


if __name__ == "__main__":
    main()
