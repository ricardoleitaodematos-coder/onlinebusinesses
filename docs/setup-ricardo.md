# O que só o Ricardo faz (set-up inicial)

Nada disto se faz por ti, e nenhum segredo entra no repositório: tokens vão para variáveis de ambiente ou para o cofre de segredos do sítio onde isto corre.

## 1. Contas
- [ ] Instagram em modo **profissional** (criador ou empresa); para o Facebook Login, uma **Página** associada.
- [ ] Conta TikTok para a marca de teste.

## 2. Apps de programador e revisão
- [ ] App na **Meta for Developers** com `instagram_business_content_publish` (ou `instagram_content_publish`); pedir **Advanced/Standard Access** (revisão da Meta).
- [ ] App na **TikTok for Developers** com `video.upload` (rascunhos) e `video.publish`; pedir a **auditoria** para sair do modo privado (demora semanas). Até lá: só rascunhos.

## 3. Telegram (aprovações e escolha de temas)
- [ ] Criar o bot com o **@BotFather** e guardar o token em `TELEGRAM_BOT_TOKEN`.
- [ ] Enviar uma mensagem ao bot e dar-me o teu `chat_id` (`TELEGRAM_CHAT_ID`). Só esse chat é aceite.

## 4. Serviços
- [ ] Chave do LLM em `ANTHROPIC_API_KEY` e o modelo em `LLM_MODEL`.
- [ ] Uma **API de pesquisa web** (para a pesquisa com fontes fiáveis); termos de uso que permitam usar os resultados.
- [ ] Um fornecedor de **voz** (consentimento para usar a tua voz como referência) e outro de **visuais** (estilos cartoon, ilustração, abstrato).
- [ ] **Armazenamento de vídeo com URL público** (o Instagram exige `video_url` público).

## 5. Onde corre
- [ ] Um sítio onde o agendador corra sozinho (servidor pequeno ou serverless), com `crontab`: pesquisa às 07:00 (Lisboa); `poll` e `publish` a cada minuto.

## 6. Decisões tuas, quando quiseres
- Nome da marca e dos canais.
- Se publicamos as duas propostas de cada tema (por defeito: sim).
- WhatsApp em vez de Telegram (mais trabalho: janela de 24 h e botões até 3).
