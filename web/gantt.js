// Gantt em SVG feito à mão + tabela de atividades.

import { estado, gruposDeExibicao, passaFiltro, resultadoAtivo, selecionar, fracaoExecutada, nomeServico } from './estado.js';
import { svg, diaDe, dataBR, mesCurto, primeiroDiaMes, proximoMes, esc, mostrarTooltip, esconderTooltip, pillStatus, num, CENARIO_ROTULO } from './util.js';

const LINHA = 20;
const GRUPO = 22;
const CAB = 34;
const COR = {
  barra: '#6f9fd8', critica: '#e34948', lb: '#8d939a', exec: 'rgba(10,20,40,.38)',
  status: '#d62d2d', seta: '#52514e', setaDet: '#d62d2d', grade: '#eceee9',
};

let zoom = 1;
let raiz = null;

export function legendaGantt() {
  return `
    <span><svg width="22" height="10"><rect x="0" y="1" width="22" height="8" rx="2" fill="${COR.barra}"/></svg>Cenário ativo</span>
    <span><svg width="22" height="10"><rect x="0" y="1" width="22" height="8" rx="2" fill="${COR.critica}"/></svg>Crítica</span>
    <span><svg width="22" height="10"><rect x="0" y="1" width="22" height="8" rx="2" fill="${COR.barra}"/><rect x="0" y="1" width="12" height="8" rx="2" fill="${COR.exec}"/></svg>Executado (proporcional à quantidade)</span>
    <span><svg width="22" height="10"><rect x="0" y="4" width="22" height="3" fill="${COR.lb}"/></svg>Linha de base</span>
    <span><svg width="12" height="12"><path d="M6 1 L11 6 L6 11 L1 6 Z" fill="#12263f"/></svg>Marco</span>
    <span><svg width="10" height="12"><line x1="5" y1="0" x2="5" y2="12" stroke="${COR.status}" stroke-width="2" stroke-dasharray="3 2"/></svg>Data de status</span>`;
}

export function iniciarGantt(el) {
  raiz = el;
  document.querySelectorAll('.gantt-barra [data-zoom]').forEach(b => {
    b.addEventListener('click', () => {
      zoom = Number(b.dataset.zoom);
      document.querySelectorAll('.gantt-barra [data-zoom]').forEach(x => x.classList.toggle('ativo', x === b));
      renderGantt();
    });
  });
}

function linhasVisiveis() {
  const out = [];
  let cabecalhoPendente = null; // cabeçalho de lote (nível 0) sem itens próprios
  for (const g of gruposDeExibicao()) {
    const itens = g.itens.filter(passaFiltro);
    if (g.nivel === 0 && !g.itens.length) { cabecalhoPendente = g; continue; }
    if (g.nivel === 0) cabecalhoPendente = null;
    if (!itens.length) continue;
    if (cabecalhoPendente) { out.push({ grupo: cabecalhoPendente }); cabecalhoPendente = null; }
    out.push({ grupo: g });
    for (const a of itens) out.push({ a });
  }
  return out;
}

export function renderGantt() {
  if (!raiz || !estado.projeto) return;
  const res = resultadoAtivo();
  if (!res) { raiz.innerHTML = '<p class="vazio">Cenário indisponível.</p>'; return; }
  const resLB = estado.cenarios.linha_base;
  const antigo = raiz.querySelector('.g-corpo');
  const scrollTop = antigo ? antigo.scrollTop : 0;
  const antigoH = raiz.querySelector('.g-barras');
  const scrollLeft = antigoH ? antigoH.scrollLeft : 0;

  const linhas = linhasVisiveis();
  if (!linhas.length) {
    raiz.innerHTML = '<p class="vazio">Nenhuma atividade atende aos filtros.</p>';
    return;
  }
  const d0 = estado.diaInicio - 7;
  const d1 = estado.diaFim + 45; // folga à direita para o rótulo de data dos marcos
  const larguraDisp = Math.max(600, (raiz.clientWidth || 900) - 272 - 20); // 20 = barra de rolagem vertical
  const pxDia = (larguraDisp * zoom) / (d1 - d0);
  const W = Math.ceil((d1 - d0) * pxDia);
  const X = (dia) => (dia - d0) * pxDia;

  // posições Y
  let y = 0;
  const posY = new Map();
  for (const l of linhas) {
    l.y = y;
    if (l.a) posY.set(l.a.id, y);
    y += l.grupo ? GRUPO : LINHA;
  }
  const H = y + 4;

  raiz.innerHTML = `
    <div class="g-cab"><div class="g-canto">Atividade · cenário <b>${esc(CENARIO_ROTULO[estado.cenarioAtivo])}</b></div><div class="g-cab-scroll"></div></div>
    <div class="g-corpo"><div class="g-rotulos"></div><div class="g-barras"></div></div>`;
  const cabScroll = raiz.querySelector('.g-cab-scroll');
  const corpo = raiz.querySelector('.g-corpo');
  const rotulos = raiz.querySelector('.g-rotulos');
  const barras = raiz.querySelector('.g-barras');

  // ---- cabeçalho (meses) ----
  const sc = svg('svg', { width: W, height: CAB }, cabScroll);
  const pxMes = 30.4 * pxDia;
  const cadaN = pxMes >= 46 ? 1 : pxMes >= 23 ? 2 : 3; // rótulo a cada N meses, sem sobreposição
  for (let m = primeiroDiaMes(d0); m <= d1; m = proximoMes(m)) {
    const x = X(m);
    if (x >= 0) svg('line', { x1: x, y1: 14, x2: x, y2: CAB, stroke: '#c9ccc5' }, sc);
    const mesIdx = new Date(m * 86400000).getUTCMonth();
    if (x >= 0 && mesIdx % cadaN === 0 && W - x > 40) {
      const t = svg('text', { x: Math.max(0, x) + 4, y: 26 }, sc);
      t.textContent = mesCurto(m);
    }
  }
  const ds = diaDe(estado.dataStatus);
  const ts = svg('text', { x: X(ds) + 3, y: 11, fill: COR.status, 'font-weight': 600 }, sc);
  ts.textContent = `status ${dataBR(estado.dataStatus)}`;
  svg('line', { x1: X(ds), y1: 0, x2: X(ds), y2: CAB, stroke: COR.status, 'stroke-width': 2 }, sc);

  // ---- rótulos (coluna fixa) ----
  const sr = svg('svg', { width: 270, height: H }, rotulos);
  // ---- barras ----
  const sb = svg('svg', { width: W, height: H }, barras);
  const defs = svg('defs', {}, sb);
  for (const [id, cor] of [['seta', COR.seta], ['setaDet', COR.setaDet]]) {
    const mk = svg('marker', { id: `g-${id}`, viewBox: '0 0 8 8', refX: 7, refY: 4, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' }, defs);
    svg('path', { d: 'M0 0 L8 4 L0 8 Z', fill: cor }, mk);
  }
  // grade mensal
  const gGrade = svg('g', {}, sb);
  for (let m = proximoMes(d0); m <= d1; m = proximoMes(m)) {
    svg('line', { x1: X(m), y1: 0, x2: X(m), y2: H, stroke: COR.grade }, gGrade);
  }

  const sel = estado.selecionada;
  for (const l of linhas) {
    if (l.grupo) {
      const g = l.grupo;
      const gr = svg('g', { class: 'grp' }, sr);
      svg('rect', { x: 0, y: l.y, width: 270, height: GRUPO, fill: g.nivel === 0 ? '#e3ecf7' : '#f1f4f8' }, gr);
      const t = svg('text', { x: 6 + g.nivel * 10, y: l.y + 15 }, gr);
      t.textContent = g.rotulo.length > 44 ? g.rotulo.slice(0, 43) + '…' : g.rotulo;
      svg('rect', { x: 0, y: l.y, width: W, height: GRUPO, fill: g.nivel === 0 ? '#e3ecf7' : '#f6f8fb', opacity: 0.7 }, sb);
      continue;
    }
    const a = l.a;
    const r = res.atividades[a.id];
    const lb = resLB && resLB.atividades[a.id];
    const ehSel = a.id === sel;

    // rótulo
    const gl = svg('g', { class: `linha${ehSel ? ' sel' : ''}`, 'data-id': a.id }, sr);
    svg('rect', { class: 'fundo', x: 0, y: l.y, width: 270, height: LINHA, fill: 'transparent' }, gl);
    const t1 = svg('text', { x: 16, y: l.y + 14, 'font-weight': r && r.critica ? 600 : 400, fill: r && r.critica ? '#a51d1d' : null }, gl);
    t1.textContent = a.id;
    const t2 = svg('text', { x: 110, y: l.y + 14, fill: '#52514e' }, gl);
    const nome = nomeServico(a.servico_id) === '—' ? a.nome : nomeServico(a.servico_id);
    t2.textContent = nome.length > 26 ? nome.slice(0, 25) + '…' : nome;

    // barra
    const gb = svg('g', { class: `linha${ehSel ? ' sel' : ''}`, 'data-id': a.id }, sb);
    svg('rect', { class: 'fundo', x: 0, y: l.y, width: W, height: LINHA, fill: 'transparent' }, gb);
    if (lb && lb.inicio && a.tipo === 'tarefa') {
      const xa = X(diaDe(lb.inicio)), xb = X(diaDe(lb.termino) + 1);
      svg('rect', { x: xa, y: l.y + 15, width: Math.max(2, xb - xa), height: 3, fill: COR.lb }, gb);
    }
    if (r && r.inicio) {
      if (a.tipo !== 'tarefa') {
        const xm = X(diaDe(r.termino || r.inicio));
        const c = l.y + 9;
        svg('path', { d: `M${xm} ${c - 6} L${xm + 6} ${c} L${xm} ${c + 6} L${xm - 6} ${c} Z`, fill: r.critica ? COR.critica : '#12263f' }, gb);
        const tt = svg('text', { x: xm + 9, y: l.y + 13, fill: '#52514e' }, gb);
        tt.textContent = dataBR(r.termino || r.inicio);
      } else {
        const xa = X(diaDe(r.inicio)), xb = X(diaDe(r.termino) + 1);
        const w = Math.max(2, xb - xa);
        svg('rect', { x: xa, y: l.y + 3, width: w, height: 11, rx: 2, fill: r.critica ? COR.critica : COR.barra }, gb);
        const fe = fracaoExecutada(a);
        if (fe > 0) svg('rect', { x: xa, y: l.y + 3, width: Math.max(1, w * fe), height: 11, rx: 2, fill: COR.exec }, gb);
        if (ehSel) svg('rect', { x: xa - 2, y: l.y + 1, width: w + 4, height: 15, rx: 3, fill: 'none', stroke: '#2a78d6', 'stroke-width': 2 }, gb);
      }
    }
  }

  // linha da data de status
  svg('line', { x1: X(ds), y1: 0, x2: X(ds), y2: H, stroke: COR.status, 'stroke-width': 1.5, 'stroke-dasharray': '4 3' }, sb);

  // setas de dependência da atividade selecionada
  if (sel && posY.has(sel)) {
    const gS = svg('g', {}, sb);
    const rels = [...(estado.preds.get(sel) || []), ...(estado.succs.get(sel) || [])];
    const det = res.atividades[sel] && res.atividades[sel].determinante;
    for (const rel of rels) {
      const p = res.atividades[rel.predecessora], s = res.atividades[rel.sucessora];
      if (!p || !s || !posY.has(rel.predecessora) || !posY.has(rel.sucessora) || !p.inicio || !s.inicio) continue;
      const tipo = rel.tipo || 'FS';
      const xp = X(tipo[0] === 'S' ? diaDe(p.inicio) : diaDe(p.termino) + 1);
      const xs = X(tipo[1] === 'S' ? diaDe(s.inicio) : diaDe(s.termino) + 1);
      const yp = posY.get(rel.predecessora) + 9, ys = posY.get(rel.sucessora) + 9;
      const ehDet = rel.sucessora === sel && rel.predecessora === det;
      const xm = Math.max(xp, xs - 8) + 6;
      svg('path', {
        d: `M${xp} ${yp} H${xm} V${ys} H${xs}`, fill: 'none',
        stroke: ehDet ? COR.setaDet : COR.seta, 'stroke-width': ehDet ? 2 : 1.2,
        'marker-end': `url(#g-${ehDet ? 'setaDet' : 'seta'})`, opacity: 0.9,
      }, gS);
    }
  }

  // eventos
  const aoClicar = (e) => {
    const g = e.target.closest('[data-id]');
    if (g) selecionar(g.dataset.id, 'gantt');
  };
  const aoPassar = (e) => {
    const g = e.target.closest('[data-id]');
    if (!g) { esconderTooltip(); return; }
    mostrarTooltip(tooltipAtividade(g.dataset.id), e);
  };
  for (const s of [sr, sb]) {
    s.addEventListener('click', aoClicar);
    s.addEventListener('mousemove', aoPassar);
    s.addEventListener('mouseleave', esconderTooltip);
  }
  barras.addEventListener('scroll', () => { cabScroll.scrollLeft = barras.scrollLeft; });
  corpo.scrollTop = scrollTop;
  barras.scrollLeft = scrollLeft;
  cabScroll.scrollLeft = scrollLeft;
}

function tooltipAtividade(id) {
  const a = estado.ativ.get(id);
  const r = resultadoAtivo().atividades[id];
  const lb = estado.cenarios.linha_base && estado.cenarios.linha_base.atividades[id];
  return `<b>${esc(id)}</b><br>${esc(a.nome)}<br>
    ${esc(CENARIO_ROTULO[estado.cenarioAtivo])}: ${dataBR(r.inicio)} → ${dataBR(r.termino)}
    ${r.duracao != null ? ` · ${r.duracao} d.u.` : ''}<br>
    LB: ${dataBR(lb && lb.inicio)} → ${dataBR(lb && lb.termino)}<br>
    Folga total: ${r.folga_total ?? '—'} · ${r.critica ? '<b style="color:#ff9b9b">CRÍTICA</b>' : 'não crítica'}`;
}

/** Rola o Gantt até a atividade selecionada (se visível). */
export function rolarGanttPara(id) {
  if (!raiz) return;
  const g = raiz.querySelector(`.g-rotulos [data-id="${CSS.escape(id)}"]`);
  const corpo = raiz.querySelector('.g-corpo');
  if (!g || !corpo || !corpo.offsetParent) return;
  const y = Number(g.querySelector('rect').getAttribute('y'));
  if (y < corpo.scrollTop || y > corpo.scrollTop + corpo.clientHeight - 30) corpo.scrollTop = Math.max(0, y - corpo.clientHeight / 3);
  const res = resultadoAtivo().atividades[id];
  const barras = raiz.querySelector('.g-barras');
  if (res && res.inicio && barras) {
    const rect = raiz.querySelector(`.g-barras [data-id="${CSS.escape(id)}"] rect:nth-of-type(2)`);
    if (rect) {
      const x = Number(rect.getAttribute('x'));
      if (x < barras.scrollLeft || x > barras.scrollLeft + barras.clientWidth - 40) barras.scrollLeft = Math.max(0, x - 80);
    }
  }
}

// ---------------- Tabela ----------------
let raizTabela = null;
export function iniciarTabela(el) { raizTabela = el; }

export function renderTabela() {
  if (!raizTabela || !estado.projeto) return;
  const res = resultadoAtivo();
  if (!res) { raizTabela.innerHTML = '<p class="vazio">Cenário indisponível.</p>'; return; }
  const linhas = [];
  for (const g of gruposDeExibicao()) for (const a of g.itens) if (passaFiltro(a)) linhas.push(a);
  if (!linhas.length) { raizTabela.innerHTML = '<p class="vazio">Nenhuma atividade atende aos filtros.</p>'; return; }
  const sel = estado.selecionada;
  const top = raizTabela.scrollTop;
  raizTabela.innerHTML = `<table class="tab"><thead><tr>
    <th>Atividade</th><th>Serviço</th><th>Lote</th><th class="num">km</th><th>Início</th><th>Término</th>
    <th class="num">Duração (d.u.)</th><th class="num">Folga total</th><th>Crítica</th><th>Status</th><th class="num">Executado</th>
  </tr></thead><tbody>${linhas.map(a => {
    const r = res.atividades[a.id] || {};
    return `<tr data-id="${esc(a.id)}" class="${a.id === sel ? 'sel' : ''}">
      <td><b>${esc(a.id)}</b></td><td>${esc(nomeServico(a.servico_id))}</td><td>${esc(a.lote_id || '—')}</td>
      <td class="num">${a.km_ini != null ? `${num(a.km_ini, 1)}–${num(a.km_fim, 1)}` : '—'}</td>
      <td>${dataBR(r.inicio)}</td><td>${dataBR(r.termino)}</td>
      <td class="num">${r.duracao ?? '—'}</td><td class="num">${r.folga_total ?? '—'}</td>
      <td>${r.critica ? '<span class="pill crit">sim</span>' : ''}</td><td>${pillStatus(a.status)}</td>
      <td class="num">${a.tipo === 'tarefa' ? `${num(fracaoExecutada(a) * 100, 0)}%` : '—'}</td></tr>`;
  }).join('')}</tbody></table>`;
  raizTabela.scrollTop = top;
  raizTabela.querySelector('tbody').addEventListener('click', (e) => {
    const tr = e.target.closest('tr[data-id]');
    if (tr) selecionar(tr.dataset.id, 'tabela');
  });
}

export function rolarTabelaPara(id) {
  if (!raizTabela || !raizTabela.offsetParent) return;
  const tr = raizTabela.querySelector(`tr[data-id="${CSS.escape(id)}"]`);
  if (!tr) return;
  const t = tr.offsetTop, h = raizTabela.clientHeight;
  if (t < raizTabela.scrollTop + 30 || t > raizTabela.scrollTop + h - 30) raizTabela.scrollTop = Math.max(0, t - h / 3);
}
