import os
import json
import re
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
OPENAI_MODEL_DIALOG = os.getenv("OPENAI_MODEL_DIALOG", "gpt-4o-mini")  # mais barato/rápido; ajuste se quiser
OPENAI_MODEL_IMAGES = os.getenv("OPENAI_MODEL_IMAGES", "gpt-4o-mini")

client = OpenAI(api_key=OPENAI_API_KEY)

# 📁 Paths
ESCOLHA_PATH = Path("output/noticia_escolhida.json")
DIALOGO_TXT_PATH = Path("output/dialogo.txt")
DIALOGO_JSON_PATH = Path("output/dialogo_estruturado.json")
IMAGENS_PLANO_PATH = Path("output/imagens_plano.json")

# 🌐 Busca contexto adicional da notícia no Google
def buscar_contexto_google(titulo: str) -> str:
    query = f"https://www.google.com/search?q={titulo.replace(' ', '+')}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(query, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        # pega trechos curtos, evita poluir
        snippets = soup.select("div span")
        texto = " ".join([s.text for s in snippets[:10]])
        return re.sub(r"\s+", " ", texto).strip()
    except Exception as e:
        print("⚠️ Erro ao buscar contexto:", e)
        return ""

# 🧽 Helper: extrai JSON robustamente (remove cercas de código, etc.)
def try_parse_json(texto: str):
    # remove cercas ```json ... ```
    fenced = re.search(r"```json(.*?)```", texto, flags=re.S|re.I)
    if fenced:
        texto = fenced.group(1)
    texto = texto.strip()
    try:
        return json.loads(texto)
    except Exception:
        # tenta achar primeiro [ ... ] ou { ... }
        m = re.search(r"(\{.*\}|\[.*\])", texto, flags=re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
    return None

# 🗣️ 1) Gera DIÁLOGO (sem imagens)
def gerar_dialogo(titulo: str, contexto_completo: str):
    prompt = f"""
Você é roteirista de vídeos curtos no TikTok, com dois personagens:
- JOÃO: curioso, animado
- ZÉ BOT: técnico, irônico e divertido

TAREFA:
Crie um DIÁLOGO natural e envolvente (estilo podcast curto) **SEM imagens** ainda.
O diálogo deve cobrir de forma clara e divertida o tema abaixo, usando o contexto fornecido.

REGRAS:
- Português BR, tom leve (véi, pô, caraca, mano, etc. sem exagero).
- Comece com uma fala de impacto (hook).
- 10 a 16 falas.
- Sem narração fora de fala. Apenas a lista de falas em JSON.
- Cada item: 
  {{ "personagem": "JOÃO" | "ZÉ BOT", "fala": "..." }}
- Traga explicações/conclusões concretas quando caber.
- Evite jargões sem explicar rapidamente.

ASSUNTO: {titulo}

CONTEXTO (resumo + agregados da busca):
{contexto_completo}

SAÍDA: JSON puro com um array de objetos {{personagem, fala}}. Sem comentários.
"""
    resp = client.chat.completions.create(
        model=OPENAI_MODEL_DIALOG,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9
    )
    content = resp.choices[0].message.content
    parsed = try_parse_json(content)
    if isinstance(parsed, list):
        return parsed
    print("❌ Falha ao parsear diálogo. Conteúdo recebido:\n", content)
    return []

# 🖼️ 2) A partir do DIÁLOGO COMPLETO, gere um PLANO GLOBAL DE IMAGENS
# ⬇️ SUBSTITUA a função gerar_plano_imagens inteira por esta
def gerar_plano_imagens(titulo: str, contexto_completo: str, falas: list, min_imgs: int | None = None):
    """
    Retorna:
    {
      "estilo_global": {...},
      "imagens": [{"linha": int, "prompt": str, "rationale": str}, ...]
    }
    Garante pelo menos N imagens (fallback heurístico se o modelo não cumprir).
    """
    if min_imgs is None:
        # ~40% das falas (entre 4 e 8 normalmente)
        min_imgs = max(4, min(8, round(len(falas) * 0.45)))

    dialogo_texto = "\n".join([f'{i:02d} {f["personagem"]}: {f["fala"]}' for i, f in enumerate(falas)])
    prompt = f"""
Você é **diretor de arte** e precisa planejar **imagens ilustrativas** para um vídeo curto.
**NÃO** coloque JOÃO nem ZÉ BOT nas imagens.

Objetivo:
- Criar um **plano global** consistente (paleta/estilo) que cubra os pontos-chave do diálogo.
- Selecionar **no mínimo {min_imgs}** falas que ganharão imagem (40–60% do total).
- As imagens devem ser altamente visuais e didáticas (infográficos simples, objetos, cenas).
- Evitar marcas/LOGOS quando sensível; use termos genéricos se necessário.

Assunto: {titulo}

Contexto auxiliar:
{contexto_completo}

DIÁLOGO (com índices):
{dialogo_texto}

REGRAS:
- Varie os tipos: produto realista/editorial, diagrama, gráfico comparativo, close em componente, ilustração de cenário, metáfora visual (ex.: sorvete para “brinde”).
- Prompts claros e específicos, pensando em legibilidade de celular.
- **No mínimo {min_imgs} imagens.**
- Formato JSON:
{{
  "estilo_global": {{
    "paleta": "…",
    "estetica": "…",
    "nota": "…"
  }},
  "imagens": [
    {{"linha": <índice>, "prompt": "<prompt detalhado>", "rationale": "<por quê>"}}
  ]
}}
Apenas JSON puro.
"""
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL_IMAGES,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9
        )
        content = resp.choices[0].message.content
        parsed = try_parse_json(content)
    except Exception as e:
        print("⚠️ Erro na chamada do plano de imagens:", e)
        parsed = None

    plano = {"estilo_global": {}, "imagens": []}
    if isinstance(parsed, dict):
        plano["estilo_global"] = parsed.get("estilo_global", {}) or {}
        # saneamento + clamp de índices:
        imgs = []
        for it in parsed.get("imagens", []):
            try:
                idx = int(it.get("linha", -1))
                pr = (it.get("prompt") or "").strip()
                ra = (it.get("rationale") or "").strip()
                if 0 <= idx < len(falas) and pr:
                    imgs.append({"linha": idx, "prompt": pr, "rationale": ra})
            except Exception:
                pass
        plano["imagens"] = imgs

    # 🔒 Fallback se veio vazio/insuficiente:
    if len(plano["imagens"]) < min_imgs:
        print(f"ℹ️ Fallback: gerando imagens heurísticas (modelo retornou {len(plano['imagens'])}/{min_imgs}).")
        faltantes = min_imgs - len(plano["imagens"])
        ja_usadas = {i["linha"] for i in plano["imagens"]}

        # Heurística: escolher falas com palavras-chave visuais
        keywords = {
            "streaming": "tela de TV moderna com mosaico de filmes e séries, estilo editorial realista",
            "música": "fone de ouvido e ondas sonoras, estilo infográfico clean",
            "séries": "grade de mini-posters genéricos de série, estética flat ilustrada",
            "jogos": "controle de videogame com partículas de energia, look 3D clean",
            "assinatura": "ícone de calendário com selo de 12 meses, infográfico minimalista",
            "um ano": "linha do tempo de 12 meses destacada, estilo infográfico",
            "cancelar": "tela de configurações com botão de cancelar destacado (sem marcas)",
            "brinde": "mão oferecendo cupom genérico com fita, ilustração flat",
            "sorvete": "casquinha de sorvete colorida, fundo liso chamativo",
            "mercado": "gráfico simples de barras com tendência, UI genérica",
            "oportunidade": "lâmpada/insight brilhando, fundo degradê",
            "teste": "checklist com marcações, prancheta ilustrada"
        }

        # rankeia falas por quantidade de keywords
        ranks = []
        for i, f in enumerate(falas):
            if i in ja_usadas:
                continue
            fala_lower = f["fala"].lower()
            score = sum(1 for k in keywords if k in fala_lower)
            ranks.append((score, i))
        ranks.sort(reverse=True)  # mais palavras-chave primeiro

        # escolhe pelos melhores; se faltar, completa em intervalos regulares
        for _, idx in ranks:
            if faltantes <= 0:
                break
            if idx not in ja_usadas:
                prompt_heuristico = None
                fala_l = falas[idx]["fala"].lower()
                for k, p in keywords.items():
                    if k in fala_l:
                        prompt_heuristico = p
                        break
                if not prompt_heuristico:
                    prompt_heuristico = "ilustração editorial minimalista do conceito mencionado, fundo limpo"

                plano["imagens"].append({
                    "linha": idx,
                    "prompt": prompt_heuristico,
                    "rationale": "fallback automático baseado em palavras-chave da fala"
                })
                ja_usadas.add(idx)
                faltantes -= 1

        # se ainda faltar, adiciona a cada 2–3 falas
        step = 2 if len(falas) <= 12 else 3
        for i in range(0, len(falas), step):
            if faltantes <= 0:
                break
            if i not in ja_usadas:
                plano["imagens"].append({
                    "linha": i,
                    "prompt": "imagem editorial simples e chamativa relacionada à fala",
                    "rationale": "fallback de espaçamento regular"
                })
                ja_usadas.add(i)
                faltantes -= 1

    # ordena por linha pra ficar estável
    plano["imagens"] = sorted(plano["imagens"], key=lambda x: x["linha"])
    return plano


# 🧠 3) Aplica o plano ao diálogo, preenchendo campo "imagem" nas falas selecionadas
# ⬇️ SUBSTITUA a aplicar_plano_nas_falas por esta (só adiciona log útil)
def aplicar_plano_nas_falas(falas: list, plano: dict) -> list:
    por_linha = {it["linha"]: it["prompt"] for it in plano.get("imagens", [])}
    final = []
    imgs_count = 0
    for i, f in enumerate(falas):
        prompt_img = por_linha.get(i, None)
        if prompt_img:
            imgs_count += 1
        final.append({
            "personagem": f.get("personagem", "JOÃO"),
            "fala": f.get("fala", "").strip(),
            "imagem": prompt_img
        })
    print(f"🖼️ Falas com imagem: {imgs_count}/{len(falas)}")
    return final


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

    # Contexto adicional
    contexto_google = buscar_contexto_google(titulo)
    contexto_completo = f"{descricao}\n\n{contexto_google}\n\n{prompt_extra}".strip()

    # 1) Diálogo sem imagens
    falas = gerar_dialogo(titulo, contexto_completo)
    if not falas:
        print("❌ Nenhum diálogo foi gerado.")
        return

    # 2) Plano global de imagens com o diálogo completo como contexto
    plano = gerar_plano_imagens(titulo, contexto_completo, falas)

    # 3) Aplica plano e salva
    dialogo_com_imagens = aplicar_plano_nas_falas(falas, plano)

    os.makedirs("output", exist_ok=True)

    # Salva JSON estruturado (agora COM imagens por fala)
    with open(DIALOGO_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(dialogo_com_imagens, f, indent=2, ensure_ascii=False)
    print(f"✅ Diálogo estruturado salvo em: {DIALOGO_JSON_PATH}")

    # Salva TXT simples
    with open(DIALOGO_TXT_PATH, "w", encoding="utf-8") as f:
        for linha in dialogo_com_imagens:
            f.write(f"{linha['personagem']}: {linha['fala']}\n")
    print(f"✅ Diálogo simples salvo em: {DIALOGO_TXT_PATH}")

    # Salva plano de imagens para auditoria/consistência
    with open(IMAGENS_PLANO_PATH, "w", encoding="utf-8") as f:
        json.dump(plano, f, indent=2, ensure_ascii=False)
    print(f"✅ Plano de imagens salvo em: {IMAGENS_PLANO_PATH}")

if __name__ == "__main__":
    main()
