"""Cenários de recuperação: o que precisa acontecer para o cenário INDEPENDENTE cumprir um prazo.

Pergunta do fiscal/gestor: "com a produtividade medida a obra termina em X; quanto cada frente
precisa render (ou quantas equipes precisa) para terminar no prazo Y?"

Método (heurístico, guloso, auditável — NÃO é otimização global):

1. Parte do cenário independente (produtividade medida). Alvo = término da obra ou de um marco.
2. Conjunto DETERMINANTE do alvo: todas as predecessoras que empatam na fixação do início,
   recursivamente (inclui caminhos paralelos empatados). Só são ajustáveis atividades por
   quantidade, não concluídas, até ``fator_max`` × a produtividade medida.
3. UMA FRENTE RESOLVE? Para cada ajustável do conjunto, BISSEÇÃO na duração inteira (a duração é
   ⌈remanescente ÷ (produtividade × equipes)⌉, então a produtividade mínima para a duração D é
   remanescente ÷ (equipes × D)) da maior duração que, sozinha, põe o alvo no prazo. Se alguma
   resolve, fica a de MENOR esforço (aumento %), desempate pela viabilidade e pelo id.
4. Senão, ESCALONAMENTO POR MENOR ESFORÇO: a cada passo recalcula o CPM, pega o conjunto
   determinante (a cadeia muda conforme se encurta) e encurta 1 dia a frente cujo fator resultante é
   o menor — equaliza o esforço (minimiza o máximo). Se nenhuma sozinha antecipa (caminhos
   empatados), encurta todas as empatadas. Para quando cumpre ou quando nada mais é ajustável.
5. Ao cumprir, RELAXA cada ajuste (do mais caro para o mais barato): devolve a maior duração que
   ainda cumpre o prazo, com os demais fixos.
6. VERIFICA aplicando o plano como ajustes no cenário ``simulado`` (o mesmo caminho da API) — por
   produtividade e, à parte, pela alternativa de equipes inteiras com a produtividade medida.

Viabilidade de cada item, contra a MELHOR SEMANA medida (boletins, mesma hierarquia de fontes do
independente: atividade → lote/serviço → serviço):
- ``viavel``: necessária ≤ melhor semana (já foi atingida em campo);
- ``acima_da_melhor_semana``: até 1,3 × a melhor semana;
- ``inviavel_sem_mudanca_de_metodo``: acima de 1,3 × a melhor semana;
- ``sem_referencia_medida``: sem boletim utilizável.
O plano todo vale o pior item; ``inviavel`` quando nem com ``fator_max`` o prazo é alcançado.

Limite conhecido: o CPM pode ter atividade "reversa" (FF/SF de entrada e SS de saída), em que
encurtar atrasa; a bisseção supõe monotonia e o passo 6 (verificação) é a garantia final.
"""

from __future__ import annotations

import math
from collections import defaultdict

from .calendario import iso, ordinal
from .cenarios import Ajuste, Projeto, executar, montar_entrada
from .motor import calcular

ORDEM_VIAB = ("viavel", "acima_da_melhor_semana", "sem_referencia_medida", "inviavel_sem_mudanca_de_metodo")
LIMIAR_METODO = 1.3
FATOR_MAX_PADRAO = 2.0
EQUIPES_MAX = 20  # mesmo limite da validação de ajustes da API
# Defesas independentes contra o paradoxo da atividade reversa (2026-11-13): (a) o passo de empate só mantém
# encurtamento que não piora o alvo; (b) antes de declarar inviável, a aceleração serve de contraprova.
# A chave abaixo existe para o teste provar que (b) sozinha também segura o caso (desligando a).
_EMPATE_SO_SE_NAO_PIORA = True


def _melhor_semana(projeto: Projeto, a: dict) -> tuple[float | None, str | None]:
    """Maior Σq ÷ Σequipes·dia semanal na primeira fonte com produção (atividade → lote/serviço → serviço)."""
    P = projeto.atividades
    niveis = (("atividade", lambda x: x["id"] == a["id"]),
              ("lote_servico", lambda x: (x.get("lote_id"), x.get("servico_id")) == (a.get("lote_id"),
                                                                                      a.get("servico_id"))),
              ("servico", lambda x: x.get("servico_id") == a.get("servico_id")))
    for nome, filtro in niveis:
        sem = defaultdict(lambda: [0.0, 0.0])
        for m in projeto.dados.get("medicoes", []):
            x = P.get(m.get("atividade_id"))
            if x is None or m.get("equipes_dias", 0) <= 0 or not filtro(x):
                continue
            s = sem[m.get("semana_inicio")]
            s[0] += float(m["quantidade"])
            s[1] += float(m["equipes_dias"])
        vals = [q / e for q, e in sem.values() if e > 0]
        if vals and max(vals) > 0:
            return max(vals), f"{nome} ({len(vals)} semanas)"
    return None, None


def _classificar(nec: float, melhor: float | None) -> tuple[str, float | None]:
    if not melhor:
        return "sem_referencia_medida", None
    r = nec / melhor
    if r <= 1 + 1e-9:
        return "viavel", r
    if r <= LIMIAR_METODO + 1e-9:
        return "acima_da_melhor_semana", r
    return "inviavel_sem_mudanca_de_metodo", r


class _Rede:
    """Cenário independente com durações substituíveis, recalculado pelo motor."""

    def __init__(self, projeto: Projeto, alvo: str | None):
        self.P = projeto
        self.ativs, self.rels, self.mem = montar_entrada(projeto, "independente")
        self.por_id = {a.id: a for a in self.ativs}
        self.base = {a.id: a.duracao for a in self.ativs}
        self.alvo = alvo
        self.ds = projeto.data_status
        self.n_calculos = 0

    def calcular(self, dur: dict[str, int]):
        for a in self.ativs:
            a.duracao = dur.get(a.id, self.base[a.id])
        self.n_calculos += 1
        res = calcular(self.ativs, self.rels, self.P.calendarios, self.P.inicio_projeto, data_status=self.ds)
        for a in self.ativs:
            a.duracao = self.base[a.id]
        return res

    def termino(self, res) -> int:
        if self.alvo is None:
            return res.termino_projeto_data
        a = self.por_id[self.alvo]
        return res.atividades[self.alvo].data_termino(self.P.calendarios[a.calendario], a)

    def conjunto_determinante(self, res) -> list[str]:
        finais = ([i for i in res.ordem if res.atividades[i].ef == res.termino_projeto]
                  if self.alvo is None else [self.alvo])
        vistos, pilha = set(), list(finais)
        while pilha:
            n = pilha.pop()
            if n not in vistos:
                vistos.add(n)
                pilha.extend(res.atividades[n].determinantes)
        return [i for i in res.ordem if i in vistos]


def _certificado_aceleracao(projeto, marco, t_prazo, fator_max, ajustaveis, R) -> dict[str, int] | None:
    """Durações que cumprem o prazo pela aceleração (``aceleracao.acelerar``), se todas as frentes ficarem com
    fator <= ``fator_max``. Só para o término da obra (a aceleração não mira marco). None se não houver."""
    if marco is not None:
        return None
    try:
        from .aceleracao import EQUIPES_MAX, acelerar
    except ImportError:
        return None
    n0 = {i: int(v["eq"]) for i, v in ajustaveis.items()}
    lim = max(1, min(EQUIPES_MAX, max((math.floor(n * fator_max + 1e-9) - n for n in n0.values()), default=1)))
    servs = {projeto.atividades[i].get("servico_id") for i in ajustaveis}
    try:
        r = acelerar(projeto, prazo=iso(t_prazo), limite_extra=lim, custos={s: 1.0 for s in servs})
    except ValueError:
        return None
    if not r["cumpre_prazo"]:
        return None
    dur = {}
    for a in r["ajustes_finais"]:
        i, n = a["atividade_id"], a["equipes"]
        if i not in ajustaveis or n / n0[i] > fator_max + 1e-9:
            return None
        v = ajustaveis[i]
        d = max(v["dmin"], math.ceil(v["rem"] / (v["prod"] * n) - 1e-9))
        if d < R.base[i]:
            dur[i] = d
    return dur if R.termino(R.calcular(dur)) <= t_prazo else None


def recuperar(projeto: Projeto, prazo: str | None = None, marco: str | None = None, folga_max: int = 5,
              fator_max: float = FATOR_MAX_PADRAO, max_passos: int = 3000) -> dict:
    if marco is not None and projeto.atividades.get(marco, {}).get("tipo") not in ("marco_termino", "marco_inicio"):
        raise ValueError(f"marco desconhecido: {marco}")
    if isinstance(fator_max, bool) or not isinstance(fator_max, (int, float)) or not math.isfinite(fator_max)             or fator_max < 1:
        raise ValueError(f"fator_max deve ser um número finito >= 1 (recebido {fator_max!r})")
    if folga_max < 0:
        raise ValueError("folga_max deve ser >= 0")
    if prazo is None or (isinstance(prazo, str) and not prazo.strip()):  # vazio = padrão (r18)
        if marco:
            prazo = executar(projeto, "linha_base")["atividades"][marco]["termino"]
        else:
            prazo = projeto.dados["meta"].get("termino_linha_base") or executar(projeto, "linha_base")["termino"]
    try:
        t_prazo = ordinal(prazo)
    except (TypeError, ValueError):
        t_prazo = None
    if t_prazo is None:
        raise ValueError(f"prazo inválido {prazo!r} (use AAAA-MM-DD)")

    R = _Rede(projeto, marco)
    ajustaveis = {}
    for a in R.ativs:
        mem = R.mem[a.id]
        if mem.get("regra") == "quantidade" and a.status != "concluida" and a.duracao > 0:
            rem, eq, prod = mem["quantidade_remanescente"], mem["equipes"], mem["produtividade"]
            dmin = max(1, math.ceil(rem / (prod * fator_max * eq) - 1e-9))
            ajustaveis[a.id] = {"rem": rem, "eq": eq, "prod": prod, "dmin": dmin}
    dur: dict[str, int] = {}

    def D(i):
        return dur.get(i, R.base[i])

    def term_com(mud: dict[str, int]) -> int:
        return R.termino(R.calcular({**dur, **mud}))

    def maior_D_que_atinge(i: str, alvo_t: int, lo: int, hi: int) -> int | None:
        """Maior duração em [lo, hi] de ``i`` (demais fixos) com término do alvo <= alvo_t."""
        if term_com({i: lo}) > alvo_t:
            return None
        while lo < hi:
            m = (lo + hi + 1) // 2
            if term_com({i: m}) <= alvo_t:
                lo = m
            else:
                hi = m - 1
        return lo

    res0 = R.calcular({})
    t0 = R.termino(res0)
    passos, motivo = [], None

    def fator(i, d):
        return ajustaveis[i]["rem"] / (ajustaveis[i]["eq"] * d) / ajustaveis[i]["prod"]

    def razao(i, d):
        nec = ajustaveis[i]["rem"] / (ajustaveis[i]["eq"] * d)
        r = _classificar(nec, _melhor_semana(projeto, projeto.atividades[i])[0])[1]
        return math.inf if r is None else r

    marco_ocorrido = (marco is not None and projeto.atividades[marco].get("status") == "concluida")
    if marco_ocorrido and t0 > t_prazo:
        motivo = (f"o marco {marco} já ocorreu em {iso(t0)}, depois do prazo {iso(t_prazo)}: não há o que "
                  f"recuperar no cronograma")
    elif t0 > t_prazo:
        # (a) uma única frente resolve? fica a de menor esforço (desempate: viabilidade, id)
        cand = [i for i in R.conjunto_determinante(res0) if i in ajustaveis and D(i) > ajustaveis[i]["dmin"]]
        solucoes = []
        for i in cand:
            d_ok = maior_D_que_atinge(i, t_prazo, ajustaveis[i]["dmin"], D(i) - 1)
            if d_ok is not None:
                solucoes.append((round(fator(i, d_ok), 12), razao(i, d_ok), i, d_ok))
        if solucoes:
            _, _, i, d_ok = min(solucoes)
            dur[i] = d_ok
            passos.append({"tipo": "uma frente resolve", "id": i, "duracao": d_ok})
        elif not cand:
            motivo = ("o conjunto determinante não tem atividade ajustável (por quantidade, em aberto) com margem "
                      "até o fator máximo")
        else:
            # (b) ESCALONAMENTO por menor esforço: a cada passo, encurta 1 dia a frente do conjunto
            # determinante cujo fator resultante é o menor (equaliza o esforço, minimiza o máximo); se
            # nenhuma sozinha antecipa (caminhos empatados), encurta todas as ajustáveis empatadas.
            res = res0
            for _ in range(max_passos):
                t_atual = R.termino(res)
                if t_atual <= t_prazo:
                    break
                cand = [i for i in R.conjunto_determinante(res) if i in ajustaveis and D(i) > ajustaveis[i]["dmin"]]
                if not cand:
                    motivo = (f"não alcança o prazo nem com produtividade {fator_max:g} × a medida nas frentes "
                              f"determinantes")
                    break
                aval = []
                for i in cand:
                    if term_com({i: D(i) - 1}) < t_atual:
                        aval.append((round(fator(i, D(i) - 1), 12), razao(i, D(i) - 1), i))
                if aval:
                    aval.sort()
                    _, _, i = aval[0]
                    teto = aval[1][0] if len(aval) > 1 else math.inf
                    dur[i] = D(i) - 1
                    # acelera: continua na mesma frente enquanto ela segue a mais barata e o alvo cai
                    while D(i) > ajustaveis[i]["dmin"] and fator(i, D(i) - 1) <= teto + 1e-12:
                        t_novo = term_com({})
                        if t_novo <= t_prazo or term_com({i: D(i) - 1}) >= t_novo:
                            break
                        dur[i] = D(i) - 1
                    passos.append({"tipo": "menor esforço", "id": i, "duracao": D(i)})
                else:
                    # empate: encurta as empatadas UMA a UMA (da de menor esforço) e só mantém o encurtamento que
                    # NÃO piora o alvo — atividade "reversa" (FF/SF de entrada, SS de saída) atrasa o término quando
                    # encurta (revisão da aceleração, 2026-11-13: na ferrovia isso dava um falso "inviável")
                    mantidos, t_ref = [], t_atual
                    for i in sorted(cand, key=lambda j: (round(fator(j, D(j) - 1), 12), j)):
                        t_novo = term_com({i: D(i) - 1})
                        if t_novo <= t_ref or not _EMPATE_SO_SE_NAO_PIORA:
                            dur[i] = D(i) - 1
                            mantidos.append(i)
                            t_ref = t_novo
                    if not mantidos:
                        motivo = (f"não alcança o prazo nem com produtividade {fator_max:g} × a medida nas frentes "
                                  f"determinantes (todo encurtamento restante atrasa o término)")
                        break
                    passos.append({"tipo": "frentes empatadas, -1 dia nas que não pioram", "ids": mantidos,
                                   "rejeitadas_por_piorar": [i for i in cand if i not in mantidos]})
                res = R.calcular(dur)
            else:
                motivo = f"limite de {max_passos} passos atingido"

    t_alc = R.termino(R.calcular(dur))
    cumpre = t_alc <= t_prazo
    certificado = None
    if not cumpre and t0 > t_prazo and not marco_ocorrido:
        # (b) antes de declarar inviável: a ACELERAÇÃO (equipes inteiras, só aceita passo que antecipa) é contraprova.
        # Se ela cumpre com fator <= fator_max em toda frente, a resposta é "cumpre" com esses ajustes.
        certificado = _certificado_aceleracao(projeto, marco, t_prazo, fator_max, ajustaveis, R)
        if certificado is not None:
            dur = certificado
            t_alc = R.termino(R.calcular(dur))
            cumpre = t_alc <= t_prazo
            passos.append({"tipo": "certificado pela aceleração (equipes inteiras) depois do escalonamento parar",
                           "ids": sorted(dur)})
    if not cumpre and motivo is None:
        motivo = f"não alcança o prazo nem com produtividade {fator_max:g} × a medida nas frentes determinantes"

    # relaxação: do ajuste mais caro ao mais barato, devolve a maior duração que ainda cumpre
    # REPETIDA até nenhuma frente mudar (revisão r11: uma passada só deixava frentes relaxáveis)
    if cumpre:
        for _ in range(len(dur) * 50 + 1):
            mudou = False
            for i in sorted(dur, key=lambda j: -(R.base[j] / dur[j])):
                d_max = maior_D_que_atinge(i, t_prazo, dur[i], R.base[i])
                if d_max is not None and d_max > dur[i]:
                    dur[i] = d_max
                    mudou = True
            if not mudou:
                break
        dur = {i: d for i, d in dur.items() if d < R.base[i]}

    plano = []
    for i, d in dur.items():
        info, a = ajustaveis[i], projeto.atividades[i]
        nec = info["rem"] / (info["eq"] * d)
        melhor, fonte = _melhor_semana(projeto, a)
        viab, razao = _classificar(nec, melhor)
        n_eq = math.ceil(info["rem"] / (info["prod"] * d) - 1e-9)
        plano.append({
            "id": i, "nome": a.get("nome"), "lote_id": a.get("lote_id"), "servico_id": a.get("servico_id"),
            "quantidade_remanescente": info["rem"], "unidade": a.get("unidade"),
            "duracao_atual": R.base[i], "duracao_necessaria": d,
            "produtividade_medida": info["prod"], "produtividade_necessaria": nec,
            "aumento_pct": round(100 * (nec / info["prod"] - 1), 6),
            "equipes_atuais": info["eq"],
            "equipes_necessarias": n_eq if n_eq <= EQUIPES_MAX else None,
            "melhor_semana": melhor, "fonte_melhor_semana": fonte,
            "razao_melhor_semana": None if razao is None else round(razao, 4),
            "viabilidade": viab,
        })
    plano.sort(key=lambda p: (p["aumento_pct"], p["id"]))

    aj_prod = [{"atividade_id": p["id"], "produtividade": p["produtividade_necessaria"]} for p in plano]
    aj_eq = [{"atividade_id": p["id"], "equipes": p["equipes_necessarias"]} for p in plano]
    verif = {}
    if plano:
        r_prod = executar(projeto, "simulado", [Ajuste(**x) for x in aj_prod])
        r_alvo = r_prod["atividades"][marco]["termino"] if marco else r_prod["termino"]
        verif["produtividade"] = {"termino": r_alvo, "cumpre": ordinal(r_alvo) <= t_prazo}
        if all(x["equipes"] for x in aj_eq):
            r_eq = executar(projeto, "simulado", [Ajuste(**x) for x in aj_eq])
            t_eq = r_eq["atividades"][marco]["termino"] if marco else r_eq["termino"]
            verif["equipes"] = {"termino": t_eq, "cumpre": ordinal(t_eq) <= t_prazo}
        else:
            verif["equipes"] = {"termino": None, "cumpre": None,
                                "nota": f"alguma frente exigiria mais de {EQUIPES_MAX} equipes"}
        if cumpre and not verif["produtividade"]["cumpre"]:
            cumpre, motivo = False, "plano não cumpriu o prazo na verificação pelo cenário simulado"
        res_final = R.calcular(dur)
    else:
        res_final = res0

    if t0 <= t_prazo:
        viab_geral = "no_prazo"
    elif not cumpre:
        viab_geral = "inviavel"
    else:
        viab_geral = max((p["viabilidade"] for p in plano), key=ORDEM_VIAB.index)
    quase = [{"id": i, "folga_total": res_final.atividades[i].folga_total} for i in res_final.ordem
             if res_final.atividades[i].folga_total is not None and res_final.atividades[i].folga_total <= folga_max
             and R.por_id[i].status != "concluida" and R.por_id[i].tipo == "tarefa"]
    return {
        "alvo": marco or "término da obra",
        "prazo": iso(t_prazo),
        "termino_atual": iso(t0),
        "termino_alcancado": iso(t_alc),
        "cumpre_prazo": t0 <= t_prazo or cumpre,
        "viabilidade": viab_geral,
        "motivo": None if (t0 <= t_prazo or cumpre) else motivo,
        "plano_tipo": ("nenhum" if t0 <= t_prazo else "minimo_que_cumpre" if cumpre
                       else "melhor_esforco_sem_cumprir"),
        "plano": plano,
        "ajustes_produtividade": aj_prod,
        "ajustes_equipes": aj_eq,
        "verificacao": verif,
        "quase_criticas_apos_plano": quase,
        "passos": passos,
        "parametros": {"fator_max": fator_max, "folga_max": folga_max, "limiar_mudanca_de_metodo": LIMIAR_METODO},
        "calculos_cpm": R.n_calculos,
        "metodo": "guloso sobre o conjunto determinante, bisseção na duração inteira, relaxação final e "
                  "verificação no cenário simulado (heurística, não ótimo global)",
    }
