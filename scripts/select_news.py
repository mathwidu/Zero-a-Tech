import json
from pathlib import Path

NOTICIAS_PATH = Path("output/noticias_disponiveis.json")
ESCOLHA_PATH = Path("output/noticia_escolhida.json")

def carregar_noticias():
    if not NOTICIAS_PATH.exists():
        print("❌ Arquivo de notícias não encontrado. Execute o news_fetcher.py antes.")
        return []

    with open(NOTICIAS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def exibir_opcoes(noticias):
    print("\n🗞️ Escolha uma das notícias abaixo:\n")
    for idx, noticia in enumerate(noticias, 1):
        print(f"[{idx}] 📌 {noticia['title']}")
        print(f"    📝 {noticia['description']}")
        print(f"    🔗 {noticia['url']}\n")

def escolher_noticia(noticias):
    while True:
        try:
            escolha = int(input("👉 Digite o número da notícia escolhida: "))
            if 1 <= escolha <= len(noticias):
                return noticias[escolha - 1]
            else:
                print("❗ Escolha inválida. Tente novamente.")
        except ValueError:
            print("❗ Entrada inválida. Digite apenas o número.")

def obter_prompt_extra():
    print("\n✍️ Deseja adicionar instruções extras ao ChatGPT para personalizar o roteiro?")
    print("Exemplo: 'Dê um tom sarcástico e mencione a Apple com imagens verde neon.'")
    return input("📌 Prompt extra (ou pressione ENTER para pular): ").strip()

def salvar_escolha(noticia, prompt_extra):
    ESCOLHA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ESCOLHA_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "noticia": f"{noticia['title']}\n\n{noticia['description']}",
            "url": noticia['url'],
            "prompt_extra": prompt_extra
        }, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Notícia escolhida salva em: {ESCOLHA_PATH}")

def main():
    noticias = carregar_noticias()
    if not noticias:
        return

    exibir_opcoes(noticias)
    noticia_escolhida = escolher_noticia(noticias)
    prompt_extra = obter_prompt_extra()
    salvar_escolha(noticia_escolhida, prompt_extra)

if __name__ == "__main__":
    main()
