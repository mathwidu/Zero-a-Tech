# Projeto Quiz — Estado Atual (Snapshot)

Este documento é uma fotografia do estado atual do módulo de Quiz.
Use como referência rápida ao reabrir o projeto.

## Visão Geral
- Vídeo vertical 1080×1920 (9:16) gerado com MoviePy.
- Pipeline: perguntas → comentários → manifest/roteiro → capa → (imagens) → TTS → render final.
- Sem introdução (HOOK) por padrão; começa direto na pergunta.
- TTS não anuncia o cronômetro; COUNTDOWN entra logo após a pergunta.

## Estrutura de Pastas
- `modules/quiz/` — código do módulo (render, geração, TTS, SFX, etc.).
- `assets/videos_fundo/` — vídeos de fundo 9:16 (MP4).
- `assets/animation/` — animações do header (direita padrão `lampada.gif`; esquerda por tema em `<slug>/`).
- `assets/fonts/` — fontes (ex.: `LuckiestGuy-Regular.ttf`).
- `output-quiz/` — saídas (questions.json, commentary.json, quiz_manifest.json, quiz_*.mp3, quiz_final.mp4, métricas TTS).

## Render (modules/quiz/quiz_video.py)
- Layout com margens globais de conteúdo: `--content-margin-x-ratio` e `--content-margin-y-ratio` (0.04 default). Use 0.10 para “borda total” ~20%.
- Header:
  - Painel branco com contorno preto; título com shrink‑to‑fit (usa textbbox + padding) e em camada acima da borda.
  - Animações: esquerda (por tema) e direita (padrão `assets/animation/lampada.gif`).
  - Bordas verticais: faixa única de cor; horizontais multicolor girando (modo `spin`).
  - Flags: `--header-ratio`, `--header-inset-x/y-ratio`, `--header-border-mode`, `--header-border-stroke`, `--header-border-speed`, `--header-right-anim-path`.
- Pergunta (cartão):
  - shrink‑to‑fit robusto: base ~30% menor, padding vertical maior, até 5 linhas, último recurso sem elipse.
  - Sempre cabe no cartão dentro dos limites do layout.
- Timer:
  - “border” usa a largura interna; alternativos `bar/ring/digits` suportados.
  - `--timer-dim` opcional, `--timer-flash`/`--beep` controláveis.
- Opções:
  - Linhas alinhadas ao grid interno, animação slide-in alternada; badge “sticker” à esquerda.
- SFX:
  - Matching automático ao RMS da voz por segmento.
  - Controles: `--sfx-voice-ratio` (default 0.38) e `--sfx-gain` (default 0.45).

## TTS (modules/quiz/tts_quiz.py)
- ElevenLabs com retry/backoff; fallback para gTTS.
- Normalização: sem reticências após `?` e colapsa `??/?!/!!!` em `?`.
- Métricas: `output-quiz/tts_metrics.json` com `total_chars`, `items` e (quando possível) `subscription` da ElevenLabs.
- A pipeline apende uma linha em `output-quiz/log_quiz.txt` com `[TTS] total_chars=... | plan_usage=used/limit rem=...`.

## Perguntas (modules/quiz/quiz_questions_gen.py)
- Prompt especializado para programação:
  - Campo extra `level`: `estagiario` | `junior` | `pleno` | `senior`.
  - Progressão forte de dificuldade e variedade (conceitos, Big‑O, estruturas, depuração, saída de código curto, boas práticas, segurança).
  - Snippets curtos de código permitidos como strings.
- Oversample + filtro de novidade:
  - Gera `count*oversample` (default 2x) e filtra por similaridade (Jaccard) contra histórico (`output-quiz/questions_history.json`) e entre si.
  - Remove pegadinhas genéricas (“todas as alternativas/anteriores”).
  - Logs mostram removidos e distribuição por nível.

## Flags‑chave
- Margens: `--content-margin-x-ratio 0.10 --content-margin-y-ratio 0.10`
- Header: `--header-ratio 0.115 --header-inset-x-ratio 0.04 --header-inset-y-ratio 0.12 --header-border-mode spin --header-border-stroke 6 --header-border-speed 0.08 --header-right-anim-path assets/animation/lampada.gif`
- Timer: `--timer-style border|ring|digits|bar --timer-dim 0.12 --timer-scale 1.15`
- SFX: `--sfx-voice-ratio 0.38 --sfx-gain 0.45`
- Perguntas: `--oversample 2 --novelty-threshold 0.82 --temp 0.55`
- Iteração rápida: `--only-q 1 --no-intro --no-cta`

## Comandos Essenciais
- Pipeline completa:
```
python -m modules.quiz.quiz_pipeline --topic "programação" --count 5 --difficulty "difícil"
```
- Etapas:
```
python -m modules.quiz.quiz_questions_gen --topic "programação" --count 5 --difficulty "média"
python -m modules.quiz.quiz_commentary_gen
python -m modules.quiz.quiz_generate --category geral --count 5
python -m modules.quiz.tts_quiz
python -m modules.quiz.quiz_video
```

## Pendências / Ideias Futuras
- Exibir `level` (estagiario/junior/pleno/senior) visualmente no header/cartão.
- Commentary adaptado ao level (aprimorar retenção e didática).
- “Anim packs” (presets) para header/CTA/opções (futuramente `animation_presets.py`).
- Matching do beep do COUNTDOWN ao RMS da voz.
- Ajuste dinâmico de `q_max` (teto de altura da pergunta) para casos extremos.

