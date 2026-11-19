// Painel de detalhes da atividade selecionada: memória de cálculo, folgas, dependências.

import { estado, resultadoAtivo, selecionar, nomeServico, fracaoExecutada } from './estado.js';
import { esc, dataBR, num, pillStatus, CENARIO_ROTULO } from './util.js';

let opcoes = {};
export function iniciarDetalhes(op) { opcoes = op || {}; }

function linkAtiv(id, extra = '') {
  return `<span class="link-ativ" data-ir="${esc(id)}">${esc(id)}</span>${extra}`;
}

export function renderDetalhes() {
  const alvos = document.querySelectorAll('[data-detalhes]');
  const id = estado.selecionada;
  let html;
  if (!id || !estado.projeto) {
    html = `<h4>Explore o modelo 4D</h4><p>Selecione uma peça, barra do Gantt ou frente na linha de balanço.</p><p>A ficha conecta <b>elemento → serviço → atividade → quantidade → previsão</b>, com memória de cálculo e fonte da produtividade.</p><p><b>Comece por “Detalhe da ponte”</b> no modo Apresentação para explorar a OAE fictícia em escala local.</p><p class="nota-contexto">Contorno vermelho indica criticidade. Atraso é mostrado no modo “Desvio vs linha de base”. Geometria ilustrativa não é quantitativo aprovado.</p>`;
  } else {
    html = conteudo(id);
  }
  alvos.forEach(el => {
    el.innerHTML = html;
    el.querySelectorAll('[data-ir]').forEach(s => s.addEventListener('click', () => selecionar(s.dataset.ir, 'detalhes')));
    el.querySelectorAll('[data-acao]').forEach(b => b.addEventListener('click', () => {
      if (b.dataset.acao === 'limpar') selecionar(null, 'detalhes');
      else if (opcoes[b.dataset.acao]) opcoes[b.dataset.acao](id);
    }));
  });
}

function conteudo(id) {
  const a = estado.ativ.get(id);
  const res = resultadoAtivo();
  const r = (res && res.atividades[id]) || {};
  const lb = estado.cenarios.linha_base && estado.cenarios.linha_base.atividades[id];
  const mem = r.memoria || {};
  const preds = estado.preds.get(id) || [];
  const succs = estado.succs.get(id) || [];
  const det = r.determinante;
  const fmtRel = (rel, outro) => `${linkAtiv(outro)} <small>${esc(rel.tipo)}${rel.lag ? (rel.lag > 0 ? '+' : '') + rel.lag : '+0'}</small>${outro === det ? ' <span class="pill crit" title="predecessora que determina o início">determinante</span>' : ''}`;
  const temGeo = opcoes.temGeometria ? opcoes.temGeometria(id) : false;
  return `
    <h4>${esc(a.id)} ${r.critica ? '<span class="pill crit">CRÍTICA</span>' : ''}
      ${r.caminho_mais_longo ? '<span class="pill longo" title="Está no caminho mais longo até o término (critério Longest Path, como no P6). Crítica = folga ≤ 0 OU caminho mais longo.">caminho mais longo</span>' : ''}</h4>
    <div style="color:var(--texto-2)">${esc(a.nome)}</div>
    <dl>
      <dt>Serviço</dt><dd>${esc(nomeServico(a.servico_id))}</dd>
      <dt>Lote / seg.</dt><dd>${esc(a.lote_id || '—')} / ${esc(a.segmento_id || '—')}</dd>
      ${a.km_ini != null ? `<dt>Trecho</dt><dd>km ${num(a.km_ini, 1)} – ${num(a.km_fim, 1)}</dd>` : ''}
      <dt>Status</dt><dd>${pillStatus(a.status)}${a.tipo === 'tarefa' ? ` · ${num(fracaoExecutada(a) * 100, 0)}% executado` : ''}</dd>
      ${a.quantidade_total ? `<dt>Quantidade</dt><dd>${num(a.quantidade_executada || 0, 0)} / ${num(a.quantidade_total, 0)} ${esc(a.unidade)}</dd>` : ''}
      ${a.quantidade_total ? `<dt>Saldo físico</dt><dd>${num(Math.max(0, a.quantidade_total - (a.quantidade_executada || 0)), 1)} ${esc(a.unidade)}</dd>` : ''}
      <dt>Origem</dt><dd>Base fictícia · geometria ilustrativa vinculada à atividade; quantidades vêm do dataset, não da malha.</dd>
    </dl>
    <h4>Cenário: ${esc(CENARIO_ROTULO[estado.cenarioAtivo])}</h4>
    <dl>
      <dt>Início</dt><dd>${dataBR(r.inicio)}</dd>
      <dt>Término</dt><dd>${dataBR(r.termino)}</dd>
      <dt>Duração</dt><dd>${r.duracao ?? '—'} dias úteis</dd>
      <dt>Linha de base</dt><dd>${dataBR(lb && lb.inicio)} → ${dataBR(lb && lb.termino)}</dd>
      <dt>Folga total</dt><dd>${r.folga_total ?? '—'} d.u.</dd>
      <dt>Folga livre</dt><dd>${r.folga_livre ?? '—'} d.u.</dd>
      <dt>Motivo do início</dt><dd>${esc(r.motivo_inicio || '—')}</dd>
    </dl>
    <h4>Memória de cálculo</h4>
    <dl>
      <dt>Regra</dt><dd>${esc(mem.regra || '—')}</dd>
      ${mem.quantidade_remanescente != null ? `<dt>Remanescente</dt><dd>${num(mem.quantidade_remanescente, 1)} ${esc(mem.unidade || '')}</dd>` : ''}
      ${mem.produtividade != null ? `<dt>Produtividade</dt><dd>${num(mem.produtividade, 2)} ${esc(mem.unidade || '')}/equipe·dia</dd>` : ''}
      ${mem.produtividade_planejada != null ? `<dt>Planejada</dt><dd>${num(mem.produtividade_planejada, 2)}</dd>` : ''}
      ${mem.fonte_produtividade ? `<dt>Fonte</dt><dd>${esc(mem.fonte_produtividade)}</dd>` : ''}
      ${mem.equipes != null ? `<dt>Equipes</dt><dd>${mem.equipes}</dd>` : ''}
    </dl>
    ${mem.formula ? `<div class="formula mono">${esc(mem.formula)}</div>` : ''}
    <h4>Predecessoras (${preds.length})</h4>
    <div>${preds.length ? preds.map(p => fmtRel(p, p.predecessora)).join('<br>') : '—'}</div>
    <h4 style="margin-top:8px">Sucessoras (${succs.length})</h4>
    <div>${succs.length ? succs.map(s => fmtRel(s, s.sucessora)).join('<br>') : '—'}</div>
    <div class="acoes">
      ${temGeo ? '<button type="button" data-acao="verNo3D">Ver no 3D</button>' : ''}
      <button type="button" data-acao="verNoGantt">Ver no Gantt</button>
      ${mem.regra === 'quantidade' ? '<button type="button" data-acao="simular">Simular esta atividade</button>' : ''}
      <button type="button" data-acao="limpar">Limpar seleção</button>
    </div>`;
}
