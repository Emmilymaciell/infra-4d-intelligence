# Matriz de rastreabilidade — demanda Pessoa A

Data: 13/11/2026. Escopo: auditoria inicial da missão `INFRA4D_CODEX_PROMPT_MASTER_V3.md`, sobre o beta existente. Todos os dados examinados são fictícios.

## Base de evidência

Esta matriz foi produzida por leitura de código, testes e documentos. O auditor não executou testes nem abriu aplicativos de engenharia nesta rodada. A existência de um teste não significa que ele foi executado agora.

O `docs/HANDOFF-CODEX.md` registra a suíte no snapshot isolado `12219c3` com **1982 passando, 7 pulados, saída 0**, e o e2e com **196 PASS, 0 FAIL**. São evidências históricas de 13/11, não certificação da árvore de trabalho desta missão. A reexecução e os resultados atuais devem ser registrados pelo orquestrador no STATE e nas matrizes de interoperabilidade.

Segundo a liberação do orquestrador, a evolução começou na branch `codex/demo-interop-vnext`, depois de proteção local em `output/protecao/pre-missao-20261113-170327/` (bundle verificado, snapshot HEAD, evidências e WIP). O auditor não repetiu a conferência desses arquivos.

Classes de evidência: **não existe**, **planejado**, **sintético verificado**, **interoperabilidade em arquivo**, **homologado em software**, **validado em obra real**. Nesta tabela, “sintético verificado” se refere ao registro histórico citado acima. Nenhuma linha significa validação em obra real. “Interoperabilidade em arquivo” não implica abertura ou editabilidade no aplicativo de destino.

Prioridades: **demo** = apresentação deste fim de semana; **retorno** = primeiro fluxo nativo → revisão → federação; **operação** = requisitos antes do uso real. Responsáveis são frentes de trabalho, não agentes permanentes nem atribuição contratual já aceita.

## Requisito → módulo → rota → prova → demo → lacuna → responsável

| ID / requisito | Implementação e rota | Prova local a reexecutar | Classe / uso na demo | Lacuna concreta / prioridade / responsável |
|---|---|---|---|---|
| A01 — IFC 4.3, classes, propriedades e quantitativos | `ifc/exportar.py`, `quantidades.py`, `requisitos.py`; `/api/ifc/exportar`, `/api/ifc/requisitos` | `test_ifc.py`: estrutura espacial, classe por serviço, Qto oficial, validação EXPRESS, requisitos e fechamento dos quantitativos | **Interoperabilidade em arquivo**; IFC sintético com `IfcRailway`, `IfcRoad`, `IfcBridge` e cronogramas | Abrir, editar, salvar, reabrir e retornar no aplicativo livre; registrar entidades/propriedades preservadas e perdas. **Retorno — BIM/IFC** |
| A02 — CRS, datum vertical, unidades, eixo, km/estaca e precisão | `gis.py`, `referencia_linear.py`, `ifc/exportar.py`; `/api/gis/geojson`, `/api/referencia/km`, `/api/referencia/ponto` | `test_gis.py`, `test_referencia_linear.py`, testes de estacas/posição em `test_ifc.py`; tolerâncias do manifesto | **Sintético verificado / arquivo**; mapa apenas ilustrativo | IFC sem `IfcMapConversion`; coordenadas locais. GeoJSON usa âncora WGS84 fictícia e plano tangente aproximado. Falta CRS métrico comum, datum vertical e transformação documentada; precisão de ida e volta não prova precisão geodésica. **Retorno — GIS/BIM** |
| A03 — Elemento ↔ atividade ↔ serviço ↔ lote ↔ trecho ↔ quantidade | GUID de elemento determinístico, `INFRA4D_Vinculo`, relações IFC; `/api/ifc/vinculo`, `POST /api/ifc/vinculos` | `test_ifc.py`: GUID estável, vínculo, conflitos, divergência de serviço/km e rateio | **Interoperabilidade em arquivo**; seleção do modelo atual | Upload retorna validação, não substitui a cena. Falta publicar revisão nativa, reconciliar IDs e mostrar mudanças sem perder vínculos. **Retorno — federação/IFC** |
| A04 — Cronograma executivo e revisões | `importadores/mspdi.py`, `xer.py`, `xer_exportar.py`, `comparar_revisoes.py`; `/api/cronograma/*`, `/api/revisoes/comparar` | `test_importadores_mspdi.py`, `test_importadores_xer.py`, `test_comparar_revisoes.py` | **Interoperabilidade em arquivo**; exportação e comparação próprias | Sem homologação em P6/Project. Primeiro comprovar planejador gratuito, documentando calendários, IDs, relações, lags, restrições e o que foi perdido. **Retorno — cronogramas** |
| A05 — Planejado, realizado, saldo e origem da medição | `painel.py`, `fiscalizacao.py`, `nao_conformidade.py`; `/api/painel`, `/api/estado4d`, `/api/fiscalizacao/*` | `test_vertical_slice.py`, `test_fiscalizacao.py`, `test_nao_conformidade.py`, `test_importar_medicoes.py` | **Sintético verificado**; quantidades e boletins inventados com fonte declarada | Fonte fiscal real, aprovação dos boletins e rastreio de revisão ainda dependem da implantação real. Hoje cenários/MC não filtram medição por estado de aprovação. **Operação — fiscalização/segurança** |
| A06 — CPM próprio, folgas, restrições e comparação | `motor.py`, `calendario.py`, `cenarios.py`, `recursos.py`; `/api/cenarios/{c}`, `/api/comparacao`, `/api/recursos/*` | `test_motor_cpm.py`, revisões adversariais, `test_vertical_slice.py`, `test_recursos.py` | **Sintético verificado**; demonstração principal preservada | Calendários em dias inteiros e outras limitações declaradas; nivelamento é camada heurística. Comparação com programa externo precisa de prova, não analogia de comportamento. **Demo/retorno — CPM** |
| A07 — Produtividade, previsão, riscos e confiança | `cenarios.py`, `montecarlo.py`, `previsao_es.py`, `cobertura.py`, `riscos_prazo.py`; `/api/previsao-probabilistica`, `/api/previsao/earned-schedule`, `/api/cobertura`, `/api/riscos` | `test_montecarlo.py`, `test_previsao_es.py`, `test_cobertura.py`, `test_riscos_prazo.py`, `test_gabarito_isolado.py` | **Sintético verificado**; previsão medida em boletins sintéticos | Backtest tem futuro sintético estacionário; chuva futura já consta no calendário. P4 é opcional/desligado por padrão; P2/P3 não podem mudar o roteiro sem decisão. **Demo/validação — previsão** |
| A08 — Filtros e seleção sincronizada | `web/estado.js`, `app.js`, `viewer3d.js`, `gantt.js`, `linhabalanco.js`; dados em `/api/projeto`, `/api/estado4d` | e2e `tests/e2e/verificar_interface.py`; `test_contrato_interface.py` | **Sintético verificado**; obra, lote, segmento, disciplina, serviço, km e período já existem | Verificar responsividade, seleção/filtros após cada alteração visual e sua semântica por tela; filtro de atividades não significa recalcular todos os indicadores por todos os filtros. **Demo — UX/QA** |
| A09 — Visualização gerencial, relatório e exportação | `web/`, `relatorio.py`, `exportacao.py`; `/`, `/api/relatorio`, `/api/exportar/*` | e2e, `test_relatorio.py`, `test_exportacao.py`, `test_api_seguranca.py` | **Sintético verificado / arquivo**; roteiro de 5 minutos disponível | Corredor esquemático, exagero 40× padrão, ficha sem seleção inicial e ausência de prova Edge/GPU real. Distinguir crítico, atrasado e selecionado. **Demo — visual/UX/produto** |
| A10 — Protocolo projetista, consórcio e fiscalização | `docs/IMPLANTACAO-REAL.md`, missão mestre e [plano de recebimento](../implantar/PLANO-PROJETISTA-CONSTRUTORA-FISCALIZACAO.md) | Revisão documental e futuro ensaio com pacote sintético; não há aceite contratual registrado | **Planejado**; explicar responsabilidades sem inventar entregas de terceiros | Formalizar pacotes, periodicidade, responsáveis, tolerâncias de aceite e tratamento de rejeições; aprovação institucional antes de dado real. **Operação — coordenação/titular** |

## Achados que restringem a evolução

1. **Upload não equivale a federação publicada.** `POST /api/ifc/vinculos` lê/verifica vínculos; `/requisitos` verifica requisitos; `/cronograma` recalcula e compara. `/api/ifc/glb` gera a geometria do projeto sintético corrente. Um retorno do aplicativo nativo precisa de uma publicação/reconciliação explícita e evidência da cena resultante.
2. **Qto geométrico e quantidade de serviço são coisas distintas.** `ifc/quantidades.py` publica o volume/comprimento da geometria esquemática e rateia separadamente a quantidade total da atividade. Decoração e alterações visuais não podem alterar automaticamente produção medida ou quantidade contratual.
3. **Escala real não prova georreferenciamento.** O GLB pode estar em metros 1:1 e ainda não ter CRS/altimetria de engenharia definidos. A transformação GIS atual é fictícia e voltada a visualização.
4. **Fonte da geometria e fonte da análise são diferentes.** O app nativo deverá guardar a geometria editável; o INFRA 4D guarda análises e vínculos aprovados. Não prometer sincronização bidirecional antes de testar o contrato.
5. **Modo público deve ser construído sobre C0.** `meta.ficticio is True` protege geradores, mas não substitui autorização de acesso/divulgação, autenticação ou isolamento. Ver [portão do Programa](../prog/PORTAO-DE-AUTORIZACAO.md).

## Reconciliação documental necessária

Os seguintes trechos são históricos ou estão desatualizados; não servem isoladamente como estado atual:

| Documento | Divergência observada | Referência mais recente a considerar |
|---|---|---|
| `STATE.md` | Cabeçalho com 20 commits à frente e 1918 testes; seção Parcial ainda diz play sem teste; ADR-0012 menciona P9 aberto | Congelamento `12219c3`, encerramento em `1fa6445`, HANDOFF-CODEX e ADR-0012 atualizado |
| `HANDOFF.md` | E2E 181/181 e P9 aberto em seções internas | HANDOFF-CODEX 196/196 e ADR-0012 com gabarito separado |
| `ARQUITETURA.md` | Base antiga e casos xfail descritos como abertos; partes atualizadas em datas diferentes | Histórico final e reexecução atual; não remover limitações sem prova |
| `AUDITORIA-2026-11-13.md` | Antes do congelamento: filtros, play, não conformidade e P9 ainda descritos como lacunas | Código em `12219c3`, CHANGELOG e HANDOFF-CODEX; preservar a auditoria como retrato daquele horário |
| `BACKLOG.md` / `IMPLANTACAO-REAL.md` | Tabelas iniciais ainda dizem ausentes recursos já entregues ou defeitos já fechados | Seções posteriores, código e testes; separar implementação de homologação externa |
| `ifc/exportar.py` | Docstring diz não haver `IfcLinearPlacement`, mas implementação e testes posteriores o incluem | `test_pecas_com_ifclinearplacement_no_eixo` e código atual; ausência de CRS permanece |

## Aceite do próximo incremento

- Preservar datasets, motor, números e roteiro congelado; evidenciar o novo visual com capturas reais.
- Reexecutar smoke, testes da demonstração e e2e conforme mudança; registrar comando, resultado e limitações, uma execução pesada por vez.
- Para cada app, anexar prova de abrir → editar → salvar → fechar → reabrir → exportar → retornar ao INFRA 4D. Guardar arquivos reais e hashes em `output/`, sem incorporá-los ao Git.
- Rejeitar ou encaminhar para revisão manual conflito de ID, unidade, CRS, vínculo ou quantitativo; nunca sobrescrever silenciosamente a fonte.
- Manter **experimental** todo recurso que não cumprir o ciclo e o teste correspondente.

Fontes: missão mestre; `AGENTS.md`; `docs/HANDOFF-CODEX.md`; `docs/ARQUITETURA.md`; auditoria de 13/11; ADR-0003/0004/0005/0012/0013/0014/0015; código e testes citados nas linhas. Esta auditoria não acessou arquivos do Programa, credenciais ou o gabarito sintético.
