#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AltTrendsHub — agregador de tendências (sem YouTube/Google Trends)
------------------------------------------------------------------
Fontes:
 - Reddit (hot + top/day) → r/gaming, r/games, r/technology, r/pcgaming (+ extras)
 - Wikimedia Pageviews (pt.wikipedia) → páginas do dia
 - Hacker News (front page via Algolia API)
 - Google News RSS (opcional, sem chave) → busca por seeds em pt-BR (--use-gn)
 - NewsAPI (opcional, requer NEWSAPI_KEY) → 'everything' em pt (--use-newsapi)

Objetivo:
 - Detectar tópicos que aparecem em MAIS DE UMA fonte (consenso cross-plataforma)
 - Produzir JSON com tópicos canônicos e score 0..1

Exemplos:
  # Sem NewsAPI, com Google News RSS e Wikipedia estrita, consenso mínimo 2
  python3 scripts/alt_trends_hub.py --use-gn --wiki-strict --min-srcs 2 --topk 15 --save output/alt_trends.json

  # Com NewsAPI + Google News (melhor BR/pt)
  python3 scripts/alt_trends_hub.py --use-gn --use-newsapi --hours-back 96 --min-srcs 2 --wiki-strict --topk 20 --save output/alt_trends.json

  # Só games
  python3 scripts/alt_trends_hub.py --use-gn --domain games --min-srcs 2 --topk 12
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
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ──────────────────────────────────────────────────────────────────────────────
# .env
# ──────────────────────────────────────────────────────────────────────────────
def load_env(path: Optional[str]) -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        print("[WARN] python-dotenv não instalado — .env não será carregado automaticamente.", file=sys.stderr)
        return
    if path and not os.path.exists(path):
        print(f"[WARN] .env não encontrado em {path}. Seguindo sem .env.", file=sys.stderr)
    load_dotenv(dotenv_path=path) if path else load_dotenv()

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

def to_hours_since(ts: float) -> float:
    """ts: epoch seconds (UTC)"""
    try:
        now = dt.datetime.now(dt.timezone.utc).timestamp()
        return max(0.0, (now - ts) / 3600.0)
    except Exception:
        return 9999.0

# ──────────────────────────────────────────────────────────────────────────────
# Seeds / domínio
# ──────────────────────────────────────────────────────────────────────────────
SEEDS_GAMES = [
    "hollow knight", "silksong", "call of duty", "black ops", "bo7", "gta 6", "gta6", "fortnite",
    "minecraft", "valorant", "cs2", "counter strike", "street fighter", "diablo", "cyberpunk",
    "ps5", "playstation 5", "xbox", "steam", "nintendo switch", "pokemon", "elden ring", "battlefield",
    "metal gear", "mafia", "brawl stars", "roblox", "eafc", "efootball"
]
SEEDS_TECH = [
    "iphone", "apple", "android", "samsung", "galaxy", "intel", "amd", "nvidia", "windows",
    "macos", "ios", "instagram", "tiktok", "whatsapp", "google", "pix", "openai", "chatgpt",
    "meta", "oculus", "quest", "inteligencia artificial", "ia", "ai"
]
SEEDS_ALL = SEEDS_GAMES + SEEDS_TECH

EXTRA_REDDIT_SUBS = [
    "NintendoSwitch", "PS5", "xbox", "Steam", "pcmasterrace", "gamingleaksandrumours"
]

def infer_bucket(text: str) -> str:
    t = strip_accents(text)
    if any(k in t for k in SEEDS_GAMES): return "games"
    if any(k in t for k in SEEDS_TECH): return "tech"
    return "general"

# Canonização / bans
ALIAS_CANON = {
    "ia": "inteligencia artificial",
    "ai": "inteligencia artificial",
    "ps5": "playstation 5",
    "xbox series x": "xbox series",
    "xbox series s": "xbox series",
}
BAN_GENERIC = {"ia", "ai", "ios"}  # desligue com --allow-generic

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
# Providers
# ──────────────────────────────────────────────────────────────────────────────
def fetch_reddit(hours_back: int = 72, limit: int = 100) -> List[Evidence]:
    import httpx
    subs = ["gaming", "games", "technology", "pcgaming"] + EXTRA_REDDIT_SUBS
    out: List[Evidence] = []
    headers = {"User-Agent": "alt-trends-bot/0.3 by zeroatech"}

    # HOT
    try:
        url = f"https://www.reddit.com/r/{'+'.join(subs)}/hot.json"
        r = httpx.get(url, headers=headers, params={"limit": min(limit, 100)}, timeout=20)
        r.raise_for_status()
        data = r.json()
        for ch in data.get("data", {}).get("children", []):
            p = ch.get("data", {})
            title = p.get("title", "")
            ups = float(p.get("ups", 0) or 0)
            created = float(p.get("created_utc", 0) or 0)*1.0
            hours = to_hours_since(created)
            if hours <= hours_back:
                out.append(Evidence("reddit", title, "https://www.reddit.com"+p.get("permalink",""),
                                    {"score": str(int(ups)), "hours": f"{hours:.1f}", "mode":"hot"}))
    except Exception as e:
        print(f"[WARN] Reddit hot falhou: {e}", file=sys.stderr)

    # TOP (dia) — cobre coisas que esquentaram algumas horas antes
    try:
        for sub in subs:
            url = f"https://www.reddit.com/r/{sub}/top.json"
            r = httpx.get(url, headers=headers, params={"t":"day","limit":50}, timeout=20)
            r.raise_for_status()
            data = r.json()
            for ch in data.get("data", {}).get("children", []):
                p = ch.get("data", {})
                title = p.get("title", "")
                ups = float(p.get("ups", 0) or 0)
                created = float(p.get("created_utc", 0) or 0)*1.0
                hours = to_hours_since(created)
                if hours <= hours_back:
                    out.append(Evidence("reddit", title, "https://www.reddit.com"+p.get("permalink",""),
                                        {"score": str(int(ups)), "hours": f"{hours:.1f}", "mode":"top"}))
    except Exception as e:
        print(f"[WARN] Reddit top/day falhou: {e}", file=sys.stderr)

    return out

def fetch_wikipedia_top(day_offset: int = 1, limit: int = 200, strict: bool = False) -> List[Evidence]:
    import httpx
    date = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=max(1, day_offset)))
    y, m, d = date.strftime("%Y"), date.strftime("%m"), date.strftime("%d")
    url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/pt.wikipedia/all-access/{y}/{m}/{d}"
    out = []
    try:
        r = httpx.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        items = (data.get("items") or [{}])[0].get("articles", [])
        for it in items[:limit]:
            title = it.get("article","").replace("_"," ")
            title_norm = strip_accents(title)
            if strict and not any(s in title_norm for s in SEEDS_ALL):
                continue
            views = float(it.get("views",0) or 0)
            out.append(Evidence("wikipedia", title, "https://pt.wikipedia.org/wiki/"+it.get("article",""),
                                {"views": str(int(views)), "hours": "12.0"}))
    except Exception as e:
        print(f"[WARN] Wikipedia falhou: {e}", file=sys.stderr)
    return out

def fetch_hackernews(limit: int = 30) -> List[Evidence]:
    import httpx, dateutil.parser
    url = "https://hn.algolia.com/api/v1/search?tags=front_page"
    out = []
    try:
        r = httpx.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        for h in (data.get("hits") or [])[:limit]:
            title = h.get("title","") or ""
            points = float(h.get("points",0) or 0)
            created = h.get("created_at")
            try:
                dt_ = dateutil.parser.isoparse(created)
                hours = to_hours_since(dt_.timestamp())
            except Exception:
                hours = 24.0
            out.append(Evidence("hackernews", title,
                                h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                                {"points": str(int(points)), "hours": f"{hours:.1f}"}))
    except Exception as e:
        print(f"[WARN] HN falhou: {e}", file=sys.stderr)
    return out

def fetch_newsapi(seeds: List[str], hours_back: int = 48, per_seed: int = 6, language: str = "pt") -> List[Evidence]:
    import httpx
    key = os.getenv("NEWSAPI_KEY","")
    if not key:
        return []
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = "https://newsapi.org/v2/everything"
    out = []
    for seed in seeds:
        params = {
            "qInTitle": seed,
            "language": language,
            "from": since,
            "sortBy": "publishedAt",
            "pageSize": per_seed,
            "apiKey": key,
            "searchIn": "title,description"
        }
        try:
            r = httpx.get(url, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
            for art in data.get("articles", []):
                title = art.get("title","") or ""
                pub = art.get("publishedAt")
                try:
                    pub_ts = dt.datetime.fromisoformat(pub.replace("Z","+00:00")).timestamp()
                    hours = to_hours_since(pub_ts)
                except Exception:
                    hours = 24.0
                out.append(Evidence("newsapi", title, art.get("url",""),
                                    {"source": (art.get("source") or {}).get("name",""), "hours": f"{hours:.1f}"}))
        except Exception as e:
            print(f"[WARN] NewsAPI falhou para seed '{seed}': {e}", file=sys.stderr)
            continue
    return out

def fetch_google_news_rss(seeds: List[str], hours_back: int = 48, per_seed: int = 8) -> List[Evidence]:
    """Google News RSS (sem chave), em pt-BR, por sementes."""
    import httpx
    out: List[Evidence] = []
    base = "https://news.google.com/rss/search"
    for seed in seeds:
        params = {
            "q": f"\"{seed}\"",
            "hl": "pt-BR",
            "gl": "BR",
            "ceid": "BR:pt-419"
        }
        try:
            r = httpx.get(base, params=params, timeout=20)
            r.raise_for_status()
            root = ET.fromstring(r.text)
            items = root.findall(".//item")[:per_seed]
            for it in items:
                title = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                pub = it.findtext("pubDate")
                try:
                    dt_ = parsedate_to_datetime(pub)
                    if dt_.tzinfo is None:
                        dt_ = dt_.replace(tzinfo=dt.timezone.utc)
                    hours = to_hours_since(dt_.timestamp())
                except Exception:
                    hours = 24.0
                if hours <= hours_back:
                    out.append(Evidence("googlenews", title, link, {"hours": f"{hours:.1f}"}))
        except Exception as e:
            print(f"[WARN] Google News RSS falhou para seed '{seed}': {e}", file=sys.stderr)
            continue
    return out

# ──────────────────────────────────────────────────────────────────────────────
# Normalização / keywords
# ──────────────────────────────────────────────────────────────────────────────
NOISE = set("official trailer teaser anuncio novo review live ao vivo reaction reactions livestream".split())

def normalize_for_grouping(title: str) -> str:
    s = slug_spaces(title)
    s = re.sub(r"\b(\d{4}|\d+p|4k|8k|hd|uhd)\b", " ", s)
    toks = [t for t in s.split() if t not in NOISE]
    key = " ".join(toks[:10]).strip()
    return ALIAS_CANON.get(key, key)

def extract_keywords(title: str, limit: int = 5) -> List[str]:
    s = slug_spaces(title)
    toks = [t for t in s.split() if t not in NOISE and len(t) > 2 and re.search(r"[a-z]", t)]
    seen, out = set(), []
    for t in toks:
        if t in seen: continue
        seen.add(t); out.append(t)
        if len(out) >= limit: break
    return out

def seed_for_title(title: str, domain: str) -> Optional[str]:
    t = slug_spaces(title)
    seeds = SEEDS_GAMES if domain == "games" else SEEDS_TECH if domain == "tech" else SEEDS_ALL
    for s in seeds:
        if s in t:
            return ALIAS_CANON.get(s, s)
    return None

def is_generic_topic(name: str) -> bool:
    key = slug_spaces(name)
    if key in BAN_GENERIC: return True
    if len(key.split()) == 1 and len(key) <= 3:
        return True
    return False

# ──────────────────────────────────────────────────────────────────────────────
# Unificação e Scoring
# ──────────────────────────────────────────────────────────────────────────────
def unify_and_score(
    evidences: List[Evidence],
    domain: str,
    geo: str = "BR",
    merge_threshold: int = 85,
    min_srcs: int = 2,
    allow_generic: bool = False,
    provider_weights: Optional[Dict[str, float]] = None
) -> List[Topic]:
    try:
        from rapidfuzz import process, fuzz
        use_fuzz = True
    except Exception:
        print("[WARN] rapidfuzz não instalado — dedup simples.", file=sys.stderr)
        use_fuzz = False

    if provider_weights is None:
        provider_weights = {
            "reddit": 1.0,
            "hackernews": 1.1,
            "wikipedia": 0.6,
            "googlenews": 0.9,
            "newsapi": 0.9
        }

    # 1) agrupa por chave canônica (seed preferida; senão, título normalizado)
    buckets: Dict[str, List[Evidence]] = {}
    name_for_key: Dict[str, str] = {}

    for ev in evidences:
        # filtro de domínio
        if domain in ("games","tech","general"):
            cat_guess = infer_bucket(ev.title)
            if domain != "general" and cat_guess != domain:
                continue

        s = seed_for_title(ev.title, domain)
        key = s if s else normalize_for_grouping(ev.title)
        if not allow_generic and is_generic_topic(key):
            continue

        buckets.setdefault(key, []).append(ev)
        if key not in name_for_key:
            name_for_key[key] = s if s else ev.title

    # 2) mescla chaves parecidas (fuzzy) — só para chaves não-semente
    if use_fuzz:
        keys = list(buckets.keys())
        used = set()
        merged: Dict[str, List[Evidence]] = {}
        for k in keys:
            if k in used: continue
            if k in SEEDS_ALL or k in ALIAS_CANON.values():
                merged[k] = buckets[k]; used.add(k); continue
            matches = process.extract(k, keys, scorer=fuzz.token_sort_ratio, limit=10)
            group = []
            for other, sim, _ in matches:
                if other in used: continue
                if (other in SEEDS_ALL or other in ALIAS_CANON.values()) and other != k:
                    continue
                if sim >= merge_threshold:
                    group.extend(buckets[other]); used.add(other)
            merged[k] = group
        buckets = merged

    # 3) calcula sinais por tópico
    topics: List[Topic] = []
    for key, evs in buckets.items():
        srcs = {e.provider for e in evs}
        if len(srcs) < min_srcs:
            continue

        title = name_for_key.get(key, key).title()
        aliases = sorted({e.title for e in evs if e.title != title})

        raw_scores = []
        rec_hours = []
        for e in evs:
            w = float((provider_weights or {}).get(e.provider, 1.0))
            if e.provider == "reddit":
                raw_scores.append(w * float(e.extra.get("score","0")))
                rec_hours.append(float(e.extra.get("hours","24")))
            elif e.provider == "hackernews":
                raw_scores.append(w * float(e.extra.get("points","0")))
                rec_hours.append(float(e.extra.get("hours","24")))
            elif e.provider == "wikipedia":
                raw_scores.append(w * float(e.extra.get("views","0")))
                rec_hours.append(float(e.extra.get("hours","12")))
            elif e.provider in ("newsapi", "googlenews"):
                raw_scores.append(w * 1.0)  # presença
                rec_hours.append(float(e.extra.get("hours","24")))
            else:
                rec_hours.append(24.0)

        pop_norm = 0.0
        if raw_scores:
            zs = zscore(raw_scores)
            pop_norm = max(0.0, min(100.0, 50.0 + 20.0*(zs[0] if len(zs)==1 else max(zs))))

        if rec_hours:
            rec_z = zscore([-h for h in rec_hours])
            rec_norm = max(0.0, min(100.0, 50.0 + 20.0*(sum(rec_z)/len(rec_z))))
        else:
            rec_norm = 0.0

        signals = {
            "src_count": float(len(srcs)),
            "news_count": float(len(evs)),
            "popularity": pop_norm,
            "recency": rec_norm
        }

        cat = infer_bucket(title)
        kws = extract_keywords(title)
        topics.append(Topic(
            topic=title,
            aliases=aliases,
            signals=signals,
            category=cat,
            geo="BR",
            evidence=evs,
            keywords=kws
        ))

    # 4) score final (logístico) — pesos priorizando consenso e popularidade
    if not topics:
        return topics

    src_list = [t.signals["src_count"] for t in topics]
    news_list = [t.signals["news_count"] for t in topics]
    pop_list = [t.signals["popularity"] for t in topics]
    rec_list = [t.signals["recency"] for t in topics]

    z_src, z_news = zscore(src_list), zscore(news_list)
    z_pop, z_rec  = zscore(pop_list), zscore(rec_list)

    WSRC, WNEWS, WPOP, WREC = 0.40, 0.15, 0.30, 0.15
    for t, a,b,c,d in zip(topics, z_src, z_news, z_pop, z_rec):
        lin = WSRC*a + WNEWS*b + WPOP*c + WREC*d
        t.signals["_score"] = float(logistic(lin))
        t.reason = f"σ({WSRC}*src + {WNEWS}*news + {WPOP}*pop + {WREC}*rec)"

    topics.sort(key=lambda x: x.signals.get("_score",0.0), reverse=True)
    return topics

# ──────────────────────────────────────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="AltTrendsHub — tendências multi-fontes (sem YouTube/GoogleTrends)")
    parser.add_argument("--env", type=str, default="", help="Caminho do .env (opcional)")
    parser.add_argument("--use-newsapi", action="store_true", help="Habilita NewsAPI (requer NEWSAPI_KEY)")
    parser.add_argument("--use-gn", action="store_true", help="Habilita Google News RSS (sem chave)")
    parser.add_argument("--hours-back", type=int, default=72, help="Janela de tempo para Reddit/News (h)")
    parser.add_argument("--topk", type=int, default=15, help="Quantidade de tópicos na saída")
    parser.add_argument("--merge-threshold", type=int, default=85, help="Similaridade p/ mesclar (0-100)")
    parser.add_argument("--domain", type=str, default="all", choices=["all","games","tech","general"], help="Filtra por domínio")
    parser.add_argument("--min-srcs", type=int, default=None, help="Mínimo de fontes distintas por tópico (default: 2 se notícias ativas; senão 1)")
    parser.add_argument("--allow-generic", action="store_true", help="Permite tópicos genéricos curtos (ex.: 'IA', 'AI')")
    parser.add_argument("--wiki-strict", action="store_true", help="Mantém só páginas da Wikipedia que batem com seeds (reduz esporte/variedades)")
    parser.add_argument("--save", type=str, default="", help="Salvar JSON em caminho indicado")
    args = parser.parse_args()

    load_env(args.env if args.env else None)

    evidences: List[Evidence] = []
    evidences += fetch_reddit(hours_back=args.hours_back, limit=100)
    evidences += fetch_wikipedia_top(day_offset=1, limit=200, strict=args.wiki_strict)
    evidences += fetch_hackernews(limit=30)

    # semente por domínio
    seeds = SEEDS_GAMES if args.domain=="games" else SEEDS_TECH if args.domain=="tech" else SEEDS_ALL

    if args.use_gn:
        evidences += fetch_google_news_rss(seeds=seeds, hours_back=min(args.hours_back, 96), per_seed=8)
    if args.use_newsapi:
        evidences += fetch_newsapi(seeds=seeds, hours_back=min(args.hours_back, 72), per_seed=6, language="pt")

    # min-srcs padrão
    if args.min_srcs is None:
        min_srcs = 2 if (args.use_gn or args.use_newsapi) else 1
    else:
        min_srcs = args.min_srcs

    topics = unify_and_score(
        evidences,
        domain=args.domain,
        merge_threshold=args.merge_threshold,
        min_srcs=min_srcs,
        allow_generic=args.allow_generic
    )

    topk = topics[: args.topk]
    print("\n=== ALT TRENDS (multi-fontes) ===")
    for i, t in enumerate(topk, 1):
        sig = t.signals
        print(f"{i:02d}. {t.topic} | score={sig.get('_score',0.0):.3f}  srcs={int(sig['src_count'])}  news={int(sig['news_count'])}  pop={sig['popularity']:.1f}  rec={sig['recency']:.1f}  [{t.category}]")

    if args.save:
        out = [t.to_dict() for t in topk]
        os.makedirs(os.path.dirname(args.save), exist_ok=True)
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\n[OK] Salvo em: {args.save}")

if __name__ == "__main__":
    main()
