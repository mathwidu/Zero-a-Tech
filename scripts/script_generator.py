import os
import json
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from openai import OpenAI
from pathlib import Path

# 🔐 Carrega variáveis
dotenv_path = Path(".env")
if dotenv_path.exists():
    load_dotenv(dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

ESCOLHA_PATH = Path("output/noticia_escolhida.json")
DIALOGO_TXT_PATH = Path("output/dialogo.txt")
DIALOGO_JSON_PATH = Path("output/dialogo_estruturado.json")

# 🌐 Busca contexto adicional da notícia no Google
def buscar_contexto_google(titulo):
    query = f"https://www.google.com/search?q={titulo.replace(' ', '+')}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(query, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        snippets = soup.select("div span")
        contexto = " ".join([s.text for s in snippets[:6]])
        return contexto.strip()
    except Exception as e:
        print("⚠️ Erro ao buscar contexto:", e)
        return ""

# 🧠 Gera diálogo em formato estruturado (JSON + imagens)
def gerar_dialogo_struct(titulo, contexto_extra=""):
    prompt = f"""
Você é um roteirista criativo para vídeos curtos no TikTok, usando dois personagens animados: JOÃO (curioso, animado) e ZÉ BOT (mais técnico, irônico e divertido). Sua tarefa é gerar um diálogo em formato JSON, onde cada fala pode ter uma imagem ilustrativa opcional.

⚠️ IMPORTANTE:
- As imagens NÃO devem conter o JOÃO nem o ZÉ BOT. Eles já aparecem no vídeo em outra camada. As imagens são como SLIDES DE AULA para ilustrar apenas o conteúdo falado.
- A imagem deve ilustrar com impacto o elemento principal da fala (ex: iPhone 17, gráfico, chip novo, robô, etc).
- Proibido descrever personagens nas imagens. Foque apenas no conteúdo da fala.
- Use estilo visual chamativo, informativo e que prenda atenção.

FORMATO DE SAÍDA:
JSON com uma lista de falas. Cada fala é um objeto com:
- "personagem": "JOÃO" ou "ZÉ BOT"
- "fala": fala natural, estilo podcast leve, descontraído, engraçado
- "imagem": descrição da imagem ilustrativa focada no conteúdo falado (ou null se não precisar)

REGRAS:
- Comece com uma fala de impacto para prender atenção.
- Use expressões informais (véi, pô, caraca, mano, etc).
- A cada 2 ou 3 falas, inclua uma com imagem bem visual.
- Gere pelo menos 10 falas.
- NÃO escreva narração ou descrições fora das falas. Apenas JSON puro.

Assunto da conversa: {titulo}
Contexto adicional: {contexto_extra}
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

# 🚀 Execução principal com integração da notícia escolhida
def main():
    if not ESCOLHA_PATH.exists():
        print("❌ Arquivo 'noticia_escolhida.json' não encontrado. Execute o select_news.py antes.")
        return

    with open(ESCOLHA_PATH, "r", encoding="utf-8") as f:
        dados = json.load(f)

    titulo = dados["noticia"].split("\n")[0].strip()
    descricao = dados["noticia"].split("\n", 1)[-1].strip()
    prompt_extra = dados.get("prompt_extra", "")
    link = dados.get("url", "")

    print(f"\n🎯 Gerando diálogo sobre: {titulo}\n🔗 {link}\n")

    # Puxa contexto adicional
    contexto_google = buscar_contexto_google(titulo)
    contexto_completo = f"{descricao}\n\n{contexto_google}\n\n{prompt_extra}".strip()

    dialogo_estruturado = gerar_dialogo_struct(titulo, contexto_completo)

    if not dialogo_estruturado:
        print("❌ Nenhum diálogo estruturado foi gerado.")
        return

    # Salva .json estruturado
    os.makedirs("output", exist_ok=True)
    with open(DIALOGO_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(dialogo_estruturado, f, indent=2, ensure_ascii=False)
    print(f"✅ Diálogo estruturado salvo em: {DIALOGO_JSON_PATH}")

    # Salva .txt com as falas
    with open(DIALOGO_TXT_PATH, "w", encoding="utf-8") as f:
        for linha in dialogo_estruturado:
            f.write(f"{linha['personagem']}: {linha['fala']}\n")
    print(f"✅ Diálogo simples salvo em: {DIALOGO_TXT_PATH}")

if __name__ == "__main__":
    main()
