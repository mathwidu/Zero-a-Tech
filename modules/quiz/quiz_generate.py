#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, json, os, random
from pathlib import Path
from datetime import datetime, timezone

import json
from .questions_bank import sample_general_knowledge

OUT_DIR = Path("output-quiz")
MANIFEST = OUT_DIR / "quiz_manifest.json"
SCRIPT_TXT = OUT_DIR / "quiz_script.txt"
COMMENTARY_JSON = OUT_DIR / "commentary.json"


def load_questions(count: int):
    """Carrega de output-quiz/questions.json se existir; senão usa banco local."""
    qfile = OUT_DIR / "questions.json"
    topic = "Conhecimentos Gerais"
    difficulty = "média"
    if qfile.exists():
        try:
            data = json.loads(qfile.read_text(encoding="utf-8"))
            items = data.get("items") or []
            topic = (data.get("topic") or topic).strip() or topic
            if data.get("difficulty"):
                difficulty = (data.get("difficulty") or difficulty).strip() or difficulty
            # normaliza
            norm = []
            for it in items[:count]:
                q = (it.get("q") or "").strip()
                opts = it.get("opts") or []
                ans = int(it.get("ans") or 0)
                if q and isinstance(opts, list) and len(opts) == 5 and 0 <= ans < 5:
                    norm.append({"q": q, "opts": opts, "ans": ans})
            if norm:
                return norm, topic, difficulty
        except Exception:
            pass
    # fallback banco local
    samples = sample_general_knowledge(count)
    return [{"q": it["q"], "opts": it["opts"], "ans": it["ans"]} for it in samples], topic, difficulty


def build_segments(category: str, count: int):
    qs, topic, difficulty = load_questions(count)
    cat_name = topic or "Conhecimentos Gerais"
    diff_map = {"fácil": "Nível Iniciante", "média": "Nível Intermediário", "difícil": "Nível Expert"}
    diff_label = diff_map.get(difficulty.lower(), difficulty)

    # Estrutura: HOOK -> (Q_ASK + COUNTDOWN + REVEAL_EXPLAIN) x N -> CTA
    segments = []
    segments.append({
        "type": "HOOK",
        "text": f"Desafio relâmpago de {cat_name} — {diff_label}! Diz nos comentários quantas você acerta.",
        "topic": cat_name,
        "difficulty": difficulty,
        "difficulty_label": diff_label,
    })
    # Carrega comentários (opcional)
    comments_map = {}
    if COMMENTARY_JSON.exists():
        try:
            cdata = json.loads(COMMENTARY_JSON.read_text(encoding="utf-8"))
            for it in cdata.get("comments", []):
                comments_map[int(it.get("index") or 0)] = {
                    "comment_q": (it.get("comment_q") or "Pensa rápido!").strip(),
                    "comment_a": (it.get("comment_a") or "Clássica — boa de saber.").strip(),
                }
        except Exception:
            pass

    for i, item in enumerate(qs, start=1):
        # Pergunta direta (sem comentário inicial) + anúncio de cronômetro
        segments.append({
            "type": "Q_ASK",
            "index": i,
            "text": item["q"],
            "options": item["opts"],
            "answer_index": item["ans"],
        })
        # countdown de 5s (repete opções para exibir durante a contagem)
        segments.append({
            "type": "COUNTDOWN",
            "index": i,
            "text": item["q"],
            "options": item["opts"],
            "answer_index": item["ans"],
            "seconds": 5,
        })
        # Resposta com explicação informativa
        segments.append({
            "type": "REVEAL_EXPLAIN",
            "index": i,
            "text": item["q"],
            "options": item["opts"],
            "answer_index": item["ans"],
            "comment_a": (comments_map.get(i, {}).get("comment_a") if 'comments_map' in locals() else None)
        })
    segments.append({
        "type": "CTA",
        # Evita dígito na fala para melhor TTS PT-BR
        "text": "Conta nos comentários quantas você acertou e segue a conta pra parte dois!",
    })
    return segments


def write_manifest_and_script(category: str, count: int):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    segments = build_segments(category, count)
    # extrai metadados do HOOK (tópico e dificuldade)
    topic = "Conhecimentos Gerais"
    difficulty = "média"
    diff_label = "Nível Intermediário"
    for seg in segments:
        if seg.get("type") == "HOOK":
            topic = seg.get("topic") or topic
            difficulty = seg.get("difficulty") or difficulty
            diff_label = seg.get("difficulty_label") or diff_label
            break
    manifest = {
        "category": category,
        "count": count,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "segments": segments,
        "topic": topic,
        "difficulty": difficulty,
        "difficulty_label": diff_label,
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # Conversor simples de números (0-60) para extenso em PT-BR
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
        # fallback
        return str(n)

    # Roteiro para TTS — sem comentário antes da pergunta; explicação após resposta
    def choose_timer_phrase(seconds: int = 5) -> str:
        s_ext = num_pt(seconds)
        variants = [
            f"Valendo! {s_ext} segundos pra responder.",
            f"Começa o timer de {s_ext} segundos…", 
            f"Responda nos próximos {s_ext} segundos!", 
            f"Preparado? {s_ext} segundos, valendo!",
            f"Tempo na tela: {s_ext} segundos. Vai!",
        ]
        # Opcional: deixar o ChatGPT escolher uma variação curtinha
        if os.getenv("QUIZ_TIMER_VARIANT_OPENAI", "0") == "1":
            try:
                from openai import OpenAI
                client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                prompt = (
                    "Gere UMA variação curtíssima (<= 8 palavras) em português do Brasil para iniciar um cronômetro "
                    f"de {num_pt(seconds)} segundos. Ex.: 'Valendo! {num_pt(seconds)} segundos pra responder.' Responda só a frase."
                )
                resp = client.chat.completions.create(
                    model=os.getenv("QUIZ_QA_MODEL", "gpt-4o-mini"),
                    messages=[{"role":"user","content":prompt}],
                    temperature=0.7,
                    max_tokens=30,
                )
                txt = (resp.choices[0].message.content or "").strip()
                if 0 < len(txt) <= 60:
                    return txt
            except Exception:
                pass
        return random.choice(variants)
    lines = []
    for seg in segments:
        t = seg["type"]
        if t == "HOOK":
            lines.append(f"NARRADOR: {seg['text']}")
        elif t == "Q_ASK":
            idx = seg["index"]
            phrase = choose_timer_phrase(5)
            # Converte índice da pergunta para extenso para evitar leitura em inglês
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

            idx_ext = num_pt(int(idx))
            lines.append(f"NARRADOR: Pergunta número {idx_ext}: {seg['text']}. {phrase}")
        elif t == "REVEAL_EXPLAIN":
            ans = seg["answer_index"]
            opt = seg["options"][ans]
            letra = ["A","B","C","D","E"][ans]
            ca = (seg.get("comment_a") or "").strip()
            # Explicação mais rica: se houver comentário gerado, usa; senão uma frase padrão
            if ca:
                lines.append(f"NARRADOR: Resposta correta: letra {letra}, {opt}. {ca}")
            else:
                lines.append(f"NARRADOR: Resposta correta: letra {letra}, {opt}. Essa é a opção certa pelos fundamentos do tema.")
        elif t == "CTA":
            lines.append(f"NARRADOR: {seg['text']}")
    SCRIPT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Gera script/manifest de quiz simples")
    ap.add_argument("--category", default="casais", help="casais|filmes|animes|politica")
    ap.add_argument("--count", type=int, default=3, help="quantidade de perguntas")
    args = ap.parse_args()

    write_manifest_and_script(args.category, args.count)
    print(f"✅ Manifest: {MANIFEST}")
    print(f"✅ Roteiro:  {SCRIPT_TXT}")


if __name__ == "__main__":
    main()
