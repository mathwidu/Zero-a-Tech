import os
from dotenv import load_dotenv
from news_fetcher import get_google_news
import openai
import requests
from bs4 import BeautifulSoup

# 🔐 Carrega .env
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")

# Inicializa cliente OpenAI
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# 🌐 Busca um contexto extra baseado no título
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

# 🧠 Gera diálogo com base no título + contexto extra
def gerar_dialogo(titulo, contexto_extra=""):
    prompt = f"""
Você é um roteirista de podcast geek para TikTok. Crie um diálogo natural e espontâneo entre dois co-hosts:

- JOÃO: animado, curioso, puxa o tema da notícia, faz perguntas ou comentários leves.
- ZÉ BOT: co-host mais técnico, mas ainda informal e divertido, responde e aprofunda o assunto de forma clara, sem ser didático demais.

⚠️ IMPORTANTE:
- É um podcast animado, estilo videocast no TikTok. O público só ouve os dois falando.
- Não use descrições de cena, narração, nem ações visuais.
- Escreva apenas o diálogo, como se fosse uma conversa entre dois amigos discutindo uma notícia da semana.
- Evite exagero de piadas ou referências. Use no máximo uma referência por conversa, e só se fizer sentido.
- Foque em explicar e comentar a notícia de forma leve e com personalidade.

Assunto da conversa: {titulo}
Contexto adicional: {contexto_extra}

Formato: Só falas, no estilo de um podcast informal geek.
Tamanho: entre 15 e 20 falas no total.
"""

    resposta = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.85
    )

    return resposta.choices[0].message.content

# 🚀 Execução principal
if __name__ == "__main__":
    print("📰 Buscando notícias da Google News...")
    noticias = get_google_news(NEWSAPI_KEY)

    if not noticias:
        print("❌ Nenhuma notícia encontrada.")
        exit()

    # Pega os dados da primeira notícia
    noticia = noticias[0]
    titulo = noticia["title"]
    descricao = noticia.get("description", "")
    link = noticia.get("url", "")

    print(f"\n🎯 Gerando diálogo sobre: {titulo}\n🔗 {link}\n")

    # Busca contexto adicional
    contexto = buscar_contexto_google(titulo)
    contexto_completo = f"{descricao}\n\n{contexto}"

    dialogo = gerar_dialogo(titulo, contexto_completo)

    # 💾 Salva o diálogo
    os.makedirs("output", exist_ok=True)
    with open("output/dialogo.txt", "w", encoding="utf-8") as f:
        f.write(dialogo)

    # 📺 Também imprime no terminal
    print(dialogo)
