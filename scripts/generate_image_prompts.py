#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, json, re, base64, time, urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from PIL import Image
import requests
from dotenv import load_dotenv
from openai import OpenAI
from bs4 import BeautifulSoup

# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Defina OPENAI_API_KEY no .env")
client = OpenAI(api_key=OPENAI_API_KEY)

DIALOGO_JSON_PATH = Path("output/dialogo_estruturado.json")
PLANO_JSON_PATH   = Path("output/imagens_plano.json")          # agora traz tipo/official_query
OUT_RAW           = Path("assets/imagens_geradas")
OUT_FINAL         = Path("assets/imagens_geradas_padronizadas")
OUT_FOR_VIDEO     = Path("output")                              # cópia quadrada para o vídeo
MANIFEST_PATH     = Path("output/imagens_manifest.json")

SIZE = (1024, 1024)  # tamanho padrão
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

PREFERRED_HOSTS = (
    "steamcdn-a.akamaihd.net", "cdn.akamai.steamstatic.com", "store.steampowered.com",
    "callofduty.com", "www.callofduty.com", "images.ctfassets.net",
    "playstation.com", "xbox.com", "ea.com", "staticdelivery.nexusmods.com"
)

for p in (OUT_RAW, OUT_FINAL, OUT_FOR_VIDEO):
    p.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def padronizar_imagem(src: Path, dst: Path, size: Tuple[int,int]=(1024,1024)):
    """Redimensiona em RGB (sem transparência) e salva com boa qualidade."""
    with Image.open(src) as img:
        img = img.convert("RGB")
        img = img.resize(size, Image.LANCZOS)
        img.save(dst, quality=95)

def load_json(path: Path, default):
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return default

def _to_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, (list, tuple, set)):
        return ", ".join(str(x).strip() for x in v if str(x).strip())
    if isinstance(v, dict):
        vals = [str(x).strip() for x in v.values() if str(x).strip()]
        return ", ".join(vals)
    return str(v).strip()

def build_style_prefix(plano: Dict[str,Any]) -> str:
    est = plano.get("estilo_global", {}) or {}
    if isinstance(est, list):
        est = {"paleta": est}
    paleta   = _to_str(est.get("paleta", ""))
    estetica = _to_str(est.get("estetica", ""))
    nota     = _to_str(est.get("nota", ""))
    parts = []
    if estetica: parts.append(estetica)
    if paleta:   parts.append(f"cores: {paleta}")
    if nota:     parts.append(nota)
    parts.append("composição centrada, legível em tela pequena, iluminação balanceada")
    return ", ".join(p for p in parts if p)

def choose_style_tail(prompt_base: str, allow_logo: bool) -> str:
    """Cauda de prompt (realista x ilustrativo). Não força 'sem logotipos' quando allow_logo=True."""
    realistas = [
        "smartphone","computador","drone","carro","servidor","fotografia","produto",
        "dispositivo","hardware","gameplay","realista","cinematográfica","marketing"
    ]
    is_real = any(w in prompt_base.lower() for w in realistas)
    base_tail = ("estilo foto editorial realista, iluminação cinematográfica, alta nitidez, profundidade de campo, 1024x1024"
                 if is_real else
                 "ilustração vetorial/flat moderna, traços limpos, cores vivas equilibradas, sombras sutis, 1024x1024")
    if not allow_logo:
        base_tail += ", sem logotipos, sem marcas registradas"
    return base_tail

def sanitize_prompt(p: str, allow_logo: bool=False) -> str:
    """Limpa excessos mas NÃO bloqueia logo quando for permitido."""
    if not p:
        return ""
    p = re.sub(r"\s+", " ", p).strip()
    if not allow_logo:
        # remove pedidos longos de texto
        p = re.sub(r"\btexto\b.*?(?:[.,]|$)", "", p, flags=re.I)
        # força 'sem logos' se não for oficial
        if "sem logotipo" not in p.lower() and "sem logotipos" not in p.lower():
            p = f"{p} | sem logotipos, sem marcas registradas"
    return p.strip(" .|")

# ──────────────────────────────────────────────────────────────────────────────
# Busca de ARTE OFICIAL
# ──────────────────────────────────────────────────────────────────────────────

def _extract_og_image(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers=UA, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for sel in [
            ('meta[property="og:image"]', "content"),
            ('meta[name="twitter:image"]', "content")
        ]:
            tag = soup.select_one(sel[0])
            if tag and tag.get(sel[1]):
                return tag.get(sel[1]).strip()
        # fallback: primeira <img> grande
        best = None; best_area = 0
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if not src: continue
            w = int(img.get("width") or 0)
            h = int(img.get("height") or 0)
            area = (w*h) if (w and h) else 0
            if area > best_area:
                best_area = area; best = src
        if best:
            return best
    except Exception:
        return None
    return None

def _resolve_ddg_redirect(href: str) -> str:
    # DuckDuckGo html usa /l/?uddg=<url>
    try:
        parsed = urllib.parse.urlparse(href)
        qs = urllib.parse.parse_qs(parsed.query)
        if "uddg" in qs:
            return urllib.parse.unquote(qs["uddg"][0])
    except Exception:
        pass
    return href

def _score_host(url: str) -> int:
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return 0
    score = 0
    for i, pref in enumerate(PREFERRED_HOSTS[::-1], start=1):
        if host.endswith(pref):
            score += 10 + i  # preferidos > outros
    return score

def buscar_arte_oficial_por_query(query: str) -> Optional[str]:
    """
    Estratégia simples:
    1) Busca HTML do DuckDuckGo (sem token).
    2) Abre o primeiro(s) resultado(s), pega og:image/twitter:image.
    3) Prefere hosts da lista PREFERRED_HOSTS.
    """
    try:
        qurl = f"https://duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
        r = requests.get(qurl, headers=UA, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        candidates = []
        for a in soup.select("a.result__a, a.result__url"):
            href = a.get("href")
            if not href: continue
            url = _resolve_ddg_redirect(href)
            img = _extract_og_image(url)
            if img:
                candidates.append((url, img, _score_host(url)))
        if not candidates:
            return None
        # escolhe o de maior score de host; se empate, o primeiro
        candidates.sort(key=lambda x: x[2], reverse=True)
        return candidates[0][1]
    except Exception:
        return None

def baixar_imagem(url: str, dest: Path) -> bool:
    try:
        r = requests.get(url, headers=UA, timeout=15)
        r.raise_for_status()
        with open(dest, "wb") as f:
            f.write(r.content)
        # valida abertura
        Image.open(dest).verify()
        return True
    except Exception:
        if dest.exists():
            dest.unlink(missing_ok=True)
        return False

# ──────────────────────────────────────────────────────────────────────────────
# Geração por IA
# ──────────────────────────────────────────────────────────────────────────────

def generate_ai_image(prompt: str, idx: int, tries: int = 2) -> Path:
    """Gera imagem com gpt-image-1 (b64) com retry simples."""
    last_err = None
    for attempt in range(1, tries+1):
        try:
            resp = client.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                size="1024x1024"  # quadrado, fundo opaco será feito na padronização
            )
            b64 = resp.data[0].b64_json
            raw_path = OUT_RAW / f"img_raw_{idx:02}.png"
            with open(raw_path, "wb") as f:
                f.write(base64.b64decode(b64))
            return raw_path
        except Exception as e:
            last_err = e
            time.sleep(1.2 * attempt)
    raise last_err

# ──────────────────────────────────────────────────────────────────────────────
# Execução
# ──────────────────────────────────────────────────────────────────────────────

def main():
    falas = load_json(DIALOGO_JSON_PATH, [])
    if not falas:
        print("❌ 'output/dialogo_estruturado.json' não encontrado ou vazio.")
        return

    plano = load_json(PLANO_JSON_PATH, {"estilo_global": {}, "imagens": []})

    # Blindagem da estrutura do plano
    if not isinstance(plano, dict):
        plano = {"estilo_global": {}, "imagens": []}
    if "estilo_global" not in plano or plano["estilo_global"] is None:
        plano["estilo_global"] = {}
    if "imagens" not in plano or not isinstance(plano["imagens"], list):
        plano["imagens"] = []

    style_prefix = build_style_prefix(plano)

    # índice -> item do plano (agora contém tipo, query, prompt)
    itens_por_linha: Dict[int, Dict[str, Any]] = {
        int(it["linha"]): it
        for it in plano.get("imagens", [])
        if isinstance(it, dict) and "linha" in it
    }

    print(f"🔎 Falas: {len(falas)} | Itens planejados: {len(itens_por_linha)}")
    manifest = {"itens": []}
    contador = 1

    for i, fala in enumerate(falas):
        item = itens_por_linha.get(i)
        if not item:
            continue  # sem imagem nessa fala

        tipo = (item.get("tipo") or "").lower()
        allow_logo = tipo == "official"  # oficial pode exibir logo/branding
        plano_prompt = (item.get("prompt") or fala.get("imagem") or "").strip()
        plano_prompt = sanitize_prompt(plano_prompt, allow_logo=allow_logo)

        # prompt final (para fallback IA)
        prompt_final = f"{style_prefix}. {plano_prompt}. {choose_style_tail(plano_prompt, allow_logo)}"
        print(f"\n🖼️ [{contador}] Fala #{i} ({tipo or 'ai'})")

        raw_path: Optional[Path] = None

        # 1) Se oficial: tenta baixar uma arte oficial via queries
        if tipo == "official":
            queries = []
            if item.get("official_query"):          queries.append(item["official_query"])
            if item.get("official_queries_extra"):  queries.extend(item["official_queries_extra"])

            got = False
            for q in queries:
                print(f"   🔎 Buscando arte oficial: {q}")
                img_url = buscar_arte_oficial_por_query(q)
                if not img_url:
                    continue
                raw_candidate = OUT_RAW / f"img_raw_{contador:02}.jpg"
                if baixar_imagem(img_url, raw_candidate):
                    raw_path = raw_candidate
                    got = True
                    print(f"   ✅ Oficial encontrada: {img_url}")
                    break
                else:
                    print("   ⚠️ Falha ao baixar, tentando próxima…")
            if not got:
                print("   ⚠️ Não achei oficial — vou gerar por IA (fallback).")

        # 2) Se não oficial (ou oficial falhou): gerar IA
        if raw_path is None:
            print(f"   🤖 Gerando IA…")
            try:
                raw_path = generate_ai_image(prompt_final, contador, tries=3)
            except Exception as e:
                print(f"❌ Erro ao gerar imagem (fala {i}): {e}")
                continue

        # padroniza/copia
        final_path = OUT_FINAL / f"img_{contador:02}.png"
        padronizar_imagem(raw_path, final_path, SIZE)

        video_path = OUT_FOR_VIDEO / f"imagem_{contador:02}.png"
        padronizar_imagem(raw_path, video_path, SIZE)

        print(f"✅ Salvo: {final_path} | Copiado p/ vídeo: {video_path}")

        manifest["itens"].append({
            "idx_global": contador,
            "fala_index": i,
            "personagem": fala.get("personagem"),
            "fala": fala.get("fala"),
            "tipo": tipo or "ai",
            "prompt_usado": prompt_final,
            "arquivo_final": str(final_path),
            "arquivo_video": str(video_path),
            "official_query": item.get("official_query"),
        })
        contador += 1

    with MANIFEST_PATH.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\n🧾 Manifest salvo em: {MANIFEST_PATH}")
    print("🏁 Fim da geração de imagens.")

if __name__ == "__main__":
    main()
