# R05 — Pesquisa aprofundada (IFC 4.3, fiscalização, linear scheduling, risco, 5D, GIS, IA)

> Data: **2026-11-12**. Complementa R01–R04 (não repete o que já está lá; R04 continua valendo para as licenças que verificou).
> Método: API do GitHub (`/repos`, `/releases/latest`, `/git/trees`, `/license`), arquivos brutos (raw.githubusercontent.com),
> metadados do PyPI (`/pypi/{p}/json`), páginas oficiais (gov.br, planalto.gov.br, docs.getodk.org, postgis.net, gao.gov,
> arxiv.org, epsg.io) via WebFetch e buscas web. Texto de PDF do DNIT extraído localmente com `pdftotext`.
> Convenção: **[V]** = visto nesta rodada na URL citada; **[B]** = visto só em resumo de busca (página não aberta);
> **[NV]** = não verificado. Nada aqui é parecer jurídico.
> Limitações da rodada: o **Reddit** continua bloqueado para o agente ("domains not accessible to our user agent") — não
> houve tentativa de contornar. A página do SINAPI na CAIXA não abriu pela ferramenta (loop de redirecionamento) e a do
> IBGE devolveu 403. A API do GitHub atingiu o limite de requisições no fim da rodada (itens marcados [NV]).

## Resumo executivo

1. **IFC 4.3 para teste existe e é gratuito, mas o "oficial" não tem alinhamento.** `buildingSMART/Certification-datasets` (CC BY 4.0) traz `Infra-Rail.ifc` e `Infra-Road.ifc` em **IFC4X3_ADD2**, georreferenciados (IfcMapConversion), porém **sem IfcAlignment**. Os exemplos com IfcAlignment, IfcLinearPlacement e IfcTask estão em `buildingSMART/IFC4.x-specification-models`, sob "todos os direitos reservados até a publicação formal" → baixar no teste, **não versionar no Git**.
2. **Validador:** o serviço da buildingSMART aceita IFC4X3_ADD2, é MIT e **pode rodar local (Docker)**; o online exige conta e não fala de privacidade → nunca subir modelo de cliente nele. `python -m ifcopenshell.validate --rules --json` é o mesmo validador usado no CI dos exemplos oficiais. IfcTester 0.9.0 é LGPL-3.0-or-later.
3. **Fiscalização DNIT (IN 57/2021, lida no PDF):** a medição no SIAC compreende ficha de medição, **diário de obras**, avanço físico, **pluviometria** e PGQ; horários de chuva são anotados obrigatoriamente no diário. Nosso boletim (`atividade_id, semana_inicio, quantidade, equipes_dias, origem`) não tem trecho executado (km), chuva, foto nem estado de aprovação do fiscal. Não foi achada API pública do SIAC.
4. **Coleta de campo:** ODK Central tem REST + OData com anexos (fotos) e Entities [V]; pyxform (XLSForm) é BSD-2; KoboToolbox servidor (kpi) é **AGPL-3.0** e o `kobocat` foi **arquivado**.
5. **Linear scheduling:** a base acadêmica do nosso detector é o *Repetitive Scheduling Method* (Harris & Ioannou 1998) e o LBMS (Kenley & Seppänen). Continua **não havendo ferramenta aberta** de diagrama tempo-km de obra (confirma R02/R04). Nosso `conflitos_balanco` já tem buffer espacial + temporal; faltam cruzamento analítico e linha "real" a partir dos boletins.
6. **Previsão:** fórmulas do Earned Schedule confirmadas no site de Lipke (SPI(t)=ES/AT; IEAC(t)=PD/SPI(t)); **ainda não implementado** no código. AACE 57R-09 (risk drivers preservam correlação) visto só em fontes secundárias. Base de projetos reais com EVM/ES (OR&S/UGent, DSLIB) serve de oráculo, licença não declarada.
7. **5D:** SICRO sai por UF/mês em **`.7z`** (SP jul/2026 publicado 2026-09-25) e o portal gov.br do DNIT declara **CC BY-ND 3.0** — cláusula "sem derivações" é dúvida jurídica para redistribuir base derivada. Qto do IFC 4.3 verificados (ex.: `Qto_EarthworksFillBaseQuantities` separa **CompactedVolume** e **LooseVolume** — casa com empolamento/transporte do SICRO).
8. **Estaca:** "20 m, notação `E + m`" só achada em material didático (USP), não em norma DNIT. IFC 4.3 modela **equação de estacas** (`Pset_Stationing.IncomingStation`) → conversão km↔estaca não pode ser só `km*50`.
9. **IA:** existe `ifcopenshell-mcp` 0.9.0 (LGPL-3.0+, dentro do repo IfcOpenShell) e `project-mcp` (MIT, lê XER/PMXML localmente). Só oportunidade futura; exige ADR e evals (componente_llm hoje é false).

---

## 1. IFC 4.3 de ferrovia/rodovia e validadores

| Item | URL | Licença/acesso verificado | Manutenção vista | Uso no INFRA 4D | Recomendação |
|---|---|---|---|---|---|
| Certification-datasets (antigo `Sample-Test-Files`, redireciona) | https://github.com/buildingSMART/Certification-datasets | **CC BY 4.0** (arquivo LICENSE) [V] | push 2026-09-04 [V] | `IFC 4.3.2.0 (IFC 4.3 ADD2)/Simple-Scene/Infra-Rail.ifc` (161 kB; IFCRAILWAY, IFCRAILWAYPART, 66 IFCTRACKELEMENT, IFCRAIL, IFCCOURSE) e `Infra-Road.ifc` (IFCROAD, 26 IFCROADPART, 16 IFCEARTHWORKSFILL); ambos com IFCPROJECTEDCRS + IFCMAPCONVERSION; gerados por SketchUp-IFC-manager 5.6.0 em 2026-06-23 [V] | **Adotar** para teste de importação de elementos, hierarquia espacial e georreferência. **Não serve** para referência linear: **zero IfcAlignment** [V]. CC BY permite versionar com atribuição (mas o `.gitignore` do projeto e o tamanho recomendam baixar no teste) |
| IFC4.x-specification-models | https://github.com/buildingSMART/IFC4.x-specification-models | **"All Rights reserved until formal release"**; IFC final sob CC BY-ND 4.0 (README) [V] | push 2026-10-14 [V]; CI valida todos os modelos [V] | `alignment-geometries-and-linear-positioning/segmented-reference-curve.ifc` (IFC4X3_ADD2: IfcAlignment + Horizontal/Vertical/**Cant**, IfcGradientCurve, IfcLinearPlacement, IfcPointByDistanceExpression) [V]; `linear-placement-of-signal`, `sectioned-solid-horizontal`, `fixed-reference-swept-area-solid`; **`construction-scheduling/construction-scheduling-task.ifc`** (IfcTask) [V]; `test/alignment_tests.py` | **Adotar como fixture externa** (download no teste, fora do Git). É o melhor oráculo para P3 do R01 (estações do eixo) e para o vínculo IfcTask ↔ atividade |
| Community-Sample-Test-Files | https://github.com/buildingsmart-community/Community-Sample-Test-Files | **sem licença declarada** (API: license null) [V] | push 2026-11-03 [V] | `IFC 4.3.2.0 (IFC 4.3)/Chesapeake Bay Bridge-Tunnel IFC Model/...4x3.ifc`; arquivo RC (`UT_Alignment_12d_11`, `LinearPlacement_1/2`) [V] | Só uso local de bancada; **não versionar**. Arquivos "RC" são de schema candidato — esperar falhas no validador |
| bSI-RailwayRoom/IFC-Rail-Unit-Test-Reference-Code | https://github.com/bSI-RailwayRoom/IFC-Rail-Unit-Test-Reference-Code | sem licença declarada [V] | último push **2024-05-19** [V] | código utilitário dos testes do IFC Rail | Descartar (parado, sem licença) |
| Validation Service (buildingSMART) | https://github.com/buildingSMART/validate · guia: https://buildingsmart.github.io/validate/user/index.html | **MIT** (código) [V]; online exige login e Termos de Uso; schemas aceitos **IFC2X3, IFC4, IFC4X3_ADD2**; ≤ 256 MB, `.ifc` não zipado [V]; privacidade/retenção **não descrita** na página [V] | v1.0.5 — 2026-09-30; push 2026-11-12 [V] | Checagem de sintaxe STEP, schema, regras normativas (IA/IP) e "industry practices" (avisos); bSDD desativado desde v0.6.6 [V]. README: sobe local com `docker compose up`, Swagger em `/api/swagger-ui` [V] | **Adotar**: online só com arquivos públicos; para modelo de cliente, **self-host** (Docker) ou ifcopenshell.validate local |
| ifc-gherkin-rules | https://github.com/buildingSMART/ifc-gherkin-rules | **MIT** [V] | v1.0.5 — 2026-09-30 [V] | regras normativas usadas pelo serviço | Avaliar depois (só se quisermos as mesmas regras offline) |
| ifcopenshell.validate | (pacote `ifcopenshell`, PyPI) · uso visto em https://github.com/buildingSMART/IFC4.x-specification-models/blob/main/validate.sh | LGPL-3.0-or-later (PyPI 0.9.0.post1, 2026-10-15) [V] | idem R04 | `python -m ifcopenshell.validate --rules --json arquivo.ifc` (linha exata do CI oficial) [V] | **Adotar** na Fase 2 (item 9): todo IFC importado passa por ele antes de virar GLB |
| IfcTester (IDS) | PyPI `ifctester` · `src/ifctester/pyproject.toml` (branch v0.9.0) | **LGPL-3.0-or-later** (pyproject) [V] | 0.9.0 — 2026-09-29 [V]; depende de flask, bcf-client, xmlschema, odfpy… [V] | Verificar requisitos de informação: "todo IfcCourse tem Qto e código de composição", "todo elemento tem GlobalId vinculado a atividade" | **Avaliar depois** (Fase 2) — dependências pesadas; usar só em ferramenta de bancada/CI |
| IDS (padrão) | https://github.com/buildingSMART/IDS | **CC BY-ND 4.0** (LICENSE) [V] | v1.0.0 — 2024-06-03; push 2026-09-25 [V] | formato XML de requisitos | Adotar como formato (não redistribuir o XSD modificado) |
| Quantity sets IFC 4.3 | https://github.com/buildingSMART/IFC4.x-development (`reference_schemas/psd/*.xml`) | licença do repo NOASSERTION [V] | push 2026-11-12 [V] | Existem `Qto_CourseBaseQuantities`, `Qto_PavementBaseQuantities`, `Qto_EarthworksCut/FillBaseQuantities`, `Qto_RailBaseQuantities`, `Qto_SleeperBaseQuantities`, `Qto_KerbBaseQuantities`, `Qto_PileBaseQuantities`… [V] (detalhe na §5) | Base do mapeamento 5D |

## 2. Fiscalização de obras no Brasil e coleta em campo

| Item | URL | Licença/acesso verificado | Manutenção/vigência vista | Uso no INFRA 4D | Recomendação |
|---|---|---|---|---|---|
| **IN 57/DNIT SEDE, 14/09/2021** (SIAC, suporte documental e pagamento de medição) | https://www.gov.br/dnit/pt-br/central-de-conteudos/atos-normativos/tipo/instrucao-normativa/2021/in-57-2021-direx-ba-176-de-16-09-2021.pdf | público [V] | vigência atual **[NV]** | Lido [V]: art. 2º XII define SIAC como "sistema corporativo do DNIT que tem por objeto o registro e controle dos contratos e medições"; **art. 10**: medição de obras no SIAC = (I) ficha de medição, (II) informações do **Diário de Obras**, (III) controle do **avanço físico**, (IV) **índices de pluviometria**, (V) PGQ (rodoviário); **art. 11**: fiscal e contratada "devem obrigatoriamente anotar no Diário de Obras os períodos (horários) do dia de ocorrência de chuvas"; arts. 12–13: **BDP** (Boletim de Desempenho Parcial) avalia cronograma físico, equipamentos, pessoal, qualidade; art. 16–17: medição liberada e aprovada pelo **fiscal do contrato**. Anexo I (suporte documental): diário, memória de cálculo, rel. pluviométrico, rel. fotográfico, rel. de avanço físico, PGQ, Resumos A/B/C do SIAC (obrigatórios: memória de cálculo e Resumos A, B, C). Anexo IV inclui **Curva S** | **Adotar como referência de modelo de dados** do boletim (Fase 3). O nosso produto não substitui o SIAC; ele lê o que a fiscalização já produz |
| Lei 14.133/2021 | https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm | público [V] | — | **art. 117 §1º**: "O fiscal do contrato anotará em registro próprio todas as ocorrências relacionadas à execução do contrato" [V]; **art. 140 I a/b**: recebimento provisório e definitivo "mediante termo detalhado" [V]; **art. 19 §3º**: BIM "preferencialmente adotada" em obras e serviços de engenharia [V] | Argumento comercial: registro de ocorrências + BIM são dever legal; o 4D dá rastreabilidade |
| IS 01/2014 (modelo de medição DNIT) | https://www.gov.br/dnit/pt-br/assuntos/licitacoes/legislacao/instrucoes-normativas/boletim-n-009-instrucao-de-servico-01-de-2014-define-modelo-de-medicao-de-obras-e-servicos-no-ambito-do-dnit.pdf | público | 2014; vigência [NV] | [B] fiscal autentica medição no SIAC; bloqueio sem justificativa escrita; relatório fotográfico com 3 fotos | Ler antes da Fase 3 |
| IS 20/2019 (acompanhamento de obras, relatórios de supervisão CGCONT) | https://www.gov.br/dnit/pt-br/central-de-conteudos/instrucoes-normativas/instrucoes-de-servicos/2019/instrucao-de-servico-20-2019-colegiada-procedimentos-a-serem-utilizados-na-cgcont-ba-208-de-25-10-2019.pdf | público | [B] | [B] supervisora elabora relatório; fiscal do contrato de supervisão aprova | Ler antes da Fase 3 (modelo de relatório de supervisão = saída que podemos gerar) |
| SUPRA (sistema de supervisão DNIT, 2016) e SIAC (SERPRO) | notícias SERPRO: https://serpro.gov.br/menu/noticias/noticias-antigas/dnit-lanca-boletim-eletronico-de-medicao | sistemas internos | [B] | **Nenhuma API pública encontrada** [NV] | Integração só por exportação/planilha que o cliente fornecer |
| ODK Central (API) | https://docs.getodk.org/central-api/ | Apache-2.0 (R04) | v2026.3.1 (R04) | REST `/projects/:id/forms/…/submissions`, **anexos de mídia por submissão**, **OData** ("straightforward JSON output"), **Entities** em `/projects/:id/datasets` [V] | **Avaliar (Fase 3)**: coletor preferido — licença permissiva, export JSON/OData, foto por submissão |
| pyxform (XLSForm → XForm) | PyPI/GitHub `XLSForm/pyxform` | **BSD-2-Clause** [V] | v4.5.0 — 2026-06-25; push 2026-11-10 [V] | Gerar o formulário de boletim a partir de uma planilha versionada | Adotar quando houver coletor |
| KoboToolbox (kpi) | https://github.com/kobotoolbox/kpi | **AGPL-3.0** [V] | 2.026.37g — 2026-11-11 [V] | mesmo ecossistema XLSForm | Só como serviço externo; plano gratuito tem limites (forum: 5k submissões/mês, 1 GB [B]; página oficial de limites não detalha valores [B]); termos do servidor humanitário [NV] |
| kobocat | https://github.com/kobotoolbox/kobocat | BSD-2-Clause [V] | **arquivado**; último release 2024-08-28 [V] | — | Descartar (R02 citava Kobo genericamente) |
| QField | (R04) | GPL-2.0 | v4.3.8 — 2026-11-12 (R04, reconfirmado) | coleta GIS offline por estaca (GeoPackage) | Ferramenta externa; troca por GPKG |

**Como se ligaria ao nosso boletim (proposta, sem código):**

```
XLSForm versionado (pyxform)  →  ODK Collect (campo, offline, foto + GPS)  →  ODK Central (OData/JSON + anexos)
  →  importador INFRA 4D (CSV/JSON → validação)  →  boletim {atividade_id, periodo_ini, periodo_fim, quantidade,
     equipes_dias, km_ini_exec, km_fim_exec, horas_chuva, fotos[{sha256, lat, lon, data}], estado ∈ {rascunho,
     conferido_fiscal, aprovado_siac}, ref_memoria_calculo, origem}
```

Campos novos justificados pela IN 57: `horas_chuva` (art. 11), `estado` (art. 16–17: só medição aprovada pelo fiscal
vale como "medido"), fotos (Anexo I item 4), `km_ini_exec/km_fim_exec` (avanço físico por trecho; alimenta a linha
real do diagrama tempo-km). Dado real → continua bloqueado pela Fase 3 (ADR-0004).

## 3. Linear scheduling / Line of Balance / tempo-km

| Item | URL | Licença/acesso | Manutenção | Uso no INFRA 4D | Recomendação |
|---|---|---|---|---|---|
| Harris & Ioannou (1998), *Scheduling Projects with Repeating Activities*, JCEM 124(4):269–278, DOI 10.1061/(ASCE)0733-9364(1998)124:4(269) | https://structurae.net/fr/litterature/article-de-revue/scheduling-projects-with-repeating-activities | artigo pago (ASCE) [B] | — | Base do **RSM**: linhas de produção X-Y, *controlling sequence*, buffers mínimos de tempo/espaço entre atividades | Citar no ADR do detector de conflitos; DOI conferido só em 2 listagens, não na ASCE [B] |
| Kenley & Seppänen, *Location-Based Management for Construction* | https://lehmanns.de/shop/technik/53901358-9780367577292-location-based-management-for-construction | livro pago [B] | — | LBMS: CPM "aumentado" com lógica em camadas por local; previsão de alarme de produção ~2 semanas antes (Seppänen 2009) [B] | Referência para "alarme de produção" a partir dos boletins (casa com item 7b) |
| Tese U. Alberta (buffers espaciais/temporais em ferramenta de linear scheduling) | https://era.library.ualberta.ca/items/e8a213cc-9b07-42f0-b267-394736136667/download/815eb73a-c9fb-495a-9d99-e4739cf16a28 | acesso aberto [B] | — | definição de *space buffer* / *time buffer* | Ler para nomear as métricas |
| Ferramentas abertas de diagrama tempo-km | buscas GitHub "line of balance", "time-location", "time-chainage" | — | — | Achados: geradores de gráfico de trens (Paiagram, train_graph — horário ferroviário, não obra) e um gist de Matplotlib (obra de bonde em Budapeste) [B] | **Nenhuma ferramenta aberta de obra** — mantém R02/R04: implementar no produto (já feito na v0.2.0) |
| TILOS / Turbo-Chart / Time Chainage | https://tiloshelp.trimble.com/Get-Started/Introduction-to-the-Tilos-Time-Distance-Diagram · https://turbo-chart.com/time-distance-location-diagram-chart · https://timechainage.co.uk/ | comerciais [B] | — | oráculo visual (se o cliente tiver licença) | Não adotar |

**Validação do nosso módulo (`scripts/infra4d/recursos.py::conflitos_balanco`, lido nesta rodada):**
o detector já mede distância espacial (`buffer_km`) e folga temporal (`buffer_dias`) entre antecessora e sucessora no
mesmo segmento — exatamente as duas métricas de buffer do RSM. Lacunas observadas:
1. **Amostragem diária** em dias corridos: a data e o km do pior momento são aproximados; o cruzamento de duas retas é
   resolvível analiticamente (t* = interseção das retas km×t), sem custo.
2. **Linha planejada apenas** (ES→km_ini, EF→km_fim, ritmo constante). O RSM/LBMS compara também a **linha real**; com
   `km_ini_exec/km_fim_exec` no boletim (§2) dá para desenhar a linha real por trechos e projetar o ritmo medido.
3. **Sem "controlling sequence"**: o RSM identifica qual frente controla o prazo no espaço; hoje temos cadeia
   determinante só no CPM.

## 4. Schedule risk analysis e previsão independente

| Item | URL | Licença/acesso | Manutenção | Uso no INFRA 4D | Recomendação |
|---|---|---|---|---|---|
| Earned Schedule (Lipke) | https://www.earnedschedule.com/Docs/Forecasting Schedule Variance Using Earned Schedule.pdf · https://www.earnedschedule.com/Docs/Applying ES to Critical Path and More.pdf | PDFs públicos [B] | artigos 2007–2017 | SV(t)=ES−AT; **SPI(t)=ES/AT**; **IEAC(t)=PD/SPI(t)** (curta) ou AT+(PD−ES)/PF(t) (longa); IECD = início + IEAC(t); mesma fórmula por marco usando MD [B, consistente em várias fontes do mesmo site] | **Adotar** (BACKLOG novo): é a 3ª previsão independente, ao lado do CPM com produtividade medida e do Monte Carlo. Não está no código hoje (grep sem ocorrência) |
| AACE RP 57R-09 (integrated cost & schedule risk analysis, risk drivers + Monte Carlo sobre CPM) | https://soma-website.pages.dev/resources/glossary/aace-57r-09/ · https://archivedproceedings.econference.io/wmsym/2012/papers/12419.pdf | RP pago; só fontes secundárias [B] | — | "risk driver" = multiplicador comum a todas as atividades afetadas na mesma iteração → preserva correlação; exige CPM com lógica "tight"; lags fixos na simulação podem distorcer [B] | Usar o conceito (driver "chuva", driver "frente/equipe"); citar como [B] até alguém ler o RP |
| GAO-16-89G — *Schedule Assessment Guide* (dez/2015) | https://www.gao.gov/products/gao-16-89g | público (termos de copyright do GAO não lidos) [V] | 2015 | 10 boas práticas; inclui schedule risk analysis [V] | Referência gratuita para os critérios de qualidade/SRA (alternativa ao PMI/AACE pagos) |
| PMI *Practice Standard for Scheduling* 3ª ed. (2019) | https://www.pmi.org/shop/p-/book/practice-standard-for-scheduling---third-edition/00101612701 | pago | 2019 | sumário tem "Schedule Risk Assessment" e earned schedule [B] | Referência; não necessária para implementar |
| OR&S / UGent — DSLIB (projetos reais com dados de controle EVM/ES) | https://www.projectmanagement.ugent.be/research/data · .../data/realdata | download livre; **licença não declarada** [V] | 200+ projetos (página diz 203 e 231) [V]; formato ProTrack + Excel [V] | **Oráculo** do Earned Schedule e da calibração do Monte Carlo com projetos reais | Uso local, fora do Git; citar Batselier & Vanhoucke (2015), IJPM 33(3):697–710 |
| pmcontrols | PyPI `pmcontrols` | MIT [V] | 0.2.1 — 2026-06-15 [V] | CPM, PERT+Monte Carlo, EVM e ES | Oráculo cruzado de fórmulas ES (não dependência) |
| trueppm-scheduler | PyPI `trueppm-scheduler` | Apache-2.0 [V] | 0.4.0 — 2026-10-31 [V] | Monte Carlo PERT-Beta vetorizado | Avaliar só como oráculo |
| mcprojsim | PyPI `mcprojsim` | MIT [V] | 0.15.2 — 2026-05-01 [V] | foco em software; Spearman de sensibilidade | Descartar (domínio diferente); ideia de **índice de sensibilidade** aproveitável |
| SimPM | PyPI `simpm` · https://github.com/Project-SimPM/SimPM | MIT [V] | 2.1.2 — 2025-12-20 [V] | simulação de eventos discretos de obra | Avaliar depois (simulação de equipamentos/ciclos) |
| cheche-pm | PyPI `cheche-pm` | MIT [V] | 0.1.13 — **2023-10-08** [V] | — | Descartar (parado) |
| pyCritical | PyPI `pycritical` | licença ambígua ("GNU" no PyPI) [V] | 1.8.2 — 2026-05-07 [V] | — | Descartar (licença indefinida) |
| numpy / scipy | PyPI | numpy: BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 [V]; scipy: BSD (texto no PyPI) [V] | numpy 2.5.4 (2026-10-10); scipy 1.18.1 (2026-08-21) [V] | cópula gaussiana (normal multivariada + CDF) para correlação entre serviços | Só se o Monte Carlo atual (stdlib `random`) não bastar; hoje dá para fazer driver comum sem dependência nova |

**Leitura do nosso Monte Carlo (`scripts/infra4d/montecarlo.py`):** bootstrap dos boletins, correlação **dentro** da
(lote, serviço), independência **entre** frentes; o próprio docstring admite faixa estreita demais (sem correlação entre
serviços, sem eventos discretos, sem chuva estocástica). A recomendação da AACE (risk drivers) resolve as três com o mesmo
mecanismo: um multiplicador sorteado por iteração aplicado a todas as atividades expostas ao driver.

## 5. BIM 5D no Brasil: SINAPI e SICRO

| Item | URL | Licença/acesso verificado | Manutenção vista | Uso no INFRA 4D | Recomendação |
|---|---|---|---|---|---|
| SICRO — relatórios por região/UF/mês | https://www.gov.br/dnit/pt-br/assuntos/planejamento-e-pesquisa/custos-referenciais/sistemas-de-custos/sicro/relatorios/relatorios-sicro | download livre; portal gov.br/DNIT declara "Todo o conteúdo deste site está publicado sob a licença" **CC BY-ND 3.0** [V] | data-base mais recente **julho/2026** (ES, MG, SP, RJ) [V]; SP: arquivo único **`sp-07-2026.7z`**, publicado 2026-09-25 [V]; arquivos antigos em `.rar` (MG jan/2017) [V] | Fonte de composição (código, unidade, produção da equipe, custo horário) | **Avaliar (oportunidade 5D)**: importador lê o `.7z` que o usuário baixa; **não redistribuir** a base nem tabela derivada sem parecer sobre o "ND" |
| SICRO — informativos e contato | https://www.gov.br/dnit/pt-br/assuntos/planejamento-e-pesquisa/custos-referenciais/sistemas-de-custos/sicro/informativos/informativo-sicro-no-01-2026.pdf | público [B] | 2026 | mudanças de base | Monitorar |
| SINAPI (CAIXA/IBGE) | https://www.caixa.gov.br/sinapi (página não abriu) · apresentação CAIXA: https://www.gov.br/transferegov/pt-br/noticias/eventos/fntu/x-fntu/apresentacoes/evento-016-sinapi-a-referencia-para-o-seu-orcamento-de-obra.pdf (HTTP 401) | **[NV]** termos de uso | IBGE publicou ref. jul/2026 em 11/08/2026 [B]; caderno: https://ftp.ibge.gov.br/Precos_Custos_e_Indices_da_Construcao_Civil/Fasciculo_Indicadores_IBGE/sinapi_202607caderno.pdf [B] | [B] desde 2025 publica "Pacote XLSX" e "Pacote ZIP" com famílias, insumos por UF, composições sintéticas por UF e analíticas sem custo; insumo sem coleta mínima sai em branco | Relevante para obra civil/edificação de apoio; **SICRO é o primário** para rodovia/ferrovia. Verificar termos antes de qualquer importador |
| Revendedores (Orçamentor, OrçaFascio) | https://orcamentor.com/sicro/ | privados | — | consulta rápida | Não usar como fonte de dado (R04 já alertou) |
| IFC 4.3 Qto (psd oficiais) | https://github.com/buildingSMART/IFC4.x-development/tree/master/reference_schemas/psd | — | push 2026-11-12 [V] | `Qto_CourseBaseQuantities`: Length, Width, Thickness, Volume, GrossVolume, Weight · `Qto_PavementBaseQuantities`: Length, Width, Depth, GrossArea, NetArea, GrossVolume, NetVolume · `Qto_EarthworksCutBaseQuantities`: Length, Width, Depth, **UndisturbedVolume, LooseVolume**, Weight · `Qto_EarthworksFillBaseQuantities`: Length, Width, Depth, **CompactedVolume, LooseVolume** [V] | Ver caminho abaixo |

**Caminho concreto IfcElementQuantity → composição (proposta testável):**

1. No IFC: código da composição como `IfcClassificationReference` (sistema "SICRO", `Identification` = código) associado
   ao elemento ou ao tipo; quantidade vem do `Qto_*BaseQuantities` padrão — nunca de geometria recalculada em silêncio.
2. Tabela versionada `mapa_composicao(classe_ifc, qto, quantidade, codigo, sistema, unidade_composicao, fator, nota)`.
   Exemplos: `IfcEarthworksFill / Qto_EarthworksFillBaseQuantities / CompactedVolume → m³ compactado`;
   transporte usa `LooseVolume` × DMT → m³·km ou t·km (conferir unidade da composição); `IfcCourse (lastro) /
   Qto_CourseBaseQuantities / Volume → m³` (casa com ETS-002 do R04: "por m³ lançado").
3. Preço: `preco(codigo, uf, data_base, desonerado)` lido do arquivo SICRO que o **usuário** baixou; custo = quantidade ×
   fator × preço. Unidade divergente = erro, não conversão implícita.
4. Para o 4D: atividade ↔ elementos (GlobalId) → quantidade planejada da atividade = Σ Qto dos elementos; produtividade
   planejada pode vir da "produção da equipe" da composição (R04 achou 25,46 m³ para a 3009091 — unidade de tempo a
   confirmar).

## 6. GIS e referência linear (km ↔ estaca)

| Item | URL | Licença/acesso verificado | Manutenção vista | Uso no INFRA 4D | Recomendação |
|---|---|---|---|---|---|
| PostGIS `ST_LineLocatePoint` | https://postgis.net/docs/ST_LineLocatePoint.html | PostGIS GPL-2.0 (espelho GitHub `postgis/postgis`) [V] | push 2026-11-10 [V]; versão atual [NV] | retorna "a float between 0 and 1" = fração do **comprimento 2D**; usar com `ST_LineInterpolatePoint` / `ST_LineSubstring`; nome atual desde 2.1.0 [V] | Só se houver servidor (Fase 3). GPL do PostGIS não contamina quem só se conecta ao banco [C] |
| GeoPackage (OGC) | https://github.com/opengeospatial/geopackage | licença do repo NOASSERTION [V] | spec **v1.4.0 — 2024-01-31** [V] | eixo + estacas + boletins georreferenciados num arquivo único; troca com QGIS/QField | **Adotar** como formato de troca (item 6 do BACKLOG) |
| GDAL / pyogrio | https://github.com/OSGeo/gdal · PyPI `pyogrio` | GDAL: descrição do repo "open source MIT licensed" (spdx NOASSERTION) [V]; pyogrio MIT [V] | GDAL v3.13.3 — 2026-08-18; pyogrio 0.13.0 — 2026-06-26 [V] | ler/escrever GPKG pelo Python | Adotar quando a persistência GPKG entrar; preferir pyogrio a fiona (fiona 1.10.1 é de 2024-09) [V] |
| Shapely / pyproj / geopandas | PyPI | Shapely BSD-3 2.2.0 (2026-10-07); pyproj MIT 3.8.0 (2026-09-05); geopandas BSD-3 1.2.0 (2026-09-28) [V] | ativos | `LineString.project/interpolate` = equivalente local do PostGIS | Shapely+pyproj já recomendados (R01); geopandas opcional |
| SIRGAS 2000 / UTM | https://epsg.io/31983 | — | — | EPSG:31983 = SIRGAS 2000 / UTM 23S, Brasil entre 48°W e 42°W [V]; demais fusos: 31982/31984/31985 [C] | Guardar o EPSG por obra no manifesto do projeto |
| Estaca de 20 m e notação | https://edisciplinas.usp.br/pluginfile.php/5332178/mod_resource/content/0/LEB0340_APOSTILA_TEORICA_10_ALTIMETRIA.pdf | material didático [B] | — | "espaçamento mais comum de 20 m"; ponto intermediário "2 + 11,23 m" [B] | Convenção [B]; **nenhuma norma DNIT encontrada** que a fixe — confirmar no manual de projeto geométrico do cliente |
| Equação de estacas no IFC 4.3 | https://ifc43-docs.standards.buildingsmart.org/IFC/RELEASE/IFC4x3/HTML/lexical/Pset_Stationing.htm · .../IfcReferent.htm | doc oficial (build "under development") [B] | — | `IfcReferent` (STATION) com `Pset_Stationing.Station`; **`IncomingStation` só existe para equação de estacas**; `HasIncreasingStation` para estaqueamento decrescente; `DistanceAlong` geométrico é independente do estaqueamento [B] | Modelar estaca como dado próprio, não derivado de km |

**Implicações para o código atual:** `dados_sinteticos.py` grava `estaca_ini = round(km * 50)` — perde a parte "+ m" e
pressupõe estaqueamento contínuo desde o km 0. Recomenda-se um tipo `Estaca(numero, mais_m)` e uma função de conversão
que receba a tabela de equações de estacas (vinda do IfcAlignment ou digitada). Risco [C, não verificado nesta rodada]:
comprimento medido em coordenadas UTM difere do comprimento no terreno pelo fator de escala (k₀ = 0,9996 no meridiano
central) — em 50 km pode passar de 10 m; projetos às vezes usam sistema topográfico local. O teste deve declarar qual
comprimento é a "verdade" (o do projeto).

## 7. Agentes de IA em planejamento/fiscalização (oportunidade futura)

| Item | URL | Licença/acesso | Manutenção | Uso possível | Recomendação |
|---|---|---|---|---|---|
| ifcopenshell-mcp (`src/ifcmcp`) | https://github.com/IfcOpenShell/IfcOpenShell/tree/v0.9.0/src/ifcmcp · PyPI `ifcopenshell-mcp` | **LGPL-3.0-or-later** (classificador PyPI) [V] | 0.9.0 — 2026-09-29 [V]; README declara ter sido gerado com ajuda de ferramenta de IA [V] | perguntar ao modelo IFC em linguagem natural (via ifcquery/ifcedit) | Futuro; só leitura |
| project-mcp | https://github.com/jeffmodeler/project-mcp | **MIT** (LICENSE) [V] | 2026 [V]; atividade [NV] | expor XER/PMXML/MS Project a um cliente LLM, local | Futuro; ideia: expor **nossa** API determinística do mesmo jeito |
| MCP4IFC (pesquisa) | https://arxiv.org/abs/2511.05533 | artigo aberto [V] | v1 2025-10-29 [V] | LLM manipula IFC via MCP + Bonsai (GPL) | Só leitura acadêmica; abstract não discute limitações [V] |
| ConstructAI | https://github.com/bilalgit/ConstructAI | [NV] | [NV] | análise de XER por assistente | Não avaliado |
| Constructa (arXiv 2502.12066) | https://arxiv.org/html/2502.12066v1 | [B] | 2025 | LLM gerando cronograma de obra | Leitura |

Riscos (para qualquer ADR futuro): resposta não determinística e alucinação de datas (conflita com "mesmo input → mesmas
datas" do ADR-0003); vazamento de dado de cliente para provedor; licença GPL do Bonsai em soluções baseadas em Blender.
Uso aceitável: o agente **chama** a API do motor e cita a saída — nunca calcula data. Exigiria virar
`componente_llm: true`, com evals.

---

## Experimentos recomendados (priorizados)

| # | Experimento | Critério de aceite testável | Prioridade |
|---|---|---|---|
| E1 | **Cruzamento analítico** no `conflitos_balanco`: interseção exata das retas km×t, além da amostragem diária | Par sintético com cruzamento conhecido em t*=10,5 d e km*=3,2: detector reporta t* e km* com erro ≤ tolerância declarada em `project.yaml` (`limites`); par paralelo com distância > buffer → 0 alertas; teste visto falhando antes da correção | Alta (Fase 1) |
| E2 | **Earned Schedule** sobre a linha de base e o avanço ponderado já existentes | SPI(t)=1 quando avanço real = planejado → IEAC(t)=PD; caso com ES/AT=0,8 → IEAC(t)=PD/0,8; resultado bate com `pmcontrols` (oráculo externo, fora da suíte) no mesmo caso | Alta (Fase 1) |
| E3 | **Risk driver comum** no Monte Carlo (ex.: "chuva" aplicado a terraplenagem e lastro na mesma iteração) | Com semente fixa: (P80−P50) com driver ≥ (P80−P50) sem driver; driver com multiplicador 1,0 reproduz exatamente a distribuição atual; P80 ≥ P50 ≥ determinístico mantido | Média |
| E4 | **IFC oficial no importador** (Fase 2, item 9): `Infra-Rail.ifc`/`Infra-Road.ifc` (CC BY) + `segmented-reference-curve.ifc` (spec models), baixados no teste, fora do Git | `ifcopenshell.validate --rules --json` sem erro nos três; importador lista IfcAlignment do spec model com estações de início/fim iguais às do README do exemplo; nos `Infra-*` reporta "sem alinhamento" explicitamente (não inventa eixo); hash SHA-256 de cada arquivo registrado | Média (Fase 2) |
| E5 | **Conversão km↔estaca com equação de estacas** | `Estaca(125, 10.00)` ↔ 2.510,00 m sem equação; com equação em 2.000 m (incoming 1.990 m) a ida e volta é identidade em 1.000 pontos; tolerância lida do manifesto | Média |
| E6 | **Boletim estendido (esquema, sem dado real)**: `km_ini_exec, km_fim_exec, horas_chuva, estado, fotos[]` nos dados fictícios | Validação rejeita boletim `aprovado_siac` sem `ref_memoria_calculo`; linha real do diagrama tempo-km sai dos `km_*_exec`; Monte Carlo usa só `estado ≥ conferido_fiscal` (configurável) | Média |
| E7 | **Mapa 5D de brinquedo**: 3 classes IFC (EarthworksFill, Course-lastro, Pavement) → códigos SICRO com preços **fictícios** | Unidade divergente gera erro; custo = Σ(qto × fator × preço) bate com cálculo manual; nenhum arquivo SICRO entra no Git | Baixa (oportunidade) |
| E8 | **Validador self-host** (Docker) só se o cliente exigir laudo idêntico ao da buildingSMART | mesmo arquivo público dá o mesmo resultado no online e no local | Baixa |

## Correções/atualizações para o BACKLOG (texto pronto para colar)

```markdown
<!-- Fase 1 -->
| 4 | ~~Linha de balanço (tempo × km)~~ **feito na v0.2.0**; detector de conflitos com buffer km/dias existe em `recursos.py` | RSM (Harris & Ioannou 1998) e LBMS — R05 §3 | próximo: cruzamento **analítico** (t*, km*) em vez de amostragem diária; linha **real** a partir de `km_ini_exec/km_fim_exec` do boletim |
| 5b | **Earned Schedule** (SPI(t), IEAC(t), IECD) como 3ª previsão independente | fórmulas de Lipke confirmadas (R05 §4); não existe no código | SPI(t)=1 ⇒ IEAC(t)=PD; caso 0,8 confere com cálculo manual e com `pmcontrols` como oráculo externo |
| 5c | Monte Carlo com **risk drivers** (AACE 57R-09, visto em fonte secundária) | faixa atual é estreita demais (docstring de `montecarlo.py`) | driver neutro (1,0) reproduz a distribuição atual; driver ativo alarga P80−P50 |
| 6 | Persistência: SQLite/**GeoPackage 1.4 (OGC)** via pyogrio (MIT) — preferir a fiona (último release 2024-09) | R05 §6 | cenário salvo reabre idêntico |
| 6b | Tipo `Estaca(numero, mais_m)` + **equações de estacas** (IFC 4.3 `Pset_Stationing.IncomingStation`); hoje `estaca = round(km*50)` | 20 m é convenção (fonte didática), não norma DNIT achada | ida e volta km↔estaca é identidade com e sem equação |

<!-- Fase 2 -->
| 9 | IFC 4.3 com IfcOpenShell → GLB por trecho + vínculo GlobalId ↔ atividade | Arquivos de teste: `buildingSMART/Certification-datasets` (CC BY 4.0; Infra-Rail/Infra-Road IFC4X3_ADD2, **sem IfcAlignment**) e `buildingSMART/IFC4.x-specification-models` (IfcAlignment, IfcLinearPlacement, IfcTask; "all rights reserved até release" → baixar no teste, **fora do Git**). Validar antes com `python -m ifcopenshell.validate --rules --json` |
| 9b | Requisitos de informação com **IDS/IfcTester** (LGPL-3.0+, deps pesadas) | ex.: todo IfcCourse com Qto e código de composição; só bancada/CI |

<!-- Fase 3 -->
| 13 | Ingestão de medições reais | Modelo do boletim segue a IN 57/DNIT/2021 (diário, avanço físico, **pluviometria**, aprovação do fiscal); SIAC não tem API pública conhecida → integrar por arquivo. Mesmo bloqueio de dado real |
| 14 | Coleta em campo: **ODK Central (Apache-2.0, REST + OData + anexos)** com XLSForm via pyxform (BSD-2); QField (GPL-2.0) só externo; KoboToolbox servidor é AGPL-3.0 e `kobocat` foi arquivado | licenças GPL/AGPL só como serviço externo |

<!-- Oportunidades 5D -->
- SICRO: arquivos `.7z` por UF/mês (jul/2026 é a data-base mais recente vista); portal gov.br/DNIT sob **CC BY-ND 3.0** → importador lê o arquivo que o usuário baixa; **não redistribuir** base nem tabela derivada sem parecer jurídico.
- Mapeamento por `IfcClassificationReference` (código SICRO) + `Qto_*BaseQuantities` oficiais (ex.: aterro usa `CompactedVolume`; transporte usa `LooseVolume` × DMT).
- SINAPI: termos de uso **não verificados** (site da CAIXA não abriu pela ferramenta).

<!-- Oportunidades IA (não é beta; exige ADR e evals) -->
- `ifcopenshell-mcp` (LGPL-3.0+) e `project-mcp` (MIT) mostram o padrão: o agente consulta ferramentas determinísticas. Para nós: expor a API do motor como ferramenta, o modelo nunca calcula datas.

<!-- Riscos -->
| RK6 | Arquivo de exemplo sem licença clara entrar no Git (spec models "all rights reserved", Community sem licença, DSLIB sem termos) | baixar no teste, registrar URL + SHA-256, nunca versionar |
| RK7 | Upload de modelo de cliente no validador online da buildingSMART (privacidade não descrita) | só arquivos públicos online; cliente → validador local |
```

## Itens não verificados nesta rodada

Vigência atual da IN 57/2021, IS 01/2014 e IS 20/2019; existência de API do SIAC/SUPRA; termos do SINAPI e do servidor
humanitário do KoboToolbox; texto integral do AACE 57R-09 e do PMI; licença dos dados DSLIB; versão atual do PostGIS;
licença de ConstructAI; atividade recente de `project-mcp` (API do GitHub em limite de requisições no fim da rodada);
fator de escala UTM × comprimento de projeto (marcado [C]).

## Fontes consultadas (principais)

- https://github.com/buildingSMART/Certification-datasets (LICENSE, README, árvore) · https://github.com/buildingSMART/IFC4.x-specification-models (README, validate.sh, árvore) · https://github.com/buildingsmart-community/Community-Sample-Test-Files · https://github.com/bSI-RailwayRoom/IFC-Rail-Unit-Test-Reference-Code · https://github.com/buildingSMART/validate · https://buildingsmart.github.io/validate/user/index.html · https://github.com/buildingSMART/ifc-gherkin-rules · https://github.com/buildingSMART/IDS · https://github.com/buildingSMART/IFC4.x-development · https://pypi.org/project/ifctester/ · https://pypi.org/project/ifcopenshell/
- https://www.gov.br/dnit/pt-br/central-de-conteudos/atos-normativos/tipo/instrucao-normativa/2021/in-57-2021-direx-ba-176-de-16-09-2021.pdf · https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm · https://docs.getodk.org/central-api/ · https://github.com/XLSForm/pyxform · https://github.com/kobotoolbox/kpi · https://github.com/kobotoolbox/kobocat · https://support.kobotoolbox.org/account_usage_limits.html
- https://structurae.net/fr/litterature/article-de-revue/scheduling-projects-with-repeating-activities · https://iglc.net/papers/Details/785 · https://wensimehrp.github.io/Paiagram/nightly/docs/index.pdf · https://medium.com/nightingale/graphing-construction-on-tram-line-6-in-budapest-24e3f660295d
- https://www.earnedschedule.com/Docs/Forecasting%20Schedule%20Variance%20Using%20Earned%20Schedule.pdf · https://www.gao.gov/products/gao-16-89g · https://www.projectmanagement.ugent.be/research/data · https://pypi.org/project/pmcontrols/ · https://pypi.org/project/trueppm-scheduler/ · https://pypi.org/project/simpm/
- https://www.gov.br/dnit/pt-br/assuntos/planejamento-e-pesquisa/custos-referenciais/sistemas-de-custos/sicro/relatorios/relatorios-sicro (e subpáginas sudeste / são-paulo / 2026 / julho)
- https://postgis.net/docs/ST_LineLocatePoint.html · https://github.com/opengeospatial/geopackage · https://epsg.io/31983 · https://pypi.org/project/pyogrio/
- https://pypi.org/project/ifcopenshell-mcp/ · https://github.com/jeffmodeler/project-mcp · https://arxiv.org/abs/2511.05533
