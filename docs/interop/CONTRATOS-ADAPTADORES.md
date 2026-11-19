# Contratos de autoria externa e federação

Data: 13/11/2026. Escopo desta rodada: **100% fictício**, sem acesso ao Programa.

## Fontes e responsabilidades

O arquivo nativo é a fonte da geometria. O INFRA 4D mantém o cálculo independente, os vínculos e a publicação aprovada. Uma malha de apresentação não determina quantidade de projeto. Os aplicativos GPL são executados separadamente; QGIS e Blender não são importados pelo servidor proprietário.

| Adaptador | Entrada / saída | Fidelidade desta rodada | Evidência |
|---|---|---|---|
| QGIS | GeoJSON → GeoPackage e projeto QGZ → GeoJSON de revisão | 108 atividades lineares, IDs e unidades; quantidade editável; CRS horizontal EPSG:4326, âncora fictícia | API oficial 3.40.14 criou, editou, salvou e reabriu nativos; GUI não observada |
| Blender | GeoJSON com pontos locais → BLEND e GLB → JSON de revisão | 108 malhas agregadas por atividade, propriedades, vértices/faces/matriz em metros; geometria ilustrativa | Blender 5.2.3 LTS/bpy salvou e reabriu BLEND; GUI não observada; não comprova Bonsai |
| FreeCAD | GeoJSON → FCStd paramétrico de três componentes → STEP e JSON de tesselação | Três IDs nativos e 108 da publicação; mm no CAD, m no contrato; quantidades de planejamento protegidas | FreeCAD 1.1.4 portátil criou/editou/salvou/reabriu, reimportou STEP e retornou malhas pela API; ver FREECAD-PARAMETRICO.md |
| IFC existente | Dataset → IFC4X3 e GLB, tabela de vínculos | Exportadores existentes; GlobalIds vinculados a atividades e cronogramas | Arquivos gerados nesta rodada; abertura/edição em Bonsai pendente |
| Cronograma existente | Dataset → MSPDI/XML e XER | Cenários calculados pelo motor atual | Arquivos gerados; ProjectLibre/P6/Project não homologados |
| Quantitativos | Dataset → CSV e XLSX | Unidades, origem e fórmulas na planilha; não infere quantidade da malha | XLSX comprovado no Excel COM16 em cópia; Calc e reingestão automática pendentes |

## API Python do contrato

`scripts/infra4d/interop.py` expõe:

- `exportar_pacote(projeto, source_app="QGIS", model_id=None, revision="r0")`: FeatureCollection com `meta.schema = infra4d.interop/1`, `source_app`, `model_id`, `revision`, `base_checksum`, `publication_checksum`, CRS e limites da geometria.
- `reconciliar_revisao(projeto, baseline, revisao)`: valida origem e produz diff sem modificar a obra.
- `aplicar_revisao(projeto, baseline, revisao)`: valida novamente e retorna **Projeto novo + relatório**. O chamador deve exigir aprovação explícita antes de publicar.
- `ErroInterop`: recusa contratual, traduzida para resposta 4xx pela rota.

Uma feição de intercâmbio representa uma atividade linear agregada; `elemento_id=atividade:<id>` não é GlobalId IFC. A identidade não muda quando a revisão muda. O GlobalId do exportador IFC continua sendo uma identidade distinta, ligada pelo identificador da atividade.

## Validações e conflitos

Baseline é regenerada a partir do Projeto canônico: cliente não pode fornecer baseline/revisão adulteradas de comum acordo. O checksum do dataset e o checksum textual da publicação permanecem protegidos. A comparação estrutural admite `0.0` e `0`, normalizados pelo JSON do navegador; jamais admite equivalência entre booleano e número.

Recusar: metadados que não sejam objeto, schema/CRS/unidades divergentes, IDs desconhecidos/duplicados/removidos, vínculos modificados, números não finitos, geometrias inválidas, quantidade inferior à executada e revisão sem identificador novo. A regra inicial é **reject** para mudança de identidade, unidade, base ou classificação; nenhuma junção silenciosa.

LineString GIS exige lon/lat finitos, 2 ou 3 coordenadas por posição e teto de vértices. Z é cota sintética local, sem datum vertical oficial. Não é levantamento para locação. A malha Blender em `properties.geometria_local_m` declara vértices locais, faces, `matrix_world`, unidade `m` e `ilustrativa: true`; conversão de visualização Z-up → Y-up é `(x,z,-y)`.

`quantidade_total` pode ser proposta para planejamento e aplicada em cópia após aprovação; `quantidade_executada`, unidade, serviço e atividade são protegidos. Mover/reescalar malha não altera quantidade de planejamento. O modelo revisado deve manter uma trilha separada da demo congelada.

## Reprodução

```powershell
$env:PYTHONPATH="scripts"
.\.venv\Scripts\python.exe -m infra4d.interop_pacote --destino output/releases/<pacote-novo>
& 'C:\Program Files\QGIS 3.40.14\bin\python-qgis-ltr.bat' scripts/infra4d/interop_qgis.py --entrada <atividades-qgis.geojson> --destino <pasta-nativa-nova>
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python scripts/infra4d/interop_blender.py -- --entrada <atividades-blender.geojson> --destino <pasta-nativa-nova>
.\.venv\Scripts\python.exe -m infra4d.interop_pacote --baseline <publicacao.geojson> --revisao <retorno.geojson> --relatorio <relatorio-novo.json>
.\.venv\Scripts\python.exe -m infra4d.interop_pacote --destino <pacote> --complementar --incluir-ifc
```

Os scripts recusam sobrescrever nativos já existentes. Executar um aplicativo pesado por vez. Testes do contrato: `tests/test_interop.py`; rota e revisões adversariais são verificadas também pelas suítes de federação/r22 do orquestrador e auditor.

## Fora da comprovação

Sem homologação por engenheiro, obra real, autoria IFC no Bonsai, planejador gratuito ou sincronização bidirecional geral. FreeCAD tem prova de um fragmento paramétrico de três peças, não importador geral de FCStd/STEP ou projeto executivo. Mudanças geométricas não redesenham automaticamente o eixo original nem a família IFC. Essa limitação deve acompanhar qualquer demonstração.
