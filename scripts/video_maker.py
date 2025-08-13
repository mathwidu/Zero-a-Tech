import os
import glob
import json
import random
import numpy as np

from moviepy import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips

from pydub import AudioSegment
from pydub.utils import make_chunks
from PIL import Image, ImageDraw, ImageFont, ImageOps

# ———— CONFIGURAÇÕES ———————————————————————
fundo_path = random.choice(glob.glob("assets/videos_fundo/*.mp4"))
saida_path = "output/video_final.mp4"
altura_personagem = 800
margem = 50
fonte_padrao = "assets/fonts/LuckiestGuy-Regular.ttf"
MANIFEST_PATH = "output/imagens_manifest.json"

def carregar_manifest():
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return { item["fala_index"]: item["arquivo_video"] for item in data.get("itens", []) }
    return {}

manifest_map = carregar_manifest()
print(f"[DEBUG] imagens no manifest: {len(manifest_map)}")

def construir_lista_falas():
    arquivos_audio = sorted(glob.glob("output/fala_*.mp3"))
    personagens = ["JOÃO", "ZÉ BOT"]
    lista_falas = []

    for i, caminho in enumerate(arquivos_audio):
        nome = personagens[i % 2]
        imagens = {
            "fechada": f"assets/personagens/{'joao' if nome == 'JOÃO' else 'zebot'}.png",
            "aberta": f"assets/personagens/{'joaoaberto' if nome == 'JOÃO' else 'zebot_aberto'}.png",
            "aberta2": f"assets/personagens/{'joaoaberto' if nome == 'JOÃO' else 'zebot_aberto2'}.png",
            "piscar": f"assets/personagens/{'joaoaberto2' if nome == 'JOÃO' else 'zebot_piscar'}.png"
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
    clip_aberta = imagem_padronizada(imagens["aberta"], altura_personagem)
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
    """Carrega a imagem preservando o canal alfa original e redimensiona para o tamanho desejado."""
    img = Image.open(imagem_path).convert("RGBA").resize(tamanho_alvo, Image.LANCZOS)
    rgba = np.array(img)  # H×W×4
    rgb = rgba[..., :3]
    alpha = rgba[..., 3].astype(np.float32) / 255.0  # 0–1
    return rgb, alpha



# ———— INÍCIO DO PROCESSAMENTO ———————————————————————
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

cenas, t_acc = [], 0
for i, f in enumerate(falas):
    audio_clip = AudioFileClip(f["audio"])
    dur = audio_clip.duration
    fundo_c = fundo_video.subclipped(t_acc, t_acc + dur).with_audio(audio_clip).with_duration(dur)
    pers = animar_personagem_com_audio(f["audio"], dur, f["posicao"], f["imagens"], fundo_w, fundo_h, f["nome"])

    imagem_ilustrativa = None
    imagem_ilustrativa_path = manifest_map.get(i)  # pega o arquivo certo pelo índice da fala

    if imagem_ilustrativa_path and os.path.exists(imagem_ilustrativa_path):
        print(f"[DEBUG] Adicionando imagem estilizada para fala {i+1}: {imagem_ilustrativa_path}")
        altura_img = int(fundo_h * 0.4)
        largura_img = int(altura_img * 0.85)
        rgb_np, alpha_np = criar_borda_glow(imagem_ilustrativa_path, (largura_img, altura_img))

        max_dur = min(3, dur)  # duração da imagem no início da fala

        # 🔧 FIX: empilha o alfa (H×W) em 3 canais para o to_mask()
        alpha_u8 = (alpha_np * 255).astype("uint8")               # H×W (0–255)
        alpha_rgb = np.dstack([alpha_u8, alpha_u8, alpha_u8])     # H×W×3

        mask_clip = ImageClip(alpha_rgb).to_mask().with_duration(max_dur)

        imagem_ilustrativa = (
            ImageClip(rgb_np)
            .with_mask(mask_clip)
            .with_start(0.2)  # relativo à cena
            .with_duration(max_dur)
            .with_position(("center", int(fundo_h * 0.08)))
            .with_opacity(0.85)
        )

    else:
        print(f"[DEBUG] Nenhuma imagem ilustrativa para fala {i+1}")

    json_path = f"output/fala_{i+1:02}_words.json"
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
        print(f"[AVISO] JSON não encontrado para fala {i+1}")

    t_acc += dur

video = concatenate_videoclips(cenas)
video.write_videofile(saida_path, codec="libx264", audio_codec="aac", fps=30,
                      temp_audiofile="temp-audio.m4a", remove_temp=True)
