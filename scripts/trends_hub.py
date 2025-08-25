#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TrendsHub — YouTube Trending (BR) somente YouTube
-------------------------------------------------
Detecta tópicos quentes a partir de 'mostPopular' do YouTube, com foco em Gaming (cat=20).

Exemplos:
  # Usando .env com YT_API_KEY
  python3 scripts/trends_hub.py --geo BR --topk 12 --save output/trends.json

  # Passando a chave via flag e só Gaming (20)
  python3 scripts/trends_hub.py --yt-api-key SUA_CHAVE --yt-categories 20 --topk 12

  # Filtrar vídeos (mín 30k views/h, publicados nas últimas 72h, excluir shorts)
  python3 scripts/trends_hub.py --min-vph 30000 --max-hours 72 --exclude-shorts --topk 10
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import math
import os
import re
import statistics
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ──────────────────────────────────────────────────────────────────────────────
# .env
# ──────────────────────────────────────────────────────────────────────────────
def load_env(path: Optional[str]) -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        print("[WARN] python-dotenv não instalado — variáveis do .env não serão carregadas automaticamente.", file=sys.stderr)
        return
    if path:
        if not os.path.exists(path):
            print(f"[WARN] .env não encontrado em {path}. Seguindo sem .env.", file=sys.stderr)
        load_dotenv(dotenv_path=path)
    else:
        load_dotenv()  # tenta ./.env

# ──────────────────────────────────────────────────────────────────────────────
# Utils
# ──────────────────────────────────────────────────────────────────────────────

def now_iso(offset_hours: int = -3) -> str:
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=offset_hours)).isoformat(timespec="seconds")

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

def zscore(values: List[float]) -> List[float]:
    if not values:
        return []
    if all(v == values[0] for v in values):
        return [0.0]*len(values)
    m = statistics.mean(values)
    sd = statistics.pstdev(values) or 1e-9
    return [(v - m) / sd for v in values]

def logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))

def parse_iso8601_duration(dur: str) -> int:
    h = m = s = 0
    m_h = re.search(r'(\d+)H', dur)
    m_m = re.search(r'(\d+)M', dur)
    m_s = re.search(r'(\d+)S', dur)
    if m_h: h = int(m_h.group(1))
    if m_m: m = int(m_m.group(1))
    if m_s: s = int(m_s.group(1))
    return h*3600 + m*60 + s

# Heurística de categoria (fallback quando cat_id não resolve)
GAME_KEYWORDS = [
    "call of duty","black ops","bo7","gta 6","gta6","ea sports fc","fifa","fortnite",
    "minecraft","valorant","cs2","counter strike","street fighter","diablo","cyberpunk",
    "cod","ps5","xbox","steam","nintendo","switch","pokemon","elden ring","battlefield",
    "hollow knight","silksong","metal gear","mafia","brawl stars","eafc","efootball","roblox"
]
TECH_KEYWORDS = [
    "iphone","apple","android","samsung","galaxy","intel","amd","nvidia","windows",
    "macos","ios","instagram","tiktok","whatsapp","google","pix","openai","chatgpt",
    "meta","oculus","quest","ia","ai","elevenlabs"
]

YT_CAT_TO_BUCKET = {"20": "games", "28": "tech"}  # Gaming, Science & Tech

def infer_category(title: str, yt_cat_id: str) -> str:
    if yt_cat_id in YT_CAT_TO_BUCKET:
        return YT_CAT_TO_BUCKET[yt_cat_id]
    t = strip_accents(title)
    if any(k in t for k in GAME_KEYWORDS): return "games"
    if any(k in t for k in TECH_KEYWORDS): return "tech"
    return "general"

# Normalizador + palavras-chave úteis
NOISE_WORDS = set("""
official trailer teaser anuncio anuncio novo review live lives ao vivo shorts reveal gameplay reaction reactions
data date release livestream gamescom showcase direct state of play playstation xbox nintendo capcom ubisoft
""".split())

def normalize_title_for_grouping(title: str) -> str:
    s = slug_spaces(title)
    s = re.sub(r"\b(\d{4}|\d+p|4k|8k|hd|uhd)\b", " ", s)
    tokens = [t for t in s.split() if t not in NOISE_WORDS]
    return " ".join(tokens[:10])  # chave canônica curta

def extract_keywords(title: str, limit: int = 6) -> List[str]:
    s = slug_spaces(title)
    toks = [t for t in s.split() if t not in NOISE_WORDS and len(t) > 2]
    # prioriza termos com letras (evita números, fps etc.)
    toks = [t for t in toks if re.search(r"[a-z]", t)]
    seen = set()
    out = []
    for t in toks:
        if t in seen: continue
        seen.add(t)
        out.append(t)
        if len(out) >= limit: break
    return out

# ──────────────────────────────────────────────────────────────────────────────
# Estruturas
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Evidence:
    provider: str
    title: str
    url: Optional[str] = None
    extra: Dict[str, str] = field(default_factory=dict)

@dataclass
class Topic:
    topic: str
    aliases: List[str]
    signals: Dict[str, float]
    category: str
    geo: str
    evidence: List[Evidence] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    reason: str = ""
    ts_generated: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict:
        return {
            "topic": self.topic,
            "aliases": self.aliases,
            "signals": self.signals,
            "score": float(self.signals.get("_score", 0.0)),
            "geo": self.geo,
            "category": self.category,
            "keywords": self.keywords,
            "evidence": [dataclasses.asdict(e) for e in self.evidence],
            "reason": self.reason,
            "ts_generated": self.ts_generated
        }

# ──────────────────────────────────────────────────────────────────────────────
# YouTube: mostPopular
# ──────────────────────────────────────────────────────────────────────────────

def fetch_youtube_trending(
    api_key: str,
    region: str = "BR",
    categories: Tuple[str, ...] = ("20",),  # foca em Gaming por padrão
    max_results: int = 50,
    exclude_shorts: bool = False,
    min_views: int = 0,
    min_vph_raw: float = 0.0,
    max_hours: Optional[float] = None
) -> List[Tuple[str, float, Evidence, Dict]]:
    """
    Retorna: (topic_estimado, vph_norm_0_100, Evidence, meta={hours, duration_s, cat_id, vph_raw})
    """
    import httpx
    base = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet,statistics,contentDetails",
        "chart": "mostPopular",
        "regionCode": region,
        "maxResults": min(max_results, 50),
        "key": api_key
    }

    try:
        r = httpx.get(base, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[ERROR] Falha YouTube API: {e}", file=sys.stderr)
        return []

    def title_to_topic(title: str) -> str:
        s = re.sub(r"(?i)\b(official|trailer|teaser|anúncio|novo|review|ao vivo|live|shorts|reveal|gameplay|reaction|livestream)\b", "", title)
        s = re.sub(r"[\[\]\(\)\|•\-–—_:]+", " ", s)
        s = re.sub(r"\s{2,}", " ", s).strip()
        parts = s.split()
        return " ".join(parts[:8]) if parts else title

    items = data.get("items", [])
    if not items:
        return []

    rows = []
    velocities = []
    recencies = []
    for it in items:
        snippet = it.get("snippet", {})
        stats = it.get("statistics", {})
        details = it.get("contentDetails", {})
        cat_id = str(snippet.get("categoryId", "")).strip()
        if categories and cat_id not in set(categories):
            continue

        title = snippet.get("title", "")
        channel = snippet.get("channelTitle", "") or "?"
        published_at = snippet.get("publishedAt", "")
        views = float(stats.get("viewCount", 0.0) or 0.0)
        duration_s = parse_iso8601_duration(details.get("duration", "PT0S"))

        if exclude_shorts and duration_s <= 60:
            continue
        if views < min_views:
            continue

        try:
            pub = dt.datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            hours = max(1.0, (dt.datetime.now(dt.timezone.utc) - pub).total_seconds() / 3600.0)
        except Exception:
            hours = 24.0
        if max_hours is not None and hours > max_hours:
            continue

        vph = views / hours if hours > 0 else views
        if vph < min_vph_raw:
            continue

        topic = title_to_topic(title)
        ev = Evidence(
            provider="youtube",
            title=title,
            url=f"https://www.youtube.com/watch?v={it.get('id','')}",
            extra={
                "channel": channel,
                "views": str(int(views)),
                "vph_raw": f"{vph:.1f}",
                "hours": f"{hours:.1f}",
                "duration_s": str(int(duration_s)),
                "cat_id": cat_id
            }
        )

        velocities.append(vph)
        recencies.append(-hours)  # mais recente = maior
        rows.append((topic, vph, ev, {"hours": hours, "duration_s": duration_s, "cat_id": cat_id, "vph_raw": vph}))

    if not rows:
        return []

    vph_norm = [max(0.0, min(100.0, 50.0 + 20.0*z)) for z in zscore(velocities)]
    recency_norm = [max(0.0, min(100.0, 50.0 + 20.0*z)) for z in zscore(recencies)]

    out = []
    for (topic, _vph, ev, meta), v_norm, r_norm in zip(rows, vph_norm, recency_norm):
        ev.extra["vph_norm"] = f"{v_norm:.1f}"
        ev.extra["recency_norm"] = f"{r_norm:.1f}"
        out.append((topic, v_norm, ev, meta))
    return out

# ──────────────────────────────────────────────────────────────────────────────
# Unificação, dedup e scoring
# ──────────────────────────────────────────────────────────────────────────────

def canonicalize_youtube(
    topics_with_scores: List[Tuple[str, float, Evidence, Dict]],
    geo: str,
    merge_threshold: int = 84
) -> List[Topic]:
    """
    Une títulos parecidos em 1 tópico canônico.
    """
    try:
        from rapidfuzz import process, fuzz
        use_fuzz = True
    except Exception:
        print("[WARN] rapidfuzz não instalado (pip install rapidfuzz). Dedup simples ativado.", file=sys.stderr)
        use_fuzz = False

    # bucket por chave canônica baseada em título limpo
    buckets: Dict[str, List[Tuple[str, float, Evidence, Dict]]] = {}
    for name, score, ev, meta in topics_with_scores:
        key = normalize_title_for_grouping(name)
        buckets.setdefault(key, []).append((name, score, ev, meta))

    # mescla buckets similares
    merged: Dict[str, List[Tuple[str, float, Evidence, Dict]]] = {}
    if use_fuzz:
        keys = list(buckets.keys())
        used = set()
        for k in keys:
            if k in used: continue
            matches = process.extract(k, keys, scorer=fuzz.token_sort_ratio, limit=10)
            group = []
            for other, sim, _ in matches:
                if other in used: continue
                if sim >= merge_threshold:
                    group.extend(buckets[other])
                    used.add(other)
            merged[k] = group
    else:
        merged = buckets

    topics: List[Topic] = []
    for k, group in merged.items():
        names = [n for n, _, _, _ in group]
        canonical = max(set(names), key=lambda x: (names.count(x), len(x)))
        aliases = sorted(set(n for n in names if n != canonical))
        evidences = [ev for _, _, ev, _ in group]

        # sinais agregados
        yt_vph = max([s for _, s, _, _ in group] or [0.0])  # 0..100
        try:
            rec_list = [float(ev.extra.get("recency_norm", "0")) for _, _, ev, _ in group]
            yt_rec = sum(rec_list)/len(rec_list) if rec_list else 0.0
        except Exception:
            yt_rec = 0.0

        top_item = max(group, key=lambda t: t[1])
        cat = infer_category(top_item[0], str(top_item[3].get("cat_id","")))
        kws = extract_keywords(canonical)

        t = Topic(
            topic=canonical,
            aliases=aliases,
            signals={
                "yt_view_velocity": float(yt_vph),
                "yt_recency": float(yt_rec),
                "_score": 0.0,
            },
            category=cat,
            geo=geo,
            evidence=evidences,
            keywords=kws
        )
        topics.append(t)
    return topics

def score_topics_youtube(topics: List[Topic], w_v: float = 0.65, w_r: float = 0.35) -> List[Topic]:
    """
    Score final (0..1) usando vph + recência.
    """
    if not topics: return topics
    v_list = [t.signals.get("yt_view_velocity", 0.0) for t in topics]
    r_list = [t.signals.get("yt_recency", 0.0) for t in topics]
    v_z = zscore(v_list)
    r_z = zscore(r_list)

    for t, zv, zr in zip(topics, v_z, r_z):
        lin = w_v*zv + w_r*zr
        t.signals["_score"] = float(logistic(lin))
        t.reason = f"score(logistic): vph_z={zv:.2f}*{w_v} + rec_z={zr:.2f}*{w_r}"

    topics.sort(key=lambda x: x.signals.get("_score", 0.0), reverse=True)
    return topics

# ──────────────────────────────────────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────────────────────────────────────

def collect_trends_youtube(
    geo: str,
    yt_api_key: str,
    yt_categories: Tuple[str, ...],
    max_results: int,
    exclude_shorts: bool,
    min_views: int,
    min_vph_raw: float,
    max_hours: Optional[float],
    merge_threshold: int
) -> List[Topic]:
    raw = fetch_youtube_trending(
        api_key=yt_api_key,
        region=geo,
        categories=yt_categories,
        max_results=max_results,
        exclude_shorts=exclude_shorts,
        min_views=min_views,
        min_vph_raw=min_vph_raw,
        max_hours=max_hours
    )
    topics = canonicalize_youtube(raw, geo=geo, merge_threshold=merge_threshold)
    topics = score_topics_youtube(topics)
    return topics

def main():
    parser = argparse.ArgumentParser(description="TrendsHub — YouTube Trending (somente YouTube)")
    parser.add_argument("--env", type=str, default="", help="Caminho do .env (opcional)")
    parser.add_argument("--yt-api-key", type=str, default="", help="YouTube Data API v3 (override)")
    parser.add_argument("--geo", type=str, default="BR", help="País/Região (regionCode), ex.: BR")
    parser.add_argument("--yt-categories", type=str, default="20", help="IDs de categorias (csv). Gaming=20, Tech=28")
    parser.add_argument("--max-results", type=int, default=50, help="Máximo de vídeos a considerar (<=50)")
    parser.add_argument("--exclude-shorts", action="store_true", help="Excluir vídeos com duração <= 60s")
    parser.add_argument("--min-views", type=int, default=0, help="Filtrar vídeos com views totais abaixo deste valor")
    parser.add_argument("--min-vph", type=float, default=0.0, help="Filtrar vídeos com views/h (bruto) abaixo deste valor")
    parser.add_argument("--max-hours", type=float, default=None, help="Filtrar vídeos publicados há mais de X horas")
    parser.add_argument("--merge-threshold", type=int, default=84, help="Similaridade (0-100) para mesclar tópicos")
    parser.add_argument("--topk", type=int, default=10, help="Quantidade de tópicos na saída")
    parser.add_argument("--min-score", type=float, default=0.0, help="Filtrar tópicos com score < min-score")
    parser.add_argument("--save", type=str, default="", help="Salvar JSON em caminho indicado")
    args = parser.parse_args()

    load_env(args.env if args.env else None)
    yt_api_key = args.yt_api_key or os.getenv("YT_API_KEY", "")
    if not yt_api_key:
        print("[ERROR] YT_API_KEY ausente. Defina no .env ou passe via --yt-api-key.", file=sys.stderr)
        sys.exit(1)

    yt_categories = tuple([c.strip() for c in (args.yt_categories or "").split(",") if c.strip()])

    topics = collect_trends_youtube(
        geo=args.geo,
        yt_api_key=yt_api_key,
        yt_categories=yt_categories,
        max_results=max(1, min(args.max_results, 50)),
        exclude_shorts=args.exclude_shorts,
        min_views=max(0, args.min_views),
        min_vph_raw=max(0.0, args.min_vph),
        max_hours=args.max_hours,
        merge_threshold=max(0, min(args.merge_threshold, 100))
    )

    topics = [t for t in topics if t.signals.get("_score", 0.0) >= args.min_score]
    topk = topics[: args.topk]

    print("\n=== TOP TÓPICOS (YouTube) ===")
    for i, t in enumerate(topk, 1):
        s = t.signals.get("_score", 0.0)
        v = t.signals.get("yt_view_velocity", 0.0)
        r = t.signals.get("yt_recency", 0.0)
        print(f"{i:02d}. {t.topic}  | score={s:.3f}  yt_vph={v:.1f}  yt_recency={r:.1f}  [{t.category}]")

    if args.save:
        out = [t.to_dict() for t in topk]
        os.makedirs(os.path.dirname(args.save), exist_ok=True)
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\n[OK] Salvo em: {args.save}")

if __name__ == "__main__":
    main()
