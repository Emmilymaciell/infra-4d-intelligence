// Linha de balanço (diagrama tempo × km) em SVG — leitura típica de obra linear.
// Cada atividade com trecho vira uma linha de (início, km_ini) a (término, km_fim) no cenário ativo;
// OAEs e atividades curtas (< 1 km) viram blocos (tempo × trecho).

import { estado, passaFiltro, resultadoAtivo, selecionar, nomeServico } from './estado.js';
import { svg, diaDe, dataBR, mesCurto, primeiroDiaMes, proximoMes, esc, num, mostrarTooltip, esconderTooltip, CENARIO_ROTULO } from './util.js';
import { estacaHTML } from './estacas.js';

// último tooltip mostrado (gerador + evento): redesenha quando a estaca chega da API
let ultimoTip = null;
function tip(gerar, e) {
  ultimoTip = { gerar, e };
  mostrarTooltip(gerar(), e);
}
function redesenharTip() {
  const t = document.querySelector('.tooltip');
  if (ultimoTip && t && !t.hidden) mostrarTooltip(ultimoTip.gerar(), ultimoTip.e);
}
import { corServico, COR_OAE } from './cores.js';

const corDe = (a) => (a.oae_id ? COR_OAE : corServico(a.servico_id));

let raiz = null;
let sobreporLB = false;

// conflitos entre frentes sucessivas (/api/recursos/conflitos-balanco), por chave cenário|lote|buffers
const conf = { chave: null, dados: null, erro: null, carregando: false };
let apiRef = null;

export function iniciarBalanco(el, chkLB, api) {
  raiz = el;
  apiRef = api || null;
  if (chkLB) chkLB.addEventListener('change', () => { sobreporLB = chkLB.checked; renderBalanco(); });
  for (const id of ['#lb-conflitos', '#lb-buffer-km', '#lb-buffer-dias', '#lb-real']) {
    const e = document.querySelector(id);
    if (e) e.addEventListener('change', () => renderBalanco());
  }
}

/** Esquece os conflitos em cache (ex.: simulação mudou o cenário simulado). */
export function invalidarConflitos() { conf.chave = null; conf.dados = null; }

// linha REAL executada (/api/fiscalizacao/linha-real), por lote
const real = {};
function garantirReal() {
  if (!document.querySelector('#lb-real')?.checked || !apiRef) return null;
  const ch = estado.filtros.lote || '';
  if (real[ch] && (real[ch].dados || real[ch].erro)) return real[ch];
  if (!real[ch]) {
    real[ch] = { carregando: true };
    apiRef.fiscLinhaReal(ch || null)
      .then(d => { real[ch] = { dados: d }; })
      .catch(e => { real[ch] = { erro: e.message }; })
      .finally(() => renderBalanco());
  }
  return null;
}

function parametrosConflito() {
  const ligado = document.querySelector('#lb-conflitos')?.checked;
  const bkm = Math.max(0, Number(document.querySelector('#lb-buffer-km')?.value || 1));
  const bd = Math.max(0, Number(document.querySelector('#lb-buffer-dias')?.value || 0));
  return { ligado, bkm, bd, chave: `${estado.cenarioAtivo}|${estado.filtros.lote || ''}|${bkm}|${bd}` };
}

/** Garante os conflitos da chave atual; quando chegam, redesenha. */
function garantirConflitos() {
  const p = parametrosConflito();
  if (!p.ligado || !apiRef) return null;
  if (conf.chave === p.chave && (conf.dados || conf.erro)) return conf;
  if (conf.carregando === p.chave) return null;
  conf.carregando = p.chave;
  apiRef.recursosConflitos(estado.cenarioAtivo, p.bkm, p.bd, estado.filtros.lote || null)
    .then(d => { conf.dados = d; conf.erro = null; })
    .catch(e => { conf.dados = null; conf.erro = e.message; })
    .finally(() => { conf.chave = p.chave; conf.carregando = false; renderBalanco(); });
  return null;
}

/** Conflito visível: alguma das duas atividades passa nos filtros globais. */
function conflitosVisiveis(c) {
  return (c.conflitos || []).filter(x => x.atividades.some(id => estado.ativ.has(id) && passaFiltro(estado.ativ.get(id))));
}

function atividadesDoDiagrama() {
  return estado.projeto.atividades.filter(a => a.tipo === 'tarefa' && a.km_ini != null && a.km_fim != null);
}

export function renderBalanco() {
  if (!raiz || !estado.projeto) return;
  if (!raiz.offsetParent) return; // aba oculta: renderiza ao abrir
  const res = resultadoAtivo();
  const resLB = estado.cenarios.linha_base;
  if (!res) { raiz.innerHTML = '<p class="vazio">Cenário indisponível.</p>'; return; }
  const todas = atividadesDoDiagrama();
  const vis = todas.filter(passaFiltro);
  const resumo = document.querySelector('#lb-resumo');
  if (resumo) resumo.innerHTML = `Cenário <b>${esc(CENARIO_ROTULO[estado.cenarioAtivo])}</b> · ${vis.length} de ${todas.length} atividades com trecho`;
  if (!vis.length) { raiz.innerHTML = '<p class="vazio">Nenhuma atividade com trecho atende aos filtros.</p>'; legenda([]); listaConflitos(null); return; }

  const W = Math.max(700, raiz.clientWidth - 14);
  const H = Math.max(460, Math.min(720, window.innerHeight - 300));
  const m = { l: 58, r: 18, t: 22, b: 30 };
  const kmMax = Math.max(...estado.projeto.lotes.map(l => l.km_fim));
  const d0 = estado.diaInicio - 7, d1 = estado.diaFim + 21;
  const X = (d) => m.l + (d - d0) / (d1 - d0) * (W - m.l - m.r);
  const Y = (km) => H - m.b - km / kmMax * (H - m.t - m.b); // km cresce para cima

  raiz.innerHTML = '';
  const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Linha de balanço: tempo no eixo horizontal, quilômetro no eixo vertical' }, raiz);

  // grade: meses
  const pxMes = 30.4 * (W - m.l - m.r) / (d1 - d0);
  const cadaN = pxMes >= 46 ? 1 : pxMes >= 23 ? 2 : 3;
  for (let mm = proximoMes(d0); mm <= d1; mm = proximoMes(mm)) {
    svg('line', { x1: X(mm), x2: X(mm), y1: m.t, y2: H - m.b, stroke: '#eceee9' }, s);
    if (new Date(mm * 86400000).getUTCMonth() % cadaN === 0 && X(mm) < W - 30) {
      svg('text', { x: X(mm) + 3, y: H - 10 }, s).textContent = mesCurto(mm);
    }
  }
  // grade: km e divisas de lote
  for (let k = 0; k <= kmMax; k += 5) {
    svg('line', { x1: m.l, x2: W - m.r, y1: Y(k), y2: Y(k), stroke: k % 10 === 0 ? '#dfe2dc' : '#f0f1ee' }, s);
    if (k % 10 === 0) svg('text', { x: m.l - 6, y: Y(k) + 4, 'text-anchor': 'end' }, s).textContent = `km ${k}`;
  }
  for (const l of estado.projeto.lotes) {
    svg('line', { x1: m.l, x2: W - m.r, y1: Y(l.km_ini), y2: Y(l.km_ini), stroke: '#9aa3ad', 'stroke-width': 1.2 }, s);
    const t = svg('text', { x: m.l + 4, y: Y((l.km_ini + l.km_fim) / 2) + 4, 'font-weight': 600, fill: '#9aa3ad' }, s);
    t.textContent = l.id;
  }
  svg('line', { x1: m.l, x2: W - m.r, y1: Y(kmMax), y2: Y(kmMax), stroke: '#9aa3ad', 'stroke-width': 1.2 }, s);

  // linha de base (opcional), por baixo
  if (sobreporLB && resLB) {
    const g = svg('g', { 'data-camada': 'lb', opacity: 0.75 }, s);
    for (const a of vis) {
      const r = resLB.atividades[a.id];
      if (!r || !r.inicio) continue;
      desenhar(g, a, r, { X, Y, cor: corDe(a), largura: 1.3, tracejado: '5 4', bloco: 'contorno' });
    }
  }

  // cenário ativo
  const sel = estado.selecionada;
  const gA = svg('g', { 'data-camada': 'cenario' }, s);
  // críticas por cima das demais
  const ordenadas = [...vis].sort((a, b) => Number(!!res.atividades[a.id]?.critica) - Number(!!res.atividades[b.id]?.critica));
  for (const a of ordenadas) {
    const r = res.atividades[a.id];
    if (!r || !r.inicio) continue;
    const g = svg('g', { class: 'ativ', 'data-id': a.id }, gA);
    if (a.id === sel) desenhar(g, a, r, { X, Y, cor: '#2a78d6', largura: 9, opacidade: 0.35, bloco: 'halo' });
    desenhar(g, a, r, { X, Y, cor: corDe(a), largura: r.critica ? 3.6 : 1.8 });
    desenhar(g, a, r, { X, Y, cor: 'transparent', largura: 12, bloco: 'alvo' }); // área de clique
  }

  // data de status
  const xs = X(diaDe(estado.dataStatus));
  svg('line', { x1: xs, x2: xs, y1: m.t - 6, y2: H - m.b, stroke: '#d62d2d', 'stroke-width': 1.5, 'stroke-dasharray': '4 3' }, s);
  svg('text', { x: xs + 4, y: m.t - 8, fill: '#d62d2d', 'font-weight': 600 }, s).textContent = `status ${dataBR(estado.dataStatus)}`;

  // linha REAL executada (diários sintéticos): traço contínuo por frente, sobre a projetada esmaecida
  const rl = garantirReal();
  const resumoReal = document.querySelector('#lb-resumo');
  if (document.querySelector('#lb-real')?.checked) {
    gA.setAttribute('opacity', '0.45');
    if (rl && rl.dados) {
      const gR = svg('g', { 'data-camada': 'real' }, s);
      const fr = (rl.dados.frentes || []).filter(f => estado.ativ.has(f.atividade_id) && passaFiltro(estado.ativ.get(f.atividade_id)));
      for (const f of fr) {
        if (!f.pontos || f.pontos.length < 2) continue;
        const pts = f.pontos.map(p => `${X(diaDe(p.data)).toFixed(1)},${Y(p.km).toFixed(1)}`).join(' ');
        const g = svg('g', { class: 'real', 'data-id': f.atividade_id, style: 'cursor:pointer' }, gR);
        svg('polyline', { points: pts, fill: 'none', stroke: '#fff', 'stroke-width': 5, 'stroke-linejoin': 'round', opacity: 0.9 }, g);
        svg('polyline', { points: pts, fill: 'none', stroke: corServico(f.servico_id), 'stroke-width': 2.6, 'stroke-linejoin': 'round' }, g);
        const u = f.pontos[f.pontos.length - 1];
        svg('circle', { cx: X(diaDe(u.data)), cy: Y(u.km), r: 3.5, fill: corServico(f.servico_id), stroke: '#fff', 'stroke-width': 1.5 }, g);
        g.addEventListener('mousemove', (e) => tip(() => `<b>${esc(f.atividade_id)}</b> — linha REAL executada (sintética)<br>
          ${dataBR(f.pontos[0].data)} → ${dataBR(u.data)} · km ${num(f.pontos[0].km, 2)} → ${num(f.km_atual, 2)}
          (estaca ${estacaHTML(f.km_atual, redesenharTip)})<br>ritmo médio ${num(f.ritmo_medio_km_por_dia_corrido, 3)} km/dia corrido · ${esc(f.status)}`, e));
        g.addEventListener('mouseleave', esconderTooltip);
        g.addEventListener('click', () => selecionar(f.atividade_id, 'balanco'));
      }
      if (resumoReal) resumoReal.innerHTML += ` · <span id="lb-real-n">${fr.length}</span> frentes com linha real`;
    } else if (rl && rl.erro && resumoReal) {
      resumoReal.innerHTML += ` · <span style="color:var(--critico)">linha real indisponível: ${esc(rl.erro)}</span>`;
    }
  }

  // conflitos entre frentes: faixa no período + círculo no pior momento (km × data)
  const c = garantirConflitos();
  if (c && c.dados) {
    const gC = svg('g', { 'data-camada': 'conflitos' }, s);
    conflitosVisiveis(c.dados).forEach((x) => {
      const idx = c.dados.conflitos.indexOf(x);
      const g = svg('g', { class: 'conflito', 'data-conflito': idx, style: 'cursor:pointer' }, gC);
      const xa = X(diaDe(x.data)), xb = X(diaDe(x.data_fim) + 1), y = Y(x.km);
      svg('rect', { x: xa, y: y - 5, width: Math.max(3, xb - xa), height: 10, rx: 5, fill: '#d62d2d', opacity: 0.18 }, g);
      const xp = X(diaDe(x.data_pior || x.data));
      svg('circle', { cx: xp, cy: y, r: 8, fill: '#fff', stroke: '#d62d2d', 'stroke-width': 2.5 }, g);
      svg('text', { x: xp, y: y + 4, 'text-anchor': 'middle', 'font-weight': 700, fill: '#d62d2d', style: 'font-size:11px' }, g).textContent = '!';
      g.addEventListener('mousemove', (e) => tip(() => tooltipConflito(x), e));
      g.addEventListener('mouseleave', esconderTooltip);
      g.addEventListener('click', () => selecionar(x.atividades[1] || x.atividades[0], 'balanco'));
    });
  }

  gA.addEventListener('click', (e) => {
    const g = e.target.closest('[data-id]');
    if (g) selecionar(g.dataset.id, 'balanco');
  });
  gA.addEventListener('mousemove', (e) => {
    const g = e.target.closest('[data-id]');
    if (!g) { esconderTooltip(); return; }
    const id = g.dataset.id;
    tip(() => tooltip(id), e);
  });
  gA.addEventListener('mouseleave', esconderTooltip);
  legenda(vis);
  listaConflitos(c);
}

function tipoConflito(x) {
  const t = [];
  if (x.ultrapassagem) t.push('ultrapassagem');
  if (x.espacial) t.push('espacial');
  if (x.temporal) t.push('temporal');
  return t.join(' + ') || '—';
}

function tooltipConflito(x) {
  return `<b>Conflito entre frentes — ${esc(x.segmento || x.lote || '')}</b><br>
    ${esc(x.atividades[0])} → ${esc(x.atividades[1])} (${esc(x.servicos.join(' → '))})<br>
    ${dataBR(x.data)} a ${dataBR(x.data_fim)} (${x.dias} dia(s)) · km ${num(x.km, 2)} (estaca ${estacaHTML(x.km, redesenharTip)})<br>
    Distância mínima entre frentes: ${num(x.distancia_km_min, 3)} km · folga mínima ${num(x.folga_dias_min, 1)} dia(s)<br>
    Tipo: ${esc(tipoConflito(x))} · pior momento ${dataBR(x.data_pior)}`;
}

function listaConflitos(c) {
  const el = document.querySelector('#balanco-conflitos');
  if (!el) return;
  const p = parametrosConflito();
  if (!p.ligado) { el.innerHTML = ''; return; }
  if (!c) { el.innerHTML = '<p class="vazio">Calculando conflitos entre frentes…</p>'; return; }
  if (c.erro) { el.innerHTML = `<p class="erro">Conflitos indisponíveis: ${esc(c.erro)}</p>`; return; }
  const lista = conflitosVisiveis(c.dados);
  el.innerHTML = `<h3>Conflitos entre frentes sucessivas (${lista.length}${lista.length !== c.dados.n_conflitos ? ` de ${c.dados.n_conflitos}` : ''})</h3>
    <p style="font-size:12px;color:var(--texto-3);margin:0 0 6px">Frente sucessora a menos de ${num(c.dados.buffer_km, 1)} km
      ${c.dados.buffer_dias ? `/ ${num(c.dados.buffer_dias, 0)} dia(s)` : ''} da antecessora. ${esc(c.dados.regra || '')}</p>
    ${lista.length ? `<div style="max-height:260px;overflow:auto"><table class="tab" id="lb-tab-conflitos"><thead><tr>
      <th>Trecho</th><th>Frentes (antecessora → sucessora)</th><th>Período</th><th class="num">km</th><th class="num">Dist. mín. (km)</th>
      <th class="num">Folga mín. (dias)</th><th>Tipo</th></tr></thead><tbody>
      ${lista.map(x => `<tr data-ir="${esc(x.atividades[1] || x.atividades[0])}" style="cursor:pointer">
        <td>${esc(x.segmento || x.lote || '—')}</td><td>${esc(x.atividades[0])} → <b>${esc(x.atividades[1])}</b></td>
        <td>${dataBR(x.data)} – ${dataBR(x.data_fim)}</td><td class="num">${num(x.km, 2)}</td>
        <td class="num">${num(x.distancia_km_min, 3)}</td><td class="num">${num(x.folga_dias_min, 1)}</td><td>${esc(tipoConflito(x))}</td></tr>`).join('')}
    </tbody></table></div>` : '<p style="color:var(--texto-2)">Nenhum conflito com estes filtros e buffers.</p>'}`;
  el.querySelectorAll('tr[data-ir]').forEach(tr => tr.addEventListener('click', () => selecionar(tr.dataset.ir, 'balanco')));
}

/** Desenha uma atividade: linha inclinada (trecho ≥ 1 km) ou bloco (OAE / trecho curto). */
function desenhar(pai, a, r, { X, Y, cor, largura, tracejado, opacidade, bloco }) {
  const xa = X(diaDe(r.inicio)), xb = X(diaDe(r.termino) + 1);
  const curto = a.oae_id || (a.km_fim - a.km_ini) < 1;
  if (curto) {
    const ya = Y(a.km_fim), yb = Y(a.km_ini);
    const h = Math.max(5, yb - ya);
    const y = (ya + yb) / 2 - h / 2;
    const attrs = { x: xa, y, width: Math.max(2, xb - xa), height: h, rx: 1 };
    if (bloco === 'alvo') svg('rect', { ...attrs, x: xa - 4, y: y - 4, width: Math.max(2, xb - xa) + 8, height: h + 8, fill: 'transparent' }, pai);
    else if (bloco === 'halo') svg('rect', { ...attrs, x: xa - 3, y: y - 3, width: Math.max(2, xb - xa) + 6, height: h + 6, fill: cor, opacity: opacidade }, pai);
    else if (bloco === 'contorno') svg('rect', { ...attrs, fill: 'none', stroke: cor, 'stroke-width': largura, 'stroke-dasharray': tracejado }, pai);
    else svg('rect', { ...attrs, fill: cor, stroke: largura > 3 ? '#d62d2d' : 'none', 'stroke-width': largura > 3 ? 1.5 : 0 }, pai);
    return;
  }
  svg('line', {
    x1: xa, y1: Y(a.km_ini), x2: xb, y2: Y(a.km_fim), stroke: cor, 'stroke-width': largura,
    'stroke-linecap': 'round', 'stroke-dasharray': tracejado || null, opacity: opacidade ?? null,
  }, pai);
}

function tooltip(id) {
  const a = estado.ativ.get(id);
  const r = resultadoAtivo().atividades[id];
  const lb = estado.cenarios.linha_base && estado.cenarios.linha_base.atividades[id];
  return `<b>${esc(id)}</b> — ${esc(nomeServico(a.servico_id))}<br>
    km ${num(a.km_ini, 1)} → ${num(a.km_fim, 1)} · estaca ${estacaHTML(a.km_ini, redesenharTip)} → ${estacaHTML(a.km_fim, redesenharTip)}<br>
    ${esc(CENARIO_ROTULO[estado.cenarioAtivo])}: ${dataBR(r.inicio)} → ${dataBR(r.termino)}<br>
    LB: ${dataBR(lb && lb.inicio)} → ${dataBR(lb && lb.termino)}<br>
    Folga total: ${r.folga_total ?? '—'}${r.critica ? ' · <b style="color:#ff9b9b">CRÍTICA</b>' : ''}${r.caminho_mais_longo ? ' · caminho mais longo' : ''}`;
}

function legenda(vis) {
  const el = document.querySelector('#balanco-legenda');
  if (!el) return;
  const servs = [...new Set(vis.filter(a => !a.oae_id).map(a => a.servico_id))];
  const temOAE = vis.some(a => a.oae_id);
  el.innerHTML = servs.map(sv => `<span><i style="background:${corServico(sv)}"></i>${esc(sv)} — ${esc(nomeServico(sv))}</span>`).join('')
    + (temOAE ? `<span><i class="q" style="background:${COR_OAE}"></i>OAE (bloco tempo × trecho)</span>` : '')
    + `<span><i style="background:#555;height:4px"></i>Crítica (traço grosso)</span>`
    + (sobreporLB ? `<span><svg width="20" height="6"><line x1="0" y1="3" x2="20" y2="3" stroke="#555" stroke-dasharray="5 4"/></svg>Linha de base</span>` : '')
    + `<span><i style="background:#d62d2d;width:2px;height:12px"></i>Data de status</span>`
    + (document.querySelector('#lb-real')?.checked ? `<span><svg width="22" height="8"><line x1="0" y1="4" x2="22" y2="4" stroke="#555" stroke-width="3"/></svg>Linha REAL executada (diários sintéticos; projetada esmaecida)</span>` : '')
    + (document.querySelector('#lb-conflitos')?.checked ? `<span><svg width="16" height="16"><circle cx="8" cy="8" r="6" fill="#fff" stroke="#d62d2d" stroke-width="2"/></svg>Conflito entre frentes (pior momento; faixa = duração)</span>` : '')
    + `<span style="color:var(--texto-3)">Inclinação = ritmo de avanço (km por tempo); linhas que se aproximam indicam conflito entre frentes.</span>`;
}
