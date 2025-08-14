#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
page_harvester.py — Zero à Tech
--------------------------------
Extrai o TEXTO COMPLETO de uma notícia, partindo do link do Google News ou do link final.
Camadas de fallback:
 1) Resolver URL real (GNews → veículo)
 2) Trafilatura
 3) JSON-LD (articleBody)
 4) Readability-lxml
 5) WordPress REST (id/slug/search)
 6) AMP
 7) r.jina.ai

Entradas:
- argv[1] opcional: URL manual
- senão, lê output/noticia_escolhida.json

Saídas:
- output/artigo_url_final.txt
- output/artigo_texto.txt
- output/itens_detectados.json (se parece promo/lista)
"""

import re, json, base64, unicodedata, sys
from pathlib import Path
from typing import Optional, Tuple, List, Dict
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

# opcional, mas muito eficaz
import trafilatura
from readability import Document

OUT = Path("output"); OUT.mkdir(parents=True, exist_ok=True)
CHOICE = OUT / "noticia_escolhida.json"
URL_TXT = OUT / "artigo_url_final.txt"
TEXT_TXT = OUT / "artigo_texto.txt"
ITENS_JSON = OUT / "itens_detectados.json"

TIMEOUT = 25
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 14) ZeroATechBot/8.0 Mobile Safari",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://news.google.com/",
    "Cache-Control": "no-cache",
}

GOOGLE = ("news.google.com","google.com","www.google.com","consent.google.com","gstatic.com","googleusercontent.com")

# mapeia alguns publishers comuns → domínio (ajuda nos métodos WP)
PUBLISHER_TO_DOMAIN = {
    "gameplayscassi": "https://gameplayscassi.com.br",
    "tecmundo": "https://www.tecmundo.com.br",
    "adrenaline": "https://adrenaline.com.br",
    "uol": "https://www.uol.com.br",
    "mmorpgbr": "https://mmorpgbr.com.br",
    "folha vitoria": "https://www.folhavitoria.com.br",
    "tudocelular.com": "https://www.tudocelular.com",
    "notebookcheck.info": "https://www.notebookcheck.info",
}

RE_MONEY    = re.compile(r"(R\$\s?\d{1,3}(?:\.\d{3})*,\d{2})|\b(\d{1,3},\d{2}\s?reais)\b", re.I)
RE_PERCENT  = re.compile(r"(\d{1,3})\s?%", re.I)
RE_PLATFORM = re.compile(r"\b(steam|epic|gog|psn|playstation|xbox|nintendo|switch|prime gaming|ea play)\b", re.I)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers básicos
# ──────────────────────────────────────────────────────────────────────────────

def safe_get(url: str, **kw):
    try:
        h = kw.pop("headers", {})
        return requests.get(url, headers={**HEADERS, **h}, timeout=TIMEOUT, **kw)
    except Exception:
        return None

def norm(s: str) -> str:
    s = (s or "").strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def norm_source_key(s: str) -> str:
    s = norm((s or "").lower())
    s = re.sub(r"[^a-z0-9\. ]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def slugify_pt(text: str) -> str:
    text = re.sub(r"\s*-\s+[^\-]+$", "", text or "").strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-{2,}", "-", text).strip("-")

def clean_text(txt: str) -> str:
    if not txt: return ""
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    out = []
    for line in txt.splitlines():
        l = line.strip()
        if not l: out.append(""); continue
        if len(l) <= 1: continue
        if any(k in l.lower() for k in ["publicidade","assine","compartilhe:","leia também:","veja também:"]):
            continue
        out.append(l)
    return "\n".join(out).strip()

# ──────────────────────────────────────────────────────────────────────────────
# Resolver Google News → URL real (decodifica /articles/<b64> quando possível)
# ──────────────────────────────────────────────────────────────────────────────

def _b64_urlsafe_decode(data: str) -> bytes:
    data = data.replace("-", "+").replace("_", "/")
    data += "=" * ((4 - len(data) % 4) % 4)
    return base64.b64decode(data, validate=False)

def decode_news_articles_url(url: str) -> Optional[str]:
    try:
        p = urlparse(url)
        if "/articles/" not in p.path: return None
        b64seg = p.path.split("/articles/")[-1].split("/")[0]
        b = _b64_urlsafe_decode(b64seg)
        m = re.search(rb"https?://[^\s\x00\"'<>]+", b)
        if m: return m.group(0).decode("utf-8","ignore")
    except Exception:
        pass
    return None

def first_external_href(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("/"): href = urljoin(base_url, href)
        p = urlparse(href)
        if p.scheme in ("http","https") and not any(p.netloc.endswith(d) for d in GOOGLE):
            return href
    return None

def resolve_final_url(start_url: str) -> str:
    d = decode_news_articles_url(start_url)
    if d: return d
    r = safe_get(start_url, allow_redirects=True)
    if not r: return start_url
    final = r.url
    host = urlparse(final).netloc.lower()
    if not any(host.endswith(d) for d in GOOGLE): return final
    soup = BeautifulSoup(r.text, "html.parser")
    for relname in ("canonical","amphtml"):
        link = soup.find("link", rel=lambda v: v and relname in v.lower())
        if link and link.get("href"):
            return urljoin(final, link["href"].strip())
    meta = soup.find("meta", attrs={"http-equiv": lambda v: v and v.lower()=="refresh"})
    if meta and "url=" in (meta.get("content") or "").lower():
        m = re.search(r"url=(.+)$", meta["content"], flags=re.I)
        if m:
            return urljoin(final, m.group(1).strip().strip("'").strip('"'))
    ext = first_external_href(soup, final)
    return ext or final

# ──────────────────────────────────────────────────────────────────────────────
# 1) Trafilatura
# ──────────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
# 1) Trafilatura (corrigido p/ usar requests + extract)
# ──────────────────────────────────────────────────────────────────────────────
def trafi_extract(url: str) -> Optional[str]:
    """Baixa o HTML com requests e usa trafilatura.extract em cima do conteúdo.
       Assim evita o fetch_url(user_agent=...) que muda entre versões."""
    try:
        r = safe_get(url, allow_redirects=True)
        if not r or not r.ok or not r.content:
            return None
        # trafilatura.extract espera bytes/str do HTML
        text = trafilatura.extract(
            r.content,
            include_images=False,
            include_tables=False,
            include_formatting=False,
            favor_recall=True,
            url=url,
        )
        return clean_text(text) if text else None
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# 2) JSON-LD (Article)
# ──────────────────────────────────────────────────────────────────────────────

def jsonld_article_body(html_text: str) -> Optional[str]:
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        for s in soup.find_all("script", type=lambda v: v and "ld+json" in v.lower()):
            try:
                data = json.loads(s.string or "{}")
            except Exception:
                continue
            def search(obj):
                if isinstance(obj, dict):
                    if (obj.get("@type") in ("Article","NewsArticle")) and obj.get("articleBody"):
                        return obj["articleBody"]
                    for v in obj.values():
                        r = search(v)
                        if r: return r
                elif isinstance(obj, list):
                    for v in obj:
                        r = search(v)
                        if r: return r
                return None
            body = search(data)
            if body:
                return clean_text(body)
    except Exception:
        pass
    return None

# ──────────────────────────────────────────────────────────────────────────────
# 3) Readability-lxml
# ──────────────────────────────────────────────────────────────────────────────

def readability_extract(html_text: str) -> Optional[str]:
    try:
        doc = Document(html_text)
        summary_html = doc.summary(html_partial=False)
        soup = BeautifulSoup(summary_html, "html.parser")
        parts = []
        for el in soup.find_all(["p","li","h2","h3","blockquote"]):
            t = el.get_text(" ", strip=True)
            if not t: continue
            # aceita bullets curtos
            if el.name == "li":
                if len(t) < 2: continue
            else:
                if len(t) < 10: continue
            parts.append(t)
        txt = "\n".join(parts)
        return clean_text(txt) if txt else None
    except Exception:
        return None

# ──────────────────────────────────────────────────────────────────────────────
# 4) WordPress (id/slug/search)
# ──────────────────────────────────────────────────────────────────────────────

def html_to_text(html_content: str) -> str:
    soup = BeautifulSoup(html_content or "", "html.parser")
    parts = []
    for el in soup.find_all(["p","li","h2","h3","blockquote"]):
        t = el.get_text(" ", strip=True)
        if not t: continue
        if el.name == "li":
            if len(t) < 2: continue
        else:
            if len(t) < 10: continue
        parts.append(t)
    return clean_text("\n".join(parts))

def wp_by_id(url: str) -> Optional[str]:
    p = urlparse(url)
    m = re.search(r"/(\d+)/?$", p.path)
    if not m: return None
    post_id = m.group(1)
    api = f"{p.scheme}://{p.netloc}/wp-json/wp/v2/posts/{post_id}"
    r = safe_get(api)
    if not r or r.status_code != 200: return None
    try:
        data = r.json()
        return html_to_text(((data.get("content") or {}).get("rendered")) or "")
    except Exception:
        return None

def wp_by_slug(url: str) -> Tuple[Optional[str], Optional[str]]:
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    segs = [s for s in p.path.split("/") if s]
    if not segs: return None, None
    slug = segs[-2] if segs[-1].isdigit() and len(segs) >= 2 else segs[-1]
    api = f"{base}/wp-json/wp/v2/posts"
    r = safe_get(api, params={"slug": slug, "per_page": 1, "_embed": "1"})
    if not r or r.status_code != 200: return None, None
    try:
        arr = r.json()
        if not isinstance(arr, list) or not arr: return None, None
        data = arr[0]
        text = html_to_text(((data.get("content") or {}).get("rendered")) or "")
        return (data.get("link") or f"{base}/{slug}/"), (text or None)
    except Exception:
        return None, None

def wp_search(source: str, title: str) -> Tuple[Optional[str], Optional[str]]:
    base = PUBLISHER_TO_DOMAIN.get(norm_source_key(source)) or ""
    if not base: return None, None
    for endpoint in (
        f"{base}/wp-json/wp/v2/search",
        f"{base}/wp-json/wp/v2/search?subtype=post",
    ):
        r = safe_get(endpoint, params={"search": title, "per_page": 10})
        if not r or r.status_code != 200:
            continue
        try:
            arr = r.json()
        except Exception:
            continue
        candidates = []
        sslug = slugify_pt(title)
        for it in arr if isinstance(arr, list) else []:
            pid = it.get("id") or it.get("post_id") or it.get("object_id")
            url = it.get("url") or it.get("link")
            ttl = (it.get("title") or it.get("name") or "")
            if not pid: continue
            score = 0
            if url and "/noticias/" in url: score += 2
            if url and sslug in (url or ""): score += 2
            if ttl and sslug in slugify_pt(ttl): score += 1
            candidates.append((score, pid, url, ttl))
        candidates.sort(reverse=True)
        for _, pid, url, ttl in candidates:
            api = f"{base}/wp-json/wp/v2/posts/{pid}"
            r2 = safe_get(api)
            if not r2 or r2.status_code != 200:
                continue
            try:
                data = r2.json()
                text = html_to_text(((data.get("content") or {}).get("rendered")) or "")
                if text and len(text) > 200:
                    return (data.get("link") or url or f"{base}/?p={pid}"), text
            except Exception:
                continue
    return None, None

# ──────────────────────────────────────────────────────────────────────────────
# 5) AMP e 6) r.jina.ai
# ──────────────────────────────────────────────────────────────────────────────

def amp_extract(url: str) -> Tuple[str, Optional[str], Optional[str]]:
    r = safe_get(url, allow_redirects=True)
    if not r: return url, None, None
    soup = BeautifulSoup(r.text, "html.parser")
    amp = soup.find("link", rel=lambda v: v and "amphtml" in v.lower())
    if amp and amp.get("href"):
        amp_url = urljoin(r.url, amp["href"].strip())
        r2 = safe_get(amp_url, allow_redirects=True)
        if r2 and r2.ok:
            t = trafi_extract(r2.url) or readability_extract(r2.text) or jsonld_article_body(r2.text)
            return r2.url, t, r2.text
    # tenta sufixos
    base = r.url.rstrip("/")
    for suf in ("/amp/", "?amp"):
        r2 = safe_get(base + suf, allow_redirects=True)
        if r2 and r2.ok:
            t = trafi_extract(r2.url) or readability_extract(r2.text) or jsonld_article_body(r2.text)
            return r2.url, t, r2.text
    return r.url, None, r.text

def jina_text(url: str) -> Optional[str]:
    u = url.replace("https://", "").replace("http://", "")
    proxy = "https://r.jina.ai/http://" + u
    r = safe_get(proxy, headers={"Accept": "text/plain"})
    if not r or r.status_code != 200: return None
    return clean_text(r.text or "")

# ──────────────────────────────────────────────────────────────────────────────
# Promo detector
# ──────────────────────────────────────────────────────────────────────────────

def looks_like_promo(text: str) -> bool:
    s = (text or "").lower()
    return any(k in s for k in ["promo","promoção","desconto","grátis","gratuito","oferta","sale","cupom","preço","%"])

def detect_promo_items(texto: str, limit: int = 60) -> List[Dict[str,str]]:
    if not texto: return []
    lines = [l.strip() for l in texto.splitlines() if l.strip()]
    items, seen = [], set()
    def clean(s: str) -> str: return re.sub(r"\s+"," ",s).strip(" -–—:•\t ")
    for i, line in enumerate(lines):
        has_pct = RE_PERCENT.search(line); has_money = RE_MONEY.search(line)
        if not (has_pct or has_money): continue
        platform = ""
        mplat = RE_PLATFORM.search(line)
        if mplat:
            platform = mplat.group(0).title().replace("Psn","PSN").replace("Playstation","PlayStation")
        candidate = RE_MONEY.sub("", RE_PERCENT.sub("", RE_PLATFORM.sub("", line)))
        candidate = re.sub(r"[\(\)\[\]\{\}]", " ", candidate)
        candidate = re.sub(r"\b(agora|por|de|até|na|no|por apenas|cada|com|em)\b", " ", candidate, flags=re.I)
        candidate = re.sub(r"[•\-–—:|]+", " ", candidate)
        candidate = clean(candidate)
        mname = re.search(r"([A-ZÁÉÍÓÚÂÊÔÃÕ][\w:'\-]+(?:\s+[A-Za-z0-9:'\-]{1,}){0,6})", candidate)
        name = mname.group(1).strip() if mname else ""
        if not name and i>0:
            prev = clean(RE_MONEY.sub("", RE_PERCENT.sub("", lines[i-1])))
            m2 = re.search(r"([A-ZÁÉÍÓÚÂÊÔÃÕ][\w:'\-]+(?:\s+[A-Za-z0-9:'\-]{1,}){0,6})", prev)
            if m2: name = m2.group(1).strip()
        if not name and i+1 < len(lines):
            nxt = clean(RE_MONEY.sub("", RE_PERCENT.sub("", lines[i+1])))
            m3 = re.search(r"([A-ZÁÉÍÓÚÂÊÔÃÕ][\w:'\-]+(?:\s+[A-Za-z0-9:'\-]{1,}){0,6})", nxt)
            if m3: name = m3.group(1).strip()
        if not name: continue
        key = name.lower()
        if key in seen: continue
        seen.add(key)
        items.append({"nome": name, "desconto": (has_pct.group(0) if has_pct else ""),
                      "preco": (has_money.group(0) if has_money else ""), "plataforma": platform})
        if len(items) >= limit: break
    return items

# ──────────────────────────────────────────────────────────────────────────────
# Orquestração
# ──────────────────────────────────────────────────────────────────────────────

def load_choice_info() -> Dict[str,str]:
    info = {"title":"", "source":"", "link":""}
    if CHOICE.exists():
        try:
            data = json.loads(CHOICE.read_text(encoding="utf-8"))
            info["title"]  = (data.get("title") or "").strip()
            info["source"] = (data.get("source") or "").strip()
            info["link"]   = (data.get("link") or "").strip()
        except Exception:
            pass
    return info

def load_start_url() -> Optional[str]:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip()
    info = load_choice_info()
    return info.get("link") or None

def main():
    info = load_choice_info()
    start = load_start_url()
    if not start:
        print("❌ Sem URL. Passe a URL ou gere output/noticia_escolhida.json.")
        return

    print("🔗 URL de origem:", start)
    final_url = resolve_final_url(start)
    print("➡️  URL resolvida:", final_url)
    URL_TXT.write_text(final_url + "\n", encoding="utf-8")

    # 1) Trafilatura
    text = trafi_extract(final_url)
    used = []
    if text and len(text) >= 1200:
        used.append("trafilatura")
    else:
        # baixa HTML pro restante das camadas
        r = safe_get(final_url, allow_redirects=True)
        html_text = r.text if (r and r.ok) else ""

        # 2) JSON-LD articleBody
        if html_text and not text:
            jtxt = jsonld_article_body(html_text)
            if jtxt and len(jtxt) >= 1200:
                text, used = jtxt, ["jsonld"]

        # 3) Readability
        if html_text and not text:
            rtxt = readability_extract(html_text)
            if rtxt and len(rtxt) >= 1200:
                text, used = rtxt, ["readability"]

        # 4) WordPress (id/slug/search)
        if not text:
            if (m := re.search(r"/(\d+)/?$", urlparse(final_url).path)):
                wpid = wp_by_id(final_url)
                if wpid and len(wpid) >= 1200:
                    text, used = wpid, ["wp-id"]
        if not text:
            wpslug_url, wpslug_txt = wp_by_slug(final_url)
            if wpslug_txt and len(wpslug_txt) >= 1200:
                final_url = wpslug_url or final_url
                text, used = wpslug_txt, ["wp-slug"]
        if not text and info.get("source") and info.get("title"):
            wps_url, wps_txt = wp_search(info["source"], info["title"])
            if wps_txt and len(wps_txt) >= 1200:
                final_url = wps_url or final_url
                text, used = wps_txt, ["wp-search"]

        # 5) AMP
        if not text:
            amp_url, amp_txt, amp_html = amp_extract(final_url)
            if amp_txt and len(amp_txt) >= 1200:
                final_url, text, used = amp_url, amp_txt, ["amp"]

        # 6) Trafilatura (segunda chance com AMP/downloader)
        if not text and amp_html:
            # tenta extrair do html AMP com trafilatura
            t2 = trafilatura.extract(amp_html, favor_recall=True, include_images=False, include_tables=False, include_formatting=False, url=final_url)
            if t2 and len(t2) >= 1200:
                text, used = clean_text(t2), ["trafilatura-amp"]

        # 7) r.jina.ai
        if not text:
            j = jina_text(final_url)
            if j and len(j) >= 800:  # às vezes o AMP é mais curto, aceita 800+
                text, used = j, ["jina"]

    if not text:
        print("❌ Não consegui extrair texto com qualidade.")
        TEXT_TXT.write_text("", encoding="utf-8")
        return

    URL_TXT.write_text(final_url + "\n", encoding="utf-8")
    TEXT_TXT.write_text(text + "\n", encoding="utf-8")
    print(f"✅ Texto salvo ({'+'.join(used)}, {len(text)} chars) → {TEXT_TXT}")

    if looks_like_promo(text):
        itens = detect_promo_items(text)
        if itens:
            ITENS_JSON.write_text(json.dumps(itens, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"🧾 Itens detectados: {len(itens)} (→ {ITENS_JSON})")
        else:
            print("ℹ️ Parece promo, mas não identifiquei linhas com %/preço (pode ser texto corrido).")
    else:
        print("ℹ️ Não é matéria de lista/promo — normal.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário.")
