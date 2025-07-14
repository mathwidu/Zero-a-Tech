# scripts/generate_caption.py

import os
from dotenv import load_dotenv
from openai import OpenAI

# 🔐 Carrega variáveis do .env
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Inicializa o cliente OpenAI com a chave carregada
client = OpenAI(api_key=OPENAI_API_KEY)

def gerar_legenda(dialogo_path, saida_path):
    if not os.path.exists(dialogo_path):
        print(f"❌ Arquivo não encontrado: {dialogo_path}")
        return

    with open(dialogo_path, "r", encoding="utf-8") as f:
        conteudo = f.read()

    prompt = f"""
O seguinte diálogo é entre dois personagens fictícios: João (humano curioso) e Zé Bot (um robô engraçado e didático).
Gere uma legenda curta para TikTok com emojis e hashtags, que chame atenção e resuma o tema do diálogo.

Texto:
\"\"\"{conteudo}\"\"\"

Regras:
- No máximo 20 palavras
- Use 1 ou 2 emojis
- Inclua de 3 a 5 hashtags relevantes para o tema
- Seja informal, como um criador de conteúdo

Legenda:
"""

    resposta = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=100
    )

    legenda = resposta.choices[0].message.content.strip()

    with open(saida_path, "w", encoding="utf-8") as f:
        f.write(legenda)

    print(f"📝 Legenda gerada e salva em {saida_path}:\n\n{legenda}\n")

if __name__ == "__main__":
    gerar_legenda("output/dialogo.txt", "output/legenda_tiktok.txt")
