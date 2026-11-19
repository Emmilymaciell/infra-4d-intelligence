// Aba "Análises": sensibilidade (tornado), plano de recuperação, diagrama de massas (Brückner),
// produtividade da terraplenagem pela DMT e exportação para BI. Tudo da API (?obra= via api.js);
// todo dado externo passa por esc()/num()/dataBR() antes de ir para HTML; eventos só por addEventListener.

import { estado, selecionar } from './estado.js';
import { api } from './api.js';
import { svg, esc, num, dataBR, diaDe, isoDe, mesCurto, mostrarTooltip, esconderTooltip, seloSimulacao } from './util.js';

let raiz = null;
let opcoes = {};
// estado de cada subseção: {chave, carregando|dados|erro}
const sec = { curva: {}, sens: {}, recup: {}, acel: {}, massas: {}, terra: {}, clima: {}, tend: {}, back: {}, atrib: {}, bi: {} };
const msgs = { recup: null, terra: null, acel: null };
let aplicando = false;

export function iniciarAnalises(el, op) {
  raiz = el;
  opcoes = op || {};
}

/** Esquece resultados (ex.: após simulação, o plano de recuperação muda). */
export function invalidarAnalises() {
  for (const k of Object.keys(sec)) sec[k] = {};
}

function obter(nome, chave, fn) {
  const s = sec[nome];
  if (s.chave === chave && (s.dados || s.erro || s.carregando)) return s;
  sec[nome] = { chave, carregando: true };
  fn().then(d => { if (sec[nome].chave === chave) sec[nome] = { chave, dados: d }; })
    .catch(e => { if (sec[nome].chave === chave) sec[nome] = { chave, erro: e.message || String(e) }; })
    .finally(() => renderAnalises());
  return sec[nome];
}

const v = (sel) => raiz.querySelector(sel)?.value;
const dias = (d) => `${d > 0 ? '+' : d < 0 ? '−' : ''}${num(Math.abs(d), 0)}`;

export function renderAnalises() {
  if (!raiz || !estado.projeto || !raiz.offsetParent) return;
  const p = v('#an-sens-p') || '0.1';
  const eq = v('#an-sens-eq') || '1';
  const prazo = v('#an-rec-prazo') ?? '';
  const marco = v('#an-rec-marco') ?? '';
  const folga = v('#an-rec-folga') ?? '';
  const passo = v('#an-mas-passo') || '100';
  const s1 = obter('sens', `${p}|${eq}`, () => api.sensibilidade(p, eq));
  const s2 = obter('recup', `${prazo}|${marco}|${folga}`, () => api.recuperacao({ prazo, marco, folga_max: folga }));
  const s3 = obter('massas', passo, () => Promise.all([api.massasDiagrama(passo), api.massasCoerencia()]));
  const s4 = obter('terra', 'x', () => api.produtividadeTerraplenagem());
  const s5 = obter('bi', 'x', () => api.exportarTabelas());
  const intens = v('#an-cli-int') || '0.3';
  const desloc = v('#an-cli-desl') || '4';
  const s7 = obter('tend', 'x', () => api.tendencia());
  const baseCs = v('#an-cs-base') || 'fisica';
  const loteCs = v('#an-cs-lote') ?? '';
  const s8 = obter('curva', `${baseCs}|${loteCs}`, () => api.curvaS(baseCs, loteCs));
  const s9 = obter('back', 'x', () => api.backtest());
  const marcoBk = v('#an-bk-marco') || 'M-FIM';
  const refBk = v('#an-bk-ref') || 'realidade_simulada';
  const dataBk = v('#an-bk-data') || dataPadraoBk(s9.dados, marcoBk);
  const s11 = dataBk ? obter('atrib', `${marcoBk}|${dataBk}`, () => api.backtestAtribuicao(marcoBk, dataBk)) : {};
  const prazoAc = v('#an-ac-prazo') ?? '';
  const limAc = v('#an-ac-lim') || '2';
  const s10 = obter('acel', `${prazoAc}|${limAc}`, () => api.aceleracao(prazoAc, limAc));
  const marcoTend = v('#an-tend-marco') || 'M-FIM';
  const s6 = obter('clima', `${intens}|${desloc}`, () => api.clima(intens, desloc));
  const marcos = estado.projeto.atividades.filter(a => a.tipo === 'marco_termino');

  raiz.innerHTML = `
    <nav class="an-indice">${[['an-curvas', 'Curva S'], ['an-sens', 'Sensibilidade'], ['an-recup', 'Plano de recuperação'], ['an-acel', 'Aceleração'], ['an-massas', 'Diagrama de massas'],
      ['an-terra', 'Produtividade pela DMT'], ['an-clima', 'Clima'], ['an-tend', 'Tendência dos marcos'], ['an-back', 'Backtest'], ['an-bi', 'Exportar (BI e GIS)']].map(([id, t]) => `<a href="#${esc(id)}" data-ancora="${esc(id)}">${esc(t)}</a>`).join(' · ')}</nav>

    <section class="bloco an-sec" id="an-curvas">
      <h3>Curva S física e financeira</h3>
      <div class="gantt-barra">
        <label>Base <select id="an-cs-base">${[['fisica', 'Física (esforço equipe·dia)'], ['financeira', 'Financeira (R$ fictícios)']].map(([k, r]) => `<option value="${esc(k)}" ${k === baseCs ? 'selected' : ''}>${esc(r)}</option>`).join('')}</select></label>
        <label>Lote <select id="an-cs-lote"><option value="">Obra inteira</option>${estado.projeto.lotes.map(l => `<option value="${esc(l.id)}" ${l.id === loteCs ? 'selected' : ''}>${esc(l.id)}</option>`).join('')}</select></label>
      </div>
      ${seloSimulacao(s8.dados)}${curvaSHTML(s8)}
    </section>

    <section class="bloco an-sec" id="an-sens">
      <h3>Sensibilidade do término (tornado)</h3>
      <div class="gantt-barra">
        <label>Variação de produtividade <select id="an-sens-p">${['0.05', '0.1', '0.2'].map(x => `<option value="${x}" ${x === p ? 'selected' : ''}>±${num(Number(x) * 100, 0)}%</option>`).join('')}</select></label>
        <label>Equipes a mais <select id="an-sens-eq">${['1', '2'].map(x => `<option value="${x}" ${x === eq ? 'selected' : ''}>+${x}</option>`).join('')}</select></label>
      </div>
      ${seloSimulacao(s1.dados)}${tornadoHTML(s1)}
    </section>

    <section class="bloco an-sec" id="an-recup">
      <h3>Plano de recuperação</h3>
      <div class="gantt-barra">
        <label>Prazo-alvo <input type="date" id="an-rec-prazo" value="${esc(prazo)}"></label>
        <label>ou marco <select id="an-rec-marco"><option value="">término da obra</option>${marcos.map(m => `<option value="${esc(m.id)}" ${m.id === marco ? 'selected' : ''}>${esc(m.id)}</option>`).join('')}</select></label>
        <label>Folga máx. (d.u.) <input type="number" id="an-rec-folga" min="0" step="1" value="${esc(folga)}" placeholder="padrão" style="width:80px"></label>
        <button type="button" id="an-rec-calc">Calcular</button>
        <span style="font-size:12px;color:var(--texto-3)">Sem prazo: o término da linha de base (contratual fictício).</span>
      </div>
      ${seloSimulacao(s2.dados)}${recuperacaoHTML(s2)}
    </section>

    <section class="bloco an-sec" id="an-acel">
      <h3>Aceleração: término × custo adicional</h3>
      <div class="gantt-barra">
        <label>Prazo-alvo <input type="date" id="an-ac-prazo" value="${esc(prazoAc)}"></label>
        <label>Equipes extras por frente (máx.) <select id="an-ac-lim">${['1', '2', '3', '4'].map(x => `<option value="${x}" ${x === limAc ? 'selected' : ''}>${x}</option>`).join('')}</select></label>
        <button type="button" id="an-ac-calc">Calcular</button>
        <span style="font-size:12px;color:var(--texto-3)">Sem prazo: o término da linha de base.</span>
      </div>
      ${seloSimulacao(s10.dados)}${aceleracaoHTML(s10)}
    </section>

    <section class="bloco an-sec" id="an-massas">
      <h3>Diagrama de massas (Brückner)</h3>
      <div class="gantt-barra">
        <label>Passo <select id="an-mas-passo">${['20', '100', '200'].map(x => `<option value="${x}" ${x === passo ? 'selected' : ''}>${x} m</option>`).join('')}</select></label>
      </div>
      ${massasHTML(s3)}
    </section>

    <section class="bloco an-sec" id="an-terra">
      <h3>Produtividade da terraplenagem pela DMT</h3>
      ${seloSimulacao(s4.dados)}${terraHTML(s4)}
    </section>

    <section class="bloco an-sec" id="an-clima">
      <h3>Clima: chuva acima, abaixo e fora de época</h3>
      <div class="gantt-barra">
        <label>Intensidade <select id="an-cli-int">${['0.1', '0.2', '0.3', '0.5'].map(x => `<option value="${x}" ${x === intens ? 'selected' : ''}>±${num(Number(x) * 100, 0)}%</option>`).join('')}</select></label>
        <label>Deslocamento da estação <select id="an-cli-desl">${['0', '2', '4', '8'].map(x => `<option value="${x}" ${x === desloc ? 'selected' : ''}>${x} semana(s)</option>`).join('')}</select></label>
      </div>
      ${seloSimulacao(s6.dados)}${climaHTML(s6)}
    </section>

    <section class="bloco an-sec" id="an-tend">
      <h3>Tendência dos marcos (MTA)</h3>
      ${seloSimulacao(s7.dados)}${tendenciaHTML(s7, marcoTend)}
    </section>

    <section class="bloco an-sec" id="an-back">
      <h3>Backtest: quanto cada previsão errou</h3>
      ${seloSimulacao(s9.dados)}${backtestHTML(s9, marcoBk, refBk)}
      ${porQueErrouHTML(s9, s11, dataBk)}
    </section>

    <section class="bloco an-sec" id="an-bi">
      <h3>Exportar para BI e GIS</h3>
      ${biHTML(s5)}
    </section>`;

  // eventos
  raiz.querySelectorAll('[data-ancora]').forEach(a => a.addEventListener('click', (e) => {
    e.preventDefault();
    raiz.querySelector(`#${a.dataset.ancora}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }));
  for (const id of ['#an-sens-p', '#an-sens-eq', '#an-mas-passo', '#an-rec-marco', '#an-cli-int', '#an-cli-desl', '#an-tend-marco', '#an-cs-base', '#an-cs-lote', '#an-bk-marco', '#an-bk-ref', '#an-ac-lim', '#an-bk-data']) raiz.querySelector(id)?.addEventListener('change', () => renderAnalises());
  raiz.querySelector('#an-rec-calc')?.addEventListener('click', () => { sec.recup = {}; renderAnalises(); });
  raiz.querySelector('#an-ac-calc')?.addEventListener('click', () => { sec.acel = {}; renderAnalises(); });
  raiz.querySelectorAll('[data-aplicar]').forEach(b => b.addEventListener('click', () => aplicar(b.dataset.aplicar)));
  raiz.querySelectorAll('[data-ir]').forEach(el => el.addEventListener('click', () => {
    selecionar(el.dataset.ir, 'analises');
    if (opcoes.irPara) opcoes.irPara('cronograma');
  }));
  if (s1.dados) tornado(raiz.querySelector('#an-tornado'), s1.dados);
  if (s3.dados) bruckner(raiz.querySelector('#an-bruckner'), s3.dados[0]);
  if (s8.dados) graficoCurvaS(raiz.querySelector('#an-cs-graf'), s8.dados);
  if (s9.dados) { graficoBacktest(raiz.querySelector('#an-bk-graf'), s9.dados, marcoBk, refBk); ligarCliqueBacktest(s9.dados); }
  if (s10.dados) graficoAceleracao(raiz.querySelector('#an-ac-graf'), s10.dados);
  if (s7.dados) graficoTendencia(raiz.querySelector('#an-tend-graf'), s7.dados, marcoTend);
  const gisSel = raiz.querySelector('#an-gis-camada');
  if (gisSel) gisSel.addEventListener('change', () => { raiz.querySelector('#an-gis-link').href = api.urlGeojson(gisSel.value); });
}

// ---------------------------------------------------------------- a) tornado
function tornadoHTML(s) {
  if (s.carregando) return '<p class="vazio">Recalculando o término para cada grupo (lote × serviço)…</p>';
  if (s.erro) return `<p class="erro">Sensibilidade indisponível: ${esc(s.erro)}</p>`;
  const d = s.dados;
  const g = d.grupos || [];
  const nZero = g.filter(x => x.efeito_zero).length;
  return `<p style="font-size:12.5px;margin:4px 0">Referência: cenário ${esc(d.cenario_referencia || '')}, término <b>${dataBR(d.termino_referencia)}</b>.
      Cada barra mostra o efeito no término de ±${num((d.p || 0) * 100, 0)}% de produtividade no grupo (verde = melhorar, vermelho = piorar), em dias úteis;
      o losango é o efeito de +${num(d.equipes, 0)} equipe(s). <span id="an-sens-resumo">${num(g.length, 0)} grupos, ${num(nZero, 0)} com efeito zero.</span></p>
    <div id="an-tornado"></div>
    <details><summary style="cursor:pointer;font-size:12.5px">Explicação por grupo</summary>
      <ul style="font-size:12.5px;line-height:1.5">${g.map(x => `<li><b>${esc(x.lote_id)} / ${esc(x.servico_id)}</b>: ${esc(x.explicacao || '')}</li>`).join('')}</ul></details>
    <p style="font-size:11.5px;color:var(--texto-3);margin:4px 0 0">Regras: ${Object.entries(d.regras || {}).map(([k, t]) => `<b>${esc(k)}</b> = ${esc(t)}`).join(' · ')}.
      ${num(d.execucoes_motor, 0)} execuções do motor.</p>`;
}

function tornado(el, d) {
  if (!el) return;
  const g = [...(d.grupos || [])].sort((a, b) => Math.abs(b.amplitude_dias_uteis || 0) - Math.abs(a.amplitude_dias_uteis || 0)
    || [a.lote_id, a.servico_id].join('/').localeCompare([b.lote_id, b.servico_id].join('/')));
  const W = 1000, linha = 22, m = { l: 120, r: 210, t: 24, b: 24 };
  const H = m.t + m.b + g.length * linha;
  const vals = g.flatMap(x => [x.melhorar?.delta_dias_uteis || 0, x.piorar?.delta_dias_uteis || 0, x.equipes?.delta_dias_uteis || 0]);
  const lim = Math.max(1, ...vals.map(Math.abs)) * 1.08;
  const X = (vv) => m.l + (vv + lim) / (2 * lim) * (W - m.l - m.r);
  const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'graf', role: 'img', 'aria-label': 'Tornado de sensibilidade do término' }, el);
  svg('line', { x1: X(0), x2: X(0), y1: m.t - 8, y2: H - m.b + 4, stroke: '#52514e', 'stroke-width': 1.5 }, s);
  svg('text', { x: X(0), y: m.t - 10, 'text-anchor': 'middle' }, s).textContent = '0 (término de referência)';
  svg('text', { x: X(-lim) + 2, y: H - 6 }, s).textContent = `antecipa ${num(lim, 0)} d.u.`;
  svg('text', { x: X(lim) - 2, y: H - 6, 'text-anchor': 'end' }, s).textContent = `atrasa ${num(lim, 0)} d.u.`;
  g.forEach((x, i) => {
    const y = m.t + i * linha;
    const gr = svg('g', { class: 'an-barra', 'data-grupo': [x.lote_id, x.servico_id].join('/') }, s);
    svg('text', { x: m.l - 8, y: y + 15, 'text-anchor': 'end', 'font-weight': x.no_caminho_determinante?.length ? 600 : 400 }, gr)
      .textContent = [x.lote_id, x.servico_id].join(' / '); // textContent: não interpreta HTML
    const dm = x.melhorar?.delta_dias_uteis || 0, dp = x.piorar?.delta_dias_uteis || 0;
    if (dm) svg('rect', { x: Math.min(X(dm), X(0)), y: y + 4, width: Math.abs(X(dm) - X(0)), height: 14, fill: '#1baf7a', rx: 2 }, gr);
    if (dp) svg('rect', { x: Math.min(X(dp), X(0)), y: y + 4, width: Math.abs(X(dp) - X(0)), height: 14, fill: '#e34948', rx: 2 }, gr);
    const de = x.equipes?.delta_dias_uteis;
    if (de) {
      const xe = X(de);
      svg('path', { d: `M${xe} ${y + 4} L${xe + 6} ${y + 11} L${xe} ${y + 18} L${xe - 6} ${y + 11} Z`, fill: '#12263f' }, gr);
    }
    const marcas = [];
    if (x.efeito_zero) marcas.push('= efeito zero');
    if (x.assimetrico) marcas.push('assimétrico');
    if (x.reverso) marcas.push('⚠ reverso');
    const t = svg('text', { x: W - m.r + 8, y: y + 15, class: 'an-marca' }, gr);
    t.textContent = `${dias(dm)} / ${dias(dp)} d.u.${marcas.length ? ` · ${marcas.join(' · ')}` : ''}`;
    if (x.reverso) t.setAttribute('fill', '#a51d1d');
    gr.addEventListener('mousemove', (e) => mostrarTooltip(`<b>${esc(x.lote_id)} / ${esc(x.servico_id)}</b><br>
      melhorar: ${dias(dm)} d.u. (término ${dataBR(x.melhorar?.termino)}) · piorar: ${dias(dp)} d.u. (término ${dataBR(x.piorar?.termino)})<br>
      +equipes: ${dias(de || 0)} d.u. · menor folga ${num(x.menor_folga_total, 0)} d.u.<br>${esc(x.explicacao || '')}`, e));
    gr.addEventListener('mouseleave', esconderTooltip);
  });
}

// ---------------------------------------------------------------- b) recuperação
const VIAB = {
  viavel: ['bom', 'viável'], acima_da_melhor_semana: ['medio', 'acima da melhor semana'],
  inviavel_sem_mudanca_de_metodo: ['ruim', 'inviável sem mudança de método'], inviavel: ['ruim', 'inviável'],
};
const pillViab = (k) => { const [c, t] = VIAB[k] || ['', k]; return `<span class="indice ${esc(c)}">${esc(t)}</span>`; };

function recuperacaoHTML(s) {
  if (s.carregando) return '<p class="vazio">Procurando o menor esforço que alcança o prazo (várias execuções do motor)…</p>';
  if (s.erro) return `<p class="erro">Plano de recuperação indisponível: ${esc(s.erro)}</p>`;
  const r = s.dados;
  const plano = r.plano || [];
  const nAj = (r.ajustes_produtividade || []).length;
  return `<div style="display:flex;gap:26px;flex-wrap:wrap;align-items:flex-end" id="an-rec-resumo">
      <div><div class="rot-p">Alvo</div><b>${esc(r.alvo || '')}</b></div>
      <div><div class="rot-p">Prazo</div><b>${dataBR(r.prazo)}</b></div>
      <div><div class="rot-p">Término atual</div><b>${dataBR(r.termino_atual)}</b></div>
      <div><div class="rot-p">Término alcançado</div><b id="an-rec-alcancado">${dataBR(r.termino_alcancado)}</b></div>
      <div><div class="rot-p">Viabilidade</div>${pillViab(r.viabilidade)} ${r.cumpre_prazo ? '<span class="pill ok">cumpre o prazo</span>' : '<span class="pill crit">não cumpre</span>'}</div>
    </div>
    ${r.motivo ? `<p style="font-size:12.5px;margin:6px 0">${esc(r.motivo)}</p>` : ''}
    ${plano.length ? `<div style="max-height:340px;overflow:auto"><table class="tab" id="an-rec-tab"><thead><tr>
      <th>Frente</th><th class="num">Remanescente</th><th class="num">Duração atual → necessária</th><th class="num">Produtividade medida → necessária</th>
      <th class="num">Equipes</th><th class="num">Melhor semana</th><th>Viabilidade</th></tr></thead><tbody>
      ${plano.map(x => `<tr><td><span class="link-ativ" data-ir="${esc(x.id)}">${esc(x.id)}</span></td>
        <td class="num">${num(x.quantidade_remanescente, 0)} <small>${esc(x.unidade || '')}</small></td>
        <td class="num">${num(x.duracao_atual, 0)} → <b>${num(x.duracao_necessaria, 0)}</b></td>
        <td class="num">${num(x.produtividade_medida, 2)} → <b>${num(x.produtividade_necessaria, 2)}</b> <small>(+${num(x.aumento_pct, 1)}%)</small></td>
        <td class="num">${num(x.equipes_atuais, 0)} → ${num(x.equipes_necessarias, 0)}</td>
        <td class="num">${num(x.melhor_semana, 2)} <small>(${num(x.razao_melhor_semana, 2)}×)</small></td>
        <td>${pillViab(x.viabilidade)}</td></tr>`).join('')}
    </tbody></table></div>` : '<p style="color:var(--texto-2)">Nenhuma frente precisa mudar: o término atual já cumpre o prazo.</p>'}
    <div class="sim-botoes">
      <button type="button" class="primario" data-aplicar="recup-prod" ${!nAj || aplicando ? 'disabled' : ''}>Aplicar como simulação (produtividade)</button>
      <button type="button" data-aplicar="recup-eq" ${!(r.ajustes_equipes || []).length || aplicando ? 'disabled' : ''}>Aplicar como simulação (equipes)</button>
    </div>
    ${msgs.recup ? `<p class="${msgs.recup.erro ? 'erro' : ''}" id="an-rec-msg">${esc(msgs.recup.texto)}</p>` : ''}
    <p style="font-size:11.5px;color:var(--texto-3);margin:4px 0 0">${esc(r.metodo || '')} Viabilidade por frente: necessária ≤ melhor semana medida = viável;
      até 1,25× = acima da melhor semana; acima disso = inviável sem mudança de método.</p>`;
}

// ---------------------------------------------------------------- c) massas
function massasHTML(s) {
  if (s.carregando) return '<p class="vazio">Calculando seções, volumes e ordenadas de Brückner…</p>';
  if (s.erro) return `<p class="erro">Diagrama de massas indisponível: ${esc(s.erro)}</p>`;
  const [d, c] = s.dados;
  const segs = c.segmentos || [];
  return `<p class="erro" style="background:#fff8e1;border-color:#ffd24a;color:#4a3900">${esc(d.aviso || c.aviso || 'Terreno sintético.')}</p>
    <div id="an-bruckner"></div>
    <p style="font-size:12.5px;margin:4px 0" id="an-mas-resumo">${num((d.estacas || []).length, 0)} ordenadas, ${num((d.pontos_passagem_km || []).length, 0)} pontos de passagem,
      ${num((d.compensacoes || []).length, 0)} ondas de compensação. Fator de homogeneização ${num(d.fator_homogeneizacao, 2)}, empolamento ${num(d.empolamento, 2)}.</p>
    <h4 style="margin:10px 0 4px">Coerência com a terraplenagem do cronograma</h4>
    <div style="max-height:300px;overflow:auto"><table class="tab" id="an-coer-tab"><thead><tr><th>Segmento</th><th>Atividade</th>
      <th class="num">Corte (m³)</th><th class="num">Aterro (m³)</th><th class="num">Geométrico (m³)</th><th class="num">No cronograma (m³)</th>
      <th class="num">Diferença</th><th>Situação</th></tr></thead><tbody>
      ${segs.map(x => `<tr><td>${esc(x.segmento_id)}</td><td><span class="link-ativ" data-ir="${esc(x.atividade_id)}">${esc(x.atividade_id)}</span></td>
        <td class="num">${num(x.volume_corte_m3, 0)}</td><td class="num">${num(x.volume_aterro_m3, 0)}</td><td class="num">${num(x.volume_geometrico_m3, 0)}</td>
        <td class="num">${num(x.quantidade_dataset_m3, 0)}</td>
        <td class="num"><span class="indice ${Math.abs(x.diferenca_relativa || 0) <= 0.2 ? 'bom' : 'medio'}">${num((x.diferenca_relativa || 0) * 100, 1)}%</span></td>
        <td>${esc(x.situacao || '')}</td></tr>`).join('')}
    </tbody></table></div>
    <p style="font-size:11.5px;color:var(--texto-3);margin:4px 0 0">${esc(d.metodo || '')}. ${esc(c.criterio || '')}</p>`;
}

function bruckner(el, d) {
  if (!el) return;
  const est = d.estacas || [];
  if (est.length < 2) { el.innerHTML = '<p class="vazio">Sem ordenadas.</p>'; return; }
  const W = 1000, H = 300, m = { l: 70, r: 14, t: 16, b: 30 };
  const k0 = est[0].km, k1 = est[est.length - 1].km;
  const ords = est.map(e => e.ordenada_m3);
  const mn = Math.min(0, ...ords), mx = Math.max(0, ...ords);
  const X = (k) => m.l + (k - k0) / (k1 - k0) * (W - m.l - m.r);
  const Y = (o) => H - m.b - (o - mn) / ((mx - mn) || 1) * (H - m.t - m.b);
  const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'graf', id: 'an-bruckner-svg', role: 'img', 'aria-label': 'Diagrama de Brückner: ordenadas de volume por km' }, el);
  // ondas de compensação (faixas alternadas, com tooltip)
  (d.compensacoes || []).forEach((cp, i) => {
    const r = svg('rect', { x: X(cp.km_ini), y: m.t, width: Math.max(1, X(cp.km_fim) - X(cp.km_ini)), height: H - m.t - m.b,
      fill: i % 2 ? '#e3ecf7' : '#f1f4f8', class: 'an-onda' }, s);
    r.addEventListener('mousemove', (e) => mostrarTooltip(`<b>Onda ${i + 1}</b>: km ${num(cp.km_ini, 2)} → ${num(cp.km_fim, 2)}<br>
      volume ${num(cp.volume_m3, 0)} m³ · DMT ${num(cp.dmt_m, 0)} m · ${esc(cp.sentido || '')}${cp.aberta ? ' · aberta' : ''}`, e));
    r.addEventListener('mouseleave', esconderTooltip);
  });
  for (const l of estado.projeto.lotes) {
    if (l.km_ini > k0 && l.km_ini < k1) svg('line', { x1: X(l.km_ini), x2: X(l.km_ini), y1: m.t, y2: H - m.b, stroke: '#9aa3ad', 'stroke-dasharray': '4 3' }, s);
  }
  // eixo
  for (let i = 0; i <= 4; i++) {
    const o = mn + (mx - mn) * i / 4;
    svg('text', { x: m.l - 6, y: Y(o) + 4, 'text-anchor': 'end' }, s).textContent = `${num(o / 1000, 0)} mil`;
  }
  const passoKm = (k1 - k0) > 30 ? 10 : 5;
  for (let k = Math.ceil(k0 / passoKm) * passoKm; k <= k1; k += passoKm) svg('text', { x: X(k), y: H - 10, 'text-anchor': 'middle' }, s).textContent = `km ${num(k, 0)}`;
  // linha de compensação (O = 0)
  svg('line', { x1: m.l, x2: W - m.r, y1: Y(0), y2: Y(0), stroke: '#12263f', 'stroke-width': 1.5, id: 'an-linha-compensacao' }, s);
  svg('text', { x: W - m.r - 4, y: Y(0) - 4, 'text-anchor': 'end', fill: '#12263f' }, s).textContent = 'linha de compensação (O = 0)';
  svg('polyline', { points: est.map(e => `${X(e.km).toFixed(1)},${Y(e.ordenada_m3).toFixed(1)}`).join(' '), fill: 'none', stroke: '#eb6834', 'stroke-width': 2, id: 'an-curva' }, s);
  (d.pontos_passagem_km || []).forEach(k => svg('circle', { cx: X(k), cy: Y(0), r: 2.5, fill: '#12263f', class: 'an-passagem' }, s));
  svg('text', { x: m.l, y: 11 }, s).textContent = 'Ordenada de Brückner (m³, corte homogeneizado − aterro acumulado)';
}

// ---------------------------------------------------------------- d) produtividade pela DMT
function terraHTML(s) {
  if (s.carregando) return '<p class="vazio">Calculando DMT e produção da frota por segmento…</p>';
  if (s.erro) return `<p class="erro">Produtividade pela DMT indisponível: ${esc(s.erro)}</p>`;
  const t = s.dados;
  const segs = t.segmentos || [];
  const ef = t.efeito_no_termino || {};
  return `<p class="erro" style="background:#fff8e1;border-color:#ffd24a;color:#4a3900">${esc(t.aviso || '')}</p>
    <div style="max-height:340px;overflow:auto"><table class="tab" id="an-terra-tab"><thead><tr><th>Segmento</th><th>Status</th>
      <th class="num">DMT (m)</th><th>Limitante</th><th class="num">Geométrica</th><th class="num">Planejada</th><th class="num">Medida</th>
      <th class="num">Geom./plan.</th><th class="num">Medida/geom.</th></tr></thead><tbody>
      ${segs.map(x => `<tr><td><span class="link-ativ" data-ir="${esc(x.atividade_id)}">${esc(x.segmento_id)}</span></td><td>${esc(x.status || '')}</td>
        <td class="num">${num(x.dmt_m, 0)}</td><td>${esc(x.limitante || '')}</td>
        <td class="num"><b>${num(x.produtividade_geometrica, 0)}</b></td><td class="num">${num(x.produtividade_planejada, 0)}</td>
        <td class="num" title="${esc(x.fonte_medida || '')}">${num(x.produtividade_medida, 0)}</td>
        <td class="num">${num(x.geometrica_sobre_planejada, 2)}</td><td class="num">${num(x.medida_sobre_geometrica, 2)}</td></tr>`).join('')}
    </tbody></table></div>
    <p style="font-size:12.5px;margin:8px 0" id="an-terra-efeito">Aplicando a produtividade geométrica nas ${num((t.ajustes_recomendados || []).length, 0)} frentes não concluídas:
      término ${dataBR(ef.termino_independente)} → <b>${dataBR(ef.termino_pela_geometria)}</b> (${dias(ef.delta_dias_corridos || 0)} dias corridos).
      DMT de equilíbrio ${num(t.dmt_equilibrio_m, 0)} m.</p>
    <div class="sim-botoes"><button type="button" class="primario" data-aplicar="terra" ${!(t.ajustes_recomendados || []).length || aplicando ? 'disabled' : ''}>Aplicar como simulação</button></div>
    ${msgs.terra ? `<p class="${msgs.terra.erro ? 'erro' : ''}" id="an-terra-msg">${esc(msgs.terra.texto)}</p>` : ''}
    <p style="font-size:11.5px;color:var(--texto-3);margin:4px 0 0">${esc(t.metodo || '')}</p>`;
}

// ---------------------------------------------------------------- e) exportar para BI
function biHTML(s) {
  if (s.carregando) return '<p class="vazio">Listando as tabelas…</p>';
  if (s.erro) return `<p class="erro">Exportação indisponível: ${esc(s.erro)}</p>`;
  const tabs = s.dados.tabelas || [];
  return `<p style="font-size:12.5px;margin:4px 0">Modelo estrela (dimensões + fatos) para Power BI / Excel. Todos os dados são FICTÍCIOS.</p>
    <p><a class="botao-link" id="an-bi-zip" href="${esc(api.urlExportarPacote())}" download>Baixar pacote completo (.zip)</a></p>
    <div class="gantt-barra">
      <label>GIS (GeoJSON, WGS84, georreferência FICTÍCIA) — camada <select id="an-gis-camada">${CAMADAS_GIS.map(k => `<option value="${esc(k)}">${esc(k)}</option>`).join('')}</select></label>
      <a class="botao-link" id="an-gis-link" href="${esc(api.urlGeojson('todas'))}" download>Baixar GeoJSON</a>
      <span style="font-size:12px;color:var(--texto-3)">Estado 4D na data de status, cenário independente. Para QGIS ou similar; não serve para locação.</span>
    </div>
    <table class="tab" id="an-bi-tab"><thead><tr><th>Tabela</th><th>Descrição</th><th class="num">Linhas</th><th>Colunas</th><th>CSV</th></tr></thead><tbody>
      ${tabs.map(x => `<tr><td><b>${esc(x.nome)}</b></td><td style="white-space:normal">${esc(x.descricao || '')}</td><td class="num">${num(x.linhas, 0)}</td>
        <td style="white-space:normal;font-size:12px">${(x.colunas || []).map(c => esc(c.nome)).join(', ')}</td>
        <td><a href="${esc(api.urlExportarCsv(x.nome))}" download data-csv="${esc(x.nome)}">${esc(x.nome)}.csv</a></td></tr>`).join('')}
    </tbody></table>`;
}

// ---------------------------------------------------------------- aplicar como simulação
async function aplicar(qual) {
  let ajustes = [];
  let alvo = 'recup';
  if (qual === 'recup-prod') ajustes = (sec.recup.dados?.ajustes_produtividade || []);
  else if (qual === 'recup-eq') ajustes = (sec.recup.dados?.ajustes_equipes || []);
  else if (qual === 'terra') { ajustes = (sec.terra.dados?.ajustes_recomendados || []); alvo = 'terra'; }
  else if (qual === 'acel') { ajustes = (sec.acel.dados?.ajustes_finais || []); alvo = 'acel'; }
  if (!ajustes.length) return;
  aplicando = true;
  msgs[alvo] = { texto: 'Aplicando os ajustes como simulação…' };
  renderAnalises();
  try {
    const r = await api.simular(ajustes.map(a => ({ ...a })));
    estado.simulacao = r;
    if (opcoes.aposSimulacao) await opcoes.aposSimulacao(true);
    const c = r.comparacao || {};
    msgs[alvo] = { texto: `Simulação aplicada (${ajustes.length} ajustes): término ${dataBR(c.termino_ref)} → ${dataBR(c.termino_alvo)} (${dias(c.delta_dias_corridos || 0)} dias corridos). Veja a aba Simulação.` };
  } catch (e) {
    msgs[alvo] = { erro: true, texto: `Simulação rejeitada: ${e.message || e}` };
  } finally {
    aplicando = false;
    renderAnalises();
  }
}

// ---------------------------------------------------------------- f) clima
function climaHTML(s) {
  if (s.carregando) return '<p class="vazio">Recalculando o cenário independente com calendários de chuva alternativos…</p>';
  if (s.erro) return `<p class="erro">Clima indisponível: ${esc(s.erro)}</p>`;
  const c = s.dados;
  const cen = c.cenarios || [];
  return `<p style="font-size:12.5px;margin:4px 0" id="an-cli-resumo">Término independente: <b>${dataBR(c.termino_independente)}</b>.
      Calendários sensíveis à chuva (marca <span class="mono">sensivel_chuva</span>): <b>${(c.calendarios_sensiveis || []).map(esc).join(', ') || 'nenhum'}</b>.
      ${num(cen.length, 0)} cenários.</p>
    <div class="kpis" id="an-cli-cards">${cen.map(x => {
      const d = x.delta_dias_corridos || 0;
      return `<div class="kpi" data-clima="${esc(x.tipo || '')}"><div class="rot">${esc(x.cenario)}</div><div class="val">${dataBR(x.termino)}</div>
        <span class="det ${d > 0 ? 'pior' : d < 0 ? 'melhor' : ''}">${dias(d)} dias corridos (${dias(x.delta_dias_uteis_obra || 0)} úteis da obra)</span>
        <div style="font-size:12px;color:var(--texto-2);margin-top:4px">${(x.calendarios || []).map(k => `${esc(k.calendario)}: +${num(k.dias_perdidos_acrescentados, 0)} / −${num(k.dias_devolvidos, 0)} dias`).join('<br>')}<br>
          ${num((x.criticas_em_calendario_sensivel || []).length, 0)} de ${num(x.n_criticas, 0)} críticas em calendário sensível</div></div>`;
    }).join('')}</div>
    <ul style="font-size:12.5px;line-height:1.5">${cen.map(x => `<li>${esc(x.explicacao || '')}</li>`).join('')}</ul>
    <p style="font-size:11.5px;color:var(--texto-3);margin:4px 0 0">${esc(c.metodo || '')}. Critério: ${esc(c.criterio_sensivel || '')}.
      Limites: ${(c.limites || []).map(esc).join(' · ')}</p>`;
}
// ---------------------------------------------------------------- g) tendência dos marcos (MTA)
const CAMADAS_GIS = ['todas', 'eixo', 'lotes', 'segmentos', 'faixa', 'atividades', 'marcos', 'restricoes', 'conflitos', 'estacas'];

function tendenciaHTML(s, marco) {
  if (s.carregando) return '<p class="vazio">Recalculando a previsão de cada marco em cada data de status passada…</p>';
  if (s.erro) return `<p class="erro">Tendência indisponível: ${esc(s.erro)}</p>`;
  const t = s.dados;
  const ms = t.marcos || [];
  const m = ms.find(x => x.id === marco) || ms[ms.length - 1];
  if (!m) return '<p class="vazio">Sem marcos.</p>';
  const inc = m.inclinacao_dias_por_semana || {};
  return `<p class="erro" style="background:#fff8e1;border-color:#ffd24a;color:#4a3900;margin:4px 0">Série SINTÉTICA: cada ponto recalcula o marco
      com os dados fictícios cortados naquela data de status (não são previsões registradas no passado).</p>
    <div class="gantt-barra"><label>Marco <select id="an-tend-marco">${ms.map(x => `<option value="${esc(x.id)}" ${x.id === m.id ? 'selected' : ''}>${esc(x.id)} — ${esc(x.nome || '')}</option>`).join('')}</select></label></div>
    <div id="an-tend-graf" style="max-width:1000px"></div>
    <p style="font-size:12.5px;margin:4px 0" id="an-tend-resumo">${num((m.serie || []).length, 0)} datas de status (a cada ${num(t.passo_dias, 0)} dias).
      Inclinação: construtora <b>${num(inc.construtora, 2)}</b> e independente <b>${num(inc.independente, 2)}</b> dias por semana
      (0 = previsão estável; 7 = o marco anda uma semana a cada semana).
      ${m.divergencia_desde ? `Divergência acima de ${num(t.limiar_divergencia_dias, 0)} dias desde <b>${dataBR(m.divergencia_desde)}</b>.` : 'Sem divergência acima do limiar.'}</p>
    <p style="font-size:11.5px;color:var(--texto-3);margin:0">${Object.entries(t.regras || {}).map(([k, r]) => `<b>${esc(k)}</b>: ${esc(r)}`).join(' · ')}</p>`;
}

/** MTA clássico: x = data de status, y = término previsto; diagonal y = x (marco atingido); divergência marcada. */
function graficoTendencia(el, t, marco) {
  const m = (t.marcos || []).find(x => x.id === marco) || (t.marcos || [])[t.marcos.length - 1];
  const serie = ((m && m.serie) || []).filter(p => diaDe(p.data_status) !== null);
  if (!el || serie.length < 2) return;
  const xs = serie.map(p => diaDe(p.data_status));
  const ys = serie.flatMap(p => [diaDe(p.termino_construtora), diaDe(p.termino_independente)]).filter(v => v !== null);
  const W = 1000, H = 300, mg = { l: 80, r: 16, t: 14, b: 30 };
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys, x1) - 10, y1 = Math.max(...ys) + 10;
  const X = (d) => mg.l + (d - x0) / ((x1 - x0) || 1) * (W - mg.l - mg.r);
  const Y = (d) => H - mg.b - (d - y0) / ((y1 - y0) || 1) * (H - mg.t - mg.b);
  const ser = [['termino_construtora', 'Construtora', '#eb6834'], ['termino_independente', 'Independente', '#1baf7a']];
  el.innerHTML = `<div class="legenda-graf">${ser.map(([, r, c]) => `<span><i style="background:${esc(c)}"></i>${esc(r)}</span>`).join('')}
    <span><svg width="22" height="8"><line x1="0" y1="4" x2="22" y2="4" stroke="#9aa3ad" stroke-dasharray="4 3"/></svg>Data de status = término (marco atingido)</span></div>`;
  const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'graf', id: 'an-tend-svg', role: 'img', 'aria-label': 'Tendência do marco por data de status' }, el);
  for (let i = 0; i <= 4; i++) {
    const d = Math.round(y0 + (y1 - y0) * i / 4);
    svg('line', { x1: mg.l, x2: W - mg.r, y1: Y(d), y2: Y(d), stroke: '#e6e8e3' }, s);
    svg('text', { x: mg.l - 6, y: Y(d) + 4, 'text-anchor': 'end' }, s).textContent = dataBR(isoDe(d));
  }
  let ultimo = -1;
  xs.forEach((d) => { const mes = new Date(d * 86400000).getUTCMonth(); if (mes !== ultimo && mes % 2 === 0) svg('text', { x: X(d), y: H - 10, 'text-anchor': 'middle' }, s).textContent = mesCurto(d); ultimo = mes; });
  // diagonal y = x (só onde cabe no eixo)
  const da = Math.max(x0, y0), db = Math.min(x1, y1);
  if (db > da) svg('line', { x1: X(da), y1: Y(da), x2: X(db), y2: Y(db), stroke: '#9aa3ad', 'stroke-dasharray': '4 3' }, s);
  if (m.divergencia_desde && diaDe(m.divergencia_desde) !== null) {
    const xd = X(diaDe(m.divergencia_desde));
    svg('line', { x1: xd, x2: xd, y1: mg.t, y2: H - mg.b, stroke: '#d62d2d', 'stroke-dasharray': '3 2', id: 'an-tend-div' }, s);
    svg('text', { x: xd + 4, y: mg.t + 10, fill: '#d62d2d' }, s).textContent = `divergência desde ${dataBR(m.divergencia_desde)}`;
  }
  for (const [k, , cor] of ser) {
    const v = serie.map((p, i) => [X(xs[i]), diaDe(p[k])]).filter(([, d]) => d !== null);
    svg('polyline', { points: v.map(([x, d]) => `${x.toFixed(1)},${Y(d).toFixed(1)}`).join(' '), fill: 'none', stroke: cor, 'stroke-width': 2, class: 'an-tend-linha' }, s);
  }
  serie.forEach((p, i) => {
    const r = svg('rect', { x: X(xs[i]) - 6, y: mg.t, width: 12, height: H - mg.t - mg.b, fill: 'transparent', class: 'an-tend-ponto' }, s);
    r.addEventListener('mousemove', (e) => mostrarTooltip(`<b>Data de status ${dataBR(p.data_status)}</b><br>
      Construtora: ${dataBR(p.termino_construtora)} · Independente: ${dataBR(p.termino_independente)}`, e));
    r.addEventListener('mouseleave', esconderTooltip);
  });
}
// ---------------------------------------------------------------- h) curva S física / financeira
const SERIES_CS = [['planejado', 'Planejado (linha de base)', '#2a78d6', '6 4'], ['previsto_construtora', 'Previsto — construtora', '#eb6834', null],
  ['previsto_independente', 'Previsto — independente', '#1baf7a', null], ['realizado', 'Realizado', '#12263f', null]];

function curvaSHTML(s) {
  if (s.carregando) return '<p class="vazio">Montando a curva S…</p>';
  if (s.erro) return `<p class="erro">Curva S indisponível: ${esc(s.erro)}</p>`;
  const c = s.dados;
  const f = c.fechamento || {};
  return `<p style="font-size:12.5px;margin:4px 0" id="an-cs-resumo">Base <b>${esc(c.base)}</b>${c.lote ? ` · lote ${esc(c.lote)}` : ''} ·
      realizado na data de status (${dataBR(c.data_status)}): <b>${num(c.percentual_realizado_na_data_status, 1)}%</b>
      (${num(c.realizado_na_data_status, 0)} de ${num(c.total, 0)}; ${esc(c.unidade || '')}). Fechamento em 100%: linha de base ${dataBR(f.linha_base)},
      construtora ${dataBR(f.construtora)}, independente ${dataBR(f.independente)}.</p>
    ${c.aviso ? `<p class="erro" style="background:#fff8e1;border-color:#ffd24a;color:#4a3900;margin:4px 0">${esc(c.aviso)}</p>` : ''}
    <div id="an-cs-graf" style="max-width:1000px"></div>
    <p style="font-size:11.5px;color:var(--texto-3);margin:4px 0 0">${esc(c.convencao || '')}. ${Object.entries(c.regras || {}).map(([k, r]) => `<b>${esc(k)}</b>: ${esc(r)}`).join(' · ')}</p>`;
}

function graficoCurvaS(el, c) {
  const pts = (c.pontos || []).filter(p => diaDe(p.data) !== null);
  if (!el || pts.length < 2) return;
  const xs = pts.map(p => diaDe(p.data));
  const W = 1000, H = 300, m = { l: 46, r: 14, t: 14, b: 30 };
  const X = (d) => m.l + (d - xs[0]) / ((xs[xs.length - 1] - xs[0]) || 1) * (W - m.l - m.r);
  const Y = (v) => H - m.b - v / 100 * (H - m.t - m.b);
  el.innerHTML = `<div class="legenda-graf">${SERIES_CS.map(([, r, cor, tr]) => `<span><svg width="22" height="8"><line x1="0" y1="4" x2="22" y2="4" stroke="${esc(cor)}" stroke-width="${cor === '#12263f' ? 3 : 2}" ${tr ? `stroke-dasharray="${esc(tr)}"` : ''}/></svg>${esc(r)}</span>`).join('')}
    <span><i style="background:#d62d2d;width:2px;height:12px"></i>Data de status</span></div>`;
  const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'graf', id: 'an-cs-svg', role: 'img', 'aria-label': 'Curva S: avanço acumulado por data' }, el);
  for (let v = 0; v <= 100; v += 20) {
    svg('line', { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), stroke: '#e6e8e3' }, s);
    svg('text', { x: m.l - 6, y: Y(v) + 4, 'text-anchor': 'end' }, s).textContent = `${v}%`;
  }
  let ult = -1;
  xs.forEach(d => { const mes = new Date(d * 86400000).getUTCMonth(); if (mes !== ult && mes % 3 === 0) svg('text', { x: X(d), y: H - 10, 'text-anchor': 'middle' }, s).textContent = mesCurto(d); ult = mes; });
  for (const [k, , cor, tr] of SERIES_CS) {
    const v = pts.map((p, i) => [X(xs[i]), p[k]]).filter(([, val]) => typeof val === 'number' && Number.isFinite(val));
    svg('polyline', { points: v.map(([x, val]) => `${x.toFixed(1)},${Y(val).toFixed(1)}`).join(' '), fill: 'none', stroke: cor,
      'stroke-width': cor === '#12263f' ? 3 : 2, 'stroke-dasharray': tr, class: 'an-cs-linha', 'data-serie': k }, s);
  }
  const ds = diaDe(c.data_status);
  if (ds !== null) svg('line', { x1: X(ds), x2: X(ds), y1: m.t, y2: H - m.b, stroke: '#d62d2d', 'stroke-width': 1.5 }, s);
  pts.forEach((p, i) => {
    const r = svg('rect', { x: X(xs[i]) - 5, y: m.t, width: 10, height: H - m.t - m.b, fill: 'transparent', class: 'an-cs-ponto' }, s);
    r.addEventListener('mousemove', (e) => mostrarTooltip(`<b>${dataBR(p.data)}</b><br>${SERIES_CS.map(([k, rot]) => `${esc(rot)}: ${typeof p[k] === 'number' ? `${num(p[k], 1)}%` : '—'}`).join('<br>')}`, e));
    r.addEventListener('mouseleave', esconderTooltip);
  });
}

// ---------------------------------------------------------------- i) backtest
const REF_BK = { realidade_simulada: 'realidade simulada do gerador', final_independente: 'término independente na data de status atual' };

function backtestHTML(s, marco, ref) {
  if (s.carregando) return '<p class="vazio">Recalculando as duas previsões em cada data de status passada…</p>';
  if (s.erro) return `<p class="erro">Backtest indisponível: ${esc(s.erro)}</p>`;
  const b = s.dados;
  const ms = b.marcos || [];
  const m = ms.find(x => x.id === marco) || ms[ms.length - 1];
  if (!m) return '<p class="vazio">Sem marcos.</p>';
  const r = (m.por_referencia || {})[ref] || Object.values(m.por_referencia || {})[0] || {};
  const mae = r.mae_dias || {};
  const fr = r.por_fracao_concluida || {};
  const circ = b.circularidade || {};
  return `<p class="erro" style="background:#fff8e1;border-color:#ffd24a;color:#4a3900;margin:4px 0"><b>Backtest SINTÉTICO.</b> A “realidade” é a do gerador
      de dados fictícios, não uma obra real. <b>Circularidade:</b> a previsão independente usa os mesmos boletins que formam a referência; quanto mais perto
      da data de status, maior a sobreposição (${num((circ.sobreposicao_boletins || [])[0] * 100, 1)}% no início → ${num((circ.sobreposicao_boletins || []).slice(-1)[0] * 100, 0)}% hoje),
      e o erro da independente tende a zero por construção. ${esc(circ.nota || '')}</p>
    <div class="gantt-barra">
      <label>Marco <select id="an-bk-marco">${ms.map(x => `<option value="${esc(x.id)}" ${x.id === m.id ? 'selected' : ''}>${esc(x.id)} — ${esc(x.nome || '')}</option>`).join('')}</select></label>
      <label>Referência <select id="an-bk-ref">${Object.keys(m.por_referencia || {}).map(k => `<option value="${esc(k)}" ${k === ref ? 'selected' : ''}>${esc(REF_BK[k] || k)}</option>`).join('')}</select></label>
    </div>
    <div class="kpis" id="an-bk-kpis">
      <div class="kpi"><div class="rot">Erro médio absoluto — construtora</div><div class="val">${num(mae.construtora, 1)} d</div></div>
      <div class="kpi"><div class="rot">Erro médio absoluto — independente</div><div class="val">${num(mae.independente, 1)} d</div></div>
      <div class="kpi"><div class="rot">Referência (término)</div><div class="val">${dataBR(r.referencia)}</div><span class="det">${esc((b.referencias || {})[ref] || '')}</span></div>
      <div class="kpi"><div class="rot">Independente estritamente melhor</div><div class="val">${num(r.datas_independente_estritamente_melhor, 0)}</div>
        <span class="det">de ${num((b.datas_de_status || []).length, 0)} datas; melhor desde ${dataBR(r.independente_melhor_desde)}</span></div>
    </div>
    <div id="an-bk-graf" style="max-width:1000px"></div>
    <table class="tab" id="an-bk-fracao" style="max-width:700px"><thead><tr><th>Obra concluída</th><th>Data de status</th><th class="num">Erro construtora (d)</th><th class="num">Erro independente (d)</th></tr></thead><tbody>
      ${Object.entries(fr).map(([k, x]) => `<tr><td>${esc(k)}</td><td>${x ? dataBR(x.data_status) : '—'}</td><td class="num">${x ? num(x.construtora, 0) : '—'}</td><td class="num">${x ? num(x.independente, 0) : '—'}</td></tr>`).join('')}
    </tbody></table>
    <p style="font-size:11.5px;color:var(--texto-3);margin:4px 0 0">Erro = previsão − referência, em dias corridos (negativo = previu cedo demais). Diferença entre as duas referências:
      ${Object.entries(circ.diferenca_referencias_dias || {}).map(([k, d]) => `${esc(k)} ${num(d, 0)} d`).join(' · ')}.</p>`;
}

function graficoBacktest(el, b, marco, ref) {
  const m = (b.marcos || []).find(x => x.id === marco) || (b.marcos || [])[b.marcos.length - 1];
  const r = m && ((m.por_referencia || {})[ref] || Object.values(m.por_referencia || {})[0]);
  const datas = b.datas_de_status || [];
  if (!el || !r || !r.erro_dias || datas.length < 2) return;
  const xs = datas.map(diaDe);
  const ser = [['construtora', 'Erro da construtora', '#eb6834'], ['independente', 'Erro da independente', '#1baf7a']];
  const vals = ser.flatMap(([k]) => (r.erro_dias[k] || []).filter(v => typeof v === 'number'));
  const lim = Math.max(10, ...vals.map(Math.abs)) * 1.1;
  const W = 1000, H = 260, mg = { l: 50, r: 14, t: 14, b: 30 };
  const X = (d) => mg.l + (d - xs[0]) / ((xs[xs.length - 1] - xs[0]) || 1) * (W - mg.l - mg.r);
  const Y = (v) => mg.t + (lim - v) / (2 * lim) * (H - mg.t - mg.b);
  el.innerHTML = `<div class="legenda-graf">${ser.map(([, rot, cor]) => `<span><i style="background:${esc(cor)}"></i>${esc(rot)}</span>`).join('')}<span>0 = acertou a referência</span></div>`;
  const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'graf', id: 'an-bk-svg', role: 'img', 'aria-label': 'Erro das previsões por data de status' }, el);
  for (const v of [-lim, -lim / 2, 0, lim / 2, lim]) {
    svg('line', { x1: mg.l, x2: W - mg.r, y1: Y(v), y2: Y(v), stroke: v === 0 ? '#52514e' : '#e6e8e3', 'stroke-width': v === 0 ? 1.5 : 1 }, s);
    svg('text', { x: mg.l - 6, y: Y(v) + 4, 'text-anchor': 'end' }, s).textContent = `${num(v, 0)} d`;
  }
  let ult = -1;
  xs.forEach(d => { const mes = new Date(d * 86400000).getUTCMonth(); if (mes !== ult && mes % 2 === 0) svg('text', { x: X(d), y: H - 10, 'text-anchor': 'middle' }, s).textContent = mesCurto(d); ult = mes; });
  for (const [k, , cor] of ser) {
    const v = (r.erro_dias[k] || []).map((e, i) => [X(xs[i]), e]).filter(([, e]) => typeof e === 'number');
    svg('polyline', { points: v.map(([x, e]) => `${x.toFixed(1)},${Y(e).toFixed(1)}`).join(' '), fill: 'none', stroke: cor, 'stroke-width': 2, class: 'an-bk-linha', 'data-serie': k }, s);
  }
}

// ---------------------------------------------------------------- j) aceleração (término × custo)
function aceleracaoHTML(s) {
  if (s.carregando) return '<p class="vazio">Acrescentando equipes na frente determinante mais barata, passo a passo…</p>';
  if (s.erro) return `<p class="erro">Aceleração indisponível: ${esc(s.erro)}</p>`;
  const a = s.dados;
  const curva = a.curva || [];
  return `<div style="display:flex;gap:26px;flex-wrap:wrap;align-items:flex-end" id="an-ac-resumo">
      <div><div class="rot-p">Prazo</div><b>${dataBR(a.prazo)}</b></div>
      <div><div class="rot-p">Término inicial</div><b>${dataBR(a.termino_inicial)}</b></div>
      <div><div class="rot-p">Término alcançado</div><b id="an-ac-alcancado">${dataBR(a.termino_alcancado)}</b></div>
      <div><div class="rot-p">Custo adicional (R$ fictícios)</div><b id="an-ac-custo">${num(a.custo_adicional_total, 0)}</b></div>
      <div>${a.cumpre_prazo ? '<span class="pill ok">cumpre o prazo</span>' : '<span class="pill crit">não cumpre</span>'}</div>
    </div>
    ${a.motivo ? `<p style="font-size:12.5px">${esc(a.motivo)}</p>` : ''}
    ${a.aviso ? `<p class="erro" style="background:#fff8e1;border-color:#ffd24a;color:#4a3900;margin:6px 0">${esc(a.aviso)}</p>` : ''}
    <div id="an-ac-graf" style="max-width:1000px"></div>
    <div style="max-height:260px;overflow:auto"><table class="tab" id="an-ac-tab"><thead><tr><th class="num">Passo</th><th>Término</th><th class="num">Custo acumulado</th><th>Equipes acrescentadas</th></tr></thead><tbody>
      ${curva.map(x => `<tr><td class="num">${num(x.passo, 0)}</td><td>${dataBR(x.termino)}</td><td class="num">${num(x.custo_acumulado, 0)}</td>
        <td style="white-space:normal;font-size:12px">${(x.ajustes || []).map(j => `<span class="link-ativ" data-ir="${esc(j.id)}">${esc(j.id)}</span> ${num(j.equipes_de, 0)}→${num(j.equipes_para, 0)} equipes (${num(j.duracao_de, 0)}→${num(j.duracao_para, 0)} d.u.; R$ ${num(j.custo, 0)})`).join('<br>') || '—'}${x.composto ? ' <small>(passo composto)</small>' : ''}</td></tr>`).join('')}
    </tbody></table></div>
    <div class="sim-botoes"><button type="button" class="primario" data-aplicar="acel" ${!(a.ajustes_finais || []).length || aplicando ? 'disabled' : ''}>Aplicar como simulação (${num((a.ajustes_finais || []).length, 0)} ajustes)</button></div>
    ${msgs.acel ? `<p class="${msgs.acel.erro ? 'erro' : ''}" id="an-ac-msg">${esc(msgs.acel.texto)}</p>` : ''}
    <p style="font-size:11.5px;color:var(--texto-3);margin:4px 0 0">${esc(a.metodo || '')}. Verificação da API: ${esc((a.verificacao || {}).como || '')}
      → ${dataBR((a.verificacao || {}).termino)} ${(a.verificacao || {}).confere ? '(confere)' : '(NÃO confere)'}.</p>`;
}

/** Curva tempo × custo: x = custo adicional acumulado, y = término; linha horizontal no prazo. */
function graficoAceleracao(el, a) {
  const c = (a.curva || []).filter(x => diaDe(x.termino) !== null);
  if (!el || c.length < 2) return;
  const ys = c.map(x => diaDe(x.termino)).concat(diaDe(a.prazo) !== null ? [diaDe(a.prazo)] : []);
  const cx = c.map(x => x.custo_acumulado || 0);
  const W = 1000, H = 260, m = { l: 80, r: 20, t: 14, b: 34 };
  const y0 = Math.min(...ys) - 5, y1 = Math.max(...ys) + 5, x1 = Math.max(...cx, 1) * 1.05;
  const X = (v) => m.l + v / x1 * (W - m.l - m.r);
  const Y = (d) => m.t + (y1 - d) / ((y1 - y0) || 1) * (H - m.t - m.b);
  const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'graf', id: 'an-ac-svg', role: 'img', 'aria-label': 'Término em função do custo adicional' }, el);
  for (let i = 0; i <= 4; i++) {
    const d = Math.round(y0 + (y1 - y0) * i / 4);
    svg('line', { x1: m.l, x2: W - m.r, y1: Y(d), y2: Y(d), stroke: '#e6e8e3' }, s);
    svg('text', { x: m.l - 6, y: Y(d) + 4, 'text-anchor': 'end' }, s).textContent = dataBR(isoDe(d));
    const v = x1 * i / 4;
    svg('text', { x: X(v), y: H - 12, 'text-anchor': 'middle' }, s).textContent = `R$ ${num(v / 1e6, 1)} mi`;
  }
  if (diaDe(a.prazo) !== null) {
    svg('line', { x1: m.l, x2: W - m.r, y1: Y(diaDe(a.prazo)), y2: Y(diaDe(a.prazo)), stroke: '#d62d2d', 'stroke-dasharray': '5 3', id: 'an-ac-prazo-linha' }, s);
    svg('text', { x: W - m.r - 4, y: Y(diaDe(a.prazo)) - 4, 'text-anchor': 'end', fill: '#d62d2d' }, s).textContent = `prazo ${dataBR(a.prazo)}`;
  }
  // degraus: cada passo mantém o término até o próximo custo
  const d = c.map((x, i) => `${i ? 'H' : 'M'}${X(cx[i]).toFixed(1)} ${i ? '' : Y(diaDe(x.termino)).toFixed(1)}${i ? ` V${Y(diaDe(x.termino)).toFixed(1)}` : ''}`).join(' ');
  svg('path', { d, fill: 'none', stroke: '#6250d6', 'stroke-width': 2, id: 'an-ac-curva' }, s);
  c.forEach((x, i) => {
    const p = svg('circle', { cx: X(cx[i]), cy: Y(diaDe(x.termino)), r: 5, fill: '#6250d6', class: 'an-ac-ponto' }, s);
    p.addEventListener('mousemove', (e) => mostrarTooltip(`<b>Passo ${num(x.passo, 0)}</b>: término ${dataBR(x.termino)}<br>custo acumulado R$ ${num(x.custo_acumulado, 0)}<br>
      ${(x.ajustes || []).map(j => `${esc(j.id)}: ${num(j.equipes_de, 0)}→${num(j.equipes_para, 0)} equipes`).join('<br>')}`, e));
    p.addEventListener('mouseleave', esconderTooltip);
  });
}
// ---------------------------------------------------------------- i2) backtest: "Por que errou?" (/api/backtest/atribuicao)
/** Data padrão: a de maior |erro| da previsão independente contra a realidade simulada, no marco escolhido. */
function dataPadraoBk(b, marco) {
  if (!b || !Array.isArray(b.datas_de_status)) return null;
  const m = (b.marcos || []).find(x => x.id === marco) || (b.marcos || [])[b.marcos.length - 1];
  const er = m && m.por_referencia && m.por_referencia.realidade_simulada && m.por_referencia.realidade_simulada.erro_dias
    && m.por_referencia.realidade_simulada.erro_dias.independente;
  if (!Array.isArray(er)) return b.datas_de_status[0] || null;
  let melhor = 0;
  er.forEach((e, i) => { if (typeof e === 'number' && Math.abs(e) > Math.abs(er[melhor] || 0)) melhor = i; });
  return b.datas_de_status[melhor] || null;
}

function porQueErrouHTML(s9, s, data) {
  if (!s9.dados) return '';
  const datas = s9.dados.datas_de_status || [];
  const cab = `<h4 style="margin:14px 0 4px">Por que errou?</h4>
    <div class="gantt-barra"><label>Data de status <select id="an-bk-data">${datas.map(d => `<option value="${esc(d)}" ${d === data ? 'selected' : ''}>${dataBR(d)}</option>`).join('')}</select></label>
      <span style="font-size:12px;color:var(--texto-3)">Ou clique num ponto do gráfico. Padrão: a data de maior erro da previsão independente.</span></div>`;
  if (!data) return cab;
  if (s.carregando) return `${cab}<p class="vazio">Refazendo a previsão de ${dataBR(data)} com a produtividade verdadeira de cada frente, uma de cada vez…</p>`;
  if (s.erro) return `${cab}<p class="erro">Atribuição indisponível: ${esc(s.erro)}</p>`;
  const a = s.dados;
  if (!a) return cab;
  const fr = [...(a.frentes || [])].sort((x, y) => (y.reducao_dias || 0) - (x.reducao_dias || 0));
  const tj = a.todas_as_frentes_juntas || {};
  return `${cab}${seloSimulacao(a)}
    <p class="erro" style="background:#fff8e1;border-color:#ffd24a;color:#4a3900;margin:4px 0">${esc((a.regras || {}).aviso || 'Realidade SINTÉTICA.')}</p>
    <div style="display:flex;gap:26px;flex-wrap:wrap;align-items:flex-end" id="an-atr-resumo">
      <div><div class="rot-p">Previsão em ${dataBR(a.data)}</div><b>${dataBR(a.termino_previsto)}</b></div>
      <div><div class="rot-p">Realidade simulada</div><b>${dataBR(a.termino_realidade_simulada)}</b></div>
      <div><div class="rot-p">Erro</div><b id="an-atr-erro">${num(a.erro_dias, 0)} d</b></div>
      <div><div class="rot-p">Todas as frentes corrigidas juntas</div><b id="an-atr-todas">${num(tj.erro_dias, 0)} d</b></div>
      <div><div class="rot-p">Resíduo de interação</div><b id="an-atr-residuo">${num(a.residuo_interacao, 0)} d</b></div>
    </div>
    ${fr.length ? `<table class="tab" id="an-atr-tab" style="margin-top:6px"><thead><tr><th>Frente</th><th class="num">Fator verdadeiro</th>
      <th class="num">Erro com a frente corrigida</th><th class="num">Redução do erro</th><th>Na cadeia</th></tr></thead><tbody>
      ${fr.map(x => `<tr data-frente="${esc(x.lote_id)}/${esc(x.servico_id)}"><td><b>${esc(x.lote_id)} / ${esc(x.servico_id)}</b></td><td class="num">${num(x.fator_verdadeiro, 3)}</td>
        <td class="num">${num(a.erro_dias, 0)} → <b>${num(x.erro_com_a_frente_corrigida, 0)}</b> d</td><td class="num">${num(x.reducao_dias, 0)} d</td>
        <td style="font-size:12px">${(x.na_cadeia || []).map(esc).join(', ')}</td></tr>`).join('')}
    </tbody></table>` : '<p style="color:var(--texto-2)">Nenhuma frente aberta na cadeia do marco nessa data.</p>'}
    <p style="font-size:11.5px;color:var(--texto-3);margin:4px 0 0">${Object.entries(a.regras || {}).filter(([k]) => k !== 'aviso').map(([k, r]) => `<b>${esc(k)}</b>: ${esc(r)}`).join(' · ')}</p>`;
}

/** Clique num ponto do gráfico do backtest escolhe a data do "Por que errou?". */
function ligarCliqueBacktest(b) {
  const s = raiz.querySelector('#an-bk-svg');
  if (!s || !b) return;
  const datas = b.datas_de_status || [];
  const xs = datas.map(diaDe);
  const vb = s.viewBox.baseVal;
  const mg = { l: 50, r: 14 };
  const X = (d) => mg.l + (d - xs[0]) / ((xs[xs.length - 1] - xs[0]) || 1) * (vb.width - mg.l - mg.r);
  datas.forEach((d, i) => {
    const r = svg('rect', { x: X(xs[i]) - 5, y: 0, width: 10, height: vb.height, fill: 'transparent', class: 'an-bk-alvo', 'data-data': d, style: 'cursor:pointer' }, s);
    r.addEventListener('click', () => {
      const sel = raiz.querySelector('#an-bk-data');
      if (sel) { sel.value = d; renderAnalises(); }
    });
  });
}