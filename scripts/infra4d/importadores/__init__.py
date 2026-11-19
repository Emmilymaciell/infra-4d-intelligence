"""Adaptadores de cronograma (biblioteca padrão, sem dependência nova).

- ``mspdi``: MS Project XML (MSPDI), exportar e importar;
- ``xer``: Primavera P6 XER, importar (leitura);
- ``rotas``: router FastAPI ``/api/cronograma`` (registrado pelo ``api.py``).

Compatibilidade com MS Project / P6 reais NÃO é alegada: validado por ida e volta
com o próprio exportador e por fixtures sintéticas escritas à mão conforme a
especificação pública. Ver ``LIMITACOES_MSPDI`` e ``LIMITACOES_XER``.
"""

from .comum import ErroImportacao
from .mspdi import LIMITACOES_MSPDI, exportar_mspdi, importar_mspdi
from .xer import LIMITACOES_XER, importar_xer

__all__ = ["ErroImportacao", "exportar_mspdi", "importar_mspdi", "importar_xer",
           "LIMITACOES_MSPDI", "LIMITACOES_XER"]
