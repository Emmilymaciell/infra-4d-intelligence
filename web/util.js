// Utilitários: datas, formatação, SVG e DOM.

const DIA = 86400000;

const RE_ISO = /^(\d{4})-(\d{2})-(\d{2})$/;

/** 'AAAA-MM-DD' -> número de dias desde 1970-01-01 (UTC, sem fuso). Texto fora do formato -> null. */
export function diaDe(iso) {
  const m = RE_ISO.exec(typeof iso === 'string' ? iso : '');
  if (!m) return null;
  return Math.round(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])) / DIA);
}

/** número de dias -> 'AAAA-MM-DD' (null se não for número finito). */
export function isoDe(dia) {
  if (!Number.isFinite(dia)) return null;
  return new Date(dia * DIA).toISOString().slice(0, 10);
}

/**
 * 'AAAA-MM-DD' -> 'DD/MM/AAAA'. VALIDA o formato: qualquer outro texto vira '—' (a saída só contém
 * dígitos e '/', portanto é segura em HTML — dado da API chega cru e pode conter marcação).
 */
export function dataBR(iso) {
  if (typeof iso !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return '—';
  const [a, m, d] = iso.split('-');
  return `${d}/${m}/${a}`;
}

const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
export function mesCurto(dia) {
  const d = new Date(dia * DIA);
  return `${MESES[d.getUTCMonth()]}/${String(d.getUTCFullYear()).slice(2)}`;
}
export function primeiroDiaMes(dia) {
  const d = new Date(dia * DIA);
  return Math.round(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1) / DIA);
}
export function proximoMes(dia) {
  const d = new Date(dia * DIA);
  return Math.round(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1) / DIA);
}

export function num(v, casas = 0) {
  // só números finitos: texto qualquer (inclusive marcação vinda da API) vira '—' — saída segura em HTML
  if (v === null || v === undefined || v === '' || !Number.isFinite(Number(v))) return '—';
  return Number(v).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
}
export function pct(v, casas = 1) {
  return v === null || v === undefined ? '—' : `${num(v, casas)}%`;
}
export function sinal(v) {
  if (v === null || v === undefined) return '—';
  return v > 0 ? `+${v}` : `${v}`;
}

/** Escapa texto para inserção em HTML. */
export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

const SVGNS = 'http://www.w3.org/2000/svg';
/** Cria elemento SVG com atributos. */
export function svg(tag, attrs = {}, pai = null) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v !== null && v !== undefined) el.setAttribute(k, v);
  }
  if (pai) pai.appendChild(el);
  return el;
}

export function debounce(fn, ms) {
  let t = null;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

// Tooltip único compartilhado pelos gráficos.
let tip = null;
export function mostrarTooltip(html, ev) {
  if (!tip) {
    tip = document.createElement('div');
    tip.className = 'tooltip';
    document.body.appendChild(tip);
  }
  tip.innerHTML = html;
  tip.hidden = false;
  const x = Math.min(ev.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
  const y = Math.min(ev.clientY + 14, window.innerHeight - tip.offsetHeight - 8);
  tip.style.left = `${x}px`;
  tip.style.top = `${y}px`;
}
export function esconderTooltip() {
  if (tip) tip.hidden = true;
}

export const STATUS_ROTULO = {
  concluida: 'Concluída', em_andamento: 'Em andamento', nao_iniciada: 'Não iniciada',
};
export function pillStatus(s) {
  const cls = s === 'concluida' ? 'ok' : s === 'em_andamento' ? 'and' : 'ni';
  return `<span class="pill ${cls}">${esc(STATUS_ROTULO[s] || s || '—')}</span>`;
}

export const CENARIO_ROTULO = {
  linha_base: 'Linha de base', construtora: 'Construtora', independente: 'Independente', simulado: 'Simulado',
};

/**
 * Selo "não segue a simulação" para respostas que trazem `simulacao_do_usuario` (texto do motivo).
 * Sem o campo: nada. Texto começando por "não" → "não segue a simulação"; outro → "segue a simulação".
 */
export function seloSimulacao(d) {
  const t = d && d.simulacao_do_usuario;
  if (typeof t !== 'string' || !t.trim()) return '';
  const nao = /^n[ãa]o\b/i.test(t.trim());
  return `<p class="selo-sim" data-selo-sim="${nao ? 'nao' : 'sim'}"><span class="pill ${nao ? 'ni' : 'and'}">${nao ? 'não segue a simulação' : 'segue a simulação'}</span>
    <small>${esc(t)}</small></p>`;
}