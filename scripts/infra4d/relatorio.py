"""Relatório técnico imprimível (HTML) da previsão independente.

Gerado no servidor a partir dos MESMOS resultados do motor que alimentam o painel —
nenhum número é digitado à mão. Pensado para imprimir/salvar em PDF pelo navegador.

Rota: GET /api/relatorio?obra=<id>  →  text/html

Seções de análise (8 a 12) leem as MESMAS funções, com os MESMOS parâmetros padrão, das rotas
correspondentes (nada é recalculado à mão): riscos_prazo.registro (/api/riscos?rapido=true),
tendencia.tendencia (/api/tendencia), recuperacao.recuperar (/api/recuperacao),
aceleracao.acelerar (/api/aceleracao), backtest.backtest (/api/backtest) e cobertura.cobertura
(/api/cobertura). Cada seção tolera módulo ausente ou falha ("indisponível") e fica em cache
por obra (identidade dos dados), como nas rotas. O tempo de geração é declarado no rodapé.
"""

from __future__ import annotations

import threading
import time
from datetime import date
from html import escape

from fastapi import APIRouter, FastAPI, Query
from fastapi.responses import HTMLResponse

from .calendario import ordinal
from .cenarios import comparar
from .painel import alertas, avanco, produtividades

def ligar(app: FastAPI, obter_estado) -> None:
    """Cria o router POR APP, com closure sobre ``obter_estado``. Antes, um global de módulo
    fazia o último ``criar_app`` sequestrar o relatório de todos os apps (rodada 4)."""
    router = APIRouter(prefix="/api")

    @router.get("/relatorio", response_class=HTMLResponse,
                responses={404: {"description": "Obra desconhecida"}})
    def relatorio(obra: str | None = Query(default=None)):
        """Relatório técnico imprimível (HTML) da previsão independente, gerado dos mesmos resultados do motor."""
        est = obter_estado(obra)
        obra_id = obra or next((k for k, v in getattr(app.state.obras, "_estados", {}).items() if v is est), "padrão")
        return HTMLResponse(gerar_html(est, obra_id, obra=obra))

    app.include_router(router)


def _br(iso: str | None) -> str:
    return "—" if not iso else date.fromisoformat(iso).strftime("%d/%m/%Y")


def _num(v, casas=2) -> str:
    if v is None:
        return "—"
    s = f"{v:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


# ----------------------------------------------------------------------------- análises (seções 8 a 12)
_cache_lock = threading.Lock()
_cache: list[tuple[object, tuple, object]] = []


def _cacheado(dados, chave: tuple, f):
    with _cache_lock:
        for d, k, v in _cache:
            if d is dados and k == chave:
                return v, True
    v = f()
    with _cache_lock:
        _cache.append((dados, chave, v))
        del _cache[:-32]
    return v, False


def analises(est, obra: str | None = None) -> dict:
    """Valores das seções 8 a 12, lidos das funções dos módulos com os parâmetros PADRÃO das rotas.
    Cada chave é o resultado da função, ou ``{"indisponivel": "<motivo>"}``. Também mede o tempo de cada uma."""
    P = est.projeto
    saida, tempos, de_cache = {}, {}, {}

    def secao(nome, f):
        t0 = time.perf_counter()
        try:
            v, c = _cacheado(P.dados, (nome, obra), f)
        except Exception as exc:  # noqa: BLE001 — módulo opcional/de outro dono não derruba o relatório
            v, c = {"indisponivel": f"{type(exc).__name__}: {str(exc)[:160]}"}, False
        saida[nome] = v
        tempos[nome] = round(time.perf_counter() - t0, 3)
        de_cache[nome] = c

    def _riscos():
        from .riscos_prazo import registro
        return registro(P, obra=obra, rapido=True)

    def _tendencia():
        from .tendencia import LIMIAR_DIVERGENCIA_DIAS, tendencia
        return tendencia(P, 7, LIMIAR_DIVERGENCIA_DIAS)

    def _recuperacao():
        from .recuperacao import recuperar
        return recuperar(P, prazo=None, marco=None, folga_max=5)

    def _aceleracao():
        from .aceleracao import LIMITE_EXTRA_PADRAO, acelerar
        return acelerar(P, prazo=None, limite_extra=LIMITE_EXTRA_PADRAO)

    def _backtest():
        from .backtest import backtest
        return backtest(P, 7)

    def _cobertura():
        from .cobertura import FOLGA_ALERTA_PADRAO_DU, cobertura
        return cobertura(P, "independente", None, folga_alerta_du=FOLGA_ALERTA_PADRAO_DU)

    for nome, f in (("riscos", _riscos), ("tendencia", _tendencia), ("recuperacao", _recuperacao),
                    ("aceleracao", _aceleracao), ("backtest", _backtest), ("cobertura", _cobertura)):
        secao(nome, f)
    saida["_tempos_s"], saida["_cache"] = tempos, de_cache
    return saida


def _marco(lista, mid="M-FIM"):
    return next((m for m in lista or [] if m.get("id") == mid), None)


def _html_analises(an: dict, e) -> list[str]:
    h = []

    def indisp(nome):
        v = an.get(nome) or {}
        if "indisponivel" in v:
            h.append(f"<p class='mu'>Indisponível: {e(v['indisponivel'])}</p>")
            return True
        return False

    # 8. riscos
    h.append("<h2>8. Cinco maiores riscos ao prazo</h2>")
    _ini = len(h)
    try:
        if not indisp("riscos"):
            r = an["riscos"]
            h.append("<table><tr><th>#</th><th>Risco</th><th>Nível</th><th class='n'>Δ potencial (dias)</th>"
                     "<th>Evidência (reproduz o número)</th></tr>")
            for i, x in enumerate(r["riscos"][:5], 1):
                ev = (x.get("evidencias") or [{}])[0]
                ev_txt = ev.get("rota", "—") + ("?" + "&".join(f"{k}={v}" for k, v in (ev.get("params") or {}).items())
                                                if ev.get("params") else "")
                delta = x.get("delta_potencial_dias")
                h.append(f"<tr><td>{i}</td><td>{e(x['titulo'])}</td><td class='{e(str(x.get('nivel', '')))}'>"
                         f"{e(str(x.get('nivel', '—')))}</td><td class='n'>{'—' if delta is None else delta}</td>"
                         f"<td class='mu'><code>{e(ev_txt)}</code></td></tr>")
            h.append("</table>")
            om = r.get("fontes_omitidas") or {}
            h.append(f"<p class='mu'>{r['n_riscos']} riscos no registro (modo rápido; omitidos: "
                     f"{e(', '.join(sorted(om)) or 'nenhum')}). Fonte: /api/riscos?rapido=true.</p>")
    except Exception as exc:  # noqa: BLE001 — formato inesperado vira 'Indisponível', nunca 500 (r18)
        del h[_ini:]
        h.append(f"<p class='mu'>Indisponível (riscos): formato inesperado ({e(type(exc).__name__)})</p>")

    # 9. tendência
    h.append("<h2>9. Tendência do término (M-FIM)</h2>")
    _ini = len(h)
    try:
        if not indisp("tendencia"):
            m = _marco(an["tendencia"].get("marcos"))
            if m is None:
                h.append("<p class='mu'>Marco M-FIM não encontrado na tendência.</p>")
            else:
                inc = m.get("inclinacao_dias_por_semana") or {}
                h.append("<table><tr><th>Previsão</th><th class='n'>Deslize (dias/semana)</th></tr>"
                         f"<tr><td>Construtora</td><td class='n'>{_num(inc.get('construtora'), 3)}</td></tr>"
                         f"<tr><td>Independente</td><td class='n'>{_num(inc.get('independente'), 3)}</td></tr></table>")
                h.append(f"<p>Divergência (independente − construtora acima de "
                         f"{an['tendencia'].get('limiar_divergencia_dias')} dias) desde: "
                         f"<b>{_br(m.get('divergencia_desde'))}</b>. Fonte: /api/tendencia.</p>")
    except Exception as exc:  # noqa: BLE001 — formato inesperado vira 'Indisponível', nunca 500 (r18)
        del h[_ini:]
        h.append(f"<p class='mu'>Indisponível (tendencia): formato inesperado ({e(type(exc).__name__)})</p>")

    # 10. recuperação e aceleração
    h.append("<h2>10. Recuperação e aceleração (para cumprir o prazo)</h2>")
    _ini = len(h)
    try:
        if not indisp("recuperacao"):
            rc = an["recuperacao"]
            h.append(f"<p><b>Recuperação</b> (produtividade/equipes mínimas): prazo {_br(rc.get('prazo'))}; término atual "
                     f"{_br(rc.get('termino_atual'))} → alcançado {_br(rc.get('termino_alcancado'))}; cumpre: "
                     f"<b>{'sim' if rc.get('cumpre_prazo') else 'não'}</b>; viabilidade: {e(str(rc.get('viabilidade') or '—'))}.</p>")
            if rc.get("plano"):
                h.append("<table><tr><th>Frente</th><th class='n'>Aumento de produtividade (%)</th>"
                         "<th class='n'>Equipes necessárias</th></tr>")
                for x in rc["plano"][:8]:
                    h.append(f"<tr><td>{e(x['id'])}</td><td class='n'>{_num(x.get('aumento_pct'), 1)}</td>"
                             f"<td class='n'>{'—' if x.get('equipes_necessarias') is None else x['equipes_necessarias']}</td></tr>")
                h.append("</table>")
    except Exception as exc:  # noqa: BLE001 — formato inesperado vira 'Indisponível', nunca 500 (r18)
        del h[_ini:]
        h.append(f"<p class='mu'>Indisponível (recuperacao): formato inesperado ({e(type(exc).__name__)})</p>")
    _ini = len(h)
    try:
        if not indisp("aceleracao"):
            ac = an["aceleracao"]
            h.append(f"<p><b>Aceleração</b> (equipes extras pelo menor custo): término {_br(ac.get('termino_inicial'))} → "
                     f"{_br(ac.get('termino_alcancado'))}; cumpre: <b>{'sim' if ac.get('cumpre_prazo') else 'não'}</b>; "
                     f"custo adicional <b>R$ {_num(ac.get('custo_adicional_total'))}</b> "
                     f"({e(str(ac.get('aviso', 'custos fictícios')))}); {len(ac.get('ajustes_finais') or [])} ajuste(s) de "
                     f"equipe. Fontes: /api/recuperacao e /api/aceleracao.</p>")
    except Exception as exc:  # noqa: BLE001 — formato inesperado vira 'Indisponível', nunca 500 (r18)
        del h[_ini:]
        h.append(f"<p class='mu'>Indisponível (aceleracao): formato inesperado ({e(type(exc).__name__)})</p>")

    # 11. backtest
    h.append("<h2>11. Backtest da previsão do término (M-FIM)</h2>")
    _ini = len(h)
    try:
        if not indisp("backtest"):
            b = an["backtest"]
            m = _marco(b.get("marcos"))
            rs = (m or {}).get("por_referencia", {}).get("realidade_simulada")
            if not rs:
                h.append("<p class='mu'>Sem referência de realidade simulada para o M-FIM.</p>")
            else:
                mae = rs.get("mae_dias") or {}
                h.append(f"<p class='aviso'>Referência SINTÉTICA: {e(b.get('referencias', {}).get('realidade_simulada', ''))}"
                         ". O backtest mede o método contra um mundo simulado, não contra uma obra real.</p>")
                h.append("<table><tr><th>Previsão</th><th class='n'>Erro médio absoluto (dias)</th></tr>"
                         f"<tr><td>Construtora</td><td class='n'>{_num(mae.get('construtora'))}</td></tr>"
                         f"<tr><td>Independente</td><td class='n'>{_num(mae.get('independente'))}</td></tr></table>")
                h.append(f"<p class='mu'>Término de referência {_br(rs.get('referencia'))}. Fonte: /api/backtest.</p>")
    except Exception as exc:  # noqa: BLE001 — formato inesperado vira 'Indisponível', nunca 500 (r18)
        del h[_ini:]
        h.append(f"<p class='mu'>Indisponível (backtest): formato inesperado ({e(type(exc).__name__)})</p>")

    # 12. cobertura
    h.append("<h2>12. Cobertura da previsão (confiança por marco)</h2>")
    _ini = len(h)
    try:
        if not indisp("cobertura"):
            co = an["cobertura"]
            h.append("<table><tr><th>Marco</th><th>Término</th><th>Confiança</th></tr>")
            for m in co.get("marcos", []):
                h.append(f"<tr><td>{e(m['id'])} <span class='mu'>{e(m.get('nome', ''))}</span></td>"
                         f"<td>{_br(m.get('termino'))}</td><td>{e(str(m.get('confianca')))}</td></tr>")
            h.append(f"</table><p class='mu'>Fator de estresse {_num(co.get('fator_estresse'), 4)}. Fonte: /api/cobertura.</p>")
    except Exception as exc:  # noqa: BLE001 — formato inesperado vira 'Indisponível', nunca 500 (r18)
        del h[_ini:]
        h.append(f"<p class='mu'>Indisponível (cobertura): formato inesperado ({e(type(exc).__name__)})</p>")
    return h


def gerar_html(est, obra_id: str, max_linhas: int = 10, obra: str | None = None) -> str:
    t_inicio = time.perf_counter()
    P = est.projeto
    d = P.dados
    res = {c: est.resultado(c) for c in ("linha_base", "construtora", "independente", "simulado")}
    ds = P.data_status
    av_real = 100 * avanco(P, res["independente"], ds)
    av_lb = 100 * avanco(P, res["linha_base"], ds)
    cmp_ci = comparar(P, res["construtora"], res["independente"])
    sim_ativa = bool(est.ajustes)
    cmp_sim = comparar(P, res["independente"], res["simulado"]) if sim_ativa else None
    al = alertas(P, res["independente"], res["construtora"])
    prods = produtividades(P)
    ind = res["independente"]
    pend = [r for r in d.get("restricoes", []) if r.get("situacao") == "pendente"]

    def dias(a, b):
        return ordinal(b) - ordinal(a)

    h = []
    e = escape
    # nome só do bloco de identificação da obra (chave "ferrovia" no esquema dos dados); NÃO depende de
    # meta.tipo_obra, então o relatório não assume tipo nenhum (P8) e segue tolerante a dado incompleto (r18)
    nome_obra = (d.get("ferrovia") or {}).get("nome") or "—"
    h.append(f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relatório técnico — {e(nome_obra)}</title>
<style>
:root{{--tx:#14213d;--mu:#5b6578;--ln:#d9dee7;--ac:#1f5fae;--al:#b42318;--ok:#18794e;--bg:#fff}}
body{{font:14px/1.45 system-ui,Segoe UI,Arial,sans-serif;color:var(--tx);background:var(--bg);margin:0 auto;max-width:980px;padding:24px}}
h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:16px;margin:26px 0 8px;border-bottom:2px solid var(--ln);padding-bottom:4px}}
.aviso{{background:#fff4ce;border:1px solid #e9c46a;padding:8px 12px;border-radius:6px;font-weight:600}}
.meta{{color:var(--mu);font-size:13px}} table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{border-bottom:1px solid var(--ln);padding:5px 6px;text-align:left;vertical-align:top}} th{{background:#f3f5f9}}
td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px}}
.k{{border:1px solid var(--ln);border-radius:6px;padding:8px 10px}} .k b{{display:block;font-size:18px}}
.alto{{color:var(--al);font-weight:600}} .medio{{color:#9a6700}} .mu{{color:var(--mu)}}
ol li{{margin-bottom:4px}} @media print{{body{{padding:0}} .naoimp{{display:none}} h2{{break-after:avoid}}}}
</style></head><body>""")
    h.append(f"<p class='aviso'>{e(d['meta'].get('aviso') or '—')}</p>")
    h.append(f"<h1>Relatório técnico — previsão independente de conclusão</h1>")
    h.append(f"<p class='meta'>{e(nome_obra)} · obra <code>{e(obra_id)}</code> · data de status "
             f"<b>{_br(d['meta']['data_status'])}</b> · premissas {e(d['meta'].get('versao_premissas', '—'))} · "
             f"gerado pelo motor CPM INFRA 4D (determinístico)</p>")
    # sem script: o relatório é servido com CSP que proíbe JavaScript (rodada 7)
    h.append("<p class='naoimp mu'>Para imprimir ou salvar em PDF, use Ctrl+P no navegador.</p>")

    h.append("<h2>1. Resumo executivo</h2><div class='kpis'>")
    for rot, val, sub in (
        ("Avanço físico real", f"{_num(av_real, 1)}%", f"linha de base previa {_num(av_lb, 1)}% ({_num(av_real - av_lb, 1)} p.p.)"),
        ("Término — linha de base", _br(res["linha_base"]["termino"]), "contratual (fictício)"),
        ("Término — construtora", _br(res["construtora"]["termino"]),
         f"{dias(res['linha_base']['termino'], res['construtora']['termino']):+d} dias vs LB"),
        ("Término — independente", _br(ind["termino"]),
         f"{cmp_ci['delta_dias_corridos']:+d} dias vs construtora"),
    ):
        h.append(f"<div class='k'><span class='mu'>{e(rot)}</span><b>{e(val)}</b><span class='mu'>{e(sub)}</span></div>")
    if sim_ativa:
        h.append(f"<div class='k'><span class='mu'>Término — simulado</span><b>{_br(res['simulado']['termino'])}</b>"
                 f"<span class='mu'>{cmp_sim['delta_dias_corridos']:+d} dias vs independente</span></div>")
    h.append("</div>")
    h.append(f"<p>A previsão independente recalcula as durações remanescentes com a <b>produtividade medida</b> nos "
             f"boletins ({len(d.get('medicoes', []))} boletins semanais) e propaga pela rede de "
             f"{len(d['atividades'])} atividades e {len(d['relacoes'])} relações. A diferença para a construtora é de "
             f"<b>{cmp_ci['delta_dias_corridos']:+d} dias corridos</b> ({cmp_ci['delta_dias_uteis']:+d} dias úteis).</p>")

    # ---- três métodos independentes, lado a lado (nenhum número digitado: todos do código)
    h.append("<h2>1b. Previsão por três métodos</h2>")
    linhas_m = [("CPM — construtora (produtividade planejada)", res["construtora"]["termino"], "rede + premissa da construtora"),
                ("CPM — independente (produtividade medida)", ind["termino"], "rede + boletins")]
    try:
        from .previsao_es import previsao as _es
        es = _es(P, resultados=res)["resultados"][0]
        linhas_m.append(("Earned Schedule — IEAC(t) com PF = SPI(t)", es.get("IEAC_spi_termino"),
                         f"avanço agregado, SPI(t) = {_num(es.get('SPI'), 3)}; ignora a lógica da rede"))
    except Exception as exc:  # noqa: BLE001 — módulo opcional: relatório não cai por ele
        es = None
        linhas_m.append(("Earned Schedule", None, f"indisponível ({type(exc).__name__})"))
    # Chave FIXA do relatório (r18: antes pegava qualquer "mc:" do cache e o relatório mudava conforme
    # chamadas anteriores à /api/previsao-probabilistica com outras opções)
    mc = est.cache.get("mc:relatorio:100:7")
    if mc is None:
        try:
            from .montecarlo import simular as _mc
            mc = _mc(P, 100, 7)
            # guarda no cache do Estado: antes recalculava a cada requisição (~0,4 s; achado de desempenho)
            with est.lock:
                est.cache.setdefault("mc:relatorio:100:7", mc)
        except Exception:  # noqa: BLE001
            mc = None
    if mc:
        linhas_m.append(("Monte Carlo — P50 / P80", f"{mc['p50']}|{mc['p80']}",
                         f"{mc['iteracoes']} iterações, semente 7, sem as opções v2 (correlação, riscos, chuva), sobre a "
                         f"produtividade medida; {mc.get('limitacoes', '')}"))
    h.append("<table><tr><th>Método</th><th>Término previsto</th><th>Base</th></tr>")
    for nome, t, base in linhas_m:
        val = " / ".join(_br(x) for x in t.split("|")) if t and "|" in t else _br(t)
        h.append(f"<tr><td>{e(nome)}</td><td><b>{val}</b></td><td class='mu'>{e(base)}</td></tr>")
    h.append("</table>")
    if es and es.get("explicacao"):
        h.append(f"<p class='mu'>{e(es['explicacao'])}</p>")

    h.append("<h2>2. Por que a previsão independente difere da construtora</h2><ol>")
    for linha in cmp_ci["explicacao"][:max_linhas]:
        h.append(f"<li>{e(linha)}</li>")
    if len(cmp_ci["explicacao"]) > max_linhas:
        h.append(f"<li class='mu'>… mais {len(cmp_ci['explicacao']) - max_linhas} linha(s) — ver Simulação no beta.</li>")
    h.append("</ol>")

    h.append("<h2>3. Cadeia determinante do término (cenário independente)</h2>")
    h.append("<table><tr><th>Atividade</th><th>Início</th><th>Término</th><th class='n'>Duração (d.u.)</th>"
             "<th>Produtividade usada</th><th>Fonte</th></tr>")
    for aid in ind["cadeia_determinante"]:
        a, r = P.atividades[aid], ind["atividades"][aid]
        m = r["memoria"]
        prod = (f"{_num(m.get('produtividade'))} {e(m.get('unidade') or '')}/eq·dia"
                if m.get("regra") == "quantidade" else e(m.get("regra", "")))
        h.append(f"<tr><td><b>{e(aid)}</b><br><span class='mu'>{e(a.get('nome') or '—')}</span></td><td>{_br(r['inicio'])}</td>"
                 f"<td>{_br(r['termino'])}</td><td class='n'>{r['duracao']}</td><td>{prod}</td>"
                 f"<td class='mu'>{e(m.get('fonte_produtividade', '—'))}</td></tr>")
    h.append("</table>")

    h.append(f"<h2>4. Alertas ({len(al)})</h2>")
    if al:
        h.append("<ul>" + "".join(f"<li class='{e(x['nivel'])}'>[{e(x['nivel'].upper())}] {e(x['texto'])}</li>"
                                  for x in al) + "</ul>")
    else:
        h.append("<p class='mu'>Nenhum alerta.</p>")

    h.append("<h2>5. Produtividade planejada × medida (por lote e serviço)</h2>")
    h.append("<table><tr><th>Lote</th><th>Serviço</th><th>Unidade</th><th class='n'>Planejada</th>"
             "<th class='n'>Medida</th><th class='n'>Índice</th><th class='n'>Boletins</th></tr>")
    for p in sorted(prods, key=lambda x: (x["indice"] is None, x["indice"] or 0)):
        cls = "alto" if p["indice"] is not None and p["indice"] < 0.85 else ""
        h.append(f"<tr><td>{e(str(p['lote_id']))}</td><td>{e(str(p['servico_id']))}</td><td>{e(p['unidade'] or '')}</td>"
                 f"<td class='n'>{_num(p['planejada'])}</td><td class='n'>{_num(p['efetiva'])}</td>"
                 f"<td class='n {cls}'>{_num(p['indice'], 2)}</td><td class='n'>{p['boletins']}</td></tr>")
    h.append("</table>")

    h.append(f"<h2>6. Restrições pendentes ({len(pend)})</h2>")
    if pend:
        h.append("<ul>" + "".join(f"<li>{e(r.get('descricao') or '—')} — libera {_br(r.get('data_liberacao'))} "
                                  f"(atividade {e(str(r.get('atividade_id') or '—'))})</li>" for r in pend) + "</ul>")
    else:
        h.append("<p class='mu'>Nenhuma.</p>")

    if sim_ativa:
        h.append("<h2>7. Simulação ativa (\"e se\")</h2><ol>")
        for linha in cmp_sim["explicacao"][:max_linhas]:
            h.append(f"<li>{e(linha)}</li>")
        h.append("</ol>")

    an = analises(est, obra)
    h.extend(_html_analises(an, e))

    h.append("<h2>Método e limitações</h2><ul class='mu'>"
             "<li>CPM próprio (FS/SS/FF/SF com lag, calendários por atividade, data de status com <i>progress "
             "override</i>, folgas, caminho crítico e caminho mais longo) — ADR-0003. Compatibilidade com P6/MS Project "
             "não é alegada.</li>"
             "<li>Duração remanescente = ⌈quantidade remanescente ÷ (produtividade × equipes)⌉; fonte da produtividade "
             "declarada por atividade (própria → lote/serviço → serviço → planejada).</li>"
             "<li>Sem nivelamento de recursos neste relatório; sem custos (5D é evolução futura).</li>"
             f"<li>Todos os dados são FICTÍCIOS, gerados por <code>{e(d['meta'].get('gerador', '—'))}</code> "
             f"(semente {e(str(d['meta'].get('semente', '—')))}).</li></ul>")
    tempos = an["_tempos_s"]
    h.append(f"<p class='mu'>Tempo de geração: {_num(time.perf_counter() - t_inicio, 2)} s (análises: "
             + ", ".join(f"{k} {_num(v, 2)} s{' (cache)' if an['_cache'].get(k) else ''}" for k, v in tempos.items())
             + ").</p>")
    h.append("</body></html>")
    return "".join(h)

