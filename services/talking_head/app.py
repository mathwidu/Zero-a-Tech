#!/usr/bin/env python3
import tempfile, shutil, subprocess, uuid
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from PIL import Image

APP_DIR = Path(__file__).parent.resolve()
RUN_SH = APP_DIR / "run_wav2lip.sh"
MODELS = APP_DIR / "models"
W2L = APP_DIR / "third_party" / "Wav2Lip"

app = FastAPI(title="TalkingHead Service (Wav2Lip)")

def ensure_ready() -> None:
    if not RUN_SH.exists():
        raise RuntimeError("run_wav2lip.sh não encontrado.")
    if not (W2L / "inference.py").exists():
        raise RuntimeError("Submódulo Wav2Lip ausente em third_party/Wav2Lip.")
    if not (MODELS / "s3fd.pth").exists():
        raise RuntimeError("Checkpoint s3fd.pth ausente em models/.")
    # Aceita GAN ou NOGAN
    has_gan = (MODELS / "wav2lip_gan.pth").exists()
    has_nogan = (MODELS / "wav2lip.pth").exists()
    if not (has_gan or has_nogan):
        raise RuntimeError("Coloque wav2lip_gan.pth ou wav2lip.pth em models/.")
    # ffmpeg é necessário para conversões
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg não encontrado no PATH dentro do container.")

ensure_ready()

@app.post("/talking-head")
def talking_head(
    image: UploadFile = File(...),
    audio: UploadFile = File(...),
    model: str = Form("wav2lip"),
    box: Optional[str] = Form(None),
):
    if model != "wav2lip":
        raise HTTPException(400, "Model não suportado neste serviço.")

    tmpdir = Path(tempfile.mkdtemp(prefix="w2l_"))
    try:
        # salva arquivos recebidos
        img_ext = Path(image.filename or "").suffix or ".png"
        aud_ext = Path(audio.filename or "").suffix or ""  # pode ser .mp3, .wav, etc.

        face_path = tmpdir / f"face{img_ext}"
        audio_path = tmpdir / (f"audio{aud_ext}" if aud_ext else "audio")

        with open(face_path, "wb") as f:
            shutil.copyfileobj(image.file, f)
        with open(audio_path, "wb") as f:
            shutil.copyfileobj(audio.file, f)

        if box:
            try:
                x1, y1, x2, y2 = map(int, box.split())
            except ValueError:
                raise HTTPException(400, "Formato de box inválido. Use 'x1 y1 x2 y2'.")
            with Image.open(face_path) as img:
                w, h = img.size
                if not (0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h):
                    raise HTTPException(400, "Coordenadas de box fora dos limites da imagem.")
                img.crop((x1, y1, x2, y2)).save(face_path)

        # Se não for WAV, converte para WAV 16 kHz mono (aceita mp3, m4a, ogg, etc.)
        if audio_path.suffix.lower() != ".wav":
            wav_path = tmpdir / "audio.wav"
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(audio_path), "-ar", "16000", "-ac", "1", str(wav_path)],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            except subprocess.CalledProcessError as e:
                msg = (e.stderr or b"").decode(errors="ignore")
                raise HTTPException(400, f"Falha ao converter áudio para WAV via ffmpeg: {msg[:500]}")
            audio_path = wav_path  # passa a usar o WAV convertido

        # roda o pipeline
        out_path = tmpdir / f"out_{uuid.uuid4().hex}.mp4"
        cmd = [str(RUN_SH), str(face_path.resolve()), str(audio_path.resolve()), str(out_path.resolve())]
        try:
            subprocess.run(
                cmd,
                cwd=APP_DIR,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as e:
            msg = (e.stderr or b"").decode(errors="ignore")
            if "no face" in msg.lower():
                raise HTTPException(422, f"Nenhum rosto detectado: {msg[:200]}")
            raise HTTPException(500, f"Wav2Lip falhou: {msg[:500]}")

        if not out_path.exists() or out_path.stat().st_size == 0:
            raise HTTPException(500, "Saída não gerada.")

        return FileResponse(
            path=str(out_path),
            media_type="video/mp4",
            filename="talking_head.mp4",
            background=BackgroundTask(shutil.rmtree, tmpdir, ignore_errors=True),
        )
    except Exception:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise
