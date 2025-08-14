#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, glob, json, random
import numpy as np

from moviepy import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips
from pydub import AudioSegment
from pydub.utils import make_chunks
from PIL import Image, ImageDraw, ImageFont

# ———— CONFIG ————————————————————————————————
fundo_path = random.choice(glob.glob("assets/videos_fundo/*.mp4"))
saida_path = "output/video_final.mp4"
altura_personagem = 800
margem = 50
fonte_padrao = "assets/fonts/LuckiestGuy-Regular.ttf"

DIALOGO_PATH  = "output/dialogo_estruturado.json"
MANIFEST_PATH = "output/imagens_manifest.json"

# ———— JSON helpers ———————————————————————————
def _load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def ler_dialogo():
    dialogo = _load_json(DIALOGO_PATH, [])
    lines_with_image_1b = [i for i, it in enumerate(dialogo, start=1) if it.get("imagem")]
    ord_by_line = {ln: k for k, ln in enumerate(lines_with_image_1b, start=1)}  # 1ª fala com imagem -> 1, etc.
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
    """Se faltar imagem no manifest, usa output/imagem_{ord}.png pelo ordinal daquela fala."""
    if line_1b not in ord_by_line:
        return None
    ord_pos = ord_by_line[line_1b]  # 1..N
    return f"output/imagem_{ord_pos:02}.png"

def pegar_tempo(line_1b, dur, times):
    if line_1b in times:
        t0, t1 = times[line_1b]
    else:
        t0, t1 = 0.2, min(3.0, dur)
    t0 = max(0.0, min(t0, dur))
    t1 = max(t0 + 0.05, min(t1, dur))
    return t0, t1

# ———— BOCA/LEGENDAS ———————————————————————————
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

def imagem_padronizada(caminho, altura):
    return ImageClip(caminho).resized(height=altura).with_duration(0.1)

def render_legenda_com_cores(palavras_coloridas, largura, altura, font_size=72, fonte=fonte_padrao):
    img = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(fonte, font_size)
    except Exception as e:
        print(f"[FALLBACK FONT] {e}")
        font = ImageFont.load_default()

    linhas, linha_atual, largura_atual = [], [], 0
    for palavra, cor in palavras_coloridas:
        w = draw.textlength(palavra + " ", font=font)
        if largura_atual + w > largura - 60:
            linhas.append(linha_atual)
            linha_atual, largura_atual = [(palavra, cor)], w
        else:
            linha_atual.append((palavra, cor))
            largura_atual += w
    if linha_atual:
        linhas.append(linha_atual)

    y_offset = (altura - len(linhas) * (font_size + 10)) // 2
    for i, linha in enumerate(linhas):
        total_l = sum(draw.textlength(p + " ", font=font) for p, _ in linha)
        x = (largura - total_l) // 2
        for palavra, cor in linha:
            for dx in (-2, 2):
                for dy in (-2, 2):
                    draw.text((x + dx, y_offset + i*(font_size+10) + dy), palavra, font=font, fill="black")
            draw.text((x, y_offset + i*(font_size+10)), palavra, font=font, fill=cor)
            x += draw.textlength(palavra + " ", font=font)
    return ImageClip(np.array(img))

def gerar_legenda_clip_palavra(palavras_json, largura, altura):
    clips = []
    for palavra in palavras_json:
        img = render_legenda_com_cores([(palavra["word"], "#FFA500")], largura, 600)
        clip = img.with_position(("center", altura - 1200)).with_start(palavra["start"]).with_end(palavra["end"])
        clips.append(clip)
    return CompositeVideoClip(clips, size=(largura, altura)).with_start(clips[0].start).with_end(clips[-1].end)

def animar_personagem_com_audio(audio_path, duracao, posicao, imagens, fundo_w, fundo_h, nome):
    audio = AudioSegment.from_file(audio_path)
    chunks = make_chunks(audio, 300)
    frames = []
    clip_fechada = imagem_padronizada(imagens["fechada"], altura_personagem)
    clip_aberta  = imagem_padronizada(imagens["aberta"],  altura_personagem)
    clip_aberta2 = imagem_padronizada(imagens["aberta2"], altura_personagem)
    piscar = np.random.randint(1, len(chunks)-2) if duracao > 5 and np.random.rand() < 0.3 else -1
    alternar = True

    for i, chunk in enumerate(chunks):
        if i == piscar:
            sprite = imagem_padronizada(imagens["piscar"], altura_personagem)
        elif chunk.rms > 400:
            sprite = clip_aberta if alternar else clip_aberta2
            alternar = not alternar
        else:
            sprite = clip_fechada
        iw, ih = sprite.size
        x = margem if posicao == "esquerda" else fundo_w - iw - margem
        y = fundo_h - ih - margem
        frame = sprite.with_position((x, y)).with_duration(0.3)
        frames.append(CompositeVideoClip([frame], size=(fundo_w, fundo_h)))
    return concatenate_videoclips(frames).with_duration(duracao)

def ler_json_legenda(caminho):
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)

def criar_borda_glow(imagem_path, tamanho_alvo):
    img = Image.open(imagem_path).convert("RGBA").resize(tamanho_alvo, Image.LANCZOS)
    rgba = np.array(img)  # H×W×4
    rgb = rgba[..., :3]
    alpha = rgba[..., 3].astype(np.float32) / 255.0
    return rgb, alpha

# ———— PROCESSO ————————————————————————————————
dialogo, lines_with_image_1b, ord_by_line = ler_dialogo()
manifest_imgs, manifest_times = carregar_manifest()

falas = construir_lista_falas()
duracao_total_falas = sum(AudioFileClip(f["audio"]).duration for f in falas)

fundo_video = VideoFileClip(fundo_path)
fundo_w, fundo_h = fundo_video.size
print(f"[DEBUG] fundo size = {fundo_w} × {fundo_h}")

if fundo_video.duration > duracao_total_falas:
    inicio = random.uniform(0, fundo_video.duration - duracao_total_falas)
    fundo_video = fundo_video.subclipped(inicio, inicio + duracao_total_falas)
else:
    inicio = 0

cenas, t_acc = [], 0.0
for i, f in enumerate(falas):
    fala_idx = i + 1  # 1-based p/ casar com manifest
    audio_clip = AudioFileClip(f["audio"])
    dur = audio_clip.duration
    fundo_c = fundo_video.subclipped(t_acc, t_acc + dur).with_audio(audio_clip).with_duration(dur)
    pers = animar_personagem_com_audio(f["audio"], dur, f["posicao"], f["imagens"], fundo_w, fundo_h, f["nome"])

    imagem_ilustrativa = None

    if fala_idx in lines_with_image_1b:
        img_path = manifest_imgs.get(fala_idx) or fallback_img_for_line(fala_idx, ord_by_line)
        if img_path and os.path.exists(img_path):
            t0, t1 = pegar_tempo(fala_idx, dur, manifest_times)
            print(f"[SYNC] fala {fala_idx:02d} → img={os.path.basename(img_path)} @ {t0:.2f}-{t1:.2f}")

            altura_img = int(fundo_h * 0.4)
            largura_img = int(altura_img * 0.85)
            rgb_np, alpha_np = criar_borda_glow(img_path, (largura_img, altura_img))

            alpha_u8 = (alpha_np * 255).astype("uint8")
            alpha_rgb = np.dstack([alpha_u8, alpha_u8, alpha_u8])
            mask_clip = ImageClip(alpha_rgb).to_mask().with_duration(t1 - t0)

            imagem_ilustrativa = (
                ImageClip(rgb_np)
                .with_mask(mask_clip)
                .with_start(t0)
                .with_duration(t1 - t0)
                .with_position(("center", int(fundo_h * 0.08)))
                .with_opacity(0.85)
            )
        else:
            print(f"[WARN] Sem imagem para fala {fala_idx} (esperada pelo diálogo).")
    else:
        # diálogo não pede imagem nesta fala
        pass

    json_path = f"output/fala_{fala_idx:02}_words.json"  # words são 1-based
    if os.path.exists(json_path):
        palavras_json = ler_json_legenda(json_path)
        legenda_clip = gerar_legenda_clip_palavra(palavras_json, fundo_w, fundo_h)

        camadas = [fundo_c]
        if imagem_ilustrativa:
            camadas.append(imagem_ilustrativa)
        camadas += [pers, legenda_clip]

        cena = CompositeVideoClip(camadas, size=(fundo_w, fundo_h)).with_duration(dur)
        cenas.append(cena)
    else:
        print(f"[AVISO] JSON não encontrado para fala {fala_idx}")

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
