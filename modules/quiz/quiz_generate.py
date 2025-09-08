#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, json, os, random, re, time
from pathlib import Path
from datetime import datetime, timezone

import json
from .questions_bank import sample_general_knowledge
from dotenv import load_dotenv
try:
    from openai import OpenAI  # type: ignore
except Exception:
    OpenAI = None  # type: ignore

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


def _hook_text_for_topic(topic: str, diff_label: str, count: int) -> str:
    """Gera um texto de HOOK curto com variações, baseado no tópico e dificuldade."""
    # Allow full override via env
    forced = os.getenv("QUIZ_HOOK_FORCE", "").strip()
    if forced:
        return forced
    tpl = [
        f"Desafio relâmpago de {{topic}} — {{diff}}! Quantas você acerta?",
        f"Valendo! Quiz de {{topic}} ({{diff}}).",
        f"{{count}} perguntas de {{topic}} — {{diff}}. Pronto?",
        f"Quanto você manja de {{topic}}? {{diff}}.",
        f"{{topic}} na veia — {{diff}}. Responde rápido!",
        f"Se você curte {{topic}}, prova agora — {{diff}}.",
    ]
    var = (os.getenv("QUIZ_HOOK_VARIANT", "random") or "random").strip().lower()
    idx = None
    if var.isdigit():
        try:
            idx = max(0, min(len(tpl)-1, int(var)))
        except Exception:
            idx = None
    if idx is None:
        idx = random.randrange(len(tpl))
    s = tpl[idx]
    return s.replace("{topic}", topic).replace("{diff}", diff_label).replace("{count}", str(count))


def _hook_candidates_via_openai(topic: str, difficulty: str, diff_label: str, count: int) -> list[str] | None:
    """Gera variações de HOOK via OpenAI. Retorna lista de 3-6 frases curtas.
    Regras:
    - PT-BR, 1 frase por variação (7-14 palavras, sem emoji/hashtag)
    - Deve mencionar: desafio + nível (diff_label)
    - Deve induzir retenção: diga que "a última é a mais difícil" e "feita para gênios da área"
    - Sem citações, sem markdown, sem números de lista.
    """
    try:
        load_dotenv()
        key = os.getenv("OPENAI_API_KEY")
        if not key or OpenAI is None:
            return None
        model = os.getenv("QUIZ_HOOK_MODEL", os.getenv("QUIZ_QA_MODEL", "gpt-4o-mini"))
        temp = float(os.getenv("QUIZ_HOOK_TEMP", os.getenv("QUIZ_QA_TEMP", "0.8")))
        n_vars = max(3, min(8, int(os.getenv("QUIZ_HOOK_VARIATIONS", "5"))))
        client = OpenAI(api_key=key)
        system = (
            "Você escreve ganchos (HOOKs) curtos e impactantes em PT-BR para vídeos de quiz (TikTok/Shorts). "
            "Objetivo: prender atenção no primeiro segundo."
        )
        user = {
            "topic": topic,
            "difficulty": difficulty,
            "difficulty_label": diff_label,
            "count": count,
            "instructions": [
                "Escreva de 3 a 6 variações curtas (1 frase cada).",
                "7–14 palavras por variação, sem emojis, hashtags ou markdown.",
                "Mencione que é um desafio e cite o nível (difficulty_label).",
                "Inclua sempre a mensagem: a última é a mais difícil e feita para gênios da área.",
                "Evite promessas absolutas; mantenha tom enérgico e bem-humorado.",
                "Retorne como linhas separadas (uma por linha), sem numeração.",
            ],
            "examples": [
                f"Desafio relâmpago de {topic} — {diff_label}. A última é para gênios, fica até o fim!",
                f"Valendo! Quiz de {topic} ({diff_label}); a última é casca grossa, só gênio passa.",
            ],
            "n": n_vars,
        }
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role":"system","content":system},{"role":"user","content":json.dumps(user, ensure_ascii=False)}],
            temperature=max(0.1, min(1.0, temp)),
            max_tokens=400,
        )
        content = resp.choices[0].message.content or ""
        # Quebra por linhas não vazias, limpa aspas
        lines = [re.sub(r'^[\s\-\d\.)]+', '', ln.strip().strip('"\'')) for ln in content.splitlines()]
        lines = [ln for ln in lines if ln]
        # Filtra tamanho (4..22 palavras)
        def wc(s: str) -> int: return len(re.findall(r"\w+", s, flags=re.UNICODE))
        lines = [ln for ln in lines if 4 <= wc(ln) <= 22]
        # Remove duplicadas aproximadas
        uniq = []
        seen = set()
        for ln in lines:
            base = re.sub(r"\W+", " ", ln.lower()).strip()
            if base in seen:
                continue
            seen.add(base)
            uniq.append(ln)
        return uniq[:n_vars] or None
    except Exception:
        return None


def gen_hook_text(topic: str, difficulty: str, diff_label: str, count: int) -> tuple[str, list[str]]:
    """Gera HOOK via OpenAI com fallback local. Retorna (escolhido, candidatos)."""
    forced = os.getenv("QUIZ_HOOK_FORCE", "").strip()
    if forced:
        return forced, [forced]
    cands = _hook_candidates_via_openai(topic, difficulty, diff_label, count) or []
    if not cands:
        # fallback local variado
        fallback = _hook_text_for_topic(topic, diff_label, count)
        return fallback, [fallback]
    chosen = random.choice(cands)
    return chosen, cands


def build_segments(category: str, count: int, no_hook: bool = True):
    qs, topic, difficulty = load_questions(count)
    cat_name = topic or "Conhecimentos Gerais"
    diff_map = {"fácil": "Nível Iniciante", "média": "Nível Intermediário", "difícil": "Nível Expert"}
    diff_label = diff_map.get(difficulty.lower(), difficulty)

    # Estrutura: HOOK -> (Q_ASK + COUNTDOWN + REVEAL_EXPLAIN) x N -> CTA
    segments = []
    if not no_hook:
        hook_text, hook_variants = gen_hook_text(cat_name, difficulty, diff_label, count)
        segments.append({
            "type": "HOOK",
            "text": hook_text,
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
    return segments, cat_name, difficulty, diff_label


def write_manifest_and_script(category: str, count: int, no_hook: bool = True):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    segments, topic, difficulty, diff_label = build_segments(category, count, no_hook=no_hook)
    manifest = {
        "category": category,
        "count": count,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "segments": segments,
        "topic": topic,
        "difficulty": difficulty,
        "difficulty_label": diff_label,
        "hook_variants": hook_variants if 'hook_variants' in locals() else [],
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
    # Removido: não anunciamos mais o cronômetro na fala do narrador.
    lines = []
    for seg in segments:
        t = seg["type"]
        if t == "HOOK":
            lines.append(f"NARRADOR: {seg['text']}")
        elif t == "Q_ASK":
            idx = seg["index"]
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
            # Sem anúncio do timer: pergunta termina e o COUNTDOWN começa logo após
            lines.append(f"NARRADOR: Pergunta número {idx_ext}: {seg['text']}")
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
    # HOOK agora habilitado por padrão (QUIZ_NO_HOOK=0). Use --no-hook para remover.
    ap.add_argument("--no-hook", action="store_true", default=bool(int(os.getenv("QUIZ_NO_HOOK","0"))), help="Remove segmento de abertura (HOOK)")
    args = ap.parse_args()

    write_manifest_and_script(args.category, args.count, no_hook=args.no_hook)
    print(f"✅ Manifest: {MANIFEST}")
    print(f"✅ Roteiro:  {SCRIPT_TXT}")


if __name__ == "__main__":
    main()
