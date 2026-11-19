"""INFRA 4D INTELLIGENCE — núcleo do beta.

Módulos:
- calendario: dias úteis, feriados, aritmética de datas em tempo de trabalho.
- motor: CPM independente (FS/SS/FF/SF, lags, restrições, data de status, folgas).
- cenarios: dados da obra -> entradas do motor (produtividade -> duração),
  cenários construtora x independente, simulação e explicação da mudança.
- dados_sinteticos: gerador determinístico da ferrovia FICTÍCIA de demonstração.
- api: FastAPI que serve o motor e a interface web.

Todos os dados deste beta são SINTÉTICOS.
"""

__version__ = "0.2.0"
