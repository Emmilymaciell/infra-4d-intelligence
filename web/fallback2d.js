// Leitura e seleção 2D quando WebGL não está disponível; sem dependência de three.js.
import { esc, dataBR } from './util.js';

export function renderFallback2D(container, projeto, resultado, aoSelecionar) {
  const atividades = projeto.atividades.filter(a => a.tipo === 'tarefa' && a.km_ini != null && a.km_fim != null);
  const servicos = [...new Set(atividades.map(a => a.servico_id))];
  const fim = Math.max(1, ...atividades.map(a => a.km_fim));
  const w = 960, h = Math.max(200, servicos.length * 26 + 45), x = km => 95 + km / fim * 830;
  const svg = `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Corredor 2D por serviço e quilômetro">
    <rect width="${w}" height="${h}" fill="#f7f9f8"/>
    ${servicos.map((s, i) => `<text x="8" y="${44 + i * 26}" font-size="12" fill="#263b50">${esc(s)}</text>`).join('')}
    ${Array.from({ length: 7 }, (_, i) => `<text x="${x(fim * i / 6)}" y="20" font-size="12" fill="#52687b">km ${Math.round(fim * i / 6)}</text>`).join('')}
    ${atividades.map(a => {
      const r = resultado && resultado.atividades[a.id], i = servicos.indexOf(a.servico_id);
      const cor = a.status === 'concluida' ? '#2b9348' : a.status === 'em_andamento' ? '#e0a020' : '#9aa3ad';
      return `<rect data-2d-id="${esc(a.id)}" x="${x(a.km_ini)}" y="${28 + i * 26}" width="${Math.max(3, x(a.km_fim) - x(a.km_ini) - 1)}" height="19" fill="${cor}" stroke="${r && r.critica ? '#d62d2d' : '#fff'}" stroke-width="${r && r.critica ? 2 : 1}" tabindex="0" role="button" aria-label="${esc(a.id)}"><title>${esc(a.id)} · ${esc(a.nome)} · término ${dataBR(r && r.termino)}</title></rect>`;
    }).join('')}</svg>`;
  const wrap = document.createElement('div'); wrap.className = 'fallback-2d';
  wrap.innerHTML = `<h3>Corredor 2D · alternativa sem WebGL</h3><p>Avanço na data de status. Verde: concluído; âmbar: em andamento; cinza: não iniciado; contorno vermelho: crítico. Clique para consultar a memória e abrir o Gantt.</p>${svg}`;
  container.appendChild(wrap);
  wrap.querySelectorAll('[data-2d-id]').forEach(el => {
    el.addEventListener('click', () => aoSelecionar(el.dataset['2dId'] || el.getAttribute('data-2d-id')));
    el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); aoSelecionar(el.getAttribute('data-2d-id')); } });
  });
}
