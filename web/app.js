// Orquestração da interface INFRA 4D: carga, abas, filtros, seleção, timeline 4D.

import { api, definirObra, obraSelecionada } from './api.js';
import { definirServicos } from './cores.js';
import { planoDeEstilos, temGeometriaPlano } from './secoes.js';
import { estado, indexarProjeto, recalcularIntervalo, ouvir, emitir, passaFiltro, avisoFiltros, selecionar, nomeServico } from './estado.js';
import { isoDe, diaDe, dataBR, debounce, esc, num, esconderTooltip } from './util.js';
import { iniciarGantt, renderGantt, legendaGantt, rolarGanttPara, iniciarTabela, renderTabela, rolarTabelaPara } from './gantt.js';
import { iniciarPainel, renderPainel, definirComparacaoConstrutora, definirPrevisao } from './painel.js';
import { iniciarDetalhes, renderDetalhes } from './detalhes.js';
import { iniciarSimulacao, renderSimulacao, prepararAtividade } from './simulacao.js';
import { renderApresentacao } from './apresentacao.js';
import { iniciarBalanco, renderBalanco, invalidarConflitos } from './linhabalanco.js';
import { iniciarRecursos, atualizarRecursos, invalidarRecursos } from './recursos.js';
import { iniciarCronoImport, renderCronoImport } from './cronoimport.js';
import { preCarregarEstacas } from './estacas.js';
import { iniciarFiscalizacao, renderFiscalizacao } from './fiscalizacao.js';
import { iniciarAnalises, renderAnalises } from './analises.js';
import { iniciarTour, abrirTour, proximo as tourProximo, anterior as tourAnterior, sair as tourSair, estadoTour } from './tour.js';
import { iniciarFederacao } from './federacao.js';

const $ = (s) => document.querySelector(s);
const CENARIOS = ['linha_base', 'construtora', 'independente', 'simulado'];
// Preferência visual simples; não guarda obra, dados ou simulação.
try {
  const preferida = sessionStorage.getItem('infra4d.experiencia');
  if (['analise', 'tecnico', 'apresentacao'].includes(preferida)) $('#v-experiencia').value = preferida;
} catch { /* armazenamento indisponível: permanece o padrão análise */ }

let viewer = null;          // Viewer3D (carregado sob demanda)
let viewerErro = null;
let saude = null;
let diaTimeline = null;     // dia (número) mostrado no 4D
let seq4d = 0;
let tocando = null;

// ---------------- erros globais ----------------
function erroGlobal(msg) {
  $('#erro-global-texto').textContent = msg;
  $('#erro-global').hidden = false;
}
function limparErroGlobal() { $('#erro-global').hidden = true; }
$('#erro-global-repetir').addEventListener('click', () => { limparErroGlobal(); carregar(); });

// Tratador global: exceção não capturada (inclusive dentro de promessas que redesenham telas) vira
// aviso visível na faixa #erro-global (textContent), em vez de deixar a aba vazia ou como estava.
function textoDoErro(x) {
  if (!x) return 'erro desconhecido';
  if (typeof x === 'string') return x;
  return x.message || String(x);
}
window.addEventListener('unhandledrejection', (e) => {
  erroGlobal(`Erro inesperado na interface: ${textoDoErro(e.reason)}`);
});
window.addEventListener('error', (e) => {
  erroGlobal(`Erro inesperado na interface: ${textoDoErro(e.error || e.message)}`);
});

// ---------------- abas ----------------
// Hash da URL: #<aba>?obra=<id>  (ex.: #painel?obra=rodovia)
function lerHash() {
  const h = location.hash.slice(1);
  const [aba, qs] = h.split('?');
  const q = new URLSearchParams(qs || '');
  return { aba: aba || null, obra: q.get('obra'), tour: q.get('tour') === '1' };
}
const HASH_INICIAL = lerHash(); // lido antes de qualquer escrita (a obra ainda não foi validada)
function escreverHash() {
  const obra = obraSelecionada() || HASH_INICIAL.obra;
  const novo = `#${estado.aba}${obra ? `?obra=${encodeURIComponent(obra)}` : ''}`;
  if (location.hash !== novo) history.replaceState(null, '', novo);
}

function irPara(aba) {
  esconderTooltip();
  estado.aba = aba;
  escreverHash();
  document.querySelectorAll('.abas [data-aba]').forEach(b => {
    const ativa = b.dataset.aba === aba;
    b.classList.toggle('ativa', ativa);
    b.setAttribute('aria-selected', ativa);
  });
  document.querySelectorAll('.aba').forEach(s => { s.hidden = s.id !== `aba-${aba}`; });
  $('#filtros').hidden = aba === 'apresentacao';
  if (aba === 'modelo') garantirViewer().then(() => viewer && viewer.aoMostrar());
  if (aba === 'cronograma') {
    renderGantt();
    renderTabela();
    if (estado.selecionada) { rolarGanttPara(estado.selecionada); rolarTabelaPara(estado.selecionada); }
  }
  if (aba === 'simulacao') renderSimulacao();
  if (aba === 'balanco') renderBalanco();
  if (aba === 'recursos') atualizarRecursos();
  if (aba === 'cronoimport') renderCronoImport();
  if (aba === 'fiscalizacao') renderFiscalizacao();
  if (aba === 'analises') renderAnalises();
  emitir('aba', aba);
}
document.querySelectorAll('.abas [data-aba]').forEach(b => b.addEventListener('click', () => irPara(b.dataset.aba)));

// ---------------- filtros ----------------
function preencherFiltros() {
  const p = estado.projeto;
  const opt = (v, t) => `<option value="${esc(v)}">${esc(t)}</option>`;
  $('#f-lote').innerHTML = opt('', 'Todos') + p.lotes.map(l => opt(l.id, `${l.id} — ${l.nome}`)).join('');
  const disc = [...new Set(p.atividades.map(a => a.disciplina).filter(Boolean))];
  $('#f-disciplina').innerHTML = opt('', 'Todas') + disc.map(d => opt(d, d)).join('');
  const servs = [...new Set(p.atividades.map(a => a.servico_id).filter(Boolean))];
  $('#f-servico').innerHTML = opt('', 'Todos') + servs.map(s => opt(s, `${s} — ${nomeServico(s)}`)).join('');
  $('#ir-para-lotes').innerHTML = p.lotes.map(l => `<button type="button" data-ir-km="${esc(l.id)}">${esc(l.id)}</button>`).join('');
  $('#f-segmento').innerHTML = opt('', 'Todos') + (p.segmentos || []).map(s => opt(s.id, s.id + ' (km ' + num(s.km_ini, 1) + '–' + num(s.km_fim, 1) + ')')).join(''); // opt() escapa
}

function lerFiltros() {
  const loteAntes = estado.filtros.lote;
  estado.filtros = {
    lote: $('#f-lote').value,
    disciplina: $('#f-disciplina').value,
    servico: $('#f-servico').value,
    soCritico: $('#f-critico').checked,
    segmento: $('#f-segmento').value,
    kmIni: numeroOuNulo($('#f-km-ini').value),
    kmFim: numeroOuNulo($('#f-km-fim').value),
    // campo de data só vale com AAAA-MM-DD completo
    dataIni: diaDe($('#f-data-ini').value) !== null ? $('#f-data-ini').value : '',
    dataFim: diaDe($('#f-data-fim').value) !== null ? $('#f-data-fim').value : '',
  };
  emitir('filtros', { loteMudou: loteAntes !== estado.filtros.lote });
}
const numeroOuNulo = (v) => (v === '' || v === null || !Number.isFinite(Number(v)) ? null : Number(v));
['#f-lote', '#f-disciplina', '#f-servico', '#f-critico', '#f-segmento', '#f-km-ini', '#f-km-fim', '#f-data-ini', '#f-data-fim']
  .forEach(s => $(s).addEventListener('change', lerFiltros));
/** Volta todos os filtros ao padrão (cenário não muda). */
function limparFiltros() {
  $('#f-lote').value = ''; $('#f-disciplina').value = ''; $('#f-servico').value = ''; $('#f-critico').checked = false;
  $('#f-segmento').value = ''; $('#f-km-ini').value = ''; $('#f-km-fim').value = ''; $('#f-data-ini').value = ''; $('#f-data-fim').value = '';
  lerFiltros();
}
$('#f-limpar').addEventListener('click', limparFiltros);
$('#v-vazio-limpar').addEventListener('click', limparFiltros);
$('#f-cenario').addEventListener('change', () => definirCenario($('#f-cenario').value));

function definirCenario(c) {
  estado.cenarioAtivo = c;
  $('#f-cenario').value = c;
  emitir('cenario', c);
}

function resumoFiltros() {
  const vis = estado.projeto.atividades.filter(passaFiltro).length;
  const aviso = avisoFiltros();
  $('#f-resumo').innerHTML = `<span id="f-resumo-n">${num(vis, 0)}</span> de ${num(estado.projeto.atividades.length, 0)} atividades atendem aos filtros`
    + (aviso ? ` · <span class="filtro-aviso">${esc(aviso)}</span>` : '')
    + (vis === 0 ? ' · <span class="filtro-aviso" id="f-resumo-vazio">nenhuma: ajuste ou limpe os filtros</span>' : '');
  // aviso de vazio no 3D: nenhuma atividade COM GEOMETRIA passa
  const el = $('#v-vazio');
  if (el) el.hidden = !(viewer && estado.projeto.atividades.every(a => !viewer.temGeometria(a.id) || !passaFiltro(a)));
}

// ---------------- painel ----------------
async function recarregarPainel() {
  try {
    estado.painel = await api.painel(estado.filtros.lote || null);
    if (!estado.filtros.lote) estado.painelGeral = estado.painel;
    renderPainel();
    $('#aviso-sim').hidden = !estado.painel.simulacao_ativa;
  } catch (e) {
    renderPainel(e.message);
  }
}

// ---------------- 3D ----------------
async function garantirViewer() {
  if (viewer || viewerErro || !estado.projeto || !estado.cenarios[estado.cenarioAtivo] || diaTimeline === null) return;
  const el = $('#viewer');
  try {
    const mod = await import('./viewer3d.js');
    viewer = new mod.Viewer3D(el, estado.projeto, {
      aoSelecionar: (id) => selecionar(id, '3d'),
      vistaInicial: frenteCritica(),
      aoPassar: (ud) => {
        hoverPeca = ud ? `${ud.elementoId}${ud.globalId ? ` · GlobalId ${ud.globalId}` : ''} · ${rotuloEstado(ud.estado)}` : '';
        mostrarHover();
      },
      aoPassarPonto: (p) => { if (p) referenciaHover(p); else { hoverRef = ''; mostrarHover(); } },
      aoClicarPonto: (p) => mostrarReferencia(p),
    });
    viewer.setExagero(Number($('#v-exagero').value));
    const experienciaInicial = $('#v-experiencia').value;
    if (experienciaInicial !== 'analise') viewer.setModoVisual(experienciaInicial);
    if ($('#v-baixo-consumo').checked) viewer.setBaixoConsumo(true);
    $('#v-exagero').value = String(viewer.exagero);
    $('#v-exagero').disabled = experienciaInicial !== 'analise';
    $('#v-visual-aviso').hidden = experienciaInicial !== 'apresentacao';
    viewer.setModoCor($('#v-modo-cor').value);
    viewer.setFiltro(passaFiltro, $('#v-ocultar').checked);
    viewer.setSelecao(estado.selecionada);
    $('#legenda-3d').innerHTML = viewer.legenda();
    resumoFiltros();  // atualiza o aviso de vazio do 3D agora que há geometria
    $('#v-modo-cor').addEventListener('change', () => {
      viewer.setModoCor($('#v-modo-cor').value);
      $('#legenda-3d').innerHTML = viewer.legenda();
    });
    $('#v-exagero').addEventListener('change', () => viewer.setExagero(Number($('#v-exagero').value)));
    $('#v-ocultar').addEventListener('change', () => viewer.setFiltro(passaFiltro, $('#v-ocultar').checked));
    $('#v-enquadrar').addEventListener('click', () => viewer.enquadrarTudo());
    $('#v-geometria').addEventListener('change', () => trocarGeometria($('#v-geometria').value));
    $('#v-experiencia').addEventListener('change', () => {
      const modo = $('#v-experiencia').value;
      try { sessionStorage.setItem('infra4d.experiencia', modo); } catch { /* preferência opcional */ }
      viewer.setModoVisual(modo);
      $('#v-exagero').value = String(viewer.exagero);
      $('#v-exagero').disabled = modo !== 'analise' || viewer.modoGeo === 'ifc';
      $('#v-visual-aviso').hidden = modo !== 'apresentacao';
      $('#legenda-3d').innerHTML = viewer.legenda();
    });
    $('#v-oae').addEventListener('click', () => viewer.enquadrarOae());
    $('#v-superior').addEventListener('click', () => viewer.vistaSuperior());
    $('#v-corte').addEventListener('change', () => viewer.setCorte($('#v-corte').checked));
    $('#v-baixo-consumo').addEventListener('change', () => viewer.setBaixoConsumo($('#v-baixo-consumo').checked));
    iniciarFederacao($('#federacao'), { viewer: () => viewer, selecionar });
    $('#ir-para').addEventListener('click', (e) => {
      const b = e.target.closest('[data-ir-km]');
      if (!b) return;
      const lote = estado.projeto.lotes.find(l => l.id === b.dataset.irKm);
      const [a, c] = lote ? [lote.km_ini, lote.km_fim] : frenteCritica();
      viewer.enquadrarKm(a, c);
    });
    if (estado.selecionada) viewer.enquadrarAtividade(estado.selecionada);
    await buscarEstado4d();
  } catch (e) {
    viewerErro = e;
    el.innerHTML = `<p class="erro" style="margin:20px">Não foi possível iniciar o visualizador 3D (WebGL indisponível ou falha ao carregar three.js): ${esc(e.message)}</p>`;
    const { renderFallback2D } = await import('./fallback2d.js');
    renderFallback2D(el, estado.projeto, resultadoParaFallback(), id => selecionar(id, '2d'));
  }
}
function resultadoParaFallback() { return estado.cenarios[estado.cenarioAtivo]; }
/** Redesenha o conteúdo da aba visível (abas que só renderizam quando visíveis). */
function renderAbaAtual() {
  const a = estado.aba;
  if (a === 'balanco') renderBalanco();
  else if (a === 'recursos') atualizarRecursos();
  else if (a === 'cronoimport') renderCronoImport();
  else if (a === 'fiscalizacao') renderFiscalizacao();
  else if (a === 'analises') renderAnalises();
  else if (a === 'simulacao') renderSimulacao();
  else if (a === 'cronograma') { renderGantt(); renderTabela(); }
}

// ---------------- referência linear no 3D (km / estaca / lote) ----------------
let hoverPeca = '', hoverRef = '', seqRef = 0;
function mostrarHover() {
  $('#v-hover').textContent = [hoverPeca, hoverRef].filter(Boolean).join(' · ');
}
function textoRef(r) {
  const lado = r.afastamento_m != null ? ` · ${Math.round(r.afastamento_m)} m ${r.lado || ''}` : '';
  return `km ${String(r.km.toFixed(3)).replace('.', ',')} · estaca ${r.estaca}${lado}`;
}
const referenciaHover = debounce(async (p) => {
  const meu = ++seqRef;
  try {
    const r = await api.referenciaPonto(p.x.toFixed(1), p.y.toFixed(1));
    if (meu !== seqRef) return;
    hoverRef = textoRef(r);
  } catch { hoverRef = ''; }
  mostrarHover();
}, 250);

/** Clique fora das peças: km/estaca/lote/segmento e atividades daquele km, num quadro sobre o 3D. */
async function mostrarReferencia(p) {
  const box = $('#v-info');
  box.hidden = false;
  box.innerHTML = '<p class="vazio" style="padding:6px">Consultando referência…</p>';
  try {
    const pt = await api.referenciaPonto(p.x.toFixed(1), p.y.toFixed(1));
    const ref = await api.referenciaKm(pt.km.toFixed(3));
    const ativs = ref.atividades || [];
    box.innerHTML = `<button type="button" class="fechar" title="Fechar">×</button>
      <h4>Ponto clicado</h4>
      <div id="v-info-ref"><b>km ${pt.km.toFixed(3).replace('.', ',')}</b> · estaca <b>${esc(pt.estaca)}</b><br>
      ${pt.afastamento_m != null ? `${Math.round(pt.afastamento_m)} m à ${pt.lado === 'esquerdo' ? 'esquerda' : 'direita'} do eixo<br>` : ''}
      Lote: <b>${esc(ref.lote ? `${ref.lote.id} — ${ref.lote.construtora}` : '—')}</b><br>
      Segmento: ${esc(ref.segmento ? ref.segmento.id : '—')}${pt.aviso ? `<br><span style="color:var(--critico)">${esc(pt.aviso)}</span>` : ''}</div>
      <h4 style="margin-top:6px">Atividades neste km (${ativs.length})</h4>
      <ul>${ativs.map(a => `<li><span class="link-ativ" data-ir="${esc(a.id)}">${esc(a.id)}</span>
        ${a.critica ? '<span class="pill crit">crítica</span>' : ''} · ${num(a.percentual_executado_data_status, 0)}%</li>`).join('')}</ul>`;
    box.querySelector('.fechar').addEventListener('click', () => { box.hidden = true; });
    box.querySelectorAll('[data-ir]').forEach(s => s.addEventListener('click', () => selecionar(s.dataset.ir, 'referencia')));
  } catch (e) {
    box.innerHTML = `<button type="button" class="fechar" title="Fechar">×</button><p class="erro">Referência indisponível: ${esc(e.message)}</p>`;
    box.querySelector('.fechar').addEventListener('click', () => { box.hidden = true; });
  }
}

// ---------------- modo "Modelo IFC" no 3D ----------------
function statusIfc(html) {
  const el = $('#v-ifc-status');
  el.hidden = !html;
  el.innerHTML = html || '';
}

/** Linha de status do IFC: resumo do modelo e os GlobalIds da atividade selecionada. */
function atualizarStatusIfc() {
  if (!viewer || viewer.modoGeo !== 'ifc' || !viewer.ifc) return;
  const r = viewer.ifc.resumo || {};
  const sel = estado.selecionada;
  const gids = sel ? viewer.globalIdsDe(sel) : [];
  statusIfc(`<span><b>Modelo IFC</b> (${esc(r.schema || 'IFC')}) em escala real: ${num(viewer.ifc.gids.size)} elementos com GlobalId,
      ${num(viewer.ifc.porAtividade.size)} atividades vinculadas${viewer.ifc.semVinculo.length ? `, ${num(viewer.ifc.semVinculo.length)} malhas sem vínculo` : ''}.
      Cor pelo estado 4D pelo vínculo GlobalId → atividade.</span>
    ${sel ? `<span id="v-ifc-sel">Selecionada <b>${esc(sel)}</b>: ${gids.length
      ? `${num(gids.length)} elemento(s) IFC — GlobalId ${gids.slice(0, 6).map(g => `<code>${esc(g)}</code>`).join(', ')}${gids.length > 6 ? '…' : ''}`
      : 'sem elemento no modelo IFC'}</span>` : ''}`);
}

async function trocarGeometria(modo) {
  if (!viewer) return;
  if (modo !== 'ifc') {
    viewer.setModoGeometria('sintetica');
    $('#v-exagero').disabled = viewer.modoVisual !== 'analise';
    statusIfc('');
    $('#legenda-3d').innerHTML = viewer.legenda();
    return;
  }
  const indisp = (saude && saude.modulos && saude.modulos.indisponiveis) || {};
  if (indisp['ifc.rotas']) {
    $('#v-geometria').value = 'sintetica';
    statusIfc(`<span class="erro" style="display:block">Modelo IFC indisponível nesta API (módulo ifc.rotas: ${esc(indisp['ifc.rotas'])}).
      Mostrando a geometria esquemática.</span>`);
    return;
  }
  $('#v-geometria').disabled = true;
  statusIfc('<span>Carregando o modelo IFC (GLB) e o vínculo GlobalId → atividade…</span>');
  try {
    const vinculo = await api.ifcVinculo();
    await viewer.carregarIfc(api.urlIfcGlb(), vinculo);
    viewer.setModoGeometria('ifc');
    $('#v-exagero').disabled = true;
    $('#legenda-3d').innerHTML = viewer.legenda();
    atualizarStatusIfc();
    // escala real: a vista geral vira uma linha; enquadra uma janela curta (~600 m) na seleção ou na frente crítica
    const sel = estado.selecionada && estado.ativ.get(estado.selecionada);
    const kmC = sel && sel.km_ini != null ? (Number(sel.km_ini) + Number(sel.km_fim)) / 2 : (frenteCritica()[0] + frenteCritica()[1]) / 2;
    viewer.enquadrarKm(kmC - 0.3, kmC + 0.3);
  } catch (e) {
    $('#v-geometria').value = 'sintetica';
    viewer.setModoGeometria('sintetica');
    $('#v-exagero').disabled = viewer.modoVisual !== 'analise';
    statusIfc(`<span class="erro" style="display:block">Não foi possível carregar o modelo IFC: ${esc(e.message || String(e))}</span>`);
  } finally {
    $('#v-geometria').disabled = false;
  }
}

function rotuloEstado(s) {
  return { concluido: 'concluído', em_execucao: 'em execução', nao_iniciado: 'não iniciado' }[s] || '';
}

// ---------------- timeline 4D ----------------
function configurarTimeline() {
  const sl = $('#t-slider');
  const max = estado.diaFim - estado.diaInicio;
  sl.max = String(max);
  if (diaTimeline === null) diaTimeline = diaDe(estado.dataStatus);
  diaTimeline = Math.min(Math.max(diaTimeline, estado.diaInicio), estado.diaFim);
  sl.value = String(diaTimeline - estado.diaInicio);
  const pos = (diaDe(estado.dataStatus) - estado.diaInicio) / max;
  // compensa a largura do "thumb" (~16 px) do range
  $('#t-marca-status').style.left = `calc(${pos * 100}% + ${8 - pos * 16}px)`;
  $('#t-data').textContent = dataBR(isoDe(diaTimeline));
}

const buscarEstado4dDebounced = debounce(() => buscarEstado4d(), 120);
async function buscarEstado4d() {
  if (!viewer) return;
  const meu = ++seq4d;
  try {
    const r = await api.estado4d(isoDe(diaTimeline), estado.cenarioAtivo);
    if (meu !== seq4d) return; // resposta antiga
    viewer.setEstado4d(r.atividades);
  } catch (e) {
    if (meu === seq4d) erroGlobal(`Falha ao obter o estado 4D: ${e.message}`);
  }
}

$('#t-slider').addEventListener('input', () => {
  diaTimeline = estado.diaInicio + Number($('#t-slider').value);
  $('#t-data').textContent = dataBR(isoDe(diaTimeline));
  buscarEstado4dDebounced();
});
/** Leva a timeline 4D a um dia (usado pela apresentação guiada). */
function irParaDia(dia) {
  pararPlay();
  diaTimeline = dia;
  configurarTimeline();
  buscarEstado4d();
}
$('#t-status').addEventListener('click', () => {
  pararPlay();
  diaTimeline = diaDe(estado.dataStatus);
  configurarTimeline();
  buscarEstado4d();
});
function pararPlay() {
  if (tocando) clearInterval(tocando);
  tocando = null;
  $('#t-play').textContent = '▶';
  $('#t-play').title = 'Reproduzir (passo semanal)';
}
$('#t-play').addEventListener('click', () => {
  if (tocando) { pararPlay(); return; }
  if (diaTimeline >= estado.diaFim) diaTimeline = estado.diaInicio;
  $('#t-play').textContent = '❚❚';
  $('#t-play').title = 'Pausar';
  tocando = setInterval(() => {
    diaTimeline = Math.min(estado.diaFim, diaTimeline + Number($('#t-velocidade').value));
    configurarTimeline();
    buscarEstado4dDebounced();
    if (diaTimeline >= estado.diaFim) pararPlay();
  }, 400);
});

// ---------------- eventos do barramento ----------------
ouvir('filtros', ({ loteMudou }) => {
  resumoFiltros();
  renderGantt();
  renderTabela();
  if (viewer) viewer.setFiltro(passaFiltro, $('#v-ocultar').checked);
  if (loteMudou) recarregarPainel();
  renderBalanco();
  atualizarRecursos();
  renderFiscalizacao();
});

ouvir('cenario', () => {
  resumoFiltros();
  renderGantt();
  renderTabela();
  renderDetalhes();
  if (viewer) viewer.setFiltro(passaFiltro, $('#v-ocultar').checked);
  buscarEstado4d();
  renderBalanco();
  atualizarRecursos();
});

ouvir('selecao', ({ id, origem }) => {
  renderDetalhes();
  renderGantt();
  renderTabela();
  if (viewer) {
    viewer.setSelecao(id);
    if (id && origem !== '3d') viewer.enquadrarAtividade(id);
  }
  if (id && origem !== 'gantt') rolarGanttPara(id);
  if (id && origem !== 'tabela') rolarTabelaPara(id);
  atualizarStatusIfc();
  renderBalanco();
  renderFiscalizacao();
});

window.addEventListener('resize', debounce(() => {
  if (estado.aba === 'cronograma') renderGantt();
  if (estado.aba === 'balanco') renderBalanco();
}, 200));

/**
 * Trecho (~7 km) da frente crítica atual no cenário ativo: centrado no fim da primeira atividade
 * crítica em andamento (ou no meio da primeira crítica não concluída).
 */
function frenteCritica() {
  const r = estado.cenarios[estado.cenarioAtivo] || estado.cenarios.independente;
  const kmMax = Math.max(...estado.projeto.lotes.map(l => l.km_fim));
  const crit = estado.projeto.atividades.filter(a => a.tipo === 'tarefa' && a.km_ini != null && a.status !== 'concluida'
    && (a.km_fim - a.km_ini) <= 10 && r && r.atividades[a.id] && r.atividades[a.id].critica);
  const emAnd = crit.filter(a => a.status === 'em_andamento');
  let centro;
  if (emAnd.length) centro = emAnd[0].km_fim;
  else if (crit.length) {
    crit.sort((a, b) => (r.atividades[a.id].inicio || '').localeCompare(r.atividades[b.id].inicio || ''));
    centro = (crit[0].km_ini + crit[0].km_fim) / 2;
  } else centro = kmMax / 2;
  const a = Math.max(0, Math.min(kmMax - 7, centro - 3.5));
  return [a, a + 7];
}

// ---------------- simulação -> recarga ----------------
async function aposSimulacao(ativa) {
  try {
    estado.cenarios.simulado = await api.cenario('simulado');
    invalidarConflitos();
    invalidarRecursos();
    recalcularIntervalo();
    configurarTimeline();
    emitir('cenarios');
    await recarregarPainel();
    definirCenario(ativa ? 'simulado' : 'independente');
  } catch (e) {
    erroGlobal(`Falha ao recarregar após a simulação: ${e.message}`);
  }
}

// ---------------- carga inicial ----------------
/** Lista as obras, escolhe a do hash (ou a primeira) e preenche o seletor. */
async function escolherObra() {
  const obras = await api.obras();
  if (!obras || !obras.length) throw new Error('a API não lista nenhuma obra');
  estado.obras = obras;
  const pedida = HASH_INICIAL.obra;
  let obra = obras.find(o => o.id === pedida);
  if (!obra) {
    if (pedida) erroGlobal(`Obra “${pedida}” não existe nesta API (disponíveis: ${obras.map(o => o.id).join(', ')}). Mostrando “${obras[0].id}”.`);
    obra = obras[0];
  }
  definirObra(obra.id);
  estado.obra = obra;
  $('#v-baixar-ifc').href = api.urlIfcExportar(true);
  $('#obra-sel').innerHTML = obras.map(o => `<option value="${esc(o.id)}">${esc(o.nome)} — ${esc(o.tipo)}, ${num(o.extensao_km, 1)} km</option>`).join('');
  $('#obra-sel').value = obra.id;
  $('#aviso-obra').textContent = obra.nome;
  escreverHash();
}

$('#obra-sel').addEventListener('change', () => {
  const nova = $('#obra-sel').value;
  if (!nova) return;
  // troca de obra = recarga completa (estado, 3D e caches limpos); a obra fica no hash da URL
  definirObra(nova);
  escreverHash();
  location.reload();
});
$('#btn-tour').addEventListener('click', () => abrirTour());
$('#btn-relatorio').addEventListener('click', () => {
  window.open(api.urlRelatorio(), '_blank', 'noopener');
});
$('#btn-reuniao').addEventListener('click', () => {
  const ativo = document.body.classList.toggle('modo-reuniao');
  $('#btn-reuniao').setAttribute('aria-pressed', String(ativo));
  $('#btn-reuniao').textContent = ativo ? 'Sair da reunião' : 'Modo reunião';
  $('#filtros').classList.toggle('reuniao-oculto', ativo);
  $('#v-filtros').setAttribute('aria-expanded', String(!ativo));
  if (viewer) viewer.aoMostrar();
});
$('#v-filtros').addEventListener('click', () => {
  const oculto = $('#filtros').classList.toggle('reuniao-oculto');
  $('#v-filtros').setAttribute('aria-expanded', String(!oculto));
  if (viewer) viewer.aoMostrar();
});

async function carregar() {
  try {
    await escolherObra();
    saude = await api.saude();
    const projeto = await api.projeto();
    indexarProjeto(projeto);
    definirServicos(projeto);
    // estacas dos km das atividades (para tooltips): vêm da API, pré-carregadas sem bloquear
    preCarregarEstacas(projeto.atividades.flatMap(a => [a.km_ini, a.km_fim]).filter(k => k != null));
    estado.plano = planoDeEstilos(projeto);
    if (projeto.ferrovia && projeto.ferrovia.nome) { $('#aviso-obra').textContent = projeto.ferrovia.nome; $('#aviso-obra').title = projeto.ferrovia.nome; }
    document.title = `INFRA 4D INTELLIGENCE — ${estado.obra ? estado.obra.nome : 'beta'} (dados fictícios)`;
    $('#aviso-data-status').textContent = dataBR(projeto.meta.data_status);
    const res = await Promise.all(CENARIOS.map(c => api.cenario(c)));
    CENARIOS.forEach((c, i) => { estado.cenarios[c] = res[i]; });
    recalcularIntervalo();
    preencherFiltros();
    resumoFiltros();
    renderApresentacao($('#apresentacao'), saude);
    $('#gantt-legenda').innerHTML = legendaGantt();
    configurarTimeline();
    renderGantt();
    renderTabela();
    renderDetalhes();
    // em paralelo, sem bloquear
    estado.simulacao = await api.simulacao();
    if (Array.isArray(estado.simulacao && estado.simulacao.ajustes) && estado.simulacao.ajustes.length) definirCenario('simulado');
    renderSimulacao();
    // Primeiro estado 4D antes das análises opcionais: num processo frio, Monte
    // Carlo/riscos/histórico podem ocupar a fila e deixar a cena toda cinza.
    if (estado.aba === 'modelo') { await garantirViewer(); viewer && viewer.aoMostrar(); }
    api.comparacao('construtora', 'independente')
      .then(c => { definirComparacaoConstrutora(c); renderPainel(); })
      .catch(() => {});
    // Monte Carlo pode demorar: carrega em segundo plano e o cartão mostra "calculando" até chegar
    definirPrevisao(null);
    api.previsaoProbabilistica(200)
      .then(p => { definirPrevisao(p); renderPainel(); })
      .catch(e => { definirPrevisao({ erro: e.message }); renderPainel(); });
    await recarregarPainel();
    // a aba aberta pelo hash foi mostrada antes de os dados chegarem: desenha agora o conteúdo dela
    renderAbaAtual();
    // continuação do tour após trocar de obra (#apresentacao?obra=X&tour=1)
    if (HASH_INICIAL.tour) abrirTour();
  } catch (e) {
    erroGlobal(`Não foi possível carregar os dados: ${e.message}`);
    const msg = `<p class="erro" style="margin:16px">API indisponível ou com erro: ${esc(e.message)}. Inicie o servidor e clique em “Tentar de novo”.</p>`;
    if (!estado.projeto) {
      $('#apresentacao').innerHTML = msg;
      for (const s of ['#painel', '#gantt', '#simulacao']) $(s).innerHTML = msg;
    }
  }
}

iniciarGantt($('#gantt'));
iniciarTabela($('#tabela'));
iniciarPainel($('#painel'), { irPara });
iniciarSimulacao($('#simulacao'), { aposMudanca: aposSimulacao, irPara });
iniciarBalanco($('#balanco'), $('#lb-sobrepor'), api);
iniciarRecursos($('#recursos'), { irPara });
iniciarCronoImport($('#cronoimport'), { irPara });
iniciarFiscalizacao($('#fiscalizacao'), { irPara });
iniciarAnalises($('#analises'), { irPara, aposSimulacao });
iniciarDetalhes({
  verNo3D: (id) => { irPara('modelo'); selecionar(id, 'detalhes'); },
  verNoGantt: (id) => { irPara('cronograma'); rolarGanttPara(id); rolarTabelaPara(id); },
  simular: (id) => { irPara('simulacao'); prepararAtividade(id); },
  temGeometria: (id) => {
    const a = estado.ativ.get(id);
    if (viewer) return viewer.temGeometria(id);
    return !!(estado.plano && temGeometriaPlano(estado.plano, a));
  },
});
renderApresentacao($('#apresentacao'), null);
// gancho de inspeção para testes automatizados/depuração no console (somente leitura recomendada)
window.__infra4d = { estado, viewer: () => viewer, irPara, selecionar, obra: () => obraSelecionada(),
  tour: { abrir: abrirTour, proximo: tourProximo, anterior: tourAnterior, sair: tourSair, estado: estadoTour } };
iniciarTour({ irPara, selecionar, irParaDia });
// permite abrir direto numa aba (e obra): /#modelo, /#painel?obra=rodovia, ...
const abaInicial = lerHash().aba;
if (abaInicial && document.querySelector(`.abas [data-aba="${CSS.escape(abaInicial)}"]`)) irPara(abaInicial);
carregar();
