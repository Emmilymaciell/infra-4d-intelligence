# Matriz de retornos reais

Incremento posterior de 14/11: FreeCAD 1.1.4 portátil, sem instalação global.
`output/releases/freecad-parametrico-20261114/nativo-verificado/` contém FCStd r0/r1,
STEP e prova oficial. Três IDs nativos verificados e 108 IDs conservados na
publicação JSON; não são 108 objetos CAD. Tabuleiro 1 → 1,25 m, STEP reimportado
com três sólidos, quantidades e prazo da referência preservados. Procedimento e
limites: `FREECAD-PARAMETRICO.md`; resultados completos recentes no topo do STATE.

Atualização de 14/11/2026: a federação web foi executada com os arquivos reais.
Chrome 157.0.8103.52: 214 PASS/0 FAIL (QGIS); Edge 157.0.4341.46: 220 PASS/0 FAIL
(Blender, malha e GLB). Resultados copiados para `09-evidencias/chrome-214-pass/`
e `09-evidencias/edge-validado/`. Renderização headless por software; não é GUI
nativa manual nem prova com GPU real. A regressão completa está registrada no STATE.

Data: 13/11/2026. Pacote: `output/releases/demo-ferrovia-vNext/` (ignorado pelo Git). Todas as entradas são fictícias.

| Aplicativo | Arquivos e prova | Operação observada | Resultado | Limite |
|---|---|---|---|---|
| QGIS 3.40.14-Bratislava | `01-gis-qgis/nativo-02/ferrovia-r0.qgz`, `ferrovia-r1.qgz`, respectivos GPKG; `prova-qgis.json`, `revisao-qgis.geojson` | API oficial criou GPKG/QGZ, editou L3-S04-TER, salvou, limpou projeto e reabriu do disco | 108 IDs; EPSG:4326; quantidade 350.000 → 385.000 m³. Retorno isolado mudou CPM de 09/09 para 21/09/2027 | GUI não observada; referência espacial fictícia; não é medição de obra |
| Blender 5.2.3 LTS — prova inicial | `04-visual-blender/nativo/ferrovia-r0.blend`, `ferrovia-r1.blend`, `ferrovia-r1.glb`, `prova-blender.json` | Aplicativo oficial em background criou, editou escala Z em 1,25, salvou e reabriu | 108 IDs; quantidade e término de 09/09/2027 preservados | Faixas ilustrativas por atividade, não peças BIM paramétricas |
| Blender 5.2.3 LTS — geometria de retorno | `04-visual-blender/nativo-malha-root/`: BLEND r0/r1, GLB, `revisao-blender.geojson` | Rodada do orquestrador exportou vértices/faces/matrix_world após reabrir o BLEND, exit 0 | Malha nativa ilustrativa para federação, com vínculo por atividade | GUI não observada; sem prova Bonsai |
| Excel COM16 | `06-quantitativos/`: planilha, `prova-excel.json`, `resumo-excel.pdf`, `resumo-excel-render-1.png`, `detalhe-excel-render-1.png` | Orquestrador abriu e editou cópia, salvou/reabriu; fórmulas saldo e SUMIFS recalcularam; ambas as folhas renderizadas e conferidas | Planilha editável real | Não comprova Calc, reingestão automática nem orçamento real |
| Bonsai | IFC gerado em `03-bim-bonsai/` | Não instalado/aberto nesta rodada | **formato gerado**, aguarda homologação no aplicativo | Não autorizado instalar Windows/extensão; IFC parser não é GUI |
| ProjectLibre | XML/XER em `05-cronograma/` | Não instalado/aberto nesta rodada | **formato gerado**, aguarda autorização e homologação | Nenhum POD nativo inventado |
| FreeCAD 1.1.4 portátil — incremento posterior | `output/releases/freecad-parametrico-20261114/nativo-verificado/` | Três Part::Box, edição de Height, salvar/fechar/reabrir FCStd; STEP exportado/reimportado; malha retornada | **edição + salvamento + retorno via runtime oficial** | Fragmento ilustrativo, sem GUI observada, projeto executivo ou IFC/Bonsai |
| LibreOffice Calc | CSV/XLSX em `06-quantitativos/` | Não instalado/aberto nesta rodada | **não validado no Calc** | Excel COM é prova de outro aplicativo |

## Evidências de reconciliação

- `08-relatorios/retorno-qgis.json`: aplicação em cópia, 108 IDs, quantidade crítica alterada e término recalculado.
- `08-relatorios/retorno-blender.json`: prova inicial da escala, quantidade preservada e checksum do dataset idêntico.
- Baseline da obra utilizada nas provas iniciais: SHA-256 canônico `6339b6d67871718281643d2b140b6b2be4e132bacc1190f8652359dd56f79dd7`. Hash representa o JSON canônico do contrato, não os bytes físicos do arquivo.
- O e2e Edge final conferiu no WebGL a espessura de 0,5 m na malha extraída do BLEND e de 0,50000000745 m no GLB, com 108 IDs e tolerância visual de 0,01 m declarada no manifesto. Isso não é tolerância de locação. Não confundir o retorno inicial de escala com a prova posterior de malha.

## Falha executada e corrigida

A primeira tentativa QGIS em `01-gis-qgis/nativo/` saiu com erro ao conferir o CRS após reabrir. OGR inferiu EPSG:4979 ao receber LineStringZ; o contrato declara somente EPSG:4326 horizontal e cota local sintética. O script foi corrigido para declarar esse CRS antes de gravar. A tentativa `nativo-02/` passou; os arquivos da falha foram preservados e não são o pacote recomendado.

Não houve observação da GUI dos aplicativos nativos: a ponte Computer Use estava indisponível na sessão. As provas acima correspondem ao runtime/API oficial, com arquivos reais salvos e reabertos. Nenhum aplicativo foi homologado por engenheiro ou com dado corporativo/obra real.
