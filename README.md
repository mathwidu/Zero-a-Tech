# Zero à Tech: Geração Automática de Vídeos com Personagens e Gameplays

Este projeto tem como objetivo criar um sistema completamente automatizado de geração de vídeos curtos para plataformas como TikTok, com foco em conteúdo educativo e de entretenimento sobre tecnologia. A proposta é transformar notícias e ideias em diálogos animados entre personagens, com visual carismático, legendas sincronizadas e gameplays de fundo.

---

## 🔄 Pipeline do Projeto

1. **Busca de Notícias** (`news_fetcher.py`):

   * Utiliza RSS para coletar notícias atualizadas sobre tecnologia.

2. **Geração de Roteiro** (`script_generator.py`):

   * Transforma uma notícia em um diálogo descontraído entre dois personagens: João e Zé Bot.

3. **Geração de Áudio** (`tts.py`):

   * Usa a API da ElevenLabs para gerar arquivos de áudio `.mp3` com vozes realistas dos personagens.

4. **Timestamps Palavra a Palavra** (`generate_word_timestamps.py`):

   * Usa o modelo Whisper para obter os tempos reais de início e fim de cada palavra falada.

5. **Geração de Legendas com Efeito Karaokê** (`generate_subtitles.py`):

   * Utiliza os dados de tempo para criar arquivos `.srt` com as palavras coloridas que mudam no ritmo da fala.

6. **Renderização do Vídeo Final** (`video_maker.py`):

   * Junta o fundo em gameplay, os personagens com bocas animadas e as legendas sincronizadas.
   * Usa MoviePy + PIL para compor o vídeo.

---

## 🕸️ Animação dos Personagens

Cada personagem possui três imagens principais:

* Boca fechada
* Boca aberta
* Piscar

Durante a fala:

* A boca alterna entre aberta e fechada ritmicamente, simulando a articulação.
* Em momentos de pausa, a boca permanece fechada.
* O personagem pode piscar aleatoriamente para tornar a an- O personagem pode piscar aleatoriamente para tornar a an\u00imação mais natural.

---

## 📁 Estrutura de Pastas

```
assets/
  personagens/
    joao.png, joaoaberto.png, joaoaberto2.png
    zebot.png, zebot_aberto.png, zebot_piscar.png
  videos_fundo/
    videofundomine.mp4
output/
  fala_01.mp3, fala_01_words.json, fala_01_lips.json
  legendas.srt, video_final.mp4
scripts/
  news_fetcher.py
  script_generator.py
  tts.py
  generate_word_timestamps.py
  generate_subtitles.py
  video_maker.py
```

---

## 🚀 O que ainda podemos fazer?

* [ ] Automatizar todo o processo com um `pipeline.py`
* [ ] Adicionar reações faciais aos personagens
* [ ] Publicação automática no TikTok com API ou automação
* [ ] Melhorar expressividade com mais sprites (sorriso, dúvida, surpresa)
* [ ] Adicionar movimentação leve (tilt, bounce, idle)

---

## 🚀 Por que isso é importante?

Esse projeto mostra como é possível automatizar a criação de conteúdo audiovisual com qualidade e carisma usando ferramentas acessíveis como Python, MoviePy, Whisper e ElevenLabs. Ideal para pequenos criadores, projetos educacionais e experimentos em IA criativa.

---

> Criado com amor e criatividade para transformar texto em conteúdo animado e inteligente. Do Zero à Tech! ✨

---

## 🧩 Módulo de Quiz (TikTok)

Gera vídeos curtos de quiz com pergunta + 5 opções, tela de gabarito (certa em verde, erradas em vermelho), narração ElevenLabs e fundo vertical 1080x1920.

### Requisitos

- Python 3.10+ e dependências: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- Chaves no `.env`: `OPENAI_API_KEY` (ChatGPT), `ELEVEN_API_KEY` (TTS). Opcional para imagens: `REPLICATE_API_TOKEN`.
- Fundos em `assets/videos_fundo/*.mp4` (use `python scripts/video.py` para baixar exemplos).

### Quickstart (interativo)

- `python -m modules.quiz.quiz_pipeline --count 5`
  - Escolha o tema (ex.: conhecimentos gerais, matemática, geografia, arte, ciências, biologia, química, física, programação, filmes, séries, música) e a dificuldade (fácil, média, difícil).
  - Saída: `output-quiz/quiz_final.mp4`.

### Passo a passo (debug/controle)

1) Gerar perguntas (ChatGPT):
   - `python -m modules.quiz.quiz_questions_gen --topic "geografia" --count 5 --difficulty média`
   - Salva `output-quiz/questions.json` (visível no log `output-quiz/log_quiz.txt`).
2) Montar roteiro/manifest:
   - `python -m modules.quiz.quiz_generate --category geral --count 5`
3) Gerar imagens por pergunta:
   - `python -m modules.quiz.quiz_image_prompts --max-workers 2 --skip-existing`
   - OpenAI `gpt-image-1` aceita tamanhos: `1024x1024` (padrão), `1024x1536`, `1536x1024` ou `auto`.
   - Controle via env: `QUIZ_IMG_PROVIDER=openai`, `QUIZ_IMG_SIZE=1024` (ou `auto`), `QUIZ_IMG_ORIENT=portrait|landscape|square`.
   - Alternativa mais barata: Replicate (ex.: FLUX Schnell/SDXL): `QUIZ_IMG_PROVIDER=replicate` + `REPLICATE_API_TOKEN`.
4) Narrar (ElevenLabs):
   - `python -m modules.quiz.tts_quiz`
   - Ajustes via `.env`: `QUIZ_TTS_VOICE`, `QUIZ_TTS_STABILITY`, `QUIZ_TTS_SIMILARITY`, `QUIZ_TTS_STYLE`, `QUIZ_TTS_SPEAKER_BOOST`.
5) Renderizar vídeo:
   - `python -m modules.quiz.quiz_video` (opções: `--q-sec 10`, `--hook-sec 3`, etc.).

### Saídas e organização

- `output-quiz/`: `questions.json`, `quiz_manifest.json`, `quiz_script.txt`, `quiz_*.mp3`, `images/`, `quiz_final.mp4`.
- O texto (pergunta/CTA/opções) é sempre renderizado acima das imagens para garantir legibilidade.

### Dicas de custo/qualidade para imagens

- OpenAI `gpt-image-1`: use `QUIZ_IMG_SIZE=1024` (ou `auto`) e, se preferir vertical, `QUIZ_IMG_ORIENT=portrait`.
- Concorrência: `--max-workers 2` (evita fila/lentidão e erros 429/400).
- Mais barato: use provider Replicate (FLUX/SDXL) e `QUIZ_IMG_SIZE=512/768`, com `QUIZ_IMG_STEPS` baixos.

### Problemas comuns

- “Nenhum vídeo em assets/videos_fundo”: adicione MP4s ou rode `python scripts/video.py`.
- “Áudios ausentes”: rode `python -m modules.quiz.tts_quiz` após gerar o manifest.
- Demora em imagens: use `--max-workers 1-2`. Para reduzir custo, considere Replicate com `QUIZ_IMG_SIZE=512`.
