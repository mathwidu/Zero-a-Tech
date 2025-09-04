# file: replicate_pipeline.py
import os
from pathlib import Path
from uuid import uuid4

import replicate
import requests
from dotenv import load_dotenv

load_dotenv()

OUT_DIR = Path(os.getenv("OUTPUT_DIR", "outputs"))
OUT_DIR.mkdir(parents=True, exist_ok=True)

client = replicate.Client(api_token=os.environ["REPLICATE_API_TOKEN"])

FACE_ALIGN = os.environ["REPLICATE_FACE_ALIGN_SLUG"]
TALKING_HEAD = os.environ["REPLICATE_TALKING_HEAD_SLUG"]
INTERPOLATE = os.environ["REPLICATE_INTERPOLATION_SLUG"]

DEFAULT_FPS = int(os.getenv("DEFAULT_FPS", "30"))
DEFAULT_RES = int(os.getenv("DEFAULT_RESOLUTION", "768"))

def _save_output(output, suffix) -> Path:
    """
    Replicate hoje pode retornar:
      - URL (str)
      - FileOutput (objeto com .read())
    Salvamos qualquer um em disco e retornamos o Path.
    """
    out_path = OUT_DIR / f"{uuid4().hex}{suffix}"

    try:
        # FileOutput tem .read()
        data = output.read()  # type: ignore[attr-defined]
        out_path.write_bytes(data)
        return out_path
    except AttributeError:
        # Assume string (URL)
        if not isinstance(output, str):
            raise TypeError(f"Tipo de saída inesperado: {type(output)}")
        resp = requests.get(output, timeout=60)
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
        return out_path

def align_face(image_path: str) -> Path:
    """Alinha/recorta a face para padronizar antes da animação."""
    with open(image_path, "rb") as f:
        output = client.run(FACE_ALIGN, input={"image": f})
    # face-align-cog retorna um único arquivo (imagem)
    return _save_output(output, suffix=".png")

def animate_memo(image_path: str, audio_path: str,
                 fps: int = DEFAULT_FPS, resolution: int = DEFAULT_RES) -> Path:
    """Gera o vídeo do personagem falando (MEMO)."""
    with open(image_path, "rb") as img, open(audio_path, "rb") as aud:
        output = client.run(
            TALKING_HEAD,
            input={
                "image": img,                 # png/jpg
                "audio": aud,                 # wav/mp3
                "fps": fps,                   # 1..60
                "resolution": resolution,     # 64..2048 (quadrado)
                # parâmetros úteis (use sob demanda):
                # "inference_steps": 20,
                # "cfg_scale": 3.5,
                # "max_audio_seconds": 60,
                # "seed": 0
            },
        )
    # MEMO retorna um único mp4
    return _save_output(output, suffix=".mp4")

def film_interpolate(video_path: str,
                     target_fps: int = DEFAULT_FPS,
                     steps: int = 1) -> Path:
    """
    Aumenta fluidez/FPS com FILM (versão vídeo).
    - num_interpolation_steps=1 => dobra o número de quadros (aprox.)
    - playback_frames_per_second ajusta o FPS final do arquivo
    """
    with open(video_path, "rb") as mp4:
        output = client.run(
            INTERPOLATE,
            input={
                "mp4": mp4,
                "playback_frames_per_second": target_fps,  # 1..60
                "num_interpolation_steps": steps,          # 1..50
            },
        )
    return _save_output(output, suffix=".mp4")

def run_pipeline(
    image_path: str,
    audio_path: str,
    fps_out: int = 30,
    use_align: bool = True,
    film_steps: int = 1,
):
    """
    1) (opcional) Alinha a face
    2) Anima com MEMO
    3) Interpola com FILM para suavizar/aumentar FPS
    """
    aligned = image_path
    if use_align:
        print(">> Alinhando rosto…")
        aligned = str(align_face(image_path))
        print("   alinhado:", aligned)

    print(">> Gerando talking head (MEMO)…")
    talking = str(animate_memo(aligned, audio_path, fps=fps_out, resolution=DEFAULT_RES))
    print("   vídeo base:", talking)

    print(">> Interpolando com FILM…")
    refined = str(film_interpolate(talking, target_fps=fps_out, steps=film_steps))
    print("   vídeo final:", refined)
    return refined

if __name__ == "__main__":
    # Exemplo rápido:
    # python replicate_pipeline.py
    # (ajuste caminhos conforme seu projeto)
    IMG = "assets/personagens/joao.png"
    AUD = "data/audio/fala_02.mp3"
    run_pipeline(IMG, AUD, fps_out=30, use_align=True, film_steps=1)
