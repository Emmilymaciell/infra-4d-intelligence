"""Cenários climáticos: o término independente sob outro regime de chuva no REMANESCENTE.

A chuva entra no beta como dias não úteis fixos nos calendários. Aqui ela vira cenário:

- **Calendário sensível à chuva** (critério declarado, revisão r13): SÓ a marca BOOLEANA
  ``"sensivel_chuva": true`` no calendário. Sem a marca, NÃO é sensível (o nome não conta: "não
  para com chuva" contém "chuva"). Marca que não é booleana (ex.: o texto "true") é recusada com
  ``ValueError``. O calendário da obra (``meta.calendario_obra``) nunca é sensível.
- **Meses chuvosos**: os do campo ``meses_chuvosos`` do calendário, se houver; senão, os meses do
  ano cujo total de não úteis EXTRAS (não úteis do calendário menos os feriados da obra, somados em
  todos os anos) é MAIOR que 10 % do mês mais chuvoso. Assim um feriado local isolado num
  mês seco (ex.: 15/06) não vira chuva.
- **Dias de chuva** = não úteis extras que caem nos meses chuvosos. LIMITE declarado: um feriado
  local ou parada DENTRO de um mês chuvoso é indistinguível de chuva e é tratado como tal.
- **Âncora**: nada com data <= data de status muda (o passado é fato).

Cenários, por calendário sensível e por mês (ano-mês) futuro:

- ``chuvoso`` (+X): acrescenta floor(X × chuva do mês + 0,5) dias perdidos, sorteados (semente) entre os
  dias úteis do mês posteriores à data de status — só ACRESCENTA não úteis;
- ``seco`` (−X): devolve floor(X × chuva do mês + 0,5) dias de chuva do mês — só REMOVE dias de chuva
  (nunca feriado);
- ``deslocado`` (N semanas; positivo = estação mais TARDE): o padrão de chuva inteiro é deslocado
  de 7·N dias; ficam os dias deslocados posteriores à data de status mais os de chuva já passados.

Cada cenário recalcula o cenário INDEPENDENTE (mesmo motor, mesma produtividade medida) numa
cópia em memória dos dados — o dataset não é alterado.
"""

from __future__ import annotations

import copy
import random
from collections import defaultdict
from datetime import date, timedelta

import math

from .calendario import iso, ordinal
from .cenarios import Projeto, executar

LIMIAR_MES_CHUVOSO = 0.10


def _arredonda(x: float) -> int:
    """Meio para CIMA (round() do Python arredonda meio para o par — revisão r13)."""
    return math.floor(x + 0.5)


def calendarios_sensiveis(projeto: Projeto) -> list[str]:
    obra = projeto.dados.get("meta", {}).get("calendario_obra")
    out = []
    for c in projeto.dados["calendarios"]:
        if c["id"] == obra:
            continue
        marca = c.get("sensivel_chuva")
        if marca is not None and not isinstance(marca, bool):
            raise ValueError(f"calendário {c['id']}: 'sensivel_chuva' deve ser booleano (true/false), "
                             f"recebido {marca!r}")
        if marca is True:
            out.append(c["id"])
    return out


def _dias_chuva(projeto: Projeto, cid: str) -> set[date]:
    c = next(x for x in projeto.dados["calendarios"] if x["id"] == cid)
    obra_id = projeto.dados.get("meta", {}).get("calendario_obra")
    feriados = set()
    if obra_id:
        feriados = {date.fromisoformat(x) for x in
                    next(x for x in projeto.dados["calendarios"] if x["id"] == obra_id).get("nao_uteis", [])}
    semana = set(c.get("dias_semana", (0, 1, 2, 3, 4)))
    extras = {d for d in (date.fromisoformat(x) for x in c.get("nao_uteis", []))
              if d not in feriados and d.weekday() in semana}
    meses = _meses_chuvosos(c, extras)
    return {d for d in extras if d.month in meses}


def _meses_chuvosos(c: dict, extras: set[date]) -> set[int]:
    if c.get("meses_chuvosos"):
        return {int(m) for m in c["meses_chuvosos"]}
    por = defaultdict(int)
    for d in extras:
        por[d.month] += 1
    if not por:
        return set()
    corte = LIMIAR_MES_CHUVOSO * max(por.values())
    return {m for m, n in por.items() if n > corte}


def calendario_alternativo(projeto: Projeto, cid: str, tipo: str, intensidade: float = 0.0,
                           deslocamento_semanas: int = 0, semente: int = 7) -> tuple[list[str], dict]:
    """Não úteis do calendário ``cid`` no cenário ``tipo`` (chuvoso | seco | deslocado) + resumo."""
    c = next(x for x in projeto.dados["calendarios"] if x["id"] == cid)
    ds = date.fromordinal(projeto.data_status)
    atuais = {date.fromisoformat(x) for x in c.get("nao_uteis", [])}
    # calendário NÃO sensível não tem "chuva": nenhum cenário o altera (r13)
    chuva = _dias_chuva(projeto, cid) if cid in calendarios_sensiveis(projeto) else set()
    semana = set(c.get("dias_semana", (0, 1, 2, 3, 4)))
    futuros = defaultdict(list)  # (ano, mês) -> dias de chuva futuros
    for d in chuva:
        if d > ds:
            futuros[(d.year, d.month)].append(d)
    novos = set(atuais)
    if tipo == "chuvoso":
        for (a, m), dias in sorted(futuros.items()):
            n = _arredonda(intensidade * len(dias))
            d0 = max(date(a, m, 1), ds + timedelta(days=1))
            fim = (date(a + (m == 12), m % 12 + 1, 1))
            cand = [d0 + timedelta(days=k) for k in range((fim - d0).days)]
            cand = [d for d in cand if d.weekday() in semana and d not in atuais]
            rng = random.Random(f"{semente}|chuvoso|{cid}|{a}-{m:02d}")
            novos |= set(rng.sample(cand, min(n, len(cand))))
    elif tipo == "seco":
        for (a, m), dias in sorted(futuros.items()):
            n = _arredonda(intensidade * len(dias))
            rng = random.Random(f"{semente}|seco|{cid}|{a}-{m:02d}")
            novos -= set(rng.sample(sorted(dias), min(n, len(dias))))
    elif tipo == "deslocado":
        desl = timedelta(days=7 * deslocamento_semanas)
        novos = {d for d in atuais if d not in chuva or d <= ds}  # feriados + chuva já passada (âncora)
        novos |= {d + desl for d in chuva if d + desl > ds}
    else:
        raise ValueError(f"tipo de cenário climático desconhecido: {tipo}")
    # âncora: passado intocado (garantia explícita, não só consequência das regras)
    novos = {d for d in novos if d > ds} | {d for d in atuais if d <= ds}
    uteis_fut = lambda s: {d for d in s if d > ds and d.weekday() in semana}  # noqa: E731
    resumo = {"calendario": cid, "meses_chuvosos": sorted({d.month for d in chuva}),
              "dias_chuva_futuros_base": sum(len(v) for v in futuros.values()),
              "dias_perdidos_acrescentados": len(uteis_fut(novos) - uteis_fut(atuais)),
              "dias_devolvidos": len(uteis_fut(atuais) - uteis_fut(novos))}
    return sorted(d.isoformat() for d in novos), resumo


def _projeto_com(projeto: Projeto, calendarios: dict[str, list[str]]) -> Projeto:
    dados = copy.copy(projeto.dados)
    dados["calendarios"] = [dict(c, nao_uteis=calendarios[c["id"]]) if c["id"] in calendarios else c
                            for c in projeto.dados["calendarios"]]
    return Projeto(dados)


def _resumo_cenario(projeto: Projeto, nome: str, res: dict, base: dict, sens: list[str], resumos: list[dict],
                    cal_obra) -> dict:
    t0, t1 = ordinal(base["termino"]), ordinal(res["termino"])
    du = cal_obra.dias_uteis_entre(t0 + 1, t1 + 1) if cal_obra else None
    crit = [i for i in res["caminho_critico"] if projeto.atividades[i].get("tipo", "tarefa") == "tarefa"
            and res["atividades"][i]["status"] != "concluida"]
    crit0 = {i for i in base["caminho_critico"]}
    sens_set = set(sens)
    crit_sens = [i for i in crit if projeto.atividades[i]["calendario"] in sens_set]
    entraram = sorted(set(crit) - crit0)
    sairam = sorted(i for i in crit0 - set(res["caminho_critico"])
                    if projeto.atividades[i].get("tipo", "tarefa") == "tarefa")
    acresc = sum(r["dias_perdidos_acrescentados"] for r in resumos)
    devol = sum(r["dias_devolvidos"] for r in resumos)
    partes = ", ".join(f"{r['calendario']} {r['dias_perdidos_acrescentados'] - r['dias_devolvidos']:+d}"
                       for r in resumos)
    delta = t1 - t0
    txt = (f"{nome}: saldo de dias perdidos no remanescente {acresc - devol:+d} ({partes}); término "
           f"{base['termino']} → {res['termino']} ({delta:+d} dias corridos"
           + (f", {du:+d} úteis no calendário da obra" if du is not None else "") + "). ")
    if delta == 0:
        txt += ("O término não muda: as frentes afetadas têm folga ou a cadeia determinante não passa pelos "
                "meses alterados.")
    else:
        txt += (f"{len(crit_sens)} de {len(crit)} tarefas críticas estão em calendário sensível à chuva"
                + (f"; entram no caminho crítico: {', '.join(entraram[:6])}" if entraram else "")
                + (f"; saem: {', '.join(sairam[:6])}" if sairam else "") + ".")
    return {"cenario": nome, "termino": res["termino"], "delta_dias_corridos": delta, "delta_dias_uteis_obra": du,
            "calendarios": resumos, "cadeia_determinante": res["cadeia_determinante"],
            "criticas_em_calendario_sensivel": crit_sens, "n_criticas": len(crit),
            "entraram_no_caminho_critico": entraram, "sairam_do_caminho_critico": sairam, "explicacao": txt}


def cenarios_climaticos(projeto: Projeto, intensidade: float = 0.3, deslocamento_semanas: int = 0,
                        semente: int = 7) -> dict:
    if not 0 <= intensidade <= 1:
        raise ValueError("intensidade deve estar entre 0 e 1 (fração da chuva do mês)")
    if not -26 <= deslocamento_semanas <= 26:
        raise ValueError("deslocamento_semanas deve estar entre -26 e 26")
    sens = calendarios_sensiveis(projeto)
    base = executar(projeto, "independente")
    obra_id = projeto.dados.get("meta", {}).get("calendario_obra")
    cal_obra = projeto.calendarios.get(obra_id) if obra_id else None
    definicoes = [("chuvoso", f"chuvoso +{intensidade:.0%}", {"intensidade": intensidade}),
                  ("seco", f"seco −{intensidade:.0%}", {"intensidade": intensidade})]
    if deslocamento_semanas:
        definicoes.append(("deslocado", f"estação {abs(deslocamento_semanas)} semana(s) "
                                        f"{'mais tarde' if deslocamento_semanas > 0 else 'mais cedo'}",
                           {"deslocamento_semanas": deslocamento_semanas}))
    saida = []
    for tipo, nome, kw in definicoes:
        cals, resumos = {}, []
        for cid in sens:
            nu, rsm = calendario_alternativo(projeto, cid, tipo, semente=semente, **kw)
            cals[cid] = nu
            resumos.append(rsm)
        res = executar(_projeto_com(projeto, cals), "independente")
        item = _resumo_cenario(projeto, nome, res, base, sens, resumos, cal_obra)
        item["tipo"] = tipo
        saida.append(item)
    return {
        "data_status": iso(projeto.data_status),
        "termino_independente": base["termino"],
        "calendarios_sensiveis": sens,
        "criterio_sensivel": "só a marca booleana 'sensivel_chuva': true no calendário (sem marca = não sensível; "
                             "marca não booleana é recusada); o calendário da obra nunca é sensível",
        "limites": ["dias de chuva = não úteis além dos feriados da obra, nos meses chuvosos (campo "
                    "'meses_chuvosos' ou > 10 % do mês mais chuvoso); feriado local DENTRO de mês chuvoso é "
                    "tratado como chuva",
                    "quantidade por mês = floor(intensidade × chuva do mês + 0,5) (meio para cima)",
                    "o deslocamento NÃO preserva o número de dias de chuva: dias deslocados para antes da data de "
                    "status saem e dias que caem em feriado ou fim de semana não somam"],
        "parametros": {"intensidade": intensidade, "deslocamento_semanas": deslocamento_semanas, "semente": semente},
        "cenarios": saida,
        "metodo": "calendários alternativos só para datas posteriores à data de status (âncora); recálculo do "
                  "cenário independente numa cópia em memória; sorteio determinístico por semente",
    }
