# R08 — Benchmark e posicionamento (para a demo)

> Data: **2026-11-12**. Método: buscas web, páginas oficiais dos fornecedores via WebFetch, documentação de ajuda e
> listas de preço de compras públicas (G-Cloud do Reino Unido).
> Convenção: **[V]** = visto nesta rodada na URL citada (página oficial ou documento primário); **[B]** = visto só
> em resumo de busca ou em site de terceiros (revenda, agregador); **[NV]** = não verificado.
> Preço só aparece quando há fonte **pública**, e preço de terceiro vem marcado [B]. Material de fornecedor é
> marketing: capacidade alegada não é capacidade demonstrada.
> Lado INFRA 4D: só o que está em `docs/ARQUITETURA.md`, executado e testado, **com dados fictícios**.
> Limites: o Reddit segue bloqueado para o agente e não houve contorno. A página de produto do TILOS redirecionou
> para uma página genérica da Trimble (ver §1). A loja da Eleco devolveu 429.

## Resumo executivo

- O mercado tem **4D maduro** (SYNCHRO, Navisworks, Fuzor), **planejamento corporativo** (P6/Primavera Cloud,
  Powerproject), **gestão de obra em nuvem** (ACC/Forma, Procore), **análise de qualidade de cronograma**
  (Acumen Fuse) e **previsão por IA a partir de histórico** (nPlan).
- **Linha de balanço / tempo-km** aparece em ferramentas específicas (TILOS; Powerproject, segundo o fornecedor;
  Prevision no Brasil, para obra repetitiva de edificação) ou em visualizadores de terceiros sobre o P6
  (ScheduleReader, TimeChainage). O próprio P6 Visualizer não documenta essa visão.
- A **previsão independente** (recalcular o término pela produtividade medida, com o motivo de cada data) não
  apareceu como função explícita de nenhuma das ferramentas pesquisadas. Os mais próximos são:
  - EVA no SYNCHRO Perform;
  - Monte Carlo no Primavera Cloud;
  - previsão por histórico no nPlan;
  - análise forense no Acumen Fuse.

  Esta é uma constatação **da pesquisa**, não prova de ausência.
- **IFC 4.3:** a página do SYNCHRO 4D lista importação até IFC 4 [V]. O Navisworks documenta um método de conversão
  com suporte a IFC 4.3 [B], sem confirmação para o TimeLiner.
- **Brasil público:**
  - o DNIT usa SIAC (contratos e medições) e SUPRA (relatórios de supervisão, uso obrigatório pela supervisora) [B];
  - a União usa o Obrasgov.br (CIPI), que tem **webservice público documentado** de execução física [B];
  - nenhum dos três faz previsão de término por CPM.
- **Onde o INFRA 4D está atrás:** escala, IFC real de cliente, colaboração multiusuário, mobile, suporte e base
  instalada. O beta é local, de um usuário, com dados fictícios.

## 1. Ferramentas comerciais e públicas

### 1.1 Tabela de capacidades

Colunas:
- **Prev. ind.:** recalcula o término pela produtividade medida, de forma independente da construtora.
- **LOB:** linha de balanço / tempo-km.
- **Auditoria:** analisa ou compara o cronograma recebido de terceiro.
- **IFC 4.3 infra:** 4D com IFC 4.3 de infraestrutura.

| Ferramenta | Prev. ind. | LOB | Auditoria | IFC 4.3 infra | Preço público | Fontes |
|---|---|---|---|---|---|---|
| **Bentley SYNCHRO 4D** (+ Perform/Control/Field) | Parcial. O 4D "compara linha de base e real" e "monitora desempenho de prazo e custo" [V]; EVA e captura de progresso web/mobile no **Perform** [B]. Sem menção a recalcular duração pela produtividade [NV] | O fornecedor cita "desafios espaciais de projetos lineares" [B]; visão tempo-km não documentada [NV] | Comparação LB × real [V] | **Importa IFC 2x, 2x2, 2x3 e 4; exporta 2x–2x3** (página do produto) [V]. IFC 4.3 não listado | **A partir de R$ 19.515,02 por 12 meses** (Virtuoso: 1 licença + 2 Keys) na página Bentley acessada do Brasil [V]; US$ 4.980 por 12 meses [B]; Perform: "Contact Us" [V] | https://www.bentley.com/software/synchro/ · https://www.bentley.com/en/products/synchro-perform/ · https://bentley.com/pds-synchro-control-ltr-en-lr-2 |
| **Autodesk Navisworks (TimeLiner)** | Não: o TimeLiner é simulação. Importa datas planejadas e reais de P6/Project e mostra "Planned against Actual" [B, ajuda Autodesk] | Não documentado [NV] | Planejado × real visual [B] | Método novo de conversão "enables support for IFC v4.3" na ajuda do Navisworks 2025 [B]; TimeLiner com IFC 4.3 [NV] | Só assinatura (Autodesk) [B]. Manage US$ 3.128,15/ano/assento na revenda CDW [B] | https://help.autodesk.com/cloudhelp/2025/ENU/Navisworks/files/GUID-E1CD4663-D460-4EA5-ABEC-FD24885BA3A6.htm · https://help.autodesk.com/cloudhelp/2025/ENU/Navisworks-Timeliner/files/GUID-91B08CFD-0B6B-4A2B-A853-BC8E173BA78C.htm · https://www.cdwg.com/product/autodesk-navisworks-manage-2027-new-subscription-annual-1-seat/9115559 |
| **Autodesk Construction Cloud / Build** (rebatizado Forma) | Não encontrado [NV] | Não encontrado [NV] | Não encontrado [NV] | [NV] | Forma Build (Reino Unido): £720 e £1.266 por usuário/ano, página Autodesk [B]; Build ≈ US$ 1.625/ano em agregadores [B] | https://www.autodesk.com/uk/products/forma-build/product-details · https://www.g2.com/products/autodesk-forma-formerly-autodesk-construction-cloud/pricing |
| **Oracle Primavera P6 / Primavera Cloud** | O CPM recalcula com a duração remanescente que o usuário informa; não deriva produtividade de medição [NV]. **Primavera Cloud tem Monte Carlo embutido** ("no add-on components") [B, docs Oracle] | **P6 Visualizer:** Gantt, TSLD e comparação, sem visão tempo-km na visão geral oficial [B]. Linear só por contorno manual ou por terceiros (ScheduleReader, TimeChainage) [B] | Comparação de versões no Visualizer [B] | Não é ferramenta 4D [NV] | Oracle não publica lista; **G-Cloud 15 (UK): P6 EPPM Cloud £244/usuário hospedado/mês, mínimo 25** [B, PDF de compras públicas] | https://docs.oracle.com/cd/E80480_01/help/en/user/90788.htm · https://docs.oracle.com/cd/F74771_01/client_help/en_US/66418.htm · https://assets.applytosupply.digitalmarketplace.service.gov.uk/g-cloud-15/documents/702001/817687594476487-pricing-document-2026-01-28-1553.pdf |
| **Asta Powerproject** (Eleco) | [NV] | O fornecedor apresenta LOB e lista "line of balance" como função [B]; se é nativa ou complemento, [NV] (fórum: "pode ser add-on") | [NV] | [NV] | Loja oficial deu 429 nesta rodada [NV] | https://elecosoft.com/us/webinar-powerproject-line-balance/ · https://planningplanet.com/comment/8789 |
| **Trimble TILOS** | [NV]. "Reflect distance data for rescheduling" [V] | **Sim: é o produto de tempo-distância** ("Time-Location System"), com histogramas e diagrama de massas no eixo da distância [V] | Relata dados reais e de progresso [V] | Não é 4D IFC [NV] | Sem preço oficial; US$ 2.095 a 4.290/ano em agregadores [B]. **A URL do produto em construction.trimble.com redirecionou para uma página genérica de construção** (status comercial [NV]) | https://tiloshelp.trimble.com/Get-Started/Introduction-to-the-Tilos-Time-Distance-Diagram · https://softwareconnect.com/reviews/trimble-tilos/ |
| **Trimble Quadri** (+ Connect) | Não, é colaboração em modelo [B] | Não (referência linear de objetos sim) [B] | Não | Formato agnóstico / padrões abertos (fornecedor) [B]; IFC 4.3 [NV] | [NV] | https://construction.trimble.com/en/products/quadri · https://www.trimble.com/en/blog/construction/article/trimble-quadri-and-trimble-connect-streamline-construction-work-on-the-highway-25-project-in-sweden |
| **Vico Office / Trimble** (location-based) | Controle de produção por local (LBMS), segundo material antigo [B] | Flowline [B] (material sem data) | [NV] | [NV] | [NV]. Status do produto [NV]; a ajuda do Trimble Connect ainda documenta "Vico locations" [B] | https://help.trimble.com/doc/trimble-connect/trimble-connect/connect-for-browsers-3d-viewer/organizer/vico-locations-and-organizer-groups |
| **Fuzor** (Kalloc) | Não | Não | Não | Cronograma importado por XML/CSV (P6, Project, Powerproject) [B, manual]; IFC para cronograma não achado | Sem lista oficial; valores conflitantes em agregadores [B] | https://fuzor-manual.atlassian.net/wiki/spaces/FM24/pages/26286840 |
| **Procore** | Não encontrado [NV] | Não encontrado [NV] | Não | [NV] | **Não publica preço**: cotação por volume anual de construção (ACV) [B] | https://blog.procore.com/deal-structures |
| **Deltek Acumen Fuse** (referência de auditoria) | Não recalcula pela produção | Não | **Sim: DCMA 14 pontos, 300+ métricas, comparação forense entre versões; lê P6, Project, Powerproject** [B, fornecedor] | Não | [NV] | https://www.deltek.com/products/ppm/schedule/acumen-fuse · https://help.deltek.com/Product/Acumen/8.11/GA/DCMA%2014%20Point%20Assessment%20Metric%20Descriptions.html |
| **nPlan** (referência de previsão independente) | **Previsão por aprendizado de máquina a partir de histórico de cronogramas** [B]; casos em ferrovia do Reino Unido (Network Rail, TRU) com números do próprio fornecedor [B] | Não | Analisa o cronograma recebido [B] | Não | [NV] | https://nplan.io/ · https://www.railwaygazette.com/uk/ai-to-improve-transpennine-route-upgrade-project-scheduling/62967.article |
| **Prevision (Sienge, Brasil)** | [NV] | **LOB e Gantt**, foco em obra repetitiva (edifícios, MCMV, loteamentos); importa MS Project (fornecedor) [B] | [NV] | [NV] | Teste de 15 dias; preço [NV] | https://sienge.com.br/prevision/ |
| **DNIT — SIAC** (público) | Não: registro e controle de contratos e medições (IN 57/2021, lida em R05) [V] | Não | Não | Não | Uso interno | R05 §2 · https://www.gov.br/dnit/pt-br/central-de-conteudos/atos-normativos/tipo/instrucao-normativa/2021/in-57-2021-direx-ba-176-de-16-09-2021.pdf |
| **DNIT — SUPRA** (público) | Não: relatórios de supervisão; uso **obrigatório** pela supervisora, e o recibo entra no processo de medição (IS 20/2019) [B] | Não | Não | Não | Uso interno | https://setcesp.org.br/noticias/dnit-lanca-sistema-de-supervisao-rodoviaria-avancada-supra/ · https://www.gov.br/dnit/pt-br/central-de-conteudos/instrucoes-normativas/instrucoes-de-servicos/2019/instrucao-de-servico-20-2019-colegiada-procedimentos-a-serem-utilizados-na-cgcont-ba-208-de-25-10-2019.pdf |
| **Obrasgov.br / CIPI** (União) | Não: cadastro e acompanhamento de projetos de investimento (Decreto 10.496/2020), execução física, georreferência por shapefile [B] | Não | Não | Não | Público. **Webservice documentado de execução física** [B] | https://www.gov.br/transferegov/pt-br/obrasgov/doc/webservice-obrasgov-execucao-fisica.pdf · https://www.gov.br/obrasgov/pt-br/sobre-obrasgov.br/documentacao-do-obrasgov.br/manual-do-obrasgov.br/manual-do-obrasgov.pdf/@@display-file/file |

### 1.2 Barreiras de adoção observadas

| Barreira | Onde aparece | Fonte |
|---|---|---|
| Licença por usuário, anual e paga em dólar ou libra | SYNCHRO (R$ 19,5 mil/ano, a partir de), Navisworks, Primavera Cloud (mínimo 25 usuários no G-Cloud), Forma Build | §1.1 |
| Preço só sob consulta e atrelado ao volume da empresa | Procore (ACV), Oracle (sem lista pública), TILOS | §1.1 |
| Ecossistema fechado ou proprietário (formato nativo, nuvem do fornecedor) | SYNCHRO (`.SP`), Primavera Cloud, ACC/Forma | [B] G-Cloud SYNCHRO: https://www.applytosupply.digitalmarketplace.service.gov.uk/g-cloud/services/918802916897257 |
| IFC 4.3 de infraestrutura ainda irregular nas ferramentas 4D | SYNCHRO (até IFC 4 na página), Navisworks (conversor sim, TimeLiner [NV]) | §1.1 |
| Visão linear fora do P6 exige outro produto | P6 + ScheduleReader/TimeChainage/TILOS | https://www.schedulereader.com/?p=4706 · https://timechainage.co.uk/ |
| Previsão por IA depende de histórico e de confiança no modelo | nPlan (números de acerto medidos pelo próprio fornecedor) | https://nplan.io/ |
| Integração com sistemas públicos | SIAC sem API pública conhecida (R05). Obrasgov.br tem webservice | R05 §2, §1.1 |

### 1.3 Contexto regulatório (motivação, não capacidade)

- **Lei 14.133/2021:**
  - art. 19 §3º: BIM "preferencialmente adotada";
  - art. 117 §1º: o fiscal registra todas as ocorrências.

  Lidos em R05 [V]: https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm
- **Decreto 10.306/2020:** BIM na execução de obras federais, em fases. O DNIT implantou pela IN 27/2021. A
  Estratégia BIM BR foi reinstituída pelo Decreto 11.888/2024. Calendário vigente das fases [NV] (fontes
  secundárias divergem) [B]:
  - https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2020/decreto/d10306.htm
  - https://www.gov.br/dnit/pt-br/central-de-conteudos/atos-normativos/tipo/instrucao-normativa/2021/in-27-2021-dpp-publ.pdf

## 2. Matriz INFRA 4D × mercado

Lado INFRA 4D: o que existe e tem teste, com **dados fictícios** (`docs/ARQUITETURA.md`).

| Dimensão | INFRA 4D hoje (evidência) | Mercado (melhor referência achada) | Situação |
|---|---|---|---|
| Previsão independente pela produtividade medida, com fonte por atividade e memória de cálculo | Sim (`cenarios.py`, `test_vertical_slice.py`) | Função explícita não encontrada; o mais próximo: EVA (SYNCHRO Perform), Monte Carlo (Primavera Cloud), IA por histórico (nPlan) | **Diferencial** a demonstrar com dado real |
| Explicação de por que o término mudou (efeito isolado, contrafactual, de cada atividade alterada) | Sim (`cenarios.py`) | Não encontrada | **Diferencial** |
| Três métodos lado a lado: CPM, Earned Schedule e Monte Carlo (v2 com correlação, riscos e chuva) | Sim (`previsao_es.py`, `montecarlo.py`, relatório) | Monte Carlo no Primavera Cloud; Primavera Risk Analysis à parte [B] | Paridade parcial; o confronto dos três num relatório é diferencial |
| Auditoria do cronograma da construtora (MSPDI/XER → motor próprio → comparação) | Sim, só com ida e volta própria e fixtures (`importadores/`) | Acumen Fuse: DCMA, 300+ métricas, forense [B]. Nós não temos DCMA 14 | **Atrás** em métricas de qualidade; **diferente** por recalcular no motor próprio. Falta validar com arquivo real |
| Linha de balanço tempo-km com cruzamento analítico de frentes e linha real executada | Sim (`recursos.py`, `fiscalizacao.py`) | TILOS (produto dedicado), Powerproject (fornecedor), visualizadores de P6 | Paridade de conceito com produto dedicado, sem a maturidade do TILOS. Integrado ao CPM e ao 4D |
| Fiscalização no modelo da IN 57/DNIT (diário, chuva, km executado, estados até aprovação, conciliação) | Sim (`fiscalizacao.py`, `test_fiscalizacao.py`) | SIAC/SUPRA (oficiais, internos); ferramentas estrangeiras não seguem IN 57 | **Diferencial local.** Não substitui o SIAC |
| 4D com IFC 4.3 de infraestrutura (IfcAlignment, IfcTask, vínculo elemento ↔ atividade) | Exporta e reimporta o próprio IFC4X3_ADD2, com 0 erros no `ifcopenshell.validate` (R07) | SYNCHRO até IFC 4 [V]; Navisworks com conversor IFC 4.3 [B] | Promissor, mas **sem IFC real de cliente**: atrás em prova |
| Visualização 3D/4D | Geometria sintética no navegador (three.js) | SYNCHRO/Navisworks/Fuzor com modelos grandes, realidade virtual, logística | **Atrás** |
| Escala e desempenho | 2 obras fictícias (~113–137 atividades); recálculo dentro do limite do manifesto | Portfólios corporativos | **Atrás / não medido** |
| Colaboração multiusuário, permissões, nuvem | Não (local, sem autenticação) | ACC/Forma, Procore, Primavera Cloud, SYNCHRO Control | **Atrás** |
| Mobile / campo | Esquema pronto; coleta não implementada | SYNCHRO Field/Perform, Procore, Build | **Atrás** |
| Suporte, treinamento, base instalada | Nenhum | Todos os comerciais | **Atrás** |
| Custo e licença | Local, sem licença paga; núcleo MIT/BSD/Apache, IfcOpenShell LGPL opcional (R04, R07) | Assinaturas anuais por usuário (§1.2) | **Diferencial** para piloto e órgão público |
| 5D | Fictício de propósito (sem SICRO/SINAPI) | SYNCHRO (cost), ACC, Procore | Atrás (de propósito) |

**O que seria preciso para competir** (ordem do `docs/IMPLANTACAO-REAL.md`):
1. Validar a previsão independente e a auditoria com cronogramas e medições **reais** (Fases 2 e 4). Sem isso, os
   diferenciais acima ficam como capacidade demonstrada só em dado fictício.
2. Métricas de qualidade de cronograma (DCMA 14, já listado em R02) para disputar com o Acumen na auditoria.
3. IFC 4.3 de cliente e de terceiros (arquivos da buildingSMART), mais desempenho com modelos grandes.
4. Multiusuário com papéis, auditoria pela sessão e hospedagem (Fases 5 e 6).
5. Coleta em campo (ODK) e importação dos arquivos que a fiscalização já produz (SIAC por arquivo). Avaliar o
   webservice do Obrasgov.br como fonte de execução física [B].

## 3. Frases de posicionamento para a apresentação

Cada frase pode ser conferida na demo ou num documento citado. Nenhuma alega compatibilidade, dado real ou escala.

1. "O INFRA 4D recalcula o término da obra a partir da produtividade medida nos boletins e mostra, para cada data,
   de onde veio o número." (vertical slice; `test_vertical_slice.py`)
2. "Quando a previsão muda, o sistema explica, atividade por atividade, quanto aquela mudança sozinha move o término."
   (efeito isolado contrafactual, `cenarios.py`)
3. "Três métodos independentes lado a lado: caminho crítico, Earned Schedule e Monte Carlo. Quando eles divergem,
   isso também é informação." (relatório; `previsao_es.py`, `montecarlo.py`)
4. "O cronograma da construtora, em MS Project XML ou Primavera XER, é recalculado no nosso próprio motor para
   auditoria. Hoje isso está validado com arquivos de teste; a validação com arquivos reais é o próximo passo."
   (`importadores/`, ADR-0003)
5. "Para obra linear, a linha de balanço tempo-km aponta onde e quando duas frentes vão se encontrar, junto do
   caminho crítico e do 4D." (`recursos.py`)
6. "A fiscalização segue o modelo de medição do DNIT (IN 57/2021): diário, chuva, km executado e aprovação do fiscal.
   O sistema complementa o SIAC; não o substitui." (`fiscalizacao.py`, R05 §2)
7. "Tudo o que você está vendo roda nesta máquina, sem licença paga e com dados fictícios. Nenhum dado de obra real
   foi usado." (ADR-0002, ADR-0004, ADR-0005)
8. "Exportamos a obra para IFC 4.3, com alinhamento e cronograma, e o arquivo passa no validador do IfcOpenShell sem
   erros. O teste com modelo de cliente ainda não foi feito." (R07)

**O que NÃO dizer:** "compatível com P6/Project"; "substitui SYNCHRO, Navisworks ou TILOS"; "mais preciso que o
mercado"; "pronto para produção"; qualquer número de economia ou acerto. Nada disso foi medido.

## 4. Itens não verificados

- Preço e status atual do TILOS (a página do produto redireciona).
- Se a LOB do Powerproject é nativa ou complemento, e o preço.
- IFC 4.3 no TimeLiner.
- Preço do Fuzor.
- Recursos de previsão do Procore e do ACC.
- Calendário vigente das fases do Decreto 10.306/2020.
- Situação atual do Vico Office.
- Conteúdo do webservice do Obrasgov.br (PDF não aberto).

---

## Resumo (10 linhas)

1. Pesquisados 16 itens: comerciais de 4D/planejamento/gestão, referências de auditoria (Acumen) e de previsão (nPlan), Prevision e sistemas públicos (SIAC, SUPRA, Obrasgov.br).
2. Ninguém documenta claramente "recalcular o término pela produtividade medida com explicação". É o diferencial central, ainda demonstrado só com dado fictício.
3. LOB tempo-km existe em produto dedicado (TILOS) ou por terceiros sobre o P6; o P6 Visualizer não documenta essa visão.
4. SYNCHRO 4D lista IFC só até a versão 4 [V]; Navisworks tem conversor IFC 4.3 [B]. O nosso IFC 4.3 só foi provado com arquivo próprio.
5. Auditoria de cronograma: o Acumen Fuse (DCMA, forense) está à frente. Nosso diferencial é recalcular no motor próprio, mas falta DCMA e arquivo real.
6. Preços públicos: SYNCHRO 4D a partir de R$ 19.515/ano [V]; P6 EPPM Cloud £244/usuário/mês, mínimo 25 (G-Cloud) [B]; Procore e Oracle sob consulta.
7. No Brasil, SIAC e SUPRA são obrigatórios e internos; o Obrasgov.br tem webservice de execução física [B]. Nenhum faz previsão por CPM.
8. Estamos atrás em escala, IFC de cliente, multiusuário, mobile e suporte.
9. Oito frases de posicionamento verificáveis, cada uma com evidência, e uma lista do que não dizer.
10. Para competir: validar com dado real (Fases 2 e 4), DCMA 14, IFC de cliente e multiusuário.
