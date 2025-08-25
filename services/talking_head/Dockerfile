FROM python:3.10-slim

# + libsndfile (p/ ler áudio), além de ffmpeg e git
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg git libsndfile1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host=0.0.0.0", "--port=8000", "--workers=1"]
