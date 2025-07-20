#!/bin/bash

LOG="/Users/mathwidu/Projetos/Projetos/zeroatech/output/log_cron.txt"
mkdir -p /Users/mathwidu/Projetos/Projetos/zeroatech/output

# garante que o ffmpeg seja encontrado pelo cron
export PATH="/opt/homebrew/bin:$PATH"

echo "==============================" >> "$LOG"
echo "Início: $(date)" >> "$LOG"

cd /Users/mathwidu/Projetos/Projetos/zeroatech || {
    echo "Falha ao entrar na pasta do projeto" >> "$LOG"
    exit 1
}

source /Users/mathwidu/Projetos/Projetos/zeroatech/.venv/bin/activate || {
    echo "Falha ao ativar o ambiente virtual" >> "$LOG"
    exit 1
}

/usr/bin/env python3 pipeline.py >> "$LOG" 2>&1 || {
    echo "Erro ao executar pipeline.py (veja saída acima)" >> "$LOG"
    exit 1
}

echo "Finalizado com sucesso: $(date)" >> "$LOG"
