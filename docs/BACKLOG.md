# BACKLOG — INFRA 4D INTELLIGENCE

> **PAUSADO (16/11/2026).** Não executar este backlog antes de receber e consolidar
> a revisão detalhada da titular. A lista de revisão futura, incluindo o relato de
> FCStd que abriu inicialmente sem geometria visível, está em
> `SNAPSHOT-PAUSA-2026-11-16.md` §F. Nenhuma pendência foi resolvida nesta pausa.

> Onda V3 (13–14/11/2026): consulte o topo de `docs/STATE.md`, a matriz
> `docs/requisitos/MATRIZ-PESSOA-A.md` e `docs/INTEROPERABILIDADE-VERIFICADA.md`
> para distinguir entregas comprovadas de lacunas. As fases abaixo preservam
> o histórico; P2/P3 não foram implementados. Bonsai, FreeCAD, planejador nativo,
> homologação humana e dados corporativos permanecem pendentes.

> Ordenado pelo que mais desbloqueia. "Fase" segue o roteiro da demonstração (docs/DEMO-PESSOA-A.md).

## Fase 1 — endurecer o beta (sem dado real)

| # | Item | Por quê | Critério de aceite |
|---|---|---|---|
| 1 | Corrigir defeitos do revisor adversarial do motor (`tests/test_revisao_adversarial_motor.py`, xfail) | o motor é o ativo central | todo xfail vira teste verde |
| 2 | Importador **MSPDI (MS Project XML)** com biblioteca padrão | primeira porta para cronograma de terceiro | ida e volta de um XML sintético preserva datas do CPM |
| 3 | Parser **XER (P6)** próprio ou PyP6Xer | xerparser é GPL-3.0; PyP6Xer é LGPL-2.1+ (R04 corrige o R02) e pode ser usado sem modificação | lê o XER sintético, compara término com P6 de referência |
| 4 | ~~Linha de balanço (tempo × km)~~ **feito na v0.2.0** | diferencial para obra linear (R02/R04) | próximo: detectar cruzamento ou aproximação de frentes e alertar |
| 5 | Monte Carlo de durações (P50/P80) sobre a produtividade medida | previsão com faixa de confiança, não uma data única | P80 ≥ P50 ≥ determinístico, reprodutível por semente |
| 6 | Persistência: SQLite/GeoPackage para medições e cenários salvos | histórico de simulações e auditoria | cenário salvo reabre idêntico |
| 7 | ~~Teste de interface automatizado~~ **feito na v0.2.0** (`tests/e2e/`, CDP sem dependência) | — | próximo: rodar também no Edge/Firefox e com GPU real |
| 7b | Alerta de produtividade ciente de **atividade reversa** | revisor r3: em atividade reversa, produzir menos antecipa o término | alerta não aponta o sentido errado |
| 8 | Nivelamento de recursos (camada separada, OR-Tools Apache-2.0) | equipes/equipamentos limitados por lote | sem sobrealocação no histograma |

### Previsão independente — achados do backtest (R12 e diagnóstico da rodovia L2, 2026-11-13)

O erro da independente no L2 da rodovia (−59 d a 10% de avanço) vem 100% de um único fator escondido: CBUQ do L2
a 0,60 (usina limitada), invisível até o 1º boletim. Prova: trocar só essa produtividade pela verdade zera o erro
em todas as datas. Nenhum método determinístico vê isso antes do boletim — é ponto honesto para a demo.

| # | Item | Critério de aceite |
|---|---|---|
| P1 | ✅ **Feito** (`GET /api/cobertura`, `cobertura.py`; `tests/test_cobertura.py`). Limite honesto (R12 §5): em 2026-03-30 nenhum sinal justo marca "baixa" no L2 da rodovia. — **Cobertura da previsão por marco:** fração do remanescente crítico com produtividade planejada/analogia × medida; previsão marcada "baixa confiança" | M-L2-FIM em 2026-03-30 sai com baixa confiança |
| P2 | Analogia pelo **recurso compartilhado** (usina), não só pelo serviço | L3 herda a produtividade do L2 após o 1º boletim |
| P3 | Gerador coerente: a restrição diz que a usina central atende L2 e L3, mas só o L2 recebe 0,60 | L3 com o mesmo fator, ou restrição corrigida (muda os números da demo) |
| P4 | ✅ **Feito, desligado por padrão** (`GET /api/previsao-probabilistica?incerteza_sem_medicao=true`; `tests/test_api_mc_sem_medicao.py`, `tests/test_montecarlo.py`). A r19 achou que a 1ª versão antecipava a previsão; corrigido (a analogia do mesmo serviço é o centro; `test_revisao_adversarial_r19.py::test_p4_nao_antecipa_a_previsao` passa) e alargamento recalibrado para 0,5. No M-L2-FIM em 03-30 a realidade ainda fica fora da faixa. — Monte Carlo com incerteza alargada para serviço sem medição | P80 do L2 em 03-30 cobre parte do deslize |
| P5 | ✅ **Feito** (`GET /api/backtest/atribuicao`, `atribuicao_erro.py` / `rotas_atribuicao.py`; `tests/test_atribuicao_erro.py`). Rodovia, M-L2-FIM em 2026-03-30: o CBUQ do L2 explica −59 → −1 dia. — Atribuição automática no backtest (trocar uma frente por vez pela verdade) | `/api/backtest` diz "o erro deste marco vem desta frente" |
| P7 | ✅ **Decidido: manter e declarar.** — Chuva futura na fotografia: os dias de chuva estão no calendário desde o início (previsão meteorológica perfeita no mundo sintético). Decidido manter e declarar | calendário climatológico (média) na fotografia, se a chuva virar fonte relevante de erro no backtest |
| P8 | ✅ **Feito** (`obra.py`, `tests/test_obra_tipo.py`, revisado pela r21). — `tipo_obra` sem padrão silencioso: hoje api, gis, exportacao, persistencia, massas, rotas_backtest, rotas_referencia, xer_exportar e ifc/exportar assumem "ferrovia" quando `meta.tipo_obra` falta | helper único; obra sem tipo = erro declarado (o orçamento já faz isso) |
| P9 | ✅ **Feito (13/11):** gabarito em `examples/synthetic/gabarito/`, acessor `sintetico_comum.gabarito`, guarda contra leitura direta (ADR-0012). Resta só a revisão de código para consumo indireto via `/api/backtest`. — Gabarito: a guarda estática e o contrafactual (r19) não pegam leitura do JSON da obra direto do disco nem consumo de `/api/backtest` por um módulo de previsão (8 evasões testadas; 6 são pegas pelo contrafactual) | regra de revisão de código registrada; avaliar isolar o gabarito em arquivo separado do dataset |
| P10 | ✅ **Feito:** orçamento `ORCAMENTO_MC` na rota (iterações × (1 + 0,5 por opção pesada) ≤ 4000; acima, 422 com o máximo que cabe; `test_api_mc_sem_medicao.py`). — Monte Carlo a 2000 iterações com todas as opções levou 22,9 s (r20) e pode passar de 30 s com a máquina carregada | teto de iterações quando criticidade, chuva, riscos e `por_marco` vêm juntos |
| P6 | Sinal antecedente fora dos boletins (produção da usina, CAP, britagem) | campo de coleta recomendado ao fiscal |

## Fase 2 — BIM real (ainda sem dado de cliente)

| # | Item | Notas |
|---|---|---|
| 9 | IFC 4.3 com IfcOpenShell (LGPL-3.0, sem modificação) → GLB por trecho + vínculo GlobalId ↔ atividade | usar IFC de exemplo públicos da buildingSMART |
| 10 | Referência linear (km/estaca) com IfcAlignment / Shapely + pyproj | precisão de estaca medida e testada |
| 11 | Avaliar web-ifc / @thatopen para modelos grandes no navegador | licenças verificadas no R04: web-ifc MPL-2.0, @thatopen/components MIT |
| 12 | CesiumJS (Apache-2.0) + 3D Tiles próprios para contexto GIS | sem Cesium ion pago |

## Fase 3 — operação (exige autorização: dado real, contas, custos)

| # | Item | Bloqueio |
|---|---|---|
| 13 | Ingestão de medições reais (diário de obra, boletins) | **dado real**: muda ADR-0004, manifesto para qa+security, dado fora do Git |
| 14 | Coleta em campo (ODK/QField) com foto georreferenciada | licenças GPL só como ferramenta externa |
| 15 | Conector Revit/Civil 3D/Navisworks (via IFC ou Speckle) | licença comercial Autodesk do cliente; estudantil proibida. Speckle Server tem módulos sob licença EE (R04); conectores v3 são Apache-2.0 |
| 16 | Publicação web multiusuário / autenticação | hospedagem e custo |

## Oportunidades futuras — BIM 5D e orçamento (não é foco do beta)

- Campo `codigo_composicao` por atividade → SINAPI/SICRO (dados públicos) → custo por quantidade.
- Curva S financeira e avanço ponderado por custo (hoje o peso é esforço planejado em equipe·dia).
- Exportação para Power BI (destino de dados) ou Apache Superset (Apache-2.0).

## Riscos

| ID | Risco | Mitigação |
|---|---|---|
| RK1 | Motor divergir de P6/Project e perder credibilidade | não alegar compatibilidade; teste de ida e volta antes; divergências documentadas |
| RK2 | Dado fictício ser confundido com real na demo | faixa permanente "DADOS FICTÍCIOS", meta.aviso, origem em cada boletim |
| RK3 | Licença copyleft entrar por dependência transitiva | matriz R01/R02/R04; checagem de licença no CI (backlog) |
| RK4 | Geometria sintética passar impressão de modelo BIM real | página de Apresentação separa implementado × simulado |
| RK5 | Pesquisa da 1ª rodada sem verificação web | R04 verifica; números de R03 marcados [OG] até ter fonte |

## Atualização da pesquisa R05 (2026-11-12)

> Colado de `docs/research/R05-pesquisa-aprofundada.md`. Onde conflita com as tabelas acima, prevalece este bloco.
> Distribuição durante a missão autônoma: E1 → agente de recursos; E2/E3 → agente de recursos (Earned Schedule e Monte Carlo v2); E5 → agente da rodovia (referência linear); E6 → agente de fiscalização.

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

## Para implantação real

> Detalhe, critérios de saída e decisões da titular em `docs/IMPLANTACAO-REAL.md`; retrato do que existe em
> `docs/ARQUITETURA.md`. Nada desta seção começa sem a decisão correspondente da titular (§9 daquele documento).

| # | Item | Fase | Critério de aceite (testável) | Bloqueio |
|---|---|---|---|---|
| IR1 | ADR que substitui o ADR-0004 (dado real: escopo, local no Drive, retenção) + manifesto `dados_sensiveis: true`, `qa+security` | 1 | ADR aceito; `/os:doctor` sem divergência; `/os:security` limpo | decisão da titular |
| IR2 | Carga de obra de pasta configurável FORA do Git (hoje só `examples/synthetic/*_ficticia.json`) | 1 | obra externa sem `meta.ficticio` → 409 em `/api/fiscalizacao/*` e 422 em `/api/orcamento/resumo` | IR1 |
| IR3 | Teste-guarda: nenhum `.json/.xer/.xml/.ifc`/imagem real entra no índice do Git fora de `examples/` e `tests/` | 1 | teste falha ao `git add` de arquivo proibido (visto falhando) | — |
| IR4 | Inventário LGPD (nomes no diário, fotos, geolocalização, login), base legal, retenção; fotos só como referência + hash | 1 | documento aprovado; nenhum campo de foto guarda bytes | jurídico / titular |
| IR5 | Ida e volta com MSPDI e XER **reais** (≥ 2 obras) contra as datas calculadas pelo P6/Project | 2 | término dentro de `verificacao.limites.divergencia_termino_dias` (a declarar); cada divergência explicada por limitação listada ou vira defeito; teste pula com motivo sem a pasta | arquivos reais |
| IR6 | Faixas de plausibilidade com fonte (SICRO lido do arquivo do usuário, DNIT, histórico) substituindo [OG] de R03/R06 como ALERTA | 3 | boletim fora da faixa gera aviso e não altera o cálculo; alerta diz [OG] quando sem fonte | — |
| IR7 | Importador de medição por arquivo (ficha de medição / Resumos A-B-C do SIAC), validado por `fiscalizacao.validar` | 4 | cada regra de recusa testada com arquivo anonimizado | IR1, IR2 |
| IR8 | Produtividade efetiva (cenários e Monte Carlo) filtra por estado do boletim (hoje não filtra) | 4 | boletim `lancado` não muda a produtividade quando a regra exige `aprovado` | decisão da regra |
| IR9 | Autenticação + autorização por papel (construtora / fiscal / gestor) + "quem" da auditoria vindo da sessão | 5 | matriz rota × papel testada (2xx/403/401); "quem" do corpo ignorado | decisão da titular |
| IR10 | Simulação por sessão (hoje uma por processo e obra, compartilhada) | 5 | duas sessões simulando ao mesmo tempo não se veem | IR9 |
| IR11 | Fechar xfail abertos das revisões r7 (frontend/XSS) e r8 (ES, MC v2, persistência) | 5 | zero xfail aberto; nova rodada adversarial de autenticação sem defeito | — |
| IR12 | Hospedagem escolhida + runbook (subir, parar, cópia, restauração) com HTTPS e limite de corpo/taxa no proxy | 6 | restauração executada e observada uma vez | decisão de custo |
| IR13 | IFC oficiais da buildingSMART (Infra-Rail/Road CC BY 4.0, modelos de alinhamento) baixados no teste, fora do Git | 7 | `ifcopenshell.validate` sem erro; importador reporta "sem alinhamento" nos Infra-*; SHA-256 registrado | — |
| IR14 | Causa raiz do travamento de suítes completas em paralelo (hoje mitigado com faulthandler e uma suíte por vez) | transversal | pilha capturada e causa corrigida, ou restrição documentada no runbook de testes | — |

## Calibração das premissas — R09 (2026-11-12)

> De `docs/research/R09-calibracao-premissas.md`. **CAL1** muda a narrativa da demo e **CAL4** exige instalar um descompactador .7z: ambos são decisões da titular.

| ID | Item | Critério | Nota |
|---|---|---|---|
| CAL1 | Alinhar TER da ferrovia ao terreno sintético (70.000 → ~54.000 m³/km) OU endurecer o terreno até ±20% — decidir comparando término e caminho crítico dos dois | `massas.coerencia` dentro de ±20% nos 12 segmentos; diferença de término registrada no CHANGELOG | muda a narrativa da demo |
| CAL2 | Declarar o MÉTODO por serviço no dataset (grade manual × mecanizada; lastro caminhão × hopper) e, se mecanizado, GRA ≈ 1,0 km/dia | campo `metodo` em `servicos` + fonte | R09 §1 |
| CAL3 | `ParametrosFrota.eficiencia` padrão 0,83 (SICRO, a confirmar na 2ª ed. do manual) e frota dimensionada pela DMT | teste: com 0,83 a produção sobe 0,83/0,70 | R09 §3 |
| CAL4 | Abrir os volumes 01 (Tabela 2: Fh por material; velocidades) e 04 (FIC por UF/mês) do Manual de Custos SICRO (.7z no gov.br) — precisa de descompactador (decisão: instalar 7-Zip ou não) | valores citados com página | R09 §3–4 |
| CAL5 | Calendário de chuva pelo FIC do SICRO (UF/mês) em vez de p sorteado; marcar "chuva sintética" na UI enquanto isso | teste: dias perdidos/mês = FIC declarado ± tolerância do manifesto | R09 §4 |
| CAL6 | Conferir na base OFICIAL do SICRO (não na réplica) as composições citadas: 5502165, 3009091, 2607206, 3009323, 4011276, 4011352, 4011464, 6416217 | tabela com código, produção e data-base | R09 §1 |
| CAL7 | Unidade de TER declarada no dataset ("corte + aterro geométricos") para não comparar com o SICRO (m³ escavado) por engano | campo/nota no JSON e no relatório | R09 §1 |
