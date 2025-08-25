#!/usr/bin/env bash
set -euo pipefail
# para logar o comando real que vai rodar (útil p/ debug):
set -x

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$APP_DIR/third_party/Wav2Lip"

FACE="$1"
AUDIO="$2"
OUT="$3"

# escolhe checkpoint
if [ -f "$APP_DIR/models/wav2lip_gan.pth" ]; then
  CHK="$APP_DIR/models/wav2lip_gan.pth"
elif [ -f "$APP_DIR/models/wav2lip.pth" ]; then
  CHK="$APP_DIR/models/wav2lip.pth"
else
  echo "Nenhum checkpoint wav2lip encontrado em $APP_DIR/models"; exit 1
fi

S3FD="$APP_DIR/models/s3fd.pth"
[ -f "$S3FD" ] || { echo "Faltando $S3FD"; exit 1; }

cd "$REPO"

# Lê o help do inference.py para descobrir quais flags existem nesse fork
HELP=$(python inference.py -h 2>&1 || true)

# --static pode ser um flag simples ou exigir valor (STATIC)
if echo "$HELP" | grep -q -- "--static STATIC"; then
  STATIC_ARG=(--static True)
elif echo "$HELP" | grep -q -- "--static"; then
  STATIC_ARG=(--static)
else
  STATIC_ARG=()
fi

# Alguns forks possuem --face_detector, outros não
if echo "$HELP" | grep -q -- "--face_detector"; then
  FACEDET_ARG=(--face_detector s3fd)
else
  FACEDET_ARG=()
fi

python inference.py \
  --checkpoint_path "$CHK" \
  --face "$FACE" \
  --audio "$AUDIO" \
  --outfile "$OUT" \
  --pads 0 10 0 0 \
  --resize_factor 1 \
  --nosmooth \
  "${FACEDET_ARG[@]}" \
  "${STATIC_ARG[@]}"
