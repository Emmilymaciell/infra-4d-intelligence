"""Tipo da obra — helper ÚNICO, sem padrão silencioso (P8 do BACKLOG).

``meta.tipo_obra`` é DECLARADO no dataset ("ferrovia" ou "rodovia"). Ausente, vazio, não-texto ou desconhecido
é ``ErroTipoObra`` (ValueError): nenhum módulo pode "assumir ferrovia". O ``api.py`` converte o erro em 422
com a mensagem, em qualquer rota.
"""

from __future__ import annotations

TIPOS_OBRA = ("ferrovia", "rodovia")


class ErroTipoObra(ValueError):
    """``meta.tipo_obra`` ausente, vazio, não-texto ou desconhecido."""


def tipo_obra(dados_ou_projeto) -> str:
    """Tipo declarado da obra. Aceita os ``dados`` (dict) ou um objeto com ``.dados`` (``cenarios.Projeto``)."""
    dados = getattr(dados_ou_projeto, "dados", dados_ou_projeto)
    meta = dados.get("meta") if isinstance(dados, dict) else None
    if not isinstance(meta, dict):
        raise ErroTipoObra("obra sem bloco 'meta': tipo de obra não declarado (não se assume 'ferrovia')")
    t = meta.get("tipo_obra")
    if not isinstance(t, str) or not t.strip():
        raise ErroTipoObra(f"obra sem meta.tipo_obra declarado ({t!r}); use um de {', '.join(TIPOS_OBRA)} "
                           "(não se assume 'ferrovia')")
    if t.strip() not in TIPOS_OBRA:
        raise ErroTipoObra(f"meta.tipo_obra desconhecido: {t!r}; use um de {', '.join(TIPOS_OBRA)}")
    return t.strip()
