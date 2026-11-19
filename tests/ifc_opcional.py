"""IFC opcional nos testes (ADR-0002; ver requirements.txt).

Sem ``ifcopenshell`` instalado, o módulo ``infra4d.ifc`` não carrega: as rotas ``/api/ifc/*`` não são
registradas, ``/api/orcamento/classificacao-ifc`` responde 503 (documentado no OpenAPI) e o
``numeros_demo`` não produz os números de IFC. O ``requirements.txt`` promete que, nesse caso, os
testes de IFC dão SKIP e o resto da API segue testado.

Este módulo é o único lugar que decide isso:
- ``SEM_IFC``: verdadeiro quando o ifcopenshell não está instalado;
- ``requer_ifc``: marca de skip com motivo explícito, para testes (ou casos parametrizados) que só
  fazem sentido com o IFC.

Com o ifcopenshell instalado (ambiente do requirements.txt), nada muda: toda asserção roda inteira.
"""

import importlib.util

import pytest

SEM_IFC = importlib.util.find_spec("ifcopenshell") is None

MOTIVO = ("requer ifcopenshell (dependência do requirements.txt, não instalada neste interpretador); "
          "sem ele as rotas /api/ifc/* não existem e classificacao-ifc responde 503 — ADR-0002")

requer_ifc = pytest.mark.skipif(SEM_IFC, reason=MOTIVO)


def eh_rota_ifc(caminho: str) -> bool:
    """Rota que só existe (ou só responde 2xx/4xx) com o exportador IFC carregado."""
    return caminho.startswith("/api/ifc/") or caminho.startswith("/api/orcamento/classificacao-ifc")
