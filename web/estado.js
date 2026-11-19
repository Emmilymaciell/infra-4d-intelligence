// Estado compartilhado da aplicação + barramento de eventos.
//
// Eventos emitidos:
//   'filtros'      filtros globais mudaram
//   'cenario'      cenário ativo mudou (Gantt/3D/tabela)
//   'selecao'      {id, origem}  atividade selecionada ('3d' | 'gantt' | 'tabela' | 'painel' | 'detalhes' | 'sim')
//   'cenarios'     resultados de cenários recarregados (ex.: após simulação)
//   'painel'       dados do painel recarregados
//   'simulacao'    resultado da simulação mudou
//   'aba'          aba visível mudou

import { diaDe } from './util.js';

export const estado = {
  projeto: null,          // /api/projeto
  ativ: new Map(),        // id -> atividade
  servicos: new Map(),    // id -> serviço
  preds: new Map(),       // id -> [relação]
  succs: new Map(),       // id -> [relação]
  cenarios: {},           // nome -> /api/cenarios/{nome}
  cenarioAtivo: 'independente',
  // kmIni/kmFim: números ou null; dataIni/dataFim: 'AAAA-MM-DD' ou ''
  filtros: { lote: '', disciplina: '', servico: '', soCritico: false, segmento: '', kmIni: null, kmFim: null, dataIni: '', dataFim: '' },
  selecionada: null,
  painel: null,
  painelGeral: null,      // painel sem filtro de lote (produtividades de todos os lotes)
  simulacao: null,        // /api/simulacao
  aba: 'apresentacao',
  dataStatus: null,       // 'AAAA-MM-DD'
  diaInicio: 0,
  diaFim: 0,
};

const bus = new EventTarget();
export function emitir(nome, detalhe) {
  bus.dispatchEvent(new CustomEvent(nome, { detail: detalhe }));
}
export function ouvir(nome, fn) {
  bus.addEventListener(nome, (e) => fn(e.detail));
}

export function indexarProjeto(p) {
  estado.projeto = p;
  estado.ativ = new Map(p.atividades.map(a => [a.id, a]));
  estado.servicos = new Map(p.servicos.map(s => [s.id, s]));
  estado.preds = new Map();
  estado.succs = new Map();
  for (const r of p.relacoes) {
    if (!estado.preds.has(r.sucessora)) estado.preds.set(r.sucessora, []);
    if (!estado.succs.has(r.predecessora)) estado.succs.set(r.predecessora, []);
    estado.preds.get(r.sucessora).push(r);
    estado.succs.get(r.predecessora).push(r);
  }
  estado.dataStatus = p.meta.data_status;
}

/** Recalcula o intervalo de datas (início do projeto até o maior término entre cenários). */
export function recalcularIntervalo() {
  // datas inválidas vindas dos dados (diaDe -> null) são ignoradas, nunca viram NaN no eixo
  let ini = diaDe(estado.projeto.meta.inicio_projeto);
  let fim = diaDe(estado.projeto.meta.termino_linha_base);
  for (const c of Object.values(estado.cenarios)) {
    const d = c ? diaDe(c.termino) : null;
    if (d !== null) fim = fim === null ? d : Math.max(fim, d);
  }
  if (ini === null) ini = diaDe(estado.projeto.meta.data_status) ?? (fim !== null ? fim - 365 : 0);
  if (fim === null || fim <= ini) fim = ini + 365;
  estado.diaInicio = ini;
  estado.diaFim = fim;
}

export function resultadoAtivo() {
  return estado.cenarios[estado.cenarioAtivo] || estado.cenarios.independente;
}

export function nomeServico(id) {
  if (!id) return '—';
  const s = estado.servicos.get(id);
  if (s) return s.nome;
  return { SIN: 'Sinalização, testes e liberação', 'OAE-FUN': 'OAE — fundações',
    'OAE-MES': 'OAE — mesoestrutura', 'OAE-SUE': 'OAE — superestrutura' }[id] || id;
}

/** A atividade passa nos filtros globais? */
export function passaFiltro(a) {
  const f = estado.filtros;
  if (f.lote && a.lote_id !== f.lote) return false;
  if (f.disciplina && a.disciplina !== f.disciplina) return false;
  if (f.servico && a.servico_id !== f.servico) return false;
  if (f.soCritico) {
    const r = resultadoAtivo();
    const ra = r && r.atividades[a.id];
    if (!ra || !ra.critica) return false;
  }
  if (f.segmento && a.segmento_id !== f.segmento) return false;
  // faixa de km: a atividade precisa ter trecho e ENCOSTAR na faixa (sobreposição, extremos inclusivos)
  if (f.kmIni !== null || f.kmFim !== null) {
    const k0 = Number(a.km_ini), k1 = Number(a.km_fim);
    if (a.km_ini == null || a.km_fim == null || !Number.isFinite(k0) || !Number.isFinite(k1)) return false;
    const lo = Math.min(k0, k1), hi = Math.max(k0, k1);
    if (f.kmIni !== null && hi < f.kmIni) return false;
    if (f.kmFim !== null && lo > f.kmFim) return false;
  }
  // período: a atividade OCORRE entre as datas no cenário corrente (início ≤ fim do período e término ≥ início do período)
  if (f.dataIni || f.dataFim) {
    const r = resultadoAtivo();
    const ra = r && r.atividades[a.id];
    const di = ra ? diaDe(ra.inicio) : null, dt = ra ? diaDe(ra.termino || ra.inicio) : null;
    if (di === null || dt === null) return false;
    if (f.dataIni && dt < diaDe(f.dataIni)) return false;
    if (f.dataFim && di > diaDe(f.dataFim)) return false;
  }
  return true;
}

/** Problemas nos filtros de faixa (km ou período invertidos) — texto para o resumo; vazio se ok. */
export function avisoFiltros() {
  const f = estado.filtros;
  const av = [];
  if (f.kmIni !== null && f.kmFim !== null && f.kmIni > f.kmFim) av.push('km inicial maior que o final');
  if (f.dataIni && f.dataFim && diaDe(f.dataIni) > diaDe(f.dataFim)) av.push('data inicial depois da final');
  return av.join('; ');
}

export function selecionar(id, origem) {
  if (id && !estado.ativ.has(id)) return;
  estado.selecionada = id || null;
  emitir('selecao', { id: estado.selecionada, origem });
}

/** Fração executada na data de status (dados de entrada, não do cenário). */
export function fracaoExecutada(a) {
  if (a.status === 'concluida') return 1;
  if (a.quantidade_total) return Math.min(1, Math.max(0, (a.quantidade_executada || 0) / a.quantidade_total));
  // atividade sem quantidade (duração fixa): mesma regra do backend — percentual_executado / 100
  const p = Number(a.percentual_executado);
  if (Number.isFinite(p)) return Math.min(1, Math.max(0, p / 100));
  return 0;
}

const ORDEM_SERV = ['SUP', 'TER', 'DRE', 'OAE-FUN', 'OAE-MES', 'OAE-SUE', 'SUB', 'DOR', 'GRA', 'LAS', 'SOL', 'SIN'];
/**
 * Atividades em ordem de exibição, agrupadas: [{chave, rotulo, nivel, itens:[atividade]}].
 * Marco inicial -> por lote (segmentos em ordem; atividades do lote sem segmento ao final) -> marcos finais.
 */
export function gruposDeExibicao() {
  const p = estado.projeto;
  const grupos = [];
  const marcos = p.atividades.filter(a => a.tipo !== 'tarefa');
  const marcoIni = marcos.filter(a => a.tipo === 'marco_inicio');
  if (marcoIni.length) grupos.push({ chave: 'ini', rotulo: 'Início', nivel: 0, itens: marcoIni });
  // ordem dos serviços = ordem da lista de serviços da obra (genérico para ferrovia/rodovia/…)
  const ordemObra = (p.servicos || []).map(s => s.id);
  const ordServ = (a) => {
    let i = ordemObra.indexOf(a.servico_id);
    if (i < 0) i = ORDEM_SERV.indexOf(a.servico_id) + (ORDEM_SERV.includes(a.servico_id) ? 0 : 99);
    return i;
  };
  for (const l of p.lotes) {
    grupos.push({ chave: l.id, rotulo: `${l.nome} — km ${l.km_ini}–${l.km_fim} · ${l.construtora}`, nivel: 0, itens: [] });
    for (const s of p.segmentos.filter(s => s.lote_id === l.id)) {
      const itens = p.atividades.filter(a => a.tipo === 'tarefa' && a.segmento_id === s.id)
        .sort((a, b) => (a.oae_id ? 1 : 0) - (b.oae_id ? 1 : 0) || ordServ(a) - ordServ(b));
      grupos.push({ chave: s.id, rotulo: `${s.id} (km ${s.km_ini}–${s.km_fim})`, nivel: 1, itens });
    }
    const doLote = p.atividades.filter(a => a.tipo === 'tarefa' && a.lote_id === l.id && !a.segmento_id);
    const mLote = marcos.filter(a => a.tipo === 'marco_termino' && a.lote_id === l.id);
    const mLoteId = marcos.filter(a => a.tipo === 'marco_termino' && !a.lote_id && a.id.includes(`-${l.id}-`));
    const fech = [...doLote, ...mLote, ...mLoteId];
    if (fech.length) grupos.push({ chave: `${l.id}-fech`, rotulo: `${l.id} — liberação`, nivel: 1, itens: fech });
  }
  const usados = new Set(grupos.flatMap(g => g.itens.map(a => a.id)));
  const resto = p.atividades.filter(a => !usados.has(a.id));
  if (resto.length) grupos.push({ chave: 'fim', rotulo: 'Marcos finais', nivel: 0, itens: resto });
  return grupos;
}
