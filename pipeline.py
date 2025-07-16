import subprocess
import sys
import os
import shutil
from datetime import datetime

def mover_output_para_backup():
    hoje = datetime.now().strftime("%Y%m%d")
    pasta_backup = os.path.join("output", "backups", hoje)
    os.makedirs(pasta_backup, exist_ok=True)

    for arquivo in os.listdir("output"):
        caminho = os.path.join("output", arquivo)
        if os.path.isfile(caminho):
            shutil.move(caminho, os.path.join(pasta_backup, arquivo))
    print(f"🗂️ Arquivos antigos movidos para: {pasta_backup}")

def debug_arquivo(path):
    if os.path.exists(path):
        tamanho = os.path.getsize(path)
        print(f"📄 Arquivo encontrado: {path} ({tamanho} bytes)")
    else:
        print(f"❌ Arquivo NÃO encontrado: {path}")

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
    print(f"\n▶ Executando: {script} {' '.join(args)}")
    result = subprocess.run(["python", script] + args, capture_output=True, text=True)

    print(f"📥 Saída:\n{result.stdout}")
    if result.stderr:
        print(f"⚠️ Erros:\n{result.stderr}")

    if result.returncode != 0:
        print(f"❌ Falha ao executar {script}. Parando pipeline.")
        sys.exit(1)

    print(f"✅ {script} finalizado com sucesso.")

if __name__ == "__main__":
    print("🚀 Iniciando pipeline completo...\n")

    # 🧹 Mover arquivos antigos para backup antes de iniciar
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

        print("\n🔎 Verificando arquivos esperados após esse passo:")
        for arquivo in arquivos_para_verificar:
            debug_arquivo(arquivo)

    # 🧠 Etapa intermediária: gerar todos os _words.json com Whisper
    print("\n🧠 Executando Whisper para todas as falas...")

    try:
        from scripts.generate_word_timestamps import extract_word_timestamps
    except ImportError:
        print("❌ Erro ao importar 'extract_word_timestamps' de generate_word_timestamps.py")
        sys.exit(1)

    mp3_files = sorted([f for f in os.listdir("output") if f.endswith(".mp3") and f.startswith("fala_")])

    for mp3 in mp3_files:
        audio_path = os.path.join("output", mp3)
        base = os.path.splitext(mp3)[0]
        output_json = os.path.join("output", f"{base}_words.json")

        if not os.path.exists(output_json):
            print(f"🗣️ Transcrevendo {mp3}...")
            try:
                extract_word_timestamps(audio_path, output_json)
                print(f"✅ JSON gerado: {output_json}")
            except Exception as e:
                print(f"❌ Erro ao gerar timestamp para {mp3}: {e}")
        else:
            print(f"✔️ Já existe: {output_json}")

    # ▶️ Scripts intermediários (ex: geração de legenda TikTok)
    for script, args in scripts_intermediarios:
        run_script(script, args)

    # ▶️ Scripts finais
    for script, args in scripts_finais:
        run_script(script, args)

        print("\n🔎 Verificando arquivos esperados após esse passo:")
        for arquivo in arquivos_para_verificar:
            debug_arquivo(arquivo)

    # 📲 Postar automaticamente no TikTok
    try:
        print("\n📲 Iniciando postagem no TikTok...")
        from scripts.post_tiktok import postar_no_tiktok
        postar_no_tiktok()
    except Exception as e:
        print(f"❌ Erro ao postar no TikTok: {e}")

    print("\n🎉 Pipeline finalizado com sucesso.")
