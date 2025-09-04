#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gera perguntas de quiz via OpenAI (ChatGPT) e salva em output-quiz/questions.json.
Formato de cada item: {"q": str, "opts": [5 itens], "ans": int 0-4}
"""

import os, json, re, sys, time
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from openai import OpenAI
import argparse

OUT_DIR = Path("output-quiz")
QUESTIONS_JSON = OUT_DIR / "questions.json"
LOG_PATH = OUT_DIR / "log_quiz.txt"


def log(msg: str):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def try_parse_json(s: str):
    # tenta extrair bloco ```json ... ``` ou o primeiro array/obj json válido
    m = re.search(r"```json\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```", s, re.I)
    if m:
        s = m.group(1)
    # tenta direto
    try:
        return json.loads(s)
    except Exception:
        # tenta localizar primeiro [...] top-level
        m2 = re.search(r"(\[\s*[\s\S]*\])", s)
        if m2:
            try:
                return json.loads(m2.group(1))
            except Exception:
                pass
    return None


def validate_items(items):
    ok = []
    for it in items:
        q = (it.get("q") or "").strip()
        opts = it.get("opts") or []
        ans = it.get("ans")
        if not q or not isinstance(opts, list) or len(opts) != 5:
            continue
        opts = [str(x).strip() for x in opts]
        if any(not x for x in opts):
            continue
        try:
            ai = int(ans)
        except Exception:
            continue
        if ai < 0 or ai >= 5:
            continue
        # remove opções duplicadas mantendo ordem
        seen = set(); uniq = []
        for x in opts:
            xl = x.lower()
            if xl in seen: continue
            seen.add(xl); uniq.append(x)
        if len(uniq) != 5:
            # completa com placeholders simples
            while len(uniq) < 5:
                uniq.append(f"Opção {len(uniq)+1}")
        ok.append({"q": q, "opts": uniq, "ans": ai})
    return ok


def build_prompt(topic: str, count: int, difficulty: str) -> tuple[str, str]:
    system = (
        "Você cria perguntas de conhecimentos gerais em Português do Brasil. "
        "Responda apenas JSON válido."
    )
    user = f"""
Gere {count} perguntas de conhecimentos gerais ({topic}, dificuldade: {difficulty}).
Regras por item:
- Campo q: a pergunta (clara e objetiva).
- Campo opts: EXATAMENTE 5 alternativas plausíveis (strings curtas).
- Campo ans: índice da alternativa correta (0 a 4).
- Não use imagens, links, nem formatação; sem gírias ou marcas registradas; evite temas sensíveis.
- Evite perguntas ambíguas ou dependentes de data/atualização (use fatos estáveis/históricos).

Responda apenas com um JSON array no formato:
[
  {{"q": "...", "opts": ["A","B","C","D","E"], "ans": 0}},
  ...
]
"""
    return system, user


def main():
    ap = argparse.ArgumentParser(description="Gera perguntas de quiz via OpenAI")
    ap.add_argument("--topic", default="conhecimentos gerais")
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--difficulty", default="média", choices=["fácil", "média", "difícil"])
    ap.add_argument("--model", default=os.getenv("QUIZ_QA_MODEL", "gpt-4o-mini"))
    args = ap.parse_args()

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        log("❌ OPENAI_API_KEY não configurada no .env")
        sys.exit(1)
    client = OpenAI(api_key=api_key)

    system, user = build_prompt(args.topic, args.count, args.difficulty)
    log(f"🧠 Gerando {args.count} perguntas — tópico: {args.topic}, dificuldade: {args.difficulty}")
    t0 = time.time()
    resp = client.chat.completions.create(
        model=args.model,
        messages=[{"role":"system","content":system},{"role":"user","content":user}],
        temperature=0.7,
        max_tokens=2000,
    )
    content = resp.choices[0].message.content
    elapsed = time.time() - t0
    log(f"📝 Resposta recebida em {elapsed:.1f}s; parseando JSON…")

    parsed = try_parse_json(content or "")
    if not isinstance(parsed, list):
        log("❌ Não consegui parsear JSON. Conteúdo salvo em output-quiz/questions_raw.txt")
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "questions_raw.txt").write_text(content or "", encoding="utf-8")
        sys.exit(1)

    items = validate_items(parsed)
    if not items:
        log("❌ Nenhuma pergunta válida após validação")
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    QUESTIONS_JSON.write_text(json.dumps({
        "topic": args.topic,
        "difficulty": args.difficulty,
        "items": items
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"✅ Perguntas salvas em {QUESTIONS_JSON} ({len(items)} itens)")


if __name__ == "__main__":
    main()

