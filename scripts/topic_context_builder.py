#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re, os, json, time, html
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlencode, urlparse

OUT = Path("output"); OUT.mkdir(exist_ok=True)
BUNDLE_PATH = OUT/"context_bundle.json"
CTX_TXT_PATH = OUT/"contexto_expandido.txt"
SOURCES_PATH = OUT/"fontes_usadas.json"

UA = "Mozilla/5.0 (Linux; Android 14) ZeroATech/3.0 Safari"
HDRS = {"User-Agent": UA, "Accept-Language":"pt-BR,pt;q=0.9,en-US;q=0.7"}
TIMEOUT = 18

# 1) fontes diretas (RSS)
FEEDS = {
  "flowgames.gg": "https://flowgames.gg/feed/",
  "adrenaline.com.br": "https://adrenaline.com.br/feed/",
  "theenemy.com.br": "https://www.theenemy.com.br/rss",
  "meups.com.br": "https://meups.com.br/feed/",
  "voxel.com.br": "https://www.voxel.com.br/rss",
  "br.ign.com": "https://br.ign.com/rss.xml",
  "eurogamer.pt": "https://www.eurogamer.pt/?output=rss",
  "techtudo.com.br/games": "https://www.techtudo.com.br/feeds/rss/games.xml",
}

# 2) adapters (mesma ideia do que você já usa)
ADAPTERS = {
  "flowgames.gg": {"selectors": [".entry-content",".single__content","article"], "min_len": 220},
  "adrenaline.com.br": {"selectors": ["article .content",".post-content",".news-content","article"], "min_len": 220},
  "theenemy.com.br": {"selectors": ["article .article-body",".article-body",".content"], "min_len": 220},
  "meups.com.br": {"selectors": ["article .entry-content",".entry-content",".single-content"], "min_len": 220},
  "voxel.com.br": {"selectors": ["article .content","article .materia-conteudo",".materia-conteudo"], "min_len": 220},
  "br.ign.com": {"selectors": ["article .content",".article-content",".content-body"], "min_len": 220},
  "eurogamer.pt": {"selectors": ["article .article-body","article .entry-content",".entry-content"], "min_len": 220},
  "techtudo.com.br": {"selectors": ["article .content-text",".content-text",".content"], "min_len": 220},
}

# 3) heurísticas (reaproveite as suas se preferir)
RE_PERCENT = re.compile(r"(\d{1,3})\s?%")
RE_MONEY   = re.compile(r"R\$\s?\d{1,3}(?:\.\d{3})*,\d{2}", re.I)
RE_PLATFORM= re.compile(r"\b(steam|epic|gog|psn|playstation|xbox|nintendo|switch|prime gaming|ea play)\b", re.I)
EDITORIAL_HINTS = {
  "lançamento": ("lançamento","estreia","chegou","release","saiu","data de lançamento"),
  "update": ("update","atualização","patch","temporada","season","dlc"),
  "recorde": ("recorde","pico","mais vendidos","topo"),
  "polêmica": ("polêmica","review bomb","críticas","bugs","otimização"),
  "desconto": ("promo","promoção","desconto","grátis","free weekend","preço"),
}

def _now_utc():
    return datetime.now(timezone.utc)

def _domain(u:str)->str:
    try:
        d = urlparse(u).netloc.lower()
        return d.replace("www.","")
    except: return ""

def _get(url:str)->Optional[requests.Response]:
    try:
        r = requests.get(url, headers=HDRS, timeout=TIMEOUT)
        if r and r.text: return r
    except: pass
    return None

def _strip_boilerplate(soup:BeautifulSoup):
    kill = re.compile(r"(newsletter|related|share|social|breadcrumbs|advert|ads|sidebar|subscribe|tag-list)", re.I)
    for tag in soup.find_all(["aside","script","style","noscript","iframe","footer","header","nav"]):
        tag.decompose()
    for div in soup.find_all(attrs={"class": kill}):
        div.decompose()

def _pull_text(soup:BeautifulSoup, selectors:List[str], min_len:int)->str:
    _strip_boilerplate(soup)
    node = None
    for sel in selectors:
        node = soup.select_one(sel)
        if node: break
    if node is None:
        node = soup.find("article") or soup
    parts=[]
    for el in node.find_all(["p","li"]):
        t = el.get_text(" ", strip=True)
        if not t: continue
        if re.search(r"(leia mais|assine|newsletter|compartilhe)", t, re.I): 
            continue
        if len(t) >= 40: parts.append(t)
        if sum(len(x) for x in parts) > 24000: break
    txt = "\n".join(parts).strip()
    return txt if len(txt) >= min_len else ""

def _extract_body(url:str)->str:
    host = _domain(url)
    r = _get(url)
    if not r: return ""
    soup = BeautifulSoup(r.text, "html.parser")
    cfg = ADAPTERS.get(host, {"selectors":["article",".content",".entry-content"],"min_len":200})
    txt = _pull_text(soup, cfg["selectors"], cfg["min_len"])
    if txt: return txt
    if not url.rstrip("/").endswith("/amp"):
        amp = url.rstrip("/")+"/amp"
        r2 = _get(amp)
        if r2:
            s2 = BeautifulSoup(r2.text, "html.parser")
            txt2 = _pull_text(s2, cfg["selectors"], 160)
            if txt2: return txt2
    return ""

def query_variants(topic:str)->List[str]:
    # simples: PT/EN, remove stopwords curtas, tenta aspas se parecer nome
    base = topic.strip()
    toks = [t for t in re.split(r"\s+", base) if len(t)>1]
    q1 = " ".join(toks)
    qs = {q1}
    # heurísticas
    if ":" in base or any(w in base.lower() for w in ["black ops","call of duty","dlc","update","temporada"]):
        qs.add(f"\"{base}\"")
    # versões curtas (marca + palavra-chave forte)
    for kw in ["preço","lançamento","data","update","desconto","grátis","polêmica","recorde"]:
        qs.add(f"{toks[0]} {kw}")
    return list(qs)

def google_news_rss(query:str)->str:
    # janela 3 dias; pt-BR; BR
    q = urlencode({"q": f"{query} when:3d"})
    return f"https://news.google.com/rss/search?{q}&hl=pt-BR&gl=BR&ceid=BR:pt-419"

def collect_from_feeds(qtokens:List[str], max_per_feed:int=6)->List[Dict[str,Any]]:
    import feedparser
    out=[]
    cutoff = _now_utc() - timedelta(days=3)
    for host, url in FEEDS.items():
        try:
            d = feedparser.parse(url)
            hits=[]
            for e in d.entries:
                title = (getattr(e,"title","") or "").strip()
                link  = (getattr(e,"link","") or "").strip()
                if not title or not link: continue
                txt = (title+" "+(getattr(e,"summary","") or "")).lower()
                if not any(t.lower() in txt for t in qtokens): 
                    continue
                # data
                pub = getattr(e,"published_parsed",None) or getattr(e,"updated_parsed",None)
                pub_dt = datetime(*pub[:6], tzinfo=timezone.utc) if pub else None
                if pub_dt and pub_dt < cutoff: 
                    continue
                hits.append({
                    "title": title, "link": link, "source": host,
                    "published_iso": pub_dt.isoformat() if pub_dt else "",
                })
                if len(hits)>=max_per_feed: break
            out.extend(hits)
        except: 
            continue
    return out

def collect_from_google_news(qvariants:List[str], cap:int=12)->List[Dict[str,Any]]:
    import feedparser
    out=[]
    for q in qvariants[:4]:
        rss = google_news_rss(q)
        try:
            d = feedparser.parse(rss)
            for e in d.entries[:cap]:
                out.append({
                    "title": (getattr(e,"title","") or "").strip(),
                    "link": (getattr(e,"link","") or "").strip(),
                    "source": _domain(getattr(e,"link","") or ""),
                    "published_iso": datetime(*e.published_parsed[:6], tzinfo=timezone.utc).isoformat()
                       if getattr(e,"published_parsed",None) else "",
                })
        except: 
            continue
    return out

def dedupe_keep_latest(items:List[Dict[str,Any]])->List[Dict[str,Any]]:
    seen=set(); out=[]
    items.sort(key=lambda x: x.get("published_iso",""), reverse=True)
    for it in items:
        url = it.get("link","").split("?")[0]
        key = (it.get("title","").lower().strip(), _domain(url))
        if key in seen: 
            continue
        seen.add(key); out.append(it)
    return out

def editorial_tags(text:str)->List[str]:
    low = text.lower()
    tags=set()
    for tag, keys in EDITORIAL_HINTS.items():
        if any(k in low for k in keys): tags.add(tag)
    return list(tags)

def extract_promos(text:str)->List[Dict[str,str]]:
    out=[]
    for line in [l.strip() for l in text.splitlines() if l.strip()]:
        pct = RE_PERCENT.search(line)
        mny = RE_MONEY.search(line)
        if not (pct or mny): continue
        plat=""
        mp = RE_PLATFORM.search(line)
        if mp: plat = mp.group(0).title().replace("Psn","PSN").replace("Playstation","PlayStation")
        name=""
        mname = re.search(r"([A-ZÁÉÍÓÚÂÊÔÃÕ][\w:'\-]+(?:\s+[A-Za-z0-9:'\-]{2,}){1,6})", line)
        if mname: name = mname.group(1).strip()
        if not name: continue
        out.append({"nome":name,"desconto": (pct.group(0) if pct else ""), "preco": (mny.group(0) if mny else ""), "plataforma": plat})
        if len(out)>=20: break
    # dedupe por nome
    ded=[]; seen=set()
    for it in out:
        k=it["nome"].lower()
        if k in seen: continue
        seen.add(k); ded.append(it)
    return ded

def build_bundle(topic:str)->Dict[str,Any]:
    qvars = query_variants(topic)
    # 1) feeds whitelisted
    feed_hits = collect_from_feeds(qvars)
    # 2) google news rss
    gnews_hits = collect_from_google_news(qvars)
    # junta + dedupe
    hits = dedupe_keep_latest(feed_hits + gnews_hits)
    # baixa corpo + extrai coisas
    sources=[]; claims=[]; promos=[]; all_tags=set(); all_text=[]
    for h in hits[:20]:
        body = _extract_body(h["link"])
        if not body: continue
        tags = editorial_tags(h["title"] + " " + body)
        all_tags.update(tags)
        promos.extend(extract_promos(body))
        sources.append({
            "title": h["title"],
            "url": h["link"],
            "source": h["source"],
            "published_iso": h.get("published_iso",""),
            "tags": tags,
            "preview": " ".join(body.split()[:80])
        })
        # fatos curtos (heurística: frases com números/datas/palavras-chave)
        for sent in re.split(r"(?<=[\.\!\?])\s+", body):
            if any(k in sent.lower() for k in ["lança","lançamento","estreia","preço","reais","dólares","update","temporada","pico","jogadores"]):
                claims.append({"text": sent.strip()[:220], "evidence": [h["link"]]})
        all_text.append(body)
    # dedupe claims por texto
    uniq=[]; seen=set()
    for c in claims:
        k=re.sub(r"\W+"," ",c["text"].lower()).strip()
        if k in seen: continue
        seen.add(k); uniq.append(c)
    # topo: escolhe ângulo
    chosen_angle = "desconto" if "desconto" in all_tags else ("lançamento" if "lançamento" in all_tags else (list(all_tags)[0] if all_tags else "geral"))
    # dedupe promo
    puniq=[]; ps=set()
    for p in promos:
        k=p["nome"].lower()
        if k in ps: continue
        ps.add(k); puniq.append(p)

    bundle = {
        "topic": topic,
        "query_variants": qvars,
        "chosen_angle": chosen_angle,
        "generated_at": _now_utc().isoformat(),
        "claims": uniq[:14],            # fatos curtos com evidências
        "promo_itens": puniq[:12],
        "ranking_itens": [],            # opcional: você pode plugar seu extrator de ranking aqui
        "sources": sources[:20]
    }
    return bundle

def write_txt(bundle:Dict[str,Any]):
    lines = [f"TEMA: {bundle['topic']}",
             f"ÂNGULO: {bundle['chosen_angle']}",
             f"Gerado: {bundle['generated_at']}",
             "\nFONTES:"]
    for s in bundle["sources"]:
        lines.append(f"- [{s.get('published_iso','')}] {s['title']} — {s['source']} — {s['url']}")
    if bundle["promo_itens"]:
        lines.append("\nPROMO DETECTADAS:")
        for it in bundle["promo_itens"]:
            lines.append(f"- {it['nome']} {it.get('desconto','')} {it.get('preco','')} {it.get('plataforma','')}")
    if bundle["claims"]:
        lines.append("\nFATOS CURTOS (para citar no vídeo):")
        for c in bundle["claims"]:
            lines.append(f"- {c['text']} (ref: {c['evidence'][0]})")
    CTX_TXT_PATH.write_text("\n".join(lines), encoding="utf-8")

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True, help="assunto escolhido pelo trends hub")
    args = ap.parse_args()
    bundle = build_bundle(args.topic.strip())
    BUNDLE_PATH.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    SOURCES_PATH.write_text(json.dumps(bundle["sources"], ensure_ascii=False, indent=2), encoding="utf-8")
    write_txt(bundle)
    print("✅ context_bundle.json, contexto_expandido.txt e fontes_usadas.json gerados em /output")

if __name__ == "__main__":
    main()
