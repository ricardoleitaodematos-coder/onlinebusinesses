# Fase 0 — Conta de teste (gestão automática) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um pipeline diário que pesquisa notícias, propõe 5 temas, deixa o Ricardo escolher 2, cria 2 propostas por tema, passa-as por barreiras automáticas e publica por APIs oficiais.

**Architecture:** Pacote Python com um módulo por responsabilidade, ligado por um orquestrador de estados guardados em SQLite. Tudo o que toca serviços externos (LLM, voz, visuais, publicação, canal com o Ricardo) fica atrás de um `Protocol` para testar com falsos e trocar de fornecedor. Os passos correm por CLI/cron, idempotentes.

**Tech Stack (escolha do agente; o spec deixa as ferramentas ao construtor):** Python 3.12, pytest, httpx, feedparser, SQLite (stdlib), ffmpeg/ffprobe, SDK do LLM (escolher com a skill `claude-api`; o modelo vem de `LLM_MODEL`, sem valor fixo no código).

**Spec:** `docs/superpowers/specs/2026-10-10-produtos-digitais-design.md` (secções 4, 8, 9, 10, 14 e 15). Regras no cofre: `segundo-cerebro/04 Projetos/Produtos Digitais (Online Businesses).md`.

## Global Constraints
- Fase 0 **sem vendas**: nada de loja, afiliados, funil, email.
- Original em **PT-PT**; **pt-BR** e **es** por dobragem e legendas, só em temas com `travels=True`.
- **5** temas por dia; o Ricardo escolhe **2**; **2** propostas (A e B) por tema; publicam-se as duas por defeito.
- Cada tema precisa de **2 fontes independentes** (domínios distintos).
- Publicação **só por APIs oficiais**; sem scripts não oficiais. Sem escolha do Ricardo, não se gera nem publica nada.
- Voz ou imagem sintéticas realistas → **rótulo de IA** da plataforma.
- Só visuais gerados por nós (`cartoon`, `illustration`, `abstract`) e música livre; nada de material de terceiros; nada fotorrealista de pessoas.
- Sempre de fora: mortes e tragédias recentes, menores, pessoas privadas, guerra como piada.
- Na primeira semana (7 dias desde a 1.ª pesquisa) só se publica o que o Ricardo aprovou.
- «Hoje» = `Europe/Lisbon`.
- Nenhum segredo no repositório; credenciais por variáveis de ambiente.

## Review Focus
1. Um feed em baixo ou com XML inválido não pára a pesquisa dos outros (Task 3).
2. Duas notícias do mesmo domínio contam como **uma** fonte (Task 3).
3. O LLM devolve JSON inválido ou cita uma fonte que não existe → rejeitar, tentar uma vez, ignorar o tema; nunca publicar (Task 5).
4. Reexecutar a publicação depois de uma falha não duplica o post (Tasks 9 e 10).
5. O Ricardo não escolhe até ao fim do dia → não se gera nem publica nada, e não se escolhe por ele (Task 10).

## File Structure
```
pyproject.toml · README.md · .gitignore
config/feeds.toml            fontes de notícias (outlet, url)
config/blocklist.toml        palavras vetadas por língua (pt, es, en)
src/onlinebusinesses/
  models.py    dataclasses + (de)serialização JSON
  config.py    Settings, FeedConfig, today_lisbon
  store.py     SQLite: temas, escolhas, propostas, estados, publicações, métricas
  research.py  feeds → fontes → temas → top 5
  brief.py     texto diário, interpretação da escolha, Channel/FileChannel
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
- `Source(id:str, url:str, domain:str, title:str, outlet:str, published_at:datetime)`
- `Topic(id:str, title:str, summary:str, sources:tuple[Source,...], category:Literal["ai","geopolitics","national","other"], travels:bool)`
- `Claim(text:str, source_ids:tuple[str,...])`
- `Proposal(id:str, topic_id:str, variant:Literal["A","B"], script_pt:str, claims:tuple[Claim,...], visual_prompts:tuple[str,...], visual_style:Literal["cartoon","illustration","abstract"], synthetic_voice:bool, synthetic_visuals:bool)`
- `Asset(path:str, origin:Literal["generated","licensed-free","third-party"], license:str|None)`
- `GateResult(passed:bool, reasons:tuple[str,...])`
- `Insights(views:int, likes:int, comments:int, shares:int, avg_watch_s:float)`
- cada classe com `to_json()->str` e `from_json(s:str)->Self`
- `Settings(db_path:Path, feeds_path:Path, out_dir:Path, tz:str, first_week_approval:bool, topics_per_day:int, picks_per_day:int, llm_model:str)`; `load_settings(env:Mapping[str,str])->Settings`
- `FeedConfig(outlet:str, url:str)`; `load_feeds(path:Path)->list[FeedConfig]`
- `today_lisbon(now:datetime)->date`

- [ ] **Step 1: Write failing tests**
  - `test_topic_json_roundtrip`: `Topic.from_json(t.to_json()) == t`; idem `Proposal`.
  - `test_today_lisbon_at_midnight`: `today_lisbon(datetime(2026,10,10,23,30,tzinfo=UTC))` (hora de verão, 00:30 em Lisboa) `== date(2026,10,11)`.
  - `test_load_settings_defaults`: `topics_per_day==5`, `picks_per_day==2`, `first_week_approval is True`, `tz=="Europe/Lisbon"`.
  - `test_load_feeds`: lê `[[feed]] outlet=… url=…` de um TOML temporário.
- [ ] **Step 2:** `pytest tests/test_models.py tests/test_config.py -v` → FAIL (módulos em falta).
- [ ] **Step 3:** Implementar o que o bloco Interfaces fixa (dataclasses `frozen=True`, `zoneinfo` para o fuso). Em `config/feeds.toml` pôr ≥6 feeds RSS de imprensa portuguesa e internacional (verificar que cada URL responde antes de os fixar).
- [ ] **Step 4:** Mesmo comando → PASS.
- [ ] **Step 5:** `git add -A && git commit -m "feat: modelos, configuração e esqueleto"`

### Task 2: Armazenamento e estados
**Files:** Create `src/onlinebusinesses/store.py`, `tests/test_store.py`.

**Interfaces — Consumes:** Task 1. **Produces:** `Status = Literal["draft","gated","approved","rejected","published"]`
`Store(path:Path)`; `init()->None`; `save_topics(day:date, topics:Sequence[Topic])->None`; `topics(day:date)->list[Topic]`; `save_choice(day:date, topic_ids:Sequence[str])->None`; `choice(day:date)->list[str]`; `save_proposals(props:Sequence[Proposal])->None`; `proposals_for(topic_id:str)->list[Proposal]`; `set_status(proposal_id:str, status:Status, reasons:Sequence[str]=())->None`; `status(proposal_id:str)->Status`; `reasons(proposal_id:str)->list[str]`; `record_publication(proposal_id:str, platform:str, external_id:str)->None`; `publication(proposal_id:str, platform:str)->str|None`; `first_day()->date|None`; `set_first_day(day:date)->None` (não substitui valor existente).

- [ ] **Step 1: Write failing tests** em `tmp_path`: round-trip de temas; `save_choice` sobrescreve a do mesmo dia; `publication` devolve `None` antes e o id depois de `record_publication`; `set_first_day` chamado duas vezes mantém o primeiro valor; `status` de proposta nova == `"draft"`.
- [ ] **Step 2:** `pytest tests/test_store.py -v` → FAIL.
- [ ] **Step 3:** Implementar com `sqlite3`; JSON nas colunas de objetos; chave única `(proposal_id, platform)` em publicações.
- [ ] **Step 4:** → PASS.
- [ ] **Step 5:** Commit `feat: store SQLite com estados e publicações`.

### Task 3: Pesquisa de notícias e temas
**Files:** Create `src/onlinebusinesses/research.py`, `src/onlinebusinesses/llm.py` (só o `LLMClient` Protocol; a Task 5 acrescenta `build_llm`), `tests/test_research.py`, `tests/fakes.py` (com `FakeLLM(responses:list[str])` que conta `calls`).

**Interfaces — Consumes:** Tasks 1–2. **Produces:** `LLMClient` (Protocol) com `complete(system:str, user:str)->str`;
`HttpGet = Callable[[str], str]`
`fetch_items(feeds:Sequence[FeedConfig], http:HttpGet, now:datetime, max_age_hours:int=36)->list[Source]`
`cluster_topics(items:Sequence[Source])->list[Topic]` (títulos normalizados; Jaccard ≥ 0.5; só devolve grupos com ≥ 2 domínios distintos)
`classify_topics(topics:Sequence[Topic], llm:LLMClient)->list[Topic]` (preenche `category` e `travels`)
`rank_topics(topics:Sequence[Topic], n:int=5)->list[Topic]` (mais domínios distintos primeiro; depois o mais recente)

- [ ] **Step 1: Write failing tests**
  - `test_fetch_skips_failing_feed`: `http` lança para o feed 1; devolve itens do feed 2 (**Review Focus 1**); também com XML inválido.
  - `test_fetch_drops_old_items`: item com 48 h fica de fora.
  - `test_same_domain_is_one_source`: duas notícias do mesmo domínio → `cluster_topics(...) == []` (**Review Focus 2**).
  - `test_cluster_two_domains_makes_topic`: títulos parecidos de 2 domínios → 1 tema com 2 `sources`.
  - `test_rank_prefers_more_domains`.
  - `test_classify_sets_category_and_travels` com `FakeLLM` a devolver `{"category":"ai","travels":true}`; JSON inválido → `category="other"`, `travels=False`.
- [ ] **Step 2:** `pytest tests/test_research.py -v` → FAIL.
- [ ] **Step 3:** Implementar com `feedparser.parse(text)`; capturar exceções por feed; `domain` = `urlparse(url).hostname` sem `www.`.
- [ ] **Step 4:** → PASS. **Step 5:** Commit `feat: pesquisa e ranking de temas`.

### Task 4: Resumo diário e escolha do Ricardo
**Files:** Create `src/onlinebusinesses/brief.py`, `tests/test_brief.py`.

**Interfaces — Produces:**
`render_brief(day:date, topics:Sequence[Topic])->str` (numera 1..N; título, categoria, resumo, links das fontes)
`parse_choice(text:str, topics:Sequence[Topic], picks:int=2)->list[str]` (aceita `"1,3"`, `"1 3"`, `"1 e 3"`; devolve ids); lança `ChoiceError`
`Channel` (Protocol): `send(day:date, text:str)->None`; `read_choice(day:date)->str|None`
`FileChannel(out_dir:Path)`: escreve `out/YYYY-MM-DD/topics.md`; lê `out/YYYY-MM-DD/choice.txt`

- [ ] **Step 1: Write failing tests:** `"1,3"` e `"1 e 3"` devolvem os ids 1.º e 3.º; `"1"`, `"1,1"`, `"1,9"` → `ChoiceError`; `render_brief` contém os 5 títulos e os URLs; `FileChannel.read_choice` devolve `None` sem ficheiro.
- [ ] **Step 2:** `pytest tests/test_brief.py -v` → FAIL. **Step 3:** Implementar. O canal real (Telegram ou email) fica adiado: precisa de um token que só o Ricardo cria (ver `docs/setup-ricardo.md`).
- [ ] **Step 4:** → PASS. **Step 5:** Commit `feat: resumo diário e escolha`.

### Task 5: Propostas (duas por tema)
**Files:** Modify `src/onlinebusinesses/llm.py`; Create `src/onlinebusinesses/proposals.py`, `tests/test_proposals.py`.

**Interfaces — Consumes:** `LLMClient` (Task 3). **Produces:** `build_llm(env:Mapping[str,str])->LLMClient` (usa `LLM_MODEL` e a chave por variável de ambiente); `generate_proposals(topic:Topic, llm:LLMClient)->tuple[Proposal,Proposal]` (variantes `"A"` e `"B"`); `ProposalError`.

- [ ] **Step 1: Write failing tests** com `FakeLLM`:
  - `test_two_variants`: JSON válido → duas propostas A e B, `topic_id` certo.
  - `test_invalid_json_retries_once_then_raises`: duas respostas inválidas → `ProposalError`; `FakeLLM.calls == 2` (**Review Focus 3**).
  - `test_unknown_source_id_is_rejected`: `Claim.source_ids` com id fora de `topic.sources` → conta como inválido → retry → `ProposalError` (**Review Focus 3**).
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
`Pipeline(store:Store, channel:Channel, llm:LLMClient, voice:Voice, visuals:Visuals, publishers:Mapping[str,Publisher], settings:Settings, http:HttpGet, blocklist:Mapping[str,Sequence[str]], workdir:Path)`
`stage_research(now:datetime)->list[Topic]` (guarda os 5, envia o resumo, fixa `first_day`)
`stage_generate(now:datetime)->list[Proposal]` (lê a escolha do canal; gera, passa barreiras, grava `gated` ou `rejected`+razões; **sem escolha não faz nada**)
`approve(proposal_id:str)->None`
`stage_publish(now:datetime)->dict[str,str]` (nos 7 primeiros dias só `approved`; depois `gated`; ignora o que já tem `publication`)
CLI: `research`, `generate`, `approve <id>`, `publish`, `report`.

- [ ] **Step 1: Write failing tests** com fakes e `tmp_path`:
  - `test_no_choice_generates_and_publishes_nothing` (**Review Focus 5**).
  - `test_choice_makes_four_proposals_per_two_topics`.
  - `test_rejected_proposal_is_never_published` (barreira falha → `rejected`, `publication is None`).
  - `test_first_week_requires_approval` e `test_after_week_one_publishes_gated`.
  - `test_publish_twice_does_not_duplicate`: 2.ª execução com o publicador falso a contar chamadas → 1 chamada (**Review Focus 4**).
  - `test_publisher_failure_leaves_status_unpublished_and_retries_safely`.
- [ ] **Step 2:** `pytest tests/test_pipeline.py -v` → FAIL.
- [ ] **Step 3:** Implementar como máquina de estados sobre o `Store`; a chave de idempotência do publicador é `proposal_id`. `README.md`: comandos e exemplo de `crontab` (pesquisa 07:00 Lisboa; geração e publicação após a escolha).
- [ ] **Step 4:** `pytest -q` (suite toda) → PASS. **Step 5:** Commit `feat: pipeline diário e CLI`.

### Task 11: Métricas e critério de sucesso
**Files:** Create `src/onlinebusinesses/metrics.py`, `tests/test_metrics.py`; Modify `store.py` (`save_insights`, `insights_for`).

**Interfaces — Produces:** `Insights` (definido na Task 1); `Store.save_insights(proposal_id:str, platform:str, ins:Insights)->None`; `Store.insights_for(proposal_id:str)->list[tuple[str,Insights]]`; `weekly_report(store:Store, start:date)->str` (publicações por dia; totais A vs B por tema); `success(store:Store, start:date)->bool` (≥1 publicação em cada um de 7 dias consecutivos; só conta o dia se não houve `approve` fora da 1.ª semana).

- [ ] **Step 1: Write failing tests:** 7 dias com publicação → `True`; falha num dia → `False`; o relatório mostra A e B lado a lado por tema.
- [ ] **Step 2:** → FAIL. **Step 3:** Implementar; comando `report` da CLI usa-o. **Step 4:** → PASS. **Step 5:** Commit `feat: métricas e relatório semanal`.

### Task 12: Conformidade e set-up do Ricardo (pesquisa, sem código)
**Files:** Create `docs/compliance.md`, `docs/setup-ricardo.md`. **Corre em paralelo desde o início e desbloqueia a Task 9.**

- [ ] **Step 1:** Em `docs/compliance.md`, resolver com **fontes primárias** (documentação oficial da Meta, do TikTok, EUR-Lex, legislação portuguesa): rótulo de IA e conteúdo político gerado por IA; AI Act artigo 50; política da Meta para respostas automáticas (para a fase seguinte); auditoria da app TikTok e permissões do Instagram (`instagram_content_publish`); difamação e honra em Portugal para sátira. Cada ponto com link e data de consulta; o que não ficar confirmado marca-se «por confirmar».
- [ ] **Step 2:** Em `docs/setup-ricardo.md`, checklist do que só o Ricardo faz: contas Instagram profissional + Página, conta TikTok, apps de programador e revisão/auditoria, tokens em segredos (nunca no repo), onde corre o agendador, armazenamento do vídeo com URL público, consentimento para a voz, canal de escolha diária.
- [ ] **Step 3:** Verificar que nenhum ponto cita blogs de ferramentas como fonte; commit `docs: conformidade e set-up`.

---

## Self-Review
- **Cobertura do spec (secção 15):** processo diário → T3, T4, T5, T10; barreiras de factos, sensibilidade, direitos e rótulo → T6; 1.ª semana com aprovação → T10; PT-PT + PT-BR/ES só em temas que viajam → T7, T8; publicação por APIs oficiais e rascunhos TikTok → T9; critério de sucesso → T11; pendentes de confirmação oficial → T12. Fora de âmbito (spec secções 5–7): produtos, preços, loja, funil, email.
- **Tipos:** `Proposal`, `Topic`, `Asset`, `GateResult`, `Insights` e `Status` definidos uma vez e usados com os mesmos nomes nas tasks seguintes. `LLMClient` nasce em T3 e `Insights` em T1, antes de quem os usa.
- **Proporção:** o plano descreve interfaces e testes, sem corpos de função.
- **Decisões em aberto que o plano não fecha** (spec 14): canal real de escolha, fornecedores de voz, visuais, alojamento do vídeo e do agendador, nome da marca. Tudo atrás de `Protocol`.
