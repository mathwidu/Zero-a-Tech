#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Pipeline simplificado para gerar um vídeo de quiz.

Etapas:
1) Gera perguntas+comentários+manifest/roteiro (quiz_generate)
2) Gera TTS (tts_quiz)
3) Renderiza vídeo (quiz_video)

Observações:
- Introdução (HOOK) habilitada por padrão no manifesto; use `--no-hook` no gerador para remover.
- As flags do render permitem ajustar margens do conteúdo, header e animações.

Uso rápido:
    python -m modules.quiz.quiz_pipeline --topic "programação" --count 5 --difficulty "média"
"""

import argparse
import subprocess
import sys
import os
import json
from pathlib import Path

def run(cmd: str):
    print(f"▶ {cmd}")
    ret = subprocess.run(cmd, shell=True)
    if ret.returncode != 0:
        sys.exit(ret.returncode)


def main():
    ap = argparse.ArgumentParser(description="Pipeline rápido de quiz")
    ap.add_argument("--topic", default=None)
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--difficulty", default=None)
    ap.add_argument("--img-workers", type=int, default=int(os.getenv("QUIZ_IMG_CONCURRENCY", "2")))
    ap.add_argument("--images", action="store_true", help="Gera imagens das perguntas (opcional)")
    args = ap.parse_args()

    topics = [
        "conhecimentos gerais","matematica","geografia","arte","ciencias","biologia","quimica","fisica","programação","filmes","series","musica"
    ]
    diffs = ["fácil","média","difícil"]

    topic = args.topic
    if not topic:
        print("\nEscolha um tema:")
        for i, t in enumerate(topics, start=1):
            print(f"  {i}. {t}")
        sel = input("Número do tema (1-12): ").strip()
        try:
            idx = max(1, min(12, int(sel)))
            topic = topics[idx-1]
        except Exception:
            topic = "conhecimentos gerais"

    difficulty = args.difficulty
    if not difficulty:
        print("\nEscolha a dificuldade:")
        for i, d in enumerate(diffs, start=1):
            print(f"  {i}. {d}")
        sel = input("Número da dificuldade (1-3): ").strip()
        try:
            idx = max(1, min(3, int(sel)))
            difficulty = diffs[idx-1]
        except Exception:
            difficulty = "média"

    run(f"python -m modules.quiz.quiz_questions_gen --topic '{topic}' --count {args.count} --difficulty {difficulty}")
    run("python -m modules.quiz.quiz_commentary_gen")
    run(f"python -m modules.quiz.quiz_generate --category geral --count {args.count}")
    run("python -m modules.quiz.quiz_intro_cover")
    if args.images:
        run(f"python -m modules.quiz.quiz_image_prompts --max-workers {args.img_workers} --skip-existing")
    else:
        print("ℹ️ Etapa de imagens das perguntas desativada (use --images para ativar).")
    run("python -m modules.quiz.tts_quiz")
    # Apêndice de métricas no log principal (se existir)
    try:
        metrics_path = Path("output-quiz/tts_metrics.json")
        log_path = Path("output-quiz/log_quiz.txt")
        if metrics_path.exists():
            m = json.loads(metrics_path.read_text(encoding="utf-8"))
            total_chars = m.get("total_chars")
            sub = m.get("subscription", {}) or {}
            line = f"[TTS] total_chars={total_chars}"
            if sub:
                cc = sub.get("character_count")
                cl = sub.get("character_limit")
                rem = None
                try:
                    rem = int(cl) - int(cc)
                except Exception:
                    rem = None
                line += f" | plan_usage={cc}/{cl} rem={rem}"
            print(line)
            if log_path.parent.exists():
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
    except Exception:
        pass
    run("python -m modules.quiz.quiz_video")


if __name__ == "__main__":
    main()
