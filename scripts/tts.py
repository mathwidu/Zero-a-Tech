from elevenlabs.client import ElevenLabs
from dotenv import load_dotenv
import os

# 🗂️ Constantes
DIALOG_PATH = "output/dialogo.txt"
OUTPUT_DIR = "output"
VOZ_JOAO = "Charlie"
VOZ_ZE = "Daniel"
MODEL_ID = "eleven_multilingual_v2"
FORMAT = "mp3_44100_128"

# 🔐 Carrega API key
load_dotenv()
api_key = os.getenv("ELEVEN_API_KEY")
client = ElevenLabs(api_key=api_key)

# 📖 Lê o diálogo do arquivo
def ler_dialogo():
    if not os.path.exists(DIALOG_PATH):
        print(f"❌ Arquivo de diálogo não encontrado: {DIALOG_PATH}")
        return []
    with open(DIALOG_PATH, "r", encoding="utf-8") as f:
        linhas = f.readlines()
    return [linha.strip() for linha in linhas if linha.strip()]

# 🔊 Gera e salva o áudio com estilo e voz customizada
def gerar_audio(texto: str, index: int, voice_name: str):
    voice = next((v for v in client.voices.get_all().voices if v.name == voice_name), None)
    if not voice:
        raise ValueError(f"❌ Voz '{voice_name}' não encontrada!")

    print(f"🎙️ {voice_name}: {texto}")

    # 🎛️ Ajustes personalizados para fluidez
    voice_settings = {
        "stability": 0.2 if voice_name == VOZ_ZE else 0.4,
        "similarity_boost": 0.85 if voice_name == VOZ_ZE else 0.75,
    }

    # 🔁 Se a voz for do Zé Bot, ajusta velocidade
    if voice_name == VOZ_ZE:
        voice_settings["speed"] = 1.0

    try:
        audio_stream = client.text_to_speech.convert(
            text=texto,
            voice_id=voice.voice_id,
            model_id=MODEL_ID,
            output_format=FORMAT,
            voice_settings=voice_settings
        )

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        file_path = os.path.join(OUTPUT_DIR, f"fala_{index:02d}.mp3")
        with open(file_path, "wb") as f:
            for chunk in audio_stream:
                f.write(chunk)

        print(f"✅ Fala {index} salva: fala_{index:02d}.mp3")
    except Exception as e:
        print(f"⚠️ Erro ao gerar fala {index}: {e}")

# ▶️ Execução principal
if __name__ == "__main__":
    print("📖 Lendo roteiro...")
    falas = ler_dialogo()

    if not falas:
        print("❌ Nenhuma fala encontrada.")
        exit()

    print(f"💬 Total de falas: {len(falas)}")

    for i, fala in enumerate(falas, start=1):
        personagem = fala.split(":", 1)[0].strip().lower()

        if personagem == "joão":
            texto_limpo = fala.split(":", 1)[1].strip()
            gerar_audio(texto_limpo, i, VOZ_JOAO)
        elif personagem in ["zé bot", "zébot"]:
            texto_limpo = fala.split(":", 1)[1].strip()
            gerar_audio(texto_limpo, i, VOZ_ZE)
        else:
            print(f"⚠️ Fala {i} não identificada com personagem: {fala}")
