import os
import subprocess
import json
from pathlib import Path

def gerar_lipsync(audio_path, dialogo_path, output_path):
    audio_path = Path(audio_path).resolve()
    dialogo_path = Path(dialogo_path).resolve()
    output_path = Path(output_path).resolve()

    if not audio_path.exists():
        raise FileNotFoundError(f"Áudio não encontrado: {audio_path}")
    if not dialogo_path.exists():
        raise FileNotFoundError(f"Diálogo não encontrado: {dialogo_path}")

    print(f"[DEBUG] Executando Rhubarb no arquivo: {audio_path.name}")

    subprocess.run([
        "rhubarb",
        "-o", str(output_path),
        "-f", "json",
        "-r", "phonetic",
        "--dialogFile", str(dialogo_path),
        str(audio_path)
    ], check=True)

    print(f"✅ Lip sync gerado: {output_path}")

if __name__ == "__main__":
    output_dir = Path("output")
    dialogo_file = output_dir / "dialogo.txt"

    for audio_file in sorted(output_dir.glob("fala_*.mp3")):
        num = audio_file.stem.split("_")[-1]
        output_file = output_dir / f"fala_{num}_lips.json"
        gerar_lipsync(audio_file, dialogo_file, output_file)
