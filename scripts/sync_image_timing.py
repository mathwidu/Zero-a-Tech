#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_image_timing.py  —  travado por fala + RELINK por ORDEM
Gera/realinha timestamps e relinka imagens sem heurística, usando:
- diálogo estruturado (quais falas têm imagem)
- fala_XX_words.json (tempo real da fala)
- output/imagem_XX.png (1ª imagem para 1ª fala com imagem, e assim por diante)

Uso:
  python3 scripts/sync_image_timing.py
  python3 scripts/sync_image_timing.py --dry-run
Somente stdlib.
"""
import argparse, json, glob
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

# Paths
DIALOGO_JSON_PATH = Path("output/dialogo_estruturado.json")
PLANO_JSON_PATH   = Path("output/imagens_plano.json")
MANIFEST_PATH     = Path("output/imagens_manifest.json")
WORDS_FMT         = "output/fala_{:02}_words.json"
IMG_GLOB          = "output/imagem_*.png"

# ---------------- IO helpers ----------------
def load_json(path: Path, default):
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[WARN] Falha ao ler {path}: {e}")
    return default

def save_json(path: Path, obj: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)

# --------------- core helpers ---------------
def fala_span(line_1b: int) -> Optional[Tuple[float,float]]:
    """Lê output/fala_XX_words.json e retorna (t0, t1) = [min(start), max(end)]."""
    words = load_json(Path(WORDS_FMT.format(line_1b)), [])
    if not words:
        return None
    starts = [float(w.get("start", 0.0)) for w in words if "start" in w]
    ends   = [float(w.get("end", 0.0))   for w in words if "end"   in w]
    if not ends:
        return None
    t0 = min(starts) if starts else 0.0
    t1 = max(ends)
    if t1 <= t0:
        t1 = t0 + 0.6
    return round(t0,3), round(t1,3)

def falas_com_imagem(dialogo: List[Dict[str,Any]]) -> List[int]:
    """Retorna índices 1-based das falas que possuem campo 'imagem'."""
    out = []
    for i, it in enumerate(dialogo, start=1):
        if it.get("imagem"):
            out.append(i)
    return out

def imagens_ordenadas() -> List[str]:
    """Lista output/imagem_XX.png ordenadas."""
    files = sorted(glob.glob(IMG_GLOB))
    return files

# ------------------- main -------------------
def main():
    ap = argparse.ArgumentParser(description="Travamento por fala + RELINK por ordem (sem shift).")
    ap.add_argument("--dry-run", action="store_true", help="não salva arquivos; só imprime")
    args = ap.parse_args()

    dialogo = load_json(DIALOGO_JSON_PATH, [])
    if not dialogo:
        print("❌ dialogo_estruturado.json não encontrado ou vazio.")
        return

    linhas_img = falas_com_imagem(dialogo)
    if not linhas_img:
        print("⚠️ Nenhuma fala com 'imagem' no diálogo.")
        return
    print(f"🧩 Falas c/ imagem (1-based): {linhas_img}")

    # spans por fala
    spans: Dict[int, Tuple[float,float]] = {}
    faltantes = []
    for ln in linhas_img:
        sp = fala_span(ln)
        if sp is None:
            faltantes.append(ln)
        else:
            spans[ln] = sp
    if faltantes:
        print(f"[WARN] Sem fala_XX_words.json para: {faltantes} (fallback 0.2–2.0s)")

    # imagens por ORDEM
    imgs = imagens_ordenadas()
    if len(imgs) < len(linhas_img):
        print(f"[WARN] Existem menos imagens ({len(imgs)}) do que falas com imagem ({len(linhas_img)}). "
              "As últimas ficarão sem arquivo_video.")
    estilo_global = load_json(PLANO_JSON_PATH, {"estilo_global": {}}).get("estilo_global", {})

    novo_plano = {"estilo_global": estilo_global, "imagens": []}
    novo_manifest = {"itens": []}

    for idx_ord, ln in enumerate(linhas_img, start=1):
        fala_obj = dialogo[ln-1]
        prompt   = fala_obj.get("imagem") or ""
        t0, t1   = spans.get(ln, (0.2, 2.0))
        arq      = imgs[idx_ord-1] if idx_ord-1 < len(imgs) else None

        # plano
        novo_plano["imagens"].append({
            "linha": ln, "prompt": prompt,
            "t_inicio": t0, "t_fim": t1
        })

        # manifest
        novo_manifest["itens"].append({
            "idx_global": idx_ord,
            "fala_index": ln,
            "personagem": fala_obj.get("personagem"),
            "fala": fala_obj.get("fala"),
            "prompt_usado": prompt,
            "arquivo_final": None,
            "arquivo_video": arq,
            "t_inicio": t0, "t_fim": t1,
            "motivo_sync": "locked_by_dialog_order"
        })

        base = arq.split("/")[-1] if arq else "∅"
        print(f"✅ fala {ln:02d} :: {t0:.2f}-{t1:.2f} :: img={base}")

    if args.dry_run:
        print("\n[dry-run] Não salvei arquivos.")
        return

    save_json(PLANO_JSON_PATH, novo_plano)
    save_json(MANIFEST_PATH, novo_manifest)
    print(f"\n🧾 Plano salvo em: {PLANO_JSON_PATH}")
    print(f"🧾 Manifest salvo em: {MANIFEST_PATH}")
    print("🏁 RELINK concluído (ordem do diálogo).")

if __name__ == "__main__":
    main()
