import os
from dotenv import load_dotenv
from news_fetcher import get_google_news
import openai

# 🔐 Carrega .env
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")

# Inicializa o cliente OpenAI no novo formato
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# 🧠 Função que gera o diálogo a partir do título
def gerar_dialogo(titulo):
    prompt = f"""
Crie um diálogo informal e divertido entre duas personas:
- João (curioso)
- Zé Bot (inteligente, estilo ChatGPT, amigo e professor jovem), explicando com clareza

Assunto: {titulo}

Use tom jovem, frases curtas e piadas leves, faça analogias (suaves) com cultura pop e trends.
"""

    resposta = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9
    )

    return resposta.choices[0].message.content

# 🚀 Execução principal
if __name__ == "__main__":
    print("📰 Buscando notícias da Google News...")
    noticias = get_google_news(NEWSAPI_KEY)

    if not noticias:
        print("❌ Nenhuma notícia encontrada, não foi possível gerar o diálogo.")
        exit()

    # 🧾 Usa o título da primeira notícia
    titulo = noticias[0].split(":")[0]
    print(f"\n🎯 Gerando diálogo sobre: {titulo}\n")

    dialogo = gerar_dialogo(titulo)

    # 💾 Salva o diálogo em arquivo
    os.makedirs("output", exist_ok=True)
    with open("output/dialogo.txt", "w", encoding="utf-8") as f:
        f.write(dialogo)

    # 📺 Também imprime no terminal
    print(dialogo)
