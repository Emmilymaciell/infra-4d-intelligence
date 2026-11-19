// Aba Recursos: histograma de equipes (barras empilhadas por serviço + linha de capacidade) e
// nivelamento de recursos (término CPM × nivelado), com controle de "frota compartilhada" (*/SERV).

import { estado, selecionar, nomeServico } from './estado.js';
import { api } from './api.js';
import { svg, diaDe, dataBR, num, esc, mesCurto, mostrarTooltip, esconderTooltip, CENARIO_ROTULO } from './util.js';
import { corServico } from './cores.js';

let raiz = null;
let opcoes = {};
let hist = null, histChave = null, histErro = null;
let niv = null, nivErro = null, nivPedido = null, nivOcupado = false;
let servicoDetalhe = '';
let seq = 0;

export function iniciarRecursos(el, op) {
  raiz = el;
  opcoes = op || {};
}

function chaveHist() {
  return `${estado.cenarioAtivo}|${estado.filtros.lote || ''}`;
}

/** Recarrega o histograma se cenário/lote mudaram (só quando a aba está visível). */
export async function atualizarRecursos(forcar = false) {
  if (!raiz || !estado.projeto || !raiz.offsetParent) return;
  const ch = chaveHist();
  if (forcar || ch !== histChave) {
    histChave = ch;
    hist = null;
    histErro = null;
    render();
    const meu = ++seq;
    try {
      const h = await api.recursosHistograma(estado.cenarioAtivo, estado.filtros.lote || null);
      if (meu !== seq) return;
      hist = h;
    } catch (e) {
      if (meu !== seq) return;
      histErro = e.message;
    }
  }
  render();
}

/** Invalida caches (troca de simulação/cenário recalculado). */
export function invalidarRecursos() {
  histChave = null;
  niv = null;
  nivErro = null;
}

function render() {
  if (!raiz || !estado.projeto) return;
  const servs = [...new Set(estado.projeto.atividades.filter(a => a.tipo === 'tarefa' && a.servico_id && a.quantidade_total)
    .map(a => a.servico_id))];
  const servFrota = raiz.querySelector('#r-frota-serv')?.value || (servs.includes('TER') ? 'TER' : servs[0]);
  const qtdFrota = raiz.querySelector('#r-frota-n')?.value || '2';
  const usarFrota = raiz.querySelector('#r-frota-usar') ? raiz.querySelector('#r-frota-usar').checked : true;
  const cenNiv = raiz.querySelector('#r-niv-cen')?.value || 'linha_base';
  const servHist = servicoDetalhe;

  raiz.innerHTML = `
    <div class="bloco">
      <h3 style="margin-top:0">Histograma de equipes — cenário ${esc(CENARIO_ROTULO[estado.cenarioAtivo])}${estado.filtros.lote ? ` · lote ${esc(estado.filtros.lote)}` : ''}</h3>
      <div class="gantt-barra">
        <label>Detalhar serviço <select id="r-hist-serv"><option value="">Todos (empilhado por serviço)</option>
          ${(hist ? [...new Set(hist.series.map(s => s.servico))] : []).map(s => `<option value="${esc(s)}" ${s === servHist ? 'selected' : ''}>${esc(s)} — ${esc(nomeServico(s))}</option>`).join('')}
        </select></label>
      </div>
      <div id="r-hist">${histErro ? `<p class="erro">Histograma indisponível: ${esc(histErro)}</p>` : hist ? '' : '<p class="vazio">Calculando histograma…</p>'}</div>
    </div>
    <div class="bloco" style="margin-top:14px">
      <h3 style="margin-top:0">Nivelamento de recursos</h3>
      <p style="margin:0 0 8px;color:var(--texto-2);font-size:13px">Compara o término do CPM (sem limite de recursos) com o término
        nivelado respeitando a capacidade de equipes por recurso (lote/serviço). A <b>frota compartilhada</b> limita o serviço na obra
        inteira (chave <span class="mono">*/SERV</span>): por exemplo, só 2 equipes de terraplenagem para os três lotes.</p>
      <div class="gantt-barra" style="gap:14px">
        <label>Cenário <select id="r-niv-cen">${['linha_base', 'construtora', 'independente', 'simulado'].map(c =>
          `<option value="${c}" ${c === cenNiv ? 'selected' : ''}>${esc(CENARIO_ROTULO[c])}</option>`).join('')}</select></label>
        <label class="chk"><input type="checkbox" id="r-frota-usar" ${usarFrota ? 'checked' : ''}> Frota compartilhada</label>
        <label>Serviço <select id="r-frota-serv">${servs.map(s => `<option value="${esc(s)}" ${s === servFrota ? 'selected' : ''}>${esc(s)} — ${esc(nomeServico(s))}</option>`).join('')}</select></label>
        <label>Equipes na obra <input type="number" id="r-frota-n" min="0" max="50" step="1" value="${esc(qtdFrota)}" style="width:70px"></label>
        <button type="button" class="primario" id="r-nivelar" ${nivOcupado ? 'disabled' : ''}>Nivelar</button>
      </div>
      <div id="r-niv">${nivelamentoHTML()}</div>
    </div>`;

  raiz.querySelector('#r-hist-serv').addEventListener('change', (e) => { servicoDetalhe = e.target.value; render(); });
  raiz.querySelector('#r-nivelar').addEventListener('click', nivelar);
  raiz.querySelectorAll('[data-ir]').forEach(el => el.addEventListener('click', () => {
    selecionar(el.dataset.ir, 'recursos');
    if (opcoes.irPara) opcoes.irPara('cronograma');
  }));
  if (hist) desenharHistograma(raiz.querySelector('#r-hist'), hist, servHist);
}

async function nivelar() {
  const cen = raiz.querySelector('#r-niv-cen').value;
  const caps = {};
  if (raiz.querySelector('#r-frota-usar').checked) {
    const n = Number(raiz.querySelector('#r-frota-n').value);
    caps[`*/${raiz.querySelector('#r-frota-serv').value}`] = n;
  }
  nivPedido = { cenario: cen, capacidades: caps };
  nivOcupado = true;
  niv = null;
  nivErro = null;
  render();
  try {
    niv = await api.recursosNivelamento(cen, caps);
  } catch (e) {
    nivErro = e.message;
  } finally {
    nivOcupado = false;
    render();
  }
}

function nivelamentoHTML() {
  if (nivOcupado) return '<p class="vazio">Nivelando (heurística serial, recalcula a rede a cada atividade)…</p>';
  if (nivErro) return `<p class="erro">Nivelamento rejeitado: ${esc(nivErro)}</p>`;
  if (!niv) return '<p class="vazio">Escolha o cenário e a frota e clique em <b>Nivelar</b>. Exemplo: linha de base com <span class="mono">*/TER = 2</span>.</p>';
  // a API aplicou as capacidades pedidas? (rota antiga ignora o parâmetro: a chave */SERV não volta)
  const pedidas = Object.keys((nivPedido && nivPedido.capacidades) || {});
  const ignoradas = pedidas.filter(k => !(niv.capacidades && k in niv.capacidades));
  const aviso = ignoradas.length
    ? `<p class="erro" id="r-niv-ignorado">A API não aplicou a frota compartilhada pedida (${ignoradas.map(esc).join(', ')}): esta versão da rota
       /api/recursos/nivelamento ainda não aceita capacidades. O resultado abaixo usa as capacidades padrão.</p>` : '';
  const d = niv.delta_dias_corridos;
  const cls = d > 0 ? 'pior' : d < 0 ? 'melhor' : '';
  const atr = niv.atividades_atrasadas || [];
  const prova = niv.prova_capacidade || {};
  return `${aviso}
    <div style="display:flex;gap:28px;flex-wrap:wrap;align-items:flex-end" id="r-niv-res">
      <div><div style="font-size:12px;color:var(--texto-2)">Término CPM (sem recursos)</div><div style="font-size:18px;font-weight:600">${dataBR(niv.termino_cpm)}</div></div>
      <div><div style="font-size:12px;color:var(--texto-2)">Término nivelado</div><div style="font-size:18px;font-weight:600">${dataBR(niv.termino_nivelado)}</div></div>
      <div><div class="delta-grande ${cls}" id="r-niv-delta">${d > 0 ? '+' : ''}${d} dias corridos</div>
        <div style="color:var(--texto-2)">${niv.delta_dias_uteis_obra ?? '—'} dias úteis da obra</div></div>
      <div><div style="font-size:12px;color:var(--texto-2)">Atividades deslocadas</div><div style="font-size:18px;font-weight:600">${niv.n_atrasadas}
        <small style="font-weight:400">(${niv.n_atrasadas_por_recurso} por recurso)</small></div></div>
      <div><div style="font-size:12px;color:var(--texto-2)">Prova de capacidade</div>
        <div>${prova.ok ? '<span class="indice bom">✓ nenhuma violação</span>' : `<span class="indice ruim">▼ ${(prova.violacoes || []).length} violações</span>`}
        ${(prova.sobrecarga_irredutivel || []).length ? `<br><small>${prova.sobrecarga_irredutivel.length} dia(s) de sobrecarga irredutível (já em andamento)</small>` : ''}</div></div>
    </div>
    ${pedidas.length && !ignoradas.length ? `<p style="font-size:12.5px;color:var(--texto-2)">Capacidades aplicadas: ${pedidas.map(k => `<span class="mono">${esc(k)} = ${niv.capacidades[k]}</span>`).join(', ')}.</p>` : ''}
    ${atr.length ? `<div style="max-height:300px;overflow:auto;margin-top:8px"><table class="tab" id="r-niv-tab"><thead><tr>
        <th>Atividade</th><th>Recurso</th><th>Início CPM</th><th>Início nivelado</th><th class="num">Atraso (d.u.)</th><th>Motivo</th></tr></thead><tbody>
        ${atr.map(x => `<tr><td><span class="link-ativ" data-ir="${esc(x.id)}">${esc(x.id)}</span></td><td class="mono">${esc(x.recurso || '—')}</td>
          <td>${dataBR(x.es_cpm)}</td><td>${dataBR(x.es_nivelado)}</td><td class="num">${x.atraso_dias_uteis}</td><td>${esc(x.motivo)}</td></tr>`).join('')}
      </tbody></table></div>` : '<p style="color:var(--texto-2)">Nenhuma atividade precisou ser deslocada: as capacidades comportam o plano.</p>'}
    <p style="font-size:11.5px;color:var(--texto-3);margin:6px 0 0">${esc(niv.heuristica || '')} Prioridade: ${esc(niv.prioridade || '')}.</p>`;
}

// ---------------- Histograma (barras empilhadas + linha de capacidade) ----------------
function desenharHistograma(el, h, servico) {
  const series = servico ? h.series.filter(s => s.servico === servico) : h.series;
  if (!series.length) { el.innerHTML = '<p class="vazio">Nenhum uso de equipes no período (tudo concluído ou sem atividades).</p>'; return; }
  // empilha por serviço (visão geral) ou por lote (serviço detalhado)
  const grupoDe = (s) => (servico ? s.lote || s.recurso : s.servico);
  const grupos = [...new Set(series.map(grupoDe))];
  const periodos = [...new Set(series.flatMap(s => s.periodos.map(p => p.periodo)))].sort();
  const valor = new Map(); // grupo|periodo -> equipes (soma dos picos semanais dos recursos do grupo)
  for (const s of series) for (const p of s.periodos) {
    const k = `${grupoDe(s)}|${p.periodo}`;
    valor.set(k, (valor.get(k) || 0) + p.equipes);
  }
  const capacidade = series.reduce((t, s) => t + (s.capacidade || 0), 0);
  const tot = periodos.map(p => grupos.reduce((t, g) => t + (valor.get(`${g}|${p}`) || 0), 0));
  const W = 1000, H = 280, m = { l: 40, r: 70, t: 14, b: 30 };
  const max = Math.max(capacidade, ...tot, 1) * 1.1;
  const bw = (W - m.l - m.r) / periodos.length;
  const Y = (v) => H - m.b - v / max * (H - m.t - m.b);
  const coresLote = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300'];
  const corDe = (g, i) => (servico ? coresLote[i % coresLote.length] : corServico(g));
  el.innerHTML = `<div class="legenda-graf">${grupos.map((g, i) => `<span><i class="q" style="background:${corDe(g, i)}"></i>${esc(g)}${servico ? '' : ` — ${esc(nomeServico(g))}`}</span>`).join('')}
    <span><svg width="22" height="8"><line x1="0" y1="4" x2="22" y2="4" stroke="#d62d2d" stroke-width="2" stroke-dasharray="5 3"/></svg>Capacidade (${capacidade} equipes)</span></div>`;
  const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'graf', id: 'r-hist-svg', role: 'img', 'aria-label': 'Histograma de equipes por período' }, el);
  const passo = max > 40 ? 10 : max > 16 ? 5 : max > 6 ? 2 : 1;
  for (let v = 0; v <= max; v += passo) {
    svg('line', { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), stroke: '#e6e8e3' }, s);
    svg('text', { x: m.l - 6, y: Y(v) + 4, 'text-anchor': 'end' }, s).textContent = v;
  }
  let ultimoMes = -1;
  periodos.forEach((p, i) => {
    const x = m.l + i * bw;
    let acum = 0;
    grupos.forEach((g, gi) => {
      const v = valor.get(`${g}|${p}`) || 0;
      if (!v) return;
      const y1 = Y(acum + v), y0 = Y(acum);
      const r = svg('rect', { x: x + 1, y: y1, width: Math.max(1, bw - 2), height: Math.max(0.5, y0 - y1 - 1), fill: corDe(g, gi), class: 'r-barra' }, s);
      r.addEventListener('mousemove', (e) => mostrarTooltip(`<b>Semana de ${dataBR(p)}</b><br>${esc(g)}: ${v} equipe(s) (pico)<br>Total: ${tot[i]} · capacidade ${capacidade}`, e));
      r.addEventListener('mouseleave', esconderTooltip);
      acum += v;
    });
    const mes = new Date(diaDe(p) * 86400000).getUTCMonth();
    if (mes !== ultimoMes) {
      if (mes % 2 === 0) svg('text', { x: x + bw / 2, y: H - 10, 'text-anchor': 'middle' }, s).textContent = mesCurto(diaDe(p));
      ultimoMes = mes;
    }
  });
  if (capacidade > 0) {
    svg('line', { x1: m.l, x2: W - m.r, y1: Y(capacidade), y2: Y(capacidade), stroke: '#d62d2d', 'stroke-width': 2, 'stroke-dasharray': '6 3', id: 'r-hist-cap' }, s);
    svg('text', { x: W - m.r + 4, y: Y(capacidade) + 4, fill: '#d62d2d', 'font-weight': 600 }, s).textContent = `cap. ${capacidade}`;
  }
  const nota = document.createElement('p');
  nota.style.cssText = 'font-size:12px;color:var(--texto-3);margin:4px 0 0';
  const sob = h.sobrealocacao || { total_dias_sobrealocados: 0, recursos: [] };
  nota.innerHTML = `Barras = pico semanal de equipes de cada recurso, somado por ${servico ? 'lote' : 'serviço'}; a linha é a soma das capacidades
    dos recursos exibidos. ${esc(h.regra || '')}<br>
    ${sob.total_dias_sobrealocados ? `<b style="color:var(--critico)">▲ ${sob.total_dias_sobrealocados} dia(s) sobrealocados</b>: ${sob.recursos.map(r => esc(r.recurso)).join(', ')}.`
      : '✓ Nenhum recurso acima da capacidade neste cenário.'}`;
  el.appendChild(nota);
}

export function renderRecursos() { atualizarRecursos(); }
