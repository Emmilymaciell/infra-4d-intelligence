# Auditoria do progresso — INFRA 4D INTELLIGENCE

> **Data:** 2026-11-13, 10:04–10:40 (−03:00). **Base comparada:** tag `v0.2.0` (`f392900`, 12/11 18:47) × `HEAD`
> `eea379d` (13/11 07:28).
> **Regra desta auditoria:** "funciona" só quando há teste automatizado executado **nesta auditoria** ou registro de
> execução com saída no repositório. Código que existe sem teste é chamado de "código", não de "funcionalidade".
> **Todos os dados do sistema são FICTÍCIOS.** Nada aqui foi validado contra obra real, Primavera P6, MS Project,
> Bonsai, Revit ou Navisworks rodando.

Levantamentos de apoio (feitos por leitura, sem editar o repositório):
- missão original × implementado: agente `pesquisa-r05`;
- inventário das pesquisas: agente `pesquisa-verificada`.

As duas tabelas foram conferidas por amostragem contra os arquivos citados e incorporadas abaixo.

---

## 0. Resumo em 10 linhas

1. Desde a `v0.2.0` foram feitos **19 commits** (`8f1e9cc` … `eea379d`), com 195 arquivos alterados
   (+60.330 / −392 linhas), e **nenhum foi enviado ao GitHub**.
2. **Suíte automatizada reexecutada agora** (`.\tests\run-tests.ps1`): **1918 passando, 6 pulados, 0 falhas, saída 0**,
   em 16min30. Os 6 pulados são verificações da r7 que dependem do navegador; o e2e as cobre (§8).
3. **e2e da interface reexecutado agora** (Chrome headless, CSP ativo): **189 PASS, 0 FAIL, saída 0**, em 3min43.
4. O núcleo pedido na missão funciona, com teste: alterar a produtividade muda a duração, a rede, o término, o
   painel e o 3D/4D, de forma rastreável (`tests/test_vertical_slice.py` + e2e).
5. Foram acrescentadas cerca de **30 capacidades novas** (§2), todas com teste próprio, sobre dados sintéticos.
6. As integrações são **por arquivo** e testadas só contra o **próprio** sistema: MSPDI, XER, IFC 4.3, GeoJSON,
   CSV. Nenhuma foi aberta em software comercial real (§5).
7. A pesquisa citou **248 links distintos**, 75 do GitHub e **nenhum do Reddit**: o site bloqueia a ferramenta de
   busca, e isso não foi contornado (§4).
8. Tempo de trabalho comprovável pelos registros: **~4h19 efetivas** de missão, em 4 janelas, e os commits
   confirmam cada janela (§10).
9. Contra a missão original: **7 de 10 entregáveis obrigatórios operacionais**. Os 3 parciais são documentais
   (§13).
10. Para a Pessoa A, já dá para demonstrar o "por que o prazo muda" de ponta a ponta. Ainda **não** dá para
    mostrar dado real, IFC aberto num software do mercado nem uso por várias pessoas (§12).

---

## 1. Comparação com a `v0.2.0`

| | `v0.2.0` (12/11 18:47) | `HEAD` (13/11 07:28) |
|---|---|---|
| Arquivos de teste (`tests/test_*.py`) | 8 | 74 |
| Testes coletados e passando | 143 | 1918 + 6 pulados (nesta auditoria) |
| Verificações e2e da interface | 41 | 189 (nesta auditoria) |
| Arquivos Python em `scripts/` | 8 | 74 |
| Arquivos JS da interface (`web/*.js`, sem bibliotecas) | 11 | 19 |
| Obras fictícias | 1 (ferrovia) | 2 (ferrovia 60 km, rodovia 48 km) |
| Rotas da API | 11 decoradores em `api.py` | 64 caminhos, 69 operações no OpenAPI |
| Pesquisas (`docs/research`) | R01–R04 | R01–R14 + anexo |
| ADRs | 0001–0004 | 0001–0005 |

Comando para reproduzir: `git diff --shortstat v0.2.0 HEAD` → `195 files changed, 60330 insertions(+), 392
deletions(-)`.

---

## 2. Funcionalidades criadas, modificadas e corrigidas (em português simples)

A coluna **Evidência** traz o teste que comprova a funcionalidade. Todas as linhas desta tabela passaram na
suíte reexecutada (§8).

### 2.1 Previsão de prazo (o coração do produto)

| Funcionalidade | O que faz, em linguagem simples | Arquivo | Evidência |
|---|---|---|---|
| Motor CPM próprio (melhorado) | Calcula o cronograma como o Primavera: datas mais cedo e mais tarde, folga e caminho crítico. Ganhou restrição "terminar até" e o modo de lógica retida | `motor.py` | `test_motor_cpm.py` + revisões motor, r2–r4 |
| Previsão independente | Recalcula o término usando a produtividade **medida** nos boletins, não a planejada | `cenarios.py` | `test_vertical_slice.py` |
| Explicação "por que mudou" | Lista quanto cada atividade contribuiu para a mudança do término | `cenarios.py` | `test_vertical_slice.py` |
| Earned Schedule | Segundo método de previsão, pela fórmula de Lipke: compara o avanço com o tempo | `previsao_es.py` | `test_previsao_es.py` |
| Monte Carlo (v2) | Sorteia milhares de cenários de produtividade e devolve P10/P50/P80/P90 do término; tem um modo opcional com incerteza maior para frentes ainda sem medição (P4) | `montecarlo.py` | `test_montecarlo.py`, `test_api_mc_sem_medicao.py` |
| Clima | Refaz o término com mais ou menos chuva | `clima.py` | `test_clima.py` |
| Sensibilidade (tornado) | Mostra quais frentes, se piorarem 10%, mais atrasam a obra | `sensibilidade.py` | `test_sensibilidade.py` |
| Recuperação de prazo | Calcula quanto cada frente precisaria render para cumprir o prazo e se isso é realista | `recuperacao.py` | `test_recuperacao.py`, `test_recuperacao_r18.py` |
| Aceleração por custo | Escolhe onde pôr equipes extras pelo menor custo (fictício) para chegar a um prazo | `aceleracao.py` | `test_aceleracao.py` |
| Registro de riscos ao prazo | Junta 9 fontes de alerta num ranking, e cada risco aponta a evidência | `riscos_prazo.py` | `test_riscos_prazo.py` |
| Cobertura da previsão | Diz se a previsão de cada marco se apoia em medição ou em "achismo" (alta, média, baixa ou indeterminada) | `cobertura.py` | `test_cobertura.py` |
| Tendência de marcos (MTA) | Mostra como a data prevista de cada marco andou semana a semana, sem usar dado do futuro | `tendencia.py` | `test_tendencia.py` |
| Backtest | Testa a previsão contra o "futuro" que o gerador sorteou e não mostra ao motor | `backtest.py` | `test_backtest.py` |
| Atribuição do erro | Num ponto do passado, diz qual frente explica o erro da previsão | `atribuicao_erro.py` | `test_atribuicao_erro.py` |
| Comparação de revisões | Compara duas versões de cronograma e diz quanto cada mudança moveu o término | `comparar_revisoes.py` | `test_comparar_revisoes.py` |
| DCMA 14 pontos | Checklist de qualidade de cronograma usado pelo mercado | `dcma.py` | `test_dcma.py` |

### 2.2 Obra linear, BIM e GIS

| Funcionalidade | O que faz | Arquivo | Evidência |
|---|---|---|---|
| Referência linear e estacas | Converte km em estaca e trata as "equações de estaca" (saltos na numeração) | `referencia_linear.py` | `test_referencia_linear.py` |
| Linha de balanço | Gráfico tempo × km que mostra frentes se alcançando; calcula o cruzamento | `recursos.py` + `web/linhabalanco.js` | `test_recursos.py` + e2e |
| Diagrama de massas (Brückner) | Corte, aterro e transporte de terra ao longo do km, conservando o volume | `massas.py` | `test_massas.py` |
| Produtividade pela DMT | A produtividade da terraplenagem depende da distância de transporte | `produtividade_terraplenagem.py` | `test_produtividade_terraplenagem.py` |
| Recursos e nivelamento | Histograma de equipes e nivelamento quando faltam equipes | `recursos.py` | `test_recursos.py` |
| IFC 4.3 (exportação) | Gera o arquivo BIM aberto (padrão buildingSMART) da obra fictícia, com alinhamento, peças posicionadas ao longo do eixo, estacas, quantidades e o **cronograma dentro do arquivo** | `ifc/*.py` | `test_ifc.py`, `test_ifc_cronograma.py` (validação EXPRESS: 0 erros) |
| GLB para o 3D | Converte o IFC em modelo 3D que o navegador abre | `ifc/importar.py` | `test_ifc.py::test_glb_nativo` |
| GeoJSON (QGIS) | Exporta as camadas da obra para um GIS, com georreferência **fictícia** declarada | `gis.py` | `test_gis.py` |

### 2.3 Fiscalização, medições e custo (5D) fictícios

| Funcionalidade | O que faz | Arquivo | Evidência |
|---|---|---|---|
| Diário e fiscalização | Diário de obra no modelo da IN 57/DNIT, conciliação construtora × fiscal | `fiscalizacao.py` | `test_fiscalizacao.py` |
| Importação de medições (CSV) | Lê boletins de uma planilha CSV e recalcula a previsão, só em memória | `importar_medicoes.py` | `test_importar_medicoes.py` |
| Orçamento 5D | Custo fictício por atividade, BDI pela fórmula do TCU, reajuste, valor agregado (EVM) e curva S financeira | `orcamento.py`, `curva_s.py` | `test_orcamento.py`, `test_curva_s.py` |
| Histórico (SQLite) | Salva cenários e fotografias para reabrir depois | `persistencia.py` | `test_persistencia.py` |
| Exportação para BI | Tabelas CSV prontas para Power BI e similares | `exportacao.py` | `test_exportacao.py` |
| Adaptador Obrasgov.br | Converte o JSON da API pública do governo para o esquema do sistema, **sem rede** | `adaptador_obrasgov.py` | `test_adaptador_obrasgov.py` |

### 2.4 Correções relevantes (achadas por revisão e corrigidas com teste)

| O que estava errado | Como foi achado | Teste de regressão |
|---|---|---|
| A recuperação dizia "inviável por 1 dia" na ferrovia, e era falso | a aceleração por custo cumpria o prazo | `test_recuperacao.py` |
| A tendência de marcos e o backtest usavam dado futuro das restrições | pesquisa R12 | `test_tendencia.py` |
| Obra real aceitava medição que se declarava fictícia em grafia diferente | revisão r14 | `test_revisao_adversarial_r14.py` |
| Peças IFC a centenas de metros do lugar | revisão r15 | `test_revisao_adversarial_r15.py` |
| BDI de 25%, acima da faixa do TCU | pesquisa R11 | `test_orcamento.py` |
| O Monte Carlo novo antecipava a previsão em vez de alargar a faixa | revisão r19 | `test_revisao_adversarial_r19.py` |
| 500 com entradas extremas (NaN, corpo binário) | varredura r20 | `test_revisao_adversarial_r20.py` |
| Vários módulos assumiam "ferrovia" quando a obra não declarava o tipo | backlog P8 + revisão r21 | `test_obra_tipo.py`, r21 |

A revisão adversarial (um agente que só procura defeito) fez **18 rodadas nesta missão** (r4–r21), além das 3
anteriores à `v0.2.0`. Hoje há **0 defeitos marcados como abertos** em `tests/test_revisao_adversarial_*.py`.

---

## 3. Classificação: o que está pronto e o que não está

**Totalmente operacional** = código + teste automatizado que passou nesta auditoria. Sempre sobre dado sintético.

- Vertical slice: produtividade → CPM → término → painel → 3D/4D.
- Motor CPM, os 4 cenários e a explicação da mudança.
- Earned Schedule, Monte Carlo, sensibilidade, clima, recuperação, aceleração, riscos, cobertura, tendência,
  backtest, atribuição do erro.
- Comparação de revisões e DCMA.
- Referência linear, linha de balanço, massas, DMT, recursos.
- Importação e exportação MSPDI e XER, exportação IFC 4.3 com cronograma, GLB, GeoJSON, CSV para BI, CSV de
  medições, SQLite.
- Relatório técnico imprimível e API documentada (OpenAPI, com teste de contrato com a interface).
- Interface com 10 abas, verificada pelo e2e (§7, §8).

**Parcial** (existe, mas falta uma parte nomeada):
- Filtros da interface: há lote, disciplina, serviço e "só crítico"; **faltam segmento/km e período**.
- Linha do tempo 4D: o controle deslizante tem teste; o **botão de reproduzir (play) não tem**.
- Seleção bidirecional: 3D ↔ Gantt ↔ tabela ↔ linha de balanço testada; **a partir do painel, não**.
- Fiscalização: diário e conciliação existem; **não conformidade não é uma entidade própria** e fotos ficam só
  como referência + hash.

**Experimental** (funciona e tem teste, mas só faz sentido com validação externa que ainda não houve):
- Leitura de cronograma IFC de terceiros (`POST /api/ifc/cronograma`): testada com arquivos gerados pelo próprio
  sistema e com variações sintéticas, não com IFC de outro software.
- Adaptador Obrasgov: testado com fixture fictícia, nunca contra a API real (é de mão única, sem rede).
- Backtest e cobertura: medem o método contra um "mundo" inventado pelo gerador, com fatores estacionários; um
  bom resultado aqui é necessário, mas não prova o método em obra real (R12).
- Orçamento 5D: BDI e reajuste com componentes e índice **fictícios**.

**Apenas planejado** (só em documento ou backlog): analogia pela usina compartilhada (P2), coerência do gerador
(P3), sinal antecedente da usina (P6), gabarito em arquivo separado (P9), banco espacial (PostGIS/GeoPackage),
leitura de IFC de cliente, conectores Revit/Civil 3D/Navisworks/AutoCAD/OpenRail/n8n, coleta de campo
(ODK/QField), calibração CAL1–CAL7, multiusuário, login e dado real (`docs/BACKLOG.md`, `docs/IMPLANTACAO-REAL.md`).

**Ausente:** arquivo `INFRA4D_CLAUDE_KICKOFF.md` citado pela missão como leitura obrigatória (não existe no
repositório); capturas de tela versionadas da demo; AMV (aparelho de mudança de via).

---

## 4. Pesquisas realizadas e fontes

Arquivos: `docs/research/R01` … `R14` (+ `R13-anexo-issue-ifcopenshell.md`). Contagem por expressão regular sobre
o texto, com margem de ±2 links por arquivo:

| Origem | Links |
|---|---|
| GitHub (repositórios, licenças, código-fonte) | 75 |
| **Reddit** | **0** |
| Oficial brasileiro (DNIT, TCU, INMET, gov.br) | 54 |
| Oficial de normas e fabricantes (buildingSMART, Deltek, Autodesk, Bentley, Trimble, Oracle) | 72 |
| Acadêmico/técnico (artigos, teses, earnedschedule.com) | 27 |
| Comunidade/fórum (OSArch, Planning Planet) | 8 |
| Registros de pacotes (PyPI etc.) | 21 |
| Outros | 22 |
| **Distintos no total** | **248** |

**Reddit:** nenhum link. O R04 (linha 48) registra que o Reddit bloqueia a ferramenta de busca e que nenhuma
thread pôde ser aberta. O bloqueio **não foi contornado**, por regra de segurança. O conteúdo de comunidade veio
de OSArch, Planning Planet e fóruns de fabricante.

**Melhores descobertas e a decisão que geraram** (marca: [V]/[A] fonte aberta e lida; [B] só resumo de busca;
[NV] não verificado; [X] executado aqui):

| Descoberta | Link (como está no R##) | Marca | Decisão no código |
|---|---|---|---|
| three.js é MIT; xeokit é AGPL | `github.com/mrdoob/three.js`, `github.com/xeokit/xeokit-sdk` (R04) | verificado | 3D em three.js (`web/viewer3d.js`) |
| MPXJ é LGPL e xerparser é GPL-3.0 | `github.com/joniles/mpxj`, `github.com/jjCode01/xerparser` (R04) | verificado | Leitores MSPDI e XER **próprios** (`importadores/xer.py` linha 11 declara que o código GPL não foi consultado) |
| Earned Schedule (Lipke) | https://www.earnedschedule.com/Docs/Forecasting%20Schedule%20Variance%20Using%20Earned%20Schedule.pdf (R05, R12) | [B]/[A] | `previsao_es.py` |
| IN 57/DNIT 2021 (medição e fiscalização) | https://www.gov.br/dnit/pt-br/central-de-conteudos/atos-normativos/tipo/instrucao-normativa/2021/in-57-2021-direx-ba-176-de-16-09-2021.pdf (R05) | [V] | `fiscalizacao.py` |
| Validador oficial da buildingSMART roda local; os IFC oficiais não têm alinhamento | https://github.com/buildingSMART/validate (R05) | [V] | validação EXPRESS em `test_ifc.py` |
| `Pset_Stationing` do IFC 4.3 (estaca) | https://ifc43-docs.standards.buildingsmart.org/IFC/RELEASE/IFC4x3/HTML/lexical/Pset_Stationing.htm (R05) | [V] | `ifc/exportar.py` linhas 487–488 |
| Limites do DCMA 14 pontos (Deltek Acumen 8.11) | https://help.deltek.com/Product/Acumen/8.11/GA/DCMA%2014%20Point%20Assessment%20Metric%20Descriptions.html (R08) | [B] | `dcma.py` |
| A API do Obrasgov não tem cronograma nem km | https://api-publica.obrasgov.gestao.gov.br/obras/openapi.json (R10) | [V] | adaptador de mão única que declara as lacunas |
| Faixa de BDI do TCU (Acórdão 2622/2013) | texto oficial **[NV]**; faixa por resumo [B] (R11) | [NV]/[B] | BDI por obra em `orcamento.py` |
| Métricas de acurácia de previsão (MAPE, critério de Lipke) | https://discovery.ucl.ac.uk/1506210/1/Waterfield_Project%20regularity.pdf (R12) | [A] | `backtest.py` |
| Defeito no IfcOpenShell 0.9 no calendário | https://github.com/IfcOpenShell/IfcOpenShell/blob/v0.9.0/src/ifcopenshell-python/ifcopenshell/util/sequence.py (R13) | [X] | contorno em `ifc/cronograma.py`; issue **em rascunho, não enviada** |

**Pesquisado e não implementado** (21 itens, com o motivo, no levantamento): CesiumJS, Speckle, leitura de IFC de
cliente, ODK/QField, Metabase/Grafana/n8n, OR-Tools, base de projetos reais DSLIB (licença não declarada),
calibração CAL1–CAL7, chuva do INMET/SICRO, busca do Obrasgov na rede, teste no Bonsai, SYNCHRO/Navisworks.

---

## 5. Integrações: o que existe de verdade

Todas são **troca por arquivo** ou por API HTTP local. "Ida e volta" quer dizer exportar e reimportar no próprio
sistema e obter as mesmas datas. Isso **não** prova que o software comercial lê o arquivo.

| Formato | Direção | Teste | Depende de software comercial para validar? |
|---|---|---|---|
| MSPDI (XML do MS Project) | entrada e saída | ida e volta: mesmas datas, término e caminho crítico (`test_importadores_mspdi.py`) | **Sim:** abrir no MS Project ou no ProjectLibre não foi feito |
| XER (Primavera P6) | entrada e saída | ida e volta, 3 cenários × 2 obras (`test_importadores_xer.py`) | **Sim:** nunca aberto no P6; compatibilidade **não é alegada** |
| IFC 4.3 (geometria, vínculo, quantidades) | saída | validação EXPRESS sem erros; posição a ≤ 1,5e-11 m (`test_ifc.py`) | **Sim:** Bonsai, Revit e Navisworks não testados |
| IFC 4.3 (cronograma 4D nativo) | saída e entrada | reimportar e recalcular dá as datas da API (`test_ifc_cronograma.py`) | **Sim:** o Bonsai foi avaliado só pelo código-fonte (R13); SYNCHRO e Navisworks sem confirmação |
| GLB | saída | os nós do GLB batem com o vínculo (`test_ifc.py`) | Não (abre no próprio navegador do beta) |
| GeoJSON | saída | ida e volta até o km dentro de 2 mm (`test_gis.py`) | QGIS não foi aberto |
| CSV para BI | saída | tabelas = motor; injeção de fórmula neutralizada (`test_exportacao.py`) | Power BI não foi aberto |
| CSV de medições | entrada | ida e volta; tudo ou nada (`test_importar_medicoes.py`) | Não |
| SQLite (histórico) | local | cenário salvo reabre idêntico (`test_persistencia.py`) | Não |
| Obrasgov.br (JSON) | entrada, mão única | fixture fictícia, sem rede (`test_adaptador_obrasgov.py`) | Depende da API pública real, nunca chamada |

---

## 6. Agentes utilizados

Nove sessões trabalharam em paralelo, cada uma dona de arquivos próprios, com congelamento antes de cada commit. O
Git não registra o agente autor; a atribuição vem do `docs/STATE.md` e do relatório da missão.

| Agente | Responsabilidade | Resultado principal |
|---|---|---|
| orquestrador | API multi-obra, motor, integração, commits verificados | `api.py`, `cenarios.py`, `painel.py`, `relatorio.py`, guardas de teste, roteiro da demo |
| rodovia | 2ª obra e análises lineares | BR-FIC 999, geradores, GeoJSON, MTA, curva S, backtest, auditoria de caches, teste do roteiro |
| cronogramas | interoperabilidade de cronograma | MSPDI/XER, DCMA, exportação BI, comparação de revisões, OpenAPI, atribuição do erro, P8 |
| bim-ifc | IFC 4.3 | exportação, GLB, quantidades, posicionamento linear, cronograma nativo |
| recursos | recursos e previsão | Monte Carlo, ES, recuperação, aceleração, clima, riscos |
| frontend | interface | 10 abas, 3D/4D, tour guiado, e2e |
| revisor-cpm | revisão adversarial | 18 rodadas na missão (r4–r21) |
| pesquisa-r05 | pesquisa e 5D | R05, R11, R13, orçamento, documentação |
| pesquisa-verificada | pesquisa com fonte aberta | R04, R12, R14, cobertura da previsão |

---

## 7. Módulos novos, telas, gráficos e simuladores

**Módulos Python novos:** 66 arquivos novos em `scripts/infra4d/` (lista: `git diff --name-status v0.2.0 HEAD --
scripts`). Os 6 que já existiam foram modificados: `api.py`, `cenarios.py`, `dados_sinteticos.py`,
`montecarlo.py`, `motor.py` e `painel.py`.

**Telas (abas, em `web/index.html`):** Apresentação · Painel · Modelo 3D/4D · Cronograma (Gantt) · Linha de balanço ·
Recursos · Cronograma da construtora · Fiscalização · Análises · Simulação. Há ainda o botão "Relatório técnico".
Na `v0.2.0` não existiam: Recursos, Cronograma da construtora, Fiscalização e Análises.

**Gráficos e painéis:**
- **Painel** (`web/painel.js`): marcos contratuais, curva S física, produção semanal, alertas, produtividade
  planejada × efetiva, previsão probabilística (histograma, P50/P80, criticidade, incerteza alargada), cartão de
  riscos, confiança por marco.
- **Análises** (`web/analises.js`): curva S física e financeira, tornado, plano de recuperação, curva término ×
  custo da aceleração, diagrama de Brückner, DMT, clima, tendência dos marcos, backtest com "Por que errou?",
  exportação BI/GIS.
- **3D/4D** (`web/viewer3d.js`): vista esquemática e modelo IFC (GLB), pintados pelo estado 4D na data escolhida.
- **Linha de balanço** (`web/linhabalanco.js`) e **histograma de recursos** (`web/recursos.js`).

**Simuladores:** Simulação de produtividade e equipes (aba Simulação, `POST /api/simulacao`), recuperação,
aceleração, clima, Monte Carlo e comparação de revisões.

**Recursos visuais de apoio:** tour guiado (`web/tour.js`), selo "não segue a simulação" nas telas que usam o
cenário de referência, faixa "DADOS FICTÍCIOS" em todas as telas.

---

## 8. Testes reexecutados nesta auditoria

| Execução | Comando | Resultado | Duração |
|---|---|---|---|
| Suíte oficial (no disco, com rede) | `.\tests\run-tests.ps1` | **1918 passando, 6 pulados, 0 falhas, saída 0** | 16min30 (10:05–10:21) |
| Motivo dos 6 pulados | `pytest -rs tests/test_revisao_adversarial_r7.py` | 6 casos de XSS que "exigem navegador"; o e2e cobre | — |
| e2e da interface (Chrome headless, CSP ativo) | `python tests\e2e\verificar_interface.py` | **189 PASS, 0 FAIL, saída 0**; inclui "nenhuma exceção JavaScript" e "nenhum erro de console" (violação de CSP inclusa) | 3min43 (10:25–10:29) |

Comparação com os registros anteriores: o snapshot isolado do último commit de código (`41cdb42`) deu 1895
passando e 29 pulados **sem rede** (`INFRA4D_SEM_REDE=1`). Com rede, os testes que usam os arquivos IFC oficiais
da buildingSMART também rodam; por isso agora são 1918 e 6.

Limites do que os testes provam:
- tudo roda sobre as duas obras fictícias;
- o e2e roda só no Chrome headless com renderização por software, sem Edge, Firefox ou GPU real;
- nenhum teste abre arquivo em software comercial.

---

## 9. Git: branches, worktrees, commits, tags e pendências

| Item | Estado | Comando |
|---|---|---|
| Branch | só `main` | `git branch -a -vv` |
| Worktrees | só o diretório principal | `git worktree list` |
| Tags | só `v0.2.0` | `git tag -n1` |
| Remoto | `origin` = (repositório privado de origem) | `git remote -v` |
| **Envio ao GitHub** | **nada enviado**: `origin/main` parado no commit de nascimento `f9df8fc`; `main` está **20 commits à frente** (a `v0.2.0` e os 19 da missão) | `git status --branch` |
| Arquivos modificados | nenhum (árvore limpa antes deste relatório) | `git status --porcelain` |
| Stash | vazio | `git stash list` |

**Pendências de integração:**
1. **Push:** depende de autorização sua; nunca foi feito.
2. **Tag nova:** não criada. Exige declarar no `project.yaml` o critério de aceite desta fase (ADR-0006 do OS).
3. **Issue do IfcOpenShell:** rascunho em `docs/research/R13-anexo-issue-ifcopenshell.md`, não enviado; a decisão
   é sua.

**Commits desde a `v0.2.0`** (horário do autor, −03:00):

| Hora | Commit | Assunto |
|---|---|---|
| 12/11 19:17 | `8f1e9cc` | API multi-obra, rodovia fictícia, importadores MSPDI/XER e FNLT |
| 19:19 | `d70bd52` | completa equação de estacas |
| 19:22 | `652328b` | fiscalização (diário IN 57) e equações de estacas |
| 19:33 | `187e548` | recursos, ES, Monte Carlo v2, histórico e abas |
| 19:44 | `e4b9be5` | massas, 5D sintético, CSP, revisões 5 e 6 |
| 20:16 | `57118f9` | IFC 4.3, recuperação, sensibilidade, exportação BI |
| 20:19 | `247af11` | massas conserva volume; orçamento ancora EV; DMT |
| 20:23 | `d8446a3` | criticidade no MC e revisões 7–9 |
| 20:39 | `4ec4932` | DCMA, clima, IFC com quantidades, roteiro da demo |
| 20:49 | `fe9a548` | importação de medições, Obrasgov, painel mais rápido |
| 20:54 | `9577865` | segurança r7, aba Análises, modelo IFC, tour |
| 21:12 | `f73d199` | riscos, GeoJSON, XER de saída, MTA, posicionamento linear |
| 13/11 01:23 | `fdf6a26` | backtest, curva S, aceleração, r14/r15 |
| 01:46 | `e5fa630` | cronograma nativo no IFC, revisões, cobertura, BDI, OpenAPI |
| 02:15 | `682c4a0` | atribuição do erro, MC sem medição, roteiro testado, r17–r19 |
| 06:28 | `670a040` | robustez r20, interface final, documentos |
| 07:06 | `4fc3e36` | tipo de obra sem padrão silencioso (P8) |
| 07:18 | `41cdb42` | teto do Monte Carlo (P10) e relatório da missão |
| 07:28 | `eea379d` | registra o snapshot final |

---

## 10. Tempo de trabalho comprovável

**Fonte 1, horários dos commits** (objetiva, `git log`): há commits entre **12/11 19:17 e 21:12**, entre **13/11
01:23 e 02:15** e entre **13/11 06:28 e 07:28**. Não há commit fora dessas faixas.

**Fonte 2, registro no `docs/STATE.md`** (escrito durante a missão): início em 12/11 **18:59:37**; paradas por
limite de uso da conta em 19:55–20:11, 21:14–01:10 e 02:17–06:10.

| Janela | Início | Fim | Efetivo | Confirmação por commit |
|---|---|---|---|---|
| 1 | 12/11 18:59 | 19:55 | 56 min | commits 19:17–19:44 |
| 2 | 20:11 | 21:14 | 63 min | commits 20:16–21:12 |
| 3 | 13/11 01:11 | 02:17 | 66 min | commits 01:23–02:15 |
| 4 | 06:11 | 07:25 | 74 min | commits 06:28–07:28 |
| **Total** | | | **~4h19** | |

**O que não dá para comprovar:** quanto trabalho cada agente fez dentro de cada janela, porque o Git não guarda
autoria por agente. Os inícios e fins de janela vêm do STATE, não do Git. A meta era ~5 h, e não foi
atingida por causa dos limites de uso.

Esta auditoria é trabalho adicional: começou em 13/11 10:04.

---

## 11. Como abrir e usar o beta

Pré-requisitos: Windows, Python 3.13 e, para o e2e, Google Chrome.

```powershell
cd C:\caminho\exemplo\infra-4d-intelligence
.\bootstrap.ps1          # só na primeira vez: cria o .venv e instala as dependências
.\run-beta.ps1           # sobe o servidor; deixe esta janela aberta (Ctrl+C encerra)
```

- Interface: **http://127.0.0.1:8765/**, só nesta máquina, sem login.
- API documentada (para testar rotas pelo navegador): **http://127.0.0.1:8765/docs**.
- Trocar de obra: seletor no topo (ferrovia ou rodovia).
- Porta alternativa: `.\run-beta.ps1 -Porta 8800`.
- Testes: `.\tests\run-tests.ps1` (saída 0 = passou, 1 = falhou, 2 = não rodou).
- Números da demo: `cd scripts; ..\.venv\Scripts\python.exe -m infra4d.numeros_demo`.

**Roteiro de uso para quem está aprendendo:**
1. Clique em **"▶ Apresentação guiada"**. Ela troca de aba sozinha e explica cada número.
2. No **Painel**, compare a previsão da construtora (23/07/2027) com a independente (09/09/2027).
3. Na aba **Modelo 3D/4D**, arraste a linha do tempo e veja as peças mudarem de cor (planejado, em execução,
   concluído). As críticas aparecem contornadas em vermelho.
4. Na aba **Simulação**, mude a produtividade da terraplenagem L3-S04 e veja o término mudar e o motivo.
5. Na aba **Análises**, abra tornado, recuperação, backtest e "Por que errou?".

---

## 12. O que já dá para mostrar à Pessoa A e o que não dá

**Pronto para demonstrar** (com o roteiro `docs/DEMO-PESSOA-A.md`, cujos 104 números são conferidos por
`test_roteiro_demo.py`):
- a diferença construtora × independente e o porquê dela, de ponta a ponta;
- a simulação ao vivo: mudar uma produtividade e ver término, painel, 3D e linha de balanço mudarem;
- os três métodos de previsão (CPM, Earned Schedule, Monte Carlo) concordando ou discordando, com explicação;
- recuperação ("cumpre só com mudança de método") e aceleração por custo;
- linha de balanço com conflitos de frentes;
- exportar IFC 4.3, MSPDI e XER e reimportar com as mesmas datas;
- "quanto a previsão errou no passado" (backtest), sempre com a ressalva de referência sintética;
- a rodovia, mostrando que o produto não é só ferroviário.

**Não está pronto para uma apresentação profissional:**
- **Nenhum dado real:** tudo é fictício e precisa ser dito logo no início.
- **Nenhum arquivo aberto em software de mercado:** não dá para dizer "abre no P6", "abre no Project", "abre no
  Revit" ou "abre no Navisworks".
- **Sem login e sem uso por várias pessoas:** roda numa máquina só.
- **Lacunas de interface:** sem filtro por segmento/km e por período; o botão play da linha do tempo não tem
  teste; não houve teste em outro navegador nem com GPU real.
- **Sem capturas de tela versionadas** como material de apoio.
- **3D esquemático:** a geometria é gerada, não vem de um projeto real.

---

## 13. Missão original × implementado

Fonte: `docs/missao/INFRA4D_PROMPT_EXECUCAO_COMPLETO.md` (interno, não publicado). Só aparece percentual onde há critério objetivo
(N de M itens do próprio documento).

| Bloco da missão | Resultado | Pendência |
|---|---|---|
| Critério mínimo de aceite do vertical slice | **atendido** (`test_vertical_slice.py` + e2e) | — |
| §12 Entregáveis obrigatórios | **7 de 10** operacionais | 12.7 matriz de pesquisa sem Reddit e com PoC só do IfcOpenShell; 12.8 só 5 ADRs; 12.10 STATE com partes velhas (corrigido nesta auditoria) |
| §7 Interface | **6 de 8** | 7.1 filtro de segmento/km e período; 7.3 play sem teste |
| §6 Motor | **7 de 7** | — |
| §4 Contratos entre módulos | **6 de 6** com teste | todos sobre dado sintético; banco espacial ausente |
| §2 Especialidades de agente | **7 de 8** | GIS sem agente dedicado |
| §3 Áreas de pesquisa | **3 de 8** inteiras, 5 parciais | AMV, grandes modelos, sensoriamento, conectores comerciais |

**Depois da auditoria (13/11, mesmo dia):** a lacuna 12.8 foi tratada com os ADR-0011 a 0015, que registram as
decisões da missão. A numeração 0006–0010 ficou reservada para não colidir com os ADRs do Project OS. O STATE foi
corrigido (12.10).

**Itens ausentes:** `INFRA4D_CLAUDE_KICKOFF.md`, que a missão manda ler, não existe no repositório e não houve
registro de pedido da localização. Também faltam banco espacial, AMV, entidade de não conformidade e capturas de
tela versionadas.

---

## 14. Evidências: onde conferir

| Assunto | Arquivo |
|---|---|
| Estado e registro da missão | `docs/STATE.md` |
| Relatório da missão (anterior a esta auditoria) | `docs/missao/RELATORIO-MISSAO-AUTONOMA.md` (interno, não publicado) |
| Retomada sem a conversa | `docs/HANDOFF.md` |
| O que existe, módulo a módulo | `docs/ARQUITETURA.md` |
| O que falta | `docs/BACKLOG.md`, `docs/IMPLANTACAO-REAL.md` |
| Histórico de mudanças | `CHANGELOG.md` → `[Não lançado]` |
| Roteiro da demo | `docs/DEMO-PESSOA-A.md` |
| Pesquisas | `docs/research/` |
| Revisões adversariais | `tests/test_revisao_adversarial_*.py` |
