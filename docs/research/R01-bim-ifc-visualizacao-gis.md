> **AVISO (2026-11-12):** esta primeira rodada foi escrita quase sem consulta à web. As licenças, versões e correções verificadas estão em `R04-verificacao-web.md`, seção 4, que **prevalece** sobre este arquivo em caso de divergência.

# R01 — Pesquisa: BIM/IFC, visualização 3D/4D web e GIS (ferramentas gratuitas/open source)

> Data: 2026-11-12 · Autor: agente de pesquisa · Status: **rascunho para revisão**
>
> **Aviso de método:** esta versão foi escrita a partir de conhecimento consolidado (corte de treino) **sem consulta web ao vivo nesta sessão**.
> Licenças listadas são as conhecidas publicamente e devem ser reconferidas no arquivo LICENSE do repositório antes da adoção.
> **Toda evidência de manutenção (último release/commit) está marcada "não verificado"** — conferir na PoC P0 (ver backlog).

## 1. Resumo executivo

1. A escolha do beta (FastAPI + CPM em Python puro + three.js com geometria sintética) é **adequada**: tudo permissivo (MIT/BSD), sem dependência de IFC no caminho crítico.
2. Para IFC 4.3 real (IfcAlignment/IfcRail/IfcRoad), o padrão de mercado aberto é **IfcOpenShell** (LGPL-3.0) no backend — único com suporte maduro a IFC4X3 e avaliação de alinhamento.
3. Caminho fase 2 recomendado: IfcOpenShell (servidor) → glTF/GLB (+ JSON de propriedades/GUIDs) → three.js. Evita levar parser WASM ao browser e mantém o front atual.
4. Alternativa no browser: **web-ifc / @thatopen/components** (MPL-2.0 / MIT, conferir) — boa para visualização, suporte a IFC4X3 de alinhamento ainda deve ser testado.
5. **xeokit-sdk é AGPL-3.0** (ou licença comercial): **descartar** para produto comercial fechado/SaaS sem comprar licença.
6. **Bonsai/BlenderBIM e FreeCAD BIM** (GPL/LGPL) servem como ferramentas de autoria/inspeção da equipe, não como código embutido no produto.
7. Para contexto geoespacial em escala (km de ferrovia), **CesiumJS (Apache-2.0) + 3D Tiles** é a melhor opção avaliar-depois; Cesium ion é serviço comercial (tem plano gratuito limitado).
8. Referência linear km/estaca: **PostGIS** (`ST_LineLocatePoint`, `ST_LineInterpolatePoint`, `ST_LineSubstring`) ou, local-first, **GeoPackage/SpatiaLite + Shapely** no Python — recomendação: Shapely/pyproj no beta, PostGIS só se houver servidor.
9. iTwin.js é MIT, mas OpenRail/OpenRoads/iModelHub são **comerciais** (trial); Speckle (Apache-2.0) é a melhor ponte gratuita para Revit/Civil 3D.
10. **Licença estudantil Autodesk não autoriza uso comercial** — nenhum entregável, teste com cliente ou dado de produção pode passar por ela.

## 2. Matriz de ferramentas

Legenda recomendação: **ADOTAR** agora · **AVALIAR** depois · **DESCARTAR**. Manutenção: "não verificado" em todas (ver aviso).

### 2.1 IFC 4.3

| Ferramenta | URL | Licença | Manutenção | Hipótese de uso no INFRA 4D | Limitações | Implicação comercial | Rec. |
|---|---|---|---|---|---|---|---|
| IfcOpenShell (Python/C++) | https://github.com/IfcOpenShell/IfcOpenShell | LGPL-3.0 | não verificado | Backend: ler IFC4X3, extrair IfcAlignment, gerar geometria, propriedades, vínculo GUID↔atividade | Wheels/versões por plataforma; geometria de alinhamento depende da versão; build pesado | LGPL: uso como biblioteca dinâmica/pacote Python sem modificar é compatível com produto fechado; modificações na lib devem ser publicadas | **AVALIAR** (fase 2, 1ª prioridade) |
| IfcConvert | (parte do IfcOpenShell) | LGPL-3.0 | não verificado | CLI de conversão IFC→glTF/OBJ/DAE em pipeline offline | Perde parte da semântica; controle fino exige API Python | Rodar como executável separado = baixo risco | **AVALIAR** |
| Bonsai (ex-BlenderBIM) | https://bonsaibim.org / repo IfcOpenShell | GPL-3.0 (add-on Blender) | não verificado | Ferramenta interna para inspecionar/criar IFC de teste e modelar alinhamento | Não embutível; curva de aprendizado | GPL: não incorporar ao produto; uso como ferramenta é livre | **ADOTAR** como ferramenta de bancada |
| ifc-pipeline | https://github.com/AECgeeks/ifc-pipeline | conferir (não verificado) | não verificado | Referência de arquitetura de fila de conversão IFC→glTF/XKT | Projeto de nicho; pode estar parado | Depende da licença | **AVALIAR** só como referência |
| web-ifc | https://github.com/ThatOpen/engine_web-ifc | MPL-2.0 (conferir) | não verificado | Parser IFC em WASM no browser/Node | Cobertura IFC4X3 de alinhamento a testar | MPL: arquivos modificados ficam abertos; uso como dependência ok | **AVALIAR** |
| That Open Engine (@thatopen/components, fragments) | https://github.com/ThatOpen | MIT (conferir por pacote) | não verificado | Viewer BIM sobre three.js, formato "fragments" para modelos grandes | APIs mudaram muito entre versões; acoplamento ao formato fragments | Permissivo | **AVALIAR** |
| IFC.js (legado, web-ifc-three/viewer) | https://github.com/IFCjs | MIT/MPL | descontinuado em favor de That Open (conhecimento, não verificado) | — | Legado | — | **DESCARTAR** |
| xBIM Toolkit (.NET) | https://github.com/xBimTeam | CDDL-1.0 | não verificado | Só se houver backend .NET | Suporte IFC4X3 incerto; stack .NET fora da arquitetura | CDDL (copyleft por arquivo) | **DESCARTAR** |
| xeokit-sdk | https://github.com/xeokit/xeokit-sdk | AGPL-3.0 ou comercial | não verificado | Viewer de alta performance (XKT) | Licença | AGPL obriga liberar código do serviço inteiro a usuários de rede | **DESCARTAR** (salvo compra de licença) |
| FreeCAD (BIM Workbench) | https://www.freecad.org | LGPL-2.0+ | não verificado | Inspeção/edição de IFC, alternativa desktop | Alinhamento/corredor fraco | Uso como ferramenta livre | **AVALIAR** (bancada) |

### 2.2 Visualização 3D/4D web

| Ferramenta | URL | Licença | Manutenção | Uso | Limitações | Comercial | Rec. |
|---|---|---|---|---|---|---|---|
| three.js | https://github.com/mrdoob/three.js | MIT | não verificado | Viewer 4D do beta (geometria sintética, cor por status/data) | Sem georreferência nativa; precisão float32 em coordenadas UTM → usar origem local | Livre | **ADOTAR** |
| CesiumJS + 3D Tiles | https://github.com/CesiumGS/cesium | Apache-2.0 | não verificado | Corredor de centenas de km sobre terreno/imagem; 4D via `clock` | Cesium ion (tiling/terreno) é SaaS comercial com tier grátis; tiling próprio exige ferramentas (ex.: 3d-tiles-tools, py3dtiles) | Livre (biblioteca) | **AVALIAR** fase 2/3 |
| deck.gl | https://github.com/visgl/deck.gl | MIT | não verificado | Camadas analíticas 2D/2.5D (heatmap de avanço por km, mapa de progresso) | Não é viewer BIM | Livre | **AVALIAR** |
| iTwin.js | https://github.com/iTwin/itwinjs-core | MIT | não verificado | Viewer de iModels | Útil de fato só com iModelHub/iTwin Platform (serviço Bentley pago) | Lib livre; plataforma paga | **DESCARTAR** no beta |
| Bentley OpenRail / OpenRoads / SYNCHRO | bentley.com | Proprietária (trial) | n/a | Referência funcional | Comercial | Requer licença | **DESCARTAR** como dependência |
| Speckle | https://github.com/specklesystems | Apache-2.0 (server/SDKs; conferir conectores) | não verificado | Ponte de dados Revit/Civil 3D/Navisworks → objetos JSON → backend | Servidor self-host é infra extra; conectores dependem do software Autodesk licenciado | Permissivo | **AVALIAR** fase 2 |

### 2.3 GIS / referência linear

| Ferramenta | URL | Licença | Manutenção | Uso | Limitações | Comercial | Rec. |
|---|---|---|---|---|---|---|---|
| Shapely + pyproj | https://github.com/shapely/shapely · https://github.com/pyproj4/pyproj | BSD-3 / MIT | não verificado | km/estaca no Python: `line.project(pt)` / `line.interpolate(d)`; conversão SIRGAS 2000/UTM | Sem banco espacial | Livre | **ADOTAR** |
| GeoPackage | https://www.geopackage.org | Padrão OGC aberto | n/a | Arquivo local-first do eixo e trechos | — | Livre | **ADOTAR** |
| GDAL/OGR | https://github.com/OSGeo/gdal | MIT/X | não verificado | Importar SHP/KML/DXF/GPKG do cliente | Wheels no Windows podem ser chatos | Livre | **ADOTAR** (via pacote pronto) |
| SpatiaLite | https://www.gaia-gis.it | MPL/GPL/LGPL tri-licença | não verificado | SQL espacial em SQLite local | Extensão nativa no Windows | Escolher MPL | **AVALIAR** |
| PostGIS | https://postgis.net | GPL-2.0 | não verificado | `ST_LineLocatePoint`, `ST_LineInterpolatePoint`, `ST_LineSubstring` em versão servidor | Exige PostgreSQL | GPL não contamina app que só se conecta via SQL | **AVALIAR** (versão servidor) |
| QGIS | https://qgis.org | GPL-2.0+ | não verificado | Bancada: validar eixo, estaqueamento, exportar GPKG | Não embutir | Ferramenta livre | **ADOTAR** (bancada) |

### 2.4 Alternativas gratuitas a Revit / Civil 3D / Navisworks / OpenRail

| Necessidade | Opção gratuita | Status | Observação |
|---|---|---|---|
| Alinhamento/corredor | FreeCAD + Bonsai; Blender + Bonsai (alinhamento IFC4X3 em evolução) | open source | Não substitui Civil 3D em produtividade; suficiente para IFC de teste |
| Coordenação/clash | Bonsai (clash via IfcClash), IfcOpenShell | open source | Sem equivalência total ao Navisworks |
| 4D | Bonsai (sequenciamento/IfcTask, animação 4D) | open source | Bom para PoC de vínculo atividade↔elemento |
| OpenRoads/OpenRail, SYNCHRO 4D, Civil 3D, Navisworks | — | **comercial/trial** | Uso só com licença válida |

### 2.5 Conectores e automação Autodesk

| Via | Licença/condição | Uso | Rec. |
|---|---|---|---|
| Revit/Civil 3D/Navisworks API .NET | Exige licença do software; SDK proprietário | Exportar elementos+GUID+parâmetros para JSON | **AVALIAR** (cliente com licença) |
| Dynamo | Open source (Dynamo core, Apache-2.0 — não verificado); roda dentro do Revit/Civil 3D licenciado | Scripts de exportação sem compilar | **AVALIAR** |
| pyRevit | GPL-3.0 (não verificado) | Automação interna | Ferramenta, não embutir |
| Speckle connectors | Apache-2.0 (conferir) | Ponte padrão | **AVALIAR** |
| Export IFC nativo (IFC4X3 no Revit/Civil 3D) | Recurso do produto | **Caminho preferido**: produto recebe IFC, não depende de API | **ADOTAR** como formato de entrada |

**Licença educacional Autodesk:** proibido uso comercial. Modelos gerados nela podem carregar marca educacional. Não usar em demo com cliente, piloto pago nem dataset de produção.

## 3. Riscos de licença (GPL/AGPL)

| Risco | Componente | Gravidade | Mitigação |
|---|---|---|---|
| AGPL obriga liberar o código de todo serviço acessado por rede | xeokit-sdk | **Alta** | Não usar; ou comprar licença comercial |
| GPL contamina distribuição de binário que linka a lib | Bonsai, QGIS, pyRevit, PostGIS (se linkado) | Média | Usar só como ferramentas externas; PostGIS via SQL não contamina |
| LGPL: obrigações ao modificar/linkar estaticamente | IfcOpenShell, FreeCAD | Baixa | Usar pacote oficial sem modificar; permitir substituição da lib; registrar no NOTICE |
| MPL/CDDL copyleft por arquivo | web-ifc, xBIM, SpatiaLite | Baixa | Não modificar arquivos da lib, ou publicar modificações |
| Plataforma "grátis" com serviço pago | Cesium ion, iTwin Platform, Speckle hosted | Média (custo/lock-in) | Preferir self-host/arquivos locais (local-first) |
| Licença educacional | Autodesk Student | **Alta** (jurídica) | Proibir no pipeline; exigir licença comercial do cliente |

Ação: manter `THIRD_PARTY_LICENSES` / inventário de dependências por release (pip-licenses, license-checker).

## 4. Avaliação da arquitetura do beta e recomendação de stack por fase

**Beta (atual) — mantida.** FastAPI + CPM puro + three.js sintético é correta: zero risco de licença, sem dependência pesada, prova o valor (CPM independente + 4D) antes de pagar o custo do IFC. Cuidados: (a) usar **origem local** (subtrair coordenada base) para evitar tremor em float32 com UTM; (b) modelar desde já um `element_id` estável (futuro GlobalId IFC) e a tabela atividade↔elemento; (c) estaca/km via Shapely.

| Fase | Backend | Front | Dados/GIS |
|---|---|---|---|
| Beta | Python 3.13, FastAPI, CPM próprio, Shapely/pyproj | three.js (MIT), geometria sintética por trecho km | GeoPackage/JSON local |
| Fase 2 (IFC real) | + IfcOpenShell: IFC4X3 → GLB por trecho + JSON (GlobalId, Pset, estação do IfcAlignment) com cache | three.js `GLTFLoader` (+ Draco/meshopt); avaliar @thatopen/fragments se modelos > ~1 GB | Eixo extraído do IfcAlignment → linha de referência linear |
| Fase 3 (escala/geo) | Tiling 3D Tiles (py3dtiles ou 3d-tiles-tools, conferir licenças) | CesiumJS (Apache) para corredor georreferenciado; deck.gl para analítica | PostGIS se houver multiusuário/servidor |
| Integração | Speckle self-host ou exportador Dynamo/.NET no ambiente licenciado do cliente | — | — |

Opção web-ifc no browser: útil para "abrir IFC sem servidor" (local-first puro), mas recomenda-se o backend como caminho principal porque IfcOpenShell tem o suporte mais completo a IFC4X3/alinhamento e permite pré-processar e cachear.

## 5. Backlog de provas de conceito

| ID | PoC | Critério de sucesso | Prioridade |
|---|---|---|---|
| P0 | Verificar licenças e últimos releases desta matriz (GitHub releases/LICENSE) | Coluna "não verificado" substituída por datas/links | Alta |
| P1 | three.js: corredor sintético de 100 km com origem local, colorido por status CPM numa data | 60 fps em notebook comum; sem jitter | Alta (beta) |
| P2 | Shapely: ponto↔km/estaca num eixo GPKG em SIRGAS 2000/UTM | Erro < 1 cm vs. cálculo de referência | Alta (beta) |
| P3 | IfcOpenShell: abrir arquivos-exemplo IFC4X3 da buildingSMART (rail/road), listar IfcAlignment e segmentos | Extração de estações e geometria do eixo | Média |
| P4 | IfcOpenShell → GLB + JSON de GlobalId → three.js com vínculo a atividade | Clique no elemento mostra atividade/folga | Média |
| P5 | web-ifc/@thatopen no browser com o mesmo IFC | Comparar tempo de carga/memória com P4 | Baixa |
| P6 | CesiumJS + 3D Tiles self-host do corredor | Carrega sem Cesium ion | Baixa |
| P7 | Speckle self-host recebendo modelo de Civil 3D (licença comercial do cliente) | Objetos com IDs estáveis no backend | Baixa |
| P8 | Inventário automático de licenças no CI (pip-licenses / license-checker) | Falha se aparecer AGPL/GPL embutida | Média |
