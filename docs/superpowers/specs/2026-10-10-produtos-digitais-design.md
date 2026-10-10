# Produtos digitais em redes sociais — desenho

Data: 2026-10-10 · Estado: **por aprovar pelo Ricardo**
Regras basilares (fonte de verdade, no cofre): `segundo-cerebro/04 Projetos/Produtos Digitais (Online Businesses).md`.

## 1. Intenção
Vender produtos digitais a partir de conteúdo viral no TikTok e no Instagram, sobre **sucesso pessoal através da produtividade com IA, organização, boas práticas e apps**. Fidelizar quem compra para vender mais produtos. O Ricardo **só aprova produtos**; o agente e os bots fazem o resto.

## 2. Objetivos, não-objetivos, anti-objetivos
**Objetivos**
- Pipeline completo e automatizado: ideia de produto → teste → produto → conteúdo → publicação → DM → venda → fidelização.
- Várias línguas, com conteúdo local.
- Cadência diária de publicação sem trabalho do Ricardo.

**Não-objetivos**
- E-books como produto principal.
- Cursos longos ou comunidades pagas no arranque.
- Aparecer na cara; personagem fictícia com vida inventada.

**Anti-objetivos (seria falha, mesmo a funcionar tecnicamente)**
- Qualquer afirmação não verdadeira: resultado, rendimento, teste não feito, testemunho.
- Automação que ponha as contas em risco (scripts não oficiais, spam de DMs).
- Conteúdo de IA genérico, indistinguível de milhares de contas.
- Omitir divulgação de afiliados ou de conteúdo sintético.

## 3. Conceito
**Marca:** um canal pessoal e anónimo («faceless»), com a voz do Ricardo. Humilde, curioso, aprende com os erros.
**Promessa:** «Não te vendo o que ouvi dizer. Mostro o que testámos, o que poupou tempo e o que não valeu a pena.»
**Narrador:** o Ricardo. Enredo só com o que ele disse; sem marcos, números ou resultados inventados. Até o Ricardo usar uma ferramenta, o texto diz «testámos», não «testei».
**Product placement:** o narrador recomenda ferramentas e produtos que passaram nos testes. Afiliados e parcerias identificados com aviso visível.

## 4. Conteúdo
Pilares (cada vídeo tem **um problema real, uma solução testada, um resultado medido, um passo seguinte**):
1. **Testado e funcionou** — ferramenta ou sistema aplicado a uma tarefa concreta, com o antes e depois (tempo, passos).
2. **Correu mal / aviso** — erro real surgido num teste: «não uses X», «usa X assim». Também é o pilar de maior confiança.
3. **Sistema do mês** — um fluxo de trabalho completo (por exemplo, caixa de email, reuniões, estudo) que culmina no produto.
4. **Bastidores do teste** — mostrar o processo de teste e as provas, sem mostrar a cara.

Formato: vídeos de 1 a 3 minutos (narração + ecrã + texto sobreposto), 9:16, reutilizados em TikTok e Reels. Cadência alvo: 1 a 2 por dia por língua, ajustável pelos dados.
Ganchos originais por vídeo; modelos copiados e conteúdo de IA genérico são evitados.

## 5. Produtos e preço
Escada de valor. **Os preços são hipóteses a testar**, não factos; a pesquisa só mostrou que templates Notion e planners vendem tipicamente entre 9 e 49 USD (fonte de vendedor de ferramentas).

| Degrau | Produto | Preço-hipótese | Função |
|---|---|---|---|
| Íman | Checklist ou mini-template gratuito | 0 | Ganhar o contacto (email) |
| Entrada | Template ou pack de prompts de uma tarefa | 5–15 € | Primeira compra, baixa fricção |
| Principal | Sistema completo (templates + guia + workflows) | 19–49 € | Receita principal |
| Pacote | Bundle de 2–3 sistemas | 39–79 € | Subir o valor médio |
| Recorrente (fase 2) | Atualizações/novos sistemas por subscrição | por testar | Receita estável |

Regras: preço testado por mercado (poder de compra difere entre PT, BR e ES); sem escassez falsa nem descontos «de 90%» inventados; devolução simples. Cada produto tem o dossiê de teste anexado (secção 7).

## 6. Fidelização
- Email como canal próprio (as redes não são nossas). Íman → sequência de boas-vindas → novidades.
- Compradores recebem **atualizações gratuitas** do produto e acesso antecipado a novos.
- Seguimento pós-compra: pergunta o que correu bem/mal; o feedback real alimenta o pilar «correu mal» e novos produtos.
- Comunidade (grupo de WhatsApp ou Telegram): fase 2, só se houver procura.

## 7. Produto: do teste ao lançamento (fidedignidade)
1. **Ideia** — o agente propõe com base em procura (palavras-chave por língua, concorrência, preços).
2. **Teste** — o agente usa a ferramenta/sistema numa tarefa real e guarda a prova (passos, tempos, capturas, erros). Dossiê em `docs/testes/<produto>/`.
3. **Produto** — construído a partir do dossiê.
4. **Aprovação do Ricardo** — vê o produto e o dossiê, usa-o brevemente (lista curta do agente) e aprova ou rejeita. **Sem aprovação não sai.**
5. **Lançamento** — conteúdo, afiliados identificados, rótulos de IA onde aplicável.
Regra de linguagem: afirmações no conteúdo têm de apontar para uma linha do dossiê.

## 8. Pipeline e automação
```
Pesquisa de tendências → Ideia de produto → Teste + dossiê → Produto → [Aprovação Ricardo]
→ Guiões/vídeos/legendas por língua → Calendário → Publicação (APIs oficiais)
→ Comentário com palavra-chave → DM automática (íman) → Email → Oferta de entrada → Principal
→ Pós-venda → Métricas → volta à pesquisa
```
**Componentes (propostas minhas, por validar):**
- **Pesquisa e métricas:** tarefa agendada que recolhe tendências e resultados e atualiza um painel; o agente propõe temas.
- **Produção de conteúdo:** guiões, narração (voz do Ricardo ou voz sintética **rotulada**), capturas de ecrã, legendas por língua.
- **Calendário e publicação:** fila por conta/língua; publicação por APIs oficiais.
- **Funil:** palavra-chave nos comentários → DM com o íman → email. Ferramenta de mercado (ManyChat) ou bot próprio sobre a API oficial.
- **Loja e entrega:** loja externa com link na bio (Gumroad, Stripe ou Lemon Squeezy); entrega automática do ficheiro.
- **Moderação:** respostas a comentários e DMs com guião e escalada para o Ricardo quando fugir ao guião.

**Limites conhecidos (confirmar nos documentos oficiais antes de construir):**
- TikTok: uma app não auditada só publica em privado; auditoria demora semanas. Via de reserva: rascunhos para o Ricardo publicar com um toque.
- Instagram: publicar exige revisão da app pela Meta; limites diários variam por fonte; DMs com janela de 24 h.
- **Política da Meta para respostas automáticas a comentários e DMs: não confirmada.**
- O TikTok Shop não aceita PDFs e cursos; vende-se por link externo.
- O agente só trabalha em sessões; a execução contínua exige tarefas agendadas ou um servidor.

**Modo de arranque (proposta minha):** primeiro mês semiautomático (o agente prepara tudo, o Ricardo toca onde a plataforma o exige); depois automático.

## 9. Idiomas
Arranque proposto: **PT-PT, PT-BR e ES** (a confirmar). Conteúdo e produtos adaptados ao local (exemplos, ferramentas disponíveis, meios de pagamento como Pix no Brasil), não só traduzidos. Cada alteração valida o idioma em todo o texto visível, incluindo o que os bots enviam.

## 10. Conformidade
- Afiliados e parcerias: aviso visível em cada publicação e na página do produto.
- Voz ou imagem sintéticas: rótulo de IA da plataforma; sem fingir pessoa humana que não existe.
- Sem alegações de saúde ou de rendimento; sem conselhos de investimento.
- Regras a confirmar nos textos oficiais: FTC (EUA), AI Act artigo 50 (UE, desde 2 de agosto de 2026), regras de cada plataforma.
- Dados pessoais (emails): consentimento claro e RGPD.
- Fiscalidade e entidade vendedora: o Ricardo decide com o seu contabilista.

## 11. Métricas
Por vídeo: retenção, partilhas, comentários com palavra-chave. Funil: comentário → DM → email → compra. Negócio: conversão por degrau, valor médio, devoluções, recompras. Decisões por dados dos próprios canais; números de blogs de ferramentas não servem de meta.

## 12. Papéis
- **Ricardo:** ajuda no set-up inicial (contas, pagamentos, IBAN, identidade, apps das plataformas); aprova produtos; usa o produto antes de aprovar.
- **Agente:** tudo o resto.

## 13. O que fica ao construtor
Escolha final de ferramentas (agendador, base de dados, editor de vídeo, voz), estrutura do repositório, nomes de marca e produtos, calendário detalhado.

## 14. Decisões em aberto
1. Idiomas de arranque.
2. Loja (Gumroad, Stripe, Lemon Squeezy).
3. DMs: ManyChat ou bot próprio (depende da política da Meta).
4. Voz: gravada pelo Ricardo ou sintética rotulada.
5. Nome da marca e dos canais.
