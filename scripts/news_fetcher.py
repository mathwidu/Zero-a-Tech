import requests
import os
import json
from dotenv import load_dotenv
from pathlib import Path

# 🔐 Carrega as variáveis do .env
load_dotenv()
API_KEY = os.getenv("NEWSAPI_KEY")

# 🌐 Google News via NewsAPI
def get_google_news(api_key, quantidade=5):
    url = "https://newsapi.org/v2/top-headlines"
    params = {
        "category": "technology",
        "language": "en",
        "pageSize": quantidade,
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
            "description": (artigo.get("description") or "").strip(),
            "url": artigo.get("url", "").strip()
        })

    return noticias

# 🔝 Função principal usada por outros scripts
def get_top_n_news(n=5):
    return get_google_news(API_KEY, quantidade=n)

# 🧪 Execução de teste manual
if __name__ == "__main__":
    print("📰 Buscando as principais notícias de tecnologia...")
    noticias = get_top_n_news(n=5)

    if not noticias:
        print("⚠️ Nenhuma notícia encontrada.")
    else:
        # Salva para uso posterior no script de seleção
        output_path = Path("output/noticias_disponiveis.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(noticias, f, ensure_ascii=False, indent=2)

        print(f"✅ {len(noticias)} notícias salvas em {output_path}.\n")
        for i, n in enumerate(noticias, 1):
            print(f"\n[{i}] 📌 {n['title']}\n📝 {n['description']}\n🔗 {n['url']}")
