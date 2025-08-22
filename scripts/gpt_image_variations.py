#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, io, json, base64, argparse, hashlib, sys
from pathlib import Path
from typing import List, Dict, Optional
from dotenv import load_dotenv
from PIL import Image
from openai import OpenAI

# ──────────────────────────────────────────────────────────────────────────────
# Configurações
# ──────────────────────────────────────────────────────────────────────────────
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Defina OPENAI_API_KEY no .env")

client = OpenAI(api_key=OPENAI_API_KEY)

IDENTITY_PROMPTS = {
    "joao": (
        "JOÃO — personagem 2D cartoon, traço limpo, outline preto, "
        "cabelo castanho curto, pele clara, camisa laranja (#FF5A5F), "
        "calça jeans azul (#3A86FF), tênis branco, paleta fixa: "
        "#FF5A5F #FFB300 #2EC4B6 #3A86FF #8338EC #0B0F19 #FFFFFF. "
        "Não mude roupa, idade, penteado ou paleta. Mantenha estilo idêntico."
    ),
    "zebot": (
        "ZÉ BOT — robô 2D cartoon simpático, traço limpo, outline preto, "
        "cabeça semicircular com olhos digitais, corpo compacto, "
        "tons principais: ciano/teal (#2EC4B6) e roxo (#8338EC), detalhes #0B0F19, "
        "Não mude design base nem paleta. Mantenha estilo idêntico."
    ),
}

POSE_TEMPLATES = {
    "frente": "Personagem de frente, corpo até a cintura, postura neutra.",
    "tres_quartos_esq": "Enquadramento ¾ esquerda, leve inclinação do tronco.",
    "tres_quartos_dir": "Enquadramento ¾ direita, leve inclinação do tronco.",
    "apontando": "Braço estendido apontando para a direita, mão em gesto de destaque.",
    "maos_na_cintura": "Mãos na cintura, postura confiante.",
    "segurando_celular": "Mão direita segurando um celular, olhando para a câmera."
}

EMOCOES = {
    "neutro": "expressão neutra, boca relaxada.",
    "feliz": "sorriso leve, olhos levemente fechados.",
    "surpreso": "sobrancelhas erguidas, boca em 'o' discreto.",
    "bravo": "sobrancelhas franzidas, boca firme.",
    "pensativo": "olhar de lado, sobrancelha ligeiramente arqueada."
}

# ──────────────────────────────────────────────────────────────────────────────
# Utilitários
# ──────────────────────────────────────────────────────────────────────────────
def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def stable_name(text: str) -> str:
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return h

def save_png_from_b64(b64_data: str, out_path: Path) -> None:
    png_bytes = base64.b64decode(b64_data)
    out_path.write_bytes(png_bytes)

def load_json(p: Path, default=None):
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return default if default is not None else {}

def save_json(p: Path, data: Dict):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def try_remove_bg_local(in_png_path: Path, out_png_path: Path) -> bool:
    """
    Tenta remover fundo localmente usando 'rembg' se estiver instalado.
    Retorna True se conseguiu gerar com alpha, False caso contrário.
    """
    try:
        from rembg import remove
    except Exception:
        print("[WARN] 'rembg' não encontrado. Instale com: pip install rembg", file=sys.stderr)
        return False

    try:
        im_bytes = in_png_path.read_bytes()
        out_bytes = remove(im_bytes)
        out_png_path.write_bytes(out_bytes)
        return True
    except Exception as e:
        print(f"[WARN] Falha ao remover fundo com rembg: {e}", file=sys.stderr)
        return False

# ──────────────────────────────────────────────────────────────────────────────
# Core
# ──────────────────────────────────────────────────────────────────────────────
def build_prompt(personagem: str, pose: str, emocao: str, extra: str = "") -> str:
    idp = IDENTITY_PROMPTS[personagem]
    pose_txt = POSE_TEMPLATES[pose]
    emo_txt = EMOCOES[emocao]
    rules = (
        "Regra: mantenha design e identidade do personagem exatamente iguais às referências. "
        "Sem mudanças de roupa, proporção facial, paleta ou traço. "
        "Fundo limpo e simples (se possível branco sólido)."
    )
    return f"{idp}\nPose: {pose_txt}\nExpressão: {emo_txt}\n{rules}\n{extra}".strip()

def collect_refs(ref_dir: Path, max_refs: int = 4) -> List[Path]:
    imgs = [p for p in ref_dir.glob("*") if p.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp"]]
    imgs = sorted(imgs)[:max_refs]
    return imgs

def _images_edit(prompt: str, refs: List[Path], size: str) -> str:
    """
    Chama images.edit com múltiplas referências.
    Retorna base64 PNG.
    """
    # abrir arquivos
    fhandles = [r.open("rb") for r in refs]
    try:
        result = client.images.edit(
            model="gpt-image-1",
            prompt=prompt,
            image=fhandles,   # lista de arquivos
            size=size,
        )
        return result.data[0].b64_json
    finally:
        # fechar
        for fh in fhandles:
            try:
                fh.close()
            except Exception:
                pass

def _images_generate(prompt: str, size: str, transparent: bool, seed: Optional[int]) -> str:
    """
    Chama images.generate (sem referências). Aceita background transparente e seed.
    Retorna base64 PNG.
    """
    kwargs = {
        "model": "gpt-image-1",
        "prompt": prompt,
        "size": size,
    }
    if transparent:
        # API aceita 'background="transparent"' no generate
        kwargs["background"] = "transparent"
    if seed is not None:
        kwargs["seed"] = seed

    result = client.images.generate(**kwargs)
    return result.data[0].b64_json

def generate_image(
    personagem: str,
    refs: List[Path],
    prompt: str,
    size: str = "1024x1024",
    transparent: bool = False,
    seed: Optional[int] = None,
) -> (str, str):
    """
    Retorna (b64_png, modo), onde modo ∈ {"edit","generate"} para logging.
    - Se houver refs -> usa edit (fidelidade).
    - Se não houver refs -> usa generate.
    Observação: transparency/seed só se aplicam a generate. Para edit,
    se transparent=True, tenta remover o fundo localmente com rembg.
    """
    if refs:
        b64 = _images_edit(prompt=prompt, refs=refs, size=size)
        modo = "edit"

        if transparent:
            # salva temporário, remove fundo com rembg se disponível
            tmp_dir = Path("output/tmp_removebg")
            ensure_dir(tmp_dir)
            tmp_in = tmp_dir / f"tmp_{stable_name(prompt)}.png"
            tmp_out = tmp_dir / f"tmp_{stable_name(prompt)}_alpha.png"
            save_png_from_b64(b64, tmp_in)
            if try_remove_bg_local(tmp_in, tmp_out):
                b64 = base64.b64encode(tmp_out.read_bytes()).decode("utf-8")
            else:
                print("[INFO] Transparência solicitada com 'edit', mas mantive fundo (use --extra 'fundo branco sólido' ou instale rembg).")

        return b64, modo

    # sem refs -> generate (suporta background e seed)
    b64 = _images_generate(prompt=prompt, size=size, transparent=transparent, seed=seed)
    return b64, "generate"

# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Gera variações fiéis com gpt-image-1 (edit ou generate com fallback).")
    parser.add_argument("--personagem", required=True, choices=["joao", "zebot"])
    parser.add_argument("--pose", required=True, choices=list(POSE_TEMPLATES.keys()))
    parser.add_argument("--emocao", required=True, choices=list(EMOCOES.keys()))
    parser.add_argument("--vertical", action="store_true", help="Gera 1024x1792 em vez de 1024x1024")
    parser.add_argument("--transparent", action="store_true", help="Fundo transparente (quando possível)")
    parser.add_argument("--seed", type=int, default=None, help="Apenas se aplica a 'generate'")
    parser.add_argument("--extra", type=str, default="", help="Instruções adicionais opcionais")
    args = parser.parse_args()

    size = "1024x1536" if args.vertical else "1024x1024"

    base_dir = Path("assets/personagens") / args.personagem / "ref"
    out_dir = Path("assets/imagens_geradas_padronizadas") / args.personagem
    ensure_dir(out_dir)

    refs = collect_refs(base_dir)
    prompt = build_prompt(args.personagem, args.pose, args.emocao, extra=args.extra)

    cache_key = f"{args.personagem}|{args.pose}|{args.emocao}|{size}|{int(args.transparent)}|{args.seed or ''}|{stable_name(args.extra)}|{len(refs)}"
    out_name = f"{args.pose}_{args.emocao}_{stable_name(cache_key)}.png"
    out_path = out_dir / out_name

    if out_path.exists():
        print(f"[CACHE] Já existe: {out_path}")
    else:
        modo = "?"
        try:
            print(f"[GEN] {args.personagem} :: {args.pose} + {args.emocao} | size={size} transparent={args.transparent} seed={args.seed} refs={len(refs)}")
            b64, modo = generate_image(
                personagem=args.personagem,
                refs=refs,
                prompt=prompt,
                size=size,
                transparent=args.transparent,
                seed=args.seed,
            )
            save_png_from_b64(b64, out_path)
            print(f"[OK] Salvo em: {out_path} ({modo})")
        except Exception as e:
            print(f"[ERRO] Falha ao gerar imagem: {e}", file=sys.stderr)
            sys.exit(1)

    # Atualiza manifest
    manifest_path = Path("output/imagens_manifest.json")
    manifest = load_json(manifest_path, default={"itens": []})
    manifest["itens"].append({
        "personagem": args.personagem.upper(),
        "pose": args.pose,
        "emocao": args.emocao,
        "arquivo": str(out_path.as_posix()),
        "size": size,
        "transparent": bool(args.transparent),
        "seed": args.seed,
        "refs_usadas": len(refs),
    })
    save_json(manifest_path, manifest)
    print(f"[MANIFEST] Atualizado: {manifest_path}")

if __name__ == "__main__":
    main()
