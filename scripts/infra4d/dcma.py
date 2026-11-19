"""Avaliação de qualidade de cronograma: DCMA 14 pontos.

Aplica-se aos cenários do motor e ao cronograma IMPORTADO da construtora (MSPDI/XER).
Trabalha sobre ``AtividadeCPM``/``Relacao`` e o resultado do motor CPM próprio.

Fontes dos limites (consultadas em 2026-11-12):
- Deltek Acumen 8.11, "DCMA 14-Point Assessment Metric Descriptions"
  (https://help.deltek.com/Product/Acumen/8.11/GA/DCMA%2014%20Point%20Assessment%20Metric%20Descriptions.html):
  confirma Lógica ≤ 5%, Leads = 0, Lags ≤ 5%, FS ≥ 90%, Restrições rígidas ≤ 5%, Folga alta > 44 dias úteis,
  Folga negativa < 0, Duração alta > 44 dias úteis ≤ 5%, Datas inválidas = 0, e as definições de 10–14.
  Essa página NÃO traz percentual para 6, 7, 11, nem limite para CPLI e BEI.
- Os limites "Folga alta ≤ 5%", "Folga negativa 0%", "Tarefas perdidas ≤ 5%", "CPLI ≥ 0,95" e
  "BEI ≥ 0,95" são os valores USUALMENTE CITADOS (revisão 2012 das diretrizes do DCMA), NÃO verificados
  em fonte primária. Cada ponto informa ``fonte_limite``.
- O próprio DCMA trata os limites como ponto de partida de análise, não como gatilho de conformidade.

Decisões de modelagem (declaradas em cada ponto):
- População = tarefas NÃO concluídas com duração > 0 (marcos excluídos), como no Acumen.
- Restrição rígida = FNLT (``restricao_termino``); SNET é restrição branda e não conta. O modelo não
  tem MSO/MFO/SNLT.
- Duração alta usa a duração do cálculo (remanescente para em andamento); a duração de linha de base
  só existe nos cenários próprios.
- Datas inválidas: datas REAIS na data de status ou depois são checadas antes do motor; datas previstas
  vêm do motor, que nunca as põe antes da data de status (as datas gravadas no arquivo importado não
  são lidas pelo importador).
- Teste do caminho crítico: EXECUTADO com o motor (a duração de uma atividade crítica é aumentada em
  N dias úteis e o término é recalculado).
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

from .calendario import ErroCalendario, iso, ordinal
from .motor import AtividadeCPM, ErroRede, Relacao, ResultadoCPM, calcular

LIMITE_DIAS = 44
ATRASO_TESTE = 10
MAX_LISTA = 500

FONTE_ACUMEN = "Deltek Acumen 8.11, DCMA 14-Point Assessment Metric Descriptions (verificado 2026-11-12)"
FONTE_USUAL = "valor usualmente citado (DCMA, revisão 2012), NÃO verificado em fonte primária"
FONTES = [
    "https://help.deltek.com/Product/Acumen/8.11/GA/DCMA%2014%20Point%20Assessment%20Metric%20Descriptions.html",
]


@dataclass
class Ponto:
    numero: int
    nome: str
    valor: float | None
    unidade: str
    limite: float | None
    criterio: str  # "<=", ">=", "==", "informativo"
    fonte_limite: str
    violadoras: list[str] = field(default_factory=list)
    nota: str = ""
    aprovado: bool | None = None
    detalhe: dict = field(default_factory=dict)

    def julgar(self) -> "Ponto":
        if self.valor is None or self.limite is None or self.criterio == "informativo":
            self.aprovado = None
        elif self.criterio == "<=":
            self.aprovado = self.valor <= self.limite + 1e-9
        elif self.criterio == ">=":
            self.aprovado = self.valor >= self.limite - 1e-9
        else:
            self.aprovado = abs(self.valor - self.limite) < 1e-9
        return self

    def como_dict(self) -> dict:
        return {"numero": self.numero, "nome": self.nome,
                "valor": None if self.valor is None else round(self.valor, 4), "unidade": self.unidade,
                "limite": self.limite, "criterio": self.criterio, "aprovado": self.aprovado,
                "n_violadoras": len(self.violadoras), "violadoras": self.violadoras[:MAX_LISTA],
                "lista_truncada": len(self.violadoras) > MAX_LISTA, "nota": self.nota,
                "fonte_limite": self.fonte_limite, "detalhe": self.detalhe}


def _pct(n: int, total: int) -> float | None:
    return None if total == 0 else 100.0 * n / total


def avaliar(atividades: list[AtividadeCPM], relacoes: list[Relacao], calendarios: dict, inicio_projeto: int,
            data_status: int | None = None, *, linha_base: dict[str, tuple[int | None, int | None]] | None = None,
            recursos: dict[str, float | None] | None = None, termino_contratual: int | None = None,
            calendario_projeto: str | None = None, atraso_teste: int = ATRASO_TESTE,
            logica_progresso: str = "sobrepor", atividade_teste: str | None = None) -> dict:
    """DCMA 14 pontos.

    ``linha_base``: {id: (inicio_lb, termino_lb)} em ordinais (pontos 11 e 14).
    ``recursos``: {id: equipes ou None} (ponto 10); None = o cronograma não traz recursos.
    ``termino_contratual``: ordinal do último dia do prazo (ponto 13).
    """
    ativs = {a.id: a for a in atividades}
    pop = [a for a in atividades if a.tipo == "tarefa" and a.status != "concluida" and a.duracao > 0]
    pop_ids = {a.id for a in pop}
    n_pop = len(pop)
    preds, succs = {}, {}
    for r in relacoes:
        succs.setdefault(r.predecessora, []).append(r)
        preds.setdefault(r.sucessora, []).append(r)
    # relações "vivas": sucessora não concluída (as de atividades concluídas não afetam a previsão)
    rels = [r for r in relacoes if r.sucessora in ativs and ativs[r.sucessora].status != "concluida"]
    pontos: list[Ponto] = []
    nota_pop = f"população: {n_pop} tarefas não concluídas com duração > 0 (marcos excluídos)"

    # 1 lógica
    sem = [a.id for a in pop if not preds.get(a.id) or not succs.get(a.id)]
    pontos.append(Ponto(1, "Lógica (sem predecessora ou sem sucessora)", _pct(len(sem), n_pop), "%", 5.0, "<=",
                        FONTE_ACUMEN, sem, nota_pop,
                        detalhe={"sem_predecessora": [i for i in sem if not preds.get(i)],
                                 "sem_sucessora": [i for i in sem if not succs.get(i)]}))
    # 2 leads, 3 lags, 4 tipos
    nota_rel = f"{len(rels)} relações com sucessora não concluída"
    leads = [f"{r.predecessora}->{r.sucessora} {r.tipo}{r.lag}" for r in rels if r.lag < 0]
    pontos.append(Ponto(2, "Leads (lag negativo)", _pct(len(leads), len(rels)), "%", 0.0, "<=", FONTE_ACUMEN,
                        leads, nota_rel))
    lags = [f"{r.predecessora}->{r.sucessora} {r.tipo}+{r.lag}" for r in rels if r.lag > 0]
    pontos.append(Ponto(3, "Lags (lag positivo)", _pct(len(lags), len(rels)), "%", 5.0, "<=", FONTE_ACUMEN,
                        lags, nota_rel))
    nao_fs = [f"{r.predecessora}->{r.sucessora} {r.tipo}" for r in rels if r.tipo != "FS"]
    fs = len(rels) - len(nao_fs)
    pontos.append(Ponto(4, "Tipos de relação (FS)", _pct(fs, len(rels)), "%", 90.0, ">=", FONTE_ACUMEN, nao_fs,
                        nota_rel + "; violadoras = relações que não são FS",
                        detalhe={t: sum(1 for r in rels if r.tipo == t) for t in ("FS", "SS", "FF", "SF")}))
    # 5 restrições rígidas
    rigidas = [a.id for a in pop if a.restricao_termino is not None]
    brandas = [a.id for a in pop if a.restricao_inicio is not None]
    pontos.append(Ponto(5, "Restrições rígidas", _pct(len(rigidas), n_pop), "%", 5.0, "<=", FONTE_ACUMEN, rigidas,
                        "rígida = FNLT (término não depois de); SNET é branda e não conta "
                        f"({len(brandas)} tarefas com SNET). O modelo não tem MSO/MFO/SNLT.",
                        detalhe={"snet_brandas": brandas}))

    # 9 datas inválidas (antes do motor: datas reais incoerentes fazem o motor recusar a rede)
    invalidas_reais = []
    if data_status is not None:
        for a in atividades:
            if a.inicio_real is not None and a.status != "nao_iniciada" and a.inicio_real >= data_status:
                invalidas_reais.append(f"{a.id}: início real {iso(a.inicio_real)} ≥ data de status")
            if a.termino_real is not None and a.status == "concluida" and a.termino_real >= data_status:
                invalidas_reais.append(f"{a.id}: término real {iso(a.termino_real)} ≥ data de status")

    # motor
    res: ResultadoCPM | None = None
    erro_motor = None
    if not invalidas_reais:
        try:
            res = calcular(atividades, relacoes, calendarios, inicio_projeto, data_status=data_status,
                           logica_progresso=logica_progresso)
        except (ErroRede, ErroCalendario) as e:
            erro_motor = str(e)
    else:
        erro_motor = "datas reais na data de status ou depois: o motor recusaria a rede"
    sem_motor = f"não calculado: {erro_motor}" if erro_motor else ""

    def ft(i):
        return res.atividades[i].folga_total

    # 6, 7 folgas
    if res:
        alta = [i for i in sorted(pop_ids) if ft(i) is not None and ft(i) > LIMITE_DIAS]
        neg = [i for i in sorted(pop_ids) if ft(i) is not None and ft(i) < 0]
        pontos.append(Ponto(6, f"Folga alta (> {LIMITE_DIAS} dias úteis)", _pct(len(alta), n_pop), "%", 5.0, "<=",
                            FONTE_USUAL, alta, nota_pop + "; folga total do motor próprio"))
        pontos.append(Ponto(7, "Folga negativa", _pct(len(neg), n_pop), "%", 0.0, "<=", FONTE_USUAL, neg,
                            nota_pop + "; folga negativa só surge com restrição de término (FNLT)"))
    else:
        pontos.append(Ponto(6, f"Folga alta (> {LIMITE_DIAS} dias úteis)", None, "%", 5.0, "<=", FONTE_USUAL,
                            nota=sem_motor))
        pontos.append(Ponto(7, "Folga negativa", None, "%", 0.0, "<=", FONTE_USUAL, nota=sem_motor))
    # 8 duração alta
    longas = [a.id for a in pop if a.duracao > LIMITE_DIAS]
    pontos.append(Ponto(8, f"Duração alta (> {LIMITE_DIAS} dias úteis)", _pct(len(longas), n_pop), "%", 5.0, "<=",
                        FONTE_ACUMEN, longas,
                        nota_pop + "; duração do cálculo (remanescente para em andamento), não a de linha de base"))
    # 9 datas inválidas
    if data_status is None:
        pontos.append(Ponto(9, "Datas inválidas", None, "qtd", 0.0, "<=", FONTE_ACUMEN,
                            nota="não se aplica: sem data de status (linha de base)"))
    else:
        prev = []
        if res:
            for a in atividades:
                r = res.atividades[a.id]
                if a.status == "nao_iniciada" and r.es < data_status:
                    prev.append(f"{a.id}: início previsto {iso(r.es)} antes da data de status")
                if a.status != "concluida" and a.duracao > 0 and r.ef <= data_status:
                    prev.append(f"{a.id}: término previsto antes da data de status")
        v = invalidas_reais + prev
        pontos.append(Ponto(9, "Datas inválidas", float(len(v)), "qtd", 0.0, "<=", FONTE_ACUMEN, v,
                            "reais ≥ data de status (checadas antes do motor) + previstas < data de status (do motor). "
                            "Datas previstas GRAVADAS no arquivo importado não são lidas pelo importador."))
    # 10 recursos
    if recursos is None:
        pontos.append(Ponto(10, "Recursos", None, "%", None, "informativo", FONTE_ACUMEN,
                            nota="não se aplica: o cronograma não traz recursos (o importador não lê "
                                 "RESOURCES/TASKRSRC nem Assignments)"))
    else:
        sem_rec = [a.id for a in pop if not recursos.get(a.id)]
        pontos.append(Ponto(10, "Recursos (tarefas sem equipes)", _pct(len(sem_rec), n_pop), "%", None,
                            "informativo", FONTE_ACUMEN, sem_rec, nota_pop + "; o DCMA não fixa limite"))
    # 11 tarefas perdidas, 14 BEI
    if linha_base is None or data_status is None:
        motivo = "sem linha de base" if linha_base is None else "sem data de status"
        pontos.append(Ponto(11, "Tarefas perdidas", None, "%", 5.0, "<=", FONTE_USUAL, nota=f"não se aplica: {motivo}"))
    else:
        devidas = [a for a in atividades if a.tipo == "tarefa"
                   and (linha_base.get(a.id) or (None, None))[1] is not None
                   and linha_base[a.id][1] < data_status]
        perdidas = [a.id for a in devidas
                    if a.status != "concluida" or (a.termino_real is not None and a.termino_real > linha_base[a.id][1])]
        pontos.append(Ponto(11, "Tarefas perdidas", _pct(len(perdidas), len(devidas)), "%", 5.0, "<=", FONTE_USUAL,
                            perdidas, f"{len(devidas)} tarefas com término de linha de base antes da data de status; "
                                      "perdida = não concluída ou concluída depois do término de linha de base"))
    # 12 teste do caminho crítico
    pontos.append(_teste_caminho_critico(atividades, relacoes, calendarios, inicio_projeto, data_status, res,
                                         sem_motor, calendario_projeto, atraso_teste, logica_progresso,
                                         atividade_teste))
    # 13 CPLI
    pontos.append(_cpli(atividades, calendarios, inicio_projeto, data_status, res, sem_motor, termino_contratual,
                        calendario_projeto))
    if linha_base is None or data_status is None:
        motivo = "sem linha de base" if linha_base is None else "sem data de status"
        pontos.append(Ponto(14, "BEI (índice de execução da linha de base)", None, "índice", 0.95, ">=", FONTE_USUAL,
                            nota=f"não se aplica: {motivo}"))
    else:
        devidas = [a for a in atividades if a.tipo == "tarefa"
                   and (linha_base.get(a.id) or (None, None))[1] is not None and linha_base[a.id][1] < data_status]
        concl = [a for a in atividades if a.tipo == "tarefa" and a.status == "concluida"]
        nao = [a.id for a in devidas if a.status != "concluida"]
        valor = None if not devidas else len(concl) / len(devidas)
        pontos.append(Ponto(14, "BEI (índice de execução da linha de base)", valor, "índice", 0.95, ">=", FONTE_USUAL,
                            nao, f"BEI = concluídas ({len(concl)}) ÷ com término de linha de base antes da data de "
                                 f"status ({len(devidas)}); violadoras = devidas e não concluídas"))

    pontos.sort(key=lambda p: p.numero)
    for p in pontos:
        p.julgar()
    saida = [p.como_dict() for p in pontos]
    return {
        "pontos": saida,
        "populacao": n_pop,
        "n_relacoes_vivas": len(rels),
        "data_status": iso(data_status),
        "termino_calculado": iso(res.termino_projeto_data) if res else None,
        "erro_motor": erro_motor,
        "resumo": {"aprovados": sum(1 for p in saida if p["aprovado"] is True),
                   "reprovados": sum(1 for p in saida if p["aprovado"] is False),
                   "nao_avaliados": sum(1 for p in saida if p["aprovado"] is None)},
        "fontes": FONTES,
        "aviso": "Os limites do DCMA são ponto de partida de análise, não critério de conformidade.",
    }


def _cal_proj(atividades, calendarios, calendario_projeto, res):
    if calendario_projeto in calendarios:
        return calendarios[calendario_projeto]
    if res:
        final = res.cadeia_determinante[-1] if res.cadeia_determinante else res.ordem[-1]
        a = next(x for x in atividades if x.id == final)
        return calendarios[a.calendario]
    return next(iter(calendarios.values()))


def _teste_caminho_critico(atividades, relacoes, calendarios, inicio, ds, res, sem_motor, cal_proj_id, n, logica,
                           atividade_teste=None):
    nome = "Teste do caminho crítico (executado no motor)"
    if res is None:
        return Ponto(12, nome, None, "dias úteis", float(n), "==", FONTE_ACUMEN, nota=sem_motor)
    por_id = {a.id: a for a in atividades}
    candidatas = [i for i in res.cadeia_determinante
                  if por_id[i].tipo == "tarefa" and por_id[i].status != "concluida" and por_id[i].duracao > 0]
    if not candidatas:
        return Ponto(12, nome, None, "dias úteis", float(n), "==", FONTE_ACUMEN,
                     nota="não se aplica: nenhuma tarefa não concluída na cadeia determinante")
    # Prefere a 1ª tarefa da cadeia cujo TÉRMINO dirige o elo seguinte (FS/FF) ou que fecha a cadeia:
    # aumentar a duração de uma tarefa que só dirige pelo início (SS/SF) não deveria mover o término,
    # e isso não é defeito da rede (achado ao rodar na linha de base da ferrovia: SUP → TER é SS+lag).
    # A relação que DIRIGE é a que de fato fixou o início do elo seguinte (motivo_inicio do motor, ex.:
    # "SS+2 de A"), não qualquer relação entre os dois (r12: par SS+FF escolhia A pela FF, que não dirige).
    cadeia = res.cadeia_determinante

    def tipo_que_dirige(suc: str, pred: str) -> str | None:
        m = re.match(r"^(FS|SS|FF|SF)[+-]?\d+ de (.+)$", res.atividades[suc].motivo_inicio or "")
        return m.group(1) if m and m.group(2) == pred else None

    def dirige_pelo_fim(i):
        k = cadeia.index(i)
        return k == len(cadeia) - 1 or tipo_que_dirige(cadeia[k + 1], i) in ("FS", "FF")

    pelo_fim = [i for i in candidatas if dirige_pelo_fim(i)]
    alvo = pelo_fim[0] if pelo_fim else candidatas[0]
    if atividade_teste is not None:  # escolha explícita do usuário
        if atividade_teste not in por_id:
            return Ponto(12, nome, None, "dias úteis", float(n), "==", FONTE_ACUMEN,
                         nota=f"atividade de teste {atividade_teste!r} inexistente")
        alvo = atividade_teste
    mod = copy.deepcopy(atividades)
    for a in mod:
        if a.id == alvo:
            a.duracao += n
    try:
        r2 = calcular(mod, relacoes, calendarios, inicio, data_status=ds, logica_progresso=logica)
    except (ErroRede, ErroCalendario) as e:
        return Ponto(12, nome, None, "dias úteis", float(n), "==", FONTE_ACUMEN, [alvo],
                     nota=f"o recálculo com o atraso falhou: {e}")
    # O atraso é julgado no calendário da ATIVIDADE testada, em que os N dias foram somados (r12: medir no
    # calendário do projeto reprovava rede sã com calendários diferentes: 5 d/semana em projeto de 6 dava 12).
    cal = _cal_proj(atividades, calendarios, cal_proj_id, res)
    atraso_proj = cal.dias_uteis_entre(res.termino_projeto_data + 1, r2.termino_projeto_data + 1)
    cal_alvo = calendarios[por_id[alvo].calendario]
    atraso_alvo = cal_alvo.dias_uteis_entre(res.termino_projeto_data + 1, r2.termino_projeto_data + 1)
    atraso = atraso_alvo
    p = Ponto(12, nome, float(atraso), "dias úteis", float(n), "==", FONTE_ACUMEN,
              [] if atraso == n else [alvo],
              f"duração de {alvo} (1ª tarefa não concluída da cadeia determinante "
              f"{'que dirige pelo término' if pelo_fim else '— nenhuma dirige pelo término'}) aumentada em "
              f"{n} dias úteis; "
              f"término {iso(res.termino_projeto_data)} → {iso(r2.termino_projeto_data)}; atraso medido no "
              f"calendário da atividade ({cal_alvo.id}), o mesmo em que os {n} dias foram somados"
              + (f" ({atraso_proj} no calendário do projeto, {cal.id}, só informativo)" if cal_alvo.id != cal.id else ""),
              detalhe={"atividade_testada": alvo, "termino_antes": iso(res.termino_projeto_data),
                       "termino_depois": iso(r2.termino_projeto_data), "atraso_calendario_atividade": atraso_alvo,
                       "atraso_calendario_projeto": atraso_proj, "calendario_atividade": cal_alvo.id,
                       "calendario_projeto": cal.id})
    return p


def _cpli(atividades, calendarios, inicio, ds, res, sem_motor, termino_contratual, cal_proj_id):
    nome = "CPLI (índice de comprimento do caminho crítico)"
    if res is None:
        return Ponto(13, nome, None, "índice", 0.95, ">=", FONTE_USUAL, nota=sem_motor)
    if termino_contratual is None:
        return Ponto(13, nome, None, "índice", 0.95, ">=", FONTE_USUAL,
                     nota="não se aplica: sem término contratual/de linha de base para medir a folga do projeto")
    cal = _cal_proj(atividades, calendarios, cal_proj_id, res)
    base = ds if ds is not None else inicio
    cpl = cal.dias_uteis_entre(base, res.termino_projeto_data + 1)
    ftp = cal.dias_uteis_entre(res.termino_projeto_data + 1, termino_contratual + 1)
    if cpl <= 0:
        return Ponto(13, nome, None, "índice", 0.95, ">=", FONTE_USUAL, nota="caminho crítico remanescente nulo")
    return Ponto(13, nome, (cpl + ftp) / cpl, "índice", 0.95, ">=", FONTE_USUAL,
                 nota=f"CPLI = (CPL {cpl} + folga do projeto {ftp}) ÷ CPL {cpl}, em dias úteis do calendário "
                      f"{cal.id}; CPL da {'data de status' if ds else 'data de início'} ao término previsto "
                      f"{iso(res.termino_projeto_data)}; folga até o término contratual {iso(termino_contratual)}",
                 detalhe={"cpl": cpl, "folga_projeto": ftp})


# =============================================================================
# Atalhos: cenário próprio e cronograma importado
# =============================================================================
def avaliar_cenario(projeto, cenario: str = "independente", ajustes=None, atraso_teste: int = ATRASO_TESTE) -> dict:
    from .cenarios import montar_entrada

    ativs, rels, _ = montar_entrada(projeto, cenario, ajustes)
    dados = projeto.dados
    lb = {a["id"]: (ordinal(a.get("inicio_lb")), ordinal(a.get("termino_lb"))) for a in dados["atividades"]}
    recursos = {a["id"]: a.get("equipes") for a in dados["atividades"]}
    ds = None if cenario == "linha_base" else projeto.data_status
    meta = dados["meta"]
    saida = avaliar(ativs, rels, projeto.calendarios, projeto.inicio_projeto, ds, linha_base=lb, recursos=recursos,
                    termino_contratual=ordinal(meta.get("termino_linha_base")),
                    calendario_projeto=meta.get("calendario_obra"), atraso_teste=atraso_teste)
    saida["origem"] = f"cenário {cenario} do motor próprio"
    saida["termino_referencia_cpli"] = meta.get("termino_linha_base")
    return saida


def avaliar_importado(dados, atraso_teste: int = ATRASO_TESTE) -> dict:
    """``dados`` = tupla de ``importar_mspdi``/``importar_xer``."""
    ativs, rels, cals, meta = dados
    saida = avaliar(ativs, rels, cals, meta["inicio_projeto"], meta.get("data_status"), linha_base=None,
                    recursos=None, termino_contratual=None, atraso_teste=atraso_teste)
    saida["origem"] = f"cronograma importado ({meta.get('formato')})"
    saida["avisos_importacao"] = meta.get("avisos", [])
    return saida
