import os
from dotenv import load_dotenv
from news_fetcher import get_google_news
import openai
import requests
import json
from bs4 import BeautifulSoup

# 🔐 Carrega .env
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")

client = openai.OpenAI(api_key=OPENAI_API_KEY)

# 🌐 Busca contexto adicional da notícia
def buscar_contexto_google(titulo):
    query = f"https://www.google.com/search?q={titulo.replace(' ', '+')}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(query, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")
        snippets = soup.select("div span")
        contexto = " ".join([s.text for s in snippets[:6]])
        return contexto.strip()
    except Exception as e:
        print("⚠️ Erro ao buscar contexto:", e)
        return ""

# 🧠 Gera diálogo em JSON estruturado com possíveis prompts de imagem
def gerar_dialogo_struct(titulo, contexto_extra=""):
    prompt = f"""
Você é um roteirista criativo para vídeos curtos no TikTok, usando dois personagens animados: JOÃO (curioso, animado) e ZÉ BOT (mais técnico, irônico e divertido). Sua tarefa é gerar um diálogo em formato JSON, onde cada fala pode opcionalmente ter uma imagem ilustrativa associada.

Regras:
- Responda no formato JSON, como uma lista de objetos. Cada objeto deve ter:
  - "personagem": "JOÃO" ou "ZÉ BOT"
  - "fala": fala natural, estilo podcast leve e engraçado
  - "imagem": descrição curta da imagem ilustrativa a ser gerada (pode ser null se não precisar)

- Comece com uma fala de impacto que prenda a atenção (gancho).
- Use expressões naturais e descontraídas ("véi", "pô", "caraca", "mano", etc).
- A cada 2 ou 3 falas, inclua uma que poderia ter uma imagem complementar.
- Seja criativo na descrição da imagem, pensando em como ela ilustraria a fala.
- NÃO escreva narração ou descrições fora das falas. Apenas JSON puro.
- Feche com uma fala incentivando o público a comentar ou seguir o canal.
-Gere sempre pelo menos 10 falas, mas sinta-se livre para criar mais se necessário.
Assunto da conversa: {titulo}
Contexto adicional: {contexto_extra}
Formato de saída: JSON com os campos "personagem", "fala", "imagem"
"""
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9
    )

    content = response.choices[0].message.content

    try:
        estrutura = json.loads(content)
        return estrutura
    except json.JSONDecodeError as e:
        print("❌ Erro ao decodificar JSON gerado pela IA:", e)
        print("📝 Resposta recebida:\n", content)
        return []

# 🚀 Execução principal
if __name__ == "__main__":
    print("📰 Buscando notícias da Google News...")
    noticias = get_google_news(NEWSAPI_KEY)

    if not noticias:
        print("❌ Nenhuma notícia encontrada.")
        exit()

    noticia = noticias[0]
    titulo = noticia["title"]
    descricao = noticia.get("description", "")
    link = noticia.get("url", "")

    print(f"\n🎯 Gerando diálogo sobre: {titulo}\n🔗 {link}\n")

    contexto_google = buscar_contexto_google(titulo)
    contexto_completo = f"{descricao}\n\n{contexto_google}" if contexto_google.strip() else descricao

    dialogo_estruturado = gerar_dialogo_struct(titulo, contexto_completo)

    if not dialogo_estruturado:
        print("❌ Nenhum diálogo estruturado foi gerado.")
        exit()

    os.makedirs("output", exist_ok=True)

    with open("output/dialogo_estruturado.json", "w", encoding="utf-8") as f:
        json.dump(dialogo_estruturado, f, indent=2, ensure_ascii=False)

    print("✅ Diálogo estruturado salvo com sucesso em JSON.")

    # Também salva um .txt simples com as falas
    with open("output/dialogo.txt", "w", encoding="utf-8") as f:
        for linha in dialogo_estruturado:
            f.write(f"{linha['personagem']}: {linha['fala']}\n")

    print("✅ Diálogo tradicional salvo em dialogo.txt.")
