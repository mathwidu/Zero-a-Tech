# Scripts do Módulo de Quiz

Visão detalhada de cada script, responsabilidades, entradas/saídas e pontos de extensão.

## Orquestração
### `modules/quiz/quiz_pipeline.py`
- Orquestra o fluxo completo: perguntas → comentários → manifest/roteiro → capa → (imagens) → TTS → render.
- Consome flags de tema/quantidade/dificuldade e variável de concorrência de imagens.
- Uso:
  - `python -m modules.quiz.quiz_pipeline --topic "programação" --count 5 --difficulty "média"`

## Geração de conteúdo
### `modules/quiz/quiz_questions_gen.py`
- Gera perguntas (OpenAI) com 5 alternativas e índice da correta.
- Salva em `output-quiz/questions.json` com metadados de tema e dificuldade.

### `modules/quiz/quiz_commentary_gen.py`
- Gera comentários curtos para a explicação pós‑resposta.
- Salva em `output-quiz/commentary.json` (chave `comments`).

### `modules/quiz/quiz_generate.py`
- Monta o `quiz_manifest.json` (sequência de segmentos) e o `quiz_script.txt` (roteiro TTS).
- Sem introdução (HOOK) por padrão; a pergunta é lida e o timer entra logo depois.
- Flags:
  - `--no-hook` (default ativo via `QUIZ_NO_HOOK=1`).

## Áudio
### `modules/quiz/tts_quiz.py`
- Lê o roteiro e sintetiza os `quiz_XX.mp3` com ElevenLabs; inclui fallback gTTS.
- Normaliza pontuação e números (ex.: “5 segundos” → “cinco segundos”).
- Corrigido para não inserir reticências após “?” e evitar leitura estranha.

### `modules/quiz/sfx.py`
- Catálogo e cache de SFX curtos (tick/ding/whoosh/etc.).
- Gera via ElevenLabs quando disponível ou sintetiza offline (fallback).
- Armazena em `output-quiz/sfx/*.wav`.

## Renderização de vídeo
### `modules/quiz/quiz_video.py`
- Compositor de vídeo (MoviePy):
  - Fundo 9:16 (crop/blur); header com animações; cartão da pergunta; timer (border/bar/ring/digits); opções; SFX; CTA.
  - Layout com margens globais configuráveis (`--content-margin-x/y-ratio`).
  - Header com animações (gif/webm) esquerda/direita e borda animada (modo `spin`).
  - Caixa da pergunta com lógica de quebra e shrink‐to‐fit para sempre caber.
- Flags principais:
  - Animações header: `--header-right-anim-path`, `--header-left-anim-dir`, `--header-anim-video-scale`, `--header-anim-chroma-thr`.
  - Borda header: `--header-border-mode spin|fill`, `--header-border-stroke`, `--header-border-speed`.
  - Margens globais: `--content-margin-x-ratio`, `--content-margin-y-ratio`.
  - Timer: `--timer-style`, `--timer-scale`, `--timer-dim`.
  - Performance: `--fps`, `--crf`, `--preset`.

## Ícones e Header
### `modules/quiz/header_assets.py`
- Resolve ícone do tema: tenta gerar via OpenAI (cache) e cai no fallback local (`topic_icons`).

### `modules/quiz/topic_icons.py`
- Geração local de ícones cartonizados por tema (PIL) e cache em `assets/icons/<slug>.png`.

## Capa e Imagens (opcional)
### `modules/quiz/quiz_intro_cover.py`
- Prepara capa com texto embutido (tema + dificuldade) e atualiza manifest.

### `modules/quiz/quiz_image_prompts.py`, `modules/quiz/quiz_images.py`
- Geração e uso de imagens por pergunta (OpenAI/Replicate ou fallback), opcional.

---

## Extensões sugeridas
- `animation_presets.py` (futuro): presets por categoria (header/transition/options/reveal/cta).
- Novas animações em `assets/animation/<categoria>/...` com WEBM (alpha) preferencial.

