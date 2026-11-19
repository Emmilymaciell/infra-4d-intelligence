"""Campo ``simulacao_do_usuario`` das rotas de análise que usam o cenário INDEPENDENTE de propósito.

Clima, aceleração, recuperação, riscos e Earned Schedule partem da produtividade MEDIDA (cenário independente),
não da simulação corrente do usuário (``POST /api/simulacao``). Sem este aviso, quem simula e abre essas abas
acha que a tela "não atualizou". O texto diz que a simulação não foi aplicada, por quê, e se há uma ativa.
"""

from __future__ import annotations


def simulacao_do_usuario(est) -> str:
    ajustes = list(getattr(est, "ajustes", None) or [])
    ativa = (f"há {len(ajustes)} ajuste(s) de simulação ativo(s) nesta obra; " if ajustes
             else "não há simulação ativa nesta obra; ")
    return ("não aplicada: " + ativa + "esta análise usa o cenário independente (produtividade medida), "
            "de propósito, para não misturar hipótese do usuário com a previsão de referência")


def com_aviso(saida: dict, est) -> dict:
    """Cópia rasa da resposta com o campo (o cache guarda a resposta SEM o aviso, que depende do estado atual)."""
    return {**saida, "simulacao_do_usuario": simulacao_do_usuario(est)}
