#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import io
import os
import re
import shlex
import subprocess
import tempfile
from typing import Optional, Tuple

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image

app = FastAPI(title="Talking Head (Wav2Lip)")

CKPT_DEFAULT = os.environ.get("CKPT_PATH", "/app/checkpoints/wav2lip_gan.pth")
S3FD_PATH    = "/app/face_detection/detection/sfd/s3fd.pth"

def _have_weights() -> Tuple[bool, list]:
    missing = []
    if not os.path.isfile(CKPT_DEFAULT):
        missing.append(CKPT_DEFAULT)
    if not os.path.isfile(S3FD_PATH):
        missing.append(S3FD_PATH)
    return (len(missing) == 0, missing)

def _parse_box(box_str: str, w: int, h: int) -> Tuple[int,int,int,int]:
    """
    Aceita "x1 y1 x2 y2" ou "x y w h". Clampa nos limites.
    """
    nums = [int(float(x)) for x in re.split(r"[,\s]+", box_str.strip()) if x]
    if len(nums) != 4:
        raise ValueError("box deve ter 4 números")
    x1, y1, x2, y2 = nums
    # detecta se é w,h
    if x2 <= 0 or y2 <= 0 or (x2 < x1) or (y2 < y1):
        # assume x,y,w,h
        x2 = x1 + nums[2]
        y2 = y1 + nums[3]
    # clampa
    x1 = max(0, min(x1, w-1)); y1 = max(0, min(y1, h-1))
    x2 = max(1, min(x2, w));   y2 = max(1, min(y2, h))
    if x2 - x1 < 8 or y2 - y1 < 8:
        raise ValueError("box muito pequeno")
    return x1, y1, x2, y2

def _crop_with_box(img_path: str, box: str) -> str:
    im = Image.open(img_path).convert("RGBA")
    w, h = im.size
    x1, y1, x2, y2 = _parse_box(box, w, h)
    # pequena margem extra
    dx = int(0.06 * (x2 - x1))
    dy = int(0.08 * (y2 - y1))
    x1 = max(0, x1 - dx); y1 = max(0, y1 - dy)
    x2 = min(w, x2 + dx); y2 = min(h, y2 + dy)
    im = im.crop((x1, y1, x2, y2))
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    # mantém alpha aqui; o script flattena depois
    im.save(tmp.name)
    return tmp.name

@app.get("/health")
def health():
    ok, missing = _have_weights()
    return {"status": "ok" if ok else "missing-weights", "missing": missing}

@app.post("/talking-head")
async def talking_head(
    image: UploadFile = File(..., description="PNG/JPG do personagem (busto)"),
    audio: UploadFile = File(..., description="Áudio de voz"),
    box: Optional[str] = Form(None, description="x1 y1 x2 y2 OU x y w h"),
    pads: Optional[str] = Form("0 15 0 0"),
    nosmooth: Optional[int] = Form(1),
    resize_factor: Optional[int] = Form(1),
    fps: Optional[int] = Form(25),
    use_gan: Optional[int] = Form(1),
):
    ok, missing = _have_weights()
    if not ok:
        return JSONResponse(
            status_code=500,
            content={"detail": "Pesos ausentes", "missing": missing}
        )

    try:
        img_bytes = await image.read()
        aud_bytes = await audio.read()
    except Exception as e:
        raise HTTPException(400, f"Falha ao ler arquivos: {e}")

    with tempfile.TemporaryDirectory() as td:
        face_path = os.path.join(td, "face.png")
        audio_path = os.path.join(td, f"audio_{os.path.splitext(audio.filename or 'a')[0]}")
        with open(face_path, "wb") as f:
            f.write(img_bytes)
        with open(audio_path, "wb") as f:
            f.write(aud_bytes)

        # recorte manual (opcional)
        if box:
            try:
                face_path = _crop_with_box(face_path, box)
            except Exception as e:
                raise HTTPException(400, f"BOX inválido: {e}")

        # escolhe checkpoint
        ckpt = CKPT_DEFAULT if use_gan else "/app/checkpoints/wav2lip.pth"
        if not os.path.isfile(ckpt):
            raise HTTPException(500, f"Checkpoint não encontrado: {ckpt}")

        outfile = os.path.join(td, "out.mp4")

        env = os.environ.copy()
        env["CKPT_PATH"] = ckpt
        env["PADS"] = pads or "0 15 0 0"
        env["NOSMOOTH"] = str(int(bool(nosmooth)))
        env["RESIZE_FACTOR"] = str(int(resize_factor) if resize_factor else 1)
        env["STATIC_IMAGE"] = "1"
        env["FPS"] = str(int(fps) if fps else 25)

        cmd = f"/app/run_wav2lip.sh {shlex.quote(face_path)} {shlex.quote(audio_path)} {shlex.quote(outfile)}"
        try:
            subprocess.run(
                cmd, shell=True, check=True, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        except subprocess.CalledProcessError as e:
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Wav2Lip falhou",
                    "cmd": cmd,
                    "stdout": e.stdout.decode(errors="ignore"),
                    "stderr": e.stderr.decode(errors="ignore")
                }
            )

        if not os.path.isfile(outfile) or os.path.getsize(outfile) < 1024:
            return JSONResponse(
                status_code=500,
                content={"detail": "Saída inválida (arquivo muito pequeno ou ausente)."}
            )

        return FileResponse(
            outfile,
            media_type="video/mp4",
            filename="talking_head.mp4"
        )
