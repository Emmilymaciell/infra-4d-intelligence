// Aba Fiscalização: diário da frente, produtividade (dia trabalhado × dia útil, perda por chuva),
// conciliação diário × boletim e formulário "lançar diário" validado pela API (sem gravar nada).
// Todos os dados são SINTÉTICOS (a API devolve `aviso` e `sintetico=true`).

import { estado, selecionar, nomeServico } from './estado.js';
import { api } from './api.js';
import { esc, dataBR, num } from './util.js';

let raiz = null;
let opcoes = {};
let frente = null;
const cache = { diario: {}, prod: {}, conc: {} };
let validacao = null;   // {valido, erros, avisos} | {erroRede}
let rascunho = null;    // valores do formulário

export function iniciarFiscalizacao(el, op) {
  raiz = el;
  opcoes = op || {};
}

export function invalidarFiscalizacao() {
  cache.diario = {}; cache.prod = {}; cache.conc = {};
}

const ESTADOS = { lancado: 'Lançado', conferido_fiscal: 'Conferido (fiscal)', aprovado: 'Aprovado' };
function pillEstado(e) {
  const cls = e === 'aprovado' ? 'ok' : e === 'conferido_fiscal' ? 'and' : 'ni';
  return `<span class="pill ${cls}">${esc(ESTADOS[e] || e || '—')}</span>`;
}

/** Frentes com diário: atividades por quantidade já iniciadas. */
function frentes() {
  return estado.projeto.atividades.filter(a => a.tipo === 'tarefa' && a.quantidade_total && a.status !== 'nao_iniciada');
}

function frentePadrao() {
  const fs = frentes();
  if (estado.selecionada && fs.some(a => a.id === estado.selecionada)) return estado.selecionada;
  if (frente && fs.some(a => a.id === frente)) return frente;
  const and = fs.find(a => a.status === 'em_andamento');
  return (and || fs[0] || {}).id || null;
}

/** Busca com cache por chave; redesenha quando chega. */
function obter(tipo, chave, fn) {
  const c = cache[tipo];
  if (c[chave] && (c[chave].dados || c[chave].erro)) return c[chave];
  if (!c[chave]) {
    c[chave] = { carregando: true };
    fn().then(d => { c[chave] = { dados: d }; }).catch(e => { c[chave] = { erro: e.message }; }).finally(() => renderFiscalizacao());
  }
  return c[chave];
}

export function renderFiscalizacao() {
  if (!raiz || !estado.projeto || !raiz.offsetParent) return;
  frente = frentePadrao();
  const lote = estado.filtros.lote || '';
  const dia = frente ? obter('diario', frente, () => api.fiscDiario(frente)) : null;
  const prod = obter('prod', lote, () => api.fiscProdutividade(lote || null));
  const conc = obter('conc', lote, () => api.fiscConciliacao(lote || null));
  const aviso = (dia && dia.dados && dia.dados.aviso) || (prod.dados && prod.dados.aviso) || '';
  if (raiz.querySelector('#fz-data')) rascunho = coletarFormulario();

  raiz.innerHTML = `
    <p class="erro" style="background:#fff8e1;border-color:#ffd24a;color:#4a3900;margin-top:0">
      <b>Fiscalização SINTÉTICA</b> — ${esc(aviso || 'dados fictícios')} Diários e boletins são derivados dos boletins fictícios; nada aqui é medição real.</p>
    <div class="grade-painel">
      <div class="bloco largo" id="fz-diario-bloco">
        <h3 style="margin-top:0">Diário da frente</h3>
        <div class="gantt-barra">
          <label>Frente <select id="fz-frente">${frentes().map(a => `<option value="${esc(a.id)}" ${a.id === frente ? 'selected' : ''}>${esc(a.id)} — ${esc(nomeServico(a.servico_id))} (${esc(a.status === 'em_andamento' ? 'em andamento' : 'concluída')})</option>`).join('')}</select></label>
          <span style="font-size:12px;color:var(--texto-3)">Selecionar uma atividade no Gantt/3D também troca a frente.</span>
        </div>
        ${diarioHTML(dia)}
      </div>
      <div class="bloco largo"><h3 style="margin-top:0">Produtividade — dia trabalhado × dia útil${lote ? ` · ${esc(lote)}` : ''}</h3>${produtividadeHTML(prod)}</div>
      <div class="bloco"><h3 style="margin-top:0">Conciliação diário × boletim${lote ? ` · ${esc(lote)}` : ''}</h3>${conciliacaoHTML(conc)}</div>
      <div class="bloco"><h3 style="margin-top:0">Lançar diário (validação)</h3>${formularioHTML()}</div>
    </div>`;

  raiz.querySelector('#fz-frente')?.addEventListener('change', (e) => { frente = e.target.value; selecionar(frente, 'fiscalizacao'); });
  raiz.querySelector('#fz-validar')?.addEventListener('click', validar);
  raiz.querySelector('#fz-limpar')?.addEventListener('click', () => { rascunho = null; validacao = null; renderFiscalizacao(); });
  raiz.querySelectorAll('[data-ir]').forEach(el => el.addEventListener('click', () => {
    selecionar(el.dataset.ir, 'fiscalizacao');
  }));
}

function diarioHTML(d) {
  if (!d) return '<p class="vazio">Nenhuma frente iniciada.</p>';
  if (d.carregando) return '<p class="vazio">Carregando diário…</p>';
  if (d.erro) return `<p class="erro">Diário indisponível: ${esc(d.erro)}</p>`;
  const lst = d.dados.diarios || [];
  const cont = {};
  for (const x of lst) cont[x.estado] = (cont[x.estado] || 0) + 1;
  const chuva = lst.reduce((s, x) => s + (x.horas_chuva || 0), 0);
  const q = lst.reduce((s, x) => s + (x.quantidade || 0), 0);
  return `<p style="font-size:12.5px;margin:4px 0 8px" id="fz-diario-resumo">${d.dados.total} diário(s)${d.dados.truncado ? ' (lista truncada)' : ''} ·
      ${Object.entries(cont).map(([e, n]) => `${pillEstado(e)} ${n}`).join(' ')} · ${num(chuva, 1)} h de chuva · ${num(q, 1)} ${esc(lst[0]?.unidade || '')} executados</p>
    ${lst.length ? `<div style="max-height:320px;overflow:auto"><table class="tab" id="fz-diario"><thead><tr>
      <th>Data</th><th>Estado</th><th class="num">Quantidade</th><th class="num">Equipes·dia</th><th class="num">Chuva (h)</th>
      <th>km executado</th><th>Ocorrências</th><th>Boletim</th></tr></thead><tbody>
      ${[...lst].reverse().map(x => `<tr>
        <td>${dataBR(x.data)}</td><td>${pillEstado(x.estado)}</td><td class="num">${num(x.quantidade, 1)} <small>${esc(x.unidade || '')}</small></td>
        <td class="num">${num(x.equipes_dias, 0)}</td><td class="num">${x.horas_chuva ? `<b style="color:#1f4f8f">${num(x.horas_chuva, 1)}</b>` : '0'}</td>
        <td>${x.km_ini_exec != null ? `${num(x.km_ini_exec, 3)} → ${num(x.km_fim_exec, 3)}` : '—'}</td>
        <td style="white-space:normal">${(x.ocorrencias || []).length ? x.ocorrencias.map(o => esc(typeof o === 'string' ? o : (o.descricao || o.texto || JSON.stringify(o)))).join('; ') : '—'}</td>
        <td><small>${esc(x.semana_boletim ? dataBR(x.semana_boletim) : '—')}</small></td></tr>`).join('')}
    </tbody></table></div>` : '<p class="vazio">Sem diários para esta frente.</p>'}
    <p style="font-size:11.5px;color:var(--texto-3);margin:4px 0 0">${esc(d.dados.origem || '')}</p>`;
}

function produtividadeHTML(p) {
  if (p.carregando) return '<p class="vazio">Carregando produtividade…</p>';
  if (p.erro) return `<p class="erro">Produtividade indisponível: ${esc(p.erro)}</p>`;
  const ativ = [...(p.dados.atividades || [])].sort((a, b) => (b.perda_por_paralisacao_pct || 0) - (a.perda_por_paralisacao_pct || 0) || a.atividade_id.localeCompare(b.atividade_id));
  const perda = (v) => {
    if (v == null) return '—';
    const cls = v >= 10 ? 'ruim' : v > 0 ? 'medio' : 'bom';
    return `<span class="indice ${cls}">${v > 0 ? '▼ ' : ''}${num(v, 1)}%</span>`;
  };
  return `${ativ.length ? `<div style="max-height:340px;overflow:auto"><table class="tab" id="fz-prod"><thead><tr>
      <th>Atividade</th><th class="num">Por dia trabalhado</th><th class="num">Por dia útil da obra</th><th class="num">Dias trab.</th>
      <th class="num">Parados chuva</th><th class="num">Parados outros</th><th>Perda por paralisação</th></tr></thead><tbody>
      ${ativ.map(a => `<tr><td><span class="link-ativ" data-ir="${esc(a.atividade_id)}">${esc(a.atividade_id)}</span></td>
        <td class="num">${num(a.prod_por_dia_trabalhado, 2)} <small>${esc(a.unidade)}</small></td><td class="num">${num(a.prod_por_dia_util_obra, 2)}</td>
        <td class="num">${a.dias_trabalhados}</td><td class="num">${a.dias_paralisados_chuva}</td><td class="num">${a.dias_paralisados_outros}</td>
        <td>${perda(a.perda_por_paralisacao_pct)}</td></tr>`).join('')}
    </tbody></table></div>` : '<p class="vazio">Sem atividades medidas no escopo.</p>'}
    <p style="font-size:11.5px;color:var(--texto-3);margin:4px 0 0">${esc(p.dados.regra || '')} · ${esc(p.dados.unidade_produtividade || '')}.
      A perda mostra quanto a produtividade “por dia útil” fica abaixo da “por dia trabalhado” por causa das paralisações (chuva e outras).</p>`;
}

function conciliacaoHTML(c) {
  if (c.carregando) return '<p class="vazio">Conciliando…</p>';
  if (c.erro) return `<p class="erro">Conciliação indisponível: ${esc(c.erro)}</p>`;
  const d = c.dados;
  const div = d.divergencias || [];
  const sem = d.diarios_sem_boletim || [];
  const linha = (o) => Object.entries(o).filter(([k]) => !['origem', 'sintetico'].includes(k))
    .map(([k, v]) => `<b>${esc(k)}</b>: ${esc(typeof v === 'object' ? JSON.stringify(v) : v)}`).join(' · ');
  return `<div id="fz-conc" style="display:flex;gap:22px;flex-wrap:wrap">
      <div><div style="font-size:12px;color:var(--texto-2)">Boletins conciliados</div><div style="font-size:18px;font-weight:600">${d.n_boletins}</div></div>
      <div><div style="font-size:12px;color:var(--texto-2)">Divergências</div><div style="font-size:18px;font-weight:600">${d.n_divergencias
        ? `<span class="indice ruim">▲ ${d.n_divergencias}</span>` : '<span class="indice bom">✓ 0</span>'}</div></div>
      <div><div style="font-size:12px;color:var(--texto-2)">Diários sem boletim</div><div style="font-size:18px;font-weight:600">${sem.length}</div></div>
    </div>
    ${div.length ? `<ul style="font-size:12.5px">${div.slice(0, 30).map(x => `<li>${linha(x)}</li>`).join('')}</ul>` : ''}
    ${sem.length ? `<p style="font-size:12.5px">Sem boletim: ${sem.slice(0, 15).map(x => esc(typeof x === 'string' ? x : `${x.atividade_id || ''} ${x.data || ''}`)).join(', ')}</p>` : ''}
    <p style="font-size:11.5px;color:var(--texto-3);margin:6px 0 0">${esc(d.regra || '')} (tolerância ${num((d.tolerancia_quantidade || 0) * 100, 2)}%).</p>`;
}

// ---------------- formulário "lançar diário" ----------------
const CAMPOS = [
  ['data', 'Data', 'date'], ['atividade_id', 'Frente (atividade)', 'frente'], ['estado', 'Estado', 'estado'],
  ['quantidade', 'Quantidade', 'number'], ['equipes_dias', 'Equipes·dia', 'number'], ['horas_chuva', 'Horas de chuva', 'number'],
  ['km_ini_exec', 'km inicial executado', 'number'], ['km_fim_exec', 'km final executado', 'number'],
  ['origem', 'Origem (quem lançou)', 'text'], ['ocorrencias', 'Ocorrências (uma por linha)', 'textarea'],
];

function valorPadrao(campo) {
  if (rascunho && campo in rascunho) return rascunho[campo];
  const a = estado.ativ.get(frente);
  return {
    data: estado.dataStatus, atividade_id: frente || '', estado: 'lancado', quantidade: '', equipes_dias: a ? String(a.equipes || 1) : '1',
    horas_chuva: '0', km_ini_exec: a ? String(a.km_ini) : '', km_fim_exec: '', origem: 'fiscal de campo (demonstração)', ocorrencias: '',
  }[campo];
}

function formularioHTML() {
  const erros = {};
  if (validacao && validacao.erros) for (const e of validacao.erros) (erros[e.campo] = erros[e.campo] || []).push(e);
  const campo = ([id, rot, tipo]) => {
    const v = valorPadrao(id) ?? '';
    const err = erros[id];
    const cls = err ? 'campo-erro' : '';
    let input;
    if (tipo === 'frente') input = `<select id="fz-${id}" class="${cls}">${estado.projeto.atividades.filter(a => a.tipo === 'tarefa' && a.quantidade_total)
      .map(a => `<option value="${esc(a.id)}" ${a.id === v ? 'selected' : ''}>${esc(a.id)}</option>`).join('')}</select>`;
    else if (tipo === 'estado') input = `<select id="fz-${id}" class="${cls}">${Object.entries(ESTADOS).map(([k, t]) => `<option value="${k}" ${k === v ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select>`;
    else if (tipo === 'textarea') input = `<textarea id="fz-${id}" rows="2" class="${cls}" style="width:100%">${esc(v)}</textarea>`;
    else input = `<input id="fz-${id}" type="${tipo}" ${tipo === 'number' ? 'step="any"' : ''} value="${esc(v)}" class="${cls}">`;
    return `<div class="fz-campo" data-campo="${id}"><label for="fz-${id}">${esc(rot)}</label>${input}
      ${err ? err.map(e => `<div class="msg-erro" data-erro="${esc(id)}">▲ ${esc(e.mensagem)} <small>(${esc(e.regra)})</small></div>`).join('') : ''}</div>`;
  };
  const outros = validacao && validacao.erros ? validacao.erros.filter(e => !CAMPOS.some(c => c[0] === e.campo)) : [];
  let res = '';
  if (validacao && validacao.erroRede) res = `<p class="erro">Validação indisponível: ${esc(validacao.erroRede)}</p>`;
  else if (validacao) {
    res = validacao.valido
      ? '<p class="indice bom" id="fz-valido" style="display:block;padding:6px 8px">✓ Diário válido — passaria na validação (nada foi gravado).</p>'
      : `<p class="erro" id="fz-invalido">${validacao.erros.length} erro(s) de validação — veja cada campo.</p>`;
    if (outros.length) res += `<ul style="font-size:12.5px">${outros.map(e => `<li><b>${esc(e.campo)}</b>: ${esc(e.mensagem)}</li>`).join('')}</ul>`;
    if ((validacao.avisos || []).length) res += `<p style="font-size:12px;color:var(--texto-3)">${validacao.avisos.map(esc).join(' · ')}</p>`;
  }
  return `<p style="font-size:12.5px;color:var(--texto-2);margin:0 0 6px">Preencha como a fiscalização faria em campo e valide.
      As regras (data ≤ data de status, quantidade ≥ 0, chuva ≤ 24 h, km dentro da frente, origem obrigatória…) são da API.
      <b>Nada é gravado.</b></p>
    <div class="fz-form">${CAMPOS.map(campo).join('')}</div>
    <div class="sim-botoes"><button type="button" class="primario" id="fz-validar">Validar diário</button>
      <button type="button" id="fz-limpar">Limpar</button></div>
    <div id="fz-res">${res}</div>`;
}

function coletarFormulario() {
  const v = {};
  for (const [id] of CAMPOS) v[id] = raiz.querySelector(`#fz-${id}`)?.value ?? '';
  return v;
}

async function validar() {
  rascunho = coletarFormulario();
  const n = (x) => (x === '' || x === null || x === undefined ? null : Number(x));
  const corpo = {
    tipo: 'diario', data: rascunho.data || null, atividade_id: rascunho.atividade_id || null, estado: rascunho.estado || null,
    quantidade: n(rascunho.quantidade), equipes_dias: n(rascunho.equipes_dias), horas_chuva: n(rascunho.horas_chuva),
    km_ini_exec: n(rascunho.km_ini_exec), km_fim_exec: n(rascunho.km_fim_exec), origem: rascunho.origem || null,
    ocorrencias: (rascunho.ocorrencias || '').split('\n').map(s => s.trim()).filter(Boolean),
  };
  try {
    validacao = await api.fiscValidar(corpo);
  } catch (e) {
    validacao = { erroRede: e.message };
  }
  renderFiscalizacao();
}
