FROM python:3.10-slim

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl ca-certificates git libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Diretórios esperados pelos pesos
RUN mkdir -p /app/checkpoints /app/face_detection/detection/sfd /app/output

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copia o código do serviço
COPY . /app

ENV PYTHONUNBUFFERED=1 \
    TORCH_HOME=/app/.torch \
    FORCE_CPU=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
