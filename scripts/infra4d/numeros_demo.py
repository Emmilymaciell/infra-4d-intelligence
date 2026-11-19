"""Números do roteiro da demonstração (docs/DEMO-PESSOA-A.md), lidos da API AGORA.

Uso:   python -m infra4d.numeros_demo            (a partir de scripts/, ou com scripts/ no PYTHONPATH)
       python -m infra4d.numeros_demo --json     (saída em JSON)

Roda a API em memória (FastAPI TestClient, sem servidor e sem rede), sobre as obras FICTÍCIAS de
``examples/synthetic/``. Não altera dados nem o repositório:
- o banco do histórico vai para um diretório temporário (variável INFRA4D_BANCO, restaurada no fim);
- a simulação é aplicada e desfeita (DELETE /api/simulacao) num app próprio;
- o IFC exportado é validado em memória (ifcopenshell.validate), se o ifcopenshell estiver instalado.

Todo número do roteiro deve vir daqui. Se um valor mudar, rode de novo e atualize o documento.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date

OBRAS = ("ferrovia", "rodovia")

# Exemplos fixos da interface para a ferrovia (web/simulacao.js, EXEMPLOS_FERROVIA)
EXEMPLOS_FERROVIA = [
    {"atividade_id": "L3-S04-TER", "produtividade": 1500, "equipes": 2},
    {"atividade_id": "L2-S04-LAS", "produtividade": 250, "equipes": 1},
]


def _dias(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def _exemplos_genericos(projeto: dict, ind: dict) -> list[dict]:
    """Mesma regra de web/simulacao.js para obras sem exemplo fixo: crítica de maior duração a 0,8× e
    com maior folga a 0,6× da produtividade do cenário independente (3 algarismos significativos)."""
    ajust = [a for a in projeto["atividades"]
             if a.get("tipo") == "tarefa" and a.get("quantidade_total") and a.get("status") != "concluida"]
    com = [(a, ind["atividades"].get(a["id"])) for a in ajust]
    com = [(a, r) for a, r in com if r and r.get("memoria", {}).get("produtividade")]
    crit = sorted([x for x in com if x[1]["critica"]], key=lambda x: -(x[1].get("duracao") or 0))
    folga = sorted([x for x in com if not x[1]["critica"] and x[1]["folga_total"] > 0],
                   key=lambda x: -x[1]["folga_total"])
    out = []
    if crit:
        a, r = crit[0]
        out.append({"atividade_id": a["id"], "produtividade": float(f"{r['memoria']['produtividade'] * 0.8:.3g}")})
    if folga:
        a, r = folga[0]
        out.append({"atividade_id": a["id"], "produtividade": float(f"{r['memoria']['produtividade'] * 0.6:.3g}")})
    return out


def _maior_repeticao(pontos: list[dict], chave: str) -> dict:
    """Maior sequência de datas de status seguidas com o mesmo término (``chave``)."""
    melhor, atual = None, None
    for p in pontos:
        if atual and p[chave] == atual["termino"]:
            atual["n"] += 1
            atual["ate"] = p["data_status"]
        else:
            atual = {"termino": p[chave], "n": 1, "de": p["data_status"], "ate": p["data_status"]}
        if melhor is None or atual["n"] > melhor["n"]:
            melhor = dict(atual)
    return melhor or {}


def _ifc(c, obra: str) -> dict:
    try:
        import ifcopenshell
        import ifcopenshell.validate
    except ImportError:
        return {"disponivel": False, "motivo": "ifcopenshell não instalado no .venv"}
    r = c.get("/api/ifc/exportar", params={"obra": obra})
    if r.status_code != 200:
        return {"disponivel": False, "motivo": f"/api/ifc/exportar respondeu {r.status_code}"}
    f = ifcopenshell.file.from_string(r.content.decode("latin-1"))
    log = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(f, log, express_rules=True)
    v = c.get("/api/ifc/vinculo", params={"obra": obra}).json()
    return {"disponivel": True, "schema": f.schema_identifier, "tamanho_kb": round(len(r.content) / 1024),
            "erros_validacao": len(log.statements), "elementos": v["resumo"]["elementos"],
            "com_vinculo": v["resumo"]["com_vinculo"], "tarefas_ifc": v["resumo"]["tarefas_ifc"],
            "alinhamentos": v["resumo"]["alinhamentos"], "classe_instalacao": v["tipo_obra"]}


def _uma_obra(c, obra: str, iteracoes_mc: int, validar_ifc: bool) -> dict:
    g = lambda url, **p: c.get(url, params={"obra": obra, **p})  # noqa: E731
    proj = g("/api/projeto").json()
    pn = g("/api/painel").json()
    t = pn["terminos"]
    es = g("/api/previsao/earned-schedule").json()
    es0 = next(r for r in es["resultados"] if r.get("lote") is None)
    mc = g("/api/previsao-probabilistica", iteracoes=iteracoes_mc, com_criticidade=True).json()
    crit = mc["criticidade"]["atividades"][:3]

    # simulação: aplicar e desfazer
    ind = g("/api/cenarios/independente").json()
    exemplos = EXEMPLOS_FERROVIA if obra == "ferrovia" else _exemplos_genericos(proj, ind)
    sims = []
    for ex in exemplos:
        r = c.post("/api/simulacao", params={"obra": obra}, json={"ajustes": [ex]})
        cmp_ = r.json()["comparacao"]
        sims.append({"ajuste": ex, "termino_antes": cmp_["termino_ref"], "termino_depois": cmp_["termino_alvo"],
                     "delta_dias_corridos": cmp_["delta_dias_corridos"]})
    c.delete("/api/simulacao", params={"obra": obra})

    conf = g("/api/recursos/conflitos-balanco").json()
    xml = g("/api/cronograma/exportar/mspdi", cenario="construtora").content
    cr = c.post("/api/cronograma/comparar", params={"obra": obra, "cenario": "independente", "formato": "mspdi"},
                content=xml, headers={"Content-Type": "application/xml"}).json()
    ev = g("/api/historico/evolucao").json()
    rep = _maior_repeticao(ev["pontos"], "termino_construtora")
    rc = g("/api/recuperacao").json()
    dc = g("/api/dcma", cenario="construtora").json()
    se = g("/api/sensibilidade").json()
    top = se["grupos"][0]
    fis = g("/api/fiscalizacao/conciliacao").json()
    orc = g("/api/orcamento/resumo").json()["evm"]
    coer = g("/api/massas/coerencia").json()["total"]
    dmt = g("/api/produtividade/terraplenagem").json()["efeito_no_termino"]
    tab = g("/api/exportar/tabelas").json()["tabelas"]

    return {
        "obra": {"nome": proj["ferrovia"].get("nome"), "tipo": proj["obra"]["tipo"],
                 "extensao_km": proj["ferrovia"].get("extensao_km"), "lotes": len(proj["lotes"]),
                 "atividades": len(proj["atividades"]), "relacoes": len(proj["relacoes"]),
                 "data_status": proj["meta"]["data_status"], "ficticio": proj["meta"].get("ficticio")},
        "painel": {"termino_linha_base": t["linha_base"], "termino_construtora": t["construtora"],
                   "termino_independente": t["independente"],
                   "delta_independente_vs_construtora_dias": _dias(t["construtora"], t["independente"]),
                   "avanco_real_pct": pn["avanco_real"], "avanco_planejado_lb_pct": pn["avanco_planejado_lb"],
                   "n_criticas": len(pn["criticas_independente"]),
                   "alerta_principal": (pn["alertas"] or [{}])[0].get("texto")},
        "earned_schedule": {"spi": es0["SPI"], "ieac_termino": es0["IEAC_spi_termino"],
                            "diferenca_vs_cpm_dias": es0["diferenca_es_spi_vs_cpm_independente_dias"]},
        "monte_carlo": {"iteracoes": mc["iteracoes"], "p50": mc["p50"], "p80": mc["p80"],
                        "largura_p10_p90_dias": mc["largura_p10_p90_dias"],
                        "criticidade_top": [{"id": a["id"], "indice": a["indice"],
                                             "correlacao": a["correlacao_duracao_termino"]} for a in crit]},
        "simulacao": sims,
        "linha_de_balanco": {"n_conflitos": conf["n_conflitos"], "n_conflitos_reais": conf["n_conflitos_reais"]},
        "cronograma_construtora": {"termino_arquivo": cr["termino_importado"], "termino_motor": cr["termino_motor"],
                                   "delta_dias": cr["delta_termino_dias_corridos"],
                                   "atividades_com_diferenca": cr["n_com_diferenca"]},
        "historico": {"construtora_repetiu": rep, "narrativa": ev["narrativa"]},
        "recuperacao": {"prazo": rc["prazo"], "termino_atual": rc["termino_atual"],
                        "termino_alcancado": rc["termino_alcancado"], "cumpre_prazo": rc["cumpre_prazo"],
                        "dias_alem_do_prazo": _dias(rc["prazo"], rc["termino_alcancado"]),
                        "viabilidade": rc["viabilidade"], "motivo": rc["motivo"], "frentes_no_plano": len(rc["plano"])},
        "dcma_construtora": {**dc["resumo"],
                             "reprovados": [f'{p["numero"]}. {p["nome"]}' for p in dc["pontos"] if p["aprovado"] is False]},
        "sensibilidade": {"grupos": len(se["grupos"]), "execucoes_motor": se["execucoes_motor"],
                          "maior": {"lote": top["lote_id"], "servico": top["servico_id"],
                                    "piorar_10pct_dias": top["piorar"]["delta_dias_corridos"],
                                    "melhorar_10pct_dias": top["melhorar"]["delta_dias_corridos"],
                                    "mais_1_equipe_dias": top["equipes"]["delta_dias_corridos"]}},
        "ifc": _ifc(c, obra) if validar_ifc else {"disponivel": False, "motivo": "validação desligada"},
        "fiscalizacao": {"ok": fis["ok"], "n_boletins": fis["n_boletins"], "n_divergencias": fis["n_divergencias"]},
        "orcamento_ficticio": {"bac": orc["bac"], "cpi": orc["cpi"], "spi": orc["spi"]},
        "massas": {"diferenca_relativa": round(coer["diferenca_relativa"], 3),
                   "coerentes": f'{coer["n_coerentes"]}/{coer["n_segmentos"]}'},
        "produtividade_dmt": None if not dmt else {"termino_pela_geometria": dmt["termino_pela_geometria"],
                                                   "delta_dias": dmt["delta_dias_corridos"]},
        "exportacao_bi": {"tabelas": len(tab)},
    }


def coletar(obras=OBRAS, iteracoes_mc: int = 200, validar_ifc: bool = True) -> dict:
    """Números do roteiro por obra. Não grava nada fora de um diretório temporário."""
    from fastapi.testclient import TestClient

    from .api import criar_app

    antes = os.environ.get("INFRA4D_BANCO")
    with tempfile.TemporaryDirectory(prefix="infra4d-demo-") as tmp:
        os.environ["INFRA4D_BANCO"] = os.path.join(tmp, "demo.sqlite")
        try:
            app = criar_app()
            with TestClient(app) as c:
                saida = {"gerado_em": date.today().isoformat(),
                         "modulos_ligados": len(app.state.rotas_ligadas),
                         "modulos_indisponiveis": dict(app.state.rotas_indisponiveis),
                         "obras": {o: _uma_obra(c, o, iteracoes_mc, validar_ifc) for o in obras}}
        finally:
            if antes is None:
                os.environ.pop("INFRA4D_BANCO", None)
            else:
                os.environ["INFRA4D_BANCO"] = antes
    return saida


def _texto(d: dict) -> str:
    linhas = [f"Números da demo — gerados em {d['gerado_em']} (dados FICTÍCIOS); "
              f"módulos ligados: {d['modulos_ligados']}, indisponíveis: {d['modulos_indisponiveis'] or 'nenhum'}"]
    for obra, n in d["obras"].items():
        linhas.append(f"\n=== {obra} ===")
        for secao, v in n.items():
            linhas.append(f"{secao}: {json.dumps(v, ensure_ascii=False)}")
    return "\n".join(linhas)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    # R14: com saída redirecionada no Windows o stdout é cp1252 e '→' quebrava com UnicodeEncodeError
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    d = coletar()
    if "--json" in argv:
        print(json.dumps(d, ensure_ascii=False, indent=1))
    else:
        print(_texto(d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
