"""Atribuição do erro de previsão por frente (backtest, P5 do BACKLOG).

Para uma data passada ``d`` e um marco: a previsão INDEPENDENTE feita em ``d`` (fotografia da obra em
``d``, ``tendencia.fotografia``) erra contra a realidade simulada do gerador (``backtest.realidade_da_obra``).
Para cada frente (lote, serviço) da cadeia do marco, refaz-se a previsão em ``d`` trocando SÓ a
produtividade dessa frente pela VERDADEIRA da realidade simulada (cenário simulado com ajuste por
atividade, sobre a fotografia) e mede-se quanto o erro cai. O que as frentes não explicam sozinhas é o
RESÍDUO DE INTERAÇÃO, declarado (como na comparação de revisões): troca de todas juntas − soma das isoladas.

Definições (declaradas também na resposta):
- erro = término previsto do marco − término na realidade simulada, em dias corridos (negativo = a previsão
  achava que acabaria ANTES);
- produtividade verdadeira de uma atividade = produtividade planejada × fator de desempenho do par
  (lote, serviço) que o gerador usou, lido do GABARITO pelo acessor único ``sintetico_comum.gabarito`` (P9:
  fora do dataset publicado; arquivo adulterado, obra não fictícia ou gerador desconhecido → recusado);
- frentes candidatas = pares (lote, serviço) das atividades por quantidade, não concluídas em ``d``, na cadeia
  determinante do marco na previsão independente E na previsão com TODAS as produtividades verdadeiras
  (a cadeia real pode passar por outra frente);
- redução = |erro antes| − |erro com a frente corrigida|.

Só leitura de ``tendencia``, ``backtest`` e ``cenarios``; nenhum dado é gravado. Obra sem realidade simulada
(não fictícia ou sem o gerador) é recusada.

Custo: 2 + nº de frentes + 1 execuções do motor sobre a fotografia (teto ``MAX_FRENTES``); tempo medido na saída.
"""

from __future__ import annotations

import time

from .calendario import iso, ordinal
from .cenarios import Ajuste, Projeto, executar

MAX_FRENTES = 60


class ErroAtribuicao(ValueError):
    """Parâmetro inválido ou obra sem realidade simulada."""


def _cadeia_do_marco(res: dict, marco: str) -> list[str]:
    cadeia, atual, vistos = [], marco, set()
    while atual and atual not in vistos:
        vistos.add(atual)
        cadeia.append(atual)
        atual = res["atividades"][atual].get("determinante")
    return list(reversed(cadeia))


def _frentes(foto: Projeto, cadeia: list[str]) -> list[tuple[str, str]]:
    out = []
    for aid in cadeia:
        a = foto.atividades[aid]
        if a.get("tipo", "tarefa") != "tarefa" or not a.get("quantidade_total") or a.get("status") == "concluida":
            continue
        k = (a.get("lote_id"), a.get("servico_id"))
        if k not in out:
            out.append(k)
    return out


def _ajustes(foto: Projeto, fatores: dict, frentes) -> list[Ajuste]:
    alvo = set(frentes)
    out = []
    for a in foto.dados["atividades"]:
        k = (a.get("lote_id"), a.get("servico_id"))
        if k in alvo and a.get("quantidade_total") and a.get("status") != "concluida":
            f = fatores.get(f"{k[0]}/{k[1]}")
            if f is None:
                raise ErroAtribuicao(f"fator de desempenho ausente para {k[0]}/{k[1]}")
            out.append(Ajuste(produtividade=a["produtividade_planejada"] * f, atividade_id=a["id"]))
    return out


def _fatores_verdadeiros(dados: dict) -> dict:
    """Fatores verdadeiros do GABARITO (P9: fora do dataset publicado), pelo acessor ÚNICO
    ``sintetico_comum.gabarito``, que confere marca fictícia, gerador, semente e o arquivo publicado contra o
    gerador (adulterado → recusado). Indisponível ou malformado → ``ErroAtribuicao`` (422)."""
    import math

    from .sintetico_comum import ErroGabarito, gabarito

    try:
        f = gabarito(dados).get("fatores_desempenho_simulados")
    except ErroGabarito as e:
        raise ErroAtribuicao(f"sem gabarito para esta obra: {e}") from None
    if not isinstance(f, dict) or not f:
        raise ErroAtribuicao("gabarito sem fatores de desempenho utilizáveis")
    for k, v in f.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            raise ErroAtribuicao(f"gabarito malformado: fator de {k} = {v!r} (esperado número > 0)")
    return f


def atribuir(projeto: Projeto, marco: str = "M-FIM", data: str | None = None) -> dict:
    from .backtest import realidade_da_obra
    from .tendencia import ErroTendencia, fotografia

    t0 = time.perf_counter()
    dados = projeto.dados
    if marco not in projeto.atividades or projeto.atividades[marco].get("tipo") != "marco_termino":
        raise ErroAtribuicao(f"marco de término desconhecido: {marco!r}")
    if not data:
        raise ErroAtribuicao("informe a data passada (AAAA-MM-DD)")
    try:
        d = ordinal(data)
    except ValueError:
        raise ErroAtribuicao(f"data inválida {data!r} (use AAAA-MM-DD)") from None
    if not (projeto.inicio_projeto < d < projeto.data_status):
        raise ErroAtribuicao(f"a data deve estar entre o início do projeto ({iso(projeto.inicio_projeto)}) e a "
                             f"data de status ({iso(projeto.data_status)}), exclusive")
    real, motivo = realidade_da_obra(dados)
    if real is None:
        raise ErroAtribuicao(f"sem realidade simulada para esta obra: {motivo}")
    fatores = _fatores_verdadeiros(dados)
    try:
        foto = Projeto(fotografia(dados, d))
    except ErroTendencia as e:
        raise ErroAtribuicao(str(e)) from None
    t_real = ordinal(real[marco])
    n_motor = 0

    def termino(ajustes):
        nonlocal n_motor
        n_motor += 1
        r = executar(foto, "simulado" if ajustes else "independente", ajustes or None)
        return r, ordinal(r["atividades"][marco]["termino"])

    res0, t0m = termino([])
    erro0 = t0m - t_real
    # cadeia real: todas as frentes ainda abertas com a produtividade verdadeira
    abertas = sorted({(a.get("lote_id"), a.get("servico_id")) for a in foto.dados["atividades"]
                      if a.get("quantidade_total") and a.get("status") != "concluida"
                      and f"{a.get('lote_id')}/{a.get('servico_id')}" in fatores})
    res_tudo, t_tudo = termino(_ajustes(foto, fatores, abertas))
    cadeias = {"independente": _cadeia_do_marco(res0, marco), "com_todas_verdadeiras": _cadeia_do_marco(res_tudo, marco)}
    frentes = _frentes(foto, cadeias["independente"])
    for k in _frentes(foto, cadeias["com_todas_verdadeiras"]):
        if k not in frentes:
            frentes.append(k)
    if len(frentes) > MAX_FRENTES:
        raise ErroAtribuicao(f"{len(frentes)} frentes candidatas: acima do teto de {MAX_FRENTES} execuções")
    linhas = []
    for k in frentes:
        _, tk = termino(_ajustes(foto, fatores, [k]))
        ek = tk - t_real
        linhas.append({"lote_id": k[0], "servico_id": k[1], "fator_verdadeiro": fatores.get(f"{k[0]}/{k[1]}"),
                       "erro_com_a_frente_corrigida": ek, "variacao_do_erro": ek - erro0,
                       "reducao_dias": abs(erro0) - abs(ek),
                       "na_cadeia": [c for c, ids in cadeias.items() if k in _frentes(foto, ids)]})
    linhas.sort(key=lambda x: (-x["reducao_dias"], x["lote_id"] or "", x["servico_id"] or ""))
    _, t_juntas = termino(_ajustes(foto, fatores, frentes)) if frentes else (None, t0m)
    erro_juntas = t_juntas - t_real
    soma = sum(x["variacao_do_erro"] for x in linhas)
    return {
        "marco": marco, "data": iso(d), "data_status_atual": iso(projeto.data_status),
        "termino_previsto": iso(t0m), "termino_realidade_simulada": real[marco],
        "erro_dias": erro0,
        "frentes": linhas,
        "todas_as_frentes_juntas": {"erro_dias": erro_juntas, "variacao_do_erro": erro_juntas - erro0},
        "residuo_interacao": (erro_juntas - erro0) - soma,
        "todas_as_abertas_verdadeiras": {"erro_dias": t_tudo - t_real,
                                         "nota": "todas as frentes abertas com a produtividade verdadeira (não só as da cadeia)"},
        "cadeias": cadeias,
        "regras": {
            "erro": "término previsto − término na realidade simulada, dias corridos (negativo = previsão otimista)",
            "produtividade_verdadeira": "planejada × fator de desempenho do gerador (gabarito do gerador, sintetico_comum.gabarito)",
            "candidatas": "pares (lote, serviço) por quantidade, abertos em d, na cadeia do marco (independente e com "
                          "todas as produtividades verdadeiras)",
            "residuo": "variação com todas as candidatas juntas − soma das variações isoladas",
            "aviso": "realidade SINTÉTICA: atribui o erro contra o mundo que o gerador inventou, não contra uma obra real",
        },
        "custo": {"execucoes_do_motor": n_motor, "segundos": round(time.perf_counter() - t0, 3),
                  "teto_frentes": MAX_FRENTES},
    }
