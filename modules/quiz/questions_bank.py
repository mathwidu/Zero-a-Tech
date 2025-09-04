#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Dict
import random


Question = Dict[str, object]


GENERAL_KNOWLEDGE: List[Question] = [
    {"q": "Qual é a capital da França?", "opts": ["Paris", "Roma", "Madri", "Berlim", "Lisboa"], "ans": 0},
    {"q": "Qual é o maior oceano do planeta?", "opts": ["Atlântico", "Índico", "Ártico", "Pacífico", "Antártico"], "ans": 3},
    {"q": "Qual é o símbolo químico da água?", "opts": ["O2", "CO2", "H2O", "NaCl", "NH3"], "ans": 2},
    {"q": "Em que ano o homem pisou na Lua pela primeira vez?", "opts": ["1959", "1965", "1969", "1972", "1979"], "ans": 2},
    {"q": "Quem pintou a Mona Lisa?", "opts": ["Michelangelo", "Leonardo da Vinci", "Van Gogh", "Picasso", "Rembrandt"], "ans": 1},
    {"q": "Qual planeta é conhecido como Planeta Vermelho?", "opts": ["Vênus", "Marte", "Júpiter", "Saturno", "Mercúrio"], "ans": 1},
    {"q": "Qual é a moeda do Japão?", "opts": ["Won", "Yuan", "Dólar", "Iene (Yen)", "Rupia"], "ans": 3},
    {"q": "Qual é o maior órgão do corpo humano?", "opts": ["Pulmão", "Coração", "Fígado", "Pele", "Rim"], "ans": 3},
    {"q": "Quem inventou o telefone?", "opts": ["Edison", "Tesla", "Graham Bell", "Marconi", "Einstein"], "ans": 2},
    {"q": "Qual é o número binário de 5?", "opts": ["11", "100", "101", "110", "111"], "ans": 2},
    {"q": "Qual elemento químico tem o símbolo Fe?", "opts": ["Ferro", "Flúor", "Fósforo", "Frâncio", "Fermio"], "ans": 0},
    {"q": "Qual é o animal terrestre mais rápido?", "opts": ["Leopardo", "Chita (Guepardo)", "Gazela", "Leão", "Lobo"], "ans": 1},
    {"q": "Qual é a montanha mais alta do mundo?", "opts": ["K2", "Kangchenjunga", "Everest", "Lhotse", "Makalu"], "ans": 2},
    {"q": "Qual idioma tem mais falantes nativos?", "opts": ["Inglês", "Espanhol", "Hindi", "Mandarim", "Árabe"], "ans": 3},
    {"q": "Quem escreveu Dom Quixote?", "opts": ["Camões", "Cervantes", "Shakespeare", "Dante", "Goethe"], "ans": 1},
    {"q": "Quanto é 2 + 2 × 2?", "opts": ["4", "6", "8", "2", "10"], "ans": 1},
]


def sample_general_knowledge(count: int) -> List[Question]:
    if count <= 0:
        return []
    n = min(count, len(GENERAL_KNOWLEDGE))
    out = random.sample(GENERAL_KNOWLEDGE, n)
    while len(out) < count:
        out.append(random.choice(GENERAL_KNOWLEDGE))
    return out[:count]

