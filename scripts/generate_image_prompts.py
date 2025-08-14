#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, json, re, base64, time
from pathlib import Path
from typing import Dict, Any, List, Tuple
from PIL import Image
import requests
from dotenv import load_dotenv
from openai import OpenAI

# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Defina OPENAI_API_KEY no .env")
client = OpenAI(api_key=OPENAI_API_KEY)

DIALOGO_JSON_PATH = Path("output/dialogo_estruturado.json")
PLANO_JSON_PATH   = Path("output/imagens_plano.json")          # opcional, mas recomendado
OUT_RAW           = Path("assets/imagens_geradas")
OUT_FINAL         = Path("assets/imagens_geradas_padronizadas")
OUT_FOR_VIDEO     = Path("output")                              # cópia quadrada para o vídeo
MANIFEST_PATH     = Path("output/imagens_manifest.json")

SIZE = (1024, 1024)  # tamanho padrão

for p in (OUT_RAW, OUT_FINAL, OUT_FOR_VIDEO):
    p.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def padronizar_imagem(src: Path, dst: Path, size: Tuple[int,int]=(1024,1024)):
    with Image.open(src) as img:
        img = img.convert("RGBA")
        img = img.resize(size, Image.LANCZOS)
        img.save(dst)

def load_json(path: Path, default):
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return default

def sanitize_prompt(p: str) -> str:
    if not p:
        return ""
    # remove pedidos de texto / aspas
    p = re.sub(r"com\s+um\s+texto\s+que\s+diz[^,.]*[.,]?", "", p, flags=re.I)
    p = re.sub(r"selo\s+de\s+['“\"].*?['”\"]", "selo genérico sem texto", p, flags=re.I)
    p = re.sub(r"com\s+palavra[s]?\s+['“\"].*?['”\"]", "sem texto", p, flags=re.I)
    p = re.sub(r"\btexto\b.*?(?:[.,]|$)", "", p, flags=re.I)

    # generalizar marcas
    subs = {
        r"\bSamsung\b": "marca de tecnologia (genérica)",
        r"\bGalaxy\b": "smartphone topo de linha (genérico)",
        r"\bApple\b": "marca de tecnologia (genérica)",
        r"\biPhone\b": "smartphone topo de linha (genérico)",
        r"\bNetflix\b": "serviço de streaming (genérico)",
        r"\bSpotify\b": "serviço de música (genérico)",
        r"\bGoogle\b": "empresa de tecnologia (genérica)",
        r"\bYouTube\b": "plataforma de vídeos (genérica)",
    }
    for patt, repl in subs.items():
        p = re.sub(patt, repl, p, flags=re.I)

    # impedir texto/logos
    no_text = "sem texto, sem logotipos, sem marcas registradas, fundo limpo"
    if no_text.lower() not in p.lower():
        p = f"{p.strip()} | {no_text}"

    # limpeza: remover palavras duplicadas consecutivas (ex.: "smartphone smartphone")
    p = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", p, flags=re.I)

    # se sobrou "selo genérico sem" sem "texto", completa:
    p = re.sub(r"selo genérico sem\b(?!\s*texto)", "selo genérico sem texto", p, flags=re.I)

    return re.sub(r"\s+", " ", p).strip()

def _to_str(v) -> str:
    """Converte v em string legível (aceita str/list/tuple/set/dict)."""
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

    # Se vier uma LISTA inteira como 'estilo_global', interpreta como paleta:
    if isinstance(est, list):
        est = {"paleta": est}

    paleta   = _to_str(est.get("paleta", ""))
    estetica = _to_str(est.get("estetica", ""))
    nota     = _to_str(est.get("nota", ""))

    parts = []
    if estetica:
        parts.append(estetica)
    if paleta:
        parts.append(f"cores: {paleta}")
    if nota:
        parts.append(nota)

    # regra padrão de clareza/legibilidade
    parts.append("composição centrada, legível em tela pequena, iluminação balanceada")
    return ", ".join(p for p in parts if p)

def choose_style_tail(prompt_base: str) -> str:
    """Rabo de prompt conforme tipo: realista x ilustrativo."""
    realistas = [
        "smartphone", "computador", "drone", "carro", "servidor",
        "fotografia", "produto", "dispositivo", "hardware"
    ]
    is_real = any(w in prompt_base.lower() for w in realistas)
    if is_real:
        return ("estilo foto editorial realista, iluminação cinematográfica, alta nitidez, "
                "profundidade de campo, sem texto, sem logotipos, 1024x1024")
    else:
        return ("ilustração vetorial/flat moderna, traços limpos, cores vivas porém equilibradas, "
                "sombras sutis, sem texto, sem logotipos, 1024x1024")

def generate_image(prompt: str, idx: int, tries: int = 2) -> Path:
    """Gera imagem com gpt-image-1 (b64) com retry simples."""
    last_err = None
    for attempt in range(1, tries+1):
        try:
            resp = client.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                size="1024x1024",  # garante quadrado
                background="transparent"
            )
            b64 = resp.data[0].b64_json
            raw_path = OUT_RAW / f"img_raw_{idx:02}.png"
            with open(raw_path, "wb") as f:
                f.write(base64.b64decode(b64))
            return raw_path
        except Exception as e:
            last_err = e
            # backoff curto
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

    # índice -> prompt do plano
    prompts_por_linha = {
        it["linha"]: it["prompt"]
        for it in plano.get("imagens", [])
        if isinstance(it, dict) and "linha" in it and "prompt" in it
    }

    print(f"🔎 Falas: {len(falas)} | Imagens planejadas: {len(prompts_por_linha)}")
    manifest = {"itens": []}
    contador = 1

    for i, fala in enumerate(falas):
        base = fala.get("imagem")
        if not base:
            # sem imagem nessa fala
            continue

        # preferir prompt do plano (já existente no teu JSON), se houver
        plano_prompt = prompts_por_linha.get(i, base)
        plano_prompt = sanitize_prompt(plano_prompt)

        # montar prompt final com estilo global + cauda por tipo
        prompt_final = f"{style_prefix}. {plano_prompt}. {choose_style_tail(plano_prompt)}"
        print(f"\n🖼️ [{contador}] Fala #{i} → Prompt:\n{prompt_final}\n")

        try:
            raw_path = generate_image(prompt_final, contador, tries=3)

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
                "prompt_usado": prompt_final,
                "arquivo_final": str(final_path),
                "arquivo_video": str(video_path)
            })
            contador += 1

        except Exception as e:
            print(f"❌ Erro ao gerar imagem da fala {i}: {e}")

    with MANIFEST_PATH.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\n🧾 Manifest salvo em: {MANIFEST_PATH}")
    print("🏁 Fim da geração de imagens.")

if __name__ == "__main__":
    main()
