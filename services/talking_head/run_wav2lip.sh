#!/usr/bin/env bash
set -euo pipefail

# Uso:
#   ./run_wav2lip.sh <face_image> <audio_file> [outfile]
#
# Config por env (opcional):
#   CKPT_PATH=/app/checkpoints/wav2lip_gan.pth (ou wav2lip.pth)
#   PADS="0 15 0 0"
#   NOSMOOTH=1
#   RESIZE_FACTOR=1
#   STATIC_IMAGE=1
#   FPS=25

FACE_IN="${1:?informe a imagem de rosto}"
AUDIO_IN="${2:?informe o áudio}"
OUTFILE="${3:-/tmp/wav2lip_out.mp4}"

CKPT="${CKPT_PATH:-/app/checkpoints/wav2lip_gan.pth}"
PADS="${PADS:-0 15 0 0}"
NOSMOOTH="${NOSMOOTH:-1}"
RESIZE="${RESIZE_FACTOR:-1}"
STATIC="${STATIC_IMAGE:-1}"
FPS="${FPS:-25}"

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

# 1) Áudio → WAV 16k mono
ffmpeg -hide_banner -loglevel error -y -i "$AUDIO_IN" -ar 16000 -ac 1 "$TMPDIR/audio.wav"

# 2) PNG com alpha → RGB (fundo cinza claro)
FACE_RGB="$TMPDIR/face_rgb.png"
python - <<PY
from PIL import Image
im = Image.open("$FACE_IN").convert("RGBA")
bg = Image.new("RGB", im.size, (240,240,240))
bg.paste(im, mask=im.split()[-1])
bg.save("$FACE_RGB")
PY

# 3) Monta args e roda inference
ARGS=(--checkpoint_path "$CKPT" --face "$FACE_RGB" --audio "$TMPDIR/audio.wav" --outfile "$OUTFILE" --fps "$FPS")
if [ "$STATIC" = "1" ]; then ARGS+=(--static); fi
if [ "$NOSMOOTH" = "1" ]; then ARGS+=(--nosmooth); fi
if [ -n "$RESIZE" ]; then ARGS+=(--resize_factor "$RESIZE"); fi

read -r P0 P1 P2 P3 <<< "$PADS"
ARGS+=(--pads "$P0" "$P1" "$P2" "$P3")

python -u /app/inference.py "${ARGS[@]}"

echo "$OUTFILE"
