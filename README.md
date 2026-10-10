# onlinebusinesses — fase 0 (conta de teste, sem vendas)

Pipeline diário: pesquisa notícias (RSS + web, fontes por nível de fiabilidade) → propõe 5 temas → o Ricardo escolhe 2 no
Telegram → 2 propostas por tema → barreiras automáticas → aprovação conversacional (Aceitar · Recusar · Melhorar) → publicação.

Desenho: `docs/superpowers/specs/2026-10-10-produtos-digitais-design.md` · Plano: `docs/superpowers/plans/` ·
Conformidade: `docs/compliance.md` · O que só o Ricardo faz: `docs/setup-ricardo.md`.

## Correr
```
python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'
pytest
python -m onlinebusinesses research   # pesquisa e envia os 5 temas
python -m onlinebusinesses poll       # processa cliques e mensagens do Telegram
python -m onlinebusinesses publish    # publica o aprovado; 7 dias após a 1.ª publicação, também o de hoje que passou as barreiras há 2 h
python -m onlinebusinesses report     # métricas, A vs B e critério de sucesso (a partir da 2.ª semana)
```
Variáveis: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `LLM_MODEL`, `ANTHROPIC_API_KEY`, opcionais `TIKTOK_ACCESS_TOKEN`,
`DB_PATH`, `OUT_DIR`, `PUBLISH_HOLD_MINUTES` (janela de revisão, 120). Nada de segredos no repositório.

## Agendamento (crontab, hora de Lisboa)
```
CRON_TZ=Europe/Lisbon
0 7 * * *   cd /caminho/onlinebusinesses && .venv/bin/python -m onlinebusinesses research
* * * * *   cd /caminho/onlinebusinesses && .venv/bin/python -m onlinebusinesses poll
* * * * *   cd /caminho/onlinebusinesses && .venv/bin/python -m onlinebusinesses publish
```

## Por configurar
Voz, visuais, API de pesquisa web e alojamento de vídeo (Instagram) estão atrás de `Protocol`s; enquanto não existirem,
`unconfigured.py` falha com uma mensagem clara e a pesquisa corre só com RSS.
