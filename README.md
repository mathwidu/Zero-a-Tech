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
