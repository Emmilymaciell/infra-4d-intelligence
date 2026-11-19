"""Interoperabilidade IFC 4.3 (protótipo, fase 2 do ADR-0002).

Depende de ``ifcopenshell`` (LGPL-3.0-or-later, usado sem modificação, como pacote
Python dinâmico). Ver ``docs/research/R07-experimento-ifc.md``.

- ``exportar``: base sintética → arquivo IFC4X3_ADD2 (estrutura espacial, IfcAlignment,
  elementos por peça com Pset ``INFRA4D_Vinculo`` e cronograma IfcTask/IfcWorkSchedule).
- ``importar``: IFC → tabela de vínculo elemento ↔ atividade, verificação contra o projeto
  e malha triangulada (JSON) ou GLB.
- ``rotas``: router FastAPI ``/api/ifc`` (não é ligado sozinho ao ``api.py``).
"""

PSET_VINCULO = "INFRA4D_Vinculo"
SCHEMA = "IFC4X3_ADD2"
