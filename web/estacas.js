// Estaca de um km: SEMPRE a da API (/api/referencia/km), que conhece a estaca de origem e as equações
// de estaca da obra. O navegador não calcula estaca (a conta local divergia com origem ≠ 0 ou equação).
// Cache por obra (a troca de obra recarrega a página) e pré-carga dos km das atividades.

import { api } from './api.js';
import { esc } from './util.js';

const cache = new Map();     // chave -> texto da estaca ('—' se a API não respondeu)
const pendentes = new Map(); // chave -> Promise

const chave = (km) => Number(km).toFixed(4);

/** Estaca em cache (texto) ou null. */
export function estacaEmCache(km) {
  return cache.has(chave(km)) ? cache.get(chave(km)) : null;
}

/** Garante a estaca do km no cache; resolve com o texto. */
export function garantirEstaca(km) {
  const k = chave(km);
  if (cache.has(k)) return Promise.resolve(cache.get(k));
  if (pendentes.has(k)) return pendentes.get(k);
  if (!Number.isFinite(Number(km))) return Promise.resolve('—');
  const p = api.referenciaKm(k)
    .then(r => (typeof r.estaca === 'string' ? r.estaca : '—'))
    .catch(() => '—')
    .then(t => { cache.set(k, t); pendentes.delete(k); return t; });
  pendentes.set(k, p);
  return p;
}

/** Pré-carrega as estacas de uma lista de km (sem bloquear a interface). */
export function preCarregarEstacas(kms) {
  const unicos = [...new Set(kms.filter(k => Number.isFinite(Number(k))).map(chave))];
  return Promise.all(unicos.map(k => garantirEstaca(Number(k))));
}

/**
 * HTML da estaca para um tooltip: o texto da API (escapado) ou "consultando…"; quando a API responder,
 * chama `aoChegar` (ex.: redesenhar o tooltip ainda aberto).
 */
export function estacaHTML(km, aoChegar) {
  const t = estacaEmCache(km);
  if (t !== null) return esc(t);
  garantirEstaca(km).then(() => aoChegar && aoChegar());
  return '<i>consultando…</i>';
}
