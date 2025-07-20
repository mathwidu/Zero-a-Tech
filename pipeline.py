import subprocess
import sys
import os
import shutil
from datetime import datetime

LOG_FILE = "output/log_pipeline.txt"

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs("output", exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {msg}\n")
    print(msg)

def mover_output_para_backup():
    hoje = datetime.now().strftime("%Y%m%d")
    pasta_backup = os.path.join("output", "backups", hoje)
    os.makedirs(pasta_backup, exist_ok=True)

    for arquivo in os.listdir("output"):
        caminho = os.path.join("output", arquivo)
        if os.path.isfile(caminho):
            shutil.move(caminho, os.path.join(pasta_backup, arquivo))
    log(f"🗂️ Arquivos antigos movidos para: {pasta_backup}")

def debug_arquivo(path):
    if os.path.exists(path):
        tamanho = os.path.getsize(path)
        log(f"📄 Arquivo encontrado: {path} ({tamanho} bytes)")
    else:
        log(f"❌ Arquivo NÃO encontrado: {path}")

scripts_iniciais = [
    ("scripts/news_fetcher.py", []),
    ("scripts/script_generator.py", []),
    ("scripts/tts.py", [])
]

scripts_intermediarios = [
    ("scripts/generate_caption.py", [])
]

scripts_finais = [
    ("scripts/generate_subtitles.py", []),
    ("scripts/video_maker.py", [])
]

def run_script(script, args):
    log(f"\n▶ Executando: {script} {' '.join(args)}")
    result = subprocess.run(["python", script] + args, capture_output=True, text=True)

    log(f"📥 Saída:\n{result.stdout}")
    if result.stderr:
        log(f"⚠️ Erros:\n{result.stderr}")

    if result.returncode != 0:
        log(f"❌ Falha ao executar {script}. Parando pipeline.")
        sys.exit(1)

    log(f"✅ {script} finalizado com sucesso.")

if __name__ == "__main__":
    log("\n🚀 Iniciando pipeline completo...\n")

    mover_output_para_backup()

    arquivos_para_verificar = [
        "output/dialogo.txt",
        "output/fala_01.mp3",
        "output/fala_01_words.json",
        "output/legendas.srt",
        "output/video_final.mp4"
    ]

    for script, args in scripts_iniciais:
        run_script(script, args)

        log("\n🔎 Verificando arquivos esperados após esse passo:")
        for arquivo in arquivos_para_verificar:
            debug_arquivo(arquivo)

    log("\n🧠 Etapa intermediária: gerar todos os _words.json com Whisper")

    try:
        from scripts.generate_word_timestamps import extract_word_timestamps
    except ImportError:
        log("❌ Erro ao importar 'extract_word_timestamps' de generate_word_timestamps.py")
        sys.exit(1)

    mp3_files = sorted([f for f in os.listdir("output") if f.endswith(".mp3") and f.startswith("fala_")])

    for mp3 in mp3_files:
        audio_path = os.path.join("output", mp3)
        base = os.path.splitext(mp3)[0]
        output_json = os.path.join("output", f"{base}_words.json")

        if not os.path.exists(output_json):
            log(f"🗣️ Transcrevendo {mp3} com Whisper...")
            try:
                extract_word_timestamps(audio_path, output_json)
                log(f"✅ JSON gerado: {output_json}")
            except Exception as e:
                log(f"❌ Erro ao gerar timestamp para {mp3}: {e}")
        else:
            log(f"✔️ Já existe: {output_json}")

    for script, args in scripts_intermediarios:
        run_script(script, args)

    for script, args in scripts_finais:
        run_script(script, args)

        log("\n🔎 Verificando arquivos esperados após esse passo:")
        for arquivo in arquivos_para_verificar:
            debug_arquivo(arquivo)

    try:
        log("\n📲 Iniciando postagem no TikTok...")
        from scripts.post_tiktok import postar_no_tiktok
        postar_no_tiktok()
    except Exception as e:
        log(f"❌ Erro ao postar no TikTok: {e}")

    log("\n🎉 Pipeline finalizado com sucesso.")
