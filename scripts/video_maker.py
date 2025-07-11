import os
import re
import glob
import json
import numpy as np
from moviepy import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips
from pydub import AudioSegment
from pydub.utils import make_chunks
from PIL import Image, ImageDraw, ImageFont

# ———— CONFIGURAÇÕES —————————————
fundo_path = "assets/videos_fundo/videofundomine.mp4"
saida_path = "output/video_final.mp4"
altura_personagem = 800
margem = 50
fonte_padrao = "assets/fonts/LuckiestGuy-Regular.ttf"

def construir_lista_falas():
    arquivos_audio = sorted(glob.glob("output/fala_*.mp3"))
    personagens = ["JOÃO", "ZÉ BOT"]
    lista_falas = []

    for i, caminho in enumerate(arquivos_audio):
        nome = personagens[i % 2]
        if nome == "JOÃO":
            imagens = {
                "fechada": "assets/personagens/joao.png",
                "aberta": "assets/personagens/joaoaberto.png",
                "piscar": "assets/personagens/joaoaberto2.png"
            }
            posicao = "esquerda"
        else:
            imagens = {
                "fechada": "assets/personagens/zebot.png",
                "aberta": "assets/personagens/zebot_aberto.png",
                "piscar": "assets/personagens/zebot_piscar.png"
            }
            posicao = "direita"

        lista_falas.append({
            "audio": caminho,
            "imagens": imagens,
            "posicao": posicao,
            "nome": nome
        })

    return lista_falas

falas = construir_lista_falas()

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

    linhas = []
    linha_atual = []
    largura_atual = 0

    for palavra, cor in palavras_coloridas:
        w = draw.textlength(palavra + " ", font=font)
        if largura_atual + w > largura - 60:
            linhas.append(linha_atual)
            linha_atual = [(palavra, cor)]
            largura_atual = w
        else:
            linha_atual.append((palavra, cor))
            largura_atual += w
    if linha_atual:
        linhas.append(linha_atual)

    y_offset = (altura - len(linhas) * (font_size + 10)) // 2

    for i, linha in enumerate(linhas):
        total_largura = sum(draw.textlength(p + " ", font=font) for p, _ in linha)
        x = (largura - total_largura) // 2
        for palavra, cor in linha:
            for dx in [-2, 2]:
                for dy in [-2, 2]:
                    draw.text((x+dx, y_offset + i*(font_size + 10) + dy), palavra, font=font, fill="black")
            draw.text((x, y_offset + i*(font_size + 10)), palavra, font=font, fill=cor)
            x += draw.textlength(palavra + " ", font=font)

    return ImageClip(np.array(img))

def gerar_legenda_clip_palavra(palavras_json, largura, altura):
    clips = []
    for palavra in palavras_json:
        texto = palavra["word"]
        inicio = palavra["start"]
        fim = palavra["end"]

        img = render_legenda_com_cores([(texto, "#FFA500")], largura, 600, font_size=72)
        clip = img.with_position(("center", altura - 1200))\
                  .with_start(inicio)\
                  .with_end(fim)
        clips.append(clip)

    return CompositeVideoClip(clips, size=(largura, altura)).with_start(clips[0].start).with_end(clips[-1].end)

def animar_personagem_com_audio(audio_path, duracao, posicao, imagens, fundo_w, fundo_h, nome):
    audio = AudioSegment.from_file(audio_path)
    chunks = make_chunks(audio, 300)
    imgs = {k: imagem_padronizada(v, altura_personagem) for k,v in imagens.items()}
    piscar = np.random.randint(1, len(chunks)-2) if duracao>5 and np.random.rand()<0.3 else -1
    frames = []
    for i, chunk in enumerate(chunks):
        rms = chunk.rms
        clip = imgs["piscar"] if i==piscar else imgs["aberta"] if rms>400 else imgs["fechada"]
        iw, ih = clip.size
        pos = (margem, fundo_h-ih-margem) if posicao=="esquerda" else (fundo_w-iw-margem, fundo_h-ih-margem)
        frame = clip.with_position(pos).with_duration(0.3)
        comp = CompositeVideoClip([frame], size=(fundo_w, fundo_h))
        frames.append(comp)
    return concatenate_videoclips(frames).with_duration(duracao)

def ler_json_legenda(caminho):
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)

# ———— CRIAÇÃO DO VÍDEO —————————————

fundo = VideoFileClip(fundo_path)
fundo_w, fundo_h = fundo.size
print(f"[DEBUG] fundo size = {fundo_w} × {fundo_h}")

cenas, t_acc = [], 0
for i, f in enumerate(falas):
    audio_clip = AudioFileClip(f["audio"])
    dur = audio_clip.duration
    fundo_c = fundo.subclipped(t_acc, t_acc + dur).with_audio(audio_clip).with_duration(dur)
    pers = animar_personagem_com_audio(f["audio"], dur, f["posicao"], f["imagens"], fundo_w, fundo_h, f["nome"])

    index = i + 1
    json_path = f"output/fala_{index:02}_words.json"
    if os.path.exists(json_path):
        palavras_json = ler_json_legenda(json_path)
        legenda_clip = gerar_legenda_clip_palavra(palavras_json, fundo_w, fundo_h)
        cena = CompositeVideoClip([fundo_c, pers, legenda_clip], size=(fundo_w, fundo_h)).with_duration(dur)
        cenas.append(cena)
    else:
        print(f"[AVISO] Legenda JSON não encontrada para fala {index}, pulando...")

    t_acc += dur

video = concatenate_videoclips(cenas)
video.write_videofile(saida_path, codec="libx264", audio_codec="aac", fps=30,
                      temp_audiofile="temp-audio.m4a", remove_temp=True)
