// Simulação "e se": produtividade/equipes -> duração -> rede (CPM) -> término.

import { estado, selecionar, nomeServico } from './estado.js';
import { api } from './api.js';
import { esc, num, dataBR } from './util.js';
import { indiceHTML } from './painel.js';

let raiz = null;
let opcoes = {};
let modo = 'atividade';
let msg = null; // {tipo: 'erro'|'ok', texto}
let ocupado = false;

// Exemplos fixos da ferrovia de demonstração (usados quando essas atividades existem na obra).
const EXEMPLOS_FERROVIA = [
  { rotulo: 'Exemplo: terraplenagem L3-S04 (crítica) a 1.500 m³/equipe·dia',
    nota: 'Atividade no caminho crítico: cada dia a mais empurra o término.',
    ajuste: { atividade_id: 'L3-S04-TER', produtividade: 1500, equipes: 2 } },
  { rotulo: 'Exemplo: lastro L2-S04 (com folga) a 250 m³/equipe·dia',
    nota: 'Atividade com folga: o atraso é absorvido e o término não muda.',
    ajuste: { atividade_id: 'L2-S04-LAS', produtividade: 250, equipes: 1 } },
  { rotulo: 'Exemplo: reforço de +1 equipe na terraplenagem L3-S04',
    nota: 'Mais equipes no caminho crítico antecipam o término — até outra cadeia virar crítica.',
    ajuste: { atividade_id: 'L3-S04-TER', equipes: 3 } },
];

/**
 * Exemplos para a obra atual: os fixos da ferrovia, se existirem; senão, gerados dos dados:
 * a crítica não concluída de maior duração (−20% de produtividade), a de maior folga (−40%) e +1 equipe na crítica.
 */
function exemplos() {
  const ids = new Set(ajustaveis().map(a => a.id));
  if (EXEMPLOS_FERROVIA.every(e => ids.has(e.ajuste.atividade_id))) return EXEMPLOS_FERROVIA;
  const ind = estado.cenarios.independente;
  if (!ind) return [];
  const comRes = ajustaveis().map(a => ({ a, r: ind.atividades[a.id] })).filter(x => x.r && x.r.memoria && x.r.memoria.produtividade);
  const crit = comRes.filter(x => x.r.critica).sort((x, y) => (y.r.duracao || 0) - (x.r.duracao || 0))[0];
  const folga = comRes.filter(x => !x.r.critica && x.r.folga_total > 0).sort((x, y) => y.r.folga_total - x.r.folga_total)[0];
  const arred = (v) => Number(v.toPrecision(3));
  const out = [];
  if (crit) {
    const p = arred(crit.r.memoria.produtividade * 0.8);
    out.push({ rotulo: `Exemplo: ${nomeServico(crit.a.servico_id).toLowerCase()} ${crit.a.id} (crítica) a ${num(p, 2)} ${crit.a.unidade}/equipe·dia`,
      nota: 'Atividade no caminho crítico: cada dia a mais empurra o término.',
      ajuste: { atividade_id: crit.a.id, produtividade: p } });
  }
  if (folga) {
    const p = arred(folga.r.memoria.produtividade * 0.6);
    out.push({ rotulo: `Exemplo: ${nomeServico(folga.a.servico_id).toLowerCase()} ${folga.a.id} (folga ${folga.r.folga_total}) a ${num(p, 2)} ${folga.a.unidade}/equipe·dia`,
      nota: 'Atividade com folga: o atraso é absorvido enquanto couber na folga.',
      ajuste: { atividade_id: folga.a.id, produtividade: p } });
  }
  if (crit) {
    const eq = (crit.r.memoria.equipes || crit.a.equipes || 1) + 1;
    out.push({ rotulo: `Exemplo: reforço para ${eq} equipes em ${crit.a.id}`,
      nota: 'Mais equipes no caminho crítico antecipam o término — até outra cadeia virar crítica.',
      ajuste: { atividade_id: crit.a.id, equipes: Math.min(20, eq) } });
  }
  return out;
}

export function iniciarSimulacao(el, op) {
  raiz = el;
  opcoes = op || {};
}

/** Atividades ajustáveis: por quantidade e ainda não concluídas. */
function ajustaveis() {
  return estado.projeto.atividades.filter(a => a.tipo === 'tarefa' && a.quantidade_total && a.status !== 'concluida');
}

function servicosAjustaveis() {
  const ids = [...new Set(ajustaveis().map(a => a.servico_id))];
  return ids.map(id => ({ id, nome: nomeServico(id) }));
}

/** Pré-seleciona uma atividade (chamado pelo painel de detalhes). */
export function prepararAtividade(id) {
  modo = 'atividade';
  msg = null;
  renderSimulacao();
  const sel = raiz.querySelector('#s-ativ');
  if (sel && [...sel.options].some(o => o.value === id)) {
    sel.value = id;
    atualizarAtual();
  }
}

export function renderSimulacao() {
  if (!raiz || !estado.projeto) return;
  const ind = estado.cenarios.independente;
  const ativs = ajustaveis();
  const servs = servicosAjustaveis();
  const valAtiv = raiz.querySelector('#s-ativ')?.value || (estado.selecionada && ativs.some(a => a.id === estado.selecionada) ? estado.selecionada : (exemplos()[0]?.ajuste.atividade_id || ativs[0]?.id));
  const valServ = raiz.querySelector('#s-serv')?.value || 'TER';
  const valLote = raiz.querySelector('#s-lote')?.value || estado.projeto.lotes[estado.projeto.lotes.length - 1]?.id;
  const acumular = raiz.querySelector('#s-acumular')?.checked || false;
  const sim = estado.simulacao;
  const ajustes = (sim && sim.ajustes) || [];
  const listaEx = exemplos();

  raiz.innerHTML = `
    <div class="bloco sim-form">
      <h2>Simulação “e se”</h2>
      <p style="margin:0 0 6px;color:var(--texto-2);font-size:13px">Altere produtividade e/ou equipes. O motor recalcula
        <b>duração = remanescente ÷ (produtividade × equipes)</b>, propaga pela rede (CPM) e mostra o novo término.
        Base de comparação: previsão <b>independente</b>.</p>
      <div class="modos">
        <label class="chk"><input type="radio" name="s-modo" value="atividade" ${modo === 'atividade' ? 'checked' : ''}> Atividade específica</label>
        <label class="chk"><input type="radio" name="s-modo" value="servico" ${modo === 'servico' ? 'checked' : ''}> Serviço + lote</label>
      </div>
      ${modo === 'atividade' ? `
        <label for="s-ativ">Atividade (só as não concluídas, medidas por quantidade)</label>
        <select id="s-ativ">${ativs.map(a => {
          const r = ind && ind.atividades[a.id];
          const info = r ? (r.critica ? ` · CRÍTICA${r.caminho_mais_longo ? ' · caminho mais longo' : ''}` : ` · folga ${r.folga_total}`) : '';
          return `<option value="${esc(a.id)}" ${a.id === valAtiv ? 'selected' : ''}>${esc(a.id)} — ${esc(nomeServico(a.servico_id))}${info}</option>`;
        }).join('')}</select>` : `
        <div class="linha2">
          <div><label for="s-serv">Serviço</label><select id="s-serv">${servs.map(s => `<option value="${esc(s.id)}" ${s.id === valServ ? 'selected' : ''}>${esc(s.id)} — ${esc(s.nome)}</option>`).join('')}</select></div>
          <div><label for="s-lote">Lote</label><select id="s-lote">${estado.projeto.lotes.map(l => `<option value="${esc(l.id)}" ${l.id === valLote ? 'selected' : ''}>${esc(l.id)}</option>`).join('')}</select></div>
        </div>`}
      <div class="sim-atual" id="s-atual"></div>
      <div class="linha2">
        <div><label for="s-prod">Nova produtividade <small id="s-unid"></small></label><input type="number" id="s-prod" min="0" step="any" placeholder="manter"></div>
        <div><label for="s-eq">Equipes</label><input type="number" id="s-eq" min="1" max="20" step="1" placeholder="manter"></div>
      </div>
      <label class="chk" style="margin-top:8px"><input type="checkbox" id="s-acumular" ${acumular ? 'checked' : ''}> Somar aos ajustes já ativos</label>
      <div class="sim-botoes">
        <button type="button" class="primario" id="s-rodar" ${ocupado ? 'disabled' : ''}>Recalcular</button>
        <button type="button" id="s-limpar" ${ocupado || !ajustes.length ? 'disabled' : ''}>Limpar simulação</button>
      </div>
      ${msg ? `<p class="${msg.tipo === 'erro' ? 'erro' : ''}" style="margin-top:10px">${esc(msg.texto)}</p>` : ''}
      <div class="exemplos">
        <b style="font-size:13px">Atalhos de demonstração</b>
        ${listaEx.map((e, i) => `<button type="button" data-ex="${i}" title="${esc(e.nota)}" ${ocupado ? 'disabled' : ''}>${esc(e.rotulo)}<br><small style="color:var(--texto-3)">${esc(e.nota)}</small></button>`).join('')}
      </div>
      <h3>Ajustes ativos (${ajustes.length})</h3>
      <div class="sim-ajustes">${ajustes.length ? ajustes.map(descreverAjuste).map(t => `<div>• ${esc(t)}</div>`).join('') : 'Nenhum — o cenário simulado é igual ao independente.'}</div>
      ${salvosHTML(ajustes)}
    </div>
    <div class="bloco sim-res">${resultadoHTML()}</div>`;

  raiz.querySelectorAll('input[name=s-modo]').forEach(r => r.addEventListener('change', () => { modo = r.value; renderSimulacao(); }));
  ['#s-ativ', '#s-serv', '#s-lote'].forEach(s => raiz.querySelector(s)?.addEventListener('change', atualizarAtual));
  raiz.querySelector('#s-rodar').addEventListener('click', () => rodar(ajusteDoFormulario()));
  raiz.querySelector('#s-limpar').addEventListener('click', limpar);
  raiz.querySelector('#s-salvar')?.addEventListener('click', () => salvar(ajustes));
  raiz.querySelectorAll('[data-reabrir]').forEach(b => b.addEventListener('click', () => reabrir(b.dataset.reabrir)));
  raiz.querySelector('#s-reaplicar')?.addEventListener('click', reaplicar);
  raiz.querySelectorAll('[data-ex]').forEach(b => b.addEventListener('click', () => {
    const ex = listaEx[Number(b.dataset.ex)];
    modo = 'atividade';
    rodar({ ...ex.ajuste }, true);
  }));
  raiz.querySelectorAll('[data-ir]').forEach(s => s.addEventListener('click', () => {
    selecionar(s.dataset.ir, 'sim');
    if (opcoes.irPara) opcoes.irPara('cronograma');
  }));
  atualizarAtual();
}

function descreverAjuste(a) {
  const alvo = a.atividade_id ? a.atividade_id : `${a.servico_id} em ${a.lote_id || 'todos os lotes'}`;
  const partes = [];
  if (a.produtividade != null) partes.push(`produtividade ${num(a.produtividade, 2)}`);
  if (a.equipes != null) partes.push(`${a.equipes} equipe(s)`);
  return `${alvo}: ${partes.join(', ') || 'sem alteração'}`;
}

function atualizarAtual() {
  const box = raiz.querySelector('#s-atual');
  if (!box) return;
  const ind = estado.cenarios.independente;
  const unid = raiz.querySelector('#s-unid');
  if (modo === 'atividade') {
    const id = raiz.querySelector('#s-ativ')?.value;
    const a = estado.ativ.get(id);
    const r = ind && ind.atividades[id];
    if (!a || !r) { box.innerHTML = '—'; return; }
    const m = r.memoria || {};
    const indice = m.produtividade && m.produtividade_planejada ? m.produtividade / m.produtividade_planejada : null;
    unid.textContent = `(${a.unidade}/equipe·dia)`;
    box.innerHTML = `<dl>
      <dt>Planejada</dt><dd>${num(m.produtividade_planejada ?? a.produtividade_planejada, 2)} ${esc(a.unidade)}/equipe·dia</dd>
      <dt>Usada (independente)</dt><dd>${num(m.produtividade, 2)} ${indiceHTML(indice)}</dd>
      <dt>Fonte</dt><dd>${esc(m.fonte_produtividade || '—')}</dd>
      <dt>Equipes</dt><dd>${m.equipes ?? a.equipes}</dd>
      <dt>Remanescente</dt><dd>${num(m.quantidade_remanescente, 1)} ${esc(a.unidade)}</dd>
      <dt>Duração / folga</dt><dd>${r.duracao} d.u. · folga ${r.folga_total ?? '—'} ${r.critica ? '<span class="pill crit">crítica</span>' : ''}
        ${r.caminho_mais_longo ? '<span class="pill longo" title="No caminho mais longo até o término (Longest Path)">caminho mais longo</span>' : ''}</dd>
    </dl>${m.formula ? `<div class="mono" style="margin-top:4px">${esc(m.formula)}</div>` : ''}`;
  } else {
    const s = raiz.querySelector('#s-serv')?.value;
    const l = raiz.querySelector('#s-lote')?.value;
    const linha = (estado.painelGeral?.produtividades || []).find(x => x.servico_id === s && x.lote_id === l);
    const alvo = ajustaveis().filter(a => a.servico_id === s && a.lote_id === l);
    const eq = [...new Set(alvo.map(a => a.equipes))];
    unid.textContent = linha ? `(${linha.unidade}/equipe·dia)` : '';
    box.innerHTML = `<dl>
      <dt>Planejada</dt><dd>${linha ? `${num(linha.planejada, 2)} ${esc(linha.unidade)}/equipe·dia` : '—'}</dd>
      <dt>Efetiva medida</dt><dd>${linha && linha.efetiva != null ? `${num(linha.efetiva, 2)} ${indiceHTML(linha.indice)} <small>(${linha.boletins} boletins)</small>` : 'sem medição'}</dd>
      <dt>Equipes atuais</dt><dd>${eq.length ? eq.join(' / ') : '—'}</dd>
      <dt>Atividades afetadas</dt><dd>${alvo.length ? alvo.map(a => esc(a.id)).join(', ') : '<b style="color:var(--critico)">nenhuma não concluída</b>'}</dd>
    </dl>`;
  }
}

function ajusteDoFormulario() {
  const prod = raiz.querySelector('#s-prod').value;
  const eq = raiz.querySelector('#s-eq').value;
  const aj = {};
  if (modo === 'atividade') aj.atividade_id = raiz.querySelector('#s-ativ').value;
  else { aj.servico_id = raiz.querySelector('#s-serv').value; aj.lote_id = raiz.querySelector('#s-lote').value; }
  if (prod !== '') aj.produtividade = Number(prod);
  if (eq !== '') aj.equipes = Number(eq);
  return aj;
}

async function rodar(ajuste, ehExemplo = false) {
  if (ajuste.produtividade == null && ajuste.equipes == null) {
    msg = { tipo: 'erro', texto: 'Informe uma nova produtividade e/ou um número de equipes.' };
    renderSimulacao();
    return;
  }
  // limites (produtividade > 0, equipes 1..20) são validados pela API, que responde 422 com o motivo
  const acumular = !ehExemplo && raiz.querySelector('#s-acumular')?.checked;
  const anteriores = acumular ? ((estado.simulacao && estado.simulacao.ajustes) || []).map(limparNulos) : [];
  ocupado = true;
  msg = { tipo: 'ok', texto: 'Recalculando a rede…' };
  renderSimulacao();
  try {
    estado.simulacao = await api.simular([...anteriores, ajuste]);
    msg = null;
    if (opcoes.aposMudanca) await opcoes.aposMudanca(true);
  } catch (e) {
    msg = { tipo: 'erro', texto: `Simulação rejeitada: ${e.message}` };
  } finally {
    ocupado = false;
    renderSimulacao();
  }
}

function limparNulos(a) {
  return Object.fromEntries(Object.entries(a).filter(([, v]) => v !== null && v !== undefined));
}

async function limpar() {
  ocupado = true;
  renderSimulacao();
  try {
    estado.simulacao = await api.limparSimulacao();
    msg = { tipo: 'ok', texto: 'Simulação limpa: o cenário simulado voltou a ser igual ao independente.' };
    if (opcoes.aposMudanca) await opcoes.aposMudanca(false);
  } catch (e) {
    msg = { tipo: 'erro', texto: `Não foi possível limpar: ${e.message}` };
  } finally {
    ocupado = false;
    renderSimulacao();
  }
}

/** Atividades marcadas como caminho mais longo (Longest Path) no cenário, na ordem de início. */
function caminhoMaisLongo(cenario) {
  const r = estado.cenarios[cenario];
  if (!r) return [];
  return Object.values(r.atividades).filter(x => x.caminho_mais_longo)
    .sort((a, b) => (a.inicio || '').localeCompare(b.inicio || '')).map(x => x.id);
}

function resultadoHTML() {
  const sim = estado.simulacao;
  if (!sim) return '<p class="vazio">Carregando estado da simulação…</p>';
  const c = sim.comparacao;
  // resposta incompleta da API: mensagem legível em vez de exceção dentro do render
  if (!Array.isArray(sim.ajustes) || !c || typeof c !== 'object') {
    return `<h2>Por que o término mudou?</h2><p class="erro" id="s-incompleto">Resposta incompleta da API de simulação
      (faltam ${!Array.isArray(sim.ajustes) ? 'ajustes' : 'comparacao'}). Recarregue a página; se persistir, a versão da API não corresponde à interface.</p>`;
  }
  if (!sim.ajustes.length) {
    return `<h2>Por que o término mudou?</h2>
      <p class="vazio">Nenhuma simulação ativa. Escolha uma atividade (ou serviço + lote), informe nova produtividade e/ou equipes e clique em <b>Recalcular</b> — ou use um dos atalhos de demonstração.</p>
      <p style="color:var(--texto-2);font-size:13px">Término da previsão independente: <b>${dataBR(c.termino_ref)}</b>.</p>`;
  }
  const d = c.delta_dias_corridos;
  const cls = d > 0 ? 'pior' : d < 0 ? 'melhor' : '';
  const texto = d > 0 ? 'mais tarde' : d < 0 ? 'mais cedo' : 'sem mudança';
  const chips = (ids, cl) => ids.length ? `<div class="chips">${ids.map(i => `<span class="chip ${cl}" data-ir="${esc(i)}">${esc(i)}</span>`).join('')}</div>` : '<span style="color:var(--texto-3)">nenhuma</span>';
  const alt = c.duracoes_alteradas || [];
  return `
    <h2>Por que o término mudou?</h2>
    <div style="display:flex;gap:28px;align-items:flex-end;flex-wrap:wrap">
      <div><div style="color:var(--texto-2);font-size:12px">Independente → simulado</div>
        <div style="font-size:16px">${dataBR(c.termino_ref)} → <b>${dataBR(c.termino_alvo)}</b></div></div>
      <div><div class="delta-grande ${cls}">${d > 0 ? '+' : ''}${d} dias corridos</div>
        <div style="color:var(--texto-2)">${c.delta_dias_uteis > 0 ? '+' : ''}${c.delta_dias_uteis} dias úteis · ${texto}</div></div>
      <div><div style="color:var(--texto-2);font-size:12px">Atividades deslocadas</div><div style="font-size:18px;font-weight:600">${Array.isArray(c.atividades_deslocadas) ? c.atividades_deslocadas.length : (c.atividades_deslocadas ?? '—')}</div></div>
    </div>
    <h3>Explicação, passo a passo</h3>
    <ol>${(c.explicacao || []).map(t => `<li>${esc(t)}</li>`).join('')}</ol>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
      <div><h3>Entraram no caminho crítico</h3>${chips(c.entraram_no_caminho_critico || [], 'ent')}</div>
      <div><h3>Saíram do caminho crítico</h3>${chips(c.sairam_do_caminho_critico || [], 'sai')}</div>
    </div>
    <h3>Caminho mais longo no cenário simulado <span class="pill longo">caminho mais longo</span></h3>
    ${chips(caminhoMaisLongo('simulado'), '')}
    ${alt.length ? `<h3>Durações alteradas</h3><div style="max-height:260px;overflow:auto"><table class="tab"><thead><tr>
      <th>Atividade</th><th class="num">Antes</th><th class="num">Depois</th><th class="num">Δ</th><th class="num">Folga antes</th><th>Crítica</th></tr></thead><tbody>
      ${alt.map(x => `<tr><td><span class="link-ativ" data-ir="${esc(x.id)}">${esc(x.id)}</span></td><td class="num">${x.duracao_antes}</td><td class="num">${x.duracao_depois}</td>
        <td class="num"><b>${x.delta_duracao > 0 ? '+' : ''}${x.delta_duracao}</b></td><td class="num">${x.folga_total_antes ?? '—'}</td>
        <td>${x.critica_antes ? 'sim' : 'não'} → ${x.critica_depois ? 'sim' : 'não'}</td></tr>`).join('')}</tbody></table></div>` : ''}
    <p style="font-size:12px;color:var(--texto-3)">O Gantt, o modelo 3D/4D e o painel passaram a mostrar o cenário <b>simulado</b>. Durações em dias úteis do calendário de cada atividade.</p>`;
}

// ---------------- ganchos para a apresentação guiada (tour.js) ----------------
/** Exemplos disponíveis para a obra atual (fixos da ferrovia ou gerados dos dados). */
export function exemplosSimulacao() { return exemplos(); }

/** Aplica o exemplo i (substitui ajustes anteriores) e devolve {exemplo, simulacao} — ou {erro}. */
export async function aplicarExemplo(i) {
  const ex = exemplos()[i];
  if (!ex) return { erro: 'exemplo indisponível nesta obra' };
  modo = 'atividade';
  await rodar({ ...ex.ajuste }, true);
  if (msg && msg.tipo === 'erro') return { erro: msg.texto };
  return { exemplo: ex, simulacao: estado.simulacao };
}

/** Limpa a simulação (mesmo fluxo do botão "Limpar simulação"). */
export async function limparSimulacaoExterna() { await limpar(); }
// ---------------- cenários salvos (persistência no servidor; reabrir confere a reprodução) ----------------
let salvos = {};       // {carregando|dados|erro}
let reaberto = null;   // resposta de /cenarios-salvos/{id}
let msgSalvos = null;  // {erro?, texto}

function carregarSalvos(forcar = false) {
  if (!forcar && (salvos.dados || salvos.erro || salvos.carregando)) return;
  salvos = { carregando: true };
  api.cenariosSalvos().then(d => { salvos = { dados: d }; }).catch(e => { salvos = { erro: e.message || String(e) }; })
    .finally(() => renderSimulacao());
}

function salvosHTML(ajustes) {
  carregarSalvos();
  const lista = (salvos.dados && salvos.dados.cenarios) || [];
  const r = reaberto;
  const conf = r && r.conferencia;
  return `<h3>Cenários salvos</h3>
    <div class="linha2"><div><label for="s-nome-salvar">Nome</label><input type="text" id="s-nome-salvar" maxlength="80" placeholder="ex.: reforço TER L3"></div>
      <div style="align-self:end"><button type="button" id="s-salvar" ${!ajustes.length || ocupado ? 'disabled' : ''}>Salvar a simulação ativa</button></div></div>
    ${msgSalvos ? `<p class="${msgSalvos.erro ? 'erro' : ''}" id="s-salvos-msg" style="font-size:12.5px">${esc(msgSalvos.texto)}</p>` : ''}
    ${salvos.carregando ? '<p class="vazio">Carregando cenários salvos…</p>' : salvos.erro ? `<p class="erro">Cenários salvos indisponíveis: ${esc(salvos.erro)}</p>`
      : lista.length ? `<table class="tab" id="s-salvos-tab"><thead><tr><th>Nome</th><th>Término</th><th class="num">Ajustes</th><th>Salvo em</th><th></th></tr></thead><tbody>
        ${lista.map(c => `<tr><td>${esc(c.nome)}</td><td>${dataBR(c.termino)}</td><td class="num">${num((c.ajustes || []).length, 0)}</td>
          <td><small>${esc(String(c.criado_em || '').replace('T', ' ').slice(0, 16))}</small></td>
          <td><button type="button" data-reabrir="${esc(c.id)}">Reabrir</button></td></tr>`).join('')}</tbody></table>`
        : '<p style="font-size:12.5px;color:var(--texto-2)">Nenhum cenário salvo nesta obra.</p>'}
    ${r ? `<div class="sim-atual" id="s-reaberto"><b>${esc(r.nome)}</b>: término gravado ${dataBR(r.termino)}${conf ? ` · recalculado agora ${dataBR(conf.termino_recalculado)}
        · ${conf.reproduz_identico ? '<span class="indice bom">✓ reproduz idêntico</span>' : '<span class="indice ruim">▼ difere do gravado</span>'}
        <br><small>${esc(conf.nota || '')}</small>` : ''}
        <div class="sim-botoes"><button type="button" class="primario" id="s-reaplicar" ${ocupado ? 'disabled' : ''}>Aplicar estes ${num((r.ajustes || []).length, 0)} ajustes como simulação</button></div></div>` : ''}`;
}

const limparNulosSalvo = (a) => Object.fromEntries(Object.entries(a || {}).filter(([, v]) => v !== null && v !== undefined));

async function salvar(ajustes) {
  const nome = (raiz.querySelector('#s-nome-salvar')?.value || '').trim();
  if (!nome) { msgSalvos = { erro: true, texto: 'Dê um nome ao cenário antes de salvar.' }; renderSimulacao(); return; }
  try {
    const r = await api.salvarCenario(nome, ajustes.map(limparNulosSalvo));
    // texto exibido via esc(msgSalvos.texto) no render
    msgSalvos = { texto: 'Cenário “' + r.nome + '” salvo (id ' + r.id + '): término ' + dataBR(r.termino) + '.' };
    carregarSalvos(true);
  } catch (e) {
    msgSalvos = { erro: true, texto: `Não foi possível salvar: ${e.message || e}` };
    renderSimulacao();
  }
}

async function reabrir(id) {
  try {
    reaberto = await api.abrirCenarioSalvo(id);
    msgSalvos = null;
  } catch (e) {
    reaberto = null;
    msgSalvos = { erro: true, texto: `Não foi possível reabrir: ${e.message || e}` };
  }
  renderSimulacao();
}

async function reaplicar() {
  if (!reaberto) return;
  const ajustes = (reaberto.ajustes || []).map(limparNulosSalvo);
  ocupado = true;
  renderSimulacao();
  try {
    estado.simulacao = await api.simular(ajustes);
    msg = null;
    if (opcoes.aposMudanca) await opcoes.aposMudanca(true);
    // texto exibido via esc(msgSalvos.texto) no render
    msgSalvos = { texto: 'Cenário “' + reaberto.nome + '” aplicado como simulação (' + ajustes.length + ' ajustes).' };
  } catch (e) {
    msgSalvos = { erro: true, texto: `Simulação rejeitada: ${e.message || e}` };
  } finally {
    ocupado = false;
    renderSimulacao();
  }
}