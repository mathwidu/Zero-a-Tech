import os
import json
import requests
from dotenv import load_dotenv
from pathlib import Path
from PIL import Image
import openai

# 🔐 Carrega as chaves do .env
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# 🗂️ Caminhos
dialogo_path = Path("output/dialogo_estruturado.json")
output_dir_raw = Path("assets/imagens_geradas")
output_dir_final = Path("assets/imagens_geradas_padronizadas")
output_para_video = Path("output")
output_dir_raw.mkdir(parents=True, exist_ok=True)
output_dir_final.mkdir(parents=True, exist_ok=True)
output_para_video.mkdir(parents=True, exist_ok=True)

# 📤 Carrega o diálogo estruturado
with dialogo_path.open("r", encoding="utf-8") as f:
    falas = json.load(f)

print(f"🔍 Total de falas no roteiro: {len(falas)}")

# 🧼 Função para padronizar imagens com Pillow
def padronizar_imagem(path_img, saida_path, tamanho=(1024, 1024)):
    with Image.open(path_img) as img:
        img = img.convert("RGBA")
        img = img.resize(tamanho, Image.LANCZOS)
        img.save(saida_path)

# 🧠 Decide o estilo com base no conteúdo da imagem
def classificar_estilo(prompt_base):
    realistas = [
        "iphone", "apple", "android", "samsung", "neuralink", "elon musk", "oculus",
        "carro", "google", "tecnologia", "inteligência artificial", "chip", "realidade virtual",
        "servidor", "smartphone", "chatgpt", "openai"
    ]
    return "realista" if any(p in prompt_base.lower() for p in realistas) else "cartoon"

# 🎨 Geração de imagens
contador = 1
for i, fala in enumerate(falas):
    prompt_base = fala.get("imagem")

    if not prompt_base:
        continue  # pula falas sem imagem

    estilo = classificar_estilo(prompt_base)

    if estilo == "realista":
        prompt_completo = (
            f"{prompt_base}. "
            "Ultra-realistic photography, cinematic lighting, highly detailed render, "
            "shallow depth of field, realistic background, natural colors, DSLR camera quality, "
            "sharp focus, 1024x1024 resolution, no text, clean and clear presentation."
        )
    else:
        prompt_completo = (
            f"{prompt_base}. "
            "Ultra expressive cartoon style, exaggerated facial features, bright saturated colors, clean vector look, "
            "meme-like energy, centered composition, pop art background, thick outlines, modern youth aesthetic, "
            "inspired by viral TikToks and animated memes, 1024x1024 resolution, no text, high visual impact."
        )

    print(f"\n🖼️ Gerando imagem {contador} ({estilo.upper()}):\n{prompt_completo}\n")

    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt_completo,
            n=1,
            size="1024x1024",
            response_format="url"
        )
        url = response.data[0].url

        # salva imagem original
        nome_raw = output_dir_raw / f"img_raw_{contador:02}.png"
        img_data = requests.get(url).content
        with open(nome_raw, "wb") as f:
            f.write(img_data)

        # padroniza imagem
        nome_final = output_dir_final / f"img_{contador:02}.png"
        padronizar_imagem(nome_raw, nome_final)
        print(f"✅ Imagem padronizada salva em: {nome_final}")

        # salva para o vídeo maker
        video_final_path = output_para_video / f"imagem_{contador:02}.png"
        padronizar_imagem(nome_raw, video_final_path)
        print(f"📎 Imagem copiada para vídeo maker: {video_final_path}")

        contador += 1

    except Exception as e:
        print(f"❌ Erro ao gerar imagem para fala {i}: {e}")

print("\n🏁 Fim da geração de imagens.")
