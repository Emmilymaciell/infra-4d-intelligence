# R04 — Verificação web de licenças, manutenção e fontes

> Data da verificação: **2026-11-12**. Método: consulta direta à API do GitHub (`/repos/{r}`, `/releases/latest`, `/license`),
> leitura do arquivo LICENSE/COPYING bruto (raw.githubusercontent.com), metadados do PyPI (`/pypi/{p}/json`) e do npm
> (`registry.npmjs.org/{p}/latest`), mais páginas oficiais via WebFetch e buscas web.
> "Último release" = tag de `releases/latest` no GitHub (ou versão no PyPI/npm, quando indicado) com a data de publicação vista.
> "Último push" = `pushed_at` do repositório na data da consulta (indica atividade, não release).
> Nada aqui é parecer jurídico; é o que os arquivos oficiais dizem hoje.

## 1. Tabela de verificação

| Ferramenta | URL consultada | Licença verificada (fonte) | Último release visto | Diverge de R01/R02? | Nota |
|---|---|---|---|---|---|
| three.js | github.com/mrdoob/three.js · npm `three` | **MIT** (GitHub spdx; npm) | r187 — 2026-10-30 (npm 0.187.0); push 2026-11-12 | Não | Muito ativo. |
| IfcOpenShell (lib Python/C++) | github.com/IfcOpenShell/IfcOpenShell · PyPI `ifcopenshell` · `src/ifcopenshell-python/pyproject.toml` | **LGPL-3.0-or-later** (pyproject e PyPI `license_expression`; GitHub spdx LGPL-3.0) | PyPI 0.9.0.post1 — 2026-10-15; branch padrão `v0.9.0`; push 2026-11-12 | Não (R01 dizia LGPL-3.0; precisão: *or-later*) | `releases/latest` do GitHub aponta para `ifcsverchok-0.9.1.261104` (2026-11-04) — o repo publica vários produtos; usar PyPI como referência de versão da lib. |
| Bonsai (ex-BlenderBIM) | `src/bonsai/COPYING` no repo IfcOpenShell (branch v0.9.0) | **GPL-3.0** (COPYING) | tags `bonsai-0.9.1-alpha2611121823` (alphas diárias, 2026-11-12) | Não | Confirma: ferramenta de bancada, nunca embutir. |
| web-ifc (ThatOpen) | github.com/ThatOpen/engine_web-ifc · npm `web-ifc` | **MPL-2.0** (GitHub spdx; npm) | 0.79 — 2026-11-11 (npm 0.0.79) | Não (R01 "conferir" → confirmado) | Ainda versão 0.x; API instável. |
| @thatopen/components | github.com/ThatOpen/engine_components · npm | **MIT** (GitHub spdx; npm) | v3.6.0 — 2026-10-22 (npm 3.6.0); `@thatopen/fragments` 3.6.1 MIT | Não (confirmado) | Major 3.x; mudanças grandes entre majors (risco de API já citado em R01). |
| xeokit-sdk | github.com/xeokit/xeokit-sdk · xeokit.io | **AGPL-3.0** (GitHub spdx) **ou licença comercial** (xeokit.io: Creoox AG vende licença para "closed-source products and SaaS") | v2.6.114 — 2026-09-02; push 2026-11-02 | Não | Mantém DESCARTAR para produto fechado/SaaS sem licença comercial. |
| CesiumJS | github.com/CesiumGS/cesium | **Apache-2.0** (GitHub spdx) | 1.147 — 2026-11-02 | Não | Releases mensais. Cesium ion (serviço) não verificado nesta rodada. |
| Speckle Server | github.com/specklesystems/speckle-server · LICENSE | **Apache-2.0, EXCETO** `packages/server/modules/workspaces/` e `.../gatekeeper/` sob **"Speckle Enterprise Edition (EE) license"** (LICENSE; GitHub mostra NOASSERTION) | 2.31.14 — 2026-06-15 (último release formal); push 2026-11-12 | **Sim** — R01 dizia "Apache-2.0" sem ressalva | Self-host: usar sem os módulos EE ou ler a licença EE antes. Cadência de releases formais parou em jun/2026 apesar de commits diários — investigar como eles versionam hoje. |
| Speckle conectores (v3) | github.com/specklesystems/speckle-sharp-connectors | **Apache-2.0** (GitHub spdx) | 2026.9.6 — 2026-11-12 | Não, mas **repo mudou** | O repo antigo `speckle-sharp` está **arquivado** (último release 2.23.3, 2025-07-11). R01 deve apontar para `speckle-sharp-connectors`. |
| FastAPI | github.com/fastapi/fastapi · PyPI | **MIT** (spdx; PyPI) | 0.162.5 — 2026-11-11 | Não | Ainda 0.x; fixar versão. |
| uvicorn | github.com/Kludex/uvicorn · PyPI | **BSD-3-Clause** (spdx; PyPI) | 0.54.0 — 2026-09-25 | n/a (não estava em R01/R02) | Repo saiu de `encode/uvicorn` (404 na API) para `Kludex/uvicorn`. |
| Shapely | github.com/shapely/shapely · PyPI | **BSD-3-Clause** | 2.2.0 — 2026-10-07 | Não | |
| pyproj | github.com/pyproj4/pyproj · PyPI | **MIT** | 3.8.0 — 2026-09-05 | Não | Embute PROJ (MIT) nas wheels. |
| MPXJ (Java) | github.com/joniles/mpxj · LICENSE · `legal/` | **LGPL-2.1** (LICENSE do repo) | v16.11.0 — 2026-11-02 | Não | `legal/` contém licenças de dependências embutidas (jgoodies, jsoup, Apache POI, rtfparserkit, sqlite-jdbc). |
| mpxj (wrapper Python) | PyPI `mpxj` · `src.python/mpxj/setup.py` · libraries.io API | **LGPL-2.0-or-later** (PyPI e setup.py, inclusive na 15.3.1) | 16.10.0 — 2026-10-05 | **Conflito resolvido** | O "MulanPSL-2.0" vem só do campo `normalized_licenses` do **libraries.io** (erro de normalização deles); o campo `original_license` de todas as versões, inclusive 15.3.1, é `LGPL-2.0-or-later`. Não há MulanPSL no projeto. Exige JVM (JPype). |
| xerparser | github.com/jjCode01/xerparser · PyPI | **GPL-3.0-only** (PyPI; spdx GPL-3.0) | PyPI 0.13.9 — 2025-11-19 (GitHub release v0.13.7 — 2025-08-20); push 2026-05-24 | Não (agora confirmado em fonte primária) | Atividade baixa em 2026. Risco GPL mantido. |
| PyP6Xer | github.com/HassanEmam/PyP6Xer · PyPI | **LGPL-2.1-or-later** (PyPI `license_expression`; GitHub spdx LGPL-2.1) | v2.0 — 2026-10-30 | **Sim** — R02 dizia "GPL" | LGPL muda o enquadramento: usável como dependência sem modificar (mesmas regras de MPXJ). Ainda assim, parser XER próprio continua viável. |
| ProjectLibre | sourceforge.net/projects/projectlibre | **CPAL-1.0** (página SourceForge) | arquivo projectlibre-1.9.8.jar; projeto atualizado 2026-07-13 | Não | CPAL tem cláusula de atribuição e efeito de rede — só como ferramenta externa/oráculo. |
| GanttProject | github.com/bardsoftware/ganttproject | **GPL-3.0** (spdx) | ganttproject-3.3.3323 — 2024-01-22 (último release formal); push 2026-11-12 | Não | Commits ativos, mas sem release formal no GitHub há ~2 anos. |
| OpenProject | github.com/opf/openproject | **GPL-3.0** (spdx) | v17.9.7 — 2026-11-09 | Não | Muito ativo. |
| OR-Tools | github.com/google/or-tools · PyPI `ortools` | **Apache-2.0** | GitHub v9.15 — 2026-01-12; PyPI 9.15.6755 | Não | |
| QGIS | github.com/qgis/QGIS | **GPL-2.0** (spdx; "or later" conforme texto do projeto — não lido nesta rodada) | final-3_44_15 — 2026-09-25 (LTR) | Não | |
| QField | github.com/opengisch/QField | **GPL-2.0** (spdx) | v4.3.8 — 2026-11-12 | Não | QFieldCloud (serviço) não verificado. |
| ODK Central | github.com/getodk/central | **Apache-2.0** (spdx) | v2026.3.1 — 2026-09-28 | Não | |
| ODK Collect | github.com/getodk/collect · LICENSE.md | **Apache-2.0** (LICENSE.md; GitHub mostra NOASSERTION por formatação) | v2026.3.5 — 2026-09-28 | Não | |
| FreeCAD | github.com/FreeCAD/FreeCAD | **LGPL-2.1** (spdx; R01 dizia LGPL-2.0+) | 1.1.4 — 2026-09-28 | Leve (versão da LGPL) | Irrelevante para a arquitetura (ferramenta de bancada). |
| Apache Superset | github.com/apache/superset | **Apache-2.0** | 6.1.0 — 2026-05-13; push 2026-11-12 | Não | |
| n8n | github.com/n8n-io/n8n · LICENSE.md | **Sustainable Use License 1.0** + arquivos `.ee.` sob **n8n Enterprise License** (LICENSE.md; GitHub NOASSERTION) | n8n@2.47.5 — 2026-11-12 | Não (confirmado) | Texto literal: "use or modify the software only for your own internal business purposes or for non-commercial or personal use. You may distribute ... only if you do so free of charge for non-commercial purposes." → **proibido embarcar ou revender**; uso interno ok. |
| iTwin.js | github.com/iTwin/itwinjs-core | **MIT** (spdx) | release/5.15.1 — 2026-11-09 | Não | Plataforma/serviços Bentley não verificados (continuam pagos segundo R01). |

Itens não verificados nesta rodada: Cesium ion (termos/planos), QFieldCloud (planos), termos de uso do SICRO, texto completo da licença Speckle EE.

## 2. Links de comunidade (discussões reais)

Observação: o Reddit **bloqueia o agente de busca** (erro "domains not accessible to our user agent"); nenhuma thread do Reddit pôde ser aberta. Os links abaixo vêm de OSArch, Planning Planet, buildingSMART e academia.

1. https://wiki.osarch.org/ifc-industry-foundation-classes-ifc-alignment/ — wiki OSArch sobre IfcAlignment: estrutura horizontal/vertical/curva composta; afirmava suporte de geometria de alinhamento no IfcOpenShell previsto para v0.8 (a lib já está em 0.9.0 — confirmar na P3).
2. https://community.osarch.org/discussion/1565 — "How to assign IfcAlignment to an object?": foco atual é ler alinhamento semântico de arquivos existentes; usuário montou IfcAlignment com linear placement no IfcOpenShell 0.8 (C++).
3. https://webthesis.biblio.polito.it/32498/1/tesi.pdf — tese Politecnico di Torino (2024): viewer web de modelos de infraestrutura que trata IfcAlignment — referência direta para (b) IFC 4.3 alignment no navegador.
4. https://community.osarch.org/discussion/416/ — thread OSArch onde empresa iniciando 4D (comparando com Synchro) pede alternativas open source — mostra o vazio de 4D aberto (a).
5. https://www.bohrium.com/paper-details/linear-4d-system-using-schedule-location-charts-for-infrastructure-projects/817060347440529409-3774 — artigo "Linear 4D system using schedule-location charts for infrastructure projects": Gantt + 4D não dá conta de localização; propõe 4D sobre diagrama tempo-caminhamento (a, c).
6. https://planningplanet.com/comment/560 — Planning Planet, "Time/Location Diagrams": profissionais de ferrovia relatam fazer diagramas tempo-local em Excel; alternativas citadas são comerciais (TILOS, Turbo-Chart) (c).
7. https://www.prnewswire.com/news-releases/trimble-acquires-linear-project-to-expand-its-heavy-civil-construction-project-management-capabilities-300045810.html — confirma: Trimble comprou a Linear project GmbH (TILOS) em março/2015.

Conclusão (c): nenhuma busca encontrou alternativa **aberta** madura ao TILOS — sustenta a decisão de R02 de implementar o diagrama tempo-km no produto.

## 3. Fontes de engenharia (ordem de grandeza)

1. **DNIT ETS-002 — Lastreamento de linha**: https://www.gov.br/dnit/pt-br/ferrovias/instrucoes-e-procedimentos/especificacoes-tecnicas-de-materiais-e-servicos-ferroviarios-etm-ets/ets-002-lastreamento-de-linha.pdf — remete às composições SICRO de lançamento de lastro, medidas **por m³ lançado ou km de via lastrada**, por bitola; transporte do lastro é composição à parte. (Conteúdo visto via resumo de busca; PDF não aberto integralmente.)
2. **DNIT ETM-002 — Lastro padrão de brita**: https://www.gov.br/dnit/pt-br/ferrovias/instrucoes-e-procedimentos/especificacoes-tecnicas-de-materiais-e-servicos-ferroviarios-etm-ets/etm-002-lastro-padrao-de-brita.pdf — especificação do material (não aberto nesta rodada).
3. **DNIT ISF-212 — Projeto de superestrutura (lastro e sublastro)**: https://www.gov.br/dnit/pt-br/ferrovias/instrucoes-e-procedimentos/instrucoes-de-servicos-ferroviarios/isf-212-projeto-de-superestrutura-da-via-permanente-lastro-e-sublastro.pdf — espessuras de lastro/sublastro para validar quantitativos por km de R03 (não aberto nesta rodada).
4. **SICRO 3009091 (via Orçamentor, revendedor privado, base 202607-SP)**: https://orcamentor.com/sicro/composicoes/3009091/ — "Lançamento de lastro, 10 cm, primeiro levante, descarga de pedra britada de caminhões": produção da equipe **25,46 m³** (unidade de tempo não explícita na página; custos são horários → provavelmente m³/h ≈ 200 m³/dia de 8 h). Equipamentos: distribuidor de agregados rebocável + rolo tandem. **Método rodoviário/caminhão**, não trem de lastro — não comparar direto com os 1.000–3.000 m³/dia de R03 (trem hopper). Conferir na base oficial do DNIT.
5. Contexto (não aberto): ANTF/EFC, estabilização dinâmica do lastro — https://www.antf.org.br/_uploads/2021/09/AVALIAÇÃO-DO-METODO-DE-ESTABILIZAÇÃO-DINAMICA-DO-LASTRO-NA-ESTRADA-DE-FERRO-CARAJAS.pdf

Não encontrado: composição SICRO de **assentamento de grade** com produção em km/dia (as vizinhas encontradas são AMV em "un" e transporte de trilho em t/tkm). As faixas de R03 para grade (0,3–0,8 km/dia manual; 1,5–3 km/dia mecanizada) e socaria (0,5–1,5 km/dia por passada) **continuam [OG], sem fonte verificada**.

## 4. Correções necessárias em R01–R03

| Arquivo | Correção |
|---|---|
| R01 | Speckle Server: trocar "Apache-2.0" por "Apache-2.0 exceto módulos `workspaces/` e `gatekeeper/` (Speckle EE license)". |
| R01 | Speckle conectores: apontar para `github.com/specklesystems/speckle-sharp-connectors` (Apache-2.0, v3); `speckle-sharp` está arquivado desde 2025-07. |
| R01 | IfcOpenShell: precisar "LGPL-3.0-or-later"; versão atual 0.9.0.post1 (PyPI, 2026-10-15). |
| R01 | web-ifc (MPL-2.0) e @thatopen/components (MIT): remover "conferir" — confirmados. |
| R01 | FreeCAD: LGPL-2.1 (não "LGPL-2.0+"). |
| R01 | Substituir todas as células "não verificado" de manutenção pelos dados da §1. |
| R02 | MPXJ: **remover o conflito MulanPSL** — é erro de normalização do libraries.io; repo = LGPL-2.1, pacote Python = LGPL-2.0-or-later (inclusive 15.3.1). Atualizar versão: Java v16.11.0, Python 16.10.0. |
| R02 | PyP6Xer: **LGPL-2.1-or-later**, não GPL; v2.0 (2026-10-30). Mover da linha de risco GPL para a linha de LGPL. |
| R02 | xerparser: GPL-3.0-only agora verificado em fonte primária (PyPI/GitHub); última versão 0.13.9 (2025-11). |
| R02 | n8n: acrescentar que arquivos `.ee.` estão sob licença Enterprise separada; citar trecho literal da Sustainable Use License. |
| R02 | ODK: confirmado Apache-2.0 (Central e Collect). QField/QGIS GPL-2.0 confirmados. GanttProject GPL-3.0 confirmado, mas sem release formal desde 2024-01. |
| R02 | TILOS: "comercial, Trimble" confirmado (aquisição da Linear project GmbH em 2015). Trocar [C] por [V]. |
| R02 | Marcar como [V] (esta rodada): ProjectLibre CPAL-1.0, OpenProject GPL-3.0, OR-Tools Apache-2.0, Superset Apache-2.0. |
| R03 | Lastro: anotar que a única composição SICRO vista (3009091) é método com caminhão (~25 m³/h) e não valida a faixa de trem hopper; grade e socaria seguem [OG]. Adicionar ETS-002 e ISF-212 como fontes a ler. |
| — | Novo item no inventário: **uvicorn** está em `github.com/Kludex/uvicorn` (BSD-3-Clause). |

## 5. Impacto na arquitetura

- **Beta (FastAPI MIT + uvicorn BSD-3 + three.js MIT + Shapely BSD-3 + pyproj MIT + motor CPM próprio):** todas as licenças confirmadas permissivas. **Nenhuma divergência afeta o beta.**
- **Fase 2 (IfcOpenShell LGPL-3.0-or-later):** confirmado; usar o pacote oficial sem modificar, como dependência dinâmica, com aviso no inventário de terceiros. Bonsai é GPL-3.0 → só bancada.
- **Importadores de cronograma:** a situação **melhorou** — MPXJ é LGPL limpo (sem MulanPSL) e PyP6Xer é LGPL, não GPL. Só xerparser continua GPL.
- **Speckle:** atenção nova — o servidor self-host não é 100% Apache (módulos EE).
- **Sem mudança:** xeokit AGPL/comercial (descartar), n8n não-OSI (não embarcar).
