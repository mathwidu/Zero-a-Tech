# Quiz Module — Onboarding

Este guia te leva do zero ao vídeo final do quiz em Linux, macOS e Windows.

## Requisitos
- Python 3.10+
- ffmpeg instalado no sistema
  - macOS: `brew install ffmpeg`
  - Debian/Ubuntu: `sudo apt-get update && sudo apt-get install -y ffmpeg`
  - Windows (PowerShell Admin): `choco install ffmpeg` (ou baixe binários e adicione ao PATH)
- Chaves de API (coloque no `.env` na raiz):
  - `OPENAI_API_KEY` (geração de perguntas/comentários/opcional imagens)
  - `ELEVEN_API_KEY` (TTS ElevenLabs)
  - `REPLICATE_API_TOKEN` (opcional para imagens)

## Ambiente
```
python3 -m venv .venv
source .venv/bin/activate         # macOS/Linux
# Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

## Onde começar
- Leia o snapshot do projeto: `docs/PROJECT_STATE.md` (estado atual, flags‑chave, decisões)
- Consulte os scripts: `docs/SCRIPTS.md` (o que cada arquivo faz e como estender)

## Pastas importantes
- `assets/videos_fundo/*.mp4` — fundos verticais (1080x1920 recomendado)
- `assets/animation/` — GIF/WEBM de animações do header (direita padrão `lampada.gif`; esquerda por tema: `assets/animation/<slug>/`)
- `assets/fonts/LuckiestGuy-Regular.ttf` — fonte principal
- `output-quiz/` — saídas (áudio, manifest, vídeo final)

## Execução rápida (pipeline completa)
```
python -m modules.quiz.quiz_pipeline --topic "programação" --count 5 --difficulty "difícil"
```

## Execução por etapas
1) Gerar perguntas/comentários/manifest
```
python -m modules.quiz.quiz_questions_gen --topic "programação" --count 5 --difficulty "difícil"
python -m modules.quiz.quiz_commentary_gen
python -m modules.quiz.quiz_generate --category geral --count 5
```
2) TTS
```
python -m modules.quiz.tts_quiz
```
3) Render
```
python -m modules.quiz.quiz_video
```

## Flags úteis (layout/estética)
- Margens globais de conteúdo: `--content-margin-x-ratio 0.10 --content-margin-y-ratio 0.10`
- Header: `--header-ratio 0.115 --header-inset-x-ratio 0.04 --header-inset-y-ratio 0.12`
- Borda do header: `--header-border-mode spin --header-border-stroke 6 --header-border-speed 0.08`
- Animações header: `--header-right-anim-path assets/animation/lampada.gif` (direita); esquerda por tema em `assets/animation/<slug>/`.

## Sem introdução de vídeo e sem anúncio de timer
- Manifesto sem HOOK por padrão (`QUIZ_NO_HOOK=1`) — começa direto na pergunta.
- TTS não anuncia mais o cronômetro; o COUNTDOWN entra logo após a pergunta.

## Dicas e troubleshooting
- “Too many open files”: já mitigado (cache de SFX em memória). Se necessário, feche apps ou aumente `ulimit -n` (macOS/Linux).
- GIFs com alpha: prefira WEBM com alpha quando possível; caso GIF, exporte com transparência real ou fundo verde para chroma.
- Render lento durante testes: use `--fps 24 --crf 23 --preset veryfast`.

## Windows — observações
- Use `py -m venv .venv` para criar o ambiente.
- Ative com `.venv\Scripts\activate`.
- Instale ffmpeg via Chocolatey ou adicionando binários no PATH.
