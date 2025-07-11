import whisper
import json
import os
import sys

def extract_word_timestamps(audio_path: str, output_path: str):
    model = whisper.load_model("base")  # pode mudar para 'small', 'medium', etc
    print("Transcrevendo com Whisper...")

    result = model.transcribe(audio_path, word_timestamps=True, verbose=True)

    palavras = []
    for segment in result["segments"]:
        for word in segment["words"]:
            palavras.append({
                "word": word["word"],
                "start": word["start"],
                "end": word["end"]
            })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(palavras, f, ensure_ascii=False, indent=2)

    print(f"Timestamps exportados para: {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python generate_word_timestamps.py caminho/para/audio.mp3")
        sys.exit(1)

    audio_file = sys.argv[1]
    filename = os.path.splitext(os.path.basename(audio_file))[0]
    output_file = os.path.join("output", f"{filename}_words.json")

    extract_word_timestamps(audio_file, output_file)
