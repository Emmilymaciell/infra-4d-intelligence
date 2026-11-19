"""Cenários de planejamento sobre os dados da obra.

Liga os dados de engenharia (quantidade, produtividade, equipes, medições) ao
motor CPM, de forma rastreável:

    duração (dias úteis) = ceil( quantidade_remanescente / (produtividade × equipes) )

Cenários:
- ``linha_base``   : obra inteira a executar, produtividade PLANEJADA, sem data de status.
- ``construtora``  : atualização da construtora FICTÍCIA. Progresso real até a
                     data de status; remanescente na produtividade planejada
                     (premissa de "recuperação" declarada pela construtora).
- ``independente`` : análise própria. Remanescente na produtividade EFETIVA
                     medida (boletins), com hierarquia de fontes declarada.
- ``simulado``     : ``independente`` + ajustes do usuário (produtividade/equipes).

Cada atividade carrega a sua ``memoria`` de cálculo, para auditoria.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .calendario import Calendario, iso, ordinal
from .motor import AtividadeCPM, Relacao, calcular

CENARIOS = ("linha_base", "construtora", "independente", "simulado")
RAIZ = Path(__file__).resolve().parents[2]
DATASET_PADRAO = RAIZ / "examples" / "synthetic" / "ferrovia_ficticia.json"


class ErroAjuste(ValueError):
    """Ajuste de simulação inválido."""


@dataclass
class Ajuste:
    produtividade: float | None = None
    equipes: int | None = None
    atividade_id: str | None = None
    servico_id: str | None = None
    lote_id: str | None = None

    @classmethod
    def de_dict(cls, d: dict) -> "Ajuste":
        try:
            prod = None if d.get("produtividade") in (None, "") else float(d["produtividade"])
            eq_bruto = d.get("equipes")
            if eq_bruto in (None, ""):
                equipes = None
            elif isinstance(eq_bruto, bool) or float(eq_bruto) != int(float(eq_bruto)):
                raise ErroAjuste("equipes deve ser um número inteiro")
            else:
                equipes = int(float(eq_bruto))
        except (TypeError, ValueError) as e:
            if isinstance(e, ErroAjuste):
                raise
            raise ErroAjuste(f"valor numérico inválido no ajuste: {e}") from None
        aj = cls(
            produtividade=prod,
            equipes=equipes,
            atividade_id=d.get("atividade_id") or None,
            servico_id=d.get("servico_id") or None,
            lote_id=d.get("lote_id") or None,
        )
        if aj.produtividade is None and aj.equipes is None:
            raise ErroAjuste("ajuste sem produtividade nem equipes")
        if aj.produtividade is not None and not (aj.produtividade > 0 and math.isfinite(aj.produtividade)):
            raise ErroAjuste("produtividade deve ser um número positivo")
        if aj.equipes is not None and not (1 <= aj.equipes <= 20):
            raise ErroAjuste("equipes deve estar entre 1 e 20")
        if not aj.atividade_id and not aj.servico_id:
            raise ErroAjuste("ajuste precisa de atividade_id ou servico_id")
        return aj

    def aplica_a(self, a: dict) -> bool:
        if self.atividade_id:
            return a["id"] == self.atividade_id
        return a.get("servico_id") == self.servico_id and (not self.lote_id or a.get("lote_id") == self.lote_id)


@dataclass
class Projeto:
    dados: dict
    calendarios: dict[str, Calendario] = field(init=False)
    atividades: dict[str, dict] = field(init=False)

    def __post_init__(self):
        self.calendarios = {c["id"]: Calendario.de_dict(c) for c in self.dados["calendarios"]}
        self.atividades = {a["id"]: a for a in self.dados["atividades"]}
        self._prod_ef = _produtividades_efetivas(self.dados)

    @classmethod
    def carregar(cls, caminho: Path | str = DATASET_PADRAO) -> "Projeto":
        return cls(json.loads(Path(caminho).read_text(encoding="utf-8-sig")))

    @property
    def data_status(self) -> int:
        return ordinal(self.dados["meta"]["data_status"])

    @property
    def inicio_projeto(self) -> int:
        return ordinal(self.dados["meta"]["inicio_projeto"])

    def produtividade_efetiva(self, a: dict) -> tuple[float, str]:
        """Produtividade efetiva (un/equipe·dia) e a FONTE do número."""
        pe = self._prod_ef
        # medição com produtividade <= 0 (equipe alocada, produção zero) não é utilizável
        # para projetar duração: cai para a fonte seguinte, e isso fica declarado.
        descartes = []
        for nivel, chave, texto in (
            ("atividade", a["id"], "medida na própria atividade"),
            ("lote_servico", (a.get("lote_id"), a.get("servico_id")), f"média medida do serviço no {a.get('lote_id')}"),
            ("servico", a.get("servico_id"), "média medida do serviço na obra"),
        ):
            if chave in pe[nivel]:
                v, n = pe[nivel][chave]
                if v > 0:
                    nota = f" (descartado: {', '.join(descartes)})" if descartes else ""
                    return v, f"{texto} ({n} boletins){nota}"
                descartes.append(f"{texto} = 0")
        nota = f" (descartado: {', '.join(descartes)})" if descartes else ""
        return a["produtividade_planejada"], "sem medição utilizável: produtividade planejada" + nota


def _produtividades_efetivas(dados: dict) -> dict:
    ativ = {a["id"]: a for a in dados["atividades"]}
    soma = {"atividade": defaultdict(lambda: [0.0, 0.0, 0]),
            "lote_servico": defaultdict(lambda: [0.0, 0.0, 0]),
            "servico": defaultdict(lambda: [0.0, 0.0, 0])}
    for m in dados.get("medicoes", []):
        a = ativ.get(m["atividade_id"])
        if not a or m["equipes_dias"] <= 0:
            continue
        for nivel, chave in (("atividade", a["id"]),
                             ("lote_servico", (a.get("lote_id"), a.get("servico_id"))),
                             ("servico", a.get("servico_id"))):
            s = soma[nivel][chave]
            s[0] += m["quantidade"]
            s[1] += m["equipes_dias"]
            s[2] += 1
    return {n: {k: (v[0] / v[1], v[2]) for k, v in d.items() if v[1] > 0} for n, d in soma.items()}


# ---------------------------------------------------------------------------
class _IndiceAjustes:
    """Ajustes indexados: por atividade_id (dict) + os por serviço/lote (lista curta), com a posição
    original para aplicar na MESMA ordem da lista (o último aplicável vence)."""

    def __init__(self, ajustes: list[Ajuste]):
        self.por_ativ: dict[str, list[tuple[int, Ajuste]]] = defaultdict(list)
        self.por_servico: list[tuple[int, Ajuste]] = []
        for i, aj in enumerate(ajustes):
            if aj.atividade_id:
                self.por_ativ[aj.atividade_id].append((i, aj))
            else:
                self.por_servico.append((i, aj))

    def para(self, a: dict) -> list[Ajuste]:
        c = list(self.por_ativ.get(a["id"], ()))
        c += [(i, aj) for i, aj in self.por_servico if aj.aplica_a(a)]
        c.sort(key=lambda x: x[0])
        return [aj for _, aj in c]


def montar_entrada(projeto: Projeto, cenario: str, ajustes: list[Ajuste] | None = None):
    if cenario not in CENARIOS:
        raise ValueError(f"cenário desconhecido: {cenario}")
    ajustes = ajustes or []
    # índice LOCAL a esta chamada: sem estado global (a lista pode ser alterada entre chamadas)
    indice = _IndiceAjustes(ajustes) if cenario == "simulado" else None
    base = cenario == "linha_base"
    usa_efetiva = cenario in ("independente", "simulado")
    ativs, memorias = [], {}
    for a in projeto.dados["atividades"]:
        mem: dict = {"cenario": cenario}
        tipo = a.get("tipo", "tarefa")
        status = "nao_iniciada" if base else a.get("status", "nao_iniciada")
        qtd_total = a.get("quantidade_total")
        if tipo != "tarefa":
            dur = 0
            mem["regra"] = "marco (duração 0)"
        elif status == "concluida":
            dur = 0
            mem["regra"] = "concluída: datas reais"
        elif qtd_total:
            executada = 0.0 if base else a.get("quantidade_executada", 0.0)
            rem = max(0.0, qtd_total - executada)
            if usa_efetiva:
                prod, fonte = projeto.produtividade_efetiva(a)
            else:
                prod, fonte = a["produtividade_planejada"], "planejada"
            equipes = a.get("equipes", 1)
            if cenario == "simulado":
                # índice (atividade_id → ajustes) montado uma vez: antes era O(atividades × ajustes),
                # quadrático no MC/sensibilidade/recuperação (1 ajuste por atividade). A ORDEM ORIGINAL é
                # preservada (o último ajuste aplicável vence), então o resultado é idêntico.
                cands = indice.para(a)
                for aj in cands:
                    if aj.produtividade is not None:
                        prod, fonte = aj.produtividade, "AJUSTE DO USUÁRIO (simulação)"
                    if aj.equipes is not None:
                        equipes = aj.equipes
            taxa = prod * equipes
            if not (taxa > 0 and math.isfinite(taxa)):
                raise ErroAjuste(f"atividade {a['id']}: produtividade × equipes deve ser positiva (recebido {taxa})")
            dur = math.ceil(rem / taxa - 1e-9) if rem > 0 else 0
            formula = f"ceil({rem:,.1f} ÷ ({prod:,.2f} × {equipes})) = {dur} dias úteis"
            if status == "em_andamento" and dur == 0:
                dur = 1
                formula = (f"remanescente {rem:,.1f} → 0 dias pela conta; a atividade não foi encerrada, "
                           f"então vale 1 dia útil POR REGRA")
            mem.update(regra="quantidade", quantidade_total=qtd_total, quantidade_executada=executada,
                       quantidade_remanescente=round(rem, 3), unidade=a.get("unidade"),
                       produtividade=round(prod, 4), fonte_produtividade=fonte,
                       produtividade_planejada=a["produtividade_planejada"], equipes=equipes,
                       formula=formula)
        else:
            total = a.get("duracao_fixa", 0)
            pct = 0.0 if base else float(a.get("percentual_executado", 0.0))
            # aritmética em porcentagem inteira-tolerante: 10 × (100−70)/100 = 3, não 3,0000000000000004 → 4
            dur = math.ceil(total * (100 - pct) / 100 - 1e-9) if status != "concluida" else 0
            formula = f"{total} × (1 − {pct:g}%) = {dur} dias úteis"
            if status == "em_andamento" and dur == 0:
                dur = 1
                formula += " → 1 dia útil POR REGRA (não encerrada)"
            mem.update(regra="duração fixa", duracao_fixa=total, formula=formula)
        if status == "em_andamento" and dur == 0:
            dur = 1
        mem["duracao_calculada"] = dur
        ativs.append(AtividadeCPM(
            id=a["id"], duracao=dur, calendario=a["calendario"], tipo=tipo, status=status,
            inicio_real=None if base else ordinal(a.get("inicio_real")),
            termino_real=None if base else ordinal(a.get("termino_real")),
            restricao_inicio=ordinal(a.get("restricao_inicio")),
            restricao_termino=None if base else ordinal(a.get("restricao_termino")),
        ))
        memorias[a["id"]] = mem
    rels = [Relacao(r["predecessora"], r["sucessora"], r.get("tipo", "FS"), r.get("lag", 0))
            for r in projeto.dados["relacoes"]]
    return ativs, rels, memorias


def executar(projeto: Projeto, cenario: str, ajustes: list[Ajuste] | None = None,
             logica_progresso: str = "sobrepor") -> dict:
    """``logica_progresso``: "sobrepor" (padrão do beta) ou "retida" (padrão do P6), ver motor.calcular."""
    ativs, rels, mem = montar_entrada(projeto, cenario, ajustes)
    ds = None if cenario == "linha_base" else projeto.data_status
    res = calcular(ativs, rels, projeto.calendarios, projeto.inicio_projeto, data_status=ds,
                   logica_progresso=logica_progresso)
    por_id = {a.id: a for a in ativs}
    saida = {}
    for aid in res.ordem:
        a = por_id[aid]
        d = res.atividades[aid].como_dict(projeto.calendarios[a.calendario], a)
        d["duracao"] = a.duracao
        d["status"] = a.status
        d["memoria"] = mem[aid]
        saida[aid] = d
    return {
        "cenario": cenario,
        "data_status": iso(ds),
        "termino": iso(res.termino_projeto_data),
        "_termino_fronteira": res.termino_projeto,
        "caminho_critico": res.caminho_critico,
        "cadeia_determinante": res.cadeia_determinante,
        "atividades": saida,
        "ajustes": [a.__dict__ for a in (ajustes or [])] if cenario == "simulado" else [],
        "logica_progresso": logica_progresso,
    }


# ---------------------------------------------------------------------------
def comparar(projeto: Projeto, ref: dict, novo: dict) -> dict:
    """Diferenças entre dois resultados e explicação auditável do término."""
    cal_obra = projeto.calendarios[projeto.dados["meta"]["calendario_obra"]]
    # delta em dias úteis medido entre as DATAS exibidas (último dia), no calendário da obra
    delta_uteis = cal_obra.dias_uteis_entre(ordinal(ref["termino"]) + 1, ordinal(novo["termino"]) + 1)
    delta_corridos = ordinal(novo["termino"]) - ordinal(ref["termino"])
    mudancas, deslocadas = [], []
    for aid, n in novo["atividades"].items():
        r = ref["atividades"][aid]
        if n["duracao"] != r["duracao"]:
            mudancas.append({
                "id": aid,
                "nome": projeto.atividades[aid].get("nome") or aid,  # r18: atividade sem nome derrubava /api/comparacao
                "duracao_antes": r["duracao"], "duracao_depois": n["duracao"],
                "delta_duracao": n["duracao"] - r["duracao"],
                "folga_total_antes": r["folga_total"], "folga_total_depois": n["folga_total"],
                "critica_antes": r["critica"], "critica_depois": n["critica"],
                "memoria_antes": r["memoria"], "memoria_depois": n["memoria"],
                "termino_antes": r["termino"], "termino_depois": n["termino"],
            })
        if n["termino"] != r["termino"] or n["inicio"] != r["inicio"]:
            deslocadas.append({"id": aid, "inicio_antes": r["inicio"], "inicio_depois": n["inicio"],
                               "termino_antes": r["termino"], "termino_depois": n["termino"]})
    cc0, cc1 = set(ref["caminho_critico"]), set(novo["caminho_critico"])
    explicacao = []
    if not mudancas:
        explicacao.append("Nenhuma duração mudou entre os cenários.")
    cadeia_nova = set(novo["cadeia_determinante"])
    iso_efeito = _efeito_isolado(projeto, ref, {m["id"]: m["duracao_depois"] for m in mudancas})
    for m in mudancas:
        m["efeito_isolado_dias_uteis"] = iso_efeito.get(m["id"])
    for m in sorted(mudancas, key=lambda x: -abs(x["delta_duracao"])):
        ma, md = m["memoria_antes"], m["memoria_depois"]
        linha = f"{m['id']} ({m['nome']}): "
        if ma.get("regra") == "quantidade" and md.get("regra") == "quantidade":
            linha += (f"produtividade {ma['produtividade']:,} → {md['produtividade']:,} {md['unidade']}/equipe·dia, "
                      f"equipes {ma['equipes']} → {md['equipes']}; remanescente {md['quantidade_remanescente']:,} {md['unidade']} "
                      f"⇒ duração {m['duracao_antes']} → {m['duracao_depois']} dias úteis ({m['delta_duracao']:+d}). ")
        else:
            linha += (f"duração {m['duracao_antes']} → {m['duracao_depois']} ({m['delta_duracao']:+d}) "
                      f"[{ma.get('regra', '?')} → {md.get('regra', '?')}]. ")
        # O texto é decidido pelo EFEITO ISOLADO (contrafactual: refazer a referência trocando só
        # esta duração), não pela folga — folga total 0 herdada pelo INÍCIO (ligação SS) não é
        # folga de duração (revisão adversarial, rodada 2).
        ft = m["folga_total_antes"]
        e = m["efeito_isolado_dias_uteis"]
        outras = len(mudancas) > 1
        moveu = bool(delta_uteis or delta_corridos)
        if e is None:
            linha += "Atividade já concluída na referência: efeito isolado não se aplica."
        elif (m["delta_duracao"] > 0 and e < 0) or (m["delta_duracao"] < 0 and e > 0):
            # atividade "reversa": início fixado por FF/SF de entrada e sucessoras ligadas ao seu
            # INÍCIO (SS). Mudar a duração desloca o início no sentido oposto. É comportamento
            # correto do CPM, não erro (achado ao conferir a explicação pelo contrafactual).
            linha += (f"Paradoxo de rede (atividade reversa): o início é fixado por uma relação de término "
                      f"(FF/SF) e as sucessoras dependem do início; isoladamente esta mudança desloca o término "
                      f"em {e:+d} dia(s) útil(eis), no sentido OPOSTO ao da duração.")
        elif m["delta_duracao"] > 0:
            if e > 0:
                linha += (f"Isoladamente, este acréscimo move o término em {e:+d} dia(s) útil(eis): excede a folga "
                          f"(folga total era {ft}) e se propaga pelas sucessoras.")
            elif outras and moveu and m["id"] in cadeia_nova:
                linha += (f"Isoladamente seria absorvido (folga total era {ft}), mas somado às outras alterações "
                          f"da mesma cadeia passa a determinar o término.")
            elif ft is not None and m["delta_duracao"] >= ft and m["critica_depois"]:
                linha += (f"Consome toda a folga total ({ft}) e passa a ser crítica; isoladamente o término "
                          f"não muda (absorvido).")
            else:
                linha += f"Folga total era {ft}: isoladamente o acréscimo é absorvido e não empurra o término."
        else:
            if e < 0:
                linha += f"Isoladamente, esta redução antecipa o término em {e:+d} dia(s) útil(eis)."
            else:
                linha += "Isoladamente, esta redução não antecipa o término (a atividade não o determina sozinha)."
        explicacao.append(linha)
    if delta_uteis or delta_corridos:
        explicacao.append(
            f"Término da obra: {ref['termino']} → {novo['termino']} "
            f"({delta_uteis:+d} dias úteis no calendário da obra, {delta_corridos:+d} dias corridos).")
        explicacao.append("Cadeia determinante do novo término: " + " → ".join(novo["cadeia_determinante"]))
    else:
        explicacao.append(f"Término da obra inalterado ({novo['termino']}).")
    return {
        "ref": ref["cenario"], "alvo": novo["cenario"],
        "termino_ref": ref["termino"], "termino_alvo": novo["termino"],
        "delta_dias_uteis": delta_uteis, "delta_dias_corridos": delta_corridos,
        "duracoes_alteradas": mudancas,
        "atividades_deslocadas": len(deslocadas),
        "deslocadas": deslocadas[:200],
        "entraram_no_caminho_critico": sorted(cc1 - cc0),
        "sairam_do_caminho_critico": sorted(cc0 - cc1),
        "explicacao": explicacao,
    }


def _efeito_isolado(projeto: Projeto, ref: dict, novas: dict[str, int]) -> dict[str, int | None]:
    """Para cada atividade: dias úteis (calendário da obra) que o término da REFERÊNCIA andaria
    se SÓ a duração dela mudasse para o valor novo. None se concluída na referência."""
    ajustes_ref = [Ajuste(**d) for d in ref.get("ajustes", [])]
    ativs, rels, _ = montar_entrada(projeto, ref["cenario"], ajustes_ref)
    ds = None if ref["cenario"] == "linha_base" else projeto.data_status
    cal_obra = projeto.calendarios[projeto.dados["meta"]["calendario_obra"]]
    por_id = {a.id: a for a in ativs}
    logica = ref.get("logica_progresso", "sobrepor")
    base = calcular(ativs, rels, projeto.calendarios, projeto.inicio_projeto, data_status=ds, logica_progresso=logica)
    saida = {}
    for aid, dur in novas.items():
        a = por_id[aid]
        if a.status == "concluida":
            saida[aid] = None
            continue
        antigo, a.duracao = a.duracao, dur
        try:
            r = calcular(ativs, rels, projeto.calendarios, projeto.inicio_projeto, data_status=ds,
                         logica_progresso=logica)
        finally:
            a.duracao = antigo
        if r.termino_projeto == base.termino_projeto:
            saida[aid] = 0
        else:
            d = cal_obra.dias_uteis_entre(base.termino_projeto_data + 1, r.termino_projeto_data + 1)
            saida[aid] = d if d else (1 if r.termino_projeto > base.termino_projeto else -1)
    return saida


# ---------------------------------------------------------------- progresso
_FALTA = object()


def _ordinal_ou_falta(a: dict, chave: str):
    return ordinal(a[chave]) if chave in a else _FALTA


def preparar_progresso(projeto: Projeto, a: dict, r: dict, data_status: int | None) -> tuple:
    """Pré-calcula (uma vez por atividade e cenário) o que ``progresso_em`` usa em qualquer ``t``:
    calendário, datas já convertidas para ordinal e a fração executada na data de status.
    Otimização da curva S (muitas datas × atividades); a aritmética é a mesma de ``progresso_em``."""
    cal = projeto.calendarios[a["calendario"]]
    tipo = a.get("tipo", "tarefa")
    if tipo != "tarefa":
        return (False, tipo, ordinal(r["termino"]), ordinal(r["inicio"]) if tipo == "marco_inicio" else None)
    total = a.get("quantidade_total")
    exec_ds = (a.get("quantidade_executada", 0) / total) if total else a.get("percentual_executado", 0) / 100
    status = r["status"]
    if status == "concluida":
        exec_ds = 1.0
    es, ef = ordinal(r["es"]), ordinal(r["ef"])
    ini = fim = None
    if data_status is not None and status != "nao_iniciada":
        ini = _ordinal_ou_falta(a, "inicio_real")
        if status == "concluida":
            fim = _ordinal_ou_falta(a, "termino_real")
            fim = fim if fim is _FALTA else fim + 1
        else:
            fim = data_status
    return (True, cal, data_status, status, exec_ds, es, ef, ini, fim)


def progresso_preparado(prep: tuple, t: int) -> float:
    """``progresso_em`` sobre o resultado de ``preparar_progresso`` (mesmos ramos, mesma aritmética)."""
    if not prep[0]:
        _, tipo, termino, inicio = prep
        return 1.0 if t > termino or (tipo == "marco_inicio" and t >= inicio) else 0.0
    _, cal, ds, status, exec_ds, es, ef, ini, fim = prep
    if ds is not None and t <= ds and status != "nao_iniciada":
        if ini is _FALTA:
            raise KeyError("inicio_real")
        if fim is _FALTA:
            raise KeyError("termino_real")
        if t <= ini:
            return 0.0
        if t >= fim:
            return exec_ds
        return exec_ds * cal.dias_uteis_entre(ini, t) / max(1, cal.dias_uteis_entre(ini, fim))
    if ds is not None and t <= ds:
        return 0.0
    if status == "nao_iniciada" or ds is None:
        if t <= es:
            return 0.0
        if t >= ef:
            return 1.0
        return cal.dias_uteis_entre(es, t) / max(1, cal.dias_uteis_entre(es, ef))
    # em andamento, t > data de status
    if t >= ef:
        return 1.0
    ini_rem = max(ds, es)
    return exec_ds + (1 - exec_ds) * cal.dias_uteis_entre(ini_rem, t) / max(1, cal.dias_uteis_entre(ini_rem, ef))


def progresso_em(projeto: Projeto, a: dict, r: dict, t: int, data_status: int | None) -> float:
    """Fração executada (0..1) da atividade ``a`` na data ``t`` segundo o resultado ``r``.

    ``r`` é o resultado da ATIVIDADE; ``data_status`` é a do CENÁRIO (None na
    linha de base). Até a data de status usa o REAL (executado medido,
    interpolado em dias úteis entre o início real e a data de status). Depois
    dela usa a PREVISÃO do cenário, interpolada em dias úteis do calendário da
    atividade. Marcos: 0 ou 1.

    Para avaliar muitas datas, use ``preparar_progresso`` uma vez e ``progresso_preparado`` por data.
    """
    return progresso_preparado(preparar_progresso(projeto, a, r, data_status), t)


def iso_hoje(d: date | None = None) -> str:
    return (d or date.today()).isoformat()
