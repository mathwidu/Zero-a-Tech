#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gera imagens via OpenAI para cada pergunta do quiz (visível e opcionalmente em paralelo).
Fallback: se não houver OPENAI_API_KEY ou a chamada falhar, cria um card local.
Atualiza quiz_manifest.json com image_path por pergunta.
"""

import os, json, base64
from pathlib import Path
from typing import Tuple, Optional
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path("output-quiz")
IMAGES_DIR = OUT_DIR / "images"
MANIFEST = OUT_DIR / "quiz_manifest.json"
FONT_PATH = "assets/fonts/LuckiestGuy-Regular.ttf"


def log(msg: str):
    ts = datetime.now(timezone.utc).isoformat()
    print(f"[{ts}] {msg}")


def ler_manifest():
    if not MANIFEST.exists():
        raise FileNotFoundError(f"Manifest não encontrado: {MANIFEST}")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def ler_fonte(size: int):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def desenhar_card(path: Path, idx: int, texto: str, size=(1024, 1024)):
    img = Image.new("RGB", size, (30, 30, 50))
    draw = ImageDraw.Draw(img)
    w, h = size
    # moldura
    draw.rectangle([8, 8, w-8, h-8], outline=(255, 255, 255), width=6)
    # título
    f1 = ler_fonte(int(min(w, h) * 0.1))
    title = f"Pergunta {idx}"
    tw = draw.textlength(title, font=f1)
    draw.text(((w - tw)//2, int(h*0.06)), title, font=f1, fill=(255, 255, 255))
    # ilustração fake (círculos)
    draw.ellipse([w*0.25, h*0.30, w*0.75, h*0.80], outline=(180, 200, 255), width=6)
    # subtítulo
    f2 = ler_fonte(int(min(w, h) * 0.06))
    txt = texto
    if len(txt) > 36:
        txt = txt[:35] + "…"
    sw = draw.textlength(txt, font=f2)
    draw.text(((w - sw)//2, int(h*0.84)), txt, font=f2, fill=(200, 220, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, quality=95)


def resumo(texto: str) -> str:
    if ":" in texto:
        texto = texto.split(":", 1)[1].strip()
    if len(texto) > 140:
        texto = texto[:139] + "…"
    return texto


def _clean_subject(s: str) -> str:
    s = s.strip().rstrip("?!. ")
    return s


def _regex_find(pattern: str, text: str) -> Optional[str]:
    import re
    m = re.search(pattern, text, flags=re.I)
    if not m:
        return None
    # pega primeiro grupo não vazio
    for g in m.groups():
        if g and g.strip():
            return _clean_subject(g)
    return None


def prompt_para_pergunta(pergunta: str) -> str:
    """Constrói prompt visual por heurística, evitando inserir o TEXTO da pergunta na imagem.
    Preferimos metáforas/ícones e composições descritivas.
    """
    q = (pergunta or "").strip()
    ql = q.lower()

    # 1) GEOGRAFIA – capital de X
    subj = _regex_find(r"capital\s+(?:da|do|de|das|dos)\s+([\wçãõáéíóúàêâ\-\s]+)", q)
    if subj:
        return (
            f"mapa estilizado da forma do país {subj} visto de cima, cores suaves, sem nomes, "
            f"destaque para um pin/localizador com um grande símbolo de interrogação no local da capital, "
            f"fundo limpo, ícones simples, sem texto, sem logotipos, composição central, estilo flat/ilustração."
        )

    # 2) ASTRONOMIA – planeta
    if "planeta" in ql:
        return (
            "sistema solar minimalista com planetas em órbita, um planeta em destaque com cor marcante, "
            "grande símbolo de interrogação acima dele, estilo flat sem texto, alto contraste, sem logotipos."
        )

    # 3) QUÍMICA – símbolo químico/elemento
    if "símbolo químico" in ql or "simbolo quimico" in ql or "elemento químico" in ql or "elemento quimico" in ql:
        return (
            "tabela periódica estilizada vista de longe, célula em destaque vazia com um grande ponto de interrogação, "
            "cores vivas porém equilibradas, sem letras, sem fórmulas textuais, estilo flat legível em tela pequena."
        )

    # 4) HISTÓRIA/FEITOS – ano em que aconteceu X
    if "em que ano" in ql or "que ano" in ql:
        return (
            "composição simbólica do evento histórico (sem números), relógio/ampulheta e calendário borrado ao fundo, "
            "um grande ponto de interrogação central, iluminação cinematográfica, sem texto."
        )

    # 5) ARTE – autor de obra famosa
    if "pintou" in ql or "autor" in ql:
        return (
            "moldura clássica de museu com silhueta de retrato borrado, pincéis e paleta ao redor, "
            "ponto de interrogação estilizado pairando, sem nomes/assinaturas, sem texto."
        )

    # 6) BIOLOGIA/ANIMAIS – mais rápido/maior
    if "mais rápido" in ql or "mais rapido" in ql or "mais alto" in ql or "maior" in ql:
        return (
            "silhuetas comparativas de animais/objetos com linhas de velocidade, um deles com interrogação, "
            "paleta vibrante, sem palavras, sem marcas, estilo flat."
        )

    # 7) MOEDAS/ECONOMIA
    if "moeda" in ql:
        return (
            "ícones de moedas e mapa do país associado, bandeiras estilizadas sem texto, "
            "um símbolo de interrogação em um pin geográfico, estilo flat."
        )

    # 8) LITERATURA – obra/autor
    if "quem escreveu" in ql or "autor" in ql:
        return (
            "livro aberto com páginas ao vento, pena e tinteiro, silhueta de autor no fundo, "
            "ponto de interrogação acima do livro, sem letras, sem texto."
        )

    # 9) MATEMÁTICA – geral
    if "quanto é" in ql or "resultado" in ql or "soma" in ql or "multiplic" in ql or "divis" in ql:
        return (
            "ícones matemáticos (sinais + − × ÷) flutuando, quadro-negro estilizado vazio, "
            "um grande ponto de interrogação central, sem números/letras legíveis."
        )

    # 10) PROGRAMAÇÃO/TECNOLOGIA
    if "programaç" in ql or "código" in ql or "algoritmo" in ql:
        return (
            "janela de editor de código estilizada sem texto, ícones de chaves e parênteses, "
            "ponto de interrogação em um cursor grande, estilo flat, sem letras."
        )

    # Default
    return (
        "ilustração temática sem texto com ícones/metáforas visuais da pergunta, grande ponto de interrogação, "
        "legível em tela pequena, composição central, sem logotipos, estilo flat moderno."
    )


PROVIDER = os.getenv("QUIZ_IMG_PROVIDER", "openai").lower().strip()


def _openai_size_str() -> str:
    val = (os.getenv("QUIZ_IMG_SIZE", "1024") or "1024").strip().lower()
    if val == "auto":
        return "auto"
    # aceita alguns apelidos
    if val in {"square", "1024", "1024x1024"}:
        return "1024x1024"
    if val in {"portrait", "vertical", "1024x1536", "1536"}:
        return "1024x1536"
    if val in {"landscape", "horizontal", "1536x1024"}:
        return "1536x1024"
    try:
        n = int(val)
        if n <= 1024:
            return "1024x1024"
        else:
            # usa orientação se informada, senão quadrado
            orient = (os.getenv("QUIZ_IMG_ORIENT", "square") or "square").lower()
            if orient.startswith("port") or orient.startswith("vert"):
                return "1024x1536"
            if orient.startswith("land") or orient.startswith("horiz"):
                return "1536x1024"
            return "1024x1024"
    except Exception:
        return "1024x1024"


def generate_openai_image(prompt: str, dest: Path) -> bool:
    try:
        from openai import OpenAI
    except Exception:
        log("❌ OpenAI SDK não encontrado. Instale 'openai' >= 1.0")
        return False
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        if not client.api_key:
            log("❌ OPENAI_API_KEY ausente no ambiente")
            return False
        size_str = _openai_size_str()
        resp = client.images.generate(model="gpt-image-1", prompt=prompt, size=size_str)
        b64 = resp.data[0].b64_json
        img_bytes = base64.b64decode(b64)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            f.write(img_bytes)
        # verify
        Image.open(dest).verify()
        return True
    except Exception as e:
        log(f"❌ OpenAI image error: {e}")
        return False


def generate_replicate_image(prompt: str, dest: Path) -> bool:
    """Gera imagem usando Replicate (modelos como FLUX Schnell ou SDXL)."""
    try:
        import replicate
    except Exception as e:
        log(f"❌ Replicate error: {e}")
        return False
    try:
        token = os.getenv("REPLICATE_API_TOKEN")
        if not token:
            return False
        client = replicate.Client(api_token=token)
        model = os.getenv("QUIZ_IMG_REPLICATE_MODEL", "black-forest-labs/flux-1-schnell")

        # Inputs comuns; modelos ignoram chaves extras sem erro.
        size = int(os.getenv("QUIZ_IMG_SIZE", "1024"))
        inputs = {
            "prompt": prompt,
            "width": size,
            "height": size,
            "num_inference_steps": int(os.getenv("QUIZ_IMG_STEPS", "8")),
            "guidance": float(os.getenv("QUIZ_IMG_GUIDANCE", "3.5")),
            "seed": 0,
        }

        output = client.run(model, input=inputs)
        # Pode retornar string (URL) ou FileOutput
        if isinstance(output, list):
            # alguns modelos retornam lista de URLs
            url = output[0]
            import requests
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
        else:
            # tenta tratar como FileOutput
            try:
                data = output.read()  # type: ignore[attr-defined]
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
            except Exception:
                return False
        Image.open(dest).verify()
        return True
    except Exception:
        return False


def _style_suffix_for_difficulty(diff: str) -> str:
    d = (diff or "").lower()
    if "fácil" in d or "facil" in d:
        return ", formas simples, paleta vibrante e amigável, poucos detalhes"
    if "difícil" in d or "dificil" in d:
        return ", composição um pouco mais detalhada, sombras sutis, contraste moderado"
    return ", estilo limpo, cores equilibradas"


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Gera imagens do quiz com logs visíveis")
    ap.add_argument("--max-workers", type=int, default=int(os.getenv("QUIZ_IMG_CONCURRENCY", "2")))
    ap.add_argument("--skip-existing", action="store_true")
    ap.add_argument("--provider", choices=["openai","replicate"], default=os.getenv("QUIZ_IMG_PROVIDER","openai"))
    args = ap.parse_args()

    load_dotenv()
    data = ler_manifest()
    segs = data.get("segments", [])
    difficulty = data.get("difficulty") or "média"
    style_tail = _style_suffix_for_difficulty(difficulty)
    tasks = []
    idx_map = []  # (seg_idx, pergunta_idx)
    idx_q = 0
    for si, seg in enumerate(segs):
        if seg.get("type") != "Q":
            continue
        idx_q += 1
        pergunta = seg.get("text", "Pergunta")
        out = IMAGES_DIR / f"q_{idx_q:02d}.png"
        if args.skip_existing and out.exists():
            log(f"⏭️ Pulando Q{idx_q} (já existe)")
            seg["image_path"] = str(out)
            # duplica no REVEAL
            for other in segs:
                if other.get("type") == "REVEAL" and other.get("index") == seg.get("index"):
                    other["image_path"] = str(out)
            continue
        prompt = prompt_para_pergunta(pergunta) + style_tail
        tasks.append((idx_q, prompt, out))
        idx_map.append((si, idx_q))

    if not tasks:
        log("ℹ️ Nada para gerar.")
    else:
        log(f"🚀 Gerando {len(tasks)} imagem(ns), workers={args.max_workers}…")
        with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as ex:
            provider = (args.provider or PROVIDER).lower().strip()
            if provider == "replicate":
                gen = generate_replicate_image
                log("🔁 Provider: Replicate (ex.: FLUX Schnell/SDXL)")
            else:
                gen = generate_openai_image
                log("🔁 Provider: OpenAI gpt-image-1")
            futs = {ex.submit(gen, prompt, out): (i, prompt, out) for (i, prompt, out) in tasks}
            for fut in as_completed(futs):
                i, prompt, out = futs[fut]
                ok = False
                try:
                    ok = fut.result()
                except Exception as e:
                    log(f"❌ Erro ao gerar Q{i}: {e}")
                if not ok:
                    segtxt = resumo(prompt)
                    desenhar_card(out, i, segtxt)
                    log(f"⚠️ Q{i}: fallback card gerado -> {out}")
                else:
                    log(f"✅ Q{i}: imagem gerada -> {out}")

    # Atualiza manifest (Q e REVEAL usam mesma imagem)
    idx_q = 0
    for seg in segs:
        if seg.get("type") != "Q":
            continue
        idx_q += 1
        out = IMAGES_DIR / f"q_{idx_q:02d}.png"
        seg["image_path"] = str(out)
        for other in segs:
            if other.get("type") == "REVEAL" and other.get("index") == seg.get("index"):
                other["image_path"] = str(out)

    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"🧾 Manifest atualizado em {MANIFEST}")


if __name__ == "__main__":
    main()
