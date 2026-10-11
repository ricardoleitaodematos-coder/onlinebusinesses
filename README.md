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
Variáveis: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `LLM_MODEL`, `ANTHROPIC_API_KEY`, opcionais `TIKTOK_ACCESS_TOKEN`
(conta PT-PT), `TIKTOK_ACCESS_TOKEN_ES` (conta TikTok em espanhol), `DB_PATH`, `OUT_DIR`, `PUBLISH_HOLD_MINUTES` (janela
de revisão, 120) e `PUBLISH_LANGUAGES` (línguas a produzir e publicar, separadas por vírgulas; por omissão `pt-PT,es`).
Nada de segredos no repositório.

Línguas: o vídeo é sempre PT-PT; nos temas que viajam (IA e geopolítica sempre; nacionais só PT) produz-se também a versão
ES (espanhol neutro, por dobragem e legendas), que o Ricardo vê na proposta («Versão ES:») e que passa pelas mesmas barreiras.
Os publicadores são por plataforma (`instagram`, `tiktok`: PT-PT) ou por plataforma e língua (`instagram:es`, `tiktok:es`).

## Agendamento (crontab, hora de Lisboa)
```
CRON_TZ=Europe/Lisbon
0 7 * * *   cd /caminho/onlinebusinesses && .venv/bin/python -m onlinebusinesses research
* * * * *   cd /caminho/onlinebusinesses && .venv/bin/python -m onlinebusinesses poll
* * * * *   cd /caminho/onlinebusinesses && .venv/bin/python -m onlinebusinesses publish
```

## Instalar na Google Cloud
O Claude corre, na sessão cloud: `bash deploy/instalar-na-google-cloud.sh`. Usa a chave `GCP_SA_KEY` (conta de serviço
com papel Owner) e as variáveis de ambiente da sessão (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `ANTHROPIC_API_KEY`,
`LLM_MODEL`, `BRAVE_API_KEY`, `INSTAGRAM_*`, `TIKTOK_*`). Empacota o código (`git archive HEAD`) para um bucket privado,
guarda os segredos no Secret Manager (`onlinebusinesses-env`), cria o bucket público dos vídeos, a conta de serviço e uma
VM e2-micro do nível gratuito cujo `startup-script` instala tudo e o `cron`. Atualizar = voltar a correr o script.
O que o Ricardo tem de fazer: `docs/setup-ricardo.md`.

Variáveis adicionais lidas pela CLI: `GOOGLE_CLOUD_PROJECT` (liga TTS e Imagen), `GCS_BUCKET` (alojamento; com
`INSTAGRAM_USER_ID`/`INSTAGRAM_ACCESS_TOKEN` e os `_ES` regista `instagram` e `instagram:es`), `VERTEX_LOCATION`,
`IMAGEN_MODEL`, `TTS_VOICE_PT`, `TTS_VOICE_ES`, `BRAVE_API_KEY`, `ENV_FILE` (por omissão `/etc/onlinebusinesses.env`).
Sem estas variáveis mantêm-se os `Unconfigured*`/`NullSearch` de `unconfigured.py`.
