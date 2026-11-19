# ADR-0002 — Arquitetura do beta: local-first, Python + web estática, sem dependência comercial

- **Data:** 2026-11-12
- **Status:** Aceita (beta). Reavaliar ao entrar dado real ou IFC real.

## Contexto

A missão pede um vertical slice executável: alterar a produtividade de um serviço tem que recalcular a duração,
propagar pela rede, mudar a previsão de término, o painel e o 3D/4D. Tudo gratuito no início, sem APIs pagas
e sem prender o motor a Revit, Navisworks, P6 ou Project. A máquina tem Python 3.13 e Node 24.

## Decisão

| Camada | Escolha | Licença | Por quê |
|---|---|---|---|
| Motor de planejamento | Python puro, próprio (`scripts/infra4d/motor.py`, `calendario.py`) | proprietária (do projeto) | Ver ADR-0003. Sem dependência: testável e auditável linha a linha |
| Cenários e produtividade | `cenarios.py` | idem | Produtividade → duração com memória de cálculo por atividade |
| API | FastAPI + uvicorn | MIT / BSD-3 | Contrato HTTP documentado (OpenAPI em `/docs`) e testável com TestClient |
| Persistência no beta | JSON versionado em `examples/synthetic/` | — | Dado sintético e determinístico. Banco entra com o dado real (SQLite/GeoPackage → PostGIS) |
| Interface | HTML + ES modules sem build, three.js vendorizado em `web/vendor/` | MIT | Roda offline, sem toolchain Node no caminho crítico |
| Geometria | Sintética, gerada no navegador a partir do eixo + atividades | — | Não há IFC viável no beta. IFC 4.3 na fase 2 (ver abaixo) |

Contratos entre módulos:

- **Elemento BIM ↔ atividade:** `elemento_id = <atividade_id>-E<nn>`, uma peça por km. A hierarquia
  `ferrovia → lote → segmento → serviço → atividade → elemento` está codificada nos ids
  (`L2-S03-LAS-E04`). Num IFC real, o `GlobalId` substitui o `-Enn` e uma tabela de vínculo ocupa o lugar da convenção.
- **Cronograma importado ↔ motor:** o motor recebe `AtividadeCPM` e `Relacao`, sem saber de onde vieram.
  Importadores MSPDI/XER são adaptadores (backlog).
- **Medição ↔ produtividade:** os boletins semanais (`medicoes`) são a única fonte da produtividade efetiva.
- **API ↔ visualizador:** `/api/estado4d?data=&cenario=` devolve a fração por atividade. O 3D não recalcula
  cronograma, só pinta.

## Alternativas consideradas

- **xeokit-sdk** (viewer BIM forte): AGPL-3.0, que obrigaria a abrir o código de todo o serviço. Descartado como dependência.
- **iTwin.js / OpenRail / SYNCHRO (Bentley):** serviços e produtos pagos. Ficam fora do núcleo.
- **Banco PostGIS já no beta:** exige instalar serviço no sistema, o que precisa de autorização. Sem ganho com dado sintético.
- **React/Vite:** traria toolchain e build sem ganho para um único desenvolvedor no beta.

## Consequências

- O beta roda com `.\bootstrap.ps1` seguido de `.\run-beta.ps1`. Não usa rede nem serviço externo.
- Fase 2 (IFC): IfcOpenShell (LGPL-3.0, usado sem modificação) no backend lê IFC 4.3 e gera GLB por trecho
  mais o vínculo GlobalId ↔ atividade. A web troca a geometria sintética por GLTFLoader. As licenças estão sendo
  verificadas em `docs/research/R04`.
- Licenças GPL/AGPL só entram como ferramenta de trabalho (QGIS, Bonsai, FreeCAD), nunca embutidas no produto.
