# O que só o Ricardo faz

Tudo o resto está pronto no código e é instalado pelo Claude na Google Cloud (`bash deploy/instalar-na-google-cloud.sh`).
Nenhum segredo entra no repositório: as chaves vão para as **variáveis de ambiente do ambiente cloud** (menu do
ambiente → Editar). **Depois de mudares variáveis do ambiente, abre uma sessão nova** para o Claude as ver.

## 1. Google Cloud (identidade e pagamento)
- [ ] Criar a conta e um projeto, com faturação ativa: <https://console.cloud.google.com/billing> (o nível gratuito exige faturação).
- [ ] Criar uma conta de serviço com papel **Owner** no projeto e descarregar a chave:
  <https://console.cloud.google.com/iam-admin/serviceaccounts> → *Criar conta de serviço* → papel *Owner* →
  abrir a conta → separador **Chaves** → *Adicionar chave* → *Criar nova chave* → **JSON**.
- [ ] Colar o JSON **inteiro** (começa por `{"type": "service_account"`) na variável `GCP_SA_KEY` do ambiente cloud.

## 2. Telegram (aprovações e escolha de temas)
- [ ] No Telegram, falar com o **@BotFather** (<https://t.me/BotFather>): `/newbot`. Colar o token em `TELEGRAM_BOT_TOKEN`.
- [ ] Enviar uma mensagem ao bot e abrir `https://api.telegram.org/bot<TOKEN>/getUpdates` no browser: o número em
  `"chat":{"id":...}` vai para `TELEGRAM_CHAT_ID`. Só esse chat é aceite.

## 3. Anthropic
- [ ] Chave em <https://console.anthropic.com/settings/keys> → `ANTHROPIC_API_KEY`; o identificador do modelo (consola) → `LLM_MODEL`.

## 4. Brave Search (pesquisa web)
- [ ] Criar conta e chave em <https://api-dashboard.search.brave.com/> (plano Search; 5 USD de créditos mensais) → `BRAVE_API_KEY`.

## 5. Contas de teste e apps (as revisões demoram dias ou semanas)
Nomes: **«Ironia Diária»** (PT) e **«Ironía Diaria»** (ES). Cada língua tem a sua conta; o ES nunca vai para as contas PT.
- [ ] Instagram profissional (criador ou empresa) + Página do Facebook associada, uma por língua: <https://www.instagram.com/accounts/emailsignup/>.
- [ ] TikTok, uma conta por língua: <https://www.tiktok.com/signup>.
- [ ] App na Meta for Developers (<https://developers.facebook.com/apps/>) com `instagram_business_content_publish`; pedir **Advanced Access**
  (revisão da Meta). Variáveis: `INSTAGRAM_USER_ID` + `INSTAGRAM_ACCESS_TOKEN` (PT) e `INSTAGRAM_USER_ID_ES` + `INSTAGRAM_ACCESS_TOKEN_ES` (ES).
- [ ] App na TikTok for Developers (<https://developers.tiktok.com/>) com `video.upload`; pedir a **auditoria** para sair do modo privado.
  Variáveis: `TIKTOK_ACCESS_TOKEN` (PT) e `TIKTOK_ACCESS_TOKEN_ES` (ES). Até haver auditoria só há rascunhos.

Os tokens do Instagram e do TikTok podem vir depois: o Claude volta a correr o script para os instalar.

## 6. Decisões tuas, quando quiseres
- `PUBLISH_LANGUAGES` (por omissão `pt-PT,es`; só PT-PT enquanto as contas ES não estão prontas). PT-BR está adiado.
- Nome da marca e dos canais; WhatsApp em vez de Telegram (mais trabalho: janela de 24 h e botões até 3).
