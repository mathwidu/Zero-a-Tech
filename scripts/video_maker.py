#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Video maker com normalização de fundo (qualquer resolução) e compat MoviePy 1.x/2.x.
- Canvas padrão 1080x1920 (9:16).
- Fundo em mode="crop" (preenche sem bordas) ou mode="blur" (fit com fundo desfocado).
- Sprites/personagens dimensionados de forma segura (nada fica fora da tela).
- Legendas por palavra (se existir output/fala_XX_words.json).
- Imagens editoriais posicionadas e mascaradas com segurança.
"""

import os, glob, json, random
import numpy as np

from moviepy import VideoFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips, vfx
try:
    from moviepy import AudioFileClip
except Exception:
    AudioFileClip = None

from pydub import AudioSegment
from pydub.utils import make_chunks
from PIL import Image, ImageDraw, ImageFont

# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────────
fundo_path = random.choice(glob.glob("assets/videos_fundo/*.mp4")) if glob.glob("assets/videos_fundo/*.mp4") else None
saida_path = "output/video_final.mp4"

# Canvas vertical padrão
TARGET_W, TARGET_H = 1080, 1920

# Personagens
ALTURA_PERSONAGEM_MAX = 800
MARGEM = 50
FONTE_PADRAO = "assets/fonts/LuckiestGuy-Regular.ttf"

# Diálogo/manifest
DIALOGO_PATH  = "output/dialogo_estruturado.json"
MANIFEST_PATH = "output/imagens_manifest.json"

# ──────────────────────────────────────────────────────────────────────────────
# Helpers de compatibilidade MoviePy (1.x vs 2.x)
# ──────────────────────────────────────────────────────────────────────────────
def _resize_clip(clip, factor=None, newsize=None):
    """Compat: 2.x (resized) x 1.x (resize)."""
    if hasattr(clip, "resized"):
        if factor is not None:
            return clip.resized(factor)
        return clip.resized(newsize=newsize)
    else:
        if factor is not None:
            return clip.resize(factor)
        return clip.resize(newsize=newsize)

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

def _with_opacity(clip, val):
    return clip.with_opacity(val) if hasattr(clip, "with_opacity") else clip.set_opacity(val)

def _subclip(clip, t0, t1):
    return clip.subclipped(t0, t1) if hasattr(clip, "subclipped") else clip.subclip(t0, t1)

# ──────────────────────────────────────────────────────────────────────────────
# JSON helpers
# ──────────────────────────────────────────────────────────────────────────────
def _load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def ler_dialogo():
    dialogo = _load_json(DIALOGO_PATH, [])
    lines_with_image_1b = [i for i, it in enumerate(dialogo, start=1) if it.get("imagem")]
    ord_by_line = {ln: k for k, ln in enumerate(lines_with_image_1b, start=1)}
    return dialogo, set(lines_with_image_1b), ord_by_line

def carregar_manifest():
    data = _load_json(MANIFEST_PATH, {"itens": []})
    imgs, times = {}, {}
    for it in data.get("itens", []):
        try:
            ln = int(it.get("fala_index"))
        except Exception:
            continue
        if ln < 1:
            continue
        if it.get("arquivo_video"):
            imgs[ln] = it["arquivo_video"]
        if it.get("t_inicio") is not None and it.get("t_fim") is not None:
            times[ln] = (float(it["t_inicio"]), float(it["t_fim"]))
    return imgs, times

def fallback_img_for_line(line_1b, ord_by_line):
    if line_1b not in ord_by_line:
        return None
    ord_pos = ord_by_line[line_1b]
    return f"output/imagem_{ord_pos:02}.png"

def pegar_tempo(line_1b, dur, times):
    if line_1b in times:
        t0, t1 = times[line_1b]
    else:
        t0, t1 = 0.2, min(3.0, dur)
    t0 = max(0.0, min(t0, dur))
    t1 = max(t0 + 0.05, min(t1, dur))
    return t0, t1

# ──────────────────────────────────────────────────────────────────────────────
# Fundo → Normalização para 1080×1920 (sem depender de vfx.crop)
# ──────────────────────────────────────────────────────────────────────────────
def normalize_background_to_vertical(clip, target_w=TARGET_W, target_h=TARGET_H, mode="crop"):
    """
    mode="crop": preenche a tela (zoom/crop central), SEM bordas, via composição/clipping.
    mode="blur": cria background desfocado 9:16 e o vídeo original "fit" por cima (usa vfx.* se existir).
    """
    w, h = clip.size

    if mode == "crop":
        # Escala para COBRIR (cover) e centraliza; o excedente fica fora e é "cortado" pelo canvas do Composite
        scale = max(target_w / w, target_h / h)
        scaled = _resize_clip(clip, factor=scale)
        # centralizar dentro do canvas target
        x = int((target_w - scaled.w) / 2)
        y = int((target_h - scaled.h) / 2)
        comp = CompositeVideoClip([_with_position(scaled, (x, y))], size=(target_w, target_h))
        return _with_duration(comp, clip.duration)

    # mode == "blur"
    # BG: cobre 9:16 e aplica blur/ajustes (se disponíveis)
    scale_bg = max(target_w / w, target_h / h)
    bg = _resize_clip(clip, factor=scale_bg)
    try:
        bg = vfx.gaussian_blur(bg, sigma=12)
    except Exception:
        pass
    try:
        bg = vfx.colorx(bg, 0.9)
    except Exception:
        pass
    try:
        bg = vfx.lum_contrast(bg, contrast=10, lum=-5, contrast_thr=127)
    except Exception:
        pass

    # FG: cabe inteiro (fit), centralizado
    scale_fit = min(target_w / w, target_h / h)
    fg = _resize_clip(clip, factor=scale_fit)
    fg = _with_position(fg, ("center", "center"))

    comp = CompositeVideoClip([_with_position(bg, ("center", "center")), fg], size=(target_w, target_h))
    return _with_duration(comp, clip.duration)

# ──────────────────────────────────────────────────────────────────────────────
# Sprites / Legendas
# ──────────────────────────────────────────────────────────────────────────────
def imagem_padronizada(caminho, altura_desejada, fundo_h):
    altura_segura = max(50, min(altura_desejada, int(fundo_h * 0.7)))
    img = ImageClip(caminho)
    # escala preservando proporção pela altura
    scale = altura_segura / img.h if img.h else 1.0
    img = _resize_clip(img, factor=scale)
    return _with_duration(img, 0.1)

def _textlength(draw, text, font):
    # PIL 10: draw.textlength; fallback: font.getlength
    try:
        return draw.textlength(text, font=font)
    except Exception:
        try:
            return font.getlength(text)
        except Exception:
            return len(text) * (font.size * 0.6 if hasattr(font, "size") else 10)

def render_legenda_com_cores(palavras_coloridas, largura, altura, font_size, fonte=FONTE_PADRAO):
    img = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(fonte, font_size)
    except Exception as e:
        print(f"[FALLBACK FONT] {e}")
        font = ImageFont.load_default()

    linhas, linha_atual, largura_atual = [], [], 0
    for palavra, cor in palavras_coloridas:
        w = _textlength(draw, palavra + " ", font)
        if largura_atual + w > largura - 60:
            if linha_atual:
                linhas.append(linha_atual)
            linha_atual, largura_atual = [(palavra, cor)], w
        else:
            linha_atual.append((palavra, cor))
            largura_atual += w
    if linha_atual:
        linhas.append(linha_atual)

    y_offset = (altura - len(linhas) * (font_size + 10)) // 2
    for i, linha in enumerate(linhas):
        total_l = sum(_textlength(draw, p + " ", font) for p, _ in linha)
        x = (largura - total_l) // 2
        for palavra, cor in linha:
            for dx in (-2, 2):
                for dy in (-2, 2):
                    draw.text((x + dx, y_offset + i*(font_size+10) + dy), palavra, font=font, fill="black")
            draw.text((x, y_offset + i*(font_size+10)), palavra, font=font, fill=cor)
            x += _textlength(draw, palavra + " ", font)
    return ImageClip(np.array(img))

def gerar_legenda_clip_palavra(palavras_json, largura, altura):
    if not palavras_json:
        return None
    font_size = max(36, int(altura * 0.035))
    caixa_h   = max(200, int(altura * 0.18))
    y_pos     = int(altura * 0.75) - caixa_h // 2

    clips = []
    for palavra in palavras_json:
        img = render_legenda_com_cores([(palavra["word"], "#FFA500")], largura, caixa_h, font_size=font_size)
        y = max(0, min(y_pos, altura - caixa_h))
        clip = _with_position(img, ("center", y))
        clip = _with_start(clip, palavra["start"])
        clip = _with_end(clip, palavra["end"])
        clips.append(clip)
    comp = CompositeVideoClip(clips, size=(largura, altura))
    comp = _with_start(comp, clips[0].start)
    comp = _with_end(comp, clips[-1].end)
    return comp

def construir_lista_falas():
    arquivos_audio = sorted(glob.glob("output/fala_*.mp3"))
    personagens = ["JOÃO", "ZÉ BOT"]
    lista_falas = []
    for i, caminho in enumerate(arquivos_audio):
        nome = personagens[i % 2]
        imagens = {
            "fechada": f"assets/personagens/{'joao' if nome == 'JOÃO' else 'zebot'}.png",
            "aberta":  f"assets/personagens/{'joaoaberto' if nome == 'JOÃO' else 'zebot_aberto'}.png",
            "aberta2": f"assets/personagens/{'joaoaberto' if nome == 'JOÃO' else 'zebot_aberto2'}.png",
            "piscar":  f"assets/personagens/{'joaoaberto2' if nome == 'JOÃO' else 'zebot_piscar'}.png"
        }
        posicao = "esquerda" if nome == "JOÃO" else "direita"
        lista_falas.append({
            "audio": caminho,
            "imagens": imagens,
            "posicao": posicao,
            "nome": nome
        })
    return lista_falas[:]

def ler_json_legenda(caminho):
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)

def criar_borda_glow(imagem_path, tamanho_alvo):
    img = Image.open(imagem_path).convert("RGBA").resize(tamanho_alvo, Image.LANCZOS)
    rgba = np.array(img)
    rgb = rgba[..., :3]
    alpha = rgba[..., 3].astype(np.float32) / 255.0
    return rgb, alpha

def animar_personagem_com_audio(audio_path, duracao, posicao, imagens, fundo_w, fundo_h, nome):
    audio = AudioSegment.from_file(audio_path)
    chunks = make_chunks(audio, 300)

    # sprites com altura segura ao canvas
    clip_fechada = imagem_padronizada(imagens["fechada"], ALTURA_PERSONAGEM_MAX, fundo_h)
    clip_aberta  = imagem_padronizada(imagens["aberta"],  ALTURA_PERSONAGEM_MAX, fundo_h)
    clip_aberta2 = imagem_padronizada(imagens["aberta2"], ALTURA_PERSONAGEM_MAX, fundo_h)

    piscar = np.random.randint(1, max(2, len(chunks)-2)) if duracao > 5 and np.random.rand() < 0.3 else -1
    alternar = True

    frames = []
    for i, chunk in enumerate(chunks):
        if i == piscar:
            sprite = imagem_padronizada(imagens["piscar"], ALTURA_PERSONAGEM_MAX, fundo_h)
        elif chunk.rms > 400:
            sprite = clip_aberta if alternar else clip_aberta2
            alternar = not alternar
        else:
            sprite = clip_fechada

        iw, ih = (sprite.w, sprite.h) if hasattr(sprite, "w") else sprite.size
        x = MARGEM if posicao == "esquerda" else fundo_w - iw - MARGEM
        y = max(0, fundo_h - ih - MARGEM)  # nunca negativo

        frame = _with_position(sprite, (x, y))
        frame = _with_duration(frame, 0.3)
        frames.append(CompositeVideoClip([frame], size=(fundo_w, fundo_h)))
    return _with_duration(concatenate_videoclips(frames), duracao)

# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE
# ──────────────────────────────────────────────────────────────────────────────
def main():
    if not fundo_path:
        raise RuntimeError("Nenhum vídeo encontrado em assets/videos_fundo/*.mp4")

    dialogo, lines_with_image_1b, ord_by_line = ler_dialogo()
    manifest_imgs, manifest_times = carregar_manifest()

    falas = construir_lista_falas()
    if not falas:
        raise RuntimeError("Nenhum áudio encontrado em output/fala_*.mp3")

    if AudioFileClip is None:
        raise RuntimeError("AudioFileClip não disponível na sua instalação do MoviePy.")

    duracao_total_falas = sum(AudioFileClip(f["audio"]).duration for f in falas)

    fundo_original = VideoFileClip(fundo_path)
    print(f"[DEBUG] fundo original size = {fundo_original.w} × {fundo_original.h}")

    # Use "crop" para preencher sem bordas; troque para "blur" se quiser evitar recortes
    fundo_base = normalize_background_to_vertical(fundo_original, TARGET_W, TARGET_H, mode="crop")
    fundo_w, fundo_h = fundo_base.size
    print(f"[DEBUG] fundo normalizado = {fundo_w} × {fundo_h}")

    if fundo_base.duration > duracao_total_falas:
        inicio = random.uniform(0, fundo_base.duration - duracao_total_falas)
        fundo_base = _subclip(fundo_base, inicio, inicio + duracao_total_falas)
    else:
        inicio = 0

    cenas, t_acc = [], 0.0
    for i, f in enumerate(falas):
        fala_idx = i + 1
        audio_clip = AudioFileClip(f["audio"])
        dur = audio_clip.duration

        # slice do fundo + áudio da fala
        fundo_c = _subclip(fundo_base, t_acc, t_acc + dur)
        fundo_c = _with_audio(fundo_c, audio_clip)
        fundo_c = _with_duration(fundo_c, dur)

        # personagem adaptativo
        pers = animar_personagem_com_audio(f["audio"], dur, f["posicao"], f["imagens"], fundo_w, fundo_h, f["nome"])

        # imagem editorial (opcional)
        imagem_ilustrativa = None
        if fala_idx in lines_with_image_1b:
            img_path = manifest_imgs.get(fala_idx) or fallback_img_for_line(fala_idx, ord_by_line)
            if img_path and os.path.exists(img_path):
                t0, t1 = pegar_tempo(fala_idx, dur, manifest_times)
                print(f"[SYNC] fala {fala_idx:02d} → img={os.path.basename(img_path)} @ {t0:.2f}-{t1:.2f}")

                altura_img = int(fundo_h * 0.4)
                largura_img = int(altura_img * 0.85)
                largura_img = max(50, min(largura_img, fundo_w - 2*MARGEM))
                altura_img  = max(50, min(altura_img,  int(fundo_h * 0.45)))

                rgb_np, alpha_np = criar_borda_glow(img_path, (largura_img, altura_img))
                if rgb_np.shape[0] > 0 and rgb_np.shape[1] > 0:
                    alpha_u8 = (alpha_np * 255).astype("uint8")
                    alpha_rgb = np.dstack([alpha_u8, alpha_u8, alpha_u8])

                    dur_img = max(0.05, t1 - t0)
                    y_top = int(fundo_h * 0.08)
                    y_top = max(0, min(y_top, fundo_h - altura_img))  # clamp vertical

                    mask_clip = ImageClip(alpha_rgb).to_mask()
                    mask_clip = _with_duration(mask_clip, dur_img)

                    imagem_ilustrativa = ImageClip(rgb_np)
                    # compat: set_mask vs with_mask
                    if hasattr(imagem_ilustrativa, "set_mask"):
                        imagem_ilustrativa = imagem_ilustrativa.set_mask(mask_clip)
                    else:
                        imagem_ilustrativa = imagem_ilustrativa.with_mask(mask_clip)

                    imagem_ilustrativa = _with_start(imagem_ilustrativa, t0)
                    imagem_ilustrativa = _with_duration(imagem_ilustrativa, dur_img)
                    imagem_ilustrativa = _with_position(imagem_ilustrativa, ("center", y_top))
                    imagem_ilustrativa = _with_opacity(imagem_ilustrativa, 0.95)
            else:
                print(f"[WARN] Sem imagem para fala {fala_idx} (esperada pelo diálogo).")

        # legendas por palavra (se existirem)
        json_path = f"output/fala_{fala_idx:02}_words.json"
        legenda_clip = None
        if os.path.exists(json_path):
            palavras_json = ler_json_legenda(json_path)
            legenda_clip = gerar_legenda_clip_palavra(palavras_json, fundo_w, fundo_h)

        # monta a cena (ordem: fundo, imagem opcional, personagem, legendas)
        camadas = [fundo_c, pers]
        if imagem_ilustrativa:
            camadas.insert(1, imagem_ilustrativa)
        if legenda_clip:
            camadas.append(legenda_clip)

        cena = CompositeVideoClip(camadas, size=(fundo_w, fundo_h))
        cena = _with_duration(cena, dur)
        cenas.append(cena)

        t_acc += dur

    video = concatenate_videoclips(cenas)
    video.write_videofile(
        saida_path,
        codec="libx264",
        audio_codec="aac",
        fps=30,
        temp_audiofile="temp-audio.m4a",
        remove_temp=True
    )

# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
