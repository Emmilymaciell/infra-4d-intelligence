> **AVISO (2026-11-12):** esta primeira rodada foi escrita quase sem consulta à web. As licenças, versões e correções verificadas estão em `R04-verificacao-web.md`, seção 4, que **prevalece** sobre este arquivo em caso de divergência.

# R02 — Planejamento, CPM, Fiscalização e 5D: pesquisa de ferramentas e bibliotecas

Data: 2026-11-12 · Escopo: pesquisa (sem instalação, sem código) · Status: rascunho para decisão

## Legenda de confiabilidade

- **[V]** verificado nesta pesquisa por busca web (fonte citada).
- **[C]** conhecimento prévio do pesquisador, **não reverificado** nesta sessão — confirmar no LICENSE/README da versão exata antes de adotar.
- "Manutenção": data/versão de release **não verificada** salvo indicação [V]. Nenhuma data de release foi checada diretamente no PyPI/GitHub nesta sessão.

## Resumo executivo

1. **Interoperabilidade com MS Project/P6 é o ponto crítico.** A única biblioteca madura que lê `.mpp`, MSPDI, XER e PMXML é **MPXJ** (Java, LGPL [V]; o pacote Python `mpxj` é wrapper via JPype e **exige JVM** [V]). Há conflito de licença em metadados do PyPI (um índice mostra MulanPSL-2.0 para a 15.3.1 [V]) — **checar antes de adotar**.
2. Para XER em Python puro: **xerparser** (GPL-3.0-only segundo índice terceiro [V]) e **PyP6Xer** (GPL, versão não confirmada [V]). GPL é **risco de licença** se o produto for distribuído fechado. Alternativa: parser XER próprio (formato é texto tabulado `%T/%F/%R`, simples) e leitura de MSPDI com `xml.etree` (padrão XML documentado pela Microsoft).
3. **Motor CPM próprio continua sendo a decisão certa**: networkx (BSD [C]) serve para grafo/ordem topológica/detecção de ciclos, mas não faz CPM com calendários, lags, restrições e data de status. OR-Tools (Apache-2.0 [C]) só para nivelamento/RCPSP futuro.
4. **Linha de balanço (LoB / time-location)**: não há equivalente aberto maduro ao TILOS [C]. Recomenda-se implementar no próprio produto (plotar atividade × km × tempo com matplotlib/Plotly) — é diferencial para ferrovia/rodovia.
5. **Fiscalização em campo**: QField (GPL [C]), ODK (Apache-2.0 [C]) e KoboToolbox (AGPL no servidor [C]) servem como **coletores de dados** com foto georreferenciada; integrar por exportação CSV/GeoPackage, não por embutir código.
6. **5D é evolução futura**: SINAPI (Caixa/IBGE) e SICRO (DNIT) são dados públicos [C]; ligar `IfcElementQuantity` → código de composição via tabela de mapeamento.
7. **Integrações BI**: Power BI Desktop gratuito, publicação/compartilhamento pago [C]; Metabase (AGPL [C]), Superset (Apache-2.0 [C]), Grafana (AGPL-3.0 desde 2021 [C]). **n8n é Sustainable Use License — não é OSI** [C], evitar como dependência embarcada.

## 1. Alternativas a MS Project / Primavera P6

| Ferramenta | URL | Licença | Manutenção | Uso hipotético | Limitações | Recomendação |
|---|---|---|---|---|---|---|
| ProjectLibre | projectlibre.com / sourceforge.net/projects/projectlibre | CPAL-1.0 [C] | não verificado | Abrir/salvar `.mpp`/MSPDI para testes de ida-e-volta; conferir CPM de referência | Desktop Java; cloud é comercial; CPM simplificado | **Avaliar depois** (oráculo de teste) |
| GanttProject | ganttproject.biz / github.com/bardsoftware/ganttproject | GPL-3.0 [C] | não verificado | Importa/exporta MSPDI | CPM básico, sem P6 | Descartar como fonte; útil só para testes |
| OpenProject | openproject.org / github.com/opf/openproject | GPL-3.0 (Community) [C]; Enterprise pago | ativo [C], não verificado | Gestão de pacotes de trabalho, Gantt, BCF/BIM module | Não é motor CPM de obra; servidor Ruby | Avaliar depois (colaboração/BCF) |
| LibrePlan | libreplan.dev | AGPL-3.0 [C] | manutenção baixa [C], não verificado | Planejamento com recursos | Projeto pouco ativo | Descartar |
| Taiga | taiga.io | MPL-2.0 [C] | não verificado | Ágil/Scrum | Não é cronograma de obra | Descartar |

## 2. Bibliotecas de leitura/escrita MSPDI, .mpp, XER, PMXML

| Biblioteca | URL | Lê | Escreve | Dependências | Licença | Recomendação |
|---|---|---|---|---|---|---|
| **MPXJ** | github.com/joniles/mpxj · mpxj.org | `.mpp` (MS Project), MSPDI, MPX, XER, PMXML, P6 DB, Phoenix, Asta, GanttProject, ProjectLibre etc. [C] | MSPDI, MPX, PMXML, XER (escrita XER em versões recentes [C]), JSON, SDEF [C] | Java (JVM). Python: `pip install mpxj` + JPype [V] | **LGPL** (2.1 no repo [V]); PyPI 15.3.1 listado como MulanPSL-2.0 em libraries.io [V] — conflito a resolver; bibliotecas embutidas em `legal/` [V] | **Adotar agora como importador opcional isolado** (processo separado, JVM declarada); não acoplar ao núcleo |
| xerparser | pypi.org/project/xerparser | XER → objetos Python [V] | não (leitura) [C] | Python puro [C] | GPL-3.0-only (índice terceiro [V]) | Avaliar; risco GPL se distribuir |
| PyP6Xer | pypi.org/project/PyP6Xer | XER [V] | escrita parcial [C] | Python puro [C] | GPL (versão não confirmada [V]) | Avaliar; idem |
| MSPDI via `xml.etree`/`lxml` | schema MSPDI da Microsoft | MSPDI | MSPDI | nenhuma (stdlib) | — | **Adotar agora**: caminho zero-dependência |
| Parser XER próprio | — | XER (texto tab) | XER | nenhuma | próprio | **Adotar agora** se GPL for problema |
| `.mpp` sem Java | — | não há alternativa madura conhecida [C] | — | — | — | `.mpp` só via MPXJ ou exportar MSPDI no MS Project |

## 3. CPM, nivelamento, simulação e previsão

| Item | URL | Licença | Uso | Limitações | Recomendação |
|---|---|---|---|---|---|
| networkx | networkx.org | BSD-3 [C] | Grafo, ordem topológica, ciclos, caminho mais longo em DAG | Sem calendário, lag, restrição | **Adotar agora** (estrutura) ou dispensar se o motor tiver topo-sort próprio |
| OR-Tools (CP-SAT) | developers.google.com/optimization | Apache-2.0 [C] | RCPSP, nivelamento de recursos | Pesado; modelagem discreta | Avaliar depois |
| python-mip | github.com/coin-or/python-mip | EPL-2.0 [C] | MILP para nivelamento | Manutenção irregular [C], não verificado | Avaliar depois |
| Monte Carlo (numpy/scipy) | numpy.org / scipy.org | BSD [C] | SRA: distribuições triangular/PERT/beta por atividade, curvas P50/P80, índice de criticidade | Implementação própria | **Adotar agora** (implementação própria simples) |
| Bibliotecas SRA prontas em Python | — | — | — | Nenhuma madura identificada nesta pesquisa (não verificado) | Implementar |
| Earned Schedule / EVM | Lipke, PMI Practice Standard for EVM [C] | — | SPI(t), ES, IEAC(t) — previsão independente baseada em desempenho | Precisa linha de base com valor/peso | **Adotar agora** (fórmulas, sem lib) |
| Line of Balance / time-location | TILOS (comercial, Trimble) [C] | — | Diagrama km × tempo, folgas espaciais, conflitos de frentes | Sem alternativa aberta madura conhecida [C] | **Implementar no produto** (matplotlib/Plotly) — diferencial |

## 4. Fiscalização / gestão de obra

| Ferramenta | URL | Licença | Uso | Limitações | Recomendação |
|---|---|---|---|---|---|
| QField / QGIS | qfield.org / qgis.org | GPL-2.0+ [C] | Coleta georreferenciada offline, fotos, por estaca/km | Curva GIS; QFieldCloud tem planos pagos [C] | **Avaliar depois** (coletor de campo, troca via GeoPackage) |
| ODK (Central/Collect) | getodk.org | Apache-2.0 [C] | Formulários (diário, NC, checklist) com foto+GPS | Servidor próprio ou pago | Avaliar depois |
| KoboToolbox | kobotoolbox.org | AGPL-3.0 (servidor) [C] | Idem, baseado em ODK/XLSForm | Hospedagem humanitária gratuita com termos de uso | Avaliar depois |
| Frappe/ERPNext | frappe.io | GPL-3.0 [C] | Medição, contratos, boletins | Escopo de ERP, pesado | Descartar para MVP |
| OpenProject | ver §1 | GPL-3.0 [C] | NC como work packages | genérico | Avaliar depois |

Diário de obra, boletim de medição e RNC: recomendação é **modelo de dados próprio** (SQLite local-first) com importação de formulários XLSForm/CSV — evita acoplamento a licença copyleft.

## 5. BIM 5D (evolução futura)

- **SINAPI** (Caixa/IBGE) e **SICRO** (DNIT): bases públicas de composições e preços, publicadas mensalmente/periodicamente em planilhas [C]; termos de uso não verificados.
- Ferramentas abertas de 5D: IfcOpenShell/Bonsai (ex-BlenderBIM) tem módulo de custo (IfcCostSchedule) — LGPL-3.0 (IfcOpenShell) / GPL-3.0 (Bonsai) [C].
- Ligação proposta: `IfcElementQuantity` (comprimento, área, volume) → tabela `mapa_composicao(classe_ifc, propriedade, codigo_sinapi|sicro, unidade, fator)` → custo = quantidade × fator × preço da composição na data-base. Conferir unidade (m³ vs m³·km para transporte SICRO).
- Recomendação: **avaliar depois**; manter só o campo `codigo_composicao` no modelo de atividades agora.

## 6. Integrações

| Ferramenta | Licença | Observação | Recomendação |
|---|---|---|---|
| Power BI Desktop | Proprietária, gratuito [C] | Compartilhar/publicar exige Pro/PPU/Fabric [C] | Exportar dados (CSV/Parquet/SQLite) compatíveis — adotar agora como destino |
| n8n | Sustainable Use License [C] — **não OSI** | Uso interno permitido; restrições comerciais | Não embarcar; só uso interno opcional |
| Metabase | AGPL-3.0 (OSS) [C] | Bom para self-service | Avaliar depois |
| Apache Superset | Apache-2.0 [C] | Mais permissivo | Avaliar depois (preferido se BI aberto) |
| Grafana | AGPL-3.0 [C] | Séries temporais | Descartar para cronograma |

## Riscos de licença

| Risco | Componente | Mitigação |
|---|---|---|
| LGPL — vincular dinamicamente é aceitável; modificar exige publicar mudanças | MPXJ | Usar sem modificar, em processo/módulo separado; incluir aviso de licença |
| Conflito LGPL vs MulanPSL-2.0 no metadado PyPI | `mpxj` (Python) | Ler LICENSE da versão exata antes de adotar |
| GPL-3.0 contamina distribuição de código fechado | xerparser, PyP6Xer, QGIS/QField, GanttProject | Parser próprio; integrar por arquivo, não por import |
| AGPL — uso em rede obriga fonte | Metabase, KoboToolbox, Grafana, LibrePlan | Usar como serviço externo separado, não modificado |
| Não-OSI (Sustainable Use) | n8n | Não redistribuir |
| Dependência Java | MPXJ | Opcional, declarada no manifesto; núcleo funciona sem JVM |

## O que o motor próprio deve suportar para ser comparável a P6/Project

1. **Tipos de relação**: FS, SS, FF, SF, com **lag/lead** positivo e negativo, em dias úteis ou corridos (P6 permite calendário do lag: predecessora, sucessora, 24h ou projeto).
2. **Calendários**: por projeto, por atividade e por recurso; dias úteis, horas/dia, feriados (nacionais/municipais), exceções, turnos; calendário 7×24 para cura/concreto; **janelas climáticas** (chuva) relevantes para terraplenagem.
3. **Tipos de atividade**: tarefa, marco de início/fim, LOE (level of effort), WBS summary, hammock.
4. **Restrições**: Start On, Start No Earlier/Later Than, Finish On, Finish No Earlier/Later Than, Mandatory Start/Finish, As Late As Possible, Expected Finish; prazo do projeto (must finish by).
5. **Data de status (data date)**: trabalho remanescente nunca antes da data de status; atividades não iniciadas no passado empurradas para frente.
6. **Progresso**: datas reais de início/fim, % físico vs % duração vs % unidades, duração remanescente; **progresso fora de sequência** tratado por:
   - **Retained Logic** (padrão P6): remanescente aguarda a predecessora.
   - **Progress Override**: ignora a lógica para atividade iniciada.
   - **Actual Dates** (P6) — opção adicional.
7. **Cálculo de folga**: total float (start, finish ou menor dos dois), free float; **caminho crítico** por folga ≤ limiar ou por **longest path**; múltiplos caminhos de folga (multiple float paths).
8. **Duração orientada por quantidade** (núcleo do produto): duração remanescente = quantidade pendente ÷ produtividade efetiva (medida no período), com produtividade planejada como fallback; tipos de duração P6 (fixed duration & units, fixed units/time) para mapear.
9. **Linhas de base** múltiplas e comparação (variância de início/fim, de duração); snapshot por data de status.
10. **Recursos** (fase 2): atribuição, curvas, nivelamento por prioridade.
11. **Métricas de qualidade de cronograma**: DCMA 14 pontos (lógica faltante, lags, leads, relações SF, restrições rígidas, folga alta, folga negativa, durações longas, CPLI, BEI).
12. **Previsão independente**: Earned Schedule (SPI(t), IEAC(t)), Monte Carlo (P50/P80) e comparação com a data da construtora.
13. **Linear scheduling**: atributos de localização (km inicial/final, sentido) por atividade para diagrama tempo-distância e detecção de conflito de frentes.
14. **Interoperabilidade**: importar MSPDI e XER preservando IDs, WBS, calendários, relações e restrições; teste de ida-e-volta comparando datas do motor com as do P6/Project (tolerância declarada no `project.yaml`).
15. **Determinismo e auditoria**: mesmo input → mesmas datas; log de por que cada data foi definida (lógica, restrição ou data de status).

## Fontes verificadas nesta sessão

- [MPXJ no GitHub](https://github.com/joniles/mpxj) · [mpxj no PyPI](https://pypi.org/project/mpxj/) · [libraries.io mpxj](https://libraries.io/pypi/mpxj) · [SourceForge MPXJ](https://sourceforge.net/projects/mpxj) · [Snyk mpxj](https://snyk.io/advisor/python/mpxj)
- [xerparser no PyPI](https://pypi.org/project/xerparser/) · [ecosyste.ms xerparser](https://packages.ecosyste.ms/registries/pypi.org/packages/xerparser) · [PyP6Xer no PyPI](https://pypi.org/project/PyP6Xer/)

Todo o resto está marcado [C] e precisa ser confirmado antes de virar ADR.
