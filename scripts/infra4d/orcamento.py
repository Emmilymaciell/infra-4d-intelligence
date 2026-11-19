"""BIM 5D SINTÉTICO: composições FICTÍCIAS, orçamento, curva S financeira e EVM de custo.

TUDO AQUI É FICTÍCIO. Nenhum número vem do SICRO ou do SINAPI (a base do SICRO no portal do DNIT
está sob CC BY-ND 3.0 e os termos do SINAPI não foram verificados — docs/research/R05 §5). Só a
ESTRUTURA espelha a deles: código, unidade, custo unitário decomposto em mão de obra, equipamento,
material e transporte, e BDI aplicado sobre o custo direto.

Regras (declaradas):

- composição por (tipo de obra, ``servico_id``); a unidade da composição TEM de ser a da atividade —
  divergência é erro (``ErroOrcamento``), nunca conversão implícita. Atividade de duração fixa (sem
  quantidade) é orçada como verba: unidade ``vb``, quantidade 1.
- preço de venda unitário = custo direto × (1 + BDI). Todo valor de EVM (PV, EV, AC, BAC) está nessa
  mesma base (preço de venda), para os índices serem comparáveis.
- BDI DECLARADO POR OBRA (fictício): componentes AC, S+G, R, DF, L e I por tipo de obra, combinados pela
  fórmula do TCU (Acórdão 2622/2013): BDI = ((1+AC+S+G+R)·(1+DF)·(1+L)) / (1−I) − 1. Os dois valores
  ficam DENTRO da faixa do acórdão para "construção de rodovias e ferrovias" (1º quartil 19,60%,
  3º quartil 24,23%; docs/research/R11). Um ``bdi`` explícito na chamada substitui o da obra.
- REAJUSTE (fictício): R = V × (Ii − I0) / I0 (variáveis da IN 01/DNIT/2023, art. 5º), com ÍNDICE
  SINTÉTICO por disciplina (taxa mensal fictícia, NÃO é série do DNIT/FGV). Data-base = ``meta.data_base_
  orcamento`` ou o 1º dia do mês de início; anualidade: no ano k ≥ 1 após a data-base vale o índice do
  k-ésimo aniversário (Lei 14.133, art. 25 §7º; Lei 10.192, art. 2º §1º). Os valores COM reajuste saem
  ao lado dos valores a preços iniciais; nada é sobrescrito.
- BAC da atividade = quantidade total × preço de venda.
- PV(t): BAC espalhado por igual nos dias úteis (calendário da atividade) da LINHA DE BASE
  ``[inicio_lb, termino_lb]``; o valor de um dia entra na fronteira de fim do dia (convenção de
  ``calendario.py``: ``t`` = início do dia).
- EV na data de status = executado × preço (``quantidade_executada``; verba: 100 % se concluída, senão
  ``percentual_executado``). É a ÂNCORA: EV do EVM = Σ EV por serviço (revisão r9).
- EV(t), só a DISTRIBUIÇÃO no tempo dessa âncora: pelo perfil dos boletins (cada boletim entra na fronteira
  ``min(semana_inicio + 7, término real + 1, data de status)`` — a MESMA regra de "semana terminada" da MTA
  (``tendencia.py``) e da curva S física/financeira (``curva_s.py``); com peso proporcional à sua quantidade, escalado para fechar
  no executado); sem boletim, por igual nos dias úteis de ``inicio_real`` até o término real ou a data
  de status; sem início real, inteiro na data de status. Boletins que não fecham com o executado viram
  AVISO no resumo (a âncora não muda).
- linha de base obrigatória: ``inicio_lb``/``termino_lb`` em AAAA-MM-DD, término ≥ início e ao menos um
  dia útil no calendário da atividade; senão ``ErroOrcamento`` (senão o BAC entraria sem nunca virar PV).
- quantidades negativas são erro. Preços e valores não são arredondados no cálculo; a saída arredonda
  só na exibição (valores em R$ com 2 casas, preço unitário com 4).
- só roda em obra com ``meta.ficticio is True`` (marca booleana; o texto do aviso não decide).
- AC(t) SINTÉTICO: cada parcela de EV × fator de custo FICTÍCIO por (lote, serviço), sorteado de forma
  determinística (semente da obra + lote + serviço) em U(0,92; 1,18). Não existe custo real nos dados.
- EVM na data de status: CV = EV − AC; SV = EV − PV; CPI = EV ÷ AC; SPI = EV ÷ PV;
  EAC = BAC ÷ CPI; ETC = EAC − AC; VAC = BAC − EAC; TCPI = (BAC − EV) ÷ (BAC − AC).
"""

from __future__ import annotations

import math
import random
import re
from bisect import bisect_right
from collections import defaultdict
from datetime import date

from .calendario import iso, ordinal
from .cenarios import Projeto
from .obra import ErroTipoObra
from .obra import tipo_obra as _tipo_obra_declarado

AVISO = ("ORÇAMENTO FICTÍCIO — composições, preços, BDI e custo real (AC) inventados para demonstração. "
         "Não são SICRO, SINAPI nem preço de mercado.")
# Faixa do TCU para "construção de rodovias e ferrovias" (Acórdão 2622/2013-Plenário), vista em planilhas
# públicas que citam o acórdão [B]; texto do acórdão no TCU não aberto (R11 §1).
FAIXA_BDI_TCU = {"q1": 0.1960, "medio": 0.2097, "q3": 0.2423,
                 "fonte": "TCU, Acórdão 2622/2013-Plenário, construção de rodovias e ferrovias (R11 §1)"}
# Componentes FICTÍCIOS por tipo de obra (frações). I = PIS 0,65% + COFINS 3,00% + ISS 2,00% (fictício),
# sem CPRB (premissa: folha não desonerada). Todos dentro das faixas por componente citadas no R11.
_FONTE_BDI = ("FICTÍCIO, declarado em orcamento.BDI_DECLARADO; componentes escolhidos dentro das faixas do "
              "TCU, Acórdão 2622/2013, construção de rodovias e ferrovias (docs/research/R11 §1)")
BDI_DECLARADO = {   # a única declaração de BDI por tipo de obra (marca fictícia + fonte)
    "ferrovia": {"ficticio": True, "fonte": _FONTE_BDI,
                 "componentes": {"AC": 0.055, "SG": 0.005, "R": 0.013, "DF": 0.010, "L": 0.075, "I": 0.0565}},
    "rodovia": {"ficticio": True, "fonte": _FONTE_BDI,
                "componentes": {"AC": 0.050, "SG": 0.005, "R": 0.012, "DF": 0.010, "L": 0.070, "I": 0.0565}},
}
BDI_COMPONENTES = {t: d["componentes"] for t, d in BDI_DECLARADO.items()}   # visão derivada (compatibilidade)


def bdi_tcu(c: dict) -> float:
    """Fórmula do TCU (Acórdão 2622/2013): ((1+AC+S+G+R)(1+DF)(1+L)) / (1−I) − 1."""
    return (1 + c["AC"] + c["SG"] + c["R"]) * (1 + c["DF"]) * (1 + c["L"]) / (1 - c["I"]) - 1


def bdi_da_obra(tipo: str) -> float:
    """BDI declarado da obra (``BDI_DECLARADO``). Tipo sem declaração é ERRO, nunca valor padrão."""
    d = BDI_DECLARADO.get(tipo)
    if d is None:
        raise ErroOrcamento(f"sem BDI declarado para o tipo de obra {tipo!r} (BDI_DECLARADO)")
    return bdi_tcu(d["componentes"])


def validar_bdi(bdi) -> float:
    """BDI explícito (``bdi=``): número real finito e >= 0. bool, texto, NaN, ±inf e negativo são ERRO."""
    if isinstance(bdi, bool) or not isinstance(bdi, (int, float)):
        raise ErroOrcamento(f"bdi inválido: {bdi!r} (esperado número real >= 0, ex.: 0.25 para 25%)")
    if not math.isfinite(bdi) or bdi < 0:
        raise ErroOrcamento(f"bdi inválido: {bdi!r} (tem de ser finito e >= 0)")
    return float(bdi)


def _bdi_efetivo(tipo: str, bdi) -> float:
    return bdi_da_obra(tipo) if bdi is None else validar_bdi(bdi)


def bdi_nota(tipo: str, bdi: float | None = None) -> str:
    """Nota do BDI USADO. Com ``bdi`` explícito, a nota diz que foi informado (e qual), não o declarado."""
    b = bdi_da_obra(tipo)
    if bdi is not None:
        return (f"BDI INFORMADO na chamada (bdi=) = {100 * validar_bdi(bdi):.2f}%: é o usado nesta resposta. "
                f"Não é o BDI declarado da obra ({tipo}, {100 * b:.2f}% pela fórmula do TCU, em bdi_declarado).")
    return (f"BDI fictício da obra ({tipo}) = {100 * b:.2f}% pela fórmula do TCU com componentes declarados "
            f"(BDI_DECLARADO, fictício); dentro da faixa {100 * FAIXA_BDI_TCU['q1']:.2f}%–{100 * FAIXA_BDI_TCU['q3']:.2f}% "
            f"de {FAIXA_BDI_TCU['fonte']}. Não é referência de mercado.")


# Reajuste: disciplina de índice por serviço (nomes da IN 01/DNIT/2023, art. 3º) e taxa mensal FICTÍCIA.
DISCIPLINA_REAJUSTE = {
    "ferrovia": {"SUP": "TERRAPLENAGEM", "TER": "TERRAPLENAGEM", "DRE": "DRENAGEM",
                 "SUB": "PAVIMENTACAO",      # analogia declarada: camada granular (bases e sub-bases)
                 "DOR": "VIA_PERMANENTE", "GRA": "VIA_PERMANENTE", "LAS": "VIA_PERMANENTE",
                 "SOL": "VIA_PERMANENTE", "SIN": "VIA_PERMANENTE",
                 "OAE-FUN": "OAE", "OAE-MES": "OAE", "OAE-SUE": "OAE"},
    "rodovia": {"SUP": "TERRAPLENAGEM", "TER": "TERRAPLENAGEM", "DRE": "DRENAGEM",
                "SBB": "PAVIMENTACAO", "BGS": "PAVIMENTACAO", "IMP": "PAVIMENTACAO", "CBU": "PAVIMENTACAO",
                "SHV": "SINALIZACAO_HORIZONTAL", "SVV": "SINALIZACAO_VERTICAL",
                "DEF": "OBRAS_COMPLEMENTARES", "LIB": "OBRAS_COMPLEMENTARES",
                "OAE-FUN": "OAE", "OAE-MES": "OAE", "OAE-SUE": "OAE"},
}
TAXA_MENSAL_FICTICIA = {"TERRAPLENAGEM": 0.0045, "DRENAGEM": 0.0040, "PAVIMENTACAO": 0.0060,
                        "SINALIZACAO_HORIZONTAL": 0.0035, "SINALIZACAO_VERTICAL": 0.0035,
                        "OBRAS_COMPLEMENTARES": 0.0038, "VIA_PERMANENTE": 0.0050, "OAE": 0.0042}
AVISO_REAJUSTE = ("ÍNDICES DE REAJUSTE SINTÉTICOS (FICTÍCIOS): I(m) = 100 × (1 + taxa)^m por disciplina; "
                  "não são os índices DNIT/FGV.")
FAIXA_FATOR_CUSTO = (0.92, 1.18)
SIMULACAO_DO_USUARIO = ("não aplicada: o orçamento usa a linha de base e o executado medido na data de status "
                        "(EVM); ajustes de simulação do usuário não mudam BAC, PV, EV nem AC")
SISTEMA_CLASSIFICACAO = "INFRA4D-FICTICIO"


class ErroOrcamento(ValueError):
    """Orçamento inconsistente (composição ausente ou unidade divergente)."""


def _c(codigo, nome, unidade, mo, eq, mat, tra):
    return {"codigo": codigo, "descricao": nome, "unidade": unidade,
            "custo_direto": {"mao_de_obra": mo, "equipamento": eq, "material": mat, "transporte": tra}}


# custo direto unitário em R$ — FICTÍCIO (ordem de grandeza plausível, sem fonte)
_FER = [
    ("SUP", _c("FIC-FER-SUP-001", "Supressão vegetal e limpeza (fictícia)", "ha", 3430.0, 5390.0, 196.0, 784.0)),
    ("TER", _c("FIC-FER-TER-001", "Corte, aterro e compactação (fictícia)", "m³", 1.48, 11.47, 0.0, 5.55)),
    ("DRE", _c("FIC-FER-DRE-001", "Drenagem: bueiros e dispositivos (fictícia)", "m", 345.0, 172.5, 517.5, 115.0)),
    ("SUB", _c("FIC-FER-SUB-001", "Sublastro compactado (fictícia)", "m³", 9.2, 32.2, 32.2, 18.4)),
    ("DOR", _c("FIC-FER-DOR-001", "Dormente de concreto distribuído (fictícia)", "un", 33.6, 29.4, 315.0, 42.0)),
    ("GRA", _c("FIC-FER-GRA-001", "Assentamento de grade com trilho (fictícia)", "km",
               147500.0, 236000.0, 2360000.0, 206500.0)),
    ("LAS", _c("FIC-FER-LAS-001", "Lastro, levante e socaria (fictícia)", "m³", 13.2, 36.3, 82.5, 33.0)),
    ("SOL", _c("FIC-FER-SOL-001", "Soldagem aluminotérmica (fictícia)", "un", 740.0, 185.0, 832.5, 92.5)),
    ("SIN", _c("FIC-FER-SIN-001", "Sinalização, testes e liberação (verba fictícia)", "vb",
               1200000.0, 600000.0, 2700000.0, 300000.0)),
]
_ROD = [
    ("SUP", _c("FIC-ROD-SUP-001", "Supressão vegetal e limpeza da faixa (fictícia)", "ha", 3010.0, 4730.0, 172.0, 688.0)),
    ("TER", _c("FIC-ROD-TER-001", "Corte, aterro e compactação (fictícia)", "m³", 1.35, 10.48, 0.0, 5.07)),
    ("DRE", _c("FIC-ROD-DRE-001", "Drenagem: bueiros e dispositivos (fictícia)", "m", 294.0, 147.0, 441.0, 98.0)),
    ("SBB", _c("FIC-ROD-SBB-001", "Reforço do subleito e sub-base (fictícia)", "m³", 7.8, 27.3, 27.3, 15.6)),
    ("BGS", _c("FIC-ROD-BGS-001", "Base de brita graduada simples (fictícia)", "m³", 10.8, 33.75, 64.8, 25.65)),
    ("IMP", _c("FIC-ROD-IMP-001", "Imprimação (fictícia)", "m²", 0.62, 1.56, 5.07, 0.55)),
    ("CBU", _c("FIC-ROD-CBU-001", "Concreto asfáltico usinado a quente (fictícia)", "t", 31.2, 104.0, 338.0, 46.8)),
    ("SHV", _c("FIC-ROD-SHV-001", "Sinalização horizontal (fictícia)", "m", 4.2, 2.8, 6.3, 0.7)),
    ("SVV", _c("FIC-ROD-SVV-001", "Sinalização vertical: placa (fictícia)", "un", 380.0, 190.0, 1235.0, 95.0)),
    ("DEF", _c("FIC-ROD-DEF-001", "Defensa metálica (fictícia)", "m", 46.5, 31.0, 217.0, 15.5)),
    ("LIB", _c("FIC-ROD-LIB-001", "Vistoria, as built e liberação (verba fictícia)", "vb", 210000.0, 70000.0, 35000.0, 35000.0)),
]
_OAE = [
    ("OAE-FUN", "Fundação: estaca (fictícia)", "un", 9600.0, 14400.0, 21600.0, 2400.0),
    ("OAE-MES", "Mesoestrutura: apoio (fictícia)", "un", 78000.0, 52000.0, 117000.0, 13000.0),
    ("OAE-SUE", "Superestrutura: vão (fictícia)", "un", 237500.0, 190000.0, 475000.0, 47500.0),
]
COMPOSICOES: dict[str, dict[str, dict]] = {
    "ferrovia": dict(_FER) | {s: _c(f"FIC-FER-{s}-001", n, u, *v) for s, n, u, *v in _OAE},
    "rodovia": dict(_ROD) | {s: _c(f"FIC-ROD-{s}-001", n, u, *v) for s, n, u, *v in _OAE},
}
for _tipo, _comps in COMPOSICOES.items():   # cada composição sabe a sua obra (BDI e reajuste dela)
    for _c_ in _comps.values():
        _c_["tipo_obra"] = _tipo

# O vínculo classe IFC ↔ serviço tem UMA fonte de verdade: o exportador (``ifc/exportar.py``,
# ``classe_ifc`` e tabelas de estilo). Este módulo só a LÊ (revisão do agente de IFC: o mapa manual antigo
# divergia em 3 pontos). A quantidade que liga o modelo ao orçamento é a que o exportador grava em
# ``INFRA4D_Quantidade.QuantidadeContratual``, na unidade do serviço convertida para SI do modelo.


class MapaIfcIndisponivel(ErroOrcamento):
    """O exportador IFC (e o ifcopenshell) não está disponível neste ambiente."""


def _exportador():
    try:
        from .ifc import exportar as exp
        from .ifc import quantidades as qt
    except ImportError as e:  # ifcopenshell é opcional (ADR-0002)
        raise MapaIfcIndisponivel(f"mapa IFC indisponível: exportador IFC não carregou ({e})") from None
    return exp, qt


def mapa_ifc(tipo: str) -> list[dict]:
    """Serviço → (classe, PredefinedType, ObjectType, composição, quantidade), DERIVADO do exportador."""
    if tipo not in COMPOSICOES:
        raise ErroOrcamento(f"sem composições fictícias para o tipo de obra {tipo!r}")
    exp, qt = _exportador()
    out = []
    for serv, comp in COMPOSICOES[tipo].items():
        sem_peca = exp.estilo_conhecido(tipo, serv) is None
        classe, predef, objtype = exp.classe_ifc(tipo, serv)
        fator_si = qt.UNIDADES.get(comp["unidade"], (None, None))[1]
        out.append({"tipo_obra": tipo, "servico_id": serv, "codigo": comp["codigo"], "unidade": comp["unidade"],
                    "classe_ifc": None if sem_peca else classe,
                    "predefined_type": None if sem_peca else predef,
                    "object_type": None if sem_peca else objtype,
                    "sem_elemento": sem_peca,
                    "qto": None if sem_peca or fator_si is None else qt.QSET_SERVICO,
                    "quantidade": None if sem_peca or fator_si is None else "QuantidadeContratual",
                    "fator_para_unidade": None if sem_peca or not fator_si else 1.0 / fator_si,
                    "qto_oficial": None if sem_peca else (qt.QTO_OFICIAL.get(classe) or (None,))[0]})
    return out


def classificacao_ifc(tipo: str, classe_ifc: str, predefined_type: str | None = None,
                      object_type: str | None = None) -> dict | None:
    """Composição para um elemento IFC pela (classe, PredefinedType[, ObjectType]) do EXPORTADOR.

    Se mais de um serviço usa a mesma classe/tipo (ex.: SBB e BGS são IfcCourse PAVEMENT na rodovia),
    devolve ``ambiguo`` com os candidatos: nesse caso vale a IfcClassificationReference gravada no elemento."""
    cands = [m for m in mapa_ifc(tipo) if not m["sem_elemento"] and m["classe_ifc"] == classe_ifc
             and (predefined_type is None or m["predefined_type"] == predefined_type)
             and (object_type is None or m["object_type"] == object_type)]
    if not cands:
        return None
    if len(cands) > 1:
        return {"ambiguo": True, "candidatos": [m["codigo"] for m in cands],
                "motivo": "mais de um serviço com a mesma classe/tipo no exportador; use a "
                          "IfcClassificationReference do próprio elemento", "ficticio": True}
    m = cands[0]
    comp = COMPOSICOES[tipo][m["servico_id"]]
    return {"IfcClassificationReference": {"Identification": comp["codigo"], "Name": comp["descricao"],
                                           "ReferencedSource": {"IfcClassification": {
                                               "Source": "INFRA 4D", "Name": SISTEMA_CLASSIFICACAO,
                                               "Edition": "fictícia"}}},
            "servico_id": m["servico_id"], "qto": m["qto"], "quantidade": m["quantidade"],
            "fator_para_unidade": m["fator_para_unidade"], "unidade": comp["unidade"], "ficticio": True}


# =========================================================================== composições
def tipo_obra(projeto: Projeto) -> str:
    """``meta.tipo_obra`` DECLARADO, pelo helper único ``obra.tipo_obra`` (P8). Ausente, vazio, não-texto ou
    desconhecido é ERRO: ``ErroTipoObra`` vira ``ErroOrcamento`` com a mesma mensagem (→ 422). O orçamento nunca
    cai em "ferrovia" por padrão silencioso (composições, BDI e reajuste dependem do tipo)."""
    try:
        return _tipo_obra_declarado(projeto)
    except ErroTipoObra as e:
        raise ErroOrcamento(str(e)) from None


def preco_venda(comp: dict, bdi: float | None = None) -> float:
    """Custo direto × (1 + BDI). Sem ``bdi``, vale o BDI declarado da obra da composição."""
    if bdi is None:
        tipo = comp.get("tipo_obra")   # gravado a partir da CHAVE de COMPOSICOES, não do texto do código
        if tipo is None:
            raise ErroOrcamento(f"composição {comp.get('codigo')!r} sem tipo de obra: informe bdi= explícito")
        bdi = bdi_da_obra(tipo)
    else:
        bdi = validar_bdi(bdi)
    return round(sum(comp["custo_direto"].values()) * (1 + bdi), 6)


def tabela(tipo: str, bdi: float | None = None) -> list[dict]:
    if tipo not in COMPOSICOES:
        raise ErroOrcamento(f"sem composições fictícias para o tipo de obra {tipo!r}")
    bdi = _bdi_efetivo(tipo, bdi)
    out = []
    for serv, c in COMPOSICOES[tipo].items():
        cd = sum(c["custo_direto"].values())
        out.append({"servico_id": serv, **c, "custo_direto_unitario": round(cd, 2), "bdi": bdi,
                    "preco_venda_unitario": round(cd * (1 + bdi), 4), "ficticio": True})
    return out


def orcar_atividades(projeto: Projeto, bdi: float | None = None) -> list[dict]:
    """Uma linha por atividade com serviço. Levanta ErroOrcamento listando TODAS as inconsistências."""
    comps = COMPOSICOES.get(tipo_obra(projeto))
    if comps is None:
        raise ErroOrcamento(f"sem composições fictícias para o tipo de obra {tipo_obra(projeto)!r}")
    bdi = _bdi_efetivo(tipo_obra(projeto), bdi)
    erros, linhas = [], []
    for a in projeto.dados["atividades"]:
        serv = a.get("servico_id")
        if not serv or a.get("tipo", "tarefa") != "tarefa":
            continue
        comp = comps.get(serv)
        if comp is None:
            erros.append(f"{a['id']}: serviço {serv} sem composição")
            continue
        por_qtd = bool(a.get("quantidade_total"))
        un_ativ = a.get("unidade") if por_qtd else "vb"
        if un_ativ != comp["unidade"]:
            erros.append(f"{a['id']}: unidade da atividade {un_ativ!r} ≠ unidade da composição "
                         f"{comp['codigo']} {comp['unidade']!r}")
            continue
        qt = float(a["quantidade_total"]) if por_qtd else 1.0
        if por_qtd:
            qe = float(a.get("quantidade_executada", 0.0))
        else:
            qe = 1.0 if a.get("status") == "concluida" else float(a.get("percentual_executado", 0.0)) / 100
        if qt < 0 or qe < 0:
            erros.append(f"{a['id']}: quantidade negativa (total {qt:g}, executado {qe:g})")
            continue
        erro_lb = _erro_linha_de_base(projeto, a)
        if erro_lb:
            erros.append(f"{a['id']}: {erro_lb}")
            continue
        pv = preco_venda(comp, bdi)
        linhas.append({"atividade_id": a["id"], "lote_id": a.get("lote_id"), "servico_id": serv,
                       "codigo": comp["codigo"], "unidade": comp["unidade"], "quantidade_total": qt,
                       "quantidade_executada": qe, "preco_venda_unitario": pv,
                       "custo_direto_orcado": qt * sum(comp["custo_direto"].values()),
                       "bac": qt * pv, "ev_na_data_status": qe * pv})
    if erros:
        raise ErroOrcamento("orçamento inconsistente: " + "; ".join(erros))
    return linhas


def _erro_linha_de_base(projeto: Projeto, a: dict) -> str | None:
    ini, fim = a.get("inicio_lb"), a.get("termino_lb")
    if not all(isinstance(x, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", x) for x in (ini, fim)):
        return f"linha de base ausente ou fora do formato AAAA-MM-DD (inicio_lb={ini!r}, termino_lb={fim!r})"
    try:
        d0, d1 = ordinal(ini), ordinal(fim)
    except ValueError:
        return f"data inválida na linha de base ({ini}, {fim})"
    if d1 < d0:
        return f"linha de base invertida (término {fim} antes do início {ini})"
    cal = projeto.calendarios.get(a.get("calendario"))
    if cal is None:
        return f"calendário desconhecido {a.get('calendario')!r}"
    if not any(cal.eh_util(d) for d in range(d0, d1 + 1)):
        return f"linha de base {ini}..{fim} sem dia útil no calendário {cal.id}: o PV nunca chegaria ao BAC"
    return None


def fator_custo(semente, lote, servico) -> float:
    return round(random.Random(f"{semente}|custo|{lote}|{servico}").uniform(*FAIXA_FATOR_CUSTO), 3)


# =========================================================================== reajuste (fictício)
_RE_DATA = re.compile(r"\d{4}-\d{2}-\d{2}")


def data_base(projeto: Projeto) -> date:
    """``meta.data_base_orcamento`` (texto AAAA-MM-DD) ou, ausente, o dia 1 do mês de início da obra.
    Valor presente e malformado é ERRO (ErroOrcamento → 422), nunca cai no padrão."""
    meta = projeto.dados.get("meta", {})
    if "data_base_orcamento" in meta and meta["data_base_orcamento"] is not None:
        v = meta["data_base_orcamento"]
        if not isinstance(v, str) or not _RE_DATA.fullmatch(v):
            raise ErroOrcamento(f"meta.data_base_orcamento inválida: {v!r} (use AAAA-MM-DD)")
        try:
            return date.fromisoformat(v)
        except ValueError:
            raise ErroOrcamento(f"meta.data_base_orcamento inválida: {v!r} (data inexistente)") from None
    ini = date.fromordinal(projeto.inicio_projeto)
    return date(ini.year, ini.month, 1)


def anos_completos(base: date, d: date) -> int:
    """Anos completos da data-base até ``d``, pela data INTEIRA: o aniversário é o mesmo dia e mês
    (data-base 15/11/2025 → 1º aniversário 15/11/2026). Data-base em 29/02 completa o ano em 01/03 nos anos
    não bissextos (o "dia imediato" quando falta a correspondência exata). Antes da data-base: 0."""
    anos = d.year - base.year - ((d.month, d.day) < (base.month, base.day))
    return max(0, anos)


def indice_sintetico(disciplina: str, meses: int) -> float:
    """I(m) = 100 × (1 + taxa)^m — FICTÍCIO."""
    if disciplina not in TAXA_MENSAL_FICTICIA:
        raise ErroOrcamento(f"sem índice sintético para a disciplina {disciplina!r}")
    return 100.0 * (1 + TAXA_MENSAL_FICTICIA[disciplina]) ** meses


def fator_reajuste(tipo: str, servico: str, base: date, dia: date) -> float:
    """1 + R/V para o serviço executado no ``dia``: Ii/I0 com Ii = índice do último aniversário da
    data-base (anualidade); 1,0 no primeiro ano."""
    disc = DISCIPLINA_REAJUSTE.get(tipo, {}).get(servico)
    if disc is None:
        raise ErroOrcamento(f"serviço {servico!r} sem disciplina de reajuste na obra {tipo!r}")
    anos = anos_completos(base, dia)
    if anos == 0:
        return 1.0
    return indice_sintetico(disc, 12 * anos) / indice_sintetico(disc, 0)


# =========================================================================== eventos no tempo
def _eventos(projeto: Projeto, linhas: list[dict], reajuste: bool = False) -> dict[str, list[tuple[int, float]]]:
    """Eventos (fronteira t, valor) de PV, EV e AC; com ``reajuste``, cada parcela × fator do dia em que
    foi (ou seria) executada (dia = fronteira − 1)."""
    ds = projeto.data_status
    tipo = tipo_obra(projeto)
    base = data_base(projeto)
    semente = projeto.dados.get("meta", {}).get("semente", 0)
    ativ = projeto.atividades
    bol = defaultdict(list)
    for m in projeto.dados.get("medicoes", []):
        bol[m["atividade_id"]].append(m)
    ev_pv = {"pv": [], "ev": [], "ac": []}
    for ln in linhas:
        a = ativ[ln["atividade_id"]]
        cal = projeto.calendarios[a["calendario"]]
        f = fator_custo(semente, a.get("lote_id"), a.get("servico_id"))
        if reajuste:
            fr = lambda t, s=a.get("servico_id"): fator_reajuste(tipo, s, base, date.fromordinal(t - 1))  # noqa: E731
        else:
            fr = lambda t: 1.0  # noqa: E731
        # PV: linha de base
        d0, d1 = ordinal(a["inicio_lb"]), ordinal(a["termino_lb"])
        dias = [d for d in range(d0, d1 + 1) if cal.eh_util(d)]
        for d in dias:
            ev_pv["pv"].append((d + 1, ln["bac"] / len(dias) * fr(d + 1)))
        # EV / AC: âncora = executado × preço; boletins/datas reais só distribuem no tempo
        alvo = ln["ev_na_data_status"]
        evs = []
        if alvo > 0:
            fim_real = ordinal(a["termino_real"]) + 1 if a.get("termino_real") else ds
            pesos = [(min(ordinal(m["semana_inicio"]) + 7, fim_real, ds), float(m["quantidade"]))
                     for m in bol.get(a["id"], []) if a.get("quantidade_total") and float(m["quantidade"]) > 0]
            soma = sum(q for _, q in pesos)
            if soma > 0:
                evs = [(t, alvo * q / soma) for t, q in pesos]
            elif a.get("inicio_real"):
                fim = ordinal(a["termino_real"]) + 1 if a.get("termino_real") else ds
                dias = [d for d in range(ordinal(a["inicio_real"]), min(fim, ds)) if cal.eh_util(d)]
                evs = [(d + 1, alvo / len(dias)) for d in dias] if dias else [(ds, alvo)]
            else:
                evs = [(ds, alvo)]
        evs = [(t, v * fr(t)) for t, v in evs]
        ev_pv["ev"] += evs
        ev_pv["ac"] += [(t, v * f) for t, v in evs]
    return ev_pv


def _acumulador(eventos: list[tuple[int, float]]):
    ev = sorted(eventos)
    ts = [t for t, _ in ev]
    acc, s = [], 0.0
    for _, v in ev:
        s += v
        acc.append(s)

    def em(t: int) -> float:
        i = bisect_right(ts, t)
        return acc[i - 1] if i else 0.0
    return em


def exigir_obra_ficticia(projeto: Projeto) -> None:
    """AC sintético só em obra com a marca booleana ``meta.ficticio is True`` (o texto do aviso não decide;
    mesma regra de fiscalizacao.obra_ficticia — revisão adversarial r6)."""
    meta = projeto.dados.get("meta", {})
    if not (isinstance(meta, dict) and meta.get("ficticio") is True):
        raise ErroOrcamento("custo real (AC) sintético só é gerado para obra com meta.ficticio = true; "
                            "obra sem a marca não recebe custo inventado")


def _filtrar(linhas, lote):
    return [ln for ln in linhas if not lote or ln["lote_id"] == lote]


# =========================================================================== EVM
def evm(projeto: Projeto, linhas: list[dict], reajuste: bool = False) -> dict:
    """EVM na data de status. Com ``reajuste``, BAC = Σ PV reajustado (orçamento projetado com reajuste)."""
    ds = projeto.data_status
    e = _eventos(projeto, linhas, reajuste)
    pv, ev, ac = (_acumulador(e[k])(ds) for k in ("pv", "ev", "ac"))
    bac = sum(v for _, v in e["pv"]) if reajuste else sum(ln["bac"] for ln in linhas)
    cpi = ev / ac if ac else None
    spi = ev / pv if pv else None
    eac = bac / cpi if cpi else None
    r2 = lambda x: None if x is None else round(x, 2)  # noqa: E731
    r4 = lambda x: None if x is None else round(x, 4)  # noqa: E731
    return {"bac": r2(bac), "pv": r2(pv), "ev": r2(ev), "ac": r2(ac), "cv": r2(ev - ac), "sv": r2(ev - pv),
            "cpi": r4(cpi), "spi": r4(spi), "eac": r2(eac), "etc": r2(None if eac is None else eac - ac),
            "vac": r2(None if eac is None else bac - eac),
            "tcpi": r4((bac - ev) / (bac - ac) if bac != ac else None),
            "percentual_fisico_financeiro": r4(ev / bac if bac else None)}


def _avisos_boletins(projeto: Projeto, linhas: list[dict]) -> list[str]:
    """Boletins que não fecham com o executado (o EV continua ancorado no executado)."""
    soma = defaultdict(float)
    for m in projeto.dados.get("medicoes", []):
        soma[m.get("atividade_id")] += float(m.get("quantidade", 0) or 0)
    out = []
    for ln in linhas:
        a = projeto.atividades[ln["atividade_id"]]
        if a.get("quantidade_total") and abs(soma[a["id"]] - ln["quantidade_executada"]) > 1e-3:
            out.append(f"{a['id']}: boletins somam {soma[a['id']]:g} e o executado é "
                       f"{ln['quantidade_executada']:g}; EV ancorado no executado")
    return out


def resumo(projeto: Projeto, lote: str | None = None, bdi: float | None = None) -> dict:
    exigir_obra_ficticia(projeto)
    tipo = tipo_obra(projeto)
    explicito = bdi
    bdi = _bdi_efetivo(tipo, bdi)
    linhas = orcar_atividades(projeto, bdi)
    lotes = sorted({ln["lote_id"] for ln in linhas})
    if lote and lote not in lotes:
        raise ErroOrcamento(f"lote sem atividades orçadas: {lote}")
    sel = _filtrar(linhas, lote)
    por_serv = defaultdict(lambda: [0.0, 0.0, None])
    for ln in sel:
        x = por_serv[ln["servico_id"]]
        x[0] += ln["bac"]
        x[1] += ln["ev_na_data_status"]
        x[2] = ln["codigo"]
    sem, com = evm(projeto, sel), evm(projeto, sel, reajuste=True)
    return {"aviso": AVISO, "ficticio": True, "simulacao_do_usuario": SIMULACAO_DO_USUARIO,
            "bdi": round(bdi, 6), "bdi_nota": bdi_nota(tipo, explicito),
            "bdi_declarado": BDI_DECLARADO.get(tipo), "faixa_bdi_tcu": FAIXA_BDI_TCU,
            "reajuste": {"aviso": AVISO_REAJUSTE, "data_base": data_base(projeto).isoformat(),
                         "formula": "R = V × (Ii − I0) / I0; Ii = índice do último aniversário da data-base",
                         "taxas_mensais_ficticias": TAXA_MENSAL_FICTICIA,
                         "reajuste_ev_ate_data_status": round(com["ev"] - sem["ev"], 2),
                         "evm_com_reajuste": com},
            "avisos": _avisos_boletins(projeto, sel),
            "data_status": projeto.dados["meta"]["data_status"], "lote": lote,
            "regras": "PV pela linha de base; EV = executado × preço de venda (boletins só distribuem no tempo); AC SINTÉTICO = EV × fator "
                      f"fictício por (lote, serviço) em U{FAIXA_FATOR_CUSTO}; EAC = BAC ÷ CPI",
            "evm": sem,
            "por_lote": [] if lote else [{"lote_id": l, **evm(projeto, _filtrar(linhas, l))} for l in lotes],
            "por_servico": [{"servico_id": s, "codigo": v[2], "bac": round(v[0], 2), "ev": round(v[1], 2)}
                            for s, v in sorted(por_serv.items())],
            "fatores_custo_ficticios": {f"{l}/{s}": fator_custo(projeto.dados["meta"].get("semente", 0), l, s)
                                        for l, s in sorted({(ln["lote_id"], ln["servico_id"]) for ln in sel})}}


def curva_s(projeto: Projeto, lote: str | None = None, passo_dias: int = 7, bdi: float | None = None) -> dict:
    """Curva S financeira acumulada (PV até o fim da linha de base; EV e AC até a data de status)."""
    exigir_obra_ficticia(projeto)
    if passo_dias < 1:
        raise ErroOrcamento("passo_dias deve ser >= 1")
    linhas = orcar_atividades(projeto, bdi)
    if lote and lote not in {ln["lote_id"] for ln in linhas}:
        raise ErroOrcamento(f"lote sem atividades orçadas: {lote}")
    sel = _filtrar(linhas, lote)
    e = _eventos(projeto, sel)
    pv, ev, ac = (_acumulador(e[k]) for k in ("pv", "ev", "ac"))
    er = _eventos(projeto, sel, reajuste=True)
    pvr, evr, acr = (_acumulador(er[k]) for k in ("pv", "ev", "ac"))
    ds = projeto.data_status
    t0 = projeto.inicio_projeto
    fim = max([t for t, _ in e["pv"]] + [ds])
    ts = sorted(set(range(t0, fim + 1, passo_dias)) | {ds, fim})
    pontos = [{"data": iso(t), "pv": round(pv(t), 2),
               "ev": round(ev(t), 2) if t <= ds else None, "ac": round(ac(t), 2) if t <= ds else None,
               "pv_reajustado": round(pvr(t), 2),
               "ev_reajustado": round(evr(t), 2) if t <= ds else None,
               "ac_reajustado": round(acr(t), 2) if t <= ds else None}
              for t in ts]
    return {"aviso": AVISO, "ficticio": True, "simulacao_do_usuario": SIMULACAO_DO_USUARIO,
            "lote": lote, "data_status": iso(ds),
            "convencao": "data = fronteira (início do dia); valores acumulados em R$ fictícios, preço de venda",
            "bac": round(sum(ln["bac"] for ln in sel), 2),
            "bac_reajustado": round(sum(v for _, v in er["pv"]), 2), "aviso_reajuste": AVISO_REAJUSTE,
            "pontos": pontos}
