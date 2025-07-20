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

- JOÃO: animado, curioso, puxa o tema da notícia, faz perguntas ou comentários leves é mais jovem.
- ZÉ BOT: co-host mais técnico, mas ainda informal e divertido, responde e aprofunda o assunto de forma clara, sem ser didático demais, mas ainda ensinando de maneira leve.

⚠️ IMPORTANTE:
- É um podcast animado, estilo videocast no TikTok. O público só ouve os dois falando.
- Não use descrições de cena, narração, nem ações visuais.
- Escreva apenas o diálogo, como se fosse uma conversa entre dois amigos discutindo uma notícia da semana.
- Comece com uma fala que chame a atenção (gancho). Pode ser uma pergunta intrigante, uma reação de surpresa ou algo que desperte curiosidade.
- Use linguagem falada e natural, com gírias leves e interjeições (tipo ‘caraca’, ‘véi’, ‘meu Deus’, etc), como numa conversa entre amigos de verdade.

- Evite exagero de piadas ou referências. Use no máximo uma referência por conversa, e só se fizer sentido.
- Foque em explicar e comentar a notícia de forma leve e com personalidade.
-As vezes, quando o gancho for apropriado, faça uma explicação mais detalhada sobre o tema, mas mantenha o tom informal.
- Inclua um breve convite para curtir ou seguir no meio do diálogo, de forma natural.
- Sempre peça que os ouvintes se inscrevam e comentem no final.
Assunto da conversa: {titulo}
Contexto adicional: {contexto_extra}

Formato: Só falas, no estilo de um podcast informal sobre tecnologia.
Use: Tecnicas para manter o diálogo fluido e natural, como perguntas abertas, respostas curtas e interações espontâneas.
Dicas: Tente prender o publico com curiosidades, perguntas provocativas e comentários engraçados.
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
    contexto_google = buscar_contexto_google(titulo)
    if not contexto_google.strip():
        contexto_completo = descricao
    else:
        contexto_completo = f"{descricao}\n\n{contexto_google}"

    dialogo = gerar_dialogo(titulo, contexto_completo)

    # Valida se o diálogo foi gerado
    if not dialogo.strip():
        print("❌ Nenhum diálogo foi gerado.")
        exit()

    # 💾 Salva o diálogo
    os.makedirs("output", exist_ok=True)
    with open("output/dialogo.txt", "w", encoding="utf-8") as f:
        f.write(dialogo)

    # 📺 Também imprime no terminal
    print("✅ Diálogo gerado com sucesso:\n")
    print(dialogo)
