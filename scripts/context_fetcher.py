#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Focused Context Fetcher — Flow Games Only (últimos 2 dias)
----------------------------------------------------------
- Busca APENAS no Flow Games (RSS direto)
- NÃO exige palavra‑chave; lista tudo dos últimos 2 dias
- Extração de corpo com vários seletores + fallback /amp
- Extrai listas "Top X" (ex.: jogos mais vendidos na Steam)
- Salva:
    • output/noticias_disponiveis.json
    • output/noticia_escolhida.json
    • output/contexto_expandido.txt
    • output/itens_detectados.json     (quando detectar promo/preço/%)
    • output/top_list.json             (quando houver lista ordenada)
"""

from __future__ import annotations
import re, json, html
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

# ──────────────────────────────────────────────────────────────────────────────
# Paths / Constantes
# ──────────────────────────────────────────────────────────────────────────────
OUT_DIR = Path("output"); OUT_DIR.mkdir(parents=True, exist_ok=True)
LIST_PATH    = OUT_DIR / "noticias_disponiveis.json"
CHOICE_PATH  = OUT_DIR / "noticia_escolhida.json"
CTX_PATH     = OUT_DIR / "contexto_expandido.txt"
ITENS_PATH   = OUT_DIR / "itens_detectados.json"
TOPLIST_PATH = OUT_DIR / "top_list.json"

TIMEOUT = 18
UA = "Mozilla/5.0 (Linux; Android 14) ZeroATechFocused/2.1 Mobile Safari"
HDRS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

# ──────────────────────────────────────────────────────────────────────────────
# Flow Games apenas
# ──────────────────────────────────────────────────────────────────────────────
FLOW_FEED = "https://flowgames.gg/feed/"

# Seletores reforçados (mudanças de tema quebram facilmente)
FLOW_SELECTORS = [
    ".entry-content",
    "article .entry-content",
    ".post-content",
    "article .post-content",
    "article .single__content",
    ".single__content",
    ".content-area article",
    "main article .content",
]

ADAPTERS = {
    "flowgames.gg": {
        "containers": FLOW_SELECTORS,
        "min_len": 220
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# Heurísticas de promo
# ──────────────────────────────────────────────────────────────────────────────
PROMO_HINTS = ("promo", "promoção", "desconto", "%", "grátis", "gratuito", "oferta", "sale", "preço", "cupom")
RE_MONEY    = re.compile(r"(R\$\s?\d{1,3}(?:\.\d{3})*,\d{2})|\b(\d{1,3},\d{2}\s?reais)\b", re.I)
RE_PERCENT  = re.compile(r"(\d{1,3})\s?%", re.I)
RE_PLATFORM = re.compile(r"\b(steam|epic|gog|psn|playstation|xbox|nintendo|switch|prime gaming|ea play)\b", re.I)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""

def safe_get(url: str) -> Optional[requests.Response]:
    try:
        r = requests.get(url, headers=HDRS, timeout=TIMEOUT, allow_redirects=True)
        # Alguns servidores retornam 403 com desktop UA; o nosso já é mobile.
        return r if (r is not None and r.text) else None
    except Exception:
        return None

def clean_spaces(s: str) -> str:
    s = re.sub(r"\u00a0", " ", s)  # nbsp
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def _strip_boilerplate(node: BeautifulSoup) -> None:
    # remove blocos comuns que poluem (newsletter, relacionados, publicidade, iframes, scripts etc.)
    kill_classes = re.compile(r"(newsletter|related|promo|share|social|breadcrumbs|post-tags|advert|ads|sidebar)", re.I)
    for tag in node.find_all(["aside","script","style","noscript","iframe","footer","header","nav"]):
        tag.decompose()
    for div in node.find_all(attrs={"class": kill_classes}):
        div.decompose()

# ──────────────────────────────────────────────────────────────────────────────
# Extração principal do artigo
# ──────────────────────────────────────────────────────────────────────────────
def _pull_text_from_container(node: BeautifulSoup, min_len: int) -> str:
    _strip_boilerplate(node)
    parts: List[str] = []
    # pega <p> e <li> longos dentro do container principal
    for el in node.find_all(["p", "li"]):
        # ignora listagens de "Leia mais" e blocos promocionais óbvios
        if el.find_parent(attrs={"class": re.compile(r"(related|more|promo|newsletter|share)", re.I)}):
            continue
        txt = el.get_text(" ", strip=True)
        if not txt:
            continue
        # filtra rodapés típicos ("Leia mais", CTAs)
        if re.search(r"(leia mais|assine|newsletter|siga-nos|siga-nos|compartilhe)", txt, re.I):
            continue
        if len(txt) >= 40:
            parts.append(txt)
        if sum(len(x) for x in parts) > 24000:
            break
    txt = "\n".join(parts).strip()
    return txt if len(txt) >= min_len else ""

def _find_main_container(soup: BeautifulSoup, selectors: List[str]) -> Optional[BeautifulSoup]:
    for sel in selectors:
        node = soup.select_one(sel)
        if node:
            return node
    # fallback: tenta o <article> ou role=main
    node = soup.find("article") or soup.find(attrs={"role": "main"})
    return node

def _extract_from_url_once(url: str) -> Tuple[str, Optional[BeautifulSoup]]:
    r = safe_get(url)
    if not r or not r.text:
        return "", None
    soup = BeautifulSoup(r.text, "html.parser")
    host = domain_of(url)
    cfg = ADAPTERS.get(host)
    if cfg:
        container = _find_main_container(soup, cfg["containers"])
        if container:
            txt = _pull_text_from_container(container, cfg["min_len"])
            if txt:
                return clean_spaces(txt), container
    # fallback geral
    container = soup.find("article") or soup.find(attrs={"role": "main"}) or soup
    txt = _pull_text_from_container(container, 200)
    return clean_spaces(txt), container

def extract_article_body(url: str) -> Tuple[str, Optional[BeautifulSoup]]:
    """
    Tenta extrair do URL "normal". Se vier vazio, tenta fallback no /amp.
    """
    txt, container = _extract_from_url_once(url)
    if txt:
        return txt, container

    # tenta versão AMP (muitos sites WP têm /amp)
    amp_url = None
    if not url.rstrip("/").endswith("/amp"):
        amp_url = url.rstrip("/") + "/amp"
        txt2, cont2 = _extract_from_url_once(amp_url)
        if txt2:
            return txt2, cont2

    return txt, container  # vazio mesmo

# ──────────────────────────────────────────────────────────────────────────────
# [Fluxo] Extração de listas “Top X” (Flow Games)
# ──────────────────────────────────────────────────────────────────────────────
def _extract_ranked_lists_from_flowgames(container: BeautifulSoup) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if not container:
        return results
    for ol in container.find_all("ol"):
        lis = [li for li in ol.find_all("li", recursive=False)]
        if len(lis) < 3:
            continue
        title = ""
        prev = ol.find_previous(lambda tag: tag.name in ("h1","h2","h3","p","strong"))
        if prev:
            t = prev.get_text(" ", strip=True)
            if t and len(t) >= 6 and not re.search(r"(leia mais|promo|newsletter|publicidade)", t, re.I):
                title = t
        itens: List[str] = []
        for idx, li in enumerate(lis, 1):
            txt = li.get_text(" ", strip=True)
            txt = re.sub(r"\s+", " ", txt).strip(" .;:+-")
            if not txt or re.search(r"(publicidade)", txt, re.I):
                continue
            itens.append(f"{idx}. {txt}")
        if itens:
            results.append({"titulo_lista": title or "Lista ordenada", "itens": itens})
    return results

# ──────────────────────────────────────────────────────────────────────────────
# Itens de promoção (heurística)
# ──────────────────────────────────────────────────────────────────────────────
def detect_promo_items(texto: str, limit: int = 24) -> List[Dict[str, str]]:
    if not texto:
        return []
    lines = [l.strip() for l in texto.splitlines() if l.strip()]
    items, seen = [], set()

    def clean(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip(" -–—:•\t ")

    for i, line in enumerate(lines):
        has_pct = RE_PERCENT.search(line)
        has_money = RE_MONEY.search(line)
        if not (has_pct or has_money):
            continue
        platform = ""
        mplat = RE_PLATFORM.search(line)
        if mplat:
            platform = mplat.group(0).title().replace("Psn", "PSN").replace("Playstation", "PlayStation")

        candidate = RE_MONEY.sub("", RE_PERCENT.sub("", RE_PLATFORM.sub("", line)))
        candidate = re.sub(r"[(){}\[\]]", " ", candidate)
        candidate = re.sub(r"\b(agora|por|de|até|na|no|por apenas|cada|com|em)\b", " ", candidate, flags=re.I)
        candidate = re.sub(r"[•\-–—:|]+", " ", candidate)
        candidate = clean(candidate)

        mname = re.search(r"([A-ZÁÉÍÓÚÂÊÔÃÕ][\w:'\-]+(?:\s+[A-Za-z0-9:'\-]{2,}){1,5})", candidate)
        name = mname.group(1).strip() if mname else ""

        if not name and i > 0:
            prev = clean(RE_MONEY.sub("", RE_PERCENT.sub("", lines[i - 1])))
            m2 = re.search(r"([A-ZÁÉÍÓÚÂÊÔÃÕ][\w:'\-]+(?:\s+[A-Za-z0-9:'\-]{2,}){1,5})", prev)
            if m2:
                name = m2.group(1).strip()

        if not name and i + 1 < len(lines):
            nxt = clean(RE_MONEY.sub("", RE_PERCENT.sub("", lines[i + 1])))
            m3 = re.search(r"([A-ZÁÉÍÓÚÂÊÔÃÕ][\w:'\-]+(?:\s+[A-Za-z0-9:'\-]{2,}){1,5})", nxt)
            if m3:
                name = m3.group(1).strip()

        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "nome": name,
            "desconto": (has_pct.group(0) if has_pct else ""),
            "preco": (has_money.group(0) if has_money else ""),
            "plataforma": platform,
        })
        if len(items) >= limit:
            break
    return items

# ──────────────────────────────────────────────────────────────────────────────
# Busca Flow Games (sem keyword), últimos N dias (fixo=2 no run)
# ──────────────────────────────────────────────────────────────────────────────
def fetch_flowgames_only(max_days: int = 2) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    cutoff = now_utc() - timedelta(days=max_days)
    d = feedparser.parse(FLOW_FEED)
    for e in d.entries:
        title = (getattr(e, "title", "") or "").strip()
        link  = (getattr(e, "link", "") or "").strip()
        if not title or not link:
            continue

        # Data
        pub_dt = None
        if getattr(e, "published_parsed", None):
            pub_dt = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
        elif getattr(e, "updated_parsed", None):
            pub_dt = datetime(*e.updated_parsed[:6], tzinfo=timezone.utc)

        if pub_dt and pub_dt < cutoff:
            continue

        out.append({
            "title": title,
            "link": link,
            "published_raw": getattr(e, "published", "") or getattr(e, "updated", ""),
            "published_iso": pub_dt.isoformat() if pub_dt else "",
            "source": "Flow Games",
            "snippet": "",
            "age_days": round((now_utc() - pub_dt).total_seconds() / 86400, 2) if pub_dt else None
        })

    out.sort(key=lambda it: it.get("published_iso") or "", reverse=True)
    return out

# ──────────────────────────────────────────────────────────────────────────────
# Persistência e montagem de contexto
# ──────────────────────────────────────────────────────────────────────────────
def save_list(items):  LIST_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
def save_choice(item): CHOICE_PATH.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
def save_context(text): CTX_PATH.write_text(text.strip() + "\n", encoding="utf-8")
def save_items_json(itens):
    if itens:
        ITENS_PATH.write_text(json.dumps(itens, ensure_ascii=False, indent=2), encoding="utf-8")
def save_toplist_json(toplists):
    if toplists:
        TOPLIST_PATH.write_text(json.dumps(toplists, ensure_ascii=False, indent=2), encoding="utf-8")

def build_context_block(item: Dict[str, Any]) -> str:
    title = item["title"]; link = item["link"]; source = item["source"]
    host  = domain_of(link)

    body, container = extract_article_body(link)

    # tenta extrair top lists do Flow Games
    toplists: List[Dict[str, Any]] = []
    if host == "flowgames.gg" and container is not None:
        toplists = _extract_ranked_lists_from_flowgames(container)
        save_toplist_json(toplists)

    # Itens de promoção (quando aplicável)
    itens = detect_promo_items(body) if any(h in (title + " " + body).lower() for h in PROMO_HINTS) else []
    save_items_json(itens)

    meta = [
        "Tema/Categoria: Foco Flow Games",
        "Query usada: (sem filtro; últimos 2 dias)",
        "Janela de recência: últimos 2 dias",
        f"Título: {title}",
        f"Fonte: {source}",
        f"Publicado (raw): {item.get('published_raw','')}",
        f"Publicado (ISO): {item.get('published_iso','')} | Idade (dias): {item.get('age_days')}",
        f"Link final: {link}",
    ]
    parts = ["\n".join(meta)]

    # Bloco de listas (se houver)
    if toplists:
        parts.append("\nListas extraídas do artigo (ordem original):")
        for lst in toplists:
            t = lst.get("titulo_lista") or "Lista"
            items_fmt = "\n".join(f"- {it}" for it in lst.get("itens", []))
            parts.append(f"{t}\n{items_fmt}")

    # Corpo limpo
    body_block = "Texto limpo (trechos principais):\n" + (body if body else "(não foi possível extrair o corpo do artigo)")
    parts.append("\n" + body_block)

    # Observações editoriais úteis para o Script Generator
    notes = []
    if toplists:
        notes.append("✅ Use a(s) lista(s) acima na ORDEM original do artigo.")
        notes.append("✅ Cite nominalmente os jogos (sem inventar títulos).")
        notes.append("✅ Se houver duas listas (ex.: Brasil e Mundo), identifique no texto curto.")
    if itens:
        notes.append("✅ Há indícios de promoção/valores — cite apenas os que constam no contexto.")
    if notes:
        parts.append("\nRegras para o roteiro:\n" + "\n".join(f"- {n}" for n in notes))

    return "\n".join(parts).strip()

# ──────────────────────────────────────────────────────────────────────────────
# CLI simples
# ──────────────────────────────────────────────────────────────────────────────
def ask(prompt, default=None):
    try:
        v = input(f"{prompt} ").strip()
        return default if (not v and default is not None) else v
    except KeyboardInterrupt:
        raise

def run():
    print("🎯 Focused Fetcher — Flow Games (últimos 2 dias)")
    # janela fixa de 2 dias (pode alterar aqui se quiser)
    days = 2

    items = fetch_flowgames_only(max_days=days)
    if not items:
        print("Nenhum item do Flow Games encontrado na janela de 2 dias.")
        save_list([])
        return

    save_list(items)

    # exibe tudo que temos (sem filtro de keyword)
    for i, it in enumerate(items, 1):
        age = it.get("age_days")
        age_s = f"{age:.2f}d" if isinstance(age, (int, float)) else "?"
        print(f"[{i}] {it['title']} — {it['source']} — {age_s}")

    # escolhe um para extrair o contexto completo
    try:
        idx = int(ask(f"Escolha (1-{len(items)}) ou 0 para cancelar:", "1"))
    except Exception:
        idx = 1
    if idx <= 0 or idx > len(items):
        print("Cancelado."); return

    chosen = items[idx - 1]
    save_choice(chosen)
    ctx = build_context_block(chosen)
    save_context(ctx)

    print("\n✅ Contexto salvo em:", CTX_PATH)
    if TOPLIST_PATH.exists():
        print("✅ Top list salva em:", TOPLIST_PATH)
    if ITENS_PATH.exists():
        print("✅ Itens detectados (promo):", ITENS_PATH)

if __name__ == "__main__":
    run()
