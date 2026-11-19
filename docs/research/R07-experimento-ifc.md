# R07 — Experimento IFC 4.3 com IfcOpenShell (protótipo executado)

- **Data:** 2026-11-12
- **Escopo:** fase 2 do ADR-0002. Exportar a ferrovia e a rodovia fictícias para IFC 4.3, reler, extrair o vínculo elemento ↔ atividade, gerar malha/GLB para o visualizador, expor isso numa API e testar o importador com IFC oficial da buildingSMART (experimento E4 do R05).
- **Status:** protótipo **executado e testado** (`tests/test_ifc.py`, 95 casos: a maioria parametrizada por obra e por arquivo externo). Os dados são **fictícios**.
- **Código:** `scripts/infra4d/ifc/` (`exportar.py`, `importar.py`, `quantidades.py`, `requisitos.py`, `cronograma.py`, `rotas.py`). Testes: `tests/test_ifc.py` e `tests/test_ifc_cronograma.py`.

## 1. Dependência instalada (verificado nesta máquina)

| Item | Valor observado |
|---|---|
| Pacote | `ifcopenshell` **0.9.0.post1**, wheel oficial do PyPI `ifcopenshell-0.9.0.post1-py313-none-win_amd64.whl` |
| Licença | `License-Expression: LGPL-3.0-or-later` (`pip show`). Confere com o R04. |
| Instalação | `.\.venv\Scripts\python.exe -m pip install ifcopenshell`, só no `.venv`, sem admin |
| Schemas embutidos | `IFC2X3`, `IFC4`, `IFC4X3_ADD2` |
| Dependências transitivas (licença pelo `pip show`) | numpy 2.5.4 (BSD-3-Clause e outras permissivas), shapely 2.2.0 (BSD-3-Clause), lark 1.3.1 (MIT), isodate 0.7.2 (BSD; o campo traz só o copyright), python-dateutil 4.0.0 (BSD-3-Clause), pyparsing 3.3.3 (MIT), tzdata 2026.6 (Apache-2.0), typing_extensions 4.16.0 (PSF-2.0) |
| Ausente, sem impacto | `networkx`: só `sequence.recalculate_schedule` fica indisponível. O aviso aparece no import, e o projeto não usa essa função. |

Uso conforme a LGPL: o pacote vai sem modificação, importado como biblioteca dinâmica. Precisa entrar no inventário de terceiros.

## 2. O que funcionou (executado e observado)

| Item | Resultado |
|---|---|
| Exportar para `IFC4X3_ADD2` | Ferrovia: 537 elementos (= peças do visualizador), 113 `IfcTask`, 264 `IfcRelSequence`, 1 `IfcAlignment`. Rodovia: 531 elementos, 137 `IfcTask`, 301 `IfcRelSequence`, 1 `IfcAlignment`. O exportador é genérico por `meta.tipo_obra`; tipo sem mapeamento é recusado com 422. |
| Estrutura espacial | `IfcProject → IfcSite → IfcRailway` ou `IfcRoad` `→ IfcRailwayPart` ou `IfcRoadPart` (um por lote, `LONGITUDINAL`) `→ IfcBridge → IfcBridgePart` (FOUNDATION/PIER/SUPERSTRUCTURE, `VERTICAL`) |
| Alinhamento | **Semântico**: `IfcAlignmentHorizontal` pelo método PI (`alignment.create_by_pi_method`), com 61 PIs (vértices de km inteiro), raio de 5000 m (limitado pela tangente) e representação `Axis` gerada pela lib. Fica referenciado na `IfcRailway`. Não foi preciso cair no `IfcPolyline` (o fallback existe no código). |
| Classes por serviço (comuns) | SUP `IfcEarthworksCut` TOPSOILREMOVAL · TER `IfcEarthworksFill` EMBANKMENT · DRE `IfcPipeSegment` CULVERT · OAE-FUN `IfcPile` · OAE-MES `IfcColumn` PIERSTEM · OAE-SUE `IfcBeam` GIRDER_SEGMENT |
| Classes da ferrovia | SUB `IfcCourse` USERDEFINED/SUBBALLAST · LAS `IfcCourse` BALLASTBED · DOR `IfcTrackElement` SLEEPER · GRA `IfcRail` RAIL · SOL `IfcFastener` WELD |
| Classes da rodovia | SBB e BGS `IfcCourse` PAVEMENT · IMP `IfcCourse` USERDEFINED/PRIMECOAT · CBU `IfcPavement` FLEXIBLE · SHV `IfcSurfaceFeature` LINEMARKING, aderida (`IfcRelAdheresToElement`) à peça de CBUQ do mesmo segmento e km · SVV `IfcSign` PICTORAL · DEF `IfcRailing` GUARDRAIL. Serviço sem mapeamento vira `IfcBuiltElement` com ObjectType = serviço, e LIB/SIN ficam sem peça, como no visualizador. |
| GlobalId determinístico | uuid5(obra + ElementoId), e o mesmo para as tarefas. Exportar duas vezes dá os mesmos GlobalIds (há teste), então GLB, tabela de vínculo e `.ifc` baixados em momentos diferentes casam. |
| Geometria | `IfcExtrudedAreaSolid` de perfil trapezoidal (`IfcArbitraryClosedProfileDef`) por parte, com as seções de `web/secoes.js` |
| Pset `INFRA4D_Vinculo` | `AtividadeId`, `ElementoId`, `KmInicial`, `KmFinal`, `ServicoId`, `LoteId` e, nas OAEs, `OaeId`, em todos os 537 elementos |
| 4D nativo | Cronograma **por cenário**, com calendários e ida e volta pelo motor (ver seção 7). Cada peça tem um `IfcRelAssignsToProduct` para as suas tarefas: a tarefa *produz* o elemento. |
| Validação `ifcopenshell.validate` | **0 erros** nas duas obras, inclusive com `express_rules=True` |
| Importar | Tabela de vínculo (GlobalId, classe, nome, atividade, fonte, km) com 537 de 537 casados, 0 conflitos. Cobertura das tarefas: 97,2%. As faltantes são `L1/L2/L3-SIN` (sinalização, sem peça física por decisão do visualizador). Os 5 marcos ficam listados à parte. |
| Fontes de vínculo | Pset, depois `IfcRelAssignsToProduct`, depois `IfcRelAssignsToProcess`. Os testes cobrem as três fontes e o conflito entre elas. |
| Malha JSON | 537 elementos, 10.284 triângulos, coordenadas relativas a uma origem local (canto mínimo), em metros, com Z para cima |
| GLB | Serializador **nativo** do IfcOpenShell (`ifcopenshell.geom.serializers.glb`), sem dependência extra. O arquivo é glTF 2.0 válido no cabeçalho, e os nós levam o GlobalId (`use-element-guids`, `y-up`). |
| Router | `ligar(app, obter_estado)` (contrato do `api.py` multi-obra; `obter_estado` guardado em `app.state`), com `?obra=` em todas as rotas. Rotas: `GET /api/ifc/exportar` (.ifc), `GET /api/ifc/glb` (glTF binário, `node.name` = GlobalId), `GET /api/ifc/vinculo` (tabela GlobalId → atividade/elemento/km e o sistema de coordenadas) e `POST /api/ifc/vinculos` (IFC qualquer no corpo binário). As três rotas GET compartilham um cache por assinatura dos dados (até 4 exportações). Testado no `criar_app()` real: `ifc.rotas` aparece em `/api/saude` → `modulos.ligados`, obra desconhecida dá 404 em todas as rotas e, sem `ifcopenshell`, o import levanta `ImportError`. Respostas: 400 sem corpo, 422 se não for IFC, 413 acima de 100 MB, 422 se o tipo de obra não tiver mapeamento. |
| Contrato GLB ↔ vínculo | Teste com as duas obras: o conjunto de nomes de nó do GLB é **igual** ao de `global_id` da tabela, e os GlobalIds do `.ifc` baixado também são os mesmos. O GLB tem Y para cima: glTF (x, y, z) = IFC (x, z, −y), em metros, com origem do IFC = coordenadas `alinhamento.pontos` do JSON. |

### Números (base sintética, esta máquina, 2026-11-12)

| Medida | Valor |
|---|---|
| Arquivo IFC com 4D | Ferrovia 1.410.695 bytes (≈1,4 MB), 22.315 entidades. Rodovia 1.653.060 bytes. |
| Arquivo IFC sem 4D | 1.297.723 bytes |
| Tempo de geração | Ferrovia 5,4 s a 6,2 s em 3 execuções (sob carga, com outros agentes rodando, chegou a 12 s; noutra rodada, 2,8 s). Rodovia 1,5–2,4 s. |
| Validação com regras EXPRESS | ≈9–16 s |
| Leitura + tabela + verificação | 0,25 s |
| Malha JSON | 3,0 s; 377.735 bytes |
| GLB | Ferrovia 3,1 s e 583.944 bytes. Rodovia 666.536 bytes. |
| Validação da rodovia (EXPRESS) | 8,3 s, 0 erros. Pico de memória do processo: 225 MB. |

As saídas ficam em `output/ifc/`, que o `.gitignore` ignora (`/output/*`).

## 3. O que não funcionou ou precisou de contorno (resultado negativo é resultado)

1. **`IfcBridgePart.UsageType` é obrigatório** no IFC4X3_ADD2. Na primeira versão, a validação deu 9 erros. Corrigido com `VERTICAL`. O teste `test_validacao_detecta_erro_real` reintroduz o defeito e exige que o validador acuse.
2. **`IfcEarthworksCut` isolado é inválido.** Como `IfcFeatureElementSubtraction`, ele exige `VoidsElements`. A regra EXPRESS também proíbe que ele esteja contido na estrutura espacial (60 erros). Solução: um `IfcGeographicElement` TERRAIN por lote como hospedeiro (sem geometria), com `IfcRelVoidsElement`, e o corte fora do `IfcRelContainedInSpatialStructure`.
3. **A API de cronograma do IfcOpenShell recalcula datas.** `sequence.edit_task_time` e `sequence.assign_sequence` aplicam um calendário padrão: a LB de 03/11/2025 virou `2025-11-04T09:00`. Foi o teste que pegou. O `assign_sequence` ainda roda `cascade_schedule` a cada chamada, o que custou ≈15 s para 264 relações. Contorno: `IfcRelSequence`, `IfcLagTime` e as datas são gravados direto nas entidades, e o IFC leva as datas do **nosso** motor. Não se exporta `IfcWorkCalendar`, então `ScheduleDuration` fica vazio.
4. **Relações duplicadas por par.** A base tem pares SS+FF entre as mesmas atividades, então a chave de conferência precisa incluir o tipo.
5. **Upload multipart não é usado.** `python-multipart` não está no `.venv`, e o POST recebe o `.ifc` como corpo `application/octet-stream`.
6. **Casar só pelo id da atividade engana.** As duas bases reutilizam ids (`L1-S01-SUP`, `OAE1-FUN`…). Conferido contra a rodovia, o IFC da ferrovia "casou" 237 elementos. Isso foi pego pelo teste de integração. Agora a verificação traz `obra_confere` (`IfcProject.Name` × id da obra) e `divergencias` (serviço, lote ou km incoerentes com a atividade). No mesmo cenário: `obra_confere = false`, 207 divergências e 300 sem atividade.
7. **Rodovia, primeira tentativa: 96 erros de validação.** (a) `IfcSurfaceFeature` exige `AdheresToElement`. (b) Por regra EXPRESS, ela não pode estar contida na estrutura espacial. Corrigido: a marcação adere à peça de CBUQ do mesmo segmento e índice (com fallback para IMP, BGS, SBB, TER e, por fim, o terreno) e fica fora do `IfcRelContainedInSpatialStructure`. Resultado: 0 erros.
8. **Bug de sombreamento pego antes do teste.** A variável `tipo` do laço das OAEs sobrescrevia o tipo da obra, e as classes da rodovia saíam erradas, embora a validação desse 0 erros. A validação de esquema não pega classe semanticamente errada. Por isso existe `test_classe_ifc_por_servico`, com a tabela esperada escrita à mão.
9. **`Math.round` × `round`.** O Python arredonda meio para o par, e o visualizador usa o `Math.round` do JS (meio para cima). Com trecho de 2,5 km, a contagem de peças divergiria. O exportador usa `floor(x + 0,5)`.

## 4. E4: IFC oficial da buildingSMART no nosso importador

Os arquivos são baixados **pelo teste** para `output/ifc/externos/`, que o Git ignora e que **nunca** é versionado. O teste confere o SHA-256. Sem rede, ou com `INFRA4D_SEM_REDE=1`, os casos dão SKIP: com a pasta vazia, 15 skipped, observado. Se o upstream mudar, também dão SKIP, com o hash novo na mensagem. O download feito pelo próprio teste foi verificado apagando um arquivo e rodando de novo.

| Arquivo | Caminho (raw GitHub, branch `main`) | Licença | SHA-256 | Bytes |
|---|---|---|---|---|
| Infra-Rail.ifc | `buildingSMART/Certification-datasets/IFC 4.3.2.0 (IFC 4.3 ADD2)/Simple-Scene/Infra-Rail.ifc` | CC BY 4.0 | `c9073051e17796b8b59f96cf268207f4011c08eedeaa791774480c33e9defbb3` | 161.670 |
| Infra-Road.ifc | idem `/Infra-Road.ifc` | CC BY 4.0 | `a3cb29433d7176bd31ff7535a596b5d7cd4eb7f2fb0eb6eee451612063c1f167` | 263.708 |
| segmented-reference-curve.ifc | `buildingSMART/IFC4.x-specification-models/models/alignment-geometries-and-linear-positioning/segmented-reference-curve/` | "all rights reserved until formal release": só baixar e testar | `d4320f2fcc7e9c385f89c56c3002a54127f8d9fb4c5a5a447bd7238806b1eadf` | 6.402 |
| linear-placement-of-signal.ifc | idem `.../linear-placement-of-signal/` | idem | `3c6b97f7a82f1a1d114233702e876f387a03701be0d8a621685e5773ce664c97` | 233.672 |
| construction-scheduling-task.ifc | idem `models/construction-scheduling/construction-scheduling-task/` | idem | `abbb30934dd36ea1370d7464300cd5a33c85ebd438ab10ed2fd258823514fb7d` | 18.874 |

O caminho citado no R05 (`alignment-geometries-and-linear-positioning/...` na raiz) dá **404**: os modelos ficam sob `models/`. A API do GitHub respondeu 403 por limite de taxa, e a árvore foi lida pelas páginas HTML do repositório.

| Arquivo | Validação (`express_rules=True`) | Alinhamento (nosso importador) | Vínculo | Tempos (abrir / validar / importar / malha) |
|---|---|---|---|---|
| Infra-Rail | **0 erros** | **"sem alinhamento"**, explícito, sem eixo inventado | 75 elementos, 0 com atividade (o arquivo não tem 4D). `IfcRailway` e `IfcMapConversion` presentes. | 0,12 s / 4,7 s / 0,49 s / 0,82 s (73 malhas) |
| Infra-Road | **0 erros** | **"sem alinhamento"** | 55 elementos, 0 com atividade. `IfcRoad` e `IfcMapConversion` presentes. | 0,02 s / 5,2 s / 0,76 s / 1,22 s (53 malhas) |
| segmented-reference-curve | **0 erros** | 1 `IfcAlignment` com horizontal, vertical e cant; 2 segmentos horizontais, 100,0 m. **Estaca inicial e final: não declaradas.** O referente "Start Station" existe, mas sem `Pset_Stationing.Station`, e o importador devolve `None` em vez de inventar 0. | sem elementos | 0,01 s / 4,2 s / 0,63 s / — |
| linear-placement-of-signal | **0 erros** | 1 `IfcAlignment` "Track alignment" com H, V e cant; 10 segmentos; 1.029,372 m. **Estaca inicial −153,1. Estaca final calculada 876,2721** (inicial + soma dos segmentos), que **bate** com o referente "End" declarado no arquivo (876,2720713). Há 23 referentes de estaca. | 2 `IfcSignal`, sem 4D | 0,02 s / 4,4 s / 0,44 s / 1,26 s |
| construction-scheduling-task | **0 erros** | "sem alinhamento" | 5 elementos (`IfcWall`, `IfcSlab`), **todos vinculados pela fonte `produto`** (`IfcRelAssignsToProduct`), sem o nosso Pset. 8 `IfcTask`. | 0,01 s / 2,8 s / 0,42 s / 0,04 s |

- **Memória:** pico do conjunto de trabalho do processo (Windows `PeakWorkingSetSize`) entre 216 e 218 MB em cada arquivo externo, contra ≈41 MB logo após o import. O custo dominante é carregar o validador e o esquema, não o tamanho do arquivo. Na ferrovia e na rodovia (≈1,5 MB), o pico foi de 224–225 MB.
- **Critério do R05 não verificável como escrito:** o E4 pedia "estações de início/fim iguais às do README do exemplo", mas o README do `segmented-reference-curve` **não declara estações** (é um exemplo de superelevação). A conferência possível foi feita no `linear-placement-of-signal`: a estaca final calculada coincide com o referente "End" do próprio arquivo.
- **Peculiaridade do IfcOpenShell:** ao gerar a malha do `linear-placement-of-signal`, o núcleo C++ escreveu linhas de depuração em UTF-16 ("local z: … delta: …") no **stdout**, 292 bytes. Isso não afeta a API, que não lê o stdout, mas quebra script que espere JSON puro no stdout.

## 5. Quantidades, classificação e requisitos de informação (ligação BIM → 4D/5D)

### 5.1 Quantidades por elemento

Cada peça leva duas famílias de quantidade, que não se misturam.

- **Qto oficial da classe** (`Qto_*BaseQuantities`), calculado da **geometria da peça**. Nomes e tipos são conferidos por teste contra o template IFC4X3 do IfcOpenShell (`ifcopenshell.util.pset.get_template`), e um nome inventado faz o teste falhar (sabotagem `CompactedVolume`→`CompactVolume`: 3 falhas). Conjuntos usados:

  | Classe | Conjunto | Quantidades |
  |---|---|---|
  | `IfcEarthworksFill` | `Qto_EarthworksFillBaseQuantities` | `Length`, `Width`, `Depth`, `CompactedVolume` |
  | `IfcEarthworksCut` | `Qto_EarthworksCutBaseQuantities` | `Length`, `Width`, `Depth`, `UndisturbedVolume` |
  | `IfcCourse` | `Qto_CourseBaseQuantities` | `Length`, `Width`, `Thickness`, `Volume` |
  | `IfcPavement` | `Qto_PavementBaseQuantities` | `Length`, `Width`, `Depth`, `GrossArea`, `NetArea`, `GrossVolume`, `NetVolume` |
  | `IfcPipeSegment` | `Qto_PipeSegmentBaseQuantities` | `Length`, `GrossCrossSectionArea` |
  | `IfcRail` | `Qto_RailBaseQuantities` | `Length`, `Volume` |
  | `IfcRailing` | `Qto_RailingBaseQuantities` | `Length` |
  | `IfcSurfaceFeature` | `Qto_SurfaceFeatureBaseQuantities` | `Area`, `Length` |
  | `IfcSign` | `Qto_SignBaseQuantities` | `Height`, `Width` |
  | `IfcPile`, `IfcColumn`, `IfcBeam` | `Qto_PileBaseQuantities`, `Qto_ColumnBaseQuantities`, `Qto_BeamBaseQuantities` | `GrossVolume`, `NetVolume` (e `Length` na viga) |

  O template **não** tem `Qto_*BaseQuantities` para `IfcTrackElement`, `IfcFastener` e `IfcBuiltElement` (só `Qto_BodyGeometryValidation`). Nessas classes há apenas o conjunto próprio abaixo.

  Quantidades oficiais **deixadas de fora de propósito**: `LooseVolume` do aterro e do corte (exige empolamento, que o dado não tem) e `Weight` (o dado não tem massa específica).
- **`INFRA4D_Quantidade`** (conjunto próprio), na **unidade do serviço**. A unidade define o tipo da quantidade: m³ → Volume; m e km → Length; m² e ha → Area; t → Weight; un → Count. O modelo guarda tudo em SI; foi acrescentada a unidade de massa `kg` ao projeto. Duas quantidades:
  - `QuantidadeGeometrica`: tirada da geometria esquemática.
  - `QuantidadeContratual`: a `quantidade_total` da atividade rateada entre as peças. Em `un` o rateio é por maior resto, porque `IfcCountMeasure` é **inteiro** no IFC4X3_ADD2.
- **Teste à mão (peça simples):** terraplenagem de 1 km em eixo reto. A peça vai do km 0,003 ao 0,997 (994 m), com seção trapezoidal de base 17 m, topo 12 m e altura 1,5 m, o que dá 21.619,5 m³. `CompactedVolume`, `QuantidadeGeometrica` **e o volume da malha triangulada pelo IfcOpenShell** (`ifcopenshell.util.shape.get_volume`, conferência independente) dão esse valor. Outros casos conferidos à mão: drenagem com 2 linhas (1.988 m), supressão com 26 m × 994 m (2,5844 ha, guardados como 25.844 m²) e grade em km de eixo (0,994 km), com `Length` do trilho de 1.988 m.

### 5.2 Coerência com o dataset (resultado: a peça é esquemática)

- **Contratual:** a soma por atividade é **igual** a `quantidade_total` em todas as atividades com peça, nas duas obras. Há teste, e a sabotagem do rateio o fez falhar.
- **Geométrica:** **não** reproduz a quantidade de projeto, e isso fica reportado (`coerencia`) em vez de escondido. A razão geométrica/contratual observada por serviço:

| Ferrovia | razão | Rodovia | razão |
|---|---|---|---|
| TER | 0,31 | TER | 0,56 |
| SUP | 0,65 | SUP | 1,08 |
| DRE | 4,7–4,8 | DRE | 6,2–6,3 |
| SUB | 1,38–1,40 | SBB / BGS | 2,94–2,97 / 2,24–2,26 |
| LAS | 0,75–0,76 | IMP | 1,99–2,01 |
| GRA | 0,99–1,01 | CBU (t) | 3,45–3,49 (massa específica premissa **fictícia** 2,4 t/m³) |
| DOR (un) | 0,0006 (a faixa contínua conta 1, contra 1.667/km) | SHV (m) | 1,99–2,01 |
| SOL (un) | 0,48 | SVV (un) | 1,33 |
| OAE-FUN | 0,28–0,33 | DEF (m) | 7,95–8,03 |
| OAE-MES / SUE | 1,00 | OAE-MES / SUE | 1,00 |

O motivo é que a seção vem do visualizador (ordem de grandeza visual) e a quantidade de projeto vem do gerador sintético. Nenhuma das duas é medição real.

### 5.3 Classificação e custo pelo modelo (5D, fictício)

- **Classificação:** uma `IfcClassification` "INFRA4D-FICTICIO" (de `orcamento.SISTEMA_CLASSIFICACAO`), declarada no `IfcProject`, e uma `IfcClassificationReference` por composição (`FIC-FER-TER-001`…), associada a cada elemento pelo serviço.
- **Custo pelo modelo** = Σ `QuantidadeContratual` × preço de venda fictício (`orcamento.preco_venda`). É **igual**, atividade por atividade (tolerância relativa 1e-9), ao BAC do `orcamento.orcar_atividades`:
  - Ferrovia: R$ 485.993.500 no modelo, contra R$ 503.993.500 no orçamento total.
  - Rodovia: R$ 218.276.100, contra R$ 219.588.600.
  - A diferença são só as **verbas sem peça física** (SIN e LIB), o que o teste também confere.
- **Custo geométrico** (Qto × preço), apenas indicativo: ferrovia R$ 494,6 mi, rodovia R$ 525,2 mi.
- **Divergência encontrada no `orcamento.py`** (arquivo de outro agente, que não editei): o `MAPA_IFC` "proposto" de lá não bate com o exportador.
  - Ele mapeia `IfcEarthworksCut` → TER; o exportador usa SUP (supressão TOPSOILREMOVAL).
  - Na rodovia, `IfcCourse` PAVEMENT → CBU por `Weight`; o exportador usa SBB/BGS, e CBU é `IfcPavement`.
  - `IfcPavement` FLEXIBLE → IMP por `NetArea`; o exportador grava IMP como `IfcCourse` PRIMECOAT.
  - O exportador classifica pelo **serviço** (direto), não por esse mapa. É preciso alinhar os dois.

### 5.4 Requisitos de informação (o que o IDS faria), `requisitos.py`

São verificados sobre os elementos construtivos: `IfcElement` **sem** aberturas, terreno `IfcGeographicElement`, `IfcElementAssembly` (que só agrega) e `IfcVirtualElement`.

- **R1:** GlobalId único.
- **R2:** Pset `INFRA4D_Vinculo.AtividadeId` **ou** `IfcRelAssignsToProduct` → `IfcTask`.
- **R3:** `IfcClassificationReference`.
- **R4:** quantidade > 0 do tipo compatível com a unidade do serviço. A unidade vem do Pset `Unidade` ou da atividade.
- **R5:** `IfcLinearPlacement` **ou** `IfcRelPositions` a partir de `IfcAlignment`, com a estaca do Pset dentro do eixo. O exportador agora grava `IfcRelPositions` eixo → peças. As peças **continuam** com `IfcLocalPlacement`, e o relatório informa o modo (`modos: IfcRelPositions 537`).
- **R6:** `IfcTask` dentro de `IfcWorkSchedule` (direto ou por aninhamento), com datas planejadas (`ScheduleStart/Finish` ou `EarlyStart/Finish`).

| Arquivo | Conclusão do relatório | R1 | R2 | R3 | R4 | R5 | R6 |
|---|---|---|---|---|---|---|---|
| Ferrovia exportada (537) | **APROVADO** | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Rodovia exportada (531) | **APROVADO** | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Infra-Rail (73) | **REPROVADO em R2–R6** | ✔ | ✘ | ✘ | ✘ | ✘ (sem IfcAlignment) | ✘ |
| Infra-Road (53) | **REPROVADO em R2–R6** | ✔ | ✘ | ✘ | ✘ | ✘ | ✘ |
| construction-scheduling-task (5) | **REPROVADO em R3, R4, R5** | ✔ | ✔ (fonte produto) | ✘ | ✘ | ✘ | ✔ |
| linear-placement-of-signal (2) | **REPROVADO em R2, R3, R4, R6** | ✔ | ✘ | ✘ | ✘ | ✔ (IfcLinearPlacement) | ✘ |
| segmented-reference-curve (0) | **NÃO VERIFICÁVEL** (sem elementos) | — | — | — | — | — | — |

- **Ressalva sobre a expectativa "os oficiais reprovam no 4D":** ela vale para os `Infra-*`. O `construction-scheduling-task` é justamente o exemplo oficial de 4D e **passa** em R2 e R6; reprova em classificação, quantidade e eixo.
- **Primeira versão do R6:** reprovava esse arquivo por exigir `ScheduleStart/Finish`, mas o exemplo grava só `EarlyStart/Finish`. O critério foi ampliado e o motivo da reprovação agora é específico ("fora de IfcWorkSchedule" ≠ "sem datas").
- **Detectores vistos falhando:** o teste `test_requisitos_detectam_cada_falha` estraga o modelo de um jeito por requisito e exige que **exatamente** o elemento estragado apareça na lista de reprovados: GlobalId duplicado, vínculo removido, classificação removida, quantidades removidas, estaca fora do eixo e `IfcRelPositions` removido. As sabotagens no código (nome de Qto, classificação desligada, rateio sem maior resto) fizeram falhar 3, 6 e 3 testes, e o código foi restaurado (`diff` vazio).
- **Rotas:** `GET /api/ifc/requisitos?obra=` (modelo exportado, com `quantidades` e `custo`) e `POST /api/ifc/requisitos?obra=` (upload, mesmo limite de 100 MB, 400 sem corpo, 422 se não for IFC). O upload do `Infra-Rail` volta `aprovado: false`, com R2 e R6 na conclusão (há teste).
- **Tempo e tamanho:** a verificação leva 0,23–0,25 s por obra. Com Qto e classificação, o IFC passou a 1,96 MB (ferrovia) e 2,26 MB (rodovia), com 0 erros na validação EXPRESS.

## 6. Conformidade IFC 4.3: `IfcLinearPlacement` e estaqueamento no eixo

### 6.1 Peças com `IfcLinearPlacement`

Cada peça agora tem `ObjectPlacement` = `IfcLinearPlacement` → `IfcAxis2PlacementLinear` → `IfcPointByDistanceExpression`:
- `DistanceAlong`, `OffsetLateral` e `OffsetVertical` são medidos sobre a curva base do `IfcAlignment`;
- `CartesianPosition` vai preenchido como posição de reserva.

O quadro usado é o do **próprio IfcOpenShell**: X na tangente, Y na normal à esquerda (lateral positiva = esquerda, confirmado por experimento) e Z para cima. A distância ao longo vem da projeção, por Newton, do ponto de origem da peça na curva. O resíduo máximo dessa projeção foi 6e-12 m na ferrovia e 1e-11 m na rodovia. Os sólidos foram reescritos no quadro girado (Rᵀ·v), e por isso a peça fica **no mesmo lugar**.

- **Teste de posição:** compara, por GlobalId, os vértices triangulados pelo IfcOpenShell na versão anterior (`IfcLocalPlacement`) e na nova (distância de Hausdorff). O resultado medido foi **1,5e-11 m** na ferrovia e **7,3e-12 m** na rodovia. **Tolerância proposta para o manifesto: `tolerancia_posicao_ifc_m: 0.001`** (1 mm, folga de 8 ordens de grandeza, a mesma escala de `tolerancia_estaca_m`). Enquanto o campo não estiver no `project.yaml`, o teste **falha** de propósito (regra do `conftest`).
- **Detector visto falhando:** sabotei o código para não girar os sólidos e as peças se deslocaram até **192,9 m** (mediana 58 m). Depois restaurei.
- **R5** agora reporta `modos: {'IfcLinearPlacement': 537}` (531 na rodovia). O `IfcRelPositions` foi mantido. Também há teste mutante: sem linear placement e sem `IfcRelPositions`, todos os elementos reprovam.
- **Validação EXPRESS:** 0 erros nas duas obras.

| Medida | Antes (`IfcLocalPlacement` + Qto) | Depois (`IfcLinearPlacement` + estacas) |
|---|---|---|
| Ferrovia: bytes | 1.959.482 | 2.143.882 (+9,4%) |
| Rodovia: bytes | 2.258.920 | 2.434.202 (+7,8%) |
| Ferrovia: tempo de geração | 1,9–4,0 s | 2,0–3,3 s |
| Rodovia: tempo de geração | 1,9–3,7 s | 2,1–3,1 s |
| Validação EXPRESS | 9–11 s, 0 erros | 8,0 / 8,2 s, 0 erros |

### 6.2 Estacas no eixo (`IfcReferent` + `Pset_Stationing`)

O km do projeto é uma **medida** (como a coordenada M de `referencia_linear`), não o comprimento da curva. Na ferrovia, 60 km de medida correspondem a 60.279,56 m de curva IFC; na rodovia, 48 km correspondem a 48.145,40 m. O IFC 4.3 calcula a estaca entre referentes como `Station + distância ao longo`. Para que a estaca IFC seja a do projeto **em cada km**:

- cada km inteiro vira um `IfcReferent` **STATION**;
- `Pset_Stationing.Station` = estaca do projeto (a mesma de `/api/referencia/km`);
- `Pset_Stationing.IncomingStation` = estaca que o IFC traria por continuidade geométrica: uma **equação de calibração** por km;
- o referente fica em `IfcLinearPlacement` sobre o eixo, com `INFRA4D_Referencia.Km`;
- as equações de estacas do projeto (`meta.equacoes_estaca`) entram do mesmo jeito, com `INFRA4D_Referencia.EstacaAnteriorMedida` = estaca "de volta" na medida do projeto.

São 61 referentes na ferrovia e 49 na rodovia. Os referentes são criados com `alignment.add_stationing_referent` (aninhados e ordenados pela própria API).

O que foi conferido:
- O importador lê as estacas dos referentes (`alinhamentos()` → `referentes`, `comparar_estacas`) e **compara com `GET /api/referencia/km`** da mesma obra, km a km: o texto é igual e a diferença em metros é ≤ `tolerancia_estaca_m` (teste nas duas obras).
- **O próprio IfcOpenShell concorda:** `alignment.distance_along_from_station(estaca)` devolve a distância do referente, com diferença 0 medida.
- **Equação de estacas** (teste à mão, eixo com deflexão): estaca 50+00 → 60+00 no km 1 dá `Station` 1.200 m, `IncomingStation` = curva percorrida, `EstacaAnteriorMedida` 1.000 m e km 2 = 110+00 (2.200 m). Validação EXPRESS sem erro.

**Limitação de fundo (resultado negativo):** o IFC não tem fator de escala de estaqueamento. Entre dois km, a estaca IFC cresce 1 m por metro de curva e a do projeto cresce 1 m por metro de medida. A diferença dentro de um km chega a **18,49 m na ferrovia** (o km 0–1 tem 1.018,49 m de curva) e a **12,85 m na rodovia**, e volta a zero em cada referente. As peças não são afetadas, porque sua posição é geométrica. O que é afetado é a leitura de estaca **entre** referentes por software de terceiros. Referentes mais densos (a cada estaca de 20 m) reduziriam o erro a ≤ 0,37 m, ao custo de cerca de 3.000 referentes.

### 6.3 Correções da revisão adversarial r15 (defeitos ALTOS 7, 8 e 9)

- **(7) Peça fora da extensão do eixo:** antes do km inicial ou depois do km final, a peça saía deslocada em silêncio (497 m e 203 m nos casos do revisor), porque a projeção prendia a distância em [0, L]. Agora a componente ao longo da tangente na ponta vai em `IfcPointByDistanceExpression.OffsetLongitudinal`. Confirmei por experimento que o IfcOpenShell respeita esse campo: um deslocamento de −100 move a peça 100 m. A `CartesianPosition` inclui o mesmo deslocamento.
- **(8) Deflexão grande no PI:** com 120° e 150° de deflexão, o Newton oscilava e a peça saía 112 m e 579 m fora do lugar. A projeção agora:
  1. procura o ponto mais próximo em toda a curva, por amostragem a cada ≤ 50 m e com pelo menos 3 amostras por segmento;
  2. refina por Newton dentro do intervalo entre as amostras vizinhas;
  3. se o Newton não converge, usa seção áurea;
  4. se o resíduo passa de `TOLERANCIA_PROJECAO_M` (0,001 m, igual a `tolerancia_posicao_ifc_m`, com teste que confere a igualdade), levanta **`ErroExportacao`**. Nunca exporta a peça deslocada.
- **(9) Eixo começando ou terminando em km não inteiro:** os PIs incluem agora o **primeiro e o último ponto** da polilinha, além dos km inteiros.
- **Teste de posição:** confere também `residuo_projecao_m` ≤ tolerância.
- **`comparar_estacas` compara POSIÇÃO:** o referente tem de estar no pé da perpendicular do ponto do km, com `desvio_longitudinal_m` ≤ tolerância; `afastamento_m` fica como informação. Um teste mutante move um referente 1 km: o texto da estaca continua igual e a posição acusa.
- **Resultado:** os casos de 120°, 150°, antes do início e depois do fim passam, e o desvio entre as versões linear e local fica em ~1e-12 m.
- **Ainda reprovado (XFAIL), por desenho:** `test_eixo_que_comeca_em_km_fracionario` exige que o referente do km 1 fique a 700,00 ± 0,01 m do referente do km 0,3. Com a curva de concordância no PI do km 1, o pé da perpendicular do vértice fica a **699,48 m**. A diferença é T − RΔ/2 ≈ RΔ³/24 = 4.480 m × 0,1405³ / 24 ≈ 0,52 m. Para caber em 0,01 m, o raio teria de ser ≤ 86 m. Todo o resto desse teste passa: estacas 300 e 1000 e peças no lugar com desvio 1,8e-12 m. É preciso decidir com o revisor: a expectativa do teste deveria ser a distância até o pé da perpendicular, não o comprimento da polilinha.
- **Custo:** a amostragem acrescenta ~2–3 s à exportação: ferrovia 6,5 s, rodovia 7,0 s. Os tamanhos não mudaram (2.363.928 e 2.703.885 bytes).

### 6.4 Defeitos do IfcOpenShell 0.9.0.post1 encontrados nesta etapa

1. **`alignment.create_by_pi_method` dá `ZeroDivisionError` com PIs colineares.** Um eixo reto de 3 PIs caía em silêncio no fallback de polilinha, e com ele o `IfcLinearPlacement`. O exportador agora remove PIs internos sem deflexão antes (`_sem_colineares`), e há teste.
2. **`alignment.generate_vertices` não funciona** ("Setting not available": `piecewise-step-type`).
3. **`alignment.evaluate_representation` sobre a curva inteira custa 9–25 ms por chamada.** `evaluate_segment` no segmento certo dá o **mesmo** quadro (diferença 0) em 0,5 ms. A primeira versão levou 23–41 s para exportar; a atual, 2–3 s.
4. **`IfcCurveSegment.SegmentLength` tem sinal** (arco à direita é negativo). Somar sem `abs()` dá um comprimento errado (54.403 m em vez de 60.280 m), e a projeção trava no fim do eixo. Corrigido.
5. **`alignment.update_fallback_position` e a triangulação de peças com `IfcLinearPlacement`** fazem o núcleo C++ escrever uma linha de depuração em UTF-16 por peça no **stdout**. Contornos:
   - a `CartesianPosition` é calculada pelo exportador;
   - o `GET /api/ifc/glb` triangula a versão `IfcLocalPlacement` do mesmo modelo (mesma geometria a 1e-11 m e mesmos GlobalIds).

   O `POST` com IFC de terceiro que use linear placement ainda polui o stdout ao gerar malha.

## 7. Cronograma nativo IFC por cenário (`cronograma.py`) e ida e volta pelo motor

### 7.1 O que é gravado

- **`IfcWorkPlan` "INFRA 4D"** (`IfcRelDeclares` no projeto), que agrega um **`IfcWorkSchedule` por cenário**: `Identification` = cenário, `StartTime` = início do projeto e `FinishTime` = término do cenário. O tipo depende do cenário:
  - linha_base → BASELINE;
  - construtora → PLANNED;
  - independente → USERDEFINED/INDEPENDENTE;
  - simulado → USERDEFINED/SIMULADO, **só quando há ajustes**. A rota usa os ajustes da simulação corrente da obra.
- **`IfcTask`** por atividade e por cenário. O IFC permite um só `TaskTime` por tarefa, por isso a tarefa se repete em cada cenário. Atributos:
  - `Identification` = atividade, `Status`, `IsMilestone` e `ObjectType` = tipo do motor;
  - GlobalId estável: uuid5 de obra + cenário + atividade.
- **`IfcTaskTime` WORKTIME:**
  - `ScheduleDuration` (ou `RemainingTime`, se a atividade estiver em andamento) em `P{n}D` de dias **úteis**;
  - `ScheduleStart` e `ScheduleFinish` = início e término da API;
  - `Early*` e `Late*` = es, ef, ls e lf do motor (**ef e lf exclusivos**, convenção do motor);
  - `TotalFloat`, `FreeFloat`, `IsCritical`, `StatusTime` = data de status, `Actual*` e `Completion` = executado/total (só se > 0, porque o tipo é `IfcPositiveRatioMeasure`).
- **`IfcWorkCalendar`** por calendário, compartilhado pelos cenários: dias úteis num `IfcRecurrencePattern` WEEKLY (1 = segunda) e dias não úteis agrupados em faixas contínuas (`ExceptionTimes`). A ligação à tarefa é por `IfcRelAssignsToControl`.
- **`IfcRelSequence`** com tipo FS, SS, FF ou SF e `IfcLagTime` WORKTIME.
- **Um `IfcRelAssignsToProduct` por peça**, ligando a tarefa da atividade nos 3 cenários (decisão do orquestrador).
- **Sem campo no IFC:** as restrições SNET e FNLT vão para o Pset `INFRA4D_Restricoes` (`IfcDate`).
- **Valores negativos:** o validador do IfcOpenShell aceita **qualquer texto** em `IfcDuration`. Testado: `"P3D"`, `"-P3D"`, `"abc"` e `"P-3D"` dão 0 erros, e o `ifcopenshell.util.date` lê `"-P3D"` como −3 dias. O aceite é **por omissão**, não por regra, e o ISO 8601 não define duração negativa. Por isso, folga negativa vai para `INFRA4D_Folgas` (com `TotalFloat`/`FreeFloat` vazios) e lag negativo vai para `INFRA4D_LagsNegativos` na tarefa sucessora, porque uma relação não aceita Pset (a `IfcRelSequence` fica sem `TimeLag`). Há teste: nenhum `IfcDuration` sai com "-".
- **Não uso a API de escrita** `ifcopenshell.api.sequence` para datas e sequências: ela recalcula as datas e faz cascata (seção 3). Crio as entidades diretamente.

### 7.2 Ida e volta (mesma lógica do teste MSPDI)

O IFC é gravado, relido e passa por `cronograma.ler(f, cenario)`, que devolve a mesma tupla de `importar_mspdi`, `(atividades, relacoes, calendarios, metadados)`. O resultado vai para `motor.calcular`.

- **Datas recalculadas:** linha de base, construtora e independente, **nas duas obras**. es/ef e folga total de **todas** as atividades, término e caminho crítico ficam **iguais** à referência (`montar_entrada` + `calcular`). O término confere com `executar()`: na ferrovia 27/05/2027, 23/07/2027 e 09/09/2027.
- **Datas gravadas iguais à API:** início, término, es, ef, ls, lf, folga total, folga livre e crítica, em todas as atividades.
- **Simulado:** com um ajuste de produtividade, a ida e volta é igual ao `executar(simulado, ajustes)`, e o término difere do independente.
- **Folga e lag negativos:** o caso com FNLT apertado e lag −3 volta exato pelo Pset.
- **Calendários:** os dias úteis e os não úteis voltam **exatamente** iguais aos do projeto.
- **Rotas:**
  - `GET /api/ifc/exportar?obra=` grava os 3 cenários, e o simulado entra quando há simulação ativa (testado: POST `/api/simulacao` → o IFC passa a trazer o simulado, com o término da API).
  - `POST /api/ifc/cronograma?obra=&cenario=` lê o cronograma de um IFC enviado, recalcula e informa `confere_com_api`. Respostas: 400 sem corpo; 422 se não for IFC; 422 se o cenário não estiver no arquivo, com a lista dos cenários que existem.
- **Detectores vistos falhando:**
  - **Mutantes no IFC:** um lag maior aumenta o término; apagar as relações que chegam numa atividade crítica antecipa o início dela; tirar uma faixa de dias não úteis muda o calendário relido. A primeira versão do mutante "apagar relação" não mudou nada, porque a base tem pares SS+FF e apagar só uma relação não basta. Corrigi para apagar todas as que chegam na atividade.
  - **Sabotagens no código:** dia da semana sem o +1 → 4 falhas; SS e FF trocados na exportação → 3 falhas; duração do andamento ignorada → 3 falhas. Restaurei, com `diff` vazio.
  - **Bug pego pelo teste de rota:** o simulado não entrava no IFC, porque os ajustes chegavam mas a lista de cenários não o incluía. Corrigido.

### 7.3 Tamanho, tempo e validação

| Medida | Antes (1 cronograma, sem calendário) | Depois (3 cenários + calendários) |
|---|---|---|
| Ferrovia: bytes | 2.143.882 | 2.364.534 (+10,3%) |
| Rodovia: bytes | 2.434.202 | 2.704.507 (+11,1%) |
| Ferrovia: tarefas / sequências / calendários / `IfcWorkTime` | 113 / 264 / 0 / 0 | 339 / 792 / 4 / 315 |
| Rodovia: tarefas / sequências | 137 / 301 | 411 / 903 (`IfcWorkTime` 464) |
| `IfcRelAssignsToProduct` | 1 por peça | 1 por peça (537 / 531), cada uma com 3 tarefas |
| Tempo de geração | 2–3 s | 3,2 s (ferrovia), 5,1 s (rodovia) |
| Validação EXPRESS | 8 s | 19,3 s (ferrovia), 19,5 s (rodovia); 0 erros nas duas |

Decisão de teste: EXPRESS completo na ferrovia e só esquema na rodovia, por tempo. Está declarado nos dois arquivos de teste.

### 7.4 Leitores de terceiros: durações e o defeito de calendário do IfcOpenShell (R13)

- **R13-3, atividade em andamento:** passa a gravar também `ScheduleDuration` = dias úteis do início ao término do cenário, no calendário dela, além de `RemainingTime`. Leitores que só olham `ScheduleDuration` (a cascata do Bonsai, pelo código) veriam duração 0. O nosso `ler` continua tirando a duração remanescente de `RemainingTime`, e a ida e volta continua exata (testes da seção 7.2).
- **Atividade concluída:** o motor usa duração 0, e por isso o `ScheduleDuration` continua `P0D`, porque o `ler` o usa. A duração **real** vai em `ActualDuration` = dias úteis entre o início e o término reais.
- **Teste visto falhando:** sabotar o `ScheduleDuration` das atividades em andamento faz o teste falhar; restaurado.
- **Defeito de calendário do IfcOpenShell 0.9.0.post1:** `util.sequence.is_day_in_work_time` testa `dia > StartDate` e depois **sobrescreve** o resultado com `dia < FinishDate`. Com qualquer `FinishDate`, toda exceção vira "todo dia antes do término". Testei com o próprio `ifcopenshell.util.sequence.is_working_day`, num feriado em 21/04/2026 (terça) e calendário de segunda a sábado:

| Como a exceção é gravada | Leitura do IfcOpenShell |
|---|---|
| 1 dia, início = término (o que gravamos) | ERRADO: 14/04 e 20/04 viram não úteis e 21/04 vira útil |
| faixa do dia anterior ao seguinte | ERRADO em 14/04 e 20/04 |
| só `StartDate` | ERRADO em 21/04, 22/04 e 28/04 |
| `YEARLY_BY_DAY_OF_MONTH` (21/4), sem datas | CERTO, mas vale para todos os anos |
| anual limitado por `StartDate`/`FinishDate` de 2026 | certo nos dias testados, mas pelo mesmo defeito vale também para os anos anteriores |

- **Conclusão (decisão do orquestrador): o formato NÃO muda.** Só o padrão anual sem datas é lido certo pelo IfcOpenShell, e ele só serve para feriado fixo que se repete todo ano. Os dias de chuva são datas avulsas (244 no CAL-TERRA da ferrovia) e **não têm contorno** válido pela especificação. Quem ler o nosso IFC com `ifcopenshell.util.sequence` (o Bonsai, por exemplo) verá dias úteis errados perto das exceções.
- **Nosso importador não usa essa função:** um grep em `scripts/` por `util.sequence`, `is_working_day` e `is_day_in_work_time` não acha nada. O `cronograma.ler` expande `StartDate..FinishDate` com lógica própria.

### 7.5 IFC de terceiro incompleto (r17, defeito 7)

O `POST /api/ifc/cronograma` respondia **500** em 7 variações válidas no esquema, mas fora do que o `ler` supunha: `SequenceType` NOTDEFINED ou ausente, `IfcTask` sem `TaskTime`, exceção de calendário sem `StartDate`, padrão WEEKLY sem `WeekdayComponent`, tarefa sem `Identification` e cronograma sem `StartTime`.

Agora o `ler` valida cada um desses casos e levanta `ErroCronograma` com o motivo, e a rota responde 422. O `ler` também recusa:
- duas tarefas com a mesma `Identification`;
- data ilegível;
- exceção invertida ou de mais de 10 anos;
- lag que não é `IfcDuration` (por exemplo `IfcRatioMeasure`);
- relação com a sucessora fora do cronograma do cenário.

Lag ou duração em **ELAPSEDTIME** (dias corridos) é lido como dias úteis e gera **aviso** declarado em `metadados["avisos"]`, que a rota devolve em `avisos`. A rota tem ainda uma rede de segurança (`TypeError`, `KeyError`, `AttributeError` e `OverflowError` viram 422) para o que escapar.

Resultado: os 7 casos da r17 passam (XPASS). Há também teste próprio com a palavra-chave do motivo em cada caso.

**Não verificado:** se outros softwares (Bonsai, Synchro, Navisworks) leem `P{n}D` em WORKTIME como n dias úteis.

## 8. Simplificações declaradas (não confundir com IFC de projeto real)

- As peças são **prismas na corda** entre o km inicial e o final de cada parte, e não `IfcSectionedSolidHorizontal`. O posicionamento é linear (seção 6), mas o sólido continua reto.
- As peças seguem a polilinha do JSON (km → x, y, cota). O eixo IFC é a concordância dos PIs de km inteiro, então passa *perto* dos pontos intermediários, sem coincidir. O desvio **não foi medido**.
- No dado sintético, km não é igual à distância percorrida no plano (km 1 ≈ 1.018 m). O IFC não corrige isso.
- Não há `IfcAlignmentVertical`: a cota está só na geometria.
- Não há georreferenciamento (`IfcMapConversion`). As coordenadas são locais, com origem no km 0.
- Não há estilos ou cores no IFC e no GLB, nem materiais.
- Terraplenagem sem distinção corte/aterro, porque o dado não distingue.
- `SUB` como `IfcCourse` USERDEFINED "SUBBALLAST" e `IMP` como `IfcCourse` USERDEFINED "PRIMECOAT" são escolhas a confirmar contra exemplos oficiais. O `Infra-Road` oficial usa `IfcCourse` e `IfcSurfaceFeature` para camadas e marcações, o que é coerente com o mapeamento adotado.
- Rodovia: as camadas são elementos soltos por km, sem `IfcPavement` agregando `IfcCourse`.
- A regra de peças e as seções estão duplicadas: em Python (`exportar.pecas`, `plano_de_estilos`, `POR_TIPO`) e em JS (`web/viewer3d.js`, `web/secoes.js`). Se uma mudar, a outra precisa acompanhar.

## 9. Não verificado

- Abrir o `.ifc` gerado em outro software (Bonsai, BIMvision, Solibri, web-ifc). Só o próprio IfcOpenShell leu e validou.
- IFC **de obra real**. Os arquivos da buildingSMART são exemplos pequenos (até 264 kB).
- Carregar o GLB no three.js (GLTFLoader). Só o cabeçalho, o chunk JSON e os nomes de nó foram verificados. O carregamento é tarefa do frontend.
- A validação do IfcOpenShell não é a ferramenta oficial da buildingSMART (validate.buildingsmart.org).

## 10. Próximos passos

1. **GLB no visualizador.** As rotas `/api/ifc/glb` e `/api/ifc/vinculo` já existem. Falta o frontend carregar com `GLTFLoader` e pintar pelo GlobalId. Se o arquivo pesar, cortar o GLB por lote.
2. **Importar geometria e alinhamento do IFC de terceiros para a referência linear** (estaca ↔ km): o `linear-placement-of-signal` é o oráculo.
3. **web-ifc no navegador** (MPL-2.0, ver R04). Testar se abre o arquivo gerado aqui, inclusive `IfcAlignment`, como alternativa ao backend.
4. Abrir o arquivo no **Bonsai** (GPL, só bancada) e conferir visualmente a estrutura espacial, o 4D e o alinhamento.
5. Posicionamento linear (`IfcLinearPlacement`) e `IfcAlignmentVertical` a partir da cota, para que as peças sigam o eixo semântico.
6. Rodovia: agregar `IfcCourse` em `IfcPavement` e usar `IfcRoadPart` CARRIAGEWAY/SHOULDER para as pistas.
7. Alinhar o `MAPA_IFC` do `orcamento.py` com as classes do exportador (ver 5.3) e decidir se a quantidade de medição do 5D deve vir do Qto geométrico, o que exige seção de projeto, não a do visualizador.
8. `IfcSectionedSolidHorizontal` (sólido que acompanha a curva) e `IfcAlignmentVertical` a partir da cota.
9. Registrar a dependência no inventário de terceiros. O orquestrador já acrescentou `ifcopenshell>=0.9,<0.10` ao `requirements.txt`.
