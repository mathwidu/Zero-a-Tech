#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generator — imagens quando pertinente, suporte a oficiais e
NORMALIZAÇÃO PARA TTS:
  • Moedas por extenso (pt-BR) e decimais com “com …”
  • Qualquer número com 2+ algarismos vira por extenso
"""

import os
import json
import re
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
OPENAI_MODEL_EXTRACT = os.getenv("OPENAI_MODEL_EXTRACT", "gpt-4o-mini")  # p/ extrair itens (baixa temp)

client = OpenAI(api_key=OPENAI_API_KEY)

# 📁 Paths
ESCOLHA_PATH = Path("output/noticia_escolhida.json")
DIALOGO_TXT_PATH = Path("output/dialogo.txt")
DIALOGO_JSON_PATH = Path("output/dialogo_estruturado.json")
IMAGENS_PLANO_PATH = Path("output/imagens_plano.json")
CONTEXTO_EXPANDIDO_PATH = Path("output/contexto_expandido.txt")

# ──────────────────────────────────────────────────────────────────────────────
# Busca Google (fallback)
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
# EXTRAÇÃO ESTRUTURADA
# ──────────────────────────────────────────────────────────────────────────────
RE_PERCENT  = re.compile(r"(\d{1,3})\s?%", re.I)
RE_POSLINE  = re.compile(r"^\s*(?:#?|\bposi[cç][aã]o\s*)?(\d{1,2})[)\.\-]?\s*[:\-–]?\s*(.+)$", re.I)
RE_BULLET   = re.compile(r"^\s*[\-\•\*]\s*(.+)$")
RE_GAME_SENTENCE = re.compile(r"([A-Z0-9][\w:'®™\-\.\s]{2,60})")

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
    m = RE_POSLINE.match(line)
    if m:
        pos = int(m.group(1))
        rest = _clean(m.group(2))
        rest = re.split(r"\s[-–—|]\s", rest)[0]
        return pos, rest
    m2 = RE_BULLET.match(line)
    if m2:
        name = _clean(m2.group(1))
        name = re.split(r"\s[-–—|]\s", name)[0]
        return 0, name
    return 0, ""

def _pick_game_name(chunk: str) -> str:
    cand = _clean(chunk)
    cand = re.sub(r"\b(versão|edição|pacote|bundle|steam|ranking|top|mais vendidos?|semana)\b", "", cand, flags=re.I)
    m = RE_GAME_SENTENCE.search(cand)
    if not m:
        return ""
    name = _clean(m.group(1))
    if (len(name.split()) >= 2) or (":" in name):
        return name
    return ""

def extrair_ranking_do_contexto(ctx: str, max_itens: int = 15) -> List[Dict[str, Any]]:
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
    if not candidatos:
        for par in re.split(r"\n{2,}", ctx):
            for m in re.finditer(r"(\d{1,2})\s*[-\.\)]\s*([^\n]+)", par):
                pos = int(m.group(1))
                name = _pick_game_name(m.group(2))
                if name:
                    candidatos.append((pos, name))
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
    for it in items:
        name = it["jogo"]
        pat = re.escape(name.split(":")[0])
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
        for m in RE_PERCENT.finditer(window):
            pistas.add(f"{m.group(1)}%")
        it["pistas"] = list(pistas)[:5]
    items.sort(key=lambda x: (x["pos"], x["jogo"]))
    return items[:max_itens]

def explicar_pista_curta(pistas: List[str]) -> str:
    if not pistas: return ""
    order = ["lançamento","update","desconto","recorde","acesso_antecipado","polêmica"]
    tokens = {p for p in pistas}
    chosen = None
    for k in order:
        if k in tokens:
            chosen = k; break
    mapping = {
        "lançamento": "estreia puxando atenção.",
        "update": "atualização recente reacendeu a procura.",
        "desconto": "desconto/ação promocional impulsionou vendas.",
        "recorde": "bateu pico e virou queridinho da semana.",
        "acesso_antecipado": "entrou em acesso antecipado e subiu no ranking.",
        "polêmica": "polêmica/bugs também colocaram o jogo em pauta.",
    }
    if not chosen:
        return ""
    return mapping[chosen]

# ──────────────────────────────────────────────────────────────────────────────
# 🔎 ENTIDADES e queries oficiais
# ──────────────────────────────────────────────────────────────────────────────
TECH_HINTS = ("gpu","rtx","dlss","fsr","ray tracing","engine","unreal","unity",
              "api","endpoint","rest","graphql","nuvem","cloud","kubernetes","container","npu","chip")

KNOWN_FRANCHISES = [
    r"call of duty(?:\:?\s*black ops\s*\d+)?",
    r"battlefield\s*\d+",
    r"gta\s*\d+|grand theft auto",
    r"fifa\s*\d+|ea\s*sports fc\s*\d+",
]

def find_games_in_text(text: str) -> List[str]:
    t = text or ""
    out = set()
    for m in re.finditer(r"\b([A-Z][\w’'\-]+(?:\s+[A-Z0-9][\w’'\-]+){1,5})\b", t):
        cand = m.group(1).strip()
        if any(w.lower() in ("joão","zé","bot","microsoft","switch") for w in cand.split()):
            continue
        if ":" in cand or len(cand.split()) >= 2:
            out.add(cand)
    low = t.lower()
    for pat in KNOWN_FRANCHISES:
        m = re.search(pat, low, flags=re.I)
        if m:
            out.add(t[m.start():m.end()].strip().title())
    return list(out)

def extract_entities(titulo: str, contexto: str, falas: list, ranking: list):
    jogos = set()
    for it in ranking or []:
        n = (it.get("jogo") or "").strip()
        if n and len(n.split()) >= 2:
            jogos.add(n)
    blob = " ".join([titulo or "", contexto or ""] + [(f.get("fala") or "") for f in falas])
    for n in find_games_in_text(blob):
        jogos.add(n)
    blob_l = blob.lower()
    techs = {t for t in TECH_HINTS if t in blob_l}
    return {"jogos": list(jogos), "techs": list(techs)}

def build_official_queries(nome_jogo: str) -> List[str]:
    base = nome_jogo.strip()
    return [
        f'{base} press kit',
        f'{base} key art',
        f'{base} official artwork',
        f'{base} logo official',
        f'{base} site:steamcdn-a.akamaihd.net',
        f'{base} site:store.steampowered.com "header"',
        f'{base} wallpaper official',
    ]

# ──────────────────────────────────────────────────────────────────────────────
# 🎨 Estética fallback
# ──────────────────────────────────────────────────────────────────────────────
POP_PALETTE = ["#FF5A5F", "#FFB300", "#2EC4B6", "#3A86FF", "#8338EC", "#0B0F19", "#FFFFFF"]

def enrich_ai_prompt_realista(base: str) -> str:
    palette = ", ".join(POP_PALETTE)
    return (
        f"{base}. aparência realista de gameplay/arte promocional; pode incluir logo do jogo; "
        f"iluminação cinematográfica; foco nítido; 9:16. Paleta sugerida: {palette}."
    )

# ──────────────────────────────────────────────────────────────────────────────
# PROMO (opcional)
# ──────────────────────────────────────────────────────────────────────────────
PROMO_HINTS = ("promo", "promoção", "desconto", "%", "grátis", "gratuito", "oferta", "sale")

def detectar_promocao(titulo: str, contexto: str) -> bool:
    s = f"{titulo}\n{contexto}".lower()
    return any(h in s for h in PROMO_HINTS)

def extrair_itens_promocao(contexto: str, max_itens: int = 12) -> list:
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
    return []

# ──────────────────────────────────────────────────────────────────────────────
# 🗣️ NORMALIZAÇÃO PARA TTS (pt-BR) — números por extenso
# ──────────────────────────────────────────────────────────────────────────────
CURRENCY_WORDS_PT = {
    "US$": "dólares", "USD": "dólares", "$": "dólares",
    "R$": "reais", "BRL": "reais",
    "€": "euros", "EUR": "euros",
    "£": "libras", "GBP": "libras",
    "¥": "ienes", "JPY": "ienes",
    "CAD": "dólares canadenses",
    "AUD": "dólares australianos",
    "MXN": "pesos mexicanos",
    "ARS": "pesos argentinos",
    "CLP": "pesos chilenos",
    "COP": "pesos colombianos",
}
CURRENCY_ALIASES = { "U$S":"US$", "U$":"US$", "U$D":"USD" }

UNIDADES = ["zero","um","dois","três","quatro","cinco","seis","sete","oito","nove"]
DEZ_A_DEZENOVE = ["dez","onze","doze","treze","quatorze","quinze","dezesseis","dezessete","dezoito","dezenove"]
DEZENAS = ["","dez","vinte","trinta","quarenta","cinquenta","sessenta","setenta","oitenta","noventa"]
CENTENAS = ["","cento","duzentos","trezentos","quatrocentos","quinhentos","seiscentos","setecentos","oitocentos","novecentos"]

def _normalize_currency_token(tok: str) -> str:
    t = tok.upper()
    if t in CURRENCY_ALIASES: t = CURRENCY_ALIASES[t]
    return t

def _duas_casas_to_words(n: int) -> str:
    if n < 10: return UNIDADES[n]
    if 10 <= n < 20: return DEZ_A_DEZENOVE[n-10]
    d, u = divmod(n, 10)
    if u == 0: return DEZENAS[d]
    return f"{DEZENAS[d]} e {UNIDADES[u]}"

def _centenas_to_words(n: int) -> str:
    if n == 100: return "cem"
    c, r = divmod(n, 100)
    if c == 0: return _duas_casas_to_words(r)
    if r == 0: return CENTENAS[c]
    return f"{CENTENAS[c]} e {_duas_casas_to_words(r)}"

def number_to_words_ptbr(n: int) -> str:
    if n < 0: return "menos " + number_to_words_ptbr(-n)
    if n < 100: return _duas_casas_to_words(n)
    if n < 1000: return _centenas_to_words(n)
    milhares, resto = divmod(n, 1000)
    if n < 1_000_000:
        prefixo = "mil" if milhares == 1 else f"{number_to_words_ptbr(milhares)} mil"
        if resto == 0: return prefixo
        conj = " " if resto < 100 else " "
        return f"{prefixo}{conj}{number_to_words_ptbr(resto)}"
    milhoes, resto = divmod(n, 1_000_000)
    prefixo = "um milhão" if milhoes == 1 else f"{number_to_words_ptbr(milhoes)} milhões"
    if resto == 0: return prefixo
    conj = " " if resto < 100 else " "
    return f"{prefixo}{conj}{number_to_words_ptbr(resto)}"

NUM_TOKEN = r"\d{1,3}(?:[.\s]\d{3})*(?:[,\.\s]\d{1,2})?|\d+"

CUR_BEFORE_NUM = re.compile(
    rf"(?<!\w)(?P<cur>US\$|U\$S|U\$|U\$D|R\$|€|£|¥|\$|USD|BRL|EUR|GBP|JPY|CAD|AUD|MXN|ARS|CLP|COP)\s*(?P<num>{NUM_TOKEN})",
    flags=re.I
)
NUM_BEFORE_CUR = re.compile(
    rf"(?P<num>{NUM_TOKEN})\s*(?P<cur>USD|BRL|EUR|GBP|JPY|CAD|AUD|MXN|ARS|CLP|COP)(?!\w)",
    flags=re.I
)
PLAIN_MULTI_DIGIT = re.compile(r"(?<![\w-])(\d{2,})(?![\w-])")  # 2+ algarismos, isolado

def _split_int_dec(num_text: str) -> Tuple[int, int | None]:
    s = re.sub(r"\s", "", num_text)
    # detecta decimal por último separador visível
    last_comma = s.rfind(","); last_dot = s.rfind(".")
    if last_comma > last_dot:
        int_part = re.sub(r"\D", "", s[:last_comma]) or "0"
        dec_part = re.sub(r"\D", "", s[last_comma+1:]) or ""
    elif last_dot > last_comma:
        int_part = re.sub(r"\D", "", s[:last_dot]) or "0"
        dec_part = re.sub(r"\D", "", s[last_dot+1:]) or ""
    else:
        int_part = re.sub(r"\D", "", s) or "0"
        dec_part = ""
    ival = int(int_part)
    dval = None
    if dec_part:
        d = int(dec_part[:2].ljust(2, "0"))
        dval = d
    return ival, dval

def _currency_words(cur: str) -> str:
    return CURRENCY_WORDS_PT.get(cur.upper(), CURRENCY_WORDS_PT.get(cur, "dólares"))

def _money_to_words(num_text: str, cur_token: str) -> str:
    cur = _normalize_currency_token(cur_token)
    inteiro, dec = _split_int_dec(num_text)
    int_words = number_to_words_ptbr(inteiro)
    cur_words = _currency_words(cur)
    if dec is None or dec == 0:
        return f"{int_words} {cur_words}"
    dec_words = number_to_words_ptbr(dec)
    return f"{int_words} com {dec_words} {cur_words}"

def _replace_cur_before_num(m: re.Match) -> str:
    cur = m.group("cur"); num = m.group("num")
    return _money_to_words(num, cur)

def _replace_num_before_cur(m: re.Match) -> str:
    num = m.group("num"); cur = m.group("cur")
    return _money_to_words(num, cur)

def _replace_plain_multi_digit(m: re.Match) -> str:
    n = int(m.group(1))
    return number_to_words_ptbr(n)

def normalize_numbers_for_tts(text: str) -> str:
    # 1) moedas com símbolo/código → por extenso
    out = CUR_BEFORE_NUM.sub(_replace_cur_before_num, text)
    out = NUM_BEFORE_CUR.sub(_replace_num_before_cur, out)
    # 2) já terminou moeda, evita duplicar “dólares dólares”
    out = re.sub(r"\b(dólares|reais|euros|libras|ienes|pesos(?:\s\w+)?)\s+\1\b", r"\1", out, flags=re.I)
    # 3) números com 2+ algarismos isolados → por extenso
    out = PLAIN_MULTI_DIGIT.sub(_replace_plain_multi_digit, out)
    return out

def normalize_dialog_for_tts(dialogo: list) -> list:
    norm = []
    for item in dialogo:
        fala = item.get("fala", "")
        fala_norm = normalize_numbers_for_tts(fala)
        norm.append({**item, "fala": fala_norm})
    return norm

# ──────────────────────────────────────────────────────────────────────────────
# 1) GERA DIÁLOGO
# ──────────────────────────────────────────────────────────────────────────────
def gerar_dialogo(titulo: str, contexto_completo: str, ranking_itens: List[Dict[str,Any]] | None = None, itens_promocao: list | None = None):
    regras_anticta = (
        "NÃO mencione link na descrição, afiliado, cupom, preço especial do link, "
        "ou qualquer CTA comercial. Foque em informação e utilidade."
    )
    # Regras para TTS
    regra_tts = (
        "Escreva números com DOIS OU MAIS algarismos por extenso (pt-BR). "
        "Para preços, escreva: '<valor por extenso> <moeda por extenso no plural>', usando 'com' para centavos. "
        "Exemplos: 'sessenta e nove com noventa e nove dólares', 'duzentos e noventa e nove reais', "
        "'cinquenta e nove com noventa euros', 'três mil quatrocentos e dezenove reais'. "
        "Evite símbolos como US$, R$, $. Não repita a moeda duas vezes."
    )

    bloco_itens = ""
    if itens_promocao:
        itens = itens_promocao[:8]
        bloco_itens = "ITENS DE PROMO PARA CITAR (não invente nada além disso):\n" + json.dumps(itens, ensure_ascii=False, indent=2)

    bloco_ranking = ""
    if ranking_itens:
        ricos = []
        for it in ranking_itens:
            exp = explicar_pista_curta(it.get("pistas", []))
            ricos.append({
                "pos": it.get("pos"),
                "jogo": it.get("jogo"),
                "motivo_curto": exp
            })
        bloco_ranking = "RANKING DETECTADO (use como referência):\n" + json.dumps(ricos, ensure_ascii=False, indent=2)

    prompt = f"""
Você é roteirista de vídeos curtos no TikTok, com dois personagens:
- JOÃO: curioso, animado, perguntas diretas e reações.
- ZÉ BOT: técnico, didático e irônico na medida, explica como repórter especializado.

OBJETIVO:
Diálogo jornalístico com GANCHO forte e fechamento rápido. Frases curtas.

REGRAS:
- Português BR; 13 a 16 falas alternando personagens.
- JSON puro (lista de objetos). Cada item: {{"personagem": "...", "fala": "..."}}
- {regras_anticta}
- {regra_tts}
- Se houver ranking, cite 5+ nomes e um motivo curto.
- Clareza > floreio.
- No final, uma pergunta ao público + pedido de like e seguir a Zero a Tech.

ASSUNTO: {titulo}

{bloco_ranking}

CONTEXTO:
{contexto_completo}

{bloco_itens}

SAÍDA: JSON puro (array de {{personagem, fala}}).
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
# 2) Plano de imagens
# ──────────────────────────────────────────────────────────────────────────────
def gerar_plano_imagens(titulo: str, contexto_completo: str, falas: list,
                        ranking_itens: list | None = None,
                        max_imgs: int | None = None,
                        only_when_entity: bool = True):
    if max_imgs is None:
        max_imgs = max(3, min(6, round(len(falas) * 0.35)))

    ents = extract_entities(titulo, contexto_completo, falas, ranking_itens or [])
    jogos = ents["jogos"]
    techs = ents["techs"]

    imagens: List[Dict[str, Any]] = []
    usados_jogos = set()

    for i, f in enumerate(falas):
        if len(imagens) >= max_imgs:
            break
        txt = (f.get("fala") or "")
        txt_l = txt.lower()

        alvo_jogo = None
        for nome in jogos:
            if nome.lower().split(":")[0] in txt_l and nome not in usados_jogos:
                alvo_jogo = nome; break
        if alvo_jogo:
            queries = build_official_queries(alvo_jogo)
            fallback_prompt = enrich_ai_prompt_realista(
                f"cena estilo marketing de {alvo_jogo}: operador com arma futurista, "
                f"ambiente de guerra moderna; pode incluir logo oficial; aspecto 9:16"
            )
            imagens.append({
                "linha": i,
                "tipo": "official",
                "official_query": queries[0],
                "official_queries_extra": queries[1:],
                "prompt": fallback_prompt,
                "rationale": f"Fala cita '{alvo_jogo}'. Preferir key art/press kit; IA só se não achar oficial."
            })
            usados_jogos.add(alvo_jogo)
            continue

        alvo_tech = None
        for t in techs:
            if t in txt_l:
                alvo_tech = t; break
        if alvo_tech:
            pr = enrich_ai_prompt_realista(
                f"metáfora visual da tecnologia '{alvo_tech}': chip e ondas de dados; "
                f"painel HUD moderno; pode conter tipografia curta e logo do recurso"
            )
            imagens.append({
                "linha": i,
                "tipo": "ai",
                "prompt": pr,
                "rationale": f"Fala menciona tecnologia '{alvo_tech}'."
            })
            continue

    if only_when_entity and not imagens:
        return {
            "estilo_global": {
                "paleta": "#FF5A5F, #FFB300, #2EC4B6, #3A86FF, #8338EC, #0B0F19, #FFFFFF",
                "estetica": "animated_soft",
                "nota": "traço grosso, shapes arredondados, cel-shading leve, contraste alto"
            },
            "imagens": []
        }

    imagens.sort(key=lambda x: x["linha"])
    return {
        "estilo_global": {
            "paleta": "#FF5A5F, #FFB300, #2EC4B6",  # curta
            "estetica": "animated_soft",
            "nota": "traço grosso, shapes arredondados, cel-shading leve, contraste alto"
        },
        "imagens": imagens[:max_imgs]
    }

# ──────────────────────────────────────────────────────────────────────────────
# 3) Aplica plano nas falas (compat legacy)
# ──────────────────────────────────────────────────────────────────────────────
def aplicar_plano_nas_falas(falas: list, plano: dict) -> list:
    por_linha = {it["linha"]: it for it in plano.get("imagens", [])}
    final = []
    imgs_count = 0
    for i, f in enumerate(falas):
        item = por_linha.get(i)
        img_payload = None
        if item:
            imgs_count += 1
            img_payload = item.get("prompt")
        final.append({
            "personagem": f.get("personagem", "JOÃO"),
            "fala": f.get("fala", "").strip(),
            "imagem": img_payload
        })
    print(f"🖼️ Falas com imagem: {imgs_count}/{len(falas)}")
    return final

# ──────────────────────────────────────────────────────────────────────────────
# MAIN
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

    # 2) ranking (se houver)
    ranking = extrair_ranking_do_contexto(contexto_completo, max_itens=15)
    if ranking:
        print(f"📊 Ranking detectado: {len(ranking)}")
    else:
        print("ℹ️ Sem ranking explícito.")

    # 3) promo (opcional)
    itens_promocao = []
    if detectar_promocao(titulo, contexto_completo):
        itens_promocao = extrair_itens_promocao(contexto_completo, max_itens=12)
        if itens_promocao:
            print(f"🛒 Itens de promoção detectados: {len(itens_promocao)}")

    # 4) diálogo (modelo já incentivado a escrever por extenso)
    falas = gerar_dialogo(titulo, contexto_completo, ranking_itens=ranking or None, itens_promocao=itens_promocao or None)
    if not falas:
        print("❌ Nenhum diálogo foi gerado.")
        return

    # 🔊 4.1) NORMALIZA FALAS PARA TTS
    falas = normalize_dialog_for_tts(falas)

    # 5) plano de imagens
    plano = gerar_plano_imagens(
        titulo, contexto_completo, falas,
        ranking_itens=ranking, max_imgs=None, only_when_entity=True
    )

    # 6) aplica e salva
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
