#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import glob
import json
import argparse
from pathlib import Path

import whisper

def extract_word_timestamps(model, audio_path: str, output_path: str, language: str | None = None):
    """
    Extrai timestamps palavra a palavra com Whisper e salva em JSON (lista de {word,start,end}).
    """
    print(f"🎙️  Transcrevendo: {audio_path}")
    result = model.transcribe(
        audio_path,
        word_timestamps=True,
        verbose=False,
        language=language  # deixe None para detecção automática
    )

    palavras = []
    for segment in result.get("segments", []):
        for word in segment.get("words", []):
            w = word.get("word")
            if not w:
                continue
            try:
                start = float(word.get("start", 0.0))
                end   = float(word.get("end", start))
            except (TypeError, ValueError):
                continue
            palavras.append({
                "word": w.strip(),
                "start": start,
                "end": end
            })

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(palavras, f, ensure_ascii=False, indent=2)

    print(f"✅ Timestamps exportados ({len(palavras)} palavras): {output_path}")

def main():
    parser = argparse.ArgumentParser(
        description="Gera fala_XX_words.json para um ou mais áudios usando Whisper."
    )
    parser.add_argument("audios", nargs="*", help="Caminhos dos arquivos .mp3 (opcional).")
    parser.add_argument("--model", default=os.getenv("WHISPER_MODEL", "base"),
                        help="Modelo do Whisper (tiny/base/small/medium/large). Padrão: base")
    parser.add_argument("--language", default=None,
                        help="Forçar idioma (ex.: pt, en). Padrão: auto-detecção")
    parser.add_argument("--force", action="store_true",
                        help="Sobrescrever JSON existente.")
    args = parser.parse_args()

    # Se não passar áudio, processa todos os output/fala_*.mp3
    audio_list = args.audios
    if not audio_list:
        audio_list = sorted(glob.glob("output/fala_*.mp3"))
        if not audio_list:
            print("⚠️  Nenhum arquivo encontrado em output/fala_*.mp3.")
            print("    Uso: python3 scripts/generate_word_timestamps.py output/fala_01.mp3 [outros.mp3]")
            sys.exit(1)

    print(f"🧠 Carregando modelo Whisper: {args.model}")
    model = whisper.load_model(args.model)

    for audio_file in audio_list:
        if not os.path.exists(audio_file):
            print(f"❌ Arquivo não existe: {audio_file}")
            continue

        base = os.path.splitext(os.path.basename(audio_file))[0]  # ex.: fala_01
        output_file = os.path.join("output", f"{base}_words.json")

        if os.path.exists(output_file) and not args.force:
            print(f"⏭️  Pulando (já existe): {output_file} — use --force para sobrescrever.")
            continue

        try:
            extract_word_timestamps(model, audio_file, output_file, language=args.language)
        except Exception as e:
            print(f"❌ Erro ao processar {audio_file}: {e}")
            # Dica comum no macOS/Linux quando falta FFmpeg:
            if "ffmpeg" in str(e).lower():
                print("💡 Dica: instale o FFmpeg (macOS: brew install ffmpeg).")

    print("🏁 Fim do processamento.")

if __name__ == "__main__":
    main()
