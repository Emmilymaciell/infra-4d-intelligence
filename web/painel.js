// Painel gerencial: KPIs, alertas, produtividade, curva S e produção semanal (SVG feito à mão).

import { estado, selecionar, nomeServico } from './estado.js';
import { svg, diaDe, isoDe, dataBR, num, pct, esc, mostrarTooltip, esconderTooltip, mesCurto, CENARIO_ROTULO, seloSimulacao } from './util.js';

// cores categóricas em ordem fixa (paleta validada); entidade -> cor nunca muda com filtro
export const COR_CENARIO = { linha_base: '#2a78d6', construtora: '#eb6834', independente: '#1baf7a', simulado: '#6250d6' };
// cor por serviço: atribuída por obra, na ordem da lista de serviços (cores.js)
import { corServico } from './cores.js';
import { api } from './api.js';

let raiz = null;
let opcoes = {};
let comparacaoCI = null;

export function iniciarPainel(el, op = {}) {
  raiz = el;
  opcoes = op;
}

export function definirComparacaoConstrutora(c) { comparacaoCI = c; }

// Previsão probabilística (Monte Carlo): null = carregando; {erro} = falha; senão resposta da API.
let previsao = null;
export function definirPrevisao(p) { previsao = p; }

// Monte Carlo com incerteza alargada para frente sem medição (P4): {alargamento, carregando|dados|erro}
let p4 = {};
const P4_ITERACOES = 200;

function p4HTML() {
  const alarg = p4.alargamento ?? 0.5;
  if (!p4.dados && !p4.erro && !p4.carregando) carregarP4(alarg);
  const cab = `<div style="border-top:1px solid var(--borda);margin-top:10px;padding-top:8px" id="p-p4">
    <b style="font-size:13px">Incerteza alargada para frente sem medição</b>
    <div class="gantt-barra" style="margin-top:6px">
      <label>Alargamento <select id="p-p4-alarg">${['0', '0.1', '0.2', '0.3', '0.4', '0.5', '0.6'].map(x => `<option value="${x}" ${Number(x) === Number(alarg) ? 'selected' : ''}>±${num(Number(x) * 100, 0)}%${x === '0.5' ? ' (padrão)' : ''}</option>`).join('')}</select></label>
      <span style="font-size:12px;color:var(--texto-3)">Padrão 50% (calibrado no backtest); teto 60% — acima disso a faixa vira ruído.</span>
    </div>`;
  if (p4.carregando) return `${cab}<p class="vazio">Rodando ${P4_ITERACOES} iterações com o fator sorteado para as frentes sem boletim próprio…</p></div>`;
  if (p4.erro) return `${cab}<p class="erro">Incerteza alargada indisponível: ${esc(p4.erro)}</p></div>`;
  const d = p4.dados;
  const inc = d.incerteza_sem_medicao || {};
  const ms = d.marcos || {};
  return `${cab}${seloSimulacao(d)}
    <p style="font-size:12.5px;margin:4px 0" id="p-p4-resumo">Grupos (lote/serviço) que usaram o modo: <b>${(inc.grupos || []).map(esc).join(', ') || 'nenhum'}</b>
      (${num((inc.atividades || []).length, 0)} atividades; ${num(inc.indices_observados, 0)} índices medidos na obra; alargamento ${num((inc.alargamento ?? alarg) * 100, 0)}%).
      Obra inteira: P50 <b>${dataBR(d.p50)}</b>, P80 <b>${dataBR(d.p80)}</b>, largura P10–P90 ${num(d.largura_p10_p90_dias, 0)} dias.</p>
    <table class="tab" id="p-p4-tab" style="max-width:820px"><thead><tr><th>Marco</th><th>P10</th><th>P50</th><th>P80</th><th>P90</th><th class="num">Largura P10–P90</th></tr></thead><tbody>
      ${Object.entries(ms).map(([id, x]) => `<tr data-marco="${esc(id)}"><td><b>${esc(id)}</b></td><td>${dataBR(x.p10)}</td><td>${dataBR(x.p50)}</td><td>${dataBR(x.p80)}</td>
        <td>${dataBR(x.p90)}</td><td class="num">${num(x.largura_p10_p90_dias, 0)} d</td></tr>`).join('')}
    </tbody></table>
    <p style="font-size:11.5px;color:var(--texto-3);margin:4px 0 0">${esc(inc.regra || '')}</p></div>`;
}

function carregarP4(alarg) {
  p4 = { alargamento: alarg, carregando: true };
  api.previsaoP4(P4_ITERACOES, alarg)
    .then(d => { if (p4.alargamento === alarg) p4 = { alargamento: alarg, dados: d }; })
    .catch(e => { if (p4.alargamento === alarg) p4 = { alargamento: alarg, erro: e.message || String(e) }; })
    .finally(() => renderPainel());
}

// Monte Carlo v2 (riscos / chuva / correlação rho), sob demanda: {params, carregando|dados|erro}
let v2 = null;
const V2_ITERACOES = 100;
// Earned Schedule por lote ('' = obra inteira): {carregando|dados|erro}
let es = {};

function obterES(lote) {
  if (es[lote] && (es[lote].dados || es[lote].erro)) return es[lote];
  if (!es[lote]) {
    es[lote] = { carregando: true };
    api.earnedSchedule(lote || null)
      .then(d => { es[lote] = { dados: d }; })
      .catch(e => { es[lote] = { erro: e.message }; })
      .finally(() => renderPainel());
  }
  return es[lote];
}

function lerControlesV2() {
  const q = (s) => raiz.querySelector(s);
  return { com_riscos: !!q('#p-v2-riscos')?.checked, com_chuva: !!q('#p-v2-chuva')?.checked, rho: Number(q('#p-v2-rho')?.value ?? 0) };
}

async function rodarV2() {
  const params = lerControlesV2();
  if (!params.com_riscos && !params.com_chuva && !(params.rho > 0)) {
    v2 = { params, erro: 'Ligue riscos, chuva ou um rho maior que 0 para a v2 diferir da v1.' };
    renderPainel();
    return;
  }
  v2 = { params, carregando: true };
  renderPainel();
  try {
    v2 = { params, dados: await api.previsaoProbabilisticaV2(V2_ITERACOES, params) };
  } catch (e) {
    v2 = { params, erro: e.message };
  }
  renderPainel();
}

function v2HTML() {
  const pr = (v2 && v2.params) || { com_riscos: true, com_chuva: true, rho: 0.5 };
  let res = '';
  if (v2 && v2.carregando) res = `<p class="vazio">Rodando ${V2_ITERACOES} iterações com riscos/chuva/correlação (CPM completo por iteração)…</p>`;
  else if (v2 && v2.erro) res = `<p class="erro">${esc(v2.erro)}</p>`;
  else if (v2 && v2.dados) {
    const d = v2.dados;
    const riscos = (d.v2 && d.v2.riscos) || null;
    const chuva = (d.v2 && d.v2.chuva) || null;
    res = `${seloSimulacao(d)}<div id="p-faixas" style="max-width:760px"></div>
      <p style="font-size:12.5px;margin:4px 0" id="p-v2-resumo">Largura P10–P90: v1 <b>${d.faixa_v1 ? d.faixa_v1.largura_p10_p90_dias : '—'}</b> dias →
        v2 <b>${d.faixa_v2 ? d.faixa_v2.largura_p10_p90_dias : d.largura_p10_p90_dias}</b> dias · P80 v1 ${dataBR(d.faixa_v1 && d.faixa_v1.p80)} → v2 <b>${dataBR(d.faixa_v2 && d.faixa_v2.p80)}</b></p>
      <p style="font-size:11.5px;color:var(--texto-3);margin:0">
        ${d.v2 && d.v2.correlacao ? `Correlação (rho ${num(d.v2.rho, 2)}): ${esc(d.v2.correlacao)}.<br>` : ''}
        ${riscos ? `Riscos (${esc(riscos.origem || '')}): ${(riscos.lista || []).map(r => `${esc(r.id)} ${esc(r.atividade_id)} p=${num(r.probabilidade, 2)} +${num(r.impacto_dias_uteis, 0)} d.u.`).join(' · ')}.<br>` : ''}
        ${chuva ? `Chuva: p=${num(chuva.p_dia_perdido, 2)} de dia perdido nos meses ${(chuva.meses || []).map(m => num(m, 0)).join(', ')} (${(chuva.calendarios || []).map(esc).join(', ')}); média ${num(chuva.media_dias_perdidos_por_iteracao, 1)} dias perdidos/iteração.` : ''}
        ${d.iteracoes} iterações na v2.</p>`;
  }
  return `<div style="border-top:1px solid var(--borda);margin-top:10px;padding-top:8px">
      <b style="font-size:13px">v1 × v2 — incluir incertezas além da média medida</b>
      <div class="gantt-barra" style="margin-top:6px">
        <label class="chk"><input type="checkbox" id="p-v2-riscos" ${pr.com_riscos ? 'checked' : ''}> Riscos discretos</label>
        <label class="chk"><input type="checkbox" id="p-v2-chuva" ${pr.com_chuva ? 'checked' : ''}> Chuva estocástica</label>
        <label>Correlação rho <input type="range" id="p-v2-rho" min="0" max="1" step="0.1" value="${pr.rho}" style="width:110px">
          <b id="p-v2-rho-txt">${num(pr.rho, 1)}</b></label>
        <button type="button" class="primario" id="p-v2-rodar" ${v2 && v2.carregando ? 'disabled' : ''}>Comparar v1 × v2</button>
      </div>${res}</div>`;
}

/** Duas faixas P10–P90 (v1 e v2) num eixo de datas comum, com marcas de P50, P80 e do determinístico. */
function faixas(el, d) {
  if (!el || !d || !d.faixa_v1 || !d.faixa_v2) return;
  const fs = [['v1 (só média medida)', d.faixa_v1, '#1baf7a'], ['v2 (riscos/chuva/rho)', d.faixa_v2, '#6250d6']];
  const datas = fs.flatMap(([, f]) => [f.p10, f.p90]).concat([d.deterministico]).map(diaDe);
  const d0 = Math.min(...datas) - 3, d1 = Math.max(...datas) + 3;
  const W = 760, H = 110, m = { l: 150, r: 20, t: 18, b: 22 };
  const X = (dd) => m.l + (dd - d0) / (d1 - d0) * (W - m.l - m.r);
  const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'graf', role: 'img', 'aria-label': 'Faixas P10–P90 da v1 e da v2' }, el);
  fs.forEach(([rot, f, cor], i) => {
    const y = m.t + i * 36;
    svg('text', { x: 4, y: y + 14 }, s).textContent = rot;
    svg('rect', { x: X(diaDe(f.p10)), y, width: Math.max(2, X(diaDe(f.p90)) - X(diaDe(f.p10))), height: 20, rx: 4, fill: cor, opacity: 0.25, class: 'faixa' }, s);
    for (const [k, w] of [['p50', 3], ['p80', 2]]) {
      const x = X(diaDe(f[k]));
      svg('line', { x1: x, x2: x, y1: y - 2, y2: y + 22, stroke: cor, 'stroke-width': w }, s);
      svg('text', { x: x + 3, y: y - 3, fill: cor, 'font-weight': 600, style: 'font-size:10px' }, s).textContent = `${k.toUpperCase()} ${dataBR(f[k]).slice(0, 5)}`;
    }
  });
  const xd = X(diaDe(d.deterministico));
  svg('line', { x1: xd, x2: xd, y1: m.t - 6, y2: H - m.b, stroke: '#52514e', 'stroke-dasharray': '3 2' }, s);
  svg('text', { x: xd + 3, y: H - 6, fill: '#52514e' }, s).textContent = `determinístico ${dataBR(d.deterministico)}`;
}

/** Cartão "Três métodos de previsão": CPM construtora, CPM independente, Earned Schedule e Monte Carlo. */
function metodosHTML(p) {
  const lote = p.lote || '';
  const e = obterES(lote);
  const cab = `<h3 style="margin-top:0">Três métodos de previsão${lote ? ` · lote ${esc(lote)}` : ''}</h3>`;
  if (e.carregando) return `${cab}<p class="vazio">Calculando Earned Schedule…</p>`;
  if (e.erro) return `${cab}<p class="erro">Earned Schedule indisponível: ${esc(e.erro)}</p>`;
  const r = (e.dados.resultados || []).find(x => (x.lote || '') === lote) || (e.dados.resultados || [])[0];
  if (!r) return `${cab}<p class="vazio">Sem resultado de Earned Schedule para o escopo.</p>`;
  const lb = r.termino_linha_base || p.terminos.linha_base;
  const vsLB = (d) => {
    if (!d || !lb) return '—';
    const x = diaDe(d) - diaDe(lb);
    return x === 0 ? '= LB' : `<span class="indice ${x > 0 ? 'ruim' : 'bom'}">${x > 0 ? '▲ +' : '▼ −'}${Math.abs(x)} d</span>`;
  };
  const mc = !lote && previsao && !previsao.erro ? previsao : null;
  const linhas = [
    ['CPM — construtora', 'rede + produtividade planejada', r.cpm_construtora_termino],
    ['CPM — independente', 'rede + produtividade medida', r.cpm_independente_termino],
    ['Earned Schedule — IEAC(t) SPI', `avanço agregado, SPI ${num(r.SPI, 3)} (ES em ${dataBR(r.ES_data)})`, r.IEAC_spi_termino],
    ['Earned Schedule — IEAC(t) PF=1', 'avanço agregado, ritmo planejado daqui em diante', r.IEAC_pf1_termino],
    ['Monte Carlo — P50', mc ? 'incerteza da média medida (v1)' : 'só para a obra inteira', mc && mc.p50],
    ['Monte Carlo — P80', mc ? 'incerteza da média medida (v1)' : 'só para a obra inteira', mc && mc.p80],
  ];
  return `${cab}
    <table class="tab" id="p-metodos-tab"><thead><tr><th>Método</th><th>Base</th><th>Término</th><th>vs linha de base (${dataBR(lb)})</th></tr></thead><tbody>
      ${linhas.map(([m, b, d]) => `<tr><td><b>${esc(m)}</b></td><td style="white-space:normal;font-size:12px">${esc(b)}</td><td>${dataBR(d)}</td><td>${vsLB(d)}</td></tr>`).join('')}
    </tbody></table>
    <p style="font-size:12.5px;margin:8px 0 4px">ES (SPI) × CPM independente: <b>${r.diferenca_es_spi_vs_cpm_independente_dias > 0 ? '+' : ''}${r.diferenca_es_spi_vs_cpm_independente_dias} dias corridos</b>.</p>
    <p style="font-size:11.5px;color:var(--texto-3);margin:0">${esc(r.explicacao || '')}<br>
      ${esc(e.dados.metodo || '')}. ${e.dados.referencia_verificada ? '' : `Referência bibliográfica não verificada nesta versão (${esc(e.dados.nota || '')}).`}</p>`;
}

function previsaoHTML() {
  const cab = '<h3>Previsão probabilística (independente) <small style="font-weight:400;color:var(--texto-3)">obra inteira</small></h3>';
  if (!previsao) return `${cab}<p class="vazio">Calculando simulações de Monte Carlo…</p>`;
  if (previsao.erro) return `${cab}<p class="erro">Previsão probabilística indisponível: ${esc(previsao.erro)}</p>`;
  const p = previsao;
  const dP = (d) => { const x = diaDe(d) - diaDe(p.deterministico); return x === 0 ? 'igual ao determinístico' : `${x > 0 ? '+' : '−'}${Math.abs(x)} d corridos vs determinístico`; };
  return `${cab}${seloSimulacao(p)}
    <div style="display:flex;gap:28px;flex-wrap:wrap;align-items:flex-start">
      <div class="kpi" style="box-shadow:none"><div class="rot">P50 (mediana)</div><div class="val">${dataBR(p.p50)}</div><span class="det">${dP(p.p50)}</span></div>
      <div class="kpi" style="box-shadow:none"><div class="rot">P80</div><div class="val">${dataBR(p.p80)}</div><span class="det">${dP(p.p80)}</span></div>
      <div style="font-size:12.5px;color:var(--texto-2);line-height:1.6">
        Determinístico: <b>${dataBR(p.deterministico)}</b><br>
        P10 ${dataBR(p.p10)} · P90 ${dataBR(p.p90)}<br>
        Faixa simulada: ${dataBR(p.min)} – ${dataBR(p.max)}<br>
        ${p.iteracoes ? `${p.iteracoes} iterações` : ''}</div>
      <div id="p-hist" style="flex:1;min-width:320px;max-width:560px"></div>
    </div>
    <p style="font-size:11.5px;color:var(--texto-3);margin:6px 0 0">Método: ${esc(p.metodo || '—')}.<br>
      Limitações: ${esc(p.limitacoes || '—')}. A faixa é estreita de propósito: representa só a incerteza da média medida, não riscos.</p>
    ${p4HTML()}
    ${v2HTML()}`;
}

function histograma(el, p) {
  if (!el || !p || p.erro || !p.histograma || !p.histograma.length) return;
  const h = p.histograma;
  const W = 520, H = 130, m = { l: 28, r: 8, t: 14, b: 22 };
  const d0 = diaDe(h[0].de), d1 = diaDe(h[h.length - 1].ate) + 1;
  const X = (d) => m.l + (d - d0) / (d1 - d0) * (W - m.l - m.r);
  const nMax = Math.max(...h.map(b => b.n));
  const Y = (n) => H - m.b - n / nMax * (H - m.t - m.b);
  const total = h.reduce((s, b) => s + b.n, 0);
  const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'graf', role: 'img', 'aria-label': 'Histograma das datas de término simuladas' }, el);
  svg('line', { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, stroke: '#c9ccc5' }, s);
  svg('text', { x: m.l - 4, y: Y(nMax) + 4, 'text-anchor': 'end' }, s).textContent = nMax;
  h.forEach((b, i) => {
    const xa = X(diaDe(b.de)), xb = X(diaDe(b.ate) + 1);
    const r = svg('rect', { x: xa + 1, y: Y(b.n), width: Math.max(1, xb - xa - 2), height: Math.max(0, H - m.b - Y(b.n)), rx: 2, fill: '#1baf7a' }, s);
    r.addEventListener('mousemove', (e) => mostrarTooltip(`<b>${dataBR(b.de)} – ${dataBR(b.ate)}</b><br>${b.n} iterações (${num(100 * b.n / total, 1)}%)`, e));
    r.addEventListener('mouseleave', esconderTooltip);
    if (i % 2 === 0 || h.length <= 6) {
      const [, mm, dd] = b.de.split('-');
      svg('text', { x: (xa + xb) / 2, y: H - 6, 'text-anchor': 'middle' }, s).textContent = `${dd}/${mm}`;
    }
  });
  const marca = (d, rot, cor, dy) => {
    const x = X(diaDe(d) + 0.5);
    svg('line', { x1: x, x2: x, y1: m.t - 2, y2: H - m.b, stroke: cor, 'stroke-width': 1.5, 'stroke-dasharray': '3 2' }, s);
    svg('text', { x: x + 3, y: m.t + dy, fill: cor, 'font-weight': 600 }, s).textContent = rot;
  };
  marca(p.deterministico, 'det.', '#52514e', 0);
  marca(p.p50, 'P50', '#12263f', 12);
  marca(p.p80, 'P80', '#d62d2d', 24);
}

function diasCorridos(a, b) {
  if (!a || !b) return null;
  return diaDe(a) - diaDe(b);
}
function detDelta(d, ref) {
  if (d === null) return `<span class="det">—</span>`;
  if (d === 0) return `<span class="det">igual a ${ref}</span>`;
  return `<span class="det ${d > 0 ? 'pior' : 'melhor'}">${d > 0 ? '+' : '−'}${Math.abs(d)} dias corridos vs ${ref}</span>`;
}

// ---------------------------------------------------------------- histórico (SINTÉTICO) e riscos ao prazo
let hist = {};    // {carregando|dados|erro}
let riscos = {};  // {carregando|dados|erro}

function carregarUmaVez(alvo, fn, definir) {
  if (alvo.dados || alvo.erro || alvo.carregando) return;
  definir({ carregando: true });
  fn().then(d => definir({ dados: d })).catch(e => definir({ erro: e.message || String(e) })).finally(() => renderPainel());
}

function historicoHTML() {
  carregarUmaVez(hist, () => api.historicoEvolucao(), (v) => { hist = v; });
  const cab = '<h3 style="margin-top:0">Evolução da previsão de término <span class="pill and">histórico SINTÉTICO</span></h3>';
  if (hist.carregando) return `${cab}<p class="vazio">Recalculando a previsão em cada data de status passada…</p>`;
  if (hist.erro) return `${cab}<p class="erro">Histórico indisponível: ${esc(hist.erro)}</p>`;
  const h = hist.dados;
  return `${cab}
    <p class="erro" style="background:#fff8e1;border-color:#ffd24a;color:#4a3900;margin:4px 0">Este histórico NÃO é registro de previsões feitas no passado:
      é recalculado agora, a partir dos dados fictícios atuais, como se a data de status fosse cada mês anterior.</p>
    <div id="p-hist-graf" style="max-width:1000px"></div>
    <ol style="font-size:13px;line-height:1.5" id="p-hist-narrativa">${(h.narrativa || []).map(t => `<li>${esc(t)}</li>`).join('')}</ol>
    <details><summary style="cursor:pointer;font-size:12.5px">Simplificações declaradas (${num((h.simplificacoes || []).length, 0)})</summary>
      <ul style="font-size:12px;color:var(--texto-2)">${(h.simplificacoes || []).map(t => `<li>${esc(t)}</li>`).join('')}</ul></details>`;
}

/** Linhas: data de status (x) × término previsto (y) — independente, construtora e linha de base. */
function graficoHistorico(el, h) {
  const pts = (h.pontos || []).filter(p => diaDe(p.data_status) !== null);
  if (!el || pts.length < 2) return;
  const series = [['termino_independente', 'Independente', COR_CENARIO.independente, null],
    ['termino_construtora', 'Construtora', COR_CENARIO.construtora, null], ['termino_linha_base', 'Linha de base', COR_CENARIO.linha_base, '6 4']];
  const xs = pts.map(p => diaDe(p.data_status));
  const ys = pts.flatMap(p => series.map(([k]) => diaDe(p[k]))).filter(v => v !== null);
  const W = 1000, H = 280, m = { l: 80, r: 16, t: 14, b: 30 };
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys) - 10, y1 = Math.max(...ys) + 10;
  const X = (d) => m.l + (d - x0) / ((x1 - x0) || 1) * (W - m.l - m.r);
  const Y = (d) => H - m.b - (d - y0) / ((y1 - y0) || 1) * (H - m.t - m.b);
  el.innerHTML = `<div class="legenda-graf">${series.map(([, rot, cor, tr]) => `<span><svg width="22" height="8"><line x1="0" y1="4" x2="22" y2="4" stroke="${esc(cor)}" stroke-width="2" ${tr ? `stroke-dasharray="${esc(tr)}"` : ''}/></svg>${esc(rot)}</span>`).join('')}</div>`;
  const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'graf', id: 'p-hist-svg', role: 'img', 'aria-label': 'Término previsto em cada data de status' }, el);
  for (let i = 0; i <= 4; i++) {
    const d = Math.round(y0 + (y1 - y0) * i / 4);
    svg('line', { x1: m.l, x2: W - m.r, y1: Y(d), y2: Y(d), stroke: '#e6e8e3' }, s);
    svg('text', { x: m.l - 6, y: Y(d) + 4, 'text-anchor': 'end' }, s).textContent = dataBR(isoDe(d));
  }
  pts.forEach((p, i) => { if (i % 2 === 0) svg('text', { x: X(xs[i]), y: H - 10, 'text-anchor': 'middle' }, s).textContent = mesCurto(xs[i]); });
  for (const [k, , cor, tr] of series) {
    const v = pts.map((p, i) => [X(xs[i]), diaDe(p[k])]).filter(([, d]) => d !== null);
    svg('polyline', { points: v.map(([x, d]) => `${x.toFixed(1)},${Y(d).toFixed(1)}`).join(' '), fill: 'none', stroke: cor, 'stroke-width': 2,
      'stroke-dasharray': tr, class: 'p-hist-linha', 'data-serie': k }, s);
  }
  pts.forEach((p, i) => {
    const alvo = svg('rect', { x: X(xs[i]) - 8, y: m.t, width: 16, height: H - m.t - m.b, fill: 'transparent', class: 'p-hist-ponto' }, s);
    alvo.addEventListener('mousemove', (e) => mostrarTooltip(`<b>Data de status ${dataBR(p.data_status)}</b><br>
      Independente: ${dataBR(p.termino_independente)} · Construtora: ${dataBR(p.termino_construtora)}<br>
      Diferença: ${num(p.diferenca_dias_corridos, 0)} dias corridos · avanço ${pct(p.avanco_real_pct)} (LB ${pct(p.avanco_previsto_lb_pct)})`, e));
    alvo.addEventListener('mouseleave', esconderTooltip);
  });
}

const NIVEL_RISCO = { alto: ['ruim', '▲ alto'], medio: ['medio', '● médio'], baixo: ['bom', '▼ baixo'] };

// ---------------------------------------------------------------- confiança da previsão por marco (/api/cobertura)
let cobertura = {};
const CONF = { alta: ['bom', '✓ alta'], media: ['medio', '● média'], 'média': ['medio', '● média'], baixa: ['ruim', '▼ baixa'],
  indeterminada: ['medio', '? indeterminada'], sem_historico: ['medio', '— sem histórico'], concluido: ['bom', '✓ concluído'] };

function coberturaHTML() {
  carregarUmaVez(cobertura, () => api.cobertura(), (v) => { cobertura = v; });
  const cab = '<h3 style="margin-top:0">Confiança da previsão por marco</h3>';
  if (cobertura.carregando) return `${cab}<p class="vazio">Estressando as frentes sem medição no motor…</p>`;
  if (cobertura.erro) return `${cab}<p class="erro">Confiança indisponível: ${esc(cobertura.erro)}</p>`;
  const c = cobertura.dados;
  const ms = c.marcos || [];
  const alertas = ms.flatMap(m => (m.alerta_sem_medicao || []).map(a => ({ ...a, marco: m.id })));
  const unicos = [...new Map(alertas.map(a => [a.atividade_id, a])).values()];
  const par = c.parametros || {};
  const fo = c.fator_estresse_origem || {};
  return `${cab}${seloSimulacao(c)}
    ${unicos.length ? `<p class="erro" id="p-cob-alerta">⚠ ${num(unicos.length, 0)} frente(s) SEM MEDIÇÃO com folga ≤ ${num(par.folga_alerta_du, 0)} dias úteis até o marco:
      ${unicos.slice(0, 12).map(a => `<span class="link-ativ" data-id="${esc(a.atividade_id)}">${esc(a.atividade_id)}</span>`).join(', ')}${unicos.length > 12 ? '…' : ''}.
      A produtividade delas vem de analogia ou do planejado, não de boletim.</p>` : '<p style="font-size:12.5px" id="p-cob-alerta-ok">✓ Nenhuma frente sem medição com folga curta até os marcos.</p>'}
    <table class="tab" id="p-cob-tab"><thead><tr><th>Marco</th><th>Término</th><th>Confiança</th><th class="num">Δ se sem medição piorar</th>
      <th class="num">Δ se medidas piorarem</th><th class="num">Trabalho sem medição</th><th>Frentes sem medição (folga curta)</th></tr></thead><tbody>
      ${ms.map(m => {
        const [cl, tx] = CONF[m.confianca] || ['medio', m.confianca];
        const e = m.estresse;  // nulo quando a confiança é indeterminada / sem histórico / concluído
        const al = m.alerta_sem_medicao || [];
        return `<tr data-marco="${esc(m.id)}"><td><b>${esc(m.id)}</b><br><small style="color:var(--texto-3)">${esc(m.nome || '')}</small></td><td>${dataBR(m.termino)}</td>
          <td><span class="indice ${esc(cl)}" data-confianca="${esc(m.confianca)}">${esc(tx)}</span>${m.motivo ? `<br><small class="p-cob-motivo">${esc(m.motivo)}</small>` : ''}</td>
          <td class="num">${e ? `+${num(e.delta_sem_medicao_dias, 0)} d<br><small>${dataBR(e.termino_estressado_sem_medicao)}</small>` : '—'}</td>
          <td class="num">${e ? `+${num(e.delta_medida_dias, 0)} d<br><small>${dataBR(e.termino_estressado_medida)}</small>` : '—'}</td>
          <td class="num">${num(((m.relatorio_origem || {}).fracao_sem_medicao || 0) * 100, 1)}%</td>
          <td style="white-space:normal;font-size:12px">${al.length ? al.map(a => `<span class="link-ativ" data-id="${esc(a.atividade_id)}">${esc(a.atividade_id)}</span>
            <small>(${esc(a.origem || '')}, folga ${num(a.folga_relativa_du, 0)}${a.na_cadeia ? ', na cadeia' : ''})</small>`).join('<br>') : '—'}</td></tr>`;
      }).join('')}
    </tbody></table>
    <p style="font-size:11.5px;color:var(--texto-3);margin:4px 0 0">Estresse: frentes sem medição e medidas com o pior índice medida/planejada já visto na obra
      (f = ${num(c.fator_estresse, 3)}, ${esc(fo.lote_id || '')}/${esc(fo.servico_id || '')}, ${num(fo.boletins, 0)} boletins). Parâmetros: limiar_baixa ${num(par.limiar_baixa, 2)}, limiar_alta ${num(par.limiar_alta, 2)}, Δ mínimo ${num(par.delta_minimo_dias, 0)} d.
      ${Object.entries(c.regras || {}).map(([k, r]) => `<b>${esc(k)}</b>: ${esc(r)}`).join(' · ')}</p>`;
}

/** Cartão com os 5 maiores riscos ao prazo (maior exposição), com o link da evidência na API. */
function riscosHTML() {
  carregarUmaVez(riscos, () => api.riscos(), (v) => { riscos = v; });
  const cab = '<h3 style="margin-top:0">Maiores riscos ao prazo</h3>';
  if (riscos.carregando) return `${cab}<p class="vazio">Cruzando produtividade, tornado, clima e Earned Schedule…</p>`;
  if (riscos.erro) return `${cab}<p class="erro">Riscos ao prazo indisponíveis: ${esc(riscos.erro)}</p>`;
  const r = riscos.dados;
  const top = [...(r.riscos || [])].sort((a, b) => (b.exposicao || 0) - (a.exposicao || 0)).slice(0, 5);
  return `${cab}${seloSimulacao(r)}<p style="font-size:12.5px;margin:4px 0">${num(r.n_riscos, 0)} riscos identificados; os 5 de maior exposição (dias de atraso potencial no término
      ${dataBR(r.termino_independente)}). Cada evidência abre o JSON da própria API.</p>
    <table class="tab" id="p-riscos-tab"><thead><tr><th>Risco</th><th>Nível</th><th class="num">Δ potencial</th><th>Explicação</th><th>Evidências</th></tr></thead><tbody>
      ${top.map(x => {
        const [c, t] = NIVEL_RISCO[x.nivel] || ['medio', x.nivel];
        return `<tr data-risco="${esc(x.id)}"><td><b>${esc(x.id)}</b> ${esc(x.titulo)}</td><td><span class="indice ${esc(c)}">${esc(t)}</span></td>
          <td class="num">+${num(x.delta_potencial_dias, 0)} d</td><td style="white-space:normal;font-size:12.5px">${esc(x.explicacao || '')}</td>
          <td>${(x.evidencias || []).map(ev => { const u = api.urlEvidencia(ev); return u ? `<a href="${esc(u)}" target="_blank" rel="noopener" class="p-evidencia">${esc(ev.fonte || ev.rota)}</a>` : ''; }).join(' · ')}</td></tr>`;
      }).join('')}
    </tbody></table>`;
}

/** Campos obrigatórios do /api/painel (com o tipo esperado) que estão ausentes ou malformados. */
export function camposFaltantesPainel(p) {
  if (!p || typeof p !== 'object') return ['(corpo inteiro)'];
  const lista = (k) => Array.isArray(p[k]);
  const obj = (k) => p[k] && typeof p[k] === 'object';
  const req = {
    terminos: obj('terminos'), criticas_independente: lista('criticas_independente'), alertas: lista('alertas'),
    produtividades: lista('produtividades'), curva_s: obj('curva_s') && Array.isArray(p.curva_s.datas) && obj('curva_s') && !!p.curva_s.series,
    producao_semanal: obj('producao_semanal') && Array.isArray(p.producao_semanal.semanas) && !!p.producao_semanal.servicos,
  };
  return Object.entries(req).filter(([, ok]) => !ok).map(([k]) => k);
}

export function renderPainel(erro) {
  if (!raiz) return;
  if (erro) { raiz.innerHTML = `<p class="erro">Não foi possível carregar o painel: ${esc(erro)}</p>`; return; }
  const p = estado.painel;
  if (!p) { raiz.innerHTML = '<p class="vazio">Carregando painel…</p>'; return; }
  // resposta incompleta da API: mensagem legível em vez de exceção dentro do render
  const faltam = camposFaltantesPainel(p);
  if (faltam.length) {
    raiz.innerHTML = `<p class="erro" id="p-incompleto">Resposta incompleta da API do painel: faltam ${esc(faltam.join(', '))}.
      Tente recarregar a página; se persistir, a versão da API não corresponde à interface.</p>`;
    return;
  }
  const t = p.terminos;
  const gap = p.avanco_real - p.avanco_planejado_lb;
  const escopo = p.lote ? `Lote ${esc(p.lote)}` : 'Obra inteira';
  raiz.innerHTML = `
    <h2>Painel gerencial — ${escopo} <small style="font-weight:400;color:var(--texto-3)">data de status ${dataBR(p.data_status)}</small></h2>
    <div class="kpis">
      <div class="kpi"><div class="rot">Avanço físico real</div><div class="val">${pct(p.avanco_real)}</div>
        <span class="det ${gap < 0 ? 'pior' : 'melhor'}">LB previa ${pct(p.avanco_planejado_lb)} (${gap >= 0 ? '+' : '−'}${num(Math.abs(gap), 1)} p.p.)</span></div>
      <div class="kpi"><div class="rot">Término — linha de base</div><div class="val">${dataBR(t.linha_base)}</div>
        <span class="det">contratual ${dataBR(p.termino_contratual)}</span></div>
      <div class="kpi"><div class="rot">Término — construtora</div><div class="val">${dataBR(t.construtora)}</div>
        ${detDelta(diasCorridos(t.construtora, t.linha_base), 'LB')}</div>
      <div class="kpi"><div class="rot">Término — previsão independente</div><div class="val">${dataBR(t.independente)}</div>
        ${detDelta(diasCorridos(t.independente, t.linha_base), 'LB')}<br>${detDelta(diasCorridos(t.independente, t.construtora), 'construtora')}</div>
      <div class="kpi"><div class="rot">Término — simulado</div><div class="val">${dataBR(t.simulado)}</div>
        ${p.simulacao_ativa ? detDelta(diasCorridos(t.simulado, t.independente), 'independente') : '<span class="det">sem simulação ativa (= independente)</span>'}</div>
      <div class="kpi"><div class="rot">Atividades críticas (independente)</div><div class="val">${p.criticas_independente.length}</div>
        <span class="det">${p.criticas_independente.slice(0, 4).map(esc).join(', ')}${p.criticas_independente.length > 4 ? '…' : ''}</span></div>
    </div>
    <div class="grade-painel">
      <div class="bloco largo" id="p-metodos">${metodosHTML(p)}</div>
      <div class="bloco largo" id="p-cobertura">${coberturaHTML()}</div>
      <div class="bloco" id="p-marcos"><h3>Marcos contratuais</h3>${marcosHTML(p.marcos_contratuais)}</div>
      <div class="bloco" id="p-sensibilidade"><h3>Sensibilidade ao método</h3>${sensibilidadeHTML(p.sensibilidade_logica)}</div>
      <div class="bloco largo" id="p-previsao">${previsaoHTML()}</div>
      <div class="bloco largo" id="p-riscos">${riscosHTML()}</div>
      <div class="bloco largo" id="p-historico">${historicoHTML()}</div>
      <div class="bloco largo"><h3>Curva S — avanço físico acumulado (%)</h3><div id="p-curva"></div></div>
      <div class="bloco"><h3>Alertas (${p.alertas.length})</h3>${alertasHTML(p.alertas)}</div>
      <div class="bloco"><h3>Produtividade planejada × efetiva</h3><div style="max-height:320px;overflow:auto">${produtividadesHTML(p.produtividades)}</div></div>
      <div class="bloco largo"><h3>Produção semanal — últimas semanas</h3><div id="p-producao"></div></div>
      ${comparacaoCI ? `<div class="bloco largo">${comparacaoHTML(comparacaoCI)}</div>` : ''}
    </div>`;
  histograma(raiz.querySelector('#p-hist'), previsao);
  if (hist.dados) graficoHistorico(raiz.querySelector('#p-hist-graf'), hist.dados);
  if (v2 && v2.dados) faixas(raiz.querySelector('#p-faixas'), v2.dados);
  raiz.querySelector('#p-v2-rodar')?.addEventListener('click', rodarV2);
  raiz.querySelector('#p-p4-alarg')?.addEventListener('change', (e) => carregarP4(Number(e.target.value)));
  raiz.querySelector('#p-v2-rho')?.addEventListener('input', (e) => { raiz.querySelector('#p-v2-rho-txt').textContent = num(Number(e.target.value), 1); });
  curvaS(raiz.querySelector('#p-curva'), p.curva_s, p.data_status, p.simulacao_ativa);
  producao(raiz.querySelector('#p-producao'), p.producao_semanal);
  raiz.querySelectorAll('[data-id]').forEach(li => li.addEventListener('click', () => {
    selecionar(li.dataset.id, 'painel');
    if (opcoes.irPara) opcoes.irPara('cronograma');
  }));
}

/** Desvio em dias corridos (positivo = atraso), com cor e sinal — nunca só cor. */
function desvioHTML(d) {
  if (d === null || d === undefined) return '<span style="color:var(--texto-3)">—</span>';
  const cls = d > 0 ? 'ruim' : d < 0 ? 'bom' : 'medio';
  const txt = d > 0 ? `▲ +${d} d` : d < 0 ? `▼ −${Math.abs(d)} d` : '= 0 d';
  return `<span class="indice ${cls}" title="${d > 0 ? 'atraso' : d < 0 ? 'antecipação' : 'no prazo'} em dias corridos">${txt}</span>`;
}

function marcosHTML(marcos) {
  if (marcos === undefined) return '<p class="vazio">Esta versão da API não informa marcos contratuais.</p>';
  if (!marcos || !marcos.length) return '<p class="vazio">Nenhum marco contratual para o escopo.</p>';
  return `<div style="max-height:320px;overflow:auto"><table class="tab" id="tab-marcos"><thead><tr>
      <th>Marco</th><th>Prazo (LB)</th><th>Construtora</th><th>Independente</th><th>Simulado</th></tr></thead><tbody>
    ${marcos.map(m => `<tr data-id="${esc(m.id)}" style="cursor:pointer" title="${esc(m.nome)} — clique para ver no cronograma">
      <td><b>${esc(m.id)}</b><br><small style="color:var(--texto-3)">${esc(m.nome)}</small></td>
      <td>${dataBR(m.prazo)}</td>
      <td>${dataBR(m.construtora)}<br>${desvioHTML(m.desvio_construtora)}</td>
      <td>${dataBR(m.independente)}<br>${desvioHTML(m.desvio_independente)}</td>
      <td>${dataBR(m.simulado)}<br>${desvioHTML(m.desvio_simulado)}</td></tr>`).join('')}
    </tbody></table></div>
    <p style="font-size:12px;color:var(--texto-3);margin:6px 0 0">Prazo = data da linha de base (contratual fictícia). Desvio em dias corridos: ▲ atraso · ▼ antecipação.</p>`;
}

function sensibilidadeHTML(s) {
  if (s === undefined) return '<p class="vazio">Esta versão da API não informa a sensibilidade ao método.</p>';
  if (!s) return '<p class="vazio">Sem dados.</p>';
  const d = s.sobrepor && s.retida ? diaDe(s.retida) - diaDe(s.sobrepor) : null;
  return `<div style="display:flex;gap:22px;flex-wrap:wrap">
      <div><div style="font-size:12px;color:var(--texto-2)">Progress override (sobrepor)</div><div style="font-size:18px;font-weight:600">${dataBR(s.sobrepor)}</div></div>
      <div><div style="font-size:12px;color:var(--texto-2)">Retained logic (lógica retida)</div><div style="font-size:18px;font-weight:600">${dataBR(s.retida)}</div></div>
    </div>
    <p style="margin:8px 0 4px;font-weight:600">${d === 0 ? 'O método não altera o término nesta data de status.'
      : d === null ? '' : `A lógica retida termina ${Math.abs(d)} dias corridos ${d > 0 ? 'depois' : 'antes'} do progress override.`}</p>
    <p style="font-size:12px;color:var(--texto-3);margin:0">${esc(s.descricao || '')}</p>`;
}

function alertasHTML(al) {
  if (!al.length) return '<p class="vazio">Nenhum alerta para o escopo.</p>';
  return `<ul class="alertas">${al.map(a => `<li class="${a.nivel}" ${a.atividade_id ? `data-id="${esc(a.atividade_id)}" title="Clique para ver a atividade no cronograma"` : ''}>
    <span class="nivel">${a.nivel === 'alto' ? '▲ alto' : '● médio'}</span>${esc(a.texto)}</li>`).join('')}</ul>`;
}

function classeIndice(i) {
  if (i === null || i === undefined) return '';
  return i >= 0.95 ? 'bom' : i >= 0.85 ? 'medio' : 'ruim';
}
export function indiceHTML(i) {
  if (i === null || i === undefined) return '<span style="color:var(--texto-3)">sem medição</span>';
  const c = classeIndice(i);
  const ic = c === 'bom' ? '✓' : c === 'medio' ? '!' : '▼';
  return `<span class="indice ${c}">${ic} ${num(i, 2)}</span>`;
}

function produtividadesHTML(linhas) {
  if (!linhas.length) return '<p class="vazio">Sem dados.</p>';
  return `<table class="tab"><thead><tr><th>Lote</th><th>Serviço</th><th class="num">Planejada</th><th class="num">Efetiva</th>
    <th>Índice</th><th class="num">Boletins</th></tr></thead><tbody>${linhas.map(l => `<tr>
    <td>${esc(l.lote_id)}</td><td title="${esc(nomeServico(l.servico_id))}">${esc(l.servico_id)}</td>
    <td class="num">${num(l.planejada, 2)} <small>${esc(l.unidade)}</small></td>
    <td class="num">${l.efetiva == null ? '—' : num(l.efetiva, 2)}</td>
    <td>${indiceHTML(l.indice)}</td><td class="num">${l.boletins}</td></tr>`).join('')}</tbody></table>
    <p style="font-size:12px;color:var(--texto-3);margin:6px 0 0">Unidade por equipe·dia útil. Índice = efetiva ÷ planejada (✓ ≥ 0,95 · ! 0,85–0,95 · ▼ &lt; 0,85).</p>`;
}

function comparacaoHTML(c) {
  return `<details class="explic"><summary>Por que a previsão independente difere da construtora? (${c.delta_dias_uteis >= 0 ? '+' : ''}${c.delta_dias_uteis} dias úteis · ${c.delta_dias_corridos >= 0 ? '+' : ''}${c.delta_dias_corridos} dias corridos)</summary>
    <p style="font-size:13px;color:var(--texto-2)">A construtora projeta o remanescente com a produtividade <b>planejada</b>; a previsão independente usa a produtividade <b>medida</b> nos boletins. Mesma rede, mesmas quantidades — só a produtividade muda.</p>
    <ol>${(c.explicacao || []).map(t => `<li>${esc(t)}</li>`).join('')}</ol></details>`;
}

// ---------------- Curva S ----------------
function curvaS(el, cs, dataStatus, simAtiva) {
  if (!cs || !cs.datas.length) { el.innerHTML = '<p class="vazio">Sem dados.</p>'; return; }
  const nomes = ['linha_base', 'construtora', 'independente', 'simulado'].filter(n => cs.series[n]);
  const W = 1000, H = 300, m = { l: 42, r: 16, t: 12, b: 28 };
  const dias = cs.datas.map(diaDe);
  const d0 = dias[0], d1 = dias[dias.length - 1];
  const X = (d) => m.l + (d - d0) / (d1 - d0) * (W - m.l - m.r);
  const Y = (v) => H - m.b - v / 100 * (H - m.t - m.b);
  el.innerHTML = `<div class="legenda-graf">${nomes.map(n => `<span><i style="background:${COR_CENARIO[n]}"></i>${CENARIO_ROTULO[n]}</span>`).join('')}
    <span><i style="background:#d62d2d;width:2px;height:12px"></i>Data de status</span>
    ${simAtiva ? '' : '<span style="color:var(--texto-3)">(sem simulação ativa: a série simulada, tracejada, coincide com a independente)</span>'}</div>`;
  const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'graf', role: 'img', 'aria-label': 'Curva S de avanço físico por cenário' }, el);
  const grade = svg('g', { class: 'grade' }, s);
  for (let v = 0; v <= 100; v += 20) {
    svg('line', { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v) }, grade);
    svg('text', { x: m.l - 6, y: Y(v) + 4, 'text-anchor': 'end' }, s).textContent = `${v}%`;
  }
  // rótulos trimestrais
  let ultimoMes = -1;
  for (const d of dias) {
    const dt = new Date(d * 86400000);
    const mes = dt.getUTCMonth();
    if (mes !== ultimoMes && mes % 3 === 0) {
      svg('text', { x: X(d), y: H - 8, 'text-anchor': 'middle' }, s).textContent = mesCurto(d);
    }
    ultimoMes = mes;
  }
  for (const n of nomes) {
    const pts = cs.series[n].map((v, i) => `${X(dias[i]).toFixed(1)},${Y(v).toFixed(1)}`).join(' ');
    svg('polyline', { points: pts, fill: 'none', stroke: COR_CENARIO[n], 'stroke-width': 2, 'stroke-linejoin': 'round',
      'stroke-dasharray': n === 'simulado' ? '6 3' : null }, s);
  }
  const xs = X(diaDe(dataStatus));
  svg('line', { x1: xs, x2: xs, y1: m.t, y2: H - m.b, stroke: '#d62d2d', 'stroke-width': 1.5 }, s);
  svg('text', { x: xs + 4, y: m.t + 10, fill: '#d62d2d' }, s).textContent = `status ${dataBR(dataStatus)}`;

  // camada de hover (crosshair + tooltip)
  const cruz = svg('line', { y1: m.t, y2: H - m.b, stroke: '#52514e', 'stroke-width': 1, visibility: 'hidden' }, s);
  const area = svg('rect', { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: 'transparent' }, s);
  area.addEventListener('mousemove', (e) => {
    const r = s.getBoundingClientRect();
    const xv = (e.clientX - r.left) / r.width * W;
    let i = 0, best = Infinity;
    dias.forEach((d, k) => { const dd = Math.abs(X(d) - xv); if (dd < best) { best = dd; i = k; } });
    cruz.setAttribute('x1', X(dias[i])); cruz.setAttribute('x2', X(dias[i])); cruz.setAttribute('visibility', 'visible');
    mostrarTooltip(`<b>${dataBR(cs.datas[i])}</b><br>${nomes.map(n => `<span style="color:${COR_CENARIO[n]}">■</span> ${CENARIO_ROTULO[n]}: ${pct(cs.series[n][i])}`).join('<br>')}`, e);
  });
  area.addEventListener('mouseleave', () => { cruz.setAttribute('visibility', 'hidden'); esconderTooltip(); });
}

// ---------------- Produção semanal (barras empilhadas por serviço) ----------------
function producao(el, ps) {
  if (!ps || !ps.semanas.length) { el.innerHTML = '<p class="vazio">Sem medições no período.</p>'; return; }
  const servs = Object.keys(ps.servicos);
  const W = 1000, H = 240, m = { l: 42, r: 10, t: 10, b: 30 };
  const tot = ps.semanas.map((_, i) => servs.reduce((s, k) => s + ps.servicos[k][i], 0));
  const max = Math.max(1, ...tot) * 1.08;
  const n = ps.semanas.length;
  const bw = (W - m.l - m.r) / n;
  const Y = (v) => H - m.b - v / max * (H - m.t - m.b);
  el.innerHTML = `<div class="legenda-graf">${servs.map(k => `<span><i class="q" style="background:${corServico(k)}"></i>${esc(k)} — ${esc(nomeServico(k))}</span>`).join('')}</div>`;
  const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'graf', role: 'img', 'aria-label': 'Produção semanal por serviço' }, el);
  const grade = svg('g', { class: 'grade' }, s);
  const passo = max > 200 ? 50 : max > 80 ? 20 : 10;
  for (let v = 0; v <= max; v += passo) {
    svg('line', { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v) }, grade);
    svg('text', { x: m.l - 6, y: Y(v) + 4, 'text-anchor': 'end' }, s).textContent = `${v}`;
  }
  ps.semanas.forEach((sem, i) => {
    let acum = 0;
    const x = m.l + i * bw + 3;
    for (const k of servs) {
      const v = ps.servicos[k][i];
      if (v <= 0) continue;
      const y1 = Y(acum + v), y0 = Y(acum);
      const r = svg('rect', { x, y: y1, width: Math.max(1, bw - 6), height: Math.max(0.5, y0 - y1 - 2), fill: corServico(k) }, s);
      r.addEventListener('mousemove', (e) => mostrarTooltip(`<b>Semana de ${dataBR(sem)}</b><br>${esc(k)} — ${esc(nomeServico(k))}: ${num(v, 1)}%<br>Total da semana: ${num(tot[i], 1)}%`, e));
      r.addEventListener('mouseleave', esconderTooltip);
      acum += v;
    }
    if (i % 2 === 0) {
      const [, mm, dd] = sem.split('-');
      svg('text', { x: x + (bw - 6) / 2, y: H - 10, 'text-anchor': 'middle' }, s).textContent = `${dd}/${mm}`;
    }
  });
  const nota = document.createElement('p');
  nota.style.cssText = 'font-size:12px;color:var(--texto-3);margin:4px 0 0';
  nota.textContent = `Eixo: ${ps.unidade || '% da quantidade executada na semana'}.`;
  el.appendChild(nota);
}
