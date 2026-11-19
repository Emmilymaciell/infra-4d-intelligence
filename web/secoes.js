// Seções transversais esquemáticas por serviço, orientadas a dados (sem three.js — usado também fora do 3D).
//
// Cada estilo é uma lista de prismas {c, wb, wt, h0, t} em metros, antes do exagero:
//   c = deslocamento lateral do eixo, wb/wt = largura da base/topo, h0 = cota da base relativa ao eixo, t = espessura.
// `marcadores: true` desenha pequenos blocos espaçados no km (em vez de faixa contínua).
// `null` = serviço sem representação física no trecho (ex.: liberação/testes do lote) — sem peça.
// Serviço desconhecido NUNCA quebra: recebe uma camada genérica empilhada (ver estiloGenerico).

const C = (c, wb, wt, h0, t) => ({ c, wb, wt, h0, t });

const COMUNS = {
  SUP: { prismas: [C(0, 26, 26, -0.14, 0.12)] },
  DRE: { prismas: [C(-9.2, 1.4, 1.4, -0.1, 0.7), C(9.2, 1.4, 1.4, -0.1, 0.7)] },
  LIB: null,
};

const POR_TIPO = {
  ferrovia: {
    TER: { prismas: [C(0, 17, 12, 0, 1.5)] },
    SUB: { prismas: [C(0, 9.5, 8, 1.5, 0.35)] },
    LAS: { prismas: [C(0, 5.2, 3.4, 1.85, 0.35)] },
    DOR: { prismas: [C(0, 2.8, 2.8, 2.2, 0.14)] },
    GRA: { prismas: [C(-0.8, 0.18, 0.18, 2.34, 0.2), C(0.8, 0.18, 0.18, 2.34, 0.2)] },
    SOL: { prismas: [C(0.8, 0.7, 0.7, 2.34, 0.6)], marcadores: true },
    SIN: null, // sinalização, testes e liberação do lote: atividade de sistema, sem peça física
  },
  // rodovia em pista dupla: plataforma ~26 m (duas pistas + acostamentos), mais larga que a ferrovia
  rodovia: {
    SUP: { prismas: [C(0, 38, 38, -0.14, 0.12)] },
    DRE: { prismas: [C(-15.5, 1.4, 1.4, -0.1, 0.7), C(15.5, 1.4, 1.4, -0.1, 0.7)] },
    TER: { prismas: [C(0, 30, 26, 0, 1.2)] },
    SBB: { prismas: [C(0, 26, 25.2, 1.2, 0.3)] },
    BGS: { prismas: [C(0, 25.2, 24.4, 1.5, 0.2)] },
    IMP: { prismas: [C(0, 24.4, 24.4, 1.7, 0.05)] },
    CBU: { prismas: [C(0, 24.4, 23.8, 1.75, 0.12)] },
    SHV: { prismas: [C(-11.4, 0.25, 0.25, 1.87, 0.04), C(-3.7, 0.25, 0.25, 1.87, 0.04), C(-0.3, 0.2, 0.2, 1.87, 0.04),
      C(0.3, 0.2, 0.2, 1.87, 0.04), C(3.7, 0.25, 0.25, 1.87, 0.04), C(11.4, 0.25, 0.25, 1.87, 0.04)] },
    SVV: { prismas: [C(-14, 0.5, 0.5, 1.2, 2.6), C(14, 0.5, 0.5, 1.2, 2.6)], marcadores: true },
    DEF: { prismas: [C(-12.6, 0.35, 0.35, 1.87, 0.75), C(12.6, 0.35, 0.35, 1.87, 0.75)] },
  },
};

// sinônimos prováveis de outras bases
const ALIAS = {
  rodovia: { SBL: 'SBB', SUBBASE: 'SBB', BAS: 'BGS', CBUQ: 'CBU', REV: 'CBU', SIN: 'SHV' },
  ferrovia: {},
};

/** Tabela de seções do tipo DECLARADO; tipo ausente ou desconhecido → vazia (nada de assumir ferrovia). */
function tabelaDoTipo(tipo) {
  return (typeof tipo === 'string' && Object.prototype.hasOwnProperty.call(POR_TIPO, tipo)) ? POR_TIPO[tipo] : {};
}

/** Estilo conhecido para (tipo de obra, serviço): objeto, `null` (sem peça) ou `undefined` (desconhecido).
 * Sem tipo declarado, só os estilos COMUNS valem; o resto vira camada genérica. */
export function estiloConhecido(tipo, servicoId) {
  const tab = tabelaDoTipo(tipo);
  const al = (typeof tipo === 'string' && Object.prototype.hasOwnProperty.call(ALIAS, tipo)) ? ALIAS[tipo] : {};
  const id = al[servicoId] || servicoId;
  if (id in tab) return tab[id];
  if (id in COMUNS) return COMUNS[id];
  return undefined;
}

/** Topo (cota relativa) mais alto entre os estilos conhecidos do tipo — base para empilhar os genéricos. */
function topoConhecido(tipo) {
  let topo = 0;
  for (const e of Object.values({ ...COMUNS, ...tabelaDoTipo(tipo) })) {
    if (!e) continue;
    for (const p of e.prismas) if (!e.marcadores) topo = Math.max(topo, p.h0 + p.t);
  }
  return topo;
}

/**
 * Plano de estilos de uma obra: {estilos: Map(servico_id -> estilo|null), genericos: [ids sem estilo]}.
 * Desconhecidos são ordenados pelo início mais cedo na linha de base (aproxima a ordem topológica da rede)
 * e empilhados acima das camadas conhecidas, cada um uma faixa estreita e fina.
 */
export function planoDeEstilos(projeto) {
  // tipo DECLARADO (obra.tipo ou meta.tipo_obra); sem ele, null: nenhuma seção específica é escolhida por padrão
  const tipo = (projeto.obra && projeto.obra.tipo) || (projeto.meta && projeto.meta.tipo_obra) || null;
  const estilos = new Map();
  const inicio = new Map();
  for (const a of projeto.atividades) {
    if (a.tipo !== 'tarefa' || !a.servico_id || a.oae_id) continue;
    const t = a.inicio_lb || '9999';
    if (!inicio.has(a.servico_id) || t < inicio.get(a.servico_id)) inicio.set(a.servico_id, t);
  }
  const genericos = [];
  for (const id of inicio.keys()) {
    const e = estiloConhecido(tipo, id);
    if (e === undefined) genericos.push(id);
    else estilos.set(id, e);
  }
  genericos.sort((a, b) => inicio.get(a).localeCompare(inicio.get(b)) || a.localeCompare(b));
  let h = topoConhecido(tipo) + 0.15;
  genericos.forEach((id, i) => {
    const w = Math.max(2.5, 7 - i * 0.8);
    estilos.set(id, { prismas: [C(0, w, w, h, 0.22)], generico: true });
    h += 0.3;
  });
  return { tipo, estilos, genericos };
}

/** A atividade tem (ou terá) geometria no 3D? */
export function temGeometriaPlano(plano, a) {
  if (!a || a.tipo !== 'tarefa' || a.km_ini == null || a.km_fim == null) return false;
  if (a.oae_id) return true;
  return !!plano.estilos.get(a.servico_id);
}
