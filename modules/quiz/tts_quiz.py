#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TTS simplificado para o módulo de quiz.
- Lê output-quiz/quiz_script.txt (linhas iniciando com "NARRADOR:")
- Gera arquivos output-quiz/quiz_XX.mp3 usando ElevenLabs.
"""

import os, time, random, re, subprocess, shutil
from pathlib import Path
from dotenv import load_dotenv
import json
import requests
from elevenlabs.client import ElevenLabs
from elevenlabs.core.api_error import ApiError
from gtts import gTTS

SCRIPT_TXT = Path("output-quiz/quiz_script.txt")
OUT_DIR = Path("output-quiz")
METRICS_JSON = OUT_DIR / "tts_metrics.json"

# Ajuste a voz padrão aqui (precisa existir na sua conta ElevenLabs)
VOZ_NARRADOR = os.environ.get("QUIZ_TTS_VOICE", "Charlie")
MODEL_ID = os.environ.get("QUIZ_TTS_MODEL", "eleven_multilingual_v2")
FORMAT = os.environ.get("QUIZ_TTS_FORMAT", "mp3_44100_128")

# Novo: controle de extroversão e velocidade
EXTROVERT = bool(int(os.environ.get("QUIZ_TTS_EXTROVERT", "1")))
# Velocidade padrão ajustada: ~20% mais rápido (em vez de 50%)
# Para ficar ~20% mais lento que o original, use 0.8
SPEEDUP = float(os.environ.get("QUIZ_TTS_SPEEDUP", "1.2"))


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

def _atempo_chain(rate: float) -> str:
    """Constrói cadeia de filtros atempo válida para o FFmpeg.
    Suporta valores fora de 0.5..2 encadeando múltiplos atempo.
    """
    rate = float(rate)
    if rate <= 0:
        return "atempo=1.0"
    parts = []
    r = rate
    # acima de 2.0: divide por 2 até cair no intervalo
    while r > 2.0:
        parts.append("atempo=2.0")
        r /= 2.0
    # abaixo de 0.5: multiplica por 2 (equivale a usar 0.5 várias vezes)
    while r < 0.5:
        parts.append("atempo=0.5")
        r /= 0.5
    parts.append(f"atempo={max(0.5, min(2.0, r)):.3f}")
    return ",".join(parts)

def _speedup_audio_file(path: Path, rate: float) -> bool:
    """Acelera o áudio via ffmpeg atempo, substituindo o arquivo no lugar.
    Retorna True se conseguiu aplicar ou se rate≈1; False se não conseguiu.
    """
    try:
        rate = float(rate)
    except Exception:
        rate = 1.0
    if rate <= 0 or abs(rate - 1.0) < 1e-3:
        return True
    if shutil.which("ffmpeg") is None:
        print("⚠️ FFmpeg não encontrado no PATH — mantendo velocidade original.")
        return False
    try:
        tmp = path.with_suffix(".tmp.mp3")
        flt = _atempo_chain(rate)
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(path),
            "-filter:a", flt,
            "-vn", str(tmp)
        ]
        subprocess.run(cmd, check=True)
        # troca atômica simples
        tmp.replace(path)
        print(f"🚀 Velocidade aplicada {rate:.2f}x -> {path.name}")
        return True
    except Exception as e:
        print(f"⚠️ Falha ao acelerar áudio ({rate}x) para {path}: {e}")
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return False


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
        # Pausas e pontuação: não inserir reticências após "?" (evita leitura estranha)
        # Normaliza espaços em torno de "?" e remove reticências
        t = t.replace("…", ", ")
        t = re.sub(r"\s*\?\s*", "?", t)
        # Colapsa pontuação repetida tipo "??" ou "!?" para uma interrogação
        t = t.replace("?!", "?")
        t = re.sub(r"[!?]{2,}", "?", t)

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

        if EXTROVERT:
            # Aumenta energia: mais ênfase e interjeições leves
            txt = t.strip()
            lower = txt.lower()
            # Perguntas
            if lower.startswith("pergunta número"):
                # substitui o primeiro ':' por '!'
                parts = list(txt)
                try:
                    i = txt.index(":")
                    parts[i] = "!"
                    txt = "".join(parts)
                except ValueError:
                    pass
                if not txt.endswith(("!", "?", ".")):
                    txt += "!"
                # adiciona um gatilho curto
                if not txt.endswith(" Valendo!"):
                    txt += " Valendo!"
            # Revelação da resposta
            elif lower.startswith("resposta correta"):
                if not txt.endswith(("!", "?", ".")):
                    txt += "!"
                if not any(w in lower for w in ["mandou bem", "boa", "acertou"]):
                    txt += " Mandou bem!"
            # CTA
            elif "comentários" in lower or "comentarios" in lower:
                if not txt.endswith(("!", "?", ".")):
                    txt += "!"
            return txt
        return t

    max_retries = int(os.getenv("QUIZ_TTS_MAX_RETRIES", "5"))
    base_sleep = float(os.getenv("QUIZ_TTS_RETRY_BASE", "2.0"))

    # Métricas agregadas desta execução
    metrics = {"provider": "elevenlabs", "total_chars": 0, "items": []}

    def human_text_and_chars(raw: str) -> tuple[str, int]:
        ht = humanize(raw)
        return ht, len(ht)

    for i, texto in enumerate(textos, start=1):
        print(f"🎙️ Narrador: {texto}")
        htext, n_chars = human_text_and_chars(texto)
        payload = dict(
            text=htext,
            voice_id=voice.voice_id,
            model_id=MODEL_ID,
            output_format=FORMAT,
            voice_settings={
                # Extroversão: menos estabilidade (mais variação) e style mais alto
                "stability": float(os.getenv("QUIZ_TTS_STABILITY", 0.30)),
                "similarity_boost": float(os.getenv("QUIZ_TTS_SIMILARITY", 0.9)),
                # Alguns planos/vozes aceitam estes campos; ignorados se não suportados
                "style": float(os.getenv("QUIZ_TTS_STYLE", 0.90)),
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
                # Aceleração de fala (pós-processamento)
                _speedup_audio_file(out_path, SPEEDUP)
                metrics["total_chars"] += n_chars
                metrics["items"].append({
                    "index": i,
                    "file": str(out_path),
                    "chars": n_chars,
                    "provider": "elevenlabs",
                })
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
                tts = gTTS(text=htext, lang="pt", tld="com.br")
                tts.save(str(out_path))
                print(f"✅ (fallback) {out_path}")
                _speedup_audio_file(out_path, SPEEDUP)
                metrics["total_chars"] += n_chars
                metrics["items"].append({
                    "index": i,
                    "file": str(out_path),
                    "chars": n_chars,
                    "provider": "gtts",
                })
            except Exception as e:
                raise RuntimeError(f"Falha no TTS (ElevenLabs e fallback gTTS): {e}")

    # Tenta obter uso de caracteres da assinatura ElevenLabs (se rede disponível)
    def try_fetch_subscription() -> dict:
        out = {}
        try:
            resp = requests.get(
                os.getenv("ELEVEN_USER_ENDPOINT", "https://api.elevenlabs.io/v1/user"),
                headers={"xi-api-key": os.getenv("ELEVEN_API_KEY", ""), "accept": "application/json"},
                timeout=10,
            )
            if resp.ok:
                data = resp.json()
                sub = data.get("subscription") or {}
                out = {
                    "character_count": sub.get("character_count"),
                    "character_limit": sub.get("character_limit"),
                    "can_extend_character_limit": sub.get("can_extend_character_limit"),
                }
        except Exception:
            pass
        return out

    sub = try_fetch_subscription()
    if sub:
        metrics["subscription"] = sub

    # Salva métricas em JSON
    try:
        METRICS_JSON.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"📊 TTS métricas salvas em {METRICS_JSON}: total_chars={metrics['total_chars']}")
        if sub:
            rem = None
            if sub.get("character_limit") is not None and sub.get("character_count") is not None:
                rem = int(sub["character_limit"]) - int(sub["character_count"])
            print(f"📈 ElevenLabs uso: {sub.get('character_count')}/{sub.get('character_limit')} (restante ~{rem})")
    except Exception:
        pass


if __name__ == "__main__":
    main()
