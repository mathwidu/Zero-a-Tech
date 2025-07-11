import json
from pathlib import Path

def ms_para_srt_timestamp(ms):
    horas = ms // 3600000
    minutos = (ms % 3600000) // 60000
    segundos = (ms % 60000) // 1000
    milissegundos = ms % 1000
    return f"{horas:02}:{minutos:02}:{segundos:02},{milissegundos:03}"

def gerar_legendas_com_timestamps(json_dir, output_path):
    json_dir = Path(json_dir).resolve()
    output_path = Path(output_path).resolve()

    print(f"[DEBUG] Procurando arquivos JSON em: {json_dir}")

    if not json_dir.exists():
        raise FileNotFoundError(f"Diretório de JSONs não encontrado: {json_dir}")

    arquivos_json = sorted(json_dir.glob("fala_*_words.json"))
    if not arquivos_json:
        raise FileNotFoundError("Nenhum arquivo de timestamp encontrado no formato 'fala_XX_words.json'")

    linhas_srt = []
    index = 1

    for json_path in arquivos_json:
        print(f"[DEBUG] Processando: {json_path.name}")
        with open(json_path, "r", encoding="utf-8") as f:
            palavras = json.load(f)

        if not palavras:
            continue

        inicio = int(palavras[0]['start'] * 1000)
        fim = int(palavras[-1]['end'] * 1000)

        inicio_str = ms_para_srt_timestamp(inicio)
        fim_str = ms_para_srt_timestamp(fim)

        texto = " ".join([p['word'] for p in palavras])

        linhas_srt.append(f"{index}")
        linhas_srt.append(f"{inicio_str} --> {fim_str}")
        linhas_srt.append(texto)
        linhas_srt.append("")

        index += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas_srt))

    print(f"✅ Legendas sincronizadas geradas: {output_path}")

if __name__ == "__main__":
    gerar_legendas_com_timestamps("output", "output/legendas.srt")
