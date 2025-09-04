#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gera comentários curtos para cada pergunta do quiz:
- comment_q: curiosidade/gancho (tom de apresentador de TV), sem repetir a pergunta.
- comment_a: comentário sobre a resposta correta (explica ou traz um fato).

Entrada: output-quiz/questions.json
Saída:  output-quiz/commentary.json
"""

import os, json, re, time
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from openai import OpenAI
import argparse

OUT_DIR = Path("output-quiz")
QUESTIONS_JSON = OUT_DIR / "questions.json"
COMMENTARY_JSON = OUT_DIR / "commentary.json"


def log(msg: str):
    ts = datetime.now(timezone.utc).isoformat()
    print(f"[{ts}] {msg}")


def try_parse_json(s: str):
    m = re.search(r"```json\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```", s, re.I)
    if m:
        s = m.group(1)
    try:
        return json.loads(s)
    except Exception:
        # tenta objeto com campo comments
        try:
            obj = json.loads(s.strip().strip("`"))
            return obj
        except Exception:
            return None


def normalize_comments(parsed, count: int):
    """Aceita lista/objeto e retorna lista de {index, comment_q, comment_a}.
    Preenche faltantes com frases padrão.
    """
    out = []
    if isinstance(parsed, list):
        for i in range(count):
            it = parsed[i] if i < len(parsed) else {}
            cq = (it.get("comment_q") if isinstance(it, dict) else None) or "Pensa rápido!"
            ca = (it.get("comment_a") if isinstance(it, dict) else None) or "Resposta clássica — anota aí!"
            out.append({"index": i+1, "comment_q": str(cq).strip(), "comment_a": str(ca).strip()})
        return out
    if isinstance(parsed, dict):
        # tenta chave 'comments'
        arr = None
        if isinstance(parsed.get("comments"), list):
            arr = parsed["comments"]
        elif isinstance(parsed.get("items"), list):
            arr = parsed["items"]
        if arr is not None:
            return normalize_comments(arr, count)
        # tenta mapa por índice como keys
        for i in range(count):
            key = str(i+1)
            it = parsed.get(key, {})
            cq = (it.get("comment_q") if isinstance(it, dict) else None) or "Pensa rápido!"
            ca = (it.get("comment_a") if isinstance(it, dict) else None) or "Resposta clássica — anota aí!"
            out.append({"index": i+1, "comment_q": str(cq).strip(), "comment_a": str(ca).strip()})
        return out
    # fallback vazio
    for i in range(count):
        out.append({"index": i+1, "comment_q": "Pensa rápido!", "comment_a": "Resposta clássica — anota aí!"})
    return out


def heuristic_fallback(items):
    """Gera comentários simples a partir da pergunta/assunto, sem repetir a pergunta."""
    out = []
    for i, it in enumerate(items, start=1):
        q = (it.get("q") or "").strip().rstrip("?"),
        cq = "Dica: puxe pela memória e confie no instinto!"
        ca = "Curioso, né? Daquelas que valem em provas e quizzes."
        out.append({"index": i, "comment_q": cq, "comment_a": ca})
    return out


def build_prompt(items, topic: str, difficulty: str) -> tuple[str, str]:
    system = (
        "Você é um apresentador de TV brasileiro, carismático e conciso. "
        "Para cada pergunta, crie dois comentários curtos em PT-BR: \n"
        "- comment_q: curiosidade/gancho antes da resposta (não repete a pergunta). \n"
        "- comment_a: comentário sobre a resposta correta (pode explicar ou trazer um fato). \n"
        "Responda apenas JSON válido."
    )
    examples = [
        {
            "q": "Qual é a capital da França?",
            "opts": ["Paris","Roma","Madri","Berlim","Lisboa"],
            "ans": 0
        }
    ]
    user = {
        "topic": topic,
        "difficulty": difficulty,
        "items": items,
        "style": {
            "tone": "apresentador de TV, leve, confiante",
            "comment_q": "1 frase, 8-16 palavras",
            "comment_a": "1 frase, 10-18 palavras",
            "avoid": ["repetir a pergunta", "citar letras das opções", "gírias pesadas"],
        }
    }
    return system, json.dumps(user, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser(description="Gera comentários do apresentador para o quiz")
    ap.add_argument("--model", default=os.getenv("QUIZ_QA_MODEL", "gpt-4o-mini"))
    args = ap.parse_args()

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        log("❌ OPENAI_API_KEY não configurada no .env")
        raise SystemExit(1)
    client = OpenAI(api_key=api_key)

    if not QUESTIONS_JSON.exists():
        log(f"❌ {QUESTIONS_JSON} não encontrado — gere perguntas primeiro.")
        raise SystemExit(1)
    qdata = json.loads(QUESTIONS_JSON.read_text(encoding="utf-8"))
    items = qdata.get("items") or []
    topic = qdata.get("topic") or "Conhecimentos Gerais"
    difficulty = qdata.get("difficulty") or "média"
    if not items:
        log("❌ Lista de perguntas vazia.")
        raise SystemExit(1)

    system, user = build_prompt(items, topic, difficulty)
    log(f"🗣️ Gerando comentários: {len(items)} itens")
    t0 = time.time()
    resp = client.chat.completions.create(
        model=args.model,
        messages=[{"role":"system","content":system},{"role":"user","content":user}],
        temperature=0.7,
        max_tokens=2000,
    )
    elapsed = time.time() - t0
    log(f"📝 Resposta recebida em {elapsed:.1f}s; parseando JSON…")

    content = resp.choices[0].message.content or ""
    parsed = try_parse_json(content)
    if parsed is None:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "commentary_raw.txt").write_text(content, encoding="utf-8")
        log("⚠️ Falha ao parsear JSON; usando fallback heurístico…")
        out = heuristic_fallback(items)
    else:
        out = normalize_comments(parsed, len(items))

    COMMENTARY_JSON.write_text(json.dumps({
        "topic": topic,
        "difficulty": difficulty,
        "comments": out
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"✅ Comentários salvos em {COMMENTARY_JSON}")


if __name__ == "__main__":
    main()
