#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gera perguntas de quiz via OpenAI (ChatGPT) e salva em output-quiz/questions.json.
Formato de cada item: {"q": str, "opts": [5 itens], "ans": int 0-4}

Melhorias de qualidade:
- Oversample (gera mais perguntas do que o necessário) e filtra por novidade.
- Histórico de perguntas para reduzir repetição entre execuções.
- Prompt especializado para programação (curtas, didáticas, variadas e com progressão de dificuldade).
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
HISTORY_JSON = OUT_DIR / "questions_history.json"


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


def _normalize_text(s: str) -> str:
    import unicodedata, re
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _jaccard(a: str, b: str) -> float:
    sa = set(_normalize_text(a).split())
    sb = set(_normalize_text(b).split())
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb); uni = len(sa | sb)
    return inter / float(uni or 1)


def _load_history() -> list[str]:
    try:
        if HISTORY_JSON.exists():
            data = json.loads(HISTORY_JSON.read_text(encoding="utf-8"))
            return [str(x) for x in data.get("items", [])]
    except Exception:
        pass
    return []


def _save_history(history: list[str]):
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        HISTORY_JSON.write_text(json.dumps({"items": history[-2000:]}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def validate_items(items):
    ok = []
    for it in items:
        q = (it.get("q") or "").strip()
        opts = it.get("opts") or []
        ans = it.get("ans")
        level = (it.get("level") or "").strip().lower()
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
        # remove opções duplicadas mantendo ordem e descarta pegadinhas genéricas
        seen = set(); uniq = []
        for x in opts:
            xl = x.lower()
            if xl in seen: continue
            if xl in {"todas as anteriores","todas as alternativas","todas as acima","nenhuma das anteriores","nenhuma das alternativas","all of the above","none of the above"}:
                continue
            seen.add(xl); uniq.append(x)
        if len(uniq) != 5:
            # completa com placeholders simples
            while len(uniq) < 5:
                uniq.append(f"Opção {len(uniq)+1}")
        item = {"q": q, "opts": uniq, "ans": ai}
        if level in {"estagiario","junior","pleno","senior"}:
            item["level"] = level
        ok.append(item)
    return ok


def build_prompt(topic: str, count: int, difficulty: str, oversample: int = 1) -> tuple[str, str, int]:
    system = (
        "Você cria perguntas de quiz em Português do Brasil. Responda apenas JSON válido."
    )
    # Se o tema for programação (ou similar), usa prompt especializado
    tl = (topic or "").lower()
    is_prog = any(k in tl for k in ["programa", "codigo", "coding", "desenvolv", "software"]) or tl == "programação"
    target = max(count * max(1, oversample), count)
    if is_prog:
        user = f"""
Gere {target} perguntas de programação (tema: {topic}). Produza itens curtos, didáticos e variados, com progressão de dificuldade dentro do conjunto.
Regras por item:
- Campo q: a pergunta (clara, com até ~18 palavras). Evite verborragia. Se apropriado, inclua um trecho de código curto (1–3 linhas) diretamente como string.
- Campo opts: EXATAMENTE 5 alternativas plausíveis e curtas (<= 60 caracteres).
- Campo ans: índice da alternativa correta (0 a 4).
- Campo level: "estagiario" | "junior" | "pleno" | "senior".
- Estilo: interessante e prático. Combine tipos: conceitos (ex.: imutabilidade), complexidade (Big‑O), estrutura de dados, depuração (bug provável), saída de código curto, boas práticas, segurança.
- Diversifique: não repita o mesmo subtipo em sequência.
- Progrida dificuldade com GRAU ELEVADO: estagiario (básico direto), junior (conceitos com exemplo), pleno (raciocínio e comparação), senior (análise profunda/ trade‑offs, atenção a edge cases/performance/concorrência).
- Evite: “todas as anteriores/alternativas”, perguntas ambíguas ou dependentes de versão/ano; evite temas sensíveis.
- Não use Markdown (sem ```), nem links, nem gírias. Snippets devem ser strings normais em uma linha ou com \n.

Responda com JSON (array) no formato:
[
  {{"q": "...", "opts": ["A","B","C","D","E"], "ans": 0, "level": "junior"}},
  ...
]
"""
    else:
        user = f"""
Gere {target} perguntas ({topic}, dificuldade alvo: {difficulty}) com progressão dentro do conjunto.
Regras por item:
- Campo q: pergunta curta e objetiva (pode conter trechos simples de código em string quando fizer sentido).
- Campo opts: EXATAMENTE 5 alternativas plausíveis (strings curtas), sem “todas as anteriores/alternativas”.
- Campo ans: índice correto (0..4).
- Campo level: "estagiario" | "junior" | "pleno" | "senior" (distribua e escale a dificuldade fortemente).
- Evite ambiguidade e dependências de data; não use formatação/links/gírias.

Retorne apenas um JSON array:
[
  {{"q": "...", "opts": ["A","B","C","D","E"], "ans": 0, "level": "estagiario"}},
  ...
]
"""
    return system, user, target


def main():
    ap = argparse.ArgumentParser(description="Gera perguntas de quiz via OpenAI")
    ap.add_argument("--topic", default="conhecimentos gerais")
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--difficulty", default="média", choices=["fácil", "média", "difícil"])
    ap.add_argument("--model", default=os.getenv("QUIZ_QA_MODEL", "gpt-4o-mini"))
    ap.add_argument("--temp", type=float, default=float(os.getenv("QUIZ_QA_TEMP","0.55")))
    ap.add_argument("--novelty-threshold", type=float, default=float(os.getenv("QUIZ_NOVELTY","0.82")), help="Jaccard mínimo para considerar repetição (0..1)")
    ap.add_argument("--oversample", type=int, default=int(os.getenv("QUIZ_OVERSAMPLE","2")), help="Gera ~count*oversample e filtra por novidade")
    args = ap.parse_args()

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        log("❌ OPENAI_API_KEY não configurada no .env")
        sys.exit(1)
    client = OpenAI(api_key=api_key)

    system, user, target = build_prompt(args.topic, args.count, args.difficulty, oversample=args.oversample)
    log(f"🧠 Gerando {args.count} perguntas — tópico: {args.topic}, dificuldade: {args.difficulty}")
    t0 = time.time()
    resp = client.chat.completions.create(
        model=args.model,
        messages=[{"role":"system","content":system},{"role":"user","content":user}],
        temperature=max(0.1, min(1.0, args.temp)),
        max_tokens=2400,
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

    # Filtra por novidade usando histórico e entre si
    hist = _load_history()
    novel = []
    dropped = 0
    for it in items:
        q = it["q"]
        if any(_jaccard(q, h) >= args.novelty_threshold for h in hist):
            dropped += 1
            continue
        if any(_jaccard(q, x["q"]) >= args.novelty_threshold for x in novel):
            dropped += 1
            continue
        novel.append(it)
        if len(novel) >= args.count:
            break
    if len(novel) < args.count:
        log(f"⚠️ Itens novos insuficientes após filtro ({len(novel)}/{args.count}); completando com remanescentes.")
        # completa com itens menos similares (ordenar por sim média ascendente)
        def avg_sim(q):
            if not hist:
                return 0.0
            return max((_jaccard(q, h) for h in hist), default=0.0)
        remaining = sorted(items, key=lambda it: avg_sim(it["q"]))
        for it in remaining:
            if it in novel:
                continue
            novel.append(it)
            if len(novel) >= args.count:
                break
    if dropped:
        log(f"🔁 Removidos por repetição/semelhança: {dropped}")

    # Atualiza histórico
    hist.extend([it["q"] for it in novel])
    _save_history(hist)

    # Estatística por nível (se presente)
    dist = {}
    for it in novel:
        lv = it.get("level")
        if lv:
            dist[lv] = dist.get(lv, 0) + 1
    if dist:
        log(f"📊 Distribuição por nível: {dist}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    QUESTIONS_JSON.write_text(json.dumps({
        "topic": args.topic,
        "difficulty": args.difficulty,
        "items": novel
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"✅ Perguntas salvas em {QUESTIONS_JSON} ({len(novel)} itens)")


if __name__ == "__main__":
    main()
