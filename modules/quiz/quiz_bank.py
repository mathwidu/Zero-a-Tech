#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Banco de perguntas simples para o módulo de quiz.
Adapte/expanda conforme a necessidade do canal.
"""

from typing import Dict, List
import random


QUIZ_BANK: Dict[str, List[str]] = {
    "casais": [
        "Quem disse ‘eu te amo’ primeiro?",
        "Qual foi o primeiro filme que vocês viram juntos?",
        "Quem demora mais para se arrumar?",
        "Qual é a comida favorita do outro?",
        "Quem é mais competitivo nos joguinhos?",
        "Qual foi a viagem mais marcante do casal?",
        "Quem esquece mais os aniversários?",
    ],
    "filmes": [
        "Em qual filme aparece a frase: ‘Que a Força esteja com você’?",
        "Qual diretor fez ‘A Origem’ e ‘Interestelar’?",
        "Qual é o nome do anel em O Senhor dos Anéis?",
        "Quem é o vilão principal em Vingadores: Ultimato?",
        "Qual animação tem a casa que voa com balões?",
    ],
    "animes": [
        "Qual é o jutsu mais famoso do Naruto?",
        "Quem é o capitão do bando do Chapéu de Palha?",
        "Em Dragon Ball Z, quem derrotou o Cell?",
        "Qual o nome do caderno em Death Note?",
        "Em Demon Slayer, qual a respiração do Tanjiro?",
    ],
    "politica": [
        "Qual é o sistema político do Brasil?",
        "O que significa separar poderes em Executivo, Legislativo e Judiciário?",
        "O que é o segundo turno em uma eleição?",
        "Qual a função principal do Senado?",
        "O que é uma PEC?",
    ],
}


def get_questions(category: str, count: int) -> List[str]:
    cat = category.lower().strip()
    base = QUIZ_BANK.get(cat) or QUIZ_BANK.get("casais", [])
    if count <= 0:
        return []
    # amostra aleatória sem repetição; completa repetindo se necessário
    n = min(len(base), count)
    out = random.sample(base, n) if base else []
    while len(out) < count:
        out.append(random.choice(base))
    return out[:count]
