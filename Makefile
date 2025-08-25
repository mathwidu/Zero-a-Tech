.PHONY: up down logs build test

up:
<TAB>docker compose up -d

down:
<TAB>docker compose down

logs:
<TAB>docker compose logs -f talking_head

build:
<TAB>docker compose build talking_head

test:
<TAB>curl -X POST http://localhost:8000/talking-head \
<TAB>  -F "image=@assets/ze_bot_frente.png" \
<TAB>  -F "audio=@output/fala_01.wav" \
<TAB>  -o output/clip_test.mp4
