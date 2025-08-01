import os
import glob
import subprocess

AUDIO_DIR = "output"
SCRIPT = "scripts/generate_word_timestamps.py"

def main():
    arquivos = sorted(glob.glob(os.path.join(AUDIO_DIR, "fala_*.mp3")))

    if not arquivos:
        print("❌ Nenhum arquivo de áudio encontrado para gerar timestamps.")
        return

    for caminho in arquivos:
        print(f"🎧 Gerando timestamps para: {os.path.basename(caminho)}")
        subprocess.run(["python3", SCRIPT, caminho])

    print("✅ Todos os arquivos de timestamp gerados com sucesso.")

if __name__ == "__main__":
    main()


