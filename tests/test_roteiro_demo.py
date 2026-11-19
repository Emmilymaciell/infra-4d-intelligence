"""O roteiro da demo (docs/DEMO-PESSOA-A.md) não pode envelhecer: cada número MARCADO bate com a API agora.

Mecanismo: o roteiro põe um marcador explícito imediatamente antes de cada número citado,

    a construtora prevê **<!-- n:ferrovia.painel.termino_construtora -->23/07/2027**

e este teste gera os números (``numeros_demo.coletar`` + as rotas de aceleração, recuperação, DCMA e histórico),
formata cada um no padrão pt-BR do documento e confere que o texto logo depois do marcador COMEÇA com ele
(ignorando espaços e o negrito ``**``). Nenhuma regex sobre o texto livre: só o marcador decide o que é conferido.

Regras: (1) marcador com chave desconhecida falha; (2) número divergente falha, dizendo o esperado e o achado;
(3) toda chave de EXIGIDAS tem de aparecer ao menos uma vez no roteiro (marcador apagado também falha).
O detector é testado num roteiro sintético (todas as chaves com o valor certo -> 0 erros; um número trocado -> 1 erro).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from ifc_opcional import SEM_IFC, requer_ifc

RAIZ = Path(__file__).resolve().parents[1]
ROTEIRO = RAIZ / "docs" / "DEMO-PESSOA-A.md"
MARCADOR = re.compile(r"<!--\s*n:([A-Za-z0-9_.\-]+)\s*-->")


# ------------------------------------------------------------------ formatos pt-BR do roteiro
def data(v):            # 2027-07-23 -> 23/07/2027
    return date.fromisoformat(v).strftime("%d/%m/%Y")


def data_curta(v):      # 2027-07-12 -> 12/07
    return date.fromisoformat(v).strftime("%d/%m")


def inteiro(v):         # 1500 -> 1.500
    return f"{int(v):,}".replace(",", ".")


def absoluto(v):        # −29 -> 29 ("29 dias antes")
    return inteiro(abs(int(v)))


def sinal(v):           # +27 / −17 / +0 (sinal de menos tipográfico)
    v = int(v)
    return f"+{v}" if v >= 0 else f"−{abs(v)}"


def dec(n):             # 71.69 -> 71,69 (n casas)
    return lambda v: f"{float(v):.{n}f}".replace(".", ",")


def pct_int(v):         # 1.0 -> 100%
    return f"{round(100 * float(v))}%"


def pct_sinal_int(v):   # 46.2 -> +46%
    return f"+{round(float(v))}%"


def mi(v):              # 1714224.9 -> R$ 1,71 mi
    return f"R$ {float(v) / 1e6:.2f} mi".replace(".", ",")


def vezes(v):           # 1.83 -> 1,8×
    return f"{float(v):.1f}×".replace(".", ",")


def vezes2(v):          # 1.3612 -> 1,36×
    return f"{float(v):.2f}×".replace(".", ",")


# ------------------------------------------------------------------ registro: chave -> (valor, formato)
def _registro(N: dict, X: dict) -> dict[str, tuple[object, callable]]:
    R = {}
    for o in ("ferrovia", "rodovia"):
        n, x = N["obras"][o], X[o]
        p, es, mc = n["painel"], n["earned_schedule"], n["monte_carlo"]
        R.update({
            f"{o}.obra.extensao_km": (n["obra"]["extensao_km"], inteiro),
            f"{o}.obra.lotes": (n["obra"]["lotes"], inteiro),
            f"{o}.obra.atividades": (n["obra"]["atividades"], inteiro),
            f"{o}.obra.relacoes": (n["obra"]["relacoes"], inteiro),
            f"{o}.obra.data_status": (n["obra"]["data_status"], data),
            f"{o}.painel.termino_linha_base": (p["termino_linha_base"], data),
            f"{o}.painel.termino_construtora": (p["termino_construtora"], data),
            f"{o}.painel.termino_independente": (p["termino_independente"], data),
            f"{o}.painel.delta_dias": (p["delta_independente_vs_construtora_dias"], inteiro),
            f"{o}.painel.delta_dias_sinal": (p["delta_independente_vs_construtora_dias"], sinal),
            f"{o}.painel.avanco_real_pct": (p["avanco_real_pct"], dec(2)),
            f"{o}.painel.avanco_lb_pct": (p["avanco_planejado_lb_pct"], dec(1)),
            f"{o}.painel.n_criticas": (p["n_criticas"], inteiro),
            f"{o}.painel.alerta_atividade": (x["alerta_atividade"], str),
            f"{o}.painel.alerta_pct": (x["alerta_pct"], str),
            f"{o}.es.spi": (es["spi"], dec(3)),
            f"{o}.es.termino": (es["ieac_termino"], data),
            f"{o}.es.diferenca_dias_abs": (es["diferenca_vs_cpm_dias"], absoluto),
            f"{o}.es.diferenca_dias_sinal": (es["diferenca_vs_cpm_dias"], sinal),
            f"{o}.mc.p50": (mc["p50"], data),
            f"{o}.mc.p50_curta": (mc["p50"], data_curta),
            f"{o}.mc.p80": (mc["p80"], data),
            f"{o}.mc.largura_dias": (mc["largura_p10_p90_dias"], inteiro),
            **{f"{o}.mc.criticidade.{i}.id": (a["id"], str) for i, a in enumerate(mc["criticidade_top"])},
            **{f"{o}.mc.criticidade.{i}.indice": (a["indice"], pct_int) for i, a in enumerate(mc["criticidade_top"])},
            f"{o}.balanco.conflitos": (n["linha_de_balanco"]["n_conflitos"], inteiro),
            f"{o}.balanco.conflitos_reais": (n["linha_de_balanco"]["n_conflitos_reais"], inteiro),
            f"{o}.sensibilidade.grupos": (n["sensibilidade"]["grupos"], inteiro),
            f"{o}.sensibilidade.execucoes": (n["sensibilidade"]["execucoes_motor"], inteiro),
            f"{o}.sensibilidade.piorar": (n["sensibilidade"]["maior"]["piorar_10pct_dias"], sinal),
            f"{o}.sensibilidade.melhorar": (n["sensibilidade"]["maior"]["melhorar_10pct_dias"], sinal),
            f"{o}.sensibilidade.mais_1_equipe": (n["sensibilidade"]["maior"]["mais_1_equipe_dias"], sinal),
            f"{o}.recuperacao.prazo": (n["recuperacao"]["prazo"], data),
            f"{o}.recuperacao.frentes": (n["recuperacao"]["frentes_no_plano"], inteiro),
            f"{o}.recuperacao.razao_max_melhor_semana": (x["razao_max"], vezes),
            f"{o}.recuperacao.razao_max_melhor_semana_2": (x["razao_max"], vezes2),
            f"{o}.recuperacao.frentes_inviaveis": (x["frentes_inviaveis"], inteiro),
            f"{o}.recuperacao.razao_min_inviaveis": (x["razao_min_inviaveis"], vezes2),
            f"{o}.recuperacao.razao_max_inviaveis": (x["razao_max_inviaveis"], vezes2),
            f"{o}.recuperacao.aumento_sobre_melhor_semana": (100 * (x["razao_max"] - 1), pct_sinal_int),
            f"{o}.aceleracao.termino": (x["acel_termino"], data),
            f"{o}.aceleracao.custo_mi": (x["acel_custo"], mi),
            f"{o}.cronograma.termino_arquivo": (n["cronograma_construtora"]["termino_arquivo"], data),
            f"{o}.cronograma.delta_dias": (n["cronograma_construtora"]["delta_dias"], sinal),
            f"{o}.cronograma.atividades_diferentes": (n["cronograma_construtora"]["atividades_com_diferenca"], inteiro),
            f"{o}.dcma.aprovados": (n["dcma_construtora"]["aprovados"], inteiro),
            f"{o}.dcma.reprovados": (n["dcma_construtora"]["reprovados"] if isinstance(
                n["dcma_construtora"]["reprovados"], int) else x["dcma_reprovados"], inteiro),
            f"{o}.dcma.nao_avaliados": (n["dcma_construtora"]["nao_avaliados"], inteiro),
            f"{o}.dcma.lags_pct": (x["dcma_lags_pct"], dec(1)),
            f"{o}.historico.termino_repetido": (n["historico"]["construtora_repetiu"]["termino"], data),
            f"{o}.historico.datas_repetidas": (n["historico"]["construtora_repetiu"]["n"], inteiro),
            f"{o}.historico.repetiu_de": (n["historico"]["construtora_repetiu"]["de"], data_curta),
            f"{o}.historico.repetiu_ate": (n["historico"]["construtora_repetiu"]["ate"], data),
            f"{o}.historico.independente_no_periodo": (x["hist_ind_no_periodo"], sinal),
            f"{o}.historico.independente_total": (x["hist_ind_total"], sinal),
            f"{o}.historico.construtora_total": (x["hist_con_total"], sinal),
            f"{o}.fiscalizacao.boletins": (n["fiscalizacao"]["n_boletins"], inteiro),
            f"{o}.fiscalizacao.divergencias": (n["fiscalizacao"]["n_divergencias"], inteiro),
            f"{o}.massas.diferenca_pct_abs": (abs(100 * n["massas"]["diferenca_relativa"]), dec(1)),
            f"{o}.massas.coerentes": (n["massas"]["coerentes"].split("/")[0], str),
            f"{o}.bi.tabelas": (n["exportacao_bi"]["tabelas"], inteiro),
            **{f"{o}.backtest.{m}.mae.{c}": (v, dec(1)) for m, d in x["backtest_mae"].items() for c, v in d.items()},
            **{f"{o}.produtividade.{k}.indice": (v["indice"], dec(3)) for k, v in x["produtividades"].items()},
            **{f"{o}.produtividade.{k}.boletins": (v["boletins"], inteiro) for k, v in x["produtividades"].items()},
            f"{o}.cobertura.obra.confianca": (x["cob_fim"]["confianca"], str),
            f"{o}.cobertura.obra.delta_sem_medicao_dias": (x["cob_fim"]["estresse"]["delta_sem_medicao_dias"], inteiro),
            f"{o}.cobertura.obra.delta_medida_dias": (x["cob_fim"]["estresse"]["delta_medida_dias"], inteiro),
            f"{o}.cobertura.obra.frentes_alerta_sem_medicao": (len(x["cob_fim"]["alerta_sem_medicao"]), inteiro),
            f"{o}.cobertura.confianca_todos_marcos": (x["cob_todos"], str),
            f"{o}.tendencia.obra.divergencia_desde": (x["tend_div"], data),
        })
        for i, s in enumerate(n["simulacao"]):
            R[f"{o}.simulacao.{i}.termino_antes_curta"] = (s["termino_antes"], data_curta)
            R[f"{o}.simulacao.{i}.termino_depois"] = (s["termino_depois"], data)
            R[f"{o}.simulacao.{i}.delta"] = (s["delta_dias_corridos"], sinal)
        if n["ifc"].get("disponivel"):
            ifc = n["ifc"]
            R.update({f"{o}.ifc.elementos": (ifc["elementos"], inteiro),
                      f"{o}.ifc.com_vinculo": (ifc["com_vinculo"], inteiro),
                      f"{o}.ifc.tarefas": (ifc["tarefas_ifc"], inteiro),
                      f"{o}.ifc.alinhamentos": (ifc["alinhamentos"], inteiro),
                      f"{o}.ifc.erros_validacao": (ifc["erros_validacao"], inteiro)})
    return {k: (v, f) for k, (v, f) in R.items() if v is not None}


def _extras(c) -> dict:
    """Números do roteiro que ``numeros_demo`` ainda não devolve, lidos das mesmas rotas."""
    out = {}
    for o in ("ferrovia", "rodovia"):
        g = lambda url, **p: c.get(url, params={"obra": o, **p}).json()  # noqa: E731
        pn = g("/api/painel")
        m = re.match(r"(\S+) é CRÍTICA e produz (\d+)% do planejado", (pn["alertas"] or [{}])[0].get("texto", ""))
        ac = g("/api/aceleracao")
        rc = g("/api/recuperacao")
        dc = g("/api/dcma", cenario="construtora")
        ev = g("/api/historico/evolucao")["pontos"]
        rep, atual = None, None                   # mesma regra de numeros_demo._maior_repeticao
        for i, pto in enumerate(ev):
            if atual and pto["termino_construtora"] == ev[atual[0]]["termino_construtora"]:
                atual[1] = i
            else:
                atual = [i, i]
            if rep is None or atual[1] - atual[0] > rep[1] - rep[0]:
                rep = list(atual)
        d = lambda a, b: (date.fromisoformat(b) - date.fromisoformat(a)).days  # noqa: E731
        razoes = [x.get("razao_melhor_semana") or 0 for x in rc.get("plano", [])]
        inviaveis = [x.get("razao_melhor_semana") or 0 for x in rc.get("plano", [])
                     if x.get("viabilidade") == "inviavel_sem_mudanca_de_metodo"]
        bt = g("/api/backtest")
        mae = {}
        for mm in bt.get("marcos", []):
            ref = mm["por_referencia"].get("realidade_simulada")
            if ref:                                    # M-L1-FIM -> "L1"; M-FIM -> "obra"
                mae[mm["id"][2:-4] if mm["id"] != "M-FIM" else "obra"] = ref["mae_dias"]
        prods = {f"{x['lote_id']}_{x['servico_id']}": x for x in pn.get("produtividades", []) if x.get("indice") is not None}
        cob = g("/api/cobertura")["marcos"]
        confs = {m_["confianca"] for m_ in cob}
        tend = next(m_ for m_ in g("/api/tendencia", passo_dias=7)["marcos"] if m_["id"] == "M-FIM")
        out[o] = {
            "alerta_atividade": m.group(1) if m else None, "alerta_pct": m.group(2) if m else None,
            "acel_termino": ac.get("termino_alcancado"), "acel_custo": ac.get("custo_adicional_total"),
            "razao_max": max(razoes) if razoes else None,
            "frentes_inviaveis": len(inviaveis),
            "razao_min_inviaveis": min(inviaveis, default=None), "razao_max_inviaveis": max(inviaveis, default=None),
            "backtest_mae": mae, "produtividades": prods,
            "cob_fim": next(m_ for m_ in cob if m_["id"] == "M-FIM"),
            "cob_todos": confs.pop() if len(confs) == 1 else "mista",
            "tend_div": tend["divergencia_desde"],
            "dcma_reprovados": dc["resumo"]["reprovados"],
            "dcma_lags_pct": next((p.get("valor") for p in dc["pontos"] if p["numero"] == 3), None),
            "hist_ind_no_periodo": d(ev[rep[0]]["termino_independente"], ev[rep[1]]["termino_independente"]),
            "hist_ind_total": d(ev[0]["termino_independente"], ev[-1]["termino_independente"]),
            "hist_con_total": d(ev[0]["termino_construtora"], ev[-1]["termino_construtora"]),
        }
    return out


@pytest.fixture(scope="module")
def registro():
    from fastapi.testclient import TestClient

    from infra4d.api import criar_app
    from infra4d.numeros_demo import coletar
    try:
        import ifcopenshell  # noqa: F401
        validar_ifc = True
    except ImportError:
        validar_ifc = False
    N = coletar(validar_ifc=validar_ifc)
    with TestClient(criar_app()) as c:
        X = _extras(c)
    return _registro(N, X)


# números que o roteiro TEM de citar com marcador (lista combinada com o orquestrador, 2026-11-13)
EXIGIDAS = {
    "rodovia.cobertura.obra.confianca", "rodovia.cobertura.obra.delta_sem_medicao_dias",
    "rodovia.cobertura.obra.delta_medida_dias", "rodovia.cobertura.obra.frentes_alerta_sem_medicao",
    "ferrovia.cobertura.confianca_todos_marcos", "rodovia.tendencia.obra.divergencia_desde",
    "ferrovia.aceleracao.custo_mi", "ferrovia.aceleracao.termino", "ferrovia.backtest.L1.mae.construtora",
    "ferrovia.backtest.L1.mae.es_pf1", "ferrovia.backtest.L1.mae.es_spi", "ferrovia.backtest.L1.mae.independente",
    "ferrovia.balanco.conflitos", "ferrovia.balanco.conflitos_reais", "ferrovia.bi.tabelas",
    "ferrovia.cronograma.atividades_diferentes", "ferrovia.cronograma.delta_dias",
    "ferrovia.cronograma.termino_arquivo", "ferrovia.dcma.aprovados", "ferrovia.dcma.lags_pct",
    "ferrovia.dcma.nao_avaliados", "ferrovia.dcma.reprovados", "ferrovia.es.diferenca_dias_abs", "ferrovia.es.spi",
    "ferrovia.es.termino", "ferrovia.fiscalizacao.boletins", "ferrovia.fiscalizacao.divergencias",
    "ferrovia.ifc.com_vinculo", "ferrovia.ifc.elementos", "ferrovia.ifc.erros_validacao", "ferrovia.ifc.tarefas",
    "ferrovia.massas.coerentes", "ferrovia.massas.diferenca_pct_abs", "ferrovia.mc.criticidade.0.id",
    "ferrovia.mc.criticidade.1.id", "ferrovia.mc.criticidade.2.id", "ferrovia.mc.criticidade.2.indice",
    "ferrovia.mc.largura_dias", "ferrovia.mc.p50", "ferrovia.mc.p80", "ferrovia.obra.atividades",
    "ferrovia.obra.data_status", "ferrovia.obra.extensao_km", "ferrovia.obra.lotes", "ferrovia.obra.relacoes",
    "ferrovia.painel.alerta_atividade", "ferrovia.painel.alerta_pct", "ferrovia.painel.avanco_lb_pct",
    "ferrovia.painel.avanco_real_pct", "ferrovia.painel.delta_dias", "ferrovia.painel.n_criticas",
    "ferrovia.painel.termino_construtora", "ferrovia.painel.termino_independente", "ferrovia.recuperacao.frentes",
    "ferrovia.recuperacao.prazo", "ferrovia.recuperacao.razao_max_melhor_semana",
    "ferrovia.sensibilidade.execucoes", "ferrovia.sensibilidade.grupos", "ferrovia.sensibilidade.mais_1_equipe",
    "ferrovia.sensibilidade.melhorar", "ferrovia.sensibilidade.piorar", "ferrovia.simulacao.0.delta",
    "ferrovia.simulacao.0.termino_antes_curta", "ferrovia.simulacao.0.termino_depois",
    "ferrovia.simulacao.1.delta", "rodovia.aceleracao.custo_mi", "rodovia.aceleracao.termino",
    "rodovia.balanco.conflitos", "rodovia.balanco.conflitos_reais", "rodovia.es.diferenca_dias_sinal",
    "rodovia.es.termino", "rodovia.fiscalizacao.boletins", "rodovia.historico.construtora_total",
    "rodovia.historico.datas_repetidas", "rodovia.historico.independente_no_periodo",
    "rodovia.historico.independente_total", "rodovia.historico.repetiu_ate", "rodovia.historico.repetiu_de",
    "rodovia.historico.termino_repetido", "rodovia.ifc.elementos", "rodovia.ifc.tarefas",
    "rodovia.massas.coerentes", "rodovia.mc.p50_curta", "rodovia.mc.p80", "rodovia.obra.atividades",
    "rodovia.obra.extensao_km", "rodovia.obra.lotes", "rodovia.obra.relacoes", "rodovia.painel.alerta_atividade",
    "rodovia.painel.alerta_pct", "rodovia.painel.delta_dias_sinal", "rodovia.painel.termino_construtora",
    "rodovia.painel.termino_independente", "rodovia.produtividade.L2_CBU.boletins",
    "rodovia.produtividade.L2_CBU.indice", "rodovia.recuperacao.frentes", "rodovia.recuperacao.frentes_inviaveis",
    "rodovia.recuperacao.prazo", "rodovia.recuperacao.razao_max_inviaveis",
    "rodovia.recuperacao.razao_min_inviaveis", "rodovia.sensibilidade.mais_1_equipe",
    "rodovia.sensibilidade.piorar",
}


# ------------------------------------------------------------------ conferência
def conferir(texto: str, registro: dict) -> list[str]:
    """Erros: chave desconhecida ou número que não bate. Texto depois do marcador: ignora espaços e '**'."""
    erros = []
    for m in MARCADOR.finditer(texto):
        chave = m.group(1)
        if chave not in registro:
            erros.append(f"marcador desconhecido: {chave}")
            continue
        valor, fmt = registro[chave]
        esperado = fmt(valor)
        depois = texto[m.end():m.end() + 80].lstrip(" * ")
        normal = lambda s: s.replace("−", "-")  # noqa: E731 — "−" e "-" valem igual na conferência
        if not normal(depois).startswith(normal(esperado)):
            achado = re.split(r"[*|\n]", depois, maxsplit=1)[0][:40]
            erros.append(f"{chave}: esperado {esperado!r}, no roteiro {achado!r}")
    return erros


def _chave_ifc(chave: str) -> bool:
    return ".ifc." in chave


def test_cada_numero_marcado_no_roteiro_bate_com_a_api(registro):
    texto = ROTEIRO.read_text(encoding="utf-8")
    erros = conferir(texto, registro)
    if SEM_IFC:  # sem ifcopenshell a API não produz os números de IFC: conferidos no teste *_ifc_* (SKIP)
        erros = [e for e in erros if not (e.startswith("marcador desconhecido: ") and _chave_ifc(e.split(": ", 1)[1]))]
    assert not erros, "roteiro desatualizado (rode numeros_demo e corrija):\n" + "\n".join(erros)


def test_toda_chave_exigida_esta_marcada_no_roteiro(registro):
    exigidas = {k for k in EXIGIDAS if not (SEM_IFC and _chave_ifc(k))}
    assert exigidas <= set(registro), f"chaves exigidas sem valor na API: {sorted(exigidas - set(registro))}"
    presentes = set(MARCADOR.findall(ROTEIRO.read_text(encoding="utf-8")))
    faltam = sorted(exigidas - presentes)
    assert not faltam, f"{len(faltam)} número(s) exigido(s) sem marcador no roteiro: {faltam}"


@requer_ifc
def test_numeros_de_ifc_do_roteiro_existem_na_api_e_batem(registro):
    """Com o ifcopenshell: as chaves *.ifc.* exigidas têm valor na API e o roteiro as marca com o número certo."""
    ifc = {k for k in EXIGIDAS if _chave_ifc(k)}
    assert len(ifc) >= 6 and ifc <= set(registro), sorted(ifc - set(registro))
    texto = ROTEIRO.read_text(encoding="utf-8")
    assert ifc <= set(MARCADOR.findall(texto))
    assert [e for e in conferir(texto, registro) if ".ifc." in e] == []


def test_detector_ve_numero_trocado(registro):
    """Roteiro sintético com todas as chaves: 0 erros; trocar UM número -> exatamente 1 erro, que o nomeia;
    marcador com chave inventada -> erro."""
    linhas = [f"- **<!-- n:{k} -->{f(v)}** texto" for k, (v, f) in registro.items()]
    texto = "\n".join(linhas)
    assert conferir(texto, registro) == []
    chave = "ferrovia.painel.termino_independente"
    certo = registro[chave][1](registro[chave][0])
    trocado = texto.replace(f"<!-- n:{chave} -->{certo}", f"<!-- n:{chave} -->10/09/2027" if certo != "10/09/2027"
                            else f"<!-- n:{chave} -->11/09/2027")
    erros = conferir(trocado, registro)
    assert len(erros) == 1 and chave in erros[0]
    assert conferir(texto + "\n<!-- n:ferrovia.nao.existe -->1", registro) == ["marcador desconhecido: ferrovia.nao.existe"]


def test_detector_no_roteiro_real_com_numero_trocado(registro, tmp_path):
    """Cópia TEMPORÁRIA do roteiro com o 1º número marcado trocado: o teste tem de falhar nela."""
    texto = ROTEIRO.read_text(encoding="utf-8")
    m = MARCADOR.search(texto)
    if m is None:
        pytest.skip("roteiro ainda sem marcadores")
    valor, fmt = registro[m.group(1)]
    certo = fmt(valor)
    ini = texto.index(certo, m.end())
    copia = tmp_path / "roteiro.md"
    copia.write_text(texto[:ini] + "99" + certo + texto[ini + len(certo):], encoding="utf-8")
    assert any(m.group(1) in e for e in conferir(copia.read_text(encoding="utf-8"), registro))
