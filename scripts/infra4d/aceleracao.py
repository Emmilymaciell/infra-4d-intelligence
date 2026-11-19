"""Aceleração com custo (crashing): equipes extras nas frentes críticas para cumprir um prazo pelo MENOR custo
adicional FICTÍCIO — o trade-off tempo × custo clássico, guloso.

Modelo de custo (declarado; preços do ``orcamento.py``, que este módulo só LÊ):

- custo da equipe·dia do serviço = produtividade (un/equipe·dia, a do cenário independente)
  × (mão de obra + equipamento do custo direto unitário) × (1 + BDI). Material e transporte acompanham a
  QUANTIDADE e não mudam com o número de equipes; serviço sem composição não é acelerável (declarado);
- +k equipes numa atividade custam ``custo_eq_dia × [max(0, n'·D' − n·D) + k × MOBILIZACAO_EQUIPE_DIAS]``:
  os equipe·dias a mais que o arredondamento da duração deixa ociosos (PISO 0: se a equipe extra elimina
  ociosidade da base, isso não vira "economia" — revisão r16), mais a mobilização/desmobilização de cada
  equipe extra (10 equipe·dias, fictício). Sem a mobilização o modelo linear daria aceleração GRÁTIS (a
  quantidade não muda, só é dividida entre mais equipes). Todo passo custa > 0: curva estritamente crescente.
- PLATÔ do arredondamento (r16): quando +1 equipe não reduz a duração (ex.: 5 → 6 equipes em 100 un a
  10 un/eq·dia continua 2 dias), o passo da frente é o MENOR k <= limite que reduz (5 → 10).

Algoritmo (guloso clássico, NÃO ótimo global):

1. Cenário independente com equipes ajustáveis; duração = ⌈remanescente ÷ (produtividade × equipes)⌉
   (a MESMA conta de ``cenarios.montar_entrada``; em andamento, no mínimo 1 dia).
2. Conjunto determinante do término (todas as predecessoras que empatam, recursivamente). Candidatas:
   atividades por quantidade, em aberto, com composição, abaixo de equipes base + ``limite_extra`` (e do
   teto de 20 da API) e cuja duração cai com +1 equipe.
3. Para cada candidata, +1 equipe sozinha: ganho (dias corridos no término) e custo. Fica a de MENOR custo
   por dia ganho (desempate: menor custo, id).
4. Se nenhuma sozinha antecipa (caminhos paralelos empatados), passo COMPOSTO: aplica a candidata mais
   barata, recalcula, e repete com o novo conjunto determinante até o término cair — encurta um em cada
   caminho.
5. Repete até cumprir o prazo, faltar candidata ("limite de equipes") ou estourar ``max_passos``/tempo.

Cada passo vira um ponto da curva tempo × custo (término estritamente decrescente, custo estritamente
crescente). Os ajustes finais são ``[{"atividade_id", "equipes"}]``, aplicáveis em ``POST /api/simulacao``;
o resultado é VERIFICADO recalculando o cenário ``simulado`` com eles.

Diferença para ``recuperacao.py``: a recuperação pergunta "quanto cada frente precisa RENDER" (produtividade
contínua, esforço igualado, viabilidade contra a melhor semana medida, sem custo); a aceleração pergunta
"quantas EQUIPES inteiras comprar, e onde, pelo menor custo", aceita a produtividade medida como está e
devolve a curva tempo × custo.
"""

from __future__ import annotations

import math
import time

from .calendario import iso, ordinal
from .cenarios import Ajuste, Projeto, executar, montar_entrada
from .motor import calcular

MOBILIZACAO_EQUIPE_DIAS = 10
LIMITE_EXTRA_PADRAO = 2
EQUIPES_MAX = 20
TEMPO_MAX_S = 60.0


def custo_equipe_dia(projeto: Projeto, servico: str | None, produtividade: float) -> float | None:
    return None if (c := _custo(projeto, servico)) is None else produtividade * c


def bdi(projeto: Projeto) -> float:
    """BDI da obra no orçamento (``bdi_da_obra`` por tipo; versões antigas: ``BDI_FICTICIO``)."""
    from . import orcamento as O
    f = getattr(O, "bdi_da_obra", None)
    return f(O.tipo_obra(projeto)) if f else O.BDI_FICTICIO


def _custo(projeto: Projeto, servico: str | None) -> float | None:
    """(mão de obra + equipamento) do custo direto UNITÁRIO × (1 + BDI); None sem composição."""
    from . import orcamento as O
    comp = O.COMPOSICOES.get(O.tipo_obra(projeto), {}).get(servico)
    if comp is None:
        return None
    cd = comp["custo_direto"]
    return (cd["mao_de_obra"] + cd["equipamento"]) * (1 + bdi(projeto))


def _duracao(rem: float, prod: float, n: int, em_andamento: bool) -> int:
    d = math.ceil(rem / (prod * n) - 1e-9) if rem > 0 else 0
    return max(d, 1) if em_andamento else d


def acelerar(projeto: Projeto, prazo: str | None = None, limite_extra: int = LIMITE_EXTRA_PADRAO,
             custos: dict[str, float] | None = None, max_passos: int = 500,
             tempo_max_s: float = TEMPO_MAX_S) -> dict:
    t_ini = time.perf_counter()
    if isinstance(limite_extra, bool) or not isinstance(limite_extra, int) or not 1 <= limite_extra <= EQUIPES_MAX:
        raise ValueError(f"limite_extra deve ser inteiro entre 1 e {EQUIPES_MAX}")
    if prazo is None or (isinstance(prazo, str) and not prazo.strip()):  # vazio = padrão (r16)
        prazo = projeto.dados["meta"].get("termino_linha_base") or executar(projeto, "linha_base")["termino"]
    try:
        t_prazo = ordinal(prazo)
    except (TypeError, ValueError):
        t_prazo = None
    if t_prazo is None:
        raise ValueError("prazo inválido (use AAAA-MM-DD)")
    if custos is None:
        # o custo vem do orçamento, que EXIGE meta.tipo_obra (sem padrão "ferrovia"): erro claro já na entrada,
        # nunca uma resposta parcial (ErroOrcamento é ValueError -> 422 na rota)
        from . import orcamento as O
        try:
            O.tipo_obra(projeto)
        except O.ErroOrcamento as e:
            raise O.ErroOrcamento(f"aceleração sem custo: {e}. Declare meta.tipo_obra ou passe 'custos'") from None

    ativs, rels, mem = montar_entrada(projeto, "independente")
    por_id = {a.id: a for a in ativs}
    base = {a.id: a.duracao for a in ativs}
    info = {}
    sem_custo = []
    for a in ativs:
        m = mem[a.id]
        if m.get("regra") != "quantidade" or a.status == "concluida" or a.duracao <= 0:
            continue
        serv = projeto.atividades[a.id].get("servico_id")
        ce = (custos or {}).get(serv) if custos is not None else custo_equipe_dia(projeto, serv, m["produtividade"])
        if ce is None:
            sem_custo.append(a.id)
            continue
        n0 = int(m["equipes"])
        info[a.id] = {"rem": m["quantidade_remanescente"], "prod": m["produtividade"], "n0": n0,
                      "nmax": min(EQUIPES_MAX, n0 + limite_extra), "custo_eq_dia": ce,
                      "andamento": a.status == "em_andamento"}
    n = {i: v["n0"] for i, v in info.items()}
    calculos = [0]

    def D(i, k=None):
        v = info[i]
        return _duracao(v["rem"], v["prod"], n[i] if k is None else k, v["andamento"])

    def cpm(extra: dict[str, int] | None = None):
        eq = {**n, **(extra or {})}
        for a in ativs:
            if a.id in info:
                v = info[a.id]
                a.duracao = _duracao(v["rem"], v["prod"], eq[a.id], v["andamento"])
        calculos[0] += 1
        res = calcular(ativs, rels, projeto.calendarios, projeto.inicio_projeto, data_status=projeto.data_status)
        for a in ativs:
            a.duracao = base[a.id]
        return res

    def determinante(res) -> list[str]:
        finais = [i for i in res.ordem if res.atividades[i].ef == res.termino_projeto]
        vistos, pilha = set(), list(finais)
        while pilha:
            x = pilha.pop()
            if x not in vistos:
                vistos.add(x)
                pilha.extend(res.atividades[x].determinantes)
        return [i for i in res.ordem if i in vistos]

    def passo_de(i) -> int | None:
        """Menor k (1..limite restante) tal que n+k equipes REDUZEM a duração; None se nenhum (platô até o teto)."""
        for k in range(1, info[i]["nmax"] - n[i] + 1):
            if D(i, n[i] + k) < D(i):
                return k
        return None

    def custo_de(i, k) -> float:
        v = info[i]
        ocioso = max(0, (n[i] + k) * D(i, n[i] + k) - n[i] * D(i))
        return v["custo_eq_dia"] * (ocioso + k * MOBILIZACAO_EQUIPE_DIAS)

    def candidatas(res) -> list[str]:
        return [i for i in determinante(res) if i in info and passo_de(i) is not None]

    res = cpm()
    t0 = res.termino_projeto_data
    curva = [{"passo": 0, "termino": iso(t0), "custo_acumulado": 0.0, "ajustes": [], "composto": False}]
    custo_total, motivo = 0.0, None
    for passo in range(1, max_passos + 1):
        t_atual = res.termino_projeto_data
        if t_atual <= t_prazo:
            break
        if time.perf_counter() - t_ini > tempo_max_s:
            motivo = f"tempo de execução acima de {tempo_max_s:g} s"
            break
        cands = candidatas(res)
        if not cands:
            motivo = (f"nenhuma frente do caminho determinante pode receber mais equipes (limite de {limite_extra} "
                      f"equipe(s) extra(s) por frente, teto {EQUIPES_MAX}, ou serviço sem composição de custo)")
            break
        opcoes = []
        for i in cands:
            k = passo_de(i)
            ganho = t_atual - cpm({i: n[i] + k}).termino_projeto_data
            if ganho > 0:
                c = custo_de(i, k)
                opcoes.append((c / ganho, c, i, k))
        aplicados = []  # [(atividade, k)]
        if opcoes:
            _, _, i, k = min(opcoes)
            aplicados.append((i, k))
        else:
            # passo composto: a mais barata, recalcula, até o término cair (encurta um em cada caminho)
            res_tmp = res
            while res_tmp.termino_projeto_data >= t_atual:
                cs = candidatas(res_tmp)
                if not cs:
                    break
                i = min(cs, key=lambda x: (custo_de(x, passo_de(x)), x))
                k = passo_de(i)
                aplicados.append((i, k))
                n[i] += k
                res_tmp = cpm()
            for i, k in reversed(aplicados):
                n[i] -= k  # desfaz: reaplicado abaixo com o registro do custo
            if res_tmp.termino_projeto_data >= t_atual:
                motivo = (f"caminhos paralelos: não há equipes disponíveis (limite de {limite_extra} extra(s) por "
                          "frente) para encurtar todos os caminhos determinantes")
                break
        registro, custo_passo = [], 0.0
        for i, k in aplicados:
            c = custo_de(i, k)
            registro.append({"id": i, "equipes_de": n[i], "equipes_para": n[i] + k, "duracao_de": D(i),
                             "duracao_para": D(i, n[i] + k), "custo": round(c, 2)})
            n[i] += k
            custo_passo += c
        res = cpm()
        custo_total += custo_passo
        curva.append({"passo": passo, "termino": iso(res.termino_projeto_data),
                      "custo_acumulado": round(custo_total, 2), "ajustes": registro, "composto": len(registro) > 1})
    else:
        motivo = f"limite de {max_passos} passos atingido"

    t_alc = res.termino_projeto_data
    cumpre = t_alc <= t_prazo
    ajustes = [{"atividade_id": i, "equipes": n[i]} for i in sorted(n) if n[i] != info[i]["n0"]]
    verif = executar(projeto, "simulado", [Ajuste(**a) for a in ajustes]) if ajustes else executar(projeto,
                                                                                                    "independente")
    return {
        "prazo": iso(t_prazo), "termino_inicial": iso(t0), "termino_alcancado": iso(t_alc),
        "cumpre_prazo": cumpre, "motivo": None if cumpre else motivo,
        "custo_adicional_total": round(custo_total, 2),
        "curva": curva, "ajustes_finais": ajustes,
        "verificacao": {"termino": verif["termino"], "confere": verif["termino"] == iso(t_alc),
                        "como": "POST /api/simulacao com {'ajustes': ajustes_finais}"},
        "sem_composicao_de_custo": sem_custo,
        "parametros": {"limite_extra": limite_extra, "mobilizacao_equipe_dias": MOBILIZACAO_EQUIPE_DIAS,
                       "custos": "informados" if custos is not None else "orçamento fictício (mão de obra + "
                                                                         "equipamento × produtividade × (1 + BDI))",
                       "max_passos": max_passos, "tempo_max_s": tempo_max_s},
        "calculos_cpm": calculos[0], "tempo_s": round(time.perf_counter() - t_ini, 3),
        "metodo": "guloso: +1 equipe na frente determinante de menor custo por dia ganho; passo composto quando "
                  "há caminhos empatados; NÃO é ótimo global",
        "aviso": "custos FICTÍCIOS (orçamento de demonstração)",
    }
