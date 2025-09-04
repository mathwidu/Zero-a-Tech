#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TTS simplificado para o módulo de quiz.
- Lê output-quiz/quiz_script.txt (linhas iniciando com "NARRADOR:")
- Gera arquivos output-quiz/quiz_XX.mp3 usando ElevenLabs.
"""

import os, time, random, re
from pathlib import Path
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from elevenlabs.core.api_error import ApiError
from gtts import gTTS

SCRIPT_TXT = Path("output-quiz/quiz_script.txt")
OUT_DIR = Path("output-quiz")

# Ajuste a voz padrão aqui (precisa existir na sua conta ElevenLabs)
VOZ_NARRADOR = os.environ.get("QUIZ_TTS_VOICE", "Charlie")
MODEL_ID = os.environ.get("QUIZ_TTS_MODEL", "eleven_multilingual_v2")
FORMAT = os.environ.get("QUIZ_TTS_FORMAT", "mp3_44100_128")


def ler_linhas():
    if not SCRIPT_TXT.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {SCRIPT_TXT}")
    linhas = [l.strip() for l in SCRIPT_TXT.read_text(encoding="utf-8").splitlines() if l.strip()]
    # mantém apenas o texto após "NARRADOR:"
    saidas = []
    for l in linhas:
        if ":" in l:
            saidas.append(l.split(":", 1)[1].strip())
        else:
            saidas.append(l)
    return saidas


def main():
    load_dotenv()
    api_key = os.getenv("ELEVEN_API_KEY")
    if not api_key:
        raise RuntimeError("Defina ELEVEN_API_KEY no .env")
    client = ElevenLabs(api_key=api_key)

    textos = ler_linhas()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # encontra voz por nome
    voice = next((v for v in client.voices.get_all().voices if v.name == VOZ_NARRADOR), None)
    if not voice:
        raise RuntimeError(f"Voz '{VOZ_NARRADOR}' não encontrada em sua conta ElevenLabs")

    def num_pt(n: int) -> str:
        unidades = {
            0: "zero", 1: "um", 2: "dois", 3: "três", 4: "quatro", 5: "cinco",
            6: "seis", 7: "sete", 8: "oito", 9: "nove", 10: "dez",
            11: "onze", 12: "doze", 13: "treze", 14: "quatorze", 15: "quinze",
            16: "dezesseis", 17: "dezessete", 18: "dezoito", 19: "dezenove",
            20: "vinte"
        }
        dezenas = {30: "trinta", 40: "quarenta", 50: "cinquenta", 60: "sessenta"}
        if n in unidades:
            return unidades[n]
        if n in dezenas:
            return dezenas[n]
        if 21 <= n <= 29:
            return "vinte e " + unidades[n - 20]
        if 31 <= n <= 39:
            return "trinta e " + unidades[n - 30]
        if 41 <= n <= 49:
            return "quarenta e " + unidades[n - 40]
        if 51 <= n <= 59:
            return "cinquenta e " + unidades[n - 50]
        return str(n)

    def humanize(t: str) -> str:
        # micro-ajustes de prosódia: pausas e ênfase
        t = t.replace(":", ": ")
        if t.lower().startswith("pergunta") and not t.endswith("!"):
            t = t + " Valendo!"
        t = t.replace("?", "? …")

        # Normaliza números para segundos: "5 segundos" -> "cinco segundos"
        def repl_seg(match: re.Match) -> str:
            num = int(match.group(1))
            plural = match.group(2)
            return f"{num_pt(num)} segundo{plural}"

        t = re.sub(r"\b(\d{1,2})\s+segundo(s)?\b", repl_seg, t, flags=re.IGNORECASE)

        # "Pergunta 1:" -> "Pergunta número um:"
        def repl_pergunta_colon(m: re.Match) -> str:
            word = m.group(1)
            num = int(m.group(2))
            return f"{word} número {num_pt(num)}:"
        t = re.sub(r"\b([Pp]ergunta)\s+(\d{1,2})\s*:", repl_pergunta_colon, t)

        def repl_pergunta(m: re.Match) -> str:
            word = m.group(1)
            num = int(m.group(2))
            return f"{word} número {num_pt(num)}"
        t = re.sub(r"\b([Pp]ergunta)\s+(\d{1,2})\b", repl_pergunta, t)

        # "parte 2" -> "parte dois" (CTA)
        def repl_parte(m: re.Match) -> str:
            word = m.group(1)
            num = int(m.group(2))
            punct = m.group(3) or ""
            return f"{word} {num_pt(num)}{punct}"
        t = re.sub(r"\b([Pp]arte)\s+(\d{1,2})([!?.])?\b", repl_parte, t)
        return t

    max_retries = int(os.getenv("QUIZ_TTS_MAX_RETRIES", "5"))
    base_sleep = float(os.getenv("QUIZ_TTS_RETRY_BASE", "2.0"))

    for i, texto in enumerate(textos, start=1):
        print(f"🎙️ Narrador: {texto}")
        payload = dict(
            text=humanize(texto),
            voice_id=voice.voice_id,
            model_id=MODEL_ID,
            output_format=FORMAT,
            voice_settings={
                "stability": float(os.getenv("QUIZ_TTS_STABILITY", 0.4)),
                "similarity_boost": float(os.getenv("QUIZ_TTS_SIMILARITY", 0.9)),
                # Alguns planos/vozes aceitam estes campos; ignorados se não suportados
                "style": float(os.getenv("QUIZ_TTS_STYLE", 0.35)),
                "use_speaker_boost": bool(int(os.getenv("QUIZ_TTS_SPEAKER_BOOST", "1"))),
            },
        )
        out_path = OUT_DIR / f"quiz_{i:02d}.mp3"

        success = False
        for attempt in range(1, max_retries + 1):
            try:
                audio_stream = client.text_to_speech.convert(**payload)
                with open(out_path, "wb") as f:
                    for chunk in audio_stream:
                        f.write(chunk)
                success = True
                print(f"✅ {out_path}")
                break
            except ApiError as e:
                if getattr(e, "status_code", None) == 429:
                    wait = base_sleep * (2 ** (attempt - 1)) + random.uniform(0, 0.8)
                    print(f"⏳ ElevenLabs ocupado (429). Tentativa {attempt}/{max_retries}. Aguardando {wait:.1f}s…")
                    time.sleep(wait)
                    continue
                else:
                    print(f"⚠️ Erro ElevenLabs (tentativa {attempt}): {e}")
                    time.sleep(1.0)
            except Exception as e:
                print(f"⚠️ Erro inesperado no TTS (tentativa {attempt}): {e}")
                time.sleep(1.0)

        if not success:
            # Fallback para gTTS (pt-br) para não travar pipeline
            try:
                print("🔁 Fallback gTTS (pt-BR)…")
                tts = gTTS(text=humanize(texto), lang="pt", tld="com.br")
                tts.save(str(out_path))
                print(f"✅ (fallback) {out_path}")
            except Exception as e:
                raise RuntimeError(f"Falha no TTS (ElevenLabs e fallback gTTS): {e}")


if __name__ == "__main__":
    main()
