# Conformidade e APIs oficiais — verificado a 2026-10-10

Só fontes primárias (documentação oficial ou texto legal). **Confirmado** = li o texto oficial nesta data. **Por confirmar** = não consegui ler a fonte primária; não se constrói em cima disto sem confirmar.

## 1. Instagram (publicação de Reels) — confirmado
Fonte: <https://developers.facebook.com/docs/instagram-platform/content-publishing/>
- Criar contentor: `POST /<IG_ID>/media` com `media_type=REELS` e `video_url` (URL **público** no momento da publicação). `caption` é parâmetro do endpoint de media.
- Estado: `GET /<IG_CONTAINER_ID>?fields=status_code` → `EXPIRED | ERROR | FINISHED | IN_PROGRESS | PUBLISHED`; sondar no máximo 1 vez por minuto, durante 5 minutos.
- Publicar: `POST /<IG_ID>/media_publish` com `creation_id`; devolve o id do media.
- **Rótulo de IA oficial:** «Set `is_ai_generated` to `true` when creating the media container.» Vale nos dois tipos de login.
- Permissões: Instagram Login → `instagram_business_basic` + `instagram_business_content_publish` (token em `graph.instagram.com`); Facebook Login → `instagram_basic`, `instagram_content_publish`, `pages_read_engagement`. Ambos exigem Advanced ou Standard Access (revisão da Meta).
- Limite: «100 API-published posts within a 24-hour moving period» (a mesma página indica 50 nos carrosséis); consultar `GET /<IG_ID>/content_publishing_limit`.
- **Por confirmar:** formato, resolução, duração e tamanho dos vídeos (a página não os indica).

## 2. TikTok (publicação) — confirmado
Fontes: <https://developers.tiktok.com/doc/content-posting-api-get-started>, <https://developers.tiktok.com/doc/content-posting-api-reference-direct-post>, <https://developers.tiktok.com/doc/content-posting-api-reference-upload-video>, <https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide>
- «All content posted by unaudited clients will be restricted to private viewing mode.» Para lifting é preciso auditoria de conformidade com os Termos.
- **Direct Post:** `POST https://open.tiktokapis.com/v2/post/publish/video/init/`, scope `video.publish`. `post_info`: `privacy_level` (obrigatório; um dos devolvidos por `/creator_info/query/`), `title` (até 2200 caracteres), `brand_content_toggle` (parceria paga), `brand_organic_toggle` (negócio próprio) e **`is_aigc`** («Set to true if the video is AI generated content»).
- **Rascunhos (inbox):** `POST /v2/post/publish/inbox/video/init/`, scope `video.upload`, 6 pedidos por minuto por token. Corpo: `source_info` com `source` = `FILE_UPLOAD` (ou `PULL_FROM_URL` com domínio verificado), `video_size`, `chunk_size`, `total_chunk_count`. Resposta: `publish_id` e `upload_url` (válido 1 hora). **Este endpoint não documenta `post_info`**, por isso não leva legenda nem `is_aigc`: quem publica o rascunho na app põe a legenda e liga o rótulo de IA.
- Envio do ficheiro (`FILE_UPLOAD`): `PUT` ao `upload_url` com `Content-Type`, `Content-Length` e `Content-Range: bytes first-last/total`; vídeos < 5 MB vão inteiros (`chunk_size` = tamanho); blocos de 5–64 MB, o último até 128 MB; `201` = completo, `206` = faltam blocos. Formatos MP4 (recomendado), WebM, MOV; máximo 4 GB.
- **Por confirmar:** o endpoint de estado (`Get Post Status`) e os passos da auditoria; a política de conteúdo de IA do TikTok (as páginas de apoio e das diretrizes não carregam sem JavaScript).

## 3. Telegram Bot API — confirmado
Fonte: <https://core.telegram.org/bots/api>
- `sendMessage`: `chat_id`, `text` de 1–4096 caracteres, `reply_markup` (`InlineKeyboardMarkup`), `link_preview_options`.
- `InlineKeyboardButton.callback_data`: «1-64 bytes».
- `getUpdates`: `offset` «must be greater by one than the highest among the identifiers of previously received updates»; um update fica confirmado quando se chama com offset maior; `timeout` por omissão 0; **não funciona com webhook ativo**.
- `Update`: no máximo um de `message` / `callback_query`; `CallbackQuery` tem `id`, `from`, `message`, `data`.
- `answerCallbackQuery`: `callback_query_id` obrigatório; `text` 0–200 caracteres.
- `editMessageReplyMarkup`: `chat_id`, `message_id`, `reply_markup`.

## 4. AI Act (UE) artigo 50 — confirmado o texto; data de aplicação por confirmar
Fonte: Regulamento (UE) 2024/1689 no EUR-Lex (<https://eur-lex.europa.eu/legal-content/PT/TXT/HTML/?uri=OJ:L_202401689>), conferido com o texto em inglês.
- 50.º n.º 2: os prestadores de sistemas de IA que geram áudio, imagem, vídeo ou texto sintéticos «shall ensure that the outputs … are marked in a machine-readable format and detectable as artificially generated or manipulated».
- 50.º n.º 4: quem usa um sistema de IA que gera ou manipula imagem, áudio ou vídeo constituindo *deep fake* «shall disclose that the content has been artificially generated or manipulated».
- Exceção: se o conteúdo faz parte de obra «evidently artistic, creative, satirical, fictional or analogous», a obrigação limita-se a divulgar a existência desse conteúdo «in an appropriate manner that does not hamper the display or enjoyment of the work». **A sátira não dispensa o aviso.**
- **Por confirmar:** a data de aplicação do artigo 50 (artigo 113 não foi lido nesta consulta; blogs falam de 2 de agosto de 2026, mas não é fonte primária).

## 5. Meta — política de média manipulados — confirmado
Fonte: <https://transparency.meta.com/policies/community-standards/manipulated-media/>
- «We require people to disclose, using our AI-disclosure tool, whenever they post organic content» fotorrealista (vídeo) ou áudio realista criado ou alterado digitalmente; a falta de divulgação pode levar a penalizações; a Meta pode também rotular por iniciativa própria.
- A página não tem regras específicas sobre representações realistas de pessoas reais nem sobre conteúdo político gerado por IA.
- **Por confirmar:** política da Meta sobre respostas automáticas a comentários e DMs (só relevante quando houver funil).

## 6. WhatsApp (alternativa futura) — parcialmente confirmado
Fonte: <https://developers.facebook.com/docs/whatsapp/cloud-api/messages/interactive-reply-buttons-messages>
- Mensagem interativa com até **3** botões; título até **20** caracteres; id do botão até **256**; o clique chega ao webhook como `interactive.button_reply` com `id` e `title`.
- **Por confirmar:** regra da janela de 24 horas (não aparece nesta página).

## 7. Sátira e honra em Portugal — por confirmar
Não consegui ler o texto dos artigos 180.º (difamação) e 181.º (injúria) do Código Penal em fonte primária nesta sessão (o Diário da República não carrega sem JavaScript e o excerto do PGDL não chegou à Parte especial). Antes de publicar sátira sobre pessoas identificáveis: ler o texto consolidado em <https://diariodarepublica.pt> e, havendo dúvida, falar com um advogado. As barreiras do pipeline já evitam pessoas privadas e deepfakes realistas.

## Consequências para o código
- Instagram: enviar `is_ai_generated=true` em todos os contentores (voz e visuais são sintéticos).
- TikTok: Direct Post leva `is_aigc=true`; enquanto a app não for auditada só há rascunhos, e o aviso ao Ricardo inclui a legenda pronta e o lembrete de ligar o rótulo de IA.
- Rótulo de IA fica obrigatório na `label_gate`; a sátira não é motivo para o retirar.

## 8. Google Cloud, Brave e nível gratuito — verificado a 2026-10-10
**Confirmado** (documentação oficial):
- Cloud TTS: `POST https://texttospeech.googleapis.com/v1/text:synthesize`; corpo `input`, `voice`, `audioConfig`; resposta `audioContent` em base64 (LINEAR16 inclui cabeçalho WAV). <https://docs.cloud.google.com/text-to-speech/docs/reference/rest/v1/text/synthesize>
- Vozes (<https://docs.cloud.google.com/text-to-speech/docs/list-voices-and-types>): pt-PT só tem `pt-PT-Standard-E/F` e `pt-PT-Wavenet-E` (feminina) / `pt-PT-Wavenet-F` (masculina); não há Neural2 nem Chirp3-HD em pt-PT. Por omissão: `pt-PT-Wavenet-F`. es-ES tem `es-ES-Neural2-A/E/H` (femininas) e `-F/-G` (masculinas), além de Chirp3-HD; por omissão `es-ES-Neural2-F`. Configuráveis com `TTS_VOICE_PT`/`TTS_VOICE_ES`.
- Imagen no Vertex AI: `POST https://REGIÃO-aiplatform.googleapis.com/v1/projects/P/locations/REGIÃO/publishers/google/models/MODELO:predict`, corpo `instances[{prompt}]` + `parameters{sampleCount, aspectRatio ("9:16" suportado), personGeneration}`; resposta `predictions[].bytesBase64Encoded`. `personGeneration` aceita `dont_allow | allow_adult | allow_all` (usamos `dont_allow`). <https://docs.cloud.google.com/vertex-ai/generative-ai/docs/image/generate-images>
- Compute Engine gratuito: uma `e2-micro` não preemptível por mês, regiões `us-west1`, `us-central1`, `us-east1`; 30 GB-mês de disco padrão; 1 GB/mês de saída da América do Norte. Cloud Storage gratuito: 5 GB-mês regional (só US), 5 000 operações A e 50 000 B. <https://docs.cloud.google.com/free/docs/free-cloud-features> (limites mudáveis com 30 dias de aviso).
- Objetos públicos: `gcloud storage buckets add-iam-policy-binding gs://BUCKET --member=allUsers --role=roles/storage.objectViewer`; falha se o bucket tiver prevenção de acesso público. O bucket de código usa `--public-access-prevention`. <https://docs.cloud.google.com/storage/docs/access-control/making-data-public>
- Brave Search API: `GET https://api.search.brave.com/res/v1/web/search`, cabeçalho `X-Subscription-Token`, `q`, `count` (máx. 20), `freshness` = `pd|pw|pm|py` ou intervalo `AAAA-MM-DDtoAAAA-MM-DD` (usamos o intervalo); resultados em `web.results[]` (`title`, `url`, `description`). Plano Search: 5 USD por 1 000 pedidos, com 5 USD de créditos mensais. <https://api-dashboard.search.brave.com/app/documentation/web-search/get-started>, <https://brave.com/search/api/>

**Por confirmar:**
- **Imagen 4 (`imagen-4.0-generate-001`, também fast e ultra) tem descontinuação anunciada para 2026-06-30**, já passada; a página aponta `gemini-2.5-flash-image` como substituto, que usa outra API (`generateContent`, não `predict`). O `ImagenVisuals` usa o `predict` do Imagen e o modelo é configurável (`IMAGEN_MODEL`); se o modelo já não responder, é preciso um fornecedor novo para o Gemini Image.
- Regiões europeias do Imagen: a documentação não as lista; por omissão `VERTEX_LOCATION=us-central1`.
- Papéis IAM para o TTS: não encontrei um papel específico; a conta de serviço leva `aiplatform.user` e `serviceusage.serviceUsageConsumer`, e a API `texttospeech.googleapis.com` fica ativa.
- Campo `page_age` (formato e presença) nos resultados da Brave: tratado como opcional; sem data usa-se o momento da pesquisa.
- Arranque da VM: usa só `curl`/`python3` com o token do servidor de metadados (Debian 12); suporte de `CRON_TZ` no cron do Debian por confirmar, por isso o fuso da VM também fica em Europe/Lisbon. Nada disto foi corrido numa conta Google real.
