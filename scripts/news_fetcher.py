import requests
import os
from dotenv import load_dotenv

# 🔐 Carrega as variáveis do .env
load_dotenv()
API_KEY = os.getenv("NEWSAPI_KEY")

# 🌐 Google News via NewsAPI
def get_google_news(api_key):
    url = "https://newsapi.org/v2/top-headlines"
    params = {
        "category": "technology",   # usa categoria ao invés de query
        "language": "en",           # em inglês pra garantir resultados
        "pageSize": 3,
        "apiKey": api_key
    }
    response = requests.get(url, params=params)

    # 🧪 Debug: imprime status e conteúdo da resposta
    print("🔍 Status code:", response.status_code)
    data = response.json()
    print("📦 Conteúdo da resposta JSON:")
    print(data)

    if "articles" not in data:
        print("❌ Erro na resposta da NewsAPI:")
        return []

    return [f"{a['title']}: {a['url']}" for a in data["articles"]]

# 🧪 Execução de teste
if __name__ == "__main__":
    print("📰 Google News (categoria: technology):")
    google_news = get_google_news(API_KEY)
    for n in google_news:
        print(" -", n)
    if not google_news:
        print("⚠️ Nada encontrado na API da NewsAPI")
