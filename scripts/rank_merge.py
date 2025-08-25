#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RankMerge — consenso de tendências (YouTube ∩ Alt)
--------------------------------------------------
Lê:
  - YouTube: output/trends.json (gerado por trends_hub.py)
  - Alt:     output/alt_trends.json (gerado por alt_trends_hub.py)

Une tópicos por fuzzy (token_sort_ratio) e ranqueia consenso.

Exemplos:
  python3 scripts/rank_merge.py \
    --yt output/trends.json \
    --alt output/alt_trends.json \
    --topk 10 \
    --threshold 84 \
    --save output/consensus.json
"""

from __future__ import annotations
import argparse, json, os, re, sys, math, statistics
from typing import List, Dict, Any, Tuple, Optional

# ──────────────────────────────────────────────────────────────────────────────
# utils
# ──────────────────────────────────────────────────────────────────────────────

def strip_accents(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[áàâãä]", "a", s)
    s = re.sub(r"[éèêë]", "e", s)
    s = re.sub(r"[íìîï]", "i", s)
    s = re.sub(r"[óòôõö]", "o", s)
    s = re.sub(r"[úùûü]", "u", s)
    s = re.sub(r"ç", "c", s)
    return s

def slug_spaces(s: str) -> str:
    s = strip_accents(s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s

def logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))

def zscore(vals: List[float]) -> List[float]:
    if not vals: return []
    if all(v == vals[0] for v in vals): return [0.0]*len(vals)
    m = statistics.mean(vals)
    sd = statistics.pstdev(vals) or 1e-9
    return [(v - m)/sd for v in vals]

def safe_get(d: Dict, path: List[str], default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur

def uniq(seq):
    seen=set(); out=[]
    for x in seq:
        if x not in seen:
            seen.add(x); out.append(x)
    return out

# ──────────────────────────────────────────────────────────────────────────────
# core
# ──────────────────────────────────────────────────────────────────────────────

def load_json(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        print(f"[ERROR] arquivo não encontrado: {path}", file=sys.stderr)
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            else:
                return []
    except Exception as e:
        print(f"[ERROR] falha ao ler {path}: {e}", file=sys.stderr)
        return []

def build_keys(item: Dict[str, Any]) -> List[str]:
    """gera chaves de matching a partir de topic, aliases e keywords"""
    keys = []
    topic = item.get("topic") or ""
    keys.append(slug_spaces(topic))
    for a in item.get("aliases", []) or []:
        keys.append(slug_spaces(a))
    for k in item.get("keywords", []) or []:
        keys.append(slug_spaces(k))
    return uniq([k for k in keys if k])

def fuzzy_best(query: str, candidates: List[str]) -> Tuple[int, float]:
    """
    retorna (idx, score 0..100) do melhor candidato (ou (-1,0))
    """
    try:
        from rapidfuzz import process, fuzz
        res = process.extractOne(query, candidates, scorer=fuzz.token_sort_ratio)
        if res is None: return -1, 0.0
        cand, score, idx = res
        return idx, float(score)
    except Exception:
        # fallback: igualdade exata
        try:
            idx = candidates.index(query)
            return idx, 100.0
        except ValueError:
            return -1, 0.0

def merge(yt_items: List[Dict[str,Any]], alt_items: List[Dict[str,Any]], threshold: int) -> Dict[str, Any]:
    # indexa ALT por múltiplas chaves
    alt_index: List[Tuple[int, str]] = []
    alt_keys_flat: List[str] = []
    for i, it in enumerate(alt_items):
        for k in build_keys(it):
            alt_index.append((i, k))
            alt_keys_flat.append(k)

    used_alt = set()
    pairs = []
    only_yt = []
    for y in yt_items:
        y_keys = build_keys(y)
        # prioriza melhor match entre todas as chaves do yt
        best = (-1, 0.0, None)  # (alt_idx, score, key_used)
        for yk in y_keys:
            idx, score = fuzzy_best(yk, alt_keys_flat)
            if score > best[1]:
                best = (alt_index[idx][0] if idx>=0 else -1, score, yk)
        if best[0] >= 0 and best[1] >= threshold and best[0] not in used_alt:
            pairs.append((y, alt_items[best[0]], best[1]))
            used_alt.add(best[0])
        else:
            only_yt.append(y)

    only_alt = [it for i, it in enumerate(alt_items) if i not in used_alt]

    return {"pairs": pairs, "only_yt": only_yt, "only_alt": only_alt}

def consensus_score(y: Dict[str,Any], a: Dict[str,Any]) -> float:
    """
    score final 0..1. Dá mais peso ao YouTube (forte proxy de demanda) e complementa com Alt.
    """
    y_s = float(safe_get(y, ["signals","_score"], 0.0) or 0.0)   # 0..1
    a_s = float(safe_get(a, ["signals","_score"], 0.0) or 0.0)   # 0..1

    # sinais auxiliares (normalizados já 0..100)
    y_v = float(safe_get(y, ["signals","yt_view_velocity"], 0.0) or 0.0)   # 0..100
    a_p = float(safe_get(a, ["signals","popularity"], 0.0) or 0.0)         # 0..100
    a_src = float(safe_get(a, ["signals","src_count"], 1.0) or 1.0)

    # normaliza auxiliares com zscore intra-par para suavizar escala
    z_v = zscore([y_v, 0.0])[0]
    z_p = zscore([a_p, 0.0])[0]
    z_src = zscore([a_src, 0.0])[0]

    # combinação linear e logística
    lin = 0.60*y_s + 0.40*a_s + 0.15*z_v + 0.10*z_p + 0.05*z_src
    return float(logistic(lin))

def union_keywords(y: Dict[str,Any], a: Dict[str,Any]) -> List[str]:
    ks = []
    for arr in (y.get("keywords", []), a.get("keywords", [])):
        for k in (arr or []):
            k = slug_spaces(k)
            if k and k not in ks: ks.append(k)
    # forma hashtags curtas (até 20 chars)
    tags = []
    for k in ks:
        tag = "#" + re.sub(r"\s+", "", k)[:20]
        if tag not in tags: tags.append(tag)
    return tags[:6]

def pick_title(y: Dict[str,Any], a: Dict[str,Any]) -> str:
    # prioriza título mais específico (maior), mas sem estourar 80 chars
    candidates = [y.get("topic",""), a.get("topic","")]
    cand = max(candidates, key=lambda s: (len(s), s))
    return cand[:80].strip() or (y.get("topic") or a.get("topic") or "Tópico")

def summarize_pair(y: Dict[str,Any], a: Dict[str,Any]) -> Dict[str,Any]:
    title = pick_title(y,a)
    category = y.get("category") if y.get("category") == a.get("category") else (y.get("category") or a.get("category") or "general")
    score_c = consensus_score(y,a)
    hashtags = union_keywords(y,a)

    # pega 1 evidência útil do YouTube (link do vídeo) e 2 do Alt (links de notícia)
    yt_ev = next((e for e in y.get("evidence",[]) if e.get("provider")=="youtube"), None)
    alt_evs = (a.get("evidence") or [])[:2]

    return {
        "topic": title,
        "category": category,
        "score_consensus": score_c,
        "score_yt": float(safe_get(y, ["signals","_score"], 0.0) or 0.0),
        "score_alt": float(safe_get(a, ["signals","_score"], 0.0) or 0.0),
        "yt_signals": {
            "yt_view_velocity": float(safe_get(y, ["signals","yt_view_velocity"], 0.0) or 0.0),
            "yt_recency": float(safe_get(y, ["signals","yt_recency"], 0.0) or 0.0),
        },
        "alt_signals": {
            "src_count": float(safe_get(a, ["signals","src_count"], 0.0) or 0.0),
            "news_count": float(safe_get(a, ["signals","news_count"], 0.0) or 0.0),
            "popularity": float(safe_get(a, ["signals","popularity"], 0.0) or 0.0),
            "recency": float(safe_get(a, ["signals","recency"], 0.0) or 0.0),
        },
        "hashtags": hashtags,
        "evidence": {
            "youtube": yt_ev,
            "alt": alt_evs
        },
        "raw": {"youtube": y, "alt": a}
    }

def main():
    ap = argparse.ArgumentParser(description="RankMerge — consenso entre YouTube e Alt")
    ap.add_argument("--yt", type=str, default="output/trends.json", help="JSON do YouTube trends_hub.py")
    ap.add_argument("--alt", type=str, default="output/alt_trends.json", help="JSON do alt_trends_hub.py")
    ap.add_argument("--topk", type=int, default=10, help="quantidade de tópicos de consenso a imprimir/salvar")
    ap.add_argument("--threshold", type=int, default=84, help="fuzzy threshold (0-100) para unir tópicos")
    ap.add_argument("--min-score-yt", type=float, default=0.0, help="filtra YouTube score < x (0..1)")
    ap.add_argument("--min-score-alt", type=float, default=0.0, help="filtra Alt score < x (0..1)")
    ap.add_argument("--save", type=str, default="output/consensus.json", help="onde salvar o JSON consolidado")
    args = ap.parse_args()

    yt = [it for it in load_json(args.yt) if float(it.get("score",0.0)) >= args.min_score_yt]
    alt = [it for it in load_json(args.alt) if float(it.get("score",0.0)) >= args.min_score_alt]

    merged = merge(yt, alt, threshold=args.threshold)

    # monta pares consolidados
    pairs = [summarize_pair(y,a) for (y,a,sim) in merged["pairs"]]
    # ordena por score de consenso
    pairs.sort(key=lambda r: r["score_consensus"], reverse=True)
    top_pairs = pairs[:args.topk]

    # listas auxiliares
    only_yt_sorted = sorted(merged["only_yt"], key=lambda x: float(x.get("score",0.0)), reverse=True)[:args.topk]
    only_alt_sorted = sorted(merged["only_alt"], key=lambda x: float(x.get("score",0.0)), reverse=True)[:args.topk]

    print("\n=== CONSENSO (YouTube ∩ Alt) ===")
    for i, r in enumerate(top_pairs, 1):
        print(f"{i:02d}. {r['topic']}  | consensus={r['score_consensus']:.3f}  yt={r['score_yt']:.3f}  alt={r['score_alt']:.3f}  [{r['category']}]  {', '.join(r['hashtags'])}")

    print("\n=== SÓ YOUTUBE (∖ Alt) ===")
    for i, y in enumerate(only_yt_sorted, 1):
        s = float(y.get("score",0.0) or 0.0)
        v = float(y.get('signals',{}).get('yt_view_velocity',0.0))
        print(f"{i:02d}. {y.get('topic','?')}  | yt_score={s:.3f}  vph_norm={v:.1f}  [{y.get('category','general')}]")

    print("\n=== SÓ ALT (∖ YouTube) ===")
    for i, a in enumerate(only_alt_sorted, 1):
        s = float(a.get("score",0.0) or 0.0)
        sc = int(a.get('signals',{}).get('src_count',0))
        print(f"{i:02d}. {a.get('topic','?')}  | alt_score={s:.3f}  srcs={sc}  [{a.get('category','general')}]")

    # salva JSON
    os.makedirs(os.path.dirname(args.save), exist_ok=True)
    out = {
        "consensus": top_pairs,
        "only_youtube": only_yt_sorted,
        "only_alt": only_alt_sorted
    }
    with open(args.save, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] Salvo em: {args.save}")

if __name__ == "__main__":
    main()
