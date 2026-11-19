# Auditoria crítica UX/3D e federação — novembro de 2026

Data: 13/11/2026. Conteúdo da frente independente de auditoria, consolidado pelo
orquestrador. Escopo: leitura de implementação e testes adversariais pequenos.
O auditor não abriu navegador/aplicativo nem conferiu pessoalmente as capturas
nesta rodada. Resultados do orquestrador/visual pertencem aos seus logs próprios.
Todos os modelos e dados são fictícios.

## Base e prioridade

Baseline Claude `12219c3` + documentação `1fa6445`, preservado por snapshot local
informado pelo orquestrador; branch `codex/demo-interop-vnext`. O registro anterior
de 1982 PASS/7 SKIP e e2e 196 PASS não é uma execução desta auditoria. Prioridade:
demo funcional e legível, com visual melhor, sem alterar datasets, CPM ou números.

## Tela por tela

| Tela/fluxo | Antes observado no código | Incremento revisado | Limite e prova necessária |
|---|---|---|---|
| Modelo 3D | Corredor esquemático, exagero 40×, crítico em contorno | Análise 4D, técnico 1:1, apresentação com terreno/água/vegetação e OAE vinculada | Contexto é ilustrativo, não dimensionamento nem quantitativo; manter análise legada |
| Câmera | Mouse e atalhos lote/frente | Vista superior, OAE e corte com controles visíveis | Handler existente não basta: observar no runtime |
| Timeline | Slider, play e data de status | Modo reunião e transparência de remanescentes | Criticidade não é atraso; timeline continua da referência |
| Detalhes | Instrução sem seleção; ficha já tinha quantidade, progresso, fonte, folgas e datas | Contexto e avisos mais claros | Diferenciar agregado por atividade, elemento IFC e malha ilustrativa |
| Federação | Upload IFC validava/comparava sem publicar cena | Prévia e publicação explícita em cópia | Acervo em memória; preservar nativos; não alegar multiusuário ou persistência |
| Retorno QGIS | Sem ciclo comprovado | GeoJSON, GPKG/QGZ e retorno de quantidade separado | Linha magenta é marcador esquemático deslocado, não malha nativa |
| Retorno Blender | Malha de visualização não provava editabilidade | Malha local com matrix_world em 1:1 e GLB com validação de IDs/bbox | Escala era ignorada no primeiro incremento; exigir prova de espessura no browser |
| Baixo consumo e fallback | Teste anterior Chrome headless | Instanciamento, detalhe reduzido e seleção 2D | Benchmark em software não prova GPU real; fallback é leitura na data de status |
| Painel e relatório | Cálculo auditável e roteiro estável | Preservar números, unidades e rastreabilidade | Filtro de atividades não significa recalcular todos os KPIs por todos os filtros; 5D é opcional |

## Defeitos confirmados e detector observado

- **R22-META:** `meta=null/lista/texto` gerava `AttributeError`/HTTP 500. Três
  casos exigem 422.
- **R22-UNITS:** `meta.units` incompatível era aceita sem conflito. Um caso exige
  `ErroInterop`.

Primeiro comando:
`.venv\Scripts\python.exe -m pytest -q tests/test_revisao_adversarial_r22.py -rx`
→ **1 PASS + 4 XFAIL(strict), exit 0, 3,21 s**, no código defeituoso.

Depois das correções, com uma hipótese DEPTH adicional:
**1 PASS + 5 XPASS(strict), exit 1, 16,09 s**. Os quatro detectores confirmados
passaram após a correção; suas marcas foram retiradas. DEPTH nunca foi defeito
reproduzido: a entrada aninhada foi recusada e a marca também saiu. A execução
seguinte foi abortada; o auditor **não observou 6 PASS**. O orquestrador deve
registrar a regressão final no STATE.

## Segurança, proveniência e quantidades

O contrato passou a conferir `meta` como objeto e a proteger unidades,
georreferência, autoridade geométrica e origem. A comparação estrutural da
baseline tolera a normalização JSON `0.0 → 0`, sem aceitar booleano como número.

`quantidade_total` só altera uma cópia. Geometria ou escala não geram medição.
Data de status e evidências de referência permanecem identificadas. Campos
`evidence_level`/`source_version` enviados pelo autor são declarações da fonte,
não um selo de homologação emitido pelo servidor. API oficial em background é
evidência distinta de GUI observada ou validação por engenheiro.

## Pendências sem detector confirmado

1. Conferir envelope superior de coordenadas z, escalas e produto `matrix_world`:
   números finitos enormes podem transbordar Float32 no renderer. Hipótese não
   reproduzida nesta janela, não classificada como defeito confirmado.
2. Ampliar casos de geometria, IDs e Qto sob transformação adversa/conflitante.
   Não inferir quantidade contratual a partir de decoração.
3. CRS IFC e datum vertical continuam locais/fictícios. Escala 1:1 não comprova
   georreferenciamento de engenharia.
4. O auditor não executou Chrome/Edge/GPU real. Evidências do time devem citar
   comandos e arquivos. Não há prova em obra real, Bonsai, P6 ou Project.

## Evidências e complemento do orquestrador

Capturas, logs e saídas ficam em `output/`, fora do Git. O auditor não inventariou
o Programa nem leu o gabarito sintético. Classificar somente o nível efetivamente
comprovado: arquivo, parser, API oficial, GUI, edição/salvamento/reabertura/retorno.

O orquestrador observou duas falhas de partida fria: cena construída, sem estado
4D, sem exceções JS/console. A correção prioriza o primeiro estado 4D antes de
Monte Carlo e das análises opcionais; a rodada seguinte passou na carga inicial,
nos modos visuais e no retorno QGIS. O e2e completo e a regressão ainda estavam
em execução ao gravar este complemento; consultar resultados finais no STATE.

Complemento de 14/11: o orquestrador observou 65 PASS na regressão focada, incluindo
os seis casos r22 sem marcas. Chrome completo: 214 PASS; Edge completo: 220 PASS,
sem falhas. No Edge, malha JSON e GLB reais preservaram a espessura de 0,5 m e os
108 IDs; cabeçalho em 1366 px e preferência visual entre obras também passaram.
São resultados do orquestrador, não execuções adicionais do auditor independente.
