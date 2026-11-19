// Aba "Cronograma da construtora": exportar MSPDI, importar MSPDI/XER e comparar com o motor.
// As datas do arquivo NÃO são usadas: o motor recalcula a rede importada (ver limitações exibidas).

import { estado, selecionar } from './estado.js';
import { api } from './api.js';
import { esc, dataBR, num, CENARIO_ROTULO, seloSimulacao } from './util.js';

let raiz = null;
let opcoes = {};
let resultado = null;   // {origem, importado, comparacao}
let erro = null;
let ocupado = false;
let soDiferencas = true;
// DCMA do NOSSO cenário (por cenário): {chave, carregando|dados|erro}
let dcmaMotor = {};
// comparação de revisões: {origem, dados} | {erro}
let rev = null;
let revOcupado = false;

export function iniciarCronoImport(el, op) {
  raiz = el;
  opcoes = op || {};
}

const CENARIOS = ['linha_base', 'construtora', 'independente', 'simulado'];

export function renderCronoImport() {
  if (!raiz || !estado.projeto) return;
  const cenExp = raiz.querySelector('#ci-exp-cen')?.value || 'construtora';
  const cenMotor = raiz.querySelector('#ci-motor-cen')?.value || 'independente';
  const cenDcma = raiz.querySelector('#ci-dcma-cen')?.value || 'independente';
  const revA = raiz.querySelector('#ci-rev-a')?.value || 'linha_base';
  const revB = raiz.querySelector('#ci-rev-b')?.value || 'construtora';
  raiz.innerHTML = `
    <div class="bloco">
      <h3 style="margin-top:0">Exportar cronograma (MSPDI do MS Project ou XER do Primavera P6)</h3>
      <div class="gantt-barra">
        <label>Cenário <select id="ci-exp-cen">${CENARIOS.map(c => `<option value="${c}" ${c === cenExp ? 'selected' : ''}>${esc(CENARIO_ROTULO[c])}</option>`).join('')}</select></label>
        <a class="botao-link" id="ci-exportar" href="${esc(api.urlExportarMspdi(cenExp))}" download>Exportar MSPDI (.xml)</a>
        <a class="botao-link" id="ci-exportar-xer" href="${esc(api.urlExportarXer(cenExp))}" download>Exportar XER (Primavera P6)</a>
        <a class="botao-link" id="ci-exportar-ifc" href="${esc(api.urlIfcExportar(true))}" download title="IFC 4.3 da obra com as tarefas e o cronograma (IfcTask/IfcWorkSchedule)">Baixar IFC com cronograma</a>
        <span style="font-size:12px;color:var(--texto-3)">Arquivo com DADOS FICTÍCIOS da obra atual.</span>
      </div>
    </div>
    <div class="bloco" style="margin-top:14px">
      <h3 style="margin-top:0">Comparar o cronograma da construtora com o motor</h3>
      <p style="margin:0 0 8px;color:var(--texto-2);font-size:13px">Envie o cronograma da construtora (MSPDI .xml ou Primavera P6 .xer).
        O motor lê a rede do arquivo, <b>recalcula as datas</b> (as datas gravadas no arquivo não são usadas) e compara, atividade a
        atividade, com o cenário escolhido do motor.</p>
      <div class="gantt-barra">
        <input type="file" id="ci-arquivo" accept=".xml,.xer,application/xml,text/xml">
        <label>Comparar com <select id="ci-motor-cen">${CENARIOS.map(c => `<option value="${c}" ${c === cenMotor ? 'selected' : ''}>${esc(CENARIO_ROTULO[c])}</option>`).join('')}</select></label>
        <button type="button" class="primario" id="ci-comparar" ${ocupado ? 'disabled' : ''}>Comparar arquivo</button>
        <button type="button" id="ci-exemplo" ${ocupado ? 'disabled' : ''} title="Exporta o cenário 'construtora' em MSPDI e o envia de volta ao comparador">Usar exemplo (cenário construtora)</button>
      </div>
      <div id="ci-res">${resultadoHTML()}</div>
    </div>
    <div class="bloco" style="margin-top:14px" id="ci-rev-bloco">
      <h3 style="margin-top:0">Comparar revisões do cronograma</h3>
      <p style="margin:0 0 8px;color:var(--texto-2);font-size:13px">O que mudou entre duas versões e quanto cada mudança, sozinha, move o término (efeito isolado);
        o que sobra é o resíduo de interação entre mudanças.</p>
      <div class="gantt-barra">
        <label>Versão A <select id="ci-rev-a">${CENARIOS.map(c => `<option value="${esc(c)}" ${c === revA ? 'selected' : ''}>${esc(CENARIO_ROTULO[c])}</option>`).join('')}</select></label>
        <label>Versão B <select id="ci-rev-b">${CENARIOS.map(c => `<option value="${esc(c)}" ${c === revB ? 'selected' : ''}>${esc(CENARIO_ROTULO[c])}</option>`).join('')}</select></label>
        <button type="button" id="ci-rev-cen" ${revOcupado ? 'disabled' : ''}>Comparar cenários</button>
      </div>
      <div class="gantt-barra">
        <label>Arquivo A <input type="file" id="ci-rev-arq-a" accept=".xml,.xer"></label>
        <label>Arquivo B <input type="file" id="ci-rev-arq-b" accept=".xml,.xer"></label>
        <button type="button" class="primario" id="ci-rev-arq" ${revOcupado ? 'disabled' : ''}>Comparar arquivos</button>
        <button type="button" id="ci-rev-exemplo" ${revOcupado ? 'disabled' : ''} title="MSPDI do cenário construtora (A) × XER do cenário independente (B)">Usar exemplo (MSPDI × XER)</button>
      </div>
      <div id="ci-rev-res">${revisoesHTML()}</div>
    </div>
    <div class="bloco" style="margin-top:14px" id="ci-dcma-bloco">
      <h3 style="margin-top:0">Avaliação DCMA de 14 pontos — cenário do motor</h3>
      <div class="gantt-barra">
        <label>Cenário <select id="ci-dcma-cen">${CENARIOS.map(c => `<option value="${esc(c)}" ${c === cenDcma ? 'selected' : ''}>${esc(CENARIO_ROTULO[c])}</option>`).join('')}</select></label>
        <span style="font-size:12px;color:var(--texto-3)">O quadro do arquivo importado aparece junto da comparação, acima.</span>
      </div>
      ${dcmaMotorHTML(cenDcma)}
    </div>`;

  raiz.querySelector('#ci-exp-cen').addEventListener('change', (e) => {
    raiz.querySelector('#ci-exportar').href = api.urlExportarMspdi(e.target.value);
    raiz.querySelector('#ci-exportar-xer').href = api.urlExportarXer(e.target.value);
  });
  raiz.querySelector('#ci-comparar').addEventListener('click', () => {
    const f = raiz.querySelector('#ci-arquivo').files[0];
    if (!f) { erro = 'Escolha um arquivo .xml (MSPDI) ou .xer (P6) antes de comparar.'; resultado = null; renderCronoImport(); return; }
    comparar(f, f.name);
  });
  raiz.querySelector('#ci-exemplo').addEventListener('click', usarExemplo);
  raiz.querySelector('#ci-dcma-cen').addEventListener('change', () => renderCronoImport());
  raiz.querySelector('#ci-rev-cen').addEventListener('click', () => compararRevisoes('cenarios'));
  raiz.querySelector('#ci-rev-arq').addEventListener('click', () => compararRevisoes('arquivos'));
  raiz.querySelector('#ci-rev-exemplo').addEventListener('click', () => compararRevisoes('exemplo'));
  const chk = raiz.querySelector('#ci-so-dif');
  if (chk) chk.addEventListener('change', () => { soDiferencas = chk.checked; renderCronoImport(); });
  raiz.querySelectorAll('[data-ir]').forEach(el => el.addEventListener('click', () => {
    selecionar(el.dataset.ir, 'cronoimport');
    if (opcoes.irPara) opcoes.irPara('cronograma');
  }));
}

async function comparar(corpo, origem) {
  const cen = raiz.querySelector('#ci-motor-cen').value;
  ocupado = true; erro = null; resultado = null;
  renderCronoImport();
  try {
    // o DCMA do arquivo não pode derrubar a comparação: resultado próprio (dados ou erro)
    const [importado, comparacao, dcma] = await Promise.all([api.importarCronograma(corpo), api.compararCronograma(corpo, cen),
      api.dcmaImportado(corpo).then(d => ({ dados: d })).catch(e => ({ erro: e.message || String(e) }))]);
    resultado = { origem, importado, comparacao, dcma };
  } catch (e) {
    erro = e.status === 415 ? `Arquivo não reconhecido: ${e.message}` : `Não foi possível comparar: ${e.message}`;
  } finally {
    ocupado = false;
    renderCronoImport();
  }
}

async function usarExemplo() {
  ocupado = true; erro = null; resultado = null;
  renderCronoImport();
  try {
    const buf = await api.exportarMspdi('construtora');
    ocupado = false;
    await comparar(buf, 'exemplo: MSPDI exportado do cenário construtora');
  } catch (e) {
    ocupado = false;
    erro = `Não foi possível montar o exemplo: ${e.message}`;
    renderCronoImport();
  }
}

function deltaHTML(d) {
  if (d === null || d === undefined) return '—';
  const cls = d > 0 ? 'ruim' : d < 0 ? 'bom' : 'medio';
  return `<span class="indice ${cls}">${d > 0 ? '▲ +' : d < 0 ? '▼ −' : '= '}${Math.abs(d)}</span>`;
}

function resultadoHTML() {
  if (ocupado) return '<p class="vazio">Lendo o arquivo e recalculando a rede…</p>';
  if (erro) return `<p class="erro" id="ci-erro">${esc(erro)}</p>`;
  if (!resultado) return '<p class="vazio">Nenhuma comparação ainda. Envie um arquivo ou use o exemplo.</p>';
  const { origem, importado: im, comparacao: c } = resultado;
  const linhas = [...(c.atividades || [])]
    .filter(a => !soDiferencas || a.delta_termino_dias_corridos || a.delta_duracao)
    .sort((a, b) => Math.abs(b.delta_termino_dias_corridos || 0) - Math.abs(a.delta_termino_dias_corridos || 0)
      || Math.abs(b.delta_duracao || 0) - Math.abs(a.delta_duracao || 0) || a.id.localeCompare(b.id));
  const dT = c.delta_termino_dias_corridos;
  const listaIds = (ids) => ids && ids.length ? ids.slice(0, 20).map(esc).join(', ') + (ids.length > 20 ? '…' : '') : 'nenhuma';
  return `
    <p style="font-size:12.5px;color:var(--texto-2);margin:8px 0">Arquivo: <b>${esc(origem)}</b> · ${esc(im.formato || '').toUpperCase()} ·
      “${esc(im.nome || '')}” · ${im.n_atividades} atividades, ${im.n_relacoes} relações, ${im.n_calendarios} calendários.</p>
    ${(im.avisos || []).length ? `<p class="erro" style="background:#fff8e1;border-color:#ffd24a;color:#4a3900">Avisos da importação: ${im.avisos.map(esc).join(' · ')}</p>` : ''}
    <div style="display:flex;gap:28px;flex-wrap:wrap;align-items:flex-end" id="ci-resumo">
      <div><div style="font-size:12px;color:var(--texto-2)">Término do arquivo (recalculado)</div><div style="font-size:18px;font-weight:600">${dataBR(c.termino_importado)}</div></div>
      <div><div style="font-size:12px;color:var(--texto-2)">Término do motor (${esc(CENARIO_ROTULO[c.cenario_motor] || c.cenario_motor)})</div><div style="font-size:18px;font-weight:600">${dataBR(c.termino_motor)}</div></div>
      <div><div class="delta-grande ${dT > 0 ? 'pior' : dT < 0 ? 'melhor' : ''}" id="ci-delta">${dT > 0 ? '+' : ''}${dT} dias corridos</div>
        <div style="color:var(--texto-2)">motor − arquivo</div></div>
      <div><div style="font-size:12px;color:var(--texto-2)">Atividades casadas</div><div style="font-size:18px;font-weight:600" id="ci-casadas">${c.n_casadas}</div></div>
      <div><div style="font-size:12px;color:var(--texto-2)">Com diferença</div><div style="font-size:18px;font-weight:600">${c.n_com_diferenca}</div></div>
    </div>
    <p style="font-size:12.5px;margin:8px 0">Só no arquivo: ${listaIds(c.so_no_importado)} · Só no motor: ${listaIds(c.so_no_motor)}</p>
    <label class="chk"><input type="checkbox" id="ci-so-dif" ${soDiferencas ? 'checked' : ''}> Só atividades com diferença</label>
    ${linhas.length ? `<div style="max-height:420px;overflow:auto;margin-top:6px"><table class="tab" id="ci-tab"><thead><tr>
      <th>Atividade</th><th class="num">Duração arquivo</th><th class="num">Duração motor</th><th>Δ dur.</th>
      <th>Término arquivo</th><th>Término motor</th><th>Δ término (d)</th><th>Crítica (motor)</th><th>Fonte da produtividade (motor)</th></tr></thead><tbody>
      ${linhas.map(a => `<tr data-ir="${esc(a.id)}" style="cursor:pointer" title="${esc(a.nome)}">
        <td><b>${esc(a.id)}</b><br><small style="color:var(--texto-3)">${esc((a.nome || '').slice(0, 60))}</small></td>
        <td class="num">${a.duracao_importada ?? '—'}</td><td class="num">${a.duracao_motor ?? '—'}</td><td>${deltaHTML(a.delta_duracao)}</td>
        <td>${dataBR(a.termino_importado)}</td><td>${dataBR(a.termino_motor)}</td><td>${deltaHTML(a.delta_termino_dias_corridos)}</td>
        <td>${a.critica_motor ? '<span class="pill crit">crítica</span>' : ''}</td>
        <td style="white-space:normal;font-size:12px">${esc(a.fonte_produtividade_motor || '—')}</td></tr>`).join('')}
    </tbody></table></div>` : '<p style="color:var(--texto-2)">Nenhuma atividade com diferença: o arquivo e o motor coincidem.</p>'}
    <h3 style="margin:14px 0 6px">Avaliação DCMA de 14 pontos — arquivo importado</h3>
    ${resultado.dcma && resultado.dcma.erro ? `<p class="erro">DCMA do arquivo indisponível: ${esc(resultado.dcma.erro)}</p>`
      : resultado.dcma ? quadroDCMA(resultado.dcma.dados, "ci-dcma-arq") : ""}
    <details style="margin-top:8px"><summary style="cursor:pointer;font-size:12.5px">Limitações da importação</summary>
      <ul style="font-size:12px;color:var(--texto-2)">${(im.limitacoes || []).map(l => `<li>${esc(l)}</li>`).join('')}</ul>
      <p style="font-size:12px;color:var(--texto-3)">${esc(im.calculado_por || '')}</p></details>`;
}

/** Gancho da apresentação guiada: roda o exemplo (construtora exportada × motor) e devolve o resultado. */
export async function rodarExemploCrono() {
  if (!raiz.querySelector('#ci-motor-cen')) renderCronoImport();
  await usarExemplo();
  return erro ? { erro } : resultado;
}
// ---------------------------------------------------------------- DCMA de 14 pontos
function dcmaMotorHTML(cen) {
  const s = dcmaMotor;
  if (s.chave !== cen) {
    dcmaMotor = { chave: cen, carregando: true };
    api.dcma(cen).then(d => { if (dcmaMotor.chave === cen) dcmaMotor = { chave: cen, dados: d }; })
      .catch(e => { if (dcmaMotor.chave === cen) dcmaMotor = { chave: cen, erro: e.message || String(e) }; })
      .finally(() => renderCronoImport());
  }
  if (dcmaMotor.carregando) return '<p class="vazio">Avaliando os 14 pontos no cenário do motor…</p>';
  if (dcmaMotor.erro) return `<p class="erro">DCMA indisponível: ${esc(dcmaMotor.erro)}</p>`;
  return quadroDCMA(dcmaMotor.dados, 'ci-dcma-motor');
}

/** Ids de atividade da obra que aparecem num texto de violadora ("A->B SS+5", "L3-S04-TER", …). */
function idsNaViolacao(txt) {
  return [...new Set(String(txt).split(/[^A-Za-z0-9_-]+/).filter(t => estado.ativ.has(t)))];
}

function statusDCMA(p) {
  if (p.aprovado === true) return '<span class="indice bom">✓ aprovado</span>';
  if (p.aprovado === false) return '<span class="indice ruim">▼ reprovado</span>';
  return '<span class="indice medio">— não se aplica / informativo</span>';
}

/** Quadro dos 14 pontos: valor, limite, situação e violadoras clicáveis (seleciona a atividade). */
function quadroDCMA(d, id) {
  if (!d || !Array.isArray(d.pontos)) return '<p class="vazio">Sem avaliação DCMA.</p>';
  const r = d.resumo || {};
  const limite = (p) => (p.limite === null || p.limite === undefined ? esc(p.criterio || '—') : `${esc(p.criterio || '')} ${num(p.limite, 2)}`);
  return `${seloSimulacao(d)}<p style="font-size:12.5px;margin:4px 0" id="${esc(id)}-resumo">${esc(d.origem || '')} · população ${num(d.populacao, 0)} tarefas,
      ${num(d.n_relacoes_vivas, 0)} relações vivas · término calculado ${dataBR(d.termino_calculado)} ·
      <span class="indice bom">✓ ${num(r.aprovados, 0)}</span> <span class="indice ruim">▼ ${num(r.reprovados, 0)}</span>
      <span class="indice medio">— ${num(r.nao_avaliados, 0)}</span></p>
    ${d.erro_motor ? `<p class="erro">${esc(d.erro_motor)}</p>` : ''}
    <div style="max-height:420px;overflow:auto"><table class="tab" id="${esc(id)}"><thead><tr><th>#</th><th>Ponto</th><th class="num">Valor</th>
      <th>Limite</th><th>Situação</th><th class="num">Violadoras</th><th>Quais (clique para selecionar)</th></tr></thead><tbody>
      ${d.pontos.map(p => `<tr data-ponto="${num(p.numero, 0)}" title="${esc(p.nota || '')}">
        <td>${num(p.numero, 0)}</td><td style="white-space:normal">${esc(p.nome)}</td>
        <td class="num">${num(p.valor, 2)} <small>${esc(p.unidade || '')}</small></td><td>${limite(p)}</td><td>${statusDCMA(p)}</td>
        <td class="num">${num(p.n_violadoras, 0)}</td>
        <td style="white-space:normal;font-size:12px">${(p.violadoras || []).length ? `<details><summary style="cursor:pointer">${num(p.violadoras.length, 0)}${p.lista_truncada ? '+' : ''}</summary>
          ${(p.violadoras || []).slice(0, 40).map(v => {
            const ids = idsNaViolacao(v);
            return `<div>${ids.length ? `<span class="link-ativ" data-ir="${esc(ids[ids.length - 1])}">${esc(v)}</span>` : esc(v)}</div>`;
          }).join('')}${p.violadoras.length > 40 ? '<div>…</div>' : ''}</details>` : '—'}</td></tr>`).join('')}
    </tbody></table></div>
    <p style="font-size:11.5px;color:var(--texto-3);margin:4px 0 0">${esc(d.aviso || '')} Fontes: ${(d.fontes || []).map(esc).join(' · ')}</p>`;
}
// ---------------------------------------------------------------- comparar revisões
/** ArrayBuffer → base64 (em blocos, sem estourar a pilha com arquivos grandes). */
function base64De(buf) {
  const b = new Uint8Array(buf);
  let s = '';
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
  return btoa(s);
}

async function compararRevisoes(modo) {
  const a = raiz.querySelector('#ci-rev-a').value;
  const b = raiz.querySelector('#ci-rev-b').value;
  const fa = raiz.querySelector('#ci-rev-arq-a')?.files[0];
  const fb = raiz.querySelector('#ci-rev-arq-b')?.files[0];
  if (modo === 'arquivos' && (!fa || !fb)) {
    rev = { erro: 'Escolha os dois arquivos (A e B), cada um MSPDI .xml ou P6 .xer.' };
    renderCronoImport();
    return;
  }
  revOcupado = true;
  rev = { carregando: true };
  renderCronoImport();
  try {
    let dados, origem;
    if (modo === 'cenarios') {
      dados = await api.revisoesComparar(a, b);
      origem = `cenários ${CENARIO_ROTULO[a] || a} × ${CENARIO_ROTULO[b] || b}`;
    } else {
      let bufA, bufB;
      if (modo === 'exemplo') {
        bufA = await api.exportarMspdi('construtora');
        const r = await fetch(api.urlExportarXer('independente'));
        if (!r.ok) throw new Error('Erro HTTP ' + Number(r.status) + ' ao exportar o XER do exemplo'); // exibido via esc(rev.erro)
        bufB = await r.arrayBuffer();
        origem = 'exemplo: MSPDI construtora × XER independente';
      } else {
        [bufA, bufB] = await Promise.all([fa.arrayBuffer(), fb.arrayBuffer()]);
        origem = `arquivos ${fa.name} × ${fb.name}`;
      }
      dados = await api.revisoesCompararArquivos({ a: { conteudo_base64: base64De(bufA) }, b: { conteudo_base64: base64De(bufB) }, efeitos_isolados: true });
    }
    rev = { origem, dados };
  } catch (e) {
    rev = { erro: `Não foi possível comparar as revisões: ${e.message || e}` };
  } finally {
    revOcupado = false;
    renderCronoImport();
  }
}

function revisoesHTML() {
  if (!rev) return '<p class="vazio">Escolha dois cenários ou envie dois arquivos.</p>';
  if (rev.carregando) return '<p class="vazio">Comparando e calculando o efeito isolado de cada mudança…</p>';
  if (rev.erro) return `<p class="erro" id="ci-rev-erro">${esc(rev.erro)}</p>`;
  const d = rev.dados;
  const at = d.atribuicao || {};
  const rc = d.reconstrucao || {};
  const cc = d.caminho_critico || {};
  const ms = [...(d.mudancas || [])].sort((x, y) => Math.abs(y.efeito_isolado_dias || 0) - Math.abs(x.efeito_isolado_dias || 0));
  const dt = d.delta_dias_corridos || 0;
  return `<p style="font-size:12.5px;margin:6px 0">${esc(rev.origem)} · A = ${esc(d.a || '')}, B = ${esc(d.b || '')} · modo ${esc(d.modo || '')}</p>
    <div style="display:flex;gap:26px;flex-wrap:wrap;align-items:flex-end" id="ci-rev-resumo">
      <div><div class="rot-p">Término A</div><b>${dataBR(d.termino_a)}</b></div>
      <div><div class="rot-p">Término B</div><b>${dataBR(d.termino_b)}</b></div>
      <div><div class="delta-grande ${dt > 0 ? 'pior' : dt < 0 ? 'melhor' : ''}" id="ci-rev-delta">${dt > 0 ? '+' : ''}${num(dt, 0)} dias corridos</div></div>
      <div><div class="rot-p">Mudanças</div><b id="ci-rev-n">${num(d.n_mudancas, 0)}</b> <small>${Object.entries(d.por_tipo || {}).map(([k, n]) => `${esc(k)}: ${num(n, 0)}`).join(', ')}</small></div>
      <div><div class="rot-p">Soma dos efeitos isolados</div><b id="ci-rev-soma">${num(at.soma_efeitos_isolados, 0)} d</b></div>
      <div><div class="rot-p">Resíduo (interação)</div><b id="ci-rev-residuo">${num(at.residuo_interacao, 0)} d</b></div>
      <div><div class="rot-p">Reconstrução de B</div>${rc.confere_com_b ? '<span class="indice bom">✓ confere</span>' : `<span class="indice ruim">▼ não confere${rc.erro ? `: ${esc(rc.erro)}` : ''}</span>`}</div>
    </div>
    ${(d.alertas || []).length ? `<ul class="alertas" id="ci-rev-alertas">${d.alertas.map(a => `<li class="alto">${esc(typeof a === 'string' ? a : (a.texto || a.mensagem || JSON.stringify(a)))}</li>`).join('')}</ul>` : ''}
    <p style="font-size:12.5px;margin:6px 0">Caminho crítico — só em A: ${(cc.so_em_A || []).map(esc).join(', ') || 'nenhuma'} · só em B: ${(cc.so_em_B || []).map(esc).join(', ') || 'nenhuma'}</p>
    <div style="max-height:360px;overflow:auto"><table class="tab" id="ci-rev-tab"><thead><tr><th>Tipo</th><th>Mudança</th><th class="num">Efeito isolado (d)</th><th>Crítica em A</th><th>Observação</th></tr></thead><tbody>
      ${ms.map(m => {
        const ids = idsNaViolacao(m.descricao || '');
        return `<tr><td>${esc(m.tipo || '')}</td><td style="white-space:normal">${ids.length ? `<span class="link-ativ" data-ir="${esc(ids[0])}">${esc(m.descricao || '')}</span>` : esc(m.descricao || '')}</td>
          <td class="num">${m.efeito_isolado_dias === null || m.efeito_isolado_dias === undefined ? '—' : `<b>${m.efeito_isolado_dias > 0 ? '+' : ''}${num(m.efeito_isolado_dias, 0)}</b>`}</td>
          <td>${m.na_cadeia_critica_A ? '<span class="pill crit">sim</span>' : ''}</td><td style="white-space:normal;font-size:12px">${esc(m.erro_isolado || '')}</td></tr>`;
      }).join('')}
    </tbody></table></div>
    <p style="font-size:11.5px;color:var(--texto-3);margin:4px 0 0">${esc(at.regra || '')}${(at.sem_efeito_calculavel || []).length ? ` Sem efeito calculável: ${at.sem_efeito_calculavel.map(esc).join(', ')}.` : ''}</p>`;
}