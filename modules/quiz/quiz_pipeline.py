#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Pipeline simplificado para gerar um vídeo de quiz:
1) Gera roteiro e manifest (quiz_generate)
2) Gera TTS (tts_quiz)
3) Renderiza vídeo (quiz_video)

Uso:
  python -m modules.quiz.quiz_pipeline --category casais --count 3
"""

import argparse
import subprocess
import sys
import os

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
    run("python -m modules.quiz.quiz_video")


if __name__ == "__main__":
    main()
