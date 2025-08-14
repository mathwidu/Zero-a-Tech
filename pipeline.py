#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, subprocess, sys, os, shutil
from datetime import datetime
from pathlib import Path

LOG_FILE   = Path("output/log_pipeline.txt")
OUTPUT_DIR = Path("output")
SCRIPTS_DIR= Path("scripts")

# ──────────────────────────────────────────────────────────────────────────────
# Log
# ──────────────────────────────────────────────────────────────────────────────
def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")
    print(msg)

# ──────────────────────────────────────────────────────────────────────────────
# Execução de scripts
# ──────────────────────────────────────────────────────────────────────────────
def run_script(script_relpath: str, args=None, interactive=False):
    """
    interactive=False -> captura stdout/stderr e grava no log ao final.
    interactive=True  -> herda stdin do terminal e 'tee' em tempo real para console + log.
    """
    if args is None: args = []
    script_path = SCRIPTS_DIR / script_relpath
    if not script_path.exists():
        log(f"❌ Script não encontrado: {script_path}")
        sys.exit(1)

    # -u: sem buffer para o filho, evita travas de output
    cmd = [sys.executable, "-u", str(script_path)] + args
    log(f"\n▶ Executando: {' '.join(cmd)}  (interactive={interactive})")

    if interactive:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        # Herdamos o teclado (stdin=sys.stdin) e coletamos stdout em tempo real
        with subprocess.Popen(
            cmd,
            stdin=sys.stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env
        ) as proc:
            # stream para console e log (efeito tee)
            with open(LOG_FILE, "a", encoding="utf-8") as flog:
                for line in proc.stdout:
                    print(line, end="")
                    flog.write(line)
            ret = proc.wait()
        if ret != 0:
            log(f"❌ Falha ao executar {script_relpath}. Parando pipeline.")
            sys.exit(1)
    else:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout:
            log(f"📥 Saída:\n{result.stdout}")
        if result.stderr:
            log(f"⚠️ Erros:\n{result.stderr}")
        if result.returncode != 0:
            log(f"❌ Falha ao executar {script_relpath}. Parando pipeline.")
            sys.exit(1)

    log(f"✅ {script_relpath} finalizado com sucesso.")

# ──────────────────────────────────────────────────────────────────────────────
# Utilidades
# ──────────────────────────────────────────────────────────────────────────────
def debug_arquivo(p):
    p = Path(p)
    if p.exists():
        log(f"📄 Arquivo encontrado: {p} ({p.stat().st_size} bytes)")
    else:
        log(f"❌ Arquivo NÃO encontrado: {p}")

def mover_output_para_backup():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = OUTPUT_DIR / "backups" / stamp
    dst.mkdir(parents=True, exist_ok=True)
    for item in OUTPUT_DIR.glob("*"):
        if item.name in ["backups", LOG_FILE.name]:
            continue
        shutil.move(str(item), str(dst / item.name))
    log(f"🗂️ Arquivos antigos movidos para: {dst}")

# checks
def check_pos_news_fetch():
    debug_arquivo("output/noticias_disponiveis.json")
    debug_arquivo("output/noticia_escolhida.json")

def check_pos_select_news():
    debug_arquivo("output/noticia_escolhida.json")

def check_pos_script_generator():
    debug_arquivo("output/dialogo.txt")
    debug_arquivo("output/dialogo_estruturado.json")

def check_pos_image_prompts():
    debug_arquivo("output/queries.json")
    debug_arquivo("output/imagens_manifest.json")

def check_pos_tts():
    for mp3 in sorted(Path("output").glob("fala_*.mp3")):
        debug_arquivo(mp3)

def check_pos_wordstamps():
    for js in sorted(Path("output").glob("fala_*_words.json")):
        debug_arquivo(js)

def check_pos_subtitles():
    debug_arquivo("output/legendas.srt")

def check_pos_video():
    debug_arquivo("output/video_final.mp4")

def check_pos_caption():
    debug_arquivo("output/caption.txt")

# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Pipeline Zero à Tech (com entrada interativa opcional)")
    ap.add_argument("--no-backup", action="store_true")
    ap.add_argument("--topic", type=str, default=None, help="Sugere um assunto para o news_fetcher (quando suportado).")
    ap.add_argument("--auto", action="store_true", help="Seleciona notícia automaticamente (select_news --auto).")
    ap.add_argument("--pick", "--index", type=int, dest="pick", help="Escolhe a notícia N (select_news --index N).")
    ap.add_argument("--interactive_all", action="store_true", help="Força todos os passos em modo interativo.")
    ap.add_argument("--skip-post", action="store_true")
    args = ap.parse_args()

    log("\n🚀 Iniciando pipeline completo...\n")
    if not args.no_backup:
        mover_output_para_backup()

    # 1) news_fetcher
    nf_args = []
    if args.topic:
        nf_args += ["--topic", args.topic]
    run_script("news_fetcher.py", nf_args, interactive=args.interactive_all)
    check_pos_news_fetch()

    # 2) select_news — se você não passou --auto/--pick, entra no modo interativo
    sn_args = []
    interactive_select = args.interactive_all
    if args.pick is not None:
        sn_args = ["--index", str(args.pick)]
        interactive_select = False
    elif args.auto:
        sn_args = ["--auto"]
        interactive_select = False
    else:
        interactive_select = True  # sem flags -> deixe eu digitar o número aqui na pipeline

    run_script("select_news.py", sn_args, interactive=interactive_select)
    check_pos_select_news()

    # 3) script_generator
    run_script("script_generator.py", [], interactive=args.interactive_all)
    check_pos_script_generator()

    # 4) generate_image_prompts
    run_script("generate_image_prompts.py", [], interactive=args.interactive_all)
    check_pos_image_prompts()

    # 5) tts
    run_script("tts.py", [], interactive=args.interactive_all)
    check_pos_tts()

    # 6) word-level timestamps
    run_script("generate_all_word_timestamps.py", [], interactive=args.interactive_all)
    check_pos_wordstamps()

    # 7) subtitles
    run_script("generate_subtitles.py", [], interactive=args.interactive_all)
    check_pos_subtitles()

    # 8) video
    run_script("video_maker.py", [], interactive=args.interactive_all)
    check_pos_video()

    # 9) caption
    run_script("generate_caption.py", [], interactive=args.interactive_all)
    check_pos_caption()

    # 10) post
    if not args.skip_post:
        run_script("post_tiktok.py", [], interactive=args.interactive_all)
    else:
        log("⏭️ Postagem pulada por --skip-post")

    log("\n🎉 Pipeline finalizado com sucesso.")

if __name__ == "__main__":
    main()
