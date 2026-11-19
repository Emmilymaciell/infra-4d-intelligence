// Apresentação guiada (tour) para a demonstração: balão sobre o elemento real, passos que EXECUTAM a ação
// (trocar de aba, selecionar, mover a timeline, simular, comparar cronograma) e textos com os NÚMEROS
// LIDOS DA API no momento — nenhum número fixo no texto. Cada número fica num <b data-num="chave"> e em
// `numeros[chave]` (valor bruto), para conferência automática (tests/e2e/verificar_interface.py).

import { estado } from './estado.js';
import { api } from './api.js';
import { esc, num, dataBR, diaDe } from './util.js';
import { aplicarExemplo, exemplosSimulacao, limparSimulacaoExterna } from './simulacao.js';
import { rodarExemploCrono } from './cronoimport.js';

let op = {};               // {irPara, selecionar, irParaDia}
let aberto = false;
let passo = 0;
let ocupado = false;
let simAplicada = false;
let numeros = {};
let ctx = null;            // dados carregados no início do tour (promessas e resultados)
let el = null;             // {realce, balao}
let texto = '';
let erroPasso = null;

export function iniciarTour(opcoes) {
  op = opcoes || {};
  document.addEventListener('keydown', (e) => {
    if (!aberto) return;
    const t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT')) return;
    if (e.key === 'ArrowRight') { e.preventDefault(); proximo(); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); anterior(); }
    else if (e.key === 'Escape') { e.preventDefault(); sair(); }
  });
  window.addEventListener('resize', () => aberto && posicionar());
  window.addEventListener('scroll', () => aberto && posicionar(), true);
}

/** Registra um número exibido (valor bruto da API) e devolve o HTML formatado. */
function N(chave, bruto, formatado) {
  numeros[chave] = bruto;
  return `<b data-num="${esc(chave)}">${esc(formatado ?? bruto)}</b>`;
}
const D = (chave, iso) => N(chave, iso, dataBR(iso));
const sinalDias = (d) => `${d > 0 ? '+' : d < 0 ? '−' : ''}${Math.abs(d)} dias corridos`;

// ---------------------------------------------------------------- passos
function passos() {
  const p = estado.projeto;
  const fer = p.ferrovia || {};
  const outras = (estado.obras || []).filter(o => o.id !== (estado.obra && estado.obra.id));
  const lista = [
    {
      titulo: 'A obra (fictícia)', aba: 'apresentacao', alvo: '.fluxo',
      texto: async () => `${esc(fer.nome || 'Obra')}: ${N('extensao_km', fer.extensao_km, `${num(fer.extensao_km, 0)} km`)},
        ${N('lotes', p.lotes.length)} lotes, ${N('atividades', p.atividades.length)} atividades e ${N('relacoes', p.relacoes.length)} relações lógicas.
        Data de status: ${D('data_status', p.meta.data_status)}. <b>Todos os dados são fictícios.</b>
        O motor segue o fluxo da faixa azul: produtividade → duração → rede (CPM) → término.`,
    },
    {
      titulo: 'Painel: o problema', aba: 'painel', alvo: '#painel .kpis',
      texto: async () => {
        const pn = await ctx.painel;
        const t = pn.terminos;
        const d = diaDe(t.independente) - diaDe(t.construtora);
        return `A construtora prevê o término em ${D('termino_construtora', t.construtora)}, supondo que a obra produza o planejado daqui para frente.
          A análise independente, com a produtividade <b>medida</b> nos boletins, prevê ${D('termino_independente', t.independente)}:
          ${N('delta_dias', d, sinalDias(d))}.`;
      },
    },
    {
      titulo: 'Painel: a causa', aba: 'painel', alvo: '#painel .alertas',
      texto: async () => {
        const pn = await ctx.painel;
        const a = (pn.alertas || [])[0];
        if (!a) return 'Nenhum alerta no escopo.';
        numeros.alerta = a.texto;
        return `Alerta principal, gerado pelo motor: <i>${esc(a.texto)}</i>
          ${a.atividade_id ? ` Atividade: ${N('alerta_atividade', a.atividade_id)}.` : ''}`;
      },
    },
    {
      titulo: 'Três métodos de previsão', aba: 'painel', alvo: '#p-metodos',
      texto: async () => {
        const [es, mc] = await Promise.all([ctx.es, ctx.mc]);
        const r = (es.resultados || []).find(x => x.lote == null) || es.resultados[0];
        return `Earned Schedule (avanço agregado, SPI ${N('spi', r.SPI, num(r.SPI, 3))}) aponta ${D('termino_es', r.IEAC_spi_termino)}.
          Monte Carlo sobre a produtividade medida: P50 ${D('p50', mc.p50)} e P80 ${D('p80', mc.p80)}
          (faixa estreita por construção: só a incerteza da média). O CPM independente localiza <b>qual</b> trabalho atrasa.`;
      },
    },
    {
      titulo: 'Modelo 3D/4D', aba: 'modelo', alvo: '#viewer',
      acao: async () => {
        const id = frenteCritica();
        if (id) op.selecionar(id, 'tour');
        op.irParaDia(diaDe(p.meta.data_status));
      },
      texto: async () => {
        const pn = await ctx.painel;
        return `Na data de status, cada peça é 1 km de um serviço, colorida pelo estado (verde concluído, âmbar em execução, cinza não iniciado).
          ${N('n_criticas', pn.criticas_independente.length)} atividades estão no caminho crítico (contorno vermelho).
          Selecionada: ${N('frente', estado.selecionada || '—')}. Clique numa peça para ver a memória de cálculo.`;
      },
    },
    {
      titulo: 'Linha do tempo 4D', aba: 'modelo', alvo: '#timeline',
      acao: async () => {
        const pn = await ctx.painel;
        op.irParaDia(diaDe(pn.terminos.independente));
      },
      texto: async () => {
        const pn = await ctx.painel;
        return `A linha do tempo foi levada ao término independente, ${D('termino_independente_4d', pn.terminos.independente)}: a obra aparece concluída.
          Arraste o controle ou use ▶ para ver a obra avançar semana a semana.`;
      },
    },
    {
      titulo: 'Simulação: atividade crítica', aba: 'simulacao', alvo: '#simulacao .sim-res',
      acao: async () => { ctx.sim1 = await aplicarExemplo(0); simAplicada = true; },
      texto: async () => textoSimulacao(ctx.sim1, 'sim1', 'crítica'),
    },
    {
      titulo: 'Simulação: atividade com folga', aba: 'simulacao', alvo: '#simulacao .sim-res',
      acao: async () => { ctx.sim2 = await aplicarExemplo(1); simAplicada = true; },
      texto: async () => {
        const t = textoSimulacao(ctx.sim2, 'sim2', 'com folga');
        const d = ctx.sim2 && ctx.sim2.simulacao ? ctx.sim2.simulacao.comparacao.delta_dias_corridos : null;
        return t + (d === 0 ? ' <b>A folga absorve o atraso</b>: gerir pelo caminho crítico, não pelo percentual.' : '');
      },
    },
    {
      titulo: 'Linha de balanço (tempo × km)', aba: 'balanco', alvo: '#balanco',
      acao: async () => {
        if (simAplicada) { await limparSimulacaoExterna(); simAplicada = false; }
        const chk = document.querySelector('#lb-conflitos');
        if (chk && !chk.checked) { chk.checked = true; chk.dispatchEvent(new Event('change')); }
        ctx.conflitos = await api.recursosConflitos('independente', 1, 0, null);
      },
      texto: async () => `Cada serviço é uma frente que avança pelos km ao longo do tempo (simulação já desfeita: cenário independente).
        ${N('n_conflitos', ctx.conflitos.n_conflitos)} conflitos entre frentes sucessivas (menos de 1 km entre elas) estão marcados com “!”.
        É o diagrama do planejamento de obra linear.`,
    },
    {
      titulo: 'Cronograma da construtora', aba: 'cronoimport', alvo: '#ci-res',
      acao: async () => { ctx.crono = await rodarExemploCrono(); },
      texto: async () => {
        const r = ctx.crono;
        if (!r || r.erro || !r.comparacao) return `Comparação indisponível: ${esc((r && r.erro) || 'sem resposta')}`;
        const c = r.comparacao;
        return `O cronograma da construtora exportado em MSPDI e recalculado pelo motor termina em ${D('crono_importado', c.termino_importado)};
          o motor independente, em ${D('crono_motor', c.termino_motor)}: ${N('crono_delta', c.delta_termino_dias_corridos, sinalDias(c.delta_termino_dias_corridos))}.
          ${N('crono_diferencas', c.n_com_diferenca)} atividades diferem, na tabela ordenada pela maior diferença.`;
      },
    },
    {
      titulo: 'Relatório técnico', aba: null, alvo: '#btn-relatorio',
      texto: async () => `Tudo isso sai num relatório técnico imprimível da obra (abre em nova aba).
        <div style="margin-top:6px"><button type="button" data-tour="relatorio">Abrir o relatório</button></div>`,
    },
    {
      titulo: 'O que é real × o que é simulado', aba: 'apresentacao', alvo: '#apresentacao .cartoes-2',
      texto: async () => {
        const cartoes = [...document.querySelectorAll('#apresentacao .cartoes-2 .cartao')];
        const itens = (c) => [...c.querySelectorAll('li')].map(li => li.textContent.trim().replace(/\s+/g, ' '));
        const real = cartoes[0] ? itens(cartoes[0]) : [];
        const sim = cartoes[1] ? itens(cartoes[1]) : [];
        numeros.real = real; numeros.simulado = sim;
        return `<b>Real:</b> ${real.slice(0, 3).map(esc).join(' · ')}.<br><b>Simulado:</b> ${sim.slice(0, 3).map(esc).join(' · ')}.`;
      },
    },
  ];
  if (outras.length) {
    const o = outras[0];
    lista.push({
      titulo: `O mesmo motor numa ${o.tipo}`, aba: null, alvo: '#obra-sel',
      texto: async () => {
        numeros.outra_obra = o.id;
        return `Nada aqui é específico de ferrovia: a mesma plataforma lê ${N('outra_nome', o.nome)} (${esc(o.tipo)}, ${N('outra_km', o.extensao_km, `${num(o.extensao_km, 0)} km`)}).
          <div style="margin-top:6px"><button type="button" class="primario" data-tour="trocar" data-obra="${esc(o.id)}">Repetir o tour na ${esc(o.tipo)}</button></div>`;
      },
    });
  }
  return lista;
}

function textoSimulacao(r, k, tipo) {
  if (!r || r.erro || !r.simulacao) return `Simulação indisponível: ${esc((r && r.erro) || 'sem resposta')}`;
  const c = r.simulacao.comparacao;
  const aj = r.exemplo.ajuste;
  const partes = [];
  if (aj.produtividade != null) partes.push(`produtividade ${N(`${k}_produtividade`, aj.produtividade, num(aj.produtividade, 2))}`);
  if (aj.equipes != null) partes.push(`${N(`${k}_equipes`, aj.equipes)} equipe(s)`);
  return `Atividade ${esc(tipo)} ${N(`${k}_atividade`, aj.atividade_id)} com ${partes.join(' e ')}:
    o término vai de ${D(`${k}_antes`, c.termino_ref)} para ${D(`${k}_depois`, c.termino_alvo)}
    (${N(`${k}_delta`, c.delta_dias_corridos, sinalDias(c.delta_dias_corridos))}). A tela mostra a conta e a cadeia determinante.`;
}

/** Atividade crítica em andamento (ou a 1ª crítica não concluída) do cenário independente. */
function frenteCritica() {
  const r = estado.cenarios.independente;
  if (!r) return null;
  const crit = estado.projeto.atividades.filter(a => a.tipo === 'tarefa' && a.status !== 'concluida' && r.atividades[a.id] && r.atividades[a.id].critica);
  return ((crit.find(a => a.status === 'em_andamento') || crit[0]) || {}).id || null;
}

// ---------------------------------------------------------------- ciclo
export async function abrirTour() {
  if (aberto || !estado.projeto) return;
  aberto = true;
  passo = 0;
  simAplicada = false;
  ctx = {
    painel: api.painel(null),
    es: api.earnedSchedule(null),
    mc: api.previsaoProbabilistica(200),
  };
  // evita "unhandled rejection" enquanto o passo não chega
  for (const k of ['painel', 'es', 'mc']) ctx[k].catch(() => {});
  criarElementos();
  await irPasso(0);
}

async function irPasso(i) {
  const lista = passos();
  if (i < 0 || i >= lista.length || ocupado) return;
  passo = i;
  ocupado = true;
  erroPasso = null;
  numeros = {};
  const s = lista[i];
  texto = '<span class="tour-exec">Executando…</span>';
  render(lista);
  try {
    if (s.aba && estado.aba !== s.aba) op.irPara(s.aba);
    if (s.acao) await s.acao();
    texto = await s.texto();
  } catch (e) {
    erroPasso = e.message || String(e);
    texto = `<span class="erro" style="display:block">Não foi possível executar este passo: ${esc(erroPasso)}</span>`;
  } finally {
    ocupado = false;
  }
  render(lista);
}

export function proximo() {
  const n = passos().length;
  if (passo >= n - 1) { sair(); return; }
  irPasso(passo + 1);
}
export function anterior() { irPasso(passo - 1); }

export async function sair() {
  if (!aberto) return;
  aberto = false;
  if (el) { el.realce.remove(); el.balao.remove(); el = null; }
  if (simAplicada) {
    simAplicada = false;
    try { await limparSimulacaoExterna(); } catch { /* a faixa de aviso mostrará a simulação se a limpeza falhar */ }
  }
}

async function trocarObra(id) {
  await sair();
  location.hash = `#apresentacao?obra=${encodeURIComponent(id)}&tour=1`;
  location.reload();
}

// ---------------------------------------------------------------- desenho
function criarElementos() {
  const realce = document.createElement('div');
  realce.className = 'tour-realce';
  const balao = document.createElement('div');
  balao.className = 'tour-balao';
  balao.setAttribute('role', 'dialog');
  balao.setAttribute('aria-live', 'polite');
  document.body.append(realce, balao);
  el = { realce, balao };
  balao.addEventListener('click', (e) => {
    const b = e.target.closest('[data-tour]');
    if (!b) return;
    const a = b.dataset.tour;
    if (a === 'proximo') proximo();
    else if (a === 'anterior') anterior();
    else if (a === 'sair') sair();
    else if (a === 'relatorio') window.open(api.urlRelatorio(), '_blank', 'noopener');
    else if (a === 'trocar') trocarObra(b.dataset.obra);
  });
}

function render(lista) {
  if (!el) return;
  const s = lista[passo];
  const ultimo = passo === lista.length - 1;
  el.balao.innerHTML = `
    <div class="tour-cab"><span>Passo ${passo + 1}/${lista.length}</span><b>${esc(s.titulo)}</b>
      <button type="button" class="tour-x" data-tour="sair" title="Sair (Esc)">×</button></div>
    <div class="tour-corpo" id="tour-corpo">${texto}</div>
    <div class="tour-pe">
      <button type="button" data-tour="anterior" ${passo === 0 || ocupado ? 'disabled' : ''}>← Anterior</button>
      <button type="button" class="primario" data-tour="proximo" ${ocupado ? 'disabled' : ''}>${ultimo ? 'Concluir' : 'Próximo →'}</button>
      <span class="tour-dica">←/→ navegam · Esc sai</span>
    </div>`;
  posicionar();
}

function posicionar() {
  if (!el) return;
  const s = passos()[passo];
  const alvo = s && s.alvo ? document.querySelector(s.alvo) : null;
  const b = el.balao;
  if (!alvo || !alvo.offsetParent) {
    el.realce.style.display = 'none';
    b.style.left = `${Math.max(16, (window.innerWidth - b.offsetWidth) / 2)}px`;
    b.style.top = `${Math.max(16, (window.innerHeight - b.offsetHeight) / 3)}px`;
    return;
  }
  let r = alvo.getBoundingClientRect();
  if (r.top < 60 || r.bottom > window.innerHeight) {
    alvo.scrollIntoView({ block: r.height > window.innerHeight * 0.6 ? 'start' : 'center' });
    r = alvo.getBoundingClientRect();
  }
  const pad = 6;
  Object.assign(el.realce.style, {
    display: 'block', left: `${r.left - pad}px`, top: `${r.top - pad}px`, width: `${r.width + 2 * pad}px`, height: `${Math.min(r.height, window.innerHeight) + 2 * pad}px`,
  });
  const bw = b.offsetWidth, bh = b.offsetHeight;
  let top = r.bottom + 12;
  if (top + bh > window.innerHeight - 8) top = r.top - bh - 12;
  if (top < 8) top = Math.max(8, Math.min(window.innerHeight - bh - 8, r.top + 12));
  const left = Math.min(Math.max(8, r.left), window.innerWidth - bw - 8);
  b.style.left = `${left}px`;
  b.style.top = `${top}px`;
}

/** Estado para inspeção/teste. */
export function estadoTour() {
  return { aberto, passo, total: aberto ? passos().length : 0, titulo: aberto ? passos()[passo].titulo : null,
    numeros: { ...numeros }, ocupado, simAplicada, erro: erroPasso, exemplos: exemplosSimulacao().map(e => e.ajuste) };
}
