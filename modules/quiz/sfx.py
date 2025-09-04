#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SFX utilitário: gera efeitos sonoros curtos via ElevenLabs (HTTP) com cache local.
Fallback offline (sintético) caso API indisponível.

CLI:
  - Listar:   python -m modules.quiz.sfx --list
  - Gerar um: python -m modules.quiz.sfx --name tick
  - Gerar todos: python -m modules.quiz.sfx --generate-all
"""

from __future__ import annotations
import os, json, base64, wave, struct
from pathlib import Path
from typing import Dict

import numpy as np


def get_cache_dir() -> Path:
    d = Path(os.getenv("QUIZ_SFX_CACHE_DIR", "output-quiz/sfx"))
    d.mkdir(parents=True, exist_ok=True)
    return d


# Catálogo simples de SFX: nome -> (prompt, duração segundos)
SFX_SPECS: Dict[str, dict] = {
    "tick":    {"prompt": "short retro game tick, dry",           "dur": 0.12},
    "ding":    {"prompt": "bright glass bell ding, clean",        "dur": 0.48},
    "whoosh":  {"prompt": "short airy whoosh up",                 "dur": 0.25},
    "stinger": {"prompt": "short cinematic impact stinger",       "dur": 0.90},
    "chime":   {"prompt": "soft bell chime, brief, clean, 500ms", "dur": 0.50},
    # notificação tipo mensageiro (inspirado em toques de mensagem, sem cópia literal)
    "message": {"prompt": "two-tone smartphone notification ping, bright, short decay, clean", "dur": 0.55},
    "melody_intro": {"prompt": "three-note smartphone notification melody, plucky marimba + synth, uplifting, 1.6 seconds", "dur": 1.60},
    "melody_outro": {"prompt": "three-note smartphone notification melody (reply motif), plucky marimba + synth, resolving cadence, 1.6 seconds", "dur": 1.60},
    # chegada de UI sólida (para entrada de alternativas)
    "solid_in": {"prompt": "short solid percussive thump / snap for UI element arrival, low-mid, 180 ms", "dur": 0.18},
}


def _save_wav(path: Path, data: np.ndarray, samplerate: int = 44100):
    """Salva audio mono ou estéreo float32 [-1,1] como WAV PCM16."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # garante 2D: (n, channels)
    if data.ndim == 1:
        data = np.stack([data, data], axis=1)
    # clamp e converte p/ int16
    x = np.clip(data, -1.0, 1.0)
    x = (x * 32767.0).astype(np.int16)
    with wave.open(str(path), 'wb') as wf:
        wf.setnchannels(x.shape[1])
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(x.tobytes())


def _synth_fallback(name: str, dur: float, sr: int = 44100) -> np.ndarray:
    """Gera um efeito sintético básico p/ fallback: tick/ding/whoosh/stinger/chime."""
    n = max(1, int(sr * dur))
    t = np.arange(n, dtype=np.float32) / float(sr)
    env = np.ones(n, dtype=np.float32)
    # ataque/decay
    a = max(1, int(0.01 * sr))
    r = max(1, int(0.08 * sr))
    env[:a] = np.linspace(0, 1, a, dtype=np.float32)
    env[-r:] = np.linspace(1, 0, r, dtype=np.float32)

    if name == "tick":
        f = 1400.0
        sig = np.sin(2 * np.pi * f * t)
        sig *= env * 0.6
        return np.stack([sig, sig], axis=1)
    if name == "ding":
        f1, f2 = 1200.0, 2000.0
        sig = 0.6*np.sin(2*np.pi*f1*t) + 0.4*np.sin(2*np.pi*f2*t)
        sig *= env * 0.6
        return np.stack([sig, sig], axis=1)
    if name == "whoosh":
        noise = np.random.randn(n).astype(np.float32)
        noise = noise / (np.max(np.abs(noise)) + 1e-6)
        tilt = np.linspace(0.2, 1.0, n).astype(np.float32)
        sig = noise * env * tilt * 0.4
        return np.stack([sig, sig], axis=1)
    if name == "stinger":
        f = 180.0
        sig = np.sin(2 * np.pi * f * t)
        sig *= env * 0.8
        return np.stack([sig, sig], axis=1)
    if name == "chime":
        f1, f2 = 880.0, 1320.0
        sig = 0.7*np.sin(2*np.pi*f1*t) + 0.5*np.sin(2*np.pi*f2*t)
        sig *= env * 0.55
        return np.stack([sig, sig], axis=1)
    if name == "melody_intro":
        # Pequena melodia de notificação (3 notas sobrepostas, leve eco, paneamento L->R)
        yL = np.zeros(n, dtype=np.float32)
        yR = np.zeros(n, dtype=np.float32)
        events = [
            (0.00, 987.77, 0.35),   # B5
            (0.25, 1318.51, 0.35),  # E6
            (0.50, 1760.00, 0.40),  # A6
        ]
        for idx, (t0, f, dlen) in enumerate(events):
            i0 = int(t0 * sr)
            i1 = min(n, i0 + int(dlen * sr))
            if i0 >= n:
                continue
            tt = np.arange(0, i1 - i0, dtype=np.float32) / float(sr)
            # timbre: seno + harmônica leve e leve vibrato
            vibr = 0.003 * np.sin(2*np.pi*6.0*tt)
            base = 2*np.pi*(f+f*vibr)*tt
            tone = 0.72*np.sin(base) + 0.28*np.sin(2*base)
            # envelope ASR curto
            a = max(1, int(0.02 * sr))
            r = max(1, int(0.10 * sr))
            envn = np.ones_like(tt)
            envn[:a] = np.linspace(0, 1, a, dtype=np.float32)
            if len(tt) > r:
                envn[-r:] = np.linspace(1, 0, r, dtype=np.float32)
            tone = (tone * envn * 0.6).astype(np.float32)
            # paneamento progressivo (L->R)
            pan = idx / max(1, len(events)-1)
            yL[i0:i1] += tone * (1.0 - 0.4*pan)
            yR[i0:i1] += tone * (0.6 + 0.4*pan)
        # eco curto
        delay = int(0.09 * sr)
        gain = 0.35
        if delay < n:
            yL[delay:] += yL[:-delay] * gain
            yR[delay:] += yR[:-delay] * gain
        # normaliza suave
        m = max(1e-6, float(max(np.max(np.abs(yL)), np.max(np.abs(yR)))))
        yL *= 0.95 / m
        yR *= 0.95 / m
        return np.stack([yL, yR], axis=1)
    if name == "melody_outro":
        # Motivo de fechamento: notas descendentes, resolvendo (R->L)
        yL = np.zeros(n, dtype=np.float32)
        yR = np.zeros(n, dtype=np.float32)
        events = [
            (0.00, 1760.00, 0.35),  # A6
            (0.25, 1318.51, 0.35),  # E6
            (0.50, 987.77, 0.40),   # B5
        ]
        for idx, (t0, f, dlen) in enumerate(events):
            i0 = int(t0 * sr)
            i1 = min(n, i0 + int(dlen * sr))
            if i0 >= n:
                continue
            tt = np.arange(0, i1 - i0, dtype=np.float32) / float(sr)
            vibr = 0.003 * np.sin(2*np.pi*6.0*tt)
            base = 2*np.pi*(f+f*vibr)*tt
            tone = 0.72*np.sin(base) + 0.28*np.sin(2*base)
            a = max(1, int(0.02 * sr))
            r = max(1, int(0.10 * sr))
            envn = np.ones_like(tt)
            envn[:a] = np.linspace(0, 1, a, dtype=np.float32)
            if len(tt) > r:
                envn[-r:] = np.linspace(1, 0, r, dtype=np.float32)
            tone = (tone * envn * 0.6).astype(np.float32)
            # paneamento progressivo (R->L)
            pan = idx / max(1, len(events)-1)
            yL[i0:i1] += tone * (0.6 + 0.4*pan)
            yR[i0:i1] += tone * (1.0 - 0.4*pan)
        delay = int(0.09 * sr)
        gain = 0.35
        if delay < n:
            yL[delay:] += yL[:-delay] * gain
            yR[delay:] += yR[:-delay] * gain
        m = max(1e-6, float(max(np.max(np.abs(yL)), np.max(np.abs(yR)))))
        yL *= 0.95 / m
        yR *= 0.95 / m
        return np.stack([yL, yR], axis=1)
    if name == "solid_in":
        # Thump/Snap curto: seno grave + transiente de ruído e click
        f = 240.0
        sig = np.sin(2*np.pi*f*t).astype(np.float32)
        # transiente (primeiros 8ms)
        k = max(1, int(0.008 * sr))
        sig[:k] += 0.6 * (np.random.randn(k).astype(np.float32) / 3.0)
        # envelope rápido
        a = max(1, int(0.005 * sr))
        r = max(1, int(0.09 * sr))
        envn = np.ones_like(sig)
        envn[:a] = np.linspace(0, 1, a, dtype=np.float32)
        envn[-r:] = np.linspace(1, 0, r, dtype=np.float32)
        sig = sig * envn * 0.8
        return np.stack([sig, sig], axis=1)
    # default beep
    sig = np.sin(2 * np.pi * 1000.0 * t) * env * 0.4
    return np.stack([sig, sig], axis=1)


def _try_generate_eleven(name: str, prompt: str, dur: float, fmt: str = "wav") -> bytes | None:
    """Tenta gerar SFX via ElevenLabs HTTP. Retorna bytes do arquivo ou None."""
    import requests
    api_key = os.getenv("ELEVEN_API_KEY")
    if not api_key:
        return None
    url = os.getenv("ELEVEN_SFX_ENDPOINT", "https://api.elevenlabs.io/v1/sound-generation/generate")
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    body = {
        "text": f"{prompt}",
        "duration_seconds": float(dur),
        "format": fmt,
    }
    try:
        r = requests.post(url, headers=headers, data=json.dumps(body), timeout=30)
        r.raise_for_status()
        return r.content
    except Exception:
        return None


def get_sfx_path(name: str) -> Path:
    """Garante um SFX em cache e retorna o Path."""
    name = name.lower().strip()
    spec = SFX_SPECS.get(name)
    if not spec:
        raise ValueError(f"SFX desconhecido: {name}")
    cache = get_cache_dir() / f"{name}.wav"
    if cache.exists() and cache.stat().st_size > 128:
        return cache

    # tenta gerar via ElevenLabs
    raw = _try_generate_eleven(name, spec["prompt"], spec["dur"], fmt="wav")
    if raw:
        cache.write_bytes(raw)
        return cache

    # fallback sintético
    data = _synth_fallback(name, spec["dur"])
    _save_wav(cache, data)
    return cache


def main():
    import argparse
    ap = argparse.ArgumentParser(description="SFX util — gera e lista efeitos com cache")
    ap.add_argument("--list", action="store_true", help="Lista SFX disponíveis")
    ap.add_argument("--name", type=str, default=None, help="Gera um SFX pelo nome")
    ap.add_argument("--generate-all", action="store_true")
    args = ap.parse_args()

    if args.list:
        print("SFX disponíveis:")
        for k, v in SFX_SPECS.items():
            print(f"- {k}: {v['prompt']} (~{v['dur']*1000:.0f} ms)")
        return

    if args.generate_all:
        for k in SFX_SPECS.keys():
            p = get_sfx_path(k)
            print(f"✅ {k}: {p}")
        return

    if args.name:
        p = get_sfx_path(args.name)
        print(f"✅ Gerado: {p}")
        return

    print("Nada a fazer. Use --list, --name tick ou --generate-all.")


if __name__ == "__main__":
    main()
