# Fase 0 — Conta de teste (gestão automática) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um pipeline diário que pesquisa notícias e a web com fontes classificadas por fiabilidade, propõe 5 temas, deixa o Ricardo escolher 2 por Telegram, cria 2 propostas por tema, passa-as por barreiras automáticas, pede-lhe aprovação conversacional (Aceitar, Recusar, Melhorar) e publica por APIs oficiais.

**Architecture:** Pacote Python com um módulo por responsabilidade, ligado por um orquestrador de estados guardados em SQLite. Tudo o que toca serviços externos (LLM, voz, visuais, publicação, canal com o Ricardo) fica atrás de um `Protocol` para testar com falsos e trocar de fornecedor. Os passos correm por CLI/cron, idempotentes; o canal com o Ricardo é consultado por polling (`poll` a cada minuto), sem processo permanente.

**Tech Stack (escolha do agente; o spec deixa as ferramentas ao construtor):** Python 3.12, pytest, httpx, feedparser, SQLite (stdlib), ffmpeg/ffprobe, SDK do LLM (escolher com a skill `claude-api`; o modelo vem de `LLM_MODEL`, sem valor fixo no código).

**Spec:** `docs/superpowers/specs/2026-10-10-produtos-digitais-design.md` (secções 4, 8, 9, 10, 14 e 15). Regras no cofre: `segundo-cerebro/04 Projetos/Produtos Digitais (Online Businesses).md`.

## Global Constraints
- Fase 0 **sem vendas**: nada de loja, afiliados, funil, email.
- Original em **PT-PT**; **pt-BR** e **es** por dobragem e legendas, só em temas com `travels=True`.
- **5** temas por dia; o Ricardo escolhe **2**; **2** propostas (A e B) por tema; publicam-se as duas por defeito.
- Cada tema precisa de **2 fontes independentes**: domínios distintos, ambos de **nível 1 ou 2** (agências, serviço público, imprensa de referência, documentação oficial). Nível 3 (blogs, redes sociais, desconhecidos) só dá contexto e nunca conta como fonte.
- A pesquisa combina feeds RSS e pesquisa na web, sempre com o contexto do tema e as fontes mais fidedignas.
- Aprovações e escolha de temas por **Telegram** (decisão do agente; WhatsApp só mais tarde, se o Ricardo quiser): botões Aceitar, Recusar, Melhorar. Só se aceitam mensagens do `chat_id` do Ricardo.
- Publicação **só por APIs oficiais**; sem scripts não oficiais. Sem escolha do Ricardo, não se gera nem publica nada.
- Voz ou imagem sintéticas realistas → **rótulo de IA** da plataforma.
- Só visuais gerados por nós (`cartoon`, `illustration`, `abstract`) e música livre; nada de material de terceiros; nada fotorrealista de pessoas.
- Sempre de fora: mortes e tragédias recentes, menores, pessoas privadas, guerra como piada.
- Nos primeiros 7 dias (`require_accept_days`) só se publica o que o Ricardo aceitou; depois publica-se o que passou nas barreiras e ele continua a poder recusar ou melhorar. «Melhorar» permite até 3 revisões por proposta (`revision_limit`).
- «Hoje» = `Europe/Lisbon`.
- Nenhum segredo no repositório; credenciais por variáveis de ambiente.

## Review Focus
1. Um feed ou a pesquisa web em baixo, ou XML inválido, não pára o resto da pesquisa (Task 3).
2. Duas notícias do mesmo domínio, ou duas fontes de nível 3, **não** contam como duas fontes (Task 3).
3. O LLM devolve JSON inválido ou cita uma fonte que não existe → rejeitar, tentar uma vez, ignorar o tema; nunca publicar (Task 5).
4. Reexecutar a publicação, ou carregar duas vezes num botão, não duplica nada (Tasks 4, 9 e 10).
5. O Ricardo não escolhe até ao fim do dia → não se gera nem publica nada, e não se escolhe por ele (Task 10).

## File Structure
```
pyproject.toml · README.md · .gitignore
config/feeds.toml            feeds RSS (outlet, url)
config/sources.toml          nível de fiabilidade por domínio (1, 2 ou 3)
config/blocklist.toml        palavras vetadas por língua (pt, es, en)
src/onlinebusinesses/
  models.py    dataclasses + (de)serialização JSON
  config.py    Settings, FeedConfig, today_lisbon
  store.py     SQLite: temas, escolhas, propostas, estados, publicações, métricas
  research.py  feeds + pesquisa web → fontes com nível → temas → top 5
  brief.py     mensagens, Channel (Protocol), TelegramChannel
  llm.py       LLMClient (Protocol) + cliente real
  proposals.py duas propostas por tema
  gates.py     factos, sensibilidade, direitos de autor, rótulo
  subtitles.py segmentos, SRT, adaptação PT-BR/ES
  media.py     Voice, Visuals (Protocols), assemble, build_video
  publishers/  base.py, instagram.py, tiktok.py
  pipeline.py  orquestração por estados
  metrics.py   insights, relatório semanal, critério de sucesso
  cli.py       python -m onlinebusinesses <comando>
tests/         um ficheiro por módulo + tests/fakes.py
docs/compliance.md · docs/setup-ricardo.md
```

---

### Task 1: Esqueleto, modelos e configuração
**Files:** Create `pyproject.toml`, `.gitignore`, `src/onlinebusinesses/{__init__,models,config}.py`, `config/feeds.toml`, `tests/test_models.py`, `tests/test_config.py`.

**Interfaces — Produces:**
- `Source(id:str, url:str, domain:str, title:str, outlet:str, published_at:datetime, tier:Literal[1,2,3])`
- `Topic(id:str, title:str, summary:str, sources:tuple[Source,...], category:Literal["ai","geopolitics","national","other"], travels:bool, context:str)`
- `Claim(text:str, source_ids:tuple[str,...])`
- `Proposal(id:str, topic_id:str, variant:Literal["A","B"], script_pt:str, claims:tuple[Claim,...], visual_prompts:tuple[str,...], visual_style:Literal["cartoon","illustration","abstract"], synthetic_voice:bool, synthetic_visuals:bool)`
- `Asset(path:str, origin:Literal["generated","licensed-free","third-party"], license:str|None)`
- `GateResult(passed:bool, reasons:tuple[str,...])`
- `Insights(views:int, likes:int, comments:int, shares:int, avg_watch_s:float)`
- cada classe com `to_json()->str` e `from_json(s:str)->Self`
- `Settings(db_path:Path, feeds_path:Path, sources_path:Path, out_dir:Path, tz:str, require_accept_days:int, revision_limit:int, topics_per_day:int, picks_per_day:int, llm_model:str, telegram_chat_id:int|None)`; `load_settings(env:Mapping[str,str])->Settings`
- `FeedConfig(outlet:str, url:str)`; `load_feeds(path:Path)->list[FeedConfig]`; `load_sources(path:Path)->dict[str,int]` (domínio → nível); `tier_of(domain:str, tiers:Mapping[str,int])->int` (desconhecido → 3)
- `today_lisbon(now:datetime)->date`

- [ ] **Step 1: Write failing tests**
  - `test_topic_json_roundtrip`: `Topic.from_json(t.to_json()) == t`; idem `Proposal`.
  - `test_today_lisbon_at_midnight`: `today_lisbon(datetime(2026,10,10,23,30,tzinfo=UTC))` (hora de verão, 00:30 em Lisboa) `== date(2026,10,11)`.
  - `test_load_settings_defaults`: `topics_per_day==5`, `picks_per_day==2`, `require_accept_days==7`, `revision_limit==3`, `tz=="Europe/Lisbon"`.
  - `test_load_feeds`: lê `[[feed]] outlet=… url=…` de um TOML temporário.
  - `test_tier_of_unknown_domain_is_3`; `load_sources` lê `[[source]] domain=… tier=…`.
- [ ] **Step 2:** `pytest tests/test_models.py tests/test_config.py -v` → FAIL (módulos em falta).
- [ ] **Step 3:** Implementar o que o bloco Interfaces fixa (dataclasses `frozen=True`, `zoneinfo` para o fuso). Em `config/feeds.toml` pôr ≥6 feeds RSS de imprensa portuguesa e internacional (verificar que cada URL responde antes de os fixar). Em `config/sources.toml` classificar cada domínio usado: nível 1 = agências e serviço público (ex.: Lusa, RTP, Reuters, AP, BBC), nível 2 = imprensa de referência; o resto cai em 3 por omissão.
- [ ] **Step 4:** Mesmo comando → PASS.
- [ ] **Step 5:** `git add -A && git commit -m "feat: modelos, configuração e esqueleto"`

### Task 2: Armazenamento e estados
**Files:** Create `src/onlinebusinesses/store.py`, `tests/test_store.py`.

**Interfaces — Consumes:** Task 1. **Produces:** `Status = Literal["draft","gated","approved","rejected","revising","published"]`
`Store(path:Path)`; `init()->None`; `save_topics(day:date, topics:Sequence[Topic])->None`; `topics(day:date)->list[Topic]`; `save_choice(day:date, topic_ids:Sequence[str])->None`; `choice(day:date)->list[str]`; `save_proposals(props:Sequence[Proposal])->None`; `proposals_for(topic_id:str)->list[Proposal]`; `set_status(proposal_id:str, status:Status, reasons:Sequence[str]=())->None`; `status(proposal_id:str)->Status`; `reasons(proposal_id:str)->list[str]`; `record_publication(proposal_id:str, platform:str, external_id:str)->None`; `publication(proposal_id:str, platform:str)->str|None`; `first_day()->date|None`; `set_first_day(day:date)->None` (não substitui valor existente); `get_offset()->int` e `set_offset(n:int)->None` (último update do Telegram tratado); `replace_proposal(p:Proposal)->None`; `bump_revision(proposal_id:str)->int` (devolve o total); `set_awaiting_feedback(proposal_id:str|None)->None`; `awaiting_feedback()->str|None`.

- [ ] **Step 1: Write failing tests** em `tmp_path`: round-trip de temas; `save_choice` sobrescreve a do mesmo dia; `publication` devolve `None` antes e o id depois de `record_publication`; `set_first_day` chamado duas vezes mantém o primeiro valor; `status` de proposta nova == `"draft"`; `get_offset()==0` por omissão; `bump_revision` devolve 1, 2, 3; `awaiting_feedback` devolve o id definido e `None` depois de `set_awaiting_feedback(None)`.
- [ ] **Step 2:** `pytest tests/test_store.py -v` → FAIL.
- [ ] **Step 3:** Implementar com `sqlite3`; JSON nas colunas de objetos; chave única `(proposal_id, platform)` em publicações.
- [ ] **Step 4:** → PASS.
- [ ] **Step 5:** Commit `feat: store SQLite com estados e publicações`.

### Task 3: Pesquisa (RSS + web), fiabilidade e temas
**Files:** Create `src/onlinebusinesses/research.py`, `src/onlinebusinesses/llm.py` (só o `LLMClient` Protocol; a Task 5 acrescenta `build_llm`), `tests/test_research.py`, `tests/fakes.py` (com `FakeLLM(responses:list[str])` que conta `calls`, `FakeSearch`, `FakeChannel`).

**Interfaces — Consumes:** Tasks 1–2. **Produces:** `LLMClient` (Protocol) com `complete(system:str, user:str)->str`;
`HttpGet = Callable[[str], str]`
`SearchProvider` (Protocol): `search(query:str, since:datetime)->list[Source]` (implementação real: uma API de pesquisa web com termos de uso que o permitam; escolher na altura, atrás do Protocol)
`fetch_items(feeds:Sequence[FeedConfig], tiers:Mapping[str,int], http:HttpGet, now:datetime, max_age_hours:int=36)->list[Source]`
`cluster_topics(items:Sequence[Source])->list[Topic]` (títulos normalizados; Jaccard ≥ 0.5; devolve **grupos com ≥ 2 domínios distintos de nível ≤ 2**)
`corroborate(topic:Topic, search:SearchProvider, tiers:Mapping[str,int], now:datetime)->Topic` (pesquisa o título do tema na web e junta fontes novas; falha da pesquisa devolve o tema como estava)
`add_context(topic:Topic, http:HttpGet, max_chars:int=4000)->Topic` (texto das 2 melhores fontes de nível ≤ 2 em `context`; só contexto, nunca fonte)
`classify_topics(topics:Sequence[Topic], llm:LLMClient)->list[Topic]` (preenche `category` e `travels`)
`rank_topics(topics:Sequence[Topic], n:int=5)->list[Topic]` (mais domínios de nível ≤ 2 primeiro; depois o mais recente)

- [ ] **Step 1: Write failing tests**
  - `test_fetch_skips_failing_feed`: `http` lança para o feed 1; devolve itens do feed 2 (**Review Focus 1**); também com XML inválido.
  - `test_fetch_drops_old_items`: item com 48 h fica de fora.
  - `test_same_domain_is_one_source`: duas notícias do mesmo domínio → `cluster_topics(...) == []` (**Review Focus 2**).
  - `test_tier3_does_not_count`: um domínio de nível 1 e outro de nível 3 → `[]` (**Review Focus 2**).
  - `test_cluster_two_trusted_domains_makes_topic`: títulos parecidos de 2 domínios de nível ≤ 2 → 1 tema.
  - `test_corroborate_adds_sources_and_survives_search_failure` (**Review Focus 1**).
  - `test_add_context_uses_only_trusted_sources`.
  - `test_rank_prefers_more_trusted_domains`.
  - `test_classify_sets_category_and_travels` com `FakeLLM` a devolver `{"category":"ai","travels":true}`; JSON inválido → `category="other"`, `travels=False`.
- [ ] **Step 2:** `pytest tests/test_research.py -v` → FAIL.
- [ ] **Step 3:** Implementar com `feedparser.parse(text)`; capturar exceções por feed e pela pesquisa; `domain` = `urlparse(url).hostname` sem `www.`; `tier` por `tier_of`.
- [ ] **Step 4:** → PASS. **Step 5:** Commit `feat: pesquisa RSS e web com fontes classificadas`.

### Task 4: Telegram — escolha de temas e aprovação conversacional
**Files:** Create `src/onlinebusinesses/brief.py`, `tests/test_brief.py`.

**Interfaces — Consumes:** Tasks 1–2. **Produces:**
`render_topics(day:date, topics:Sequence[Topic])->str` (numera 1..N; título, categoria, resumo, links das fontes)
`render_proposal(p:Proposal, topic:Topic)->str` (variante, guião, afirmações com fonte)
`Event` = `TopicsChosen(day:date, topic_ids:tuple[str,...])` | `ProposalDecision(proposal_id:str, action:Literal["accept","reject","improve"])` | `Feedback(proposal_id:str, text:str)`
`Channel` (Protocol): `send_topics(day:date, topics:Sequence[Topic])->None` (botões 1..N que alternam a seleção + «Confirmar»); `send_proposal(p:Proposal, topic:Topic)->None` (botões Aceitar · Recusar · Melhorar); `ask_feedback(proposal_id:str)->None`; `notify(text:str)->None`; `poll()->list[Event]`
`TelegramChannel(http:HttpClient, token:str, chat_id:int, store:Store)`: `getUpdates` com o offset guardado no `Store`; `sendMessage` com `inline_keyboard`.
`callback_data`: `t:<n>` (alternar tema), `tc:<day>` (confirmar), `p:<proposal_id>:<a|r|i>`; máximo 64 bytes (`proposal_id` com 8 caracteres).

- [ ] **Step 1: Write failing tests** com `http` falso:
  - `test_updates_from_other_chat_are_ignored`: update com `chat.id` diferente → `poll()==[]` e nenhuma resposta enviada.
  - `test_confirm_with_two_selected_returns_topics_chosen`; confirmar com 1 ou 3 selecionados → sem evento e mensagem a pedir exatamente 2.
  - `test_decision_buttons_map_to_actions`: `p:ab12cd34:a` → `ProposalDecision("ab12cd34","accept")`.
  - `test_double_press_is_idempotent`: o mesmo `update_id` duas vezes → um só evento (o offset avança) (**Review Focus 4**).
  - `test_free_text_after_improve_becomes_feedback`: com `store.awaiting_feedback()=="ab12cd34"`, uma mensagem de texto → `Feedback("ab12cd34", texto)`; sem pedido pendente, texto solto é ignorado.
  - `test_callback_data_fits_64_bytes`.
  - `test_render_topics_lists_all_titles_and_urls`.
- [ ] **Step 2:** `pytest tests/test_brief.py -v` → FAIL.
- [ ] **Step 3:** Implementar. Confirmar na documentação oficial da Telegram Bot API (`core.telegram.org/bots/api`) os métodos, o limite de `callback_data` e `answerCallbackQuery` (Task 12). O token vem de `TELEGRAM_BOT_TOKEN`.
- [ ] **Step 4:** → PASS. **Step 5:** Commit `feat: canal Telegram com botões`.

### Task 5: Propostas (duas por tema)
**Files:** Modify `src/onlinebusinesses/llm.py`; Create `src/onlinebusinesses/proposals.py`, `tests/test_proposals.py`.

**Interfaces — Consumes:** `LLMClient` (Task 3). **Produces:** `build_llm(env:Mapping[str,str])->LLMClient` (usa `LLM_MODEL` e a chave por variável de ambiente); `generate_proposals(topic:Topic, llm:LLMClient)->tuple[Proposal,Proposal]` (variantes `"A"` e `"B"`; usa `topic.context`); `revise_proposal(p:Proposal, topic:Topic, feedback:str, llm:LLMClient)->Proposal` (mesma variante e `id`); `ProposalError`.

- [ ] **Step 1: Write failing tests** com `FakeLLM`:
  - `test_two_variants`: JSON válido → duas propostas A e B, `topic_id` certo.
  - `test_invalid_json_retries_once_then_raises`: duas respostas inválidas → `ProposalError`; `FakeLLM.calls == 2` (**Review Focus 3**).
  - `test_unknown_source_id_is_rejected`: `Claim.source_ids` com id fora de `topic.sources` → conta como inválido → retry → `ProposalError` (**Review Focus 3**).
  - `test_revise_includes_feedback_and_keeps_variant`: o prompt contém o texto do Ricardo; `id` e `variant` iguais; resposta inválida → `ProposalError`.
  - `test_prompt_demands_pt_pt_and_sources`: o prompt enviado contém «PT-PT», os ids das fontes e a proibição de pessoas reais fotorrealistas.
- [ ] **Step 2:** `pytest tests/test_proposals.py -v` → FAIL.
- [ ] **Step 3:** Implementar. Pedir ao LLM JSON com `script_pt`, `claims`, `visual_prompts`, `visual_style`; `synthetic_voice=True` e `synthetic_visuals=True` fixados pelo código, não pelo LLM.
- [ ] **Step 4:** → PASS. **Step 5:** Commit `feat: geração de propostas com validação de fontes`.

### Task 6: Barreiras
**Files:** Create `src/onlinebusinesses/gates.py`, `config/blocklist.toml`, `tests/test_gates.py`.

**Interfaces — Produces:**
`fact_gate(p:Proposal, topic:Topic)->GateResult` (≥1 afirmação; cada uma cita ≥1 fonte do tema; tema com ≥2 domínios)
`sensitivity_gate(p:Proposal, blocklist:Mapping[str,Sequence[str]])->GateResult` (palavras vetadas em `script_pt` e `visual_prompts`; «fotorrealista/photorealistic/deepfake» nos prompts)
`copyright_gate(assets:Sequence[Asset])->GateResult` (falha se algum `origin=="third-party"` ou `licensed-free` sem `license`)
`label_gate(p:Proposal, ai_label_set:bool)->GateResult` (voz ou imagem sintéticas exigem rótulo)
`load_blocklist(path:Path)->dict[str,list[str]]`
`run_gates(p, topic, assets, ai_label_set, blocklist)->GateResult` (junta todas as razões)

- [ ] **Step 1: Write failing tests:** afirmação sem fonte falha; afirmação com id inexistente falha; `"morreu"` (pt), `"muertos"` (es), `"minor"` (en) no `script_pt` falham; `visual_prompts=("retrato fotorrealista do ministro",)` falha; `Asset(origin="third-party")` falha; `label_gate(p, False)` falha com voz sintética e passa com `True`; `run_gates` num caso limpo → `passed=True`; num caso com 2 problemas → `len(reasons)==2`.
- [ ] **Step 2:** `pytest tests/test_gates.py -v` → FAIL.
- [ ] **Step 3:** Implementar; correspondência por palavra inteira, sem distinguir maiúsculas nem acentos. `config/blocklist.toml`: termos em `pt`, `es`, `en` para morte, tragédia, vítimas, menor/criança, ataque/atentado, suicídio.
- [ ] **Step 4:** → PASS. **Step 5:** Commit `feat: barreiras de factos, sensibilidade, direitos e rótulo`.

### Task 7: Legendas e adaptação PT-BR/ES
**Files:** Create `src/onlinebusinesses/subtitles.py`, `tests/test_subtitles.py`.

**Interfaces — Produces:** `Segment(start:float, end:float, text:str)`; `split_script(script:str, wpm:int=170)->list[Segment]`; `build_srt(segments:Sequence[Segment])->str`; `languages_for(topic:Topic)->list[str]` (`["pt-PT"]`, mais `["pt-BR","es"]` se `travels`); `localize(script_pt:str, lang:Literal["pt-BR","es"], llm:LLMClient)->str`.

- [ ] **Step 1: Write failing tests:** `build_srt` produz `1\n00:00:00,000 --> 00:00:02,500\ntexto\n\n`; `split_script` não deixa segmentos sobrepostos e o último termina em `len(words)/wpm*60`; `languages_for` com `travels=False` → `["pt-PT"]`; `localize` envia ao LLM um prompt com «pt-BR», o texto original e a instrução de adaptar referências locais (não só traduzir).
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar. **Step 4:** → PASS. **Step 5:** Commit `feat: legendas e adaptação de língua`.

### Task 8: Voz, visuais e montagem do vídeo
**Files:** Create `src/onlinebusinesses/media.py`, `tests/test_media.py`.

**Interfaces — Produces:**
`Voice` (Protocol): `synthesize(text:str, lang:str, out:Path)->Path`
`Visuals` (Protocol): `render(prompts:Sequence[str], style:str, out_dir:Path)->list[Path]`
`assemble(audio:Path, frames:Sequence[Path], srt:Path, out:Path)->Path` (MP4 9:16, 1080×1920, legendas queimadas, duração = áudio)
`build_video(p:Proposal, lang:str, voice:Voice, visuals:Visuals, llm:LLMClient, workdir:Path)->tuple[Path, list[Asset]]` (usa `localize` se `lang!="pt-PT"`; todos os `Asset` com `origin="generated"`)

- [ ] **Step 1: Write failing tests** (saltar se `ffmpeg` não existir): fixture gera 3 s de seno e 3 PNGs com `ffmpeg -f lavfi`; `test_assemble_is_vertical`: `ffprobe` dá 1080×1920 e duração ≈ 3 s (±0,5); `test_build_video_assets_are_generated` com `Voice` e `Visuals` falsos.
- [ ] **Step 2:** `pytest tests/test_media.py -v` → FAIL. **Step 3:** Implementar `assemble` com `subprocess` e filtro `subtitles`. Os fornecedores reais de voz e visuais ficam por escolher; a voz usa a do Ricardo como referência só com o consentimento dele (`docs/setup-ricardo.md`).
- [ ] **Step 4:** → PASS. **Step 5:** Commit `feat: montagem de vídeo e adaptadores de voz e visuais`.

### Task 9: Publicadores (Instagram e TikTok)
**Files:** Create `src/onlinebusinesses/publishers/{__init__,base,instagram,tiktok}.py`, `tests/test_publishers.py`. **Bloqueada pela Task 12** (endpoints e campos têm de vir da documentação oficial).

**Interfaces — Produces:**
`Publisher` (Protocol): `publish(video:Path, caption:str, ai_label:bool, key:str)->str` (devolve id externo); `insights(external_id:str)->Insights` (tipo da Task 11)
`PublishError`
`VideoHost` (Protocol): `upload(path:Path)->str` (URL público; implementação real por escolher, o Instagram exige URL)
`InstagramPublisher(http:HttpClient, host:VideoHost, user_id:str, token:str)`: criar contentor → esperar `FINISHED` → publicar.
`TikTokDraftPublisher(http:HttpClient, token:str)`: envia para rascunhos (inbox) até a app ser auditada.

- [ ] **Step 1: Write failing tests** com `http` falso que regista pedidos: ordem criar→estado→publicar no Instagram; `ai_label=True` aparece no pedido com o campo documentado; estado `ERROR` → `PublishError` e nenhuma publicação; TikTok envia para rascunho, nunca para publicação direta; resposta 4xx → `PublishError`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar com os endpoints e nomes de campo da documentação oficial (anotar a URL consultada em comentário). **Step 4:** → PASS. **Step 5:** Commit `feat: publicadores por APIs oficiais`.

### Task 10: Orquestração e CLI
**Files:** Create `src/onlinebusinesses/{pipeline,cli,__main__}.py`, `README.md`, `tests/test_pipeline.py`.

**Interfaces — Consumes:** Tasks 1–9. **Produces:**
`Pipeline(store:Store, channel:Channel, llm:LLMClient, search:SearchProvider, voice:Voice, visuals:Visuals, publishers:Mapping[str,Publisher], settings:Settings, http:HttpGet, blocklist:Mapping[str,Sequence[str]], tiers:Mapping[str,int], workdir:Path)`
`stage_research(now:datetime)->list[Topic]` (RSS + pesquisa + contexto + classificação + top 5; envia os temas com botões; fixa `first_day`)
`stage_poll(now:datetime)->None` (processa `channel.poll()`: `TopicsChosen` → gera 2 propostas por tema, passa as barreiras e envia cada uma aprovada nelas com botões; `rejected` pelas barreiras avisa com as razões; `ProposalDecision`: accept → `approved`, reject → `rejected`, improve → `revising` + `ask_feedback`; `Feedback` → `revise_proposal`, nova passagem pelas barreiras e novo envio; à 4.ª revisão → `rejected`)
`stage_publish(now:datetime)->dict[str,str]` (até `require_accept_days` só `approved`; depois `approved` e `gated`; ignora o que já tem `publication`; avisa o Ricardo do que publicou)
CLI: `research`, `poll`, `publish`, `report`.

- [ ] **Step 1: Write failing tests** com fakes e `tmp_path`:
  - `test_no_choice_generates_and_publishes_nothing` (**Review Focus 5**): `poll` sem `TopicsChosen` e `publish` → 0 propostas, 0 publicações.
  - `test_choice_makes_four_proposals_per_two_topics`.
  - `test_rejected_by_gates_is_never_published_and_ricardo_is_told_why`.
  - `test_accept_then_publish`; `test_reject_never_publishes`.
  - `test_improve_asks_feedback_then_revises_and_resends`; `test_fourth_revision_rejects`.
  - `test_first_week_requires_accept_and_week_two_publishes_gated`.
  - `test_publish_twice_does_not_duplicate` e `test_same_decision_event_twice_does_not_duplicate` (**Review Focus 4**).
  - `test_publisher_failure_leaves_status_unpublished_and_retries_safely`.
  - `test_research_survives_search_failure`.
- [ ] **Step 2:** `pytest tests/test_pipeline.py -v` → FAIL.
- [ ] **Step 3:** Implementar como máquina de estados sobre o `Store`; a chave de idempotência do publicador é `proposal_id`. `README.md`: comandos e `crontab` (pesquisa 07:00 Lisboa; `poll` e `publish` a cada minuto).
- [ ] **Step 4:** `pytest -q` (suite toda) → PASS. **Step 5:** Commit `feat: pipeline diário, aprovação conversacional e CLI`.

### Task 11: Métricas e critério de sucesso
**Files:** Create `src/onlinebusinesses/metrics.py`, `tests/test_metrics.py`; Modify `store.py` (`save_insights`, `insights_for`).

**Interfaces — Produces:** `Insights` (definido na Task 1); `Store.save_insights(proposal_id:str, platform:str, ins:Insights)->None`; `Store.insights_for(proposal_id:str)->list[tuple[str,Insights]]`; `weekly_report(store:Store, start:date)->str` (publicações por dia; totais A vs B por tema); `success(store:Store, start:date)->bool` (≥1 publicação em cada um de 7 dias consecutivos; só conta o dia se não houve `approve` fora da 1.ª semana).

- [ ] **Step 1: Write failing tests:** 7 dias com publicação → `True`; falha num dia → `False`; o relatório mostra A e B lado a lado por tema.
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar; comando `report` da CLI usa-o. **Step 4:** → PASS. **Step 5:** Commit `feat: métricas e relatório semanal`.

### Task 12: Conformidade e set-up do Ricardo (pesquisa, sem código)
**Files:** Create `docs/compliance.md`, `docs/setup-ricardo.md`. **Corre em paralelo desde o início e desbloqueia a Task 9.**

- [ ] **Step 1:** Em `docs/compliance.md`, resolver com **fontes primárias** (documentação oficial da Meta, do TikTok, EUR-Lex, legislação portuguesa): rótulo de IA e conteúdo político gerado por IA; AI Act artigo 50; política da Meta para respostas automáticas (para a fase seguinte); auditoria da app TikTok e permissões do Instagram (`instagram_content_publish`); difamação e honra em Portugal para sátira; Telegram Bot API (`inline_keyboard`, limite de `callback_data`, `getUpdates`, `answerCallbackQuery`); botões interativos do WhatsApp (limite de botões e janela de 24 h) como alternativa futura. Cada ponto com link e data de consulta; o que não ficar confirmado marca-se «por confirmar».
- [ ] **Step 2:** Em `docs/setup-ricardo.md`, checklist do que só o Ricardo faz: contas Instagram profissional + Página, conta TikTok, apps de programador e revisão/auditoria, tokens em segredos (nunca no repo), onde corre o agendador, armazenamento do vídeo com URL público, consentimento para a voz, criar o bot do Telegram com o BotFather e dizer o `chat_id` (token em segredo, `TELEGRAM_BOT_TOKEN`; só esse `chat_id` é aceite); conta de uma API de pesquisa web para a Task 3.
- [ ] **Step 3:** Verificar que nenhum ponto cita blogs de ferramentas como fonte; commit `docs: conformidade e set-up`.

---

## Self-Review
- **Cobertura do spec (secção 15):** processo diário (pesquisa RSS + web com níveis de fiabilidade, escolha e aprovação por Telegram) → T3, T4, T5, T10; barreiras de factos, sensibilidade, direitos e rótulo → T6; aprovação obrigatória na 1.ª semana e botões Aceitar/Recusar/Melhorar → T4, T10; PT-PT + PT-BR/ES só em temas que viajam → T7, T8; publicação por APIs oficiais e rascunhos TikTok → T9; critério de sucesso → T11; pendentes de confirmação oficial → T12. Fora de âmbito (spec secções 5–7): produtos, preços, loja, funil, email.
- **Tipos:** `Proposal`, `Topic`, `Asset`, `GateResult`, `Insights` e `Status` definidos uma vez e usados com os mesmos nomes nas tasks seguintes. `LLMClient` nasce em T3 e `Insights` em T1, antes de quem os usa.
- **Proporção:** o plano descreve interfaces e testes, sem corpos de função.
- **Decisões em aberto que o plano não fecha** (spec 14): fornecedores de voz e da API de pesquisa web, visuais, alojamento do vídeo e do agendador, nome da marca. Tudo atrás de `Protocol`.
