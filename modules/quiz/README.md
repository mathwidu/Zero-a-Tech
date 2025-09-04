# Quiz Module

## Visão Geral
Módulo para gerar vídeos curtos de quiz (TikTok/Shorts), com:
- Perguntas + 5 alternativas, contagem regressiva (ring com beep e flash), resposta destacada.
- Narração ElevenLabs (com retry e fallback gTTS).
- Capa de introdução (tema + dificuldade) com texto integrado na imagem.
- Render rápido com filtros para iterar só 1 pergunta.

Saídas ficam em `output-quiz/`.

## Requisitos
- Python 3.10+, `pip install -r requirements.txt`
- `.env`: `OPENAI_API_KEY`, `ELEVEN_API_KEY` (opcional `REPLICATE_API_TOKEN`)
- Fundos em `assets/videos_fundo/*.mp4`
- Fonte: `assets/fonts/LuckiestGuy-Regular.ttf`

## Estrutura
- Perguntas: `modules/quiz/quiz_questions_gen.py`
- Comentários: `modules/quiz/quiz_commentary_gen.py`
- Manifest/roteiro: `modules/quiz/quiz_generate.py`
- Capa inicial: `modules/quiz/quiz_intro_cover.py`
- Imagens por pergunta (opcional): `modules/quiz/quiz_image_prompts.py`
- TTS: `modules/quiz/tts_quiz.py`
- Render: `modules/quiz/quiz_video.py`
- Pipeline: `modules/quiz/quiz_pipeline.py`

## Quickstart (pipeline)
- Interativa (tema/dificuldade), com capa, TTS e render:
  - `python -m modules/quiz/quiz_pipeline --count 5`
- Com beep e ring (via env):
  - `QUIZ_COUNTDOWN_BEEP=1 python -m modules/quiz/quiz_pipeline --count 5`
- Habilitar geração de imagens (opcional): `--images`

## Fluxo por etapas
1) Perguntas (ChatGPT)
- `python -m modules/quiz/quiz_questions_gen --topic "geografia" --count 5 --difficulty média`
2) Comentários
- `python -m modules/quiz/quiz_commentary_gen`
3) Manifest/roteiro
- `python -m modules/quiz/quiz_generate --category geral --count 5`
4) Capa (texto embutido)
- `python -m modules/quiz/quiz_intro_cover`
5) Imagens (opcional)
- `python -m modules/quiz/quiz_image_prompts --max-workers 2 --skip-existing`
6) TTS
- `python -m modules/quiz/tts_quiz`
7) Render
- `python -m modules/quiz/quiz_video`

## Render — flags
- Filtro para iterar rápido:
  - `--only-q N`: renderiza só a questão N.
  - `--limit-questions K`: primeiras K questões.
  - `--no-intro`, `--no-cta`.
- Timer:
  - `--timer-style ring|digits` (padrão: ring)
  - `--timer-scale 1.15` (tamanho do ring)
  - `--timer-dim 0.12` (escurecimento no COUNTDOWN)
  - `--timer-flash` (flash por segundo), `--timer-flash-ms 120`, `--timer-flash-alpha 0.28`
- Beep:
  - `--beep` (beep por segundo com pitch ascendente)
  - `--beep-freq 1000`, `--beep-sec 0.25`, `--beep-vol 0.32`
- Fundo/encode:
  - `--bg-mode crop|blur`, `--crf 18`, `--preset slow` ou `--bitrate 10M`, `--fps 30`

## Imagens (opcional)
- OpenAI (gpt-image-1): `1024x1024`, `1024x1536`, `1536x1024` ou `auto`.
  - Env: `QUIZ_IMG_PROVIDER=openai`, `QUIZ_IMG_SIZE=1024|auto`, `QUIZ_IMG_ORIENT=portrait|landscape|square`
- Replicate (barato): FLUX/SDXL (512/768).
  - Env: `QUIZ_IMG_PROVIDER=replicate`, `REPLICATE_API_TOKEN`, `QUIZ_IMG_REPLICATE_MODEL`
  - `QUIZ_IMG_STEPS`, `QUIZ_IMG_GUIDANCE`, `QUIZ_IMG_CONCURRENCY`
- Comando: `python -m modules/quiz/quiz_image_prompts --max-workers 2 --skip-existing`

## TTS
- ElevenLabs com retry/backoff + fallback gTTS.
- Env:
  - `QUIZ_TTS_VOICE`, `QUIZ_TTS_STABILITY`, `QUIZ_TTS_SIMILARITY`, `QUIZ_TTS_STYLE`, `QUIZ_TTS_SPEAKER_BOOST`
  - Retry: `QUIZ_TTS_MAX_RETRIES`, `QUIZ_TTS_RETRY_BASE`
 - Dica de idioma: use uma voz PT-BR (ex.: configure `QUIZ_TTS_VOICE` para uma voz brasileira na sua conta). As frases de timer agora usam números por extenso ("cinco segundos"), evitando leitura de números em inglês.

## Capa de introdução
- Gera uma por tema+dificuldade e salva em `assets/quiz_covers/<tema>/<dificuldade>.png`.
- Texto (tema + nível + CTA) embutido na imagem com ajuste dinâmico.
- `python -m modules/quiz/quiz_intro_cover`

## Saídas
- `output-quiz/`
  - `questions.json`, `commentary.json`, `quiz_manifest.json`, `quiz_script.txt`
  - `quiz_*.mp3`
  - `images/` (se geradas)
  - `quiz_final.mp4`

## Dicas
- Iteração rápida:
  - `python -m modules/quiz/quiz_video --only-q 1 --no-intro --no-cta --timer-style ring --beep`
- Fundo nítido sem zoom:
  - `python -m modules/quiz/quiz_video --bg-mode blur --crf 18 --preset slow`
- Timer mais impactante:
  - `python -m modules/quiz/quiz_video --timer-scale 1.25 --timer-flash --beep-vol 0.6`
