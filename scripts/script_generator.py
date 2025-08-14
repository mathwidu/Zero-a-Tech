import os
import json
import re
import random
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from openai import OpenAI
from pathlib import Path
from typing import List, Dict, Any, Tuple

# 🔐 Env
dotenv_path = Path(".env")
if dotenv_path.exists():
    load_dotenv(dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_DIALOG = os.getenv("OPENAI_MODEL_DIALOG", "gpt-4o-mini")
OPENAI_MODEL_IMAGES = os.getenv("OPENAI_MODEL_IMAGES", "gpt-4o-mini")
OPENAI_MODEL_EXTRACT = os.getenv("OPENAI_MODEL_EXTRACT", "gpt-4o-mini")  # p/ extrair itens de promo (baixa temp)

client = OpenAI(api_key=OPENAI_API_KEY)

# 📁 Paths
ESCOLHA_PATH = Path("output/noticia_escolhida.json")
DIALOGO_TXT_PATH = Path("output/dialogo.txt")
DIALOGO_JSON_PATH = Path("output/dialogo_estruturado.json")
IMAGENS_PLANO_PATH = Path("output/imagens_plano.json")
CONTEXTO_EXPANDIDO_PATH = Path("output/contexto_expandido.txt")  # do Context Fetcher

# ──────────────────────────────────────────────────────────────────────────────
# Fallback de busca Google (só se não houver contexto_expandido)
# ──────────────────────────────────────────────────────────────────────────────
def buscar_contexto_google(titulo: str) -> str:
    query = f"https://www.google.com/search?q={titulo.replace(' ', '+')}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(query, headers=headers, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        snippets = soup.select("div span")
        texto = " ".join([s.text for s in snippets[:10]])
        return re.sub(r"\s+", " ", texto).strip()
    except Exception as e:
        print("⚠️ Erro ao buscar contexto:", e)
        return ""

# ──────────────────────────────────────────────────────────────────────────────
# Helpers JSON
# ──────────────────────────────────────────────────────────────────────────────
def try_parse_json(texto: str):
    fenced = re.search(r"```json(.*?)```", texto, flags=re.S | re.I)
    if fenced:
        texto = fenced.group(1)
    texto = texto.strip()
    try:
        return json.loads(texto)
    except Exception:
        m = re.search(r"(\{.*\}|\[.*\])", texto, flags=re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
    return None

# ──────────────────────────────────────────────────────────────────────────────
# 🎯 EXTRAÇÃO ESTRUTURADA DE RANKING (foco: “mais vendidos na Steam” etc.)
# ──────────────────────────────────────────────────────────────────────────────

RE_MONEY    = re.compile(r"(R\$\s?\d{1,3}(?:\.\d{3})*,\d{2})|\b(\d{1,3},\d{2}\s?reais)\b", re.I)
RE_PERCENT  = re.compile(r"(\d{1,3})\s?%", re.I)
RE_POSLINE  = re.compile(r"^\s*(?:#?|\bposi[cç][aã]o\s*)?(\d{1,2})[)\.\-]?\s*[:\-–]?\s*(.+)$", re.I)
RE_BULLET   = re.compile(r"^\s*[\-\•\*]\s*(.+)$")
RE_GAME_SENTENCE = re.compile(r"([A-Z0-9][\w:'®™\-\.\s]{2,60})")  # heurística leve pra nomes título-case

EDITORIAL_HINTS = {
    "lançamento": ("lançamento", "estreia", "chegou", "release", "estreou", "saiu"),
    "desconto": ("promo", "promoção", "desconto", "%", "grátis", "gratuito", "oferta", "sale", "preço", "free weekend"),
    "update": ("update", "atualização", "patch", "temporada", "season", "conteúdo novo", "dlc"),
    "recorde": ("recorde", "topo", "mais vendido", "pico", "players simultâneos", "pico de jogadores"),
    "polêmica": ("polêmica", "review bomb", "críticas", "bugs", "otimização", "queda de avaliações"),
    "acesso_antecipado": ("acesso antecipado", "early access", "beta"),
}

def _clean(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "").strip(" \t-–—•|")
    return s.strip()

def _extract_pos_line(line: str) -> Tuple[int, str]:
    """
    Tenta extrair "posição" e "nome do jogo" de uma linha.
    Retorna (pos, name) ou (0, "") se não bater.
    """
    m = RE_POSLINE.match(line)
    if m:
        pos = int(m.group(1))
        rest = _clean(m.group(2))
        # corta em " - " / " — " / " | "
        rest = re.split(r"\s[-–—|]\s", rest)[0]
        return pos, rest
    # bullets sem número? trata como pos 0 (posterior normaliza)
    m2 = RE_BULLET.match(line)
    if m2:
        name = _clean(m2.group(1))
        name = re.split(r"\s[-–—|]\s", name)[0]
        return 0, name
    return 0, ""

def _pick_game_name(chunk: str) -> str:
    """
    A partir de um pedaço de texto, tenta isolar um nome de jogo plausível.
    Heurística: sequência Title/Case com ≥2 palavras ou presença de :/subtítulo.
    """
    cand = _clean(chunk)
    # corta ruído comum
    cand = re.sub(r"\b(versão|edição|pacote|bundle|steam|ranking|top|mais vendidos?|semana)\b", "", cand, flags=re.I)
    # pega primeiro trecho com cara de nome
    m = RE_GAME_SENTENCE.search(cand)
    if not m:
        return ""
    name = _clean(m.group(1))
    # exige 2+ palavras ou ter dois-pontos
    if (len(name.split()) >= 2) or (":" in name):
        return name
    return ""

def extrair_ranking_do_contexto(ctx: str, max_itens: int = 15) -> List[Dict[str, Any]]:
    """
    Procura lista numerada/bullet no contexto e monta:
    [{"pos":1,"jogo":"Nome", "pistas":["lançamento","desconto 30%","update"]}, ...]
    """
    if not ctx:
        return []
    linhas = [l for l in (ctx.splitlines() or []) if l.strip()]
    candidatos: List[Tuple[int, str]] = []
    for ln in linhas:
        pos, raw = _extract_pos_line(ln)
        if pos == 0 and not raw:
            continue
        name = _pick_game_name(raw or ln)
        if not name:
            continue
        candidatos.append((pos, name))

    # se nada por linhas, tenta capturar por parágrafos com "Top 10", etc.
    if not candidatos:
        for par in re.split(r"\n{2,}", ctx):
            for m in re.finditer(r"(\d{1,2})\s*[-\.\)]\s*([^\n]+)", par):
                pos = int(m.group(1))
                name = _pick_game_name(m.group(2))
                if name:
                    candidatos.append((pos, name))

    # normaliza posições (se veio 0, ignora ordenação)
    vistos = set()
    items: List[Dict[str, Any]] = []
    auto_pos = 1
    for pos, name in candidatos:
        key = name.lower()
        if key in vistos:
            continue
        vistos.add(key)
        items.append({"pos": (pos or auto_pos), "jogo": name, "pistas": []})
        if pos == 0:
            auto_pos += 1

    # enriquece pistas por palavra-chave
    low = ctx.lower()
    for it in items:
        name = it["jogo"]
        pat = re.escape(name.split(":")[0])  # usa prefixo pra bater
        # varre janelas locais do contexto pra coletar sinais
        window = ""
        for m in re.finditer(pat, ctx, flags=re.I):
            ini = max(0, m.start() - 220)
            fim = min(len(ctx), m.end() + 220)
            window += " " + ctx[ini:fim]
        wlow = window.lower()
        pistas = set()
        for tag, keys in EDITORIAL_HINTS.items():
            if any(k in wlow for k in keys):
                pistas.add(tag)
        # porcentagem / dinheiro
        for m in RE_PERCENT.finditer(window):
            pistas.add(f"{m.group(1)}%")
        for m in RE_MONEY.finditer(window):
            pistas.add(m.group(0))
        it["pistas"] = list(pistas)[:5]  # limita ruído

    # ordena por pos quando houver
    items.sort(key=lambda x: (x["pos"], x["jogo"]))
    return items[:max_itens]

def explicar_pista_curta(pistas: List[str]) -> str:
    """
    Converte pistas em uma frase curtinha editorial (máx. ~12 palavras).
    Prioriza: lançamento > update > desconto > recorde > acesso_antecipado > polêmica.
    """
    if not pistas: return ""
    order = ["lançamento","update","desconto","recorde","acesso_antecipado","polêmica"]
    tokens = {p for p in pistas}
    chosen = None
    for k in order:
        if k in tokens:
            chosen = k; break
    if not chosen:
        # tenta achar % ou preço
        for t in tokens:
            if t.endswith("%") or t.startswith("R$"):
                return f"aproveita {t}."
        return ""
    mapping = {
        "lançamento": "estreia puxando atenção.",
        "update": "atualização recente reacendeu a procura.",
        "desconto": "desconto/ação promocional impulsionou vendas.",
        "recorde": "bateu pico e virou queridinho da semana.",
        "acesso_antecipado": "entrou em acesso antecipado e subiu no ranking.",
        "polêmica": "polêmica/bugs também colocaram o jogo em pauta.",
    }
    # complementa com % se houver
    extra = ""
    for t in tokens:
        if t.endswith("%"):
            extra = f" ({t} off)"
            break
    return mapping.get(chosen, "")[:-1] + extra + "."

# ──────────────────────────────────────────────────────────────────────────────
# 🎨 NOVO ESTILO: “ANIMADO, TRAÇOS GROSSOS E SUAVES” + REFERÊNCIAS POP/GEEK
# ──────────────────────────────────────────────────────────────────────────────
POP_STYLE_PRESETS = {
    "animated_soft": (
        "estilo desenho animado moderno; contornos grossos e suaves; "
        "cel-shading leve; shapes arredondados; sombra suave; fundo com gradiente macio; "
        "granulação sutil; composição limpa; 9:16"
    ),
    "poster_vibes": (
        "pôster ilustrado minimalista; tipografia grande e orgânica; "
        "banners curvos; adesivos/cartelas; 9:16"
    ),
    "comic_bold": (
        "quadrinhos com traço grosso; onomatopeias discretas; balões arredondados; "
        "linhas de ação mínimas; 9:16"
    ),
    "diagram_fun": (
        "diagrama lúdico; ícones redondinhos; setas largas; rótulos curtíssimos; "
        "sem poluição; 9:16"
    ),
    "infocard": (
        "cartão informativo colorido; blocos com cantos muito arredondados; "
        "ícones grandes; hierarquia clara; 9:16"
    )
}

POP_TAXONOMY = [
    (("ia","inteligência artificial","modelo","llm","transformer","agente"),
     "animated_soft",
     "metáfora de um mascote‑robô simpático (genérico), com chip brilhando e fiozinho de pensamento"),
    (("game","jogo","fps","rpg","ranked","console","controle"),
     "comic_bold",
     "controle de videogame estilizado com contorno grosso; faíscas de hype; placar divertido"),
    (("streaming","filme","série","anime","conteúdo"),
        "poster_vibes",
        "mural de telas genéricas com silhuetas abstratas; adesivos ‘maratona’, ‘episódio novo’"),
    (("api","endpoint","rest","graphql"),
     "diagram_fun",
     "fluxo simplificado Cliente → API → Serviço → DB com blocos arredondados e setas largas"),
    (("nuvem","cloud","kubernetes","container","deploy"),
     "diagram_fun",
     "pilha de caixinhas coloridas (pods genéricos) com um foguete cartoon subindo"),
    (("gpu","rtx","tensor","npu","chip"),
     "animated_soft",
     "chip gigante com olhos simpáticos (genérico), faixas de energia; estrelas de brilho"),
    (("segurança","privacidade","criptografia","hash","vazamento"),
     "infocard",
     "cadeado cartoon fofo, camadas de escudo; “dicas rápidas” com 2-3 tags curtas"),
    (("mercado","tendência","crescimento","queda","ações","cripto","preço"),
     "infocard",
     "gráfico cartoon com seta grossa; carinhas de ‘uau!’ e ‘ops!’ discretas"),
    (("comparação","vs","prós","contras","melhor que"),
     "poster_vibes",
     "placar versus com dois blocos coloridos; checkmarks; 3 bullets por lado"),
    (("rede","wi-fi","5g","download","upload","latência","ping"),
     "diagram_fun",
     "torre de sinal cartoon; ondas largas; medidores redondos de velocidade")
]

POP_PALETTE = ["#FF5A5F", "#FFB300", "#2EC4B6", "#3A86FF", "#8338EC", "#0B0F19", "#FFFFFF"]

NEGATIVE_CONTENT = [
    "não usar logos ou marcas registradas",
    "não usar personagens licenciados por nome/imagem",
    "não usar posters, capas ou artes oficiais",
    "evitar textos longos; rótulos curtos (2–3 palavras)",
    "sem watermark"
]

def _escolher_preset(tipo: str) -> str:
    return POP_STYLE_PRESETS.get(tipo, POP_STYLE_PRESETS["animated_soft"])

def _pop_hint(fala: str):
    fala_l = fala.lower()
    for keys, tipo, desc in POP_TAXONOMY:
        if any(k in fala_l for k in keys):
            return tipo, desc
    return "animated_soft", "metáfora divertida do conceito central com objetos fofos e contorno grosso"

def enriquecer_prompt_pop(prompt_base: str, fala: str):
    tipo, desc = _pop_hint(fala)
    preset = _escolher_preset(tipo)
    composition = (
        "enquadramento central com respiro; elementos grandes; margens seguras para 9:16; "
        "hierarquia visual clara; foco no objeto principal"
    )
    mobile_rules = (
        "pensado para tela de celular; contraste alto; traços grossos e suaves; "
        "sem poluição; rótulos com no máximo 2–3 palavras"
    )
    negative = "; ".join(NEGATIVE_CONTENT)
    palette = ", ".join(POP_PALETTE)
    final = (
        f"{prompt_base}. {desc}. {preset}. "
        f"paleta sugerida: {palette}. {composition}. {mobile_rules}. "
        f"Adicionar: contorno espesso, cel‑shading leve, shapes arredondados, adesivos/selos genéricos. "
        f"Evitar: {negative}."
    )
    return final

# ──────────────────────────────────────────────────────────────────────────────
# EXTRAÇÃO DE ITENS (promoções/entradas/saídas) do contexto
# ──────────────────────────────────────────────────────────────────────────────
PROMO_HINTS = ("promo", "promoção", "desconto", "%", "grátis", "gratuito", "oferta", "sale")

def detectar_promocao(titulo: str, contexto: str) -> bool:
    s = f"{titulo}\n{contexto}".lower()
    return any(h in s for h in PROMO_HINTS)

def extrair_itens_promocao(contexto: str, max_itens: int = 12) -> list:
    """
    Usa o modelo p/ converter contexto em lista:
    [{"nome": str, "desconto": "NN%", "preco": "R$ 10,99", "plataforma":"Steam/Epic/..."}, ...]
    Sem inventar: só o que estiver no texto. Temperatura baixa.
    """
    if not contexto or len(contexto) < 40:
        return []

    system = "Você extrai itens de promoções de jogos sem inventar nada. Responda apenas JSON válido."
    user = f"""
Do texto abaixo, extraia no MÁXIMO {max_itens} itens de jogos em promoção (ou jogos grátis), se houver.
Inclua apenas o que aparecer explicitamente no texto. Não invente.

Campos: nome (str), desconto (str opcional), preco (str opcional), plataforma (str opcional).
Responda APENAS o JSON (array). Sem comentários.

TEXTO:
{contexto}
"""
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL_EXTRACT,
            messages=[{"role":"system","content":system},{"role":"user","content":user}],
            temperature=0.2
        )
        parsed = try_parse_json(resp.choices[0].message.content)
        if isinstance(parsed, list):
            clean = []
            for it in parsed:
                nome = (it.get("nome") or "").strip()
                if not nome:
                    continue
                clean.append({
                    "nome": nome,
                    "desconto": (it.get("desconto") or "").strip(),
                    "preco": (it.get("preco") or "").strip(),
                    "plataforma": (it.get("plataforma") or "").strip(),
                })
            return clean
    except Exception as e:
        print("⚠️ Erro ao extrair itens de promoção:", e)

    # Fallback heurístico
    nomes = set()
    for m in re.finditer(r"“([^”]{3,70})”|\"([^\"]{3,70})\"", contexto):
        val = (m.group(1) or m.group(2) or "").strip()
        if 2 < len(val) <= 70 and not re.search(r"\s", val) is None:
            nomes.add(val)
    if not nomes:
        for m in re.finditer(r"\b([A-Z][A-Za-z0-9][\w\s:\-]{2,40})\b", contexto):
            cand = m.group(1).strip()
            if len(cand.split()) >= 2 and not re.search(r"\d{4}", cand):
                nomes.add(cand)
    return [{"nome": n} for n in list(nomes)[:max_itens]]

# ──────────────────────────────────────────────────────────────────────────────
# 1) GERA DIÁLOGO (repórter + influenciador, com foco no ranking detectado)
# ──────────────────────────────────────────────────────────────────────────────
def gerar_dialogo(titulo: str, contexto_completo: str, ranking_itens: List[Dict[str,Any]] | None = None, itens_promocao: list | None = None):
    regras_anticta = (
        "NÃO mencione link na descrição, afiliado, cupom, preço especial do link, "
        "ou qualquer CTA comercial. Foque em informação e utilidade."
    )
    guia_pop = (
        "Faça até DUAS referências pop/geek SUTIS no roteiro inteiro (não por fala), "
        "como metáforas ou comparações (ex.: 'nível bônus', 'boss final', 'multiverso'), "
        "sem citar marcas registradas ou nomes de personagens/licenças."
    )

    bloco_itens = ""
    if itens_promocao:
        itens = itens_promocao[:8]
        bloco_itens = "ITENS DE PROMO PARA CITAR (não invente nada além disso):\n" + json.dumps(itens, ensure_ascii=False, indent=2)

    bloco_ranking = ""
    if ranking_itens:
        # adiciona explicação curtinha calculada
        ricos = []
        for it in ranking_itens:
            exp = explicar_pista_curta(it.get("pistas", []))
            ricos.append({
                "pos": it.get("pos"),
                "jogo": it.get("jogo"),
                "motivo_curto": exp
            })
        bloco_ranking = "RANKING DETECTADO (use isso como FONTE PRINCIPAL; não invente nomes fora desta lista):\n" + json.dumps(ricos, ensure_ascii=False, indent=2)

    prompt = f"""
Você é roteirista de vídeos curtos no TikTok, com dois personagens:
- JOÃO: curioso, animado, faz perguntas diretas e reações.
- ZÉ BOT: técnico, didático e irônico na medida, explica como repórter especializado.

OBJETIVO:
Escreva um DIÁLOGO jornalístico (estilo podcast curto) com GANCHO forte e fechamento rápido.
Tom: claro, assertivo e divertido. Priorize a notícia e o 'porquê importa' em frases curtas.

ESTILO POP/GEEK:
{guia_pop}

REGRAS GERAIS:
-Sempre começe com um gancho forte (tem que prender o expectador logo de cara). (pode até extrapolar a noticia mas depois falar a realidade com leveza)
- Português BR.
- 13 a 16 falas alternando JOÃO/ZÉ BOT.
- Sem narração fora de fala. Apenas JSON (lista de objetos).
- Cada item: {{ "personagem": "JOÃO" | "ZÉ BOT", "fala": "..." }}
- {regras_anticta}
-Se tiver uma lista sempre cite inteira;
-cuidado para não ficar repetitivo;
- FOCO: a pauta é "{titulo}". NÃO traga jogos que NÃO estejam no ranking.
- CITE nominalmente os jogos do ranking (no mínimo 5 nomes) e, quando possível, explique em 1 frase o motivo de estarem nessa posição foque em coisas que o jogo é famoso por e (lançamento, desconto, update, etc.). Use o campo "motivo_curto" como inspiração.
- Use o ranking na ordem (topo primeiro) e contextualize rapidamente o cenário (ex.: semana, plataforma, tendência).
- Evite clickbait e floreio. Clareza > impacto.
-Sempre tente ter maior retenção de view e maior captura de expectador
-Linguagem jovem e acessível, mas sem gírias excessivas.
-Use jargões gamer para falar de jogos, mas evite jargões técnicos demais.

ASSUNTO: {titulo}

{bloco_ranking}

CONTEXTO AUXILIAR (para detalhes de fundo):
{contexto_completo}

{bloco_itens}

SAÍDA: JSON puro com um array de objetos {{personagem, fala}}. Sem comentários.
"""
    resp = client.chat.completions.create(
        model=OPENAI_MODEL_DIALOG,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6
    )
    content = resp.choices[0].message.content
    parsed = try_parse_json(content)
    if isinstance(parsed, list):
        return parsed
    print("❌ Falha ao parsear diálogo. Conteúdo recebido:\n", content)
    return []

# ──────────────────────────────────────────────────────────────────────────────
# 2) Plano de imagens (novo booster POP/ANIMADO)
# ──────────────────────────────────────────────────────────────────────────────
def gerar_plano_imagens(titulo: str, contexto_completo: str, falas: list, min_imgs: int | None = None):
    if min_imgs is None:
        min_imgs = max(4, min(8, round(len(falas) * 0.45)))
    dialogo_texto = "\n".join([f'{i:02d} {f["personagem"]}: {f["fala"]}' for i, f in enumerate(falas)])

    prompt = f"""
ATUE COMO: Diretor de arte para vídeos 9:16 com estética ANIMADA (traço grosso e suave).

OBJETIVO:
Planejar **imagens** que aparecem durante o vídeo. **Não inclua JOÃO/ZÉ BOT** nas imagens.
Foque em metáforas visuais pop/geek SUTIS, objetos fofos, contorno espesso, cel‑shading leve e alto contraste.
Evite qualquer marca ou personagem licenciado explícito (use apenas inspirações genéricas).

ASSUNTO: {titulo}

CONTEXTO AUXILIAR:
{contexto_completo}

DIÁLOGO (com índices):
{dialogo_texto}

REGRAS GERAIS:
- Mobile first: elementos grandes, leitura rápida, rótulos curtíssimos (≤ 3 palavras).
- Varie formatos: pôster minimalista, cartoon de objeto, diagrama lúdico, infocard, placar VS, gráfico divertido.
- **Selecione no mínimo {min_imgs}** falas para receber imagem.
- Formato de saída **JSON puro**:
{{
  "estilo_global": {{
    "paleta": "lista de hex",
    "estetica": "animated_soft/comic_bold/diagram_fun/infocard/poster_vibes (escolha no máx. 2)",
    "nota": "consistência, traço grosso, shapes arredondados, cel‑shading leve"
  }},
  "imagens": [{{ "linha": <índice>, "prompt": "<descrição 9:16>", "rationale": "<motivo>" }}]
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
        imgs = []
        for it in parsed.get("imagens", []):
            try:
                idx = int(it.get("linha", -1))
                pr = (it.get("prompt") or "").strip()
                ra = (it.get("rationale") or "").strip()
                if 0 <= idx < len(falas) and pr:
                    pr_final = enriquecer_prompt_pop(pr, falas[idx]["fala"])
                    imgs.append({"linha": idx, "prompt": pr_final, "rationale": ra})
            except Exception:
                pass
        plano["imagens"] = imgs

    # Fallback se veio insuficiente
    if len(plano["imagens"]) < min_imgs:
        print(f"ℹ️ Fallback: gerando imagens POP heurísticas (modelo retornou {len(plano['imagens'])}/{min_imgs}).")
        faltantes = min_imgs - len(plano["imagens"])
        ja_usadas = {i["linha"] for i in plano["imagens"]}

        ranks = []
        for i, f in enumerate(falas):
            if i in ja_usadas: 
                continue
            _, _desc = _pop_hint(f["fala"])
            score = 1 if _desc else 0
            fala_lower = f["fala"].lower()
            score += sum(1 for k in ("gráfico","placar","diagrama","comparação","timeline","dica","alerta") if k in fala_lower)
            ranks.append((score, i))
        ranks.sort(reverse=True)

        for _, idx in ranks:
            if faltantes <= 0: break
            base = "ilustração animada com traços grossos sobre o conceito central"
            pr_final = enriquecer_prompt_pop(base, falas[idx]["fala"])
            plano["imagens"].append({
                "linha": idx,
                "prompt": pr_final,
                "rationale": "fallback automático com estética animada pop"
            })
            ja_usadas.add(idx); faltantes -= 1

        step = 2 if len(falas) <= 12 else 3
        for i in range(0, len(falas), step):
            if faltantes <= 0: break
            if i not in ja_usadas:
                base = "cartão informativo pop com ícone grande e rótulo curto"
                pr_final = enriquecer_prompt_pop(base, falas[i]["fala"])
                plano["imagens"].append({
                    "linha": i,
                    "prompt": pr_final,
                    "rationale": "fallback de espaçamento regular com estética animada"
                })
                ja_usadas.add(i); faltantes -= 1

    if not plano["estilo_global"]:
        plano["estilo_global"] = {
            "paleta": ", ".join(POP_PALETTE),
            "estetica": "animated_soft + diagram_fun (até 2 estilos)",
            "nota": "traço grosso, shapes arredondados, cel‑shading leve, contraste alto"
        }

    plano["imagens"] = sorted(plano["imagens"], key=lambda x: x["linha"])
    return plano

# ──────────────────────────────────────────────────────────────────────────────
# 3) Aplica plano nas falas
# ──────────────────────────────────────────────────────────────────────────────
def aplicar_plano_nas_falas(falas: list, plano: dict) -> list:
    por_linha = {it["linha"]: it["prompt"] for it in plano.get("imagens", [])}
    final = []
    imgs_count = 0
    for i, f in enumerate(falas):
        prompt_img = por_linha.get(i)
        if prompt_img: imgs_count += 1
        final.append({
            "personagem": f.get("personagem", "JOÃO"),
            "fala": f.get("fala", "").strip(),
            "imagem": prompt_img
        })
    print(f"🖼️ Falas com imagem: {imgs_count}/{len(falas)}")
    return final

# ──────────────────────────────────────────────────────────────────────────────
# MAIN — compatível com Context Fetcher + legado
# ──────────────────────────────────────────────────────────────────────────────
def main():
    if not ESCOLHA_PATH.exists():
        print("❌ 'output/noticia_escolhida.json' não encontrado.")
        print("   Rode antes:  python3 scripts/context_fetcher.py")
        return

    dados = json.loads(ESCOLHA_PATH.read_text(encoding="utf-8"))

    # Context Fetcher (novo) ou News/Select (antigo)
    titulo = None; link = None; descricao = ""; prompt_extra = dados.get("prompt_extra", "")
    if "title" in dados or "link" in dados:
        titulo = (dados.get("title") or "").strip()
        link = (dados.get("link") or "").strip()
        descricao = (dados.get("snippet") or "").strip()
        if not titulo and dados.get("noticia"):
            titulo = dados["noticia"].split("\n")[0].strip()
    else:
        raw = (dados.get("noticia") or "").strip()
        if raw:
            parts = raw.split("\n", 1)
            titulo = parts[0].strip()
            if len(parts) > 1:
                descricao = parts[1].strip()
        link = (dados.get("url") or "").strip()

    if not titulo:
        print("❌ Não foi possível determinar o título da notícia.")
        return

    print(f"\n🎯 Gerando diálogo sobre: {titulo}")
    if link: print(f"🔗 {link}")

    # 1) contexto
    if CONTEXTO_EXPANDIDO_PATH.exists():
        contexto_completo = CONTEXTO_EXPANDIDO_PATH.read_text(encoding="utf-8").strip()
    else:
        contexto_google = buscar_contexto_google(titulo)
        contexto_completo = f"{descricao}\n\n{contexto_google}\n\n{prompt_extra}".strip()

    # 1.1) extrai ranking estruturado p/ orientar o roteiro
    ranking = extrair_ranking_do_contexto(contexto_completo, max_itens=15)
    if ranking:
        print(f"📊 Ranking detectado: {len(ranking)} jogos")
    else:
        print("ℹ️ Nenhuma lista/posição detectada; o roteiro seguirá apenas com contexto geral.")

    # 2) detectar promoção e extrair itens (quando for o caso)
    itens_promocao = []
    if detectar_promocao(titulo, contexto_completo):
        itens_promocao = extrair_itens_promocao(contexto_completo, max_itens=12)
        if itens_promocao:
            print(f"🛒 Itens de promoção detectados: {len(itens_promocao)}")
        else:
            print("ℹ️ Nenhum item estruturado encontrado; o diálogo seguirá sem listar preços/percentuais.")

    # 3) diálogo (focado no ranking)
    falas = gerar_dialogo(titulo, contexto_completo, ranking_itens=ranking or None, itens_promocao=itens_promocao or None)
    if not falas:
        print("❌ Nenhum diálogo foi gerado.")
        return

    # 4) plano de imagens (estilo animado/pop)
    plano = gerar_plano_imagens(titulo, contexto_completo, falas)

    # 5) aplica e salva
    dialogo_com_imagens = aplicar_plano_nas_falas(falas, plano)
    os.makedirs("output", exist_ok=True)

    DIALOGO_JSON_PATH.write_text(json.dumps(dialogo_com_imagens, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Diálogo estruturado salvo em: {DIALOGO_JSON_PATH}")

    with open(DIALOGO_TXT_PATH, "w", encoding="utf-8") as f:
        for linha in dialogo_com_imagens:
            f.write(f"{linha['personagem']}: {linha['fala']}\n")
    print(f"✅ Diálogo simples salvo em: {DIALOGO_TXT_PATH}")

    IMAGENS_PLANO_PATH.write_text(json.dumps(plano, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Plano de imagens salvo em: {IMAGENS_PLANO_PATH}")

if __name__ == "__main__":
    main()
