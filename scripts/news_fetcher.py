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
        "category": "technology",   # Categoria tecnologia
        "language": "en",           # Em inglês para garantir variedade
        "pageSize": 3,              # Traz até 3 notícias
        "apiKey": api_key
    }

    response = requests.get(url, params=params)
    print("🔍 Status code:", response.status_code)

    try:
        data = response.json()
    except ValueError:
        print("❌ Erro ao interpretar JSON da resposta.")
        return []

    if "articles" not in data:
        print("❌ Resposta inválida da NewsAPI:", data)
        return []

    noticias = []
    for artigo in data["articles"]:
        noticias.append({
            "title": artigo.get("title", "").strip(),
            "description": artigo.get("description", "").strip(),
            "url": artigo.get("url", "").strip()
        })

    return noticias

# 🧪 Execução de teste
if __name__ == "__main__":
    print("📰 Google News (categoria: technology):")
    noticias = get_google_news(API_KEY)
    
    if not noticias:
        print("⚠️ Nenhuma notícia encontrada.")
    else:
        for n in noticias:
            print("\n📌 Título:", n["title"])
            print("📝 Descrição:", n["description"])
            print("🔗 Link:", n["url"])
