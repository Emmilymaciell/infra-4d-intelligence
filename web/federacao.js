// Retorno de autoria externa: prévia obrigatória, publicação isolada e explícita.
import { api } from './api.js';
import { esc, dataBR, num } from './util.js';

export function iniciarFederacao(el, opcoes) {
  let baseline = null, revisao = null, previa = null, registroExibido = null;
  let componentes = new Map();
  el.innerHTML = `<p>O arquivo nativo é a fonte da geometria. Revise o retorno antes de publicar uma cópia isolada; a demonstração de referência permanece preservada.</p>
    <div class="acoes"><label>Aplicativo <select id="fed-app"><option>QGIS</option><option>Blender</option><option>FreeCAD</option></select></label>
    <button type="button" id="fed-exportar">Baixar base editável</button>
    <label>Base original <input type="file" id="fed-base" accept=".json,.geojson"></label>
    <label>Revisão retornada <input type="file" id="fed-revisao" accept=".json,.geojson"></label></div>
    <div class="acoes"><label>Malha GLB do Blender (opcional) <input type="file" id="fed-glb" accept=".glb"></label>
    <button type="button" id="fed-carregar-glb" disabled>Exibir malha nativa da revisão</button></div>
    <div class="acoes"><button type="button" id="fed-validar">Conferir revisão</button>
    <button type="button" id="fed-publicar" disabled>Publicar revisão isolada</button>
    <button type="button" id="fed-enquadrar" disabled>Enquadrar revisão</button>
    <label><input type="checkbox" id="fed-isolar" disabled> Só revisão · ocultar referência 3D</label>
    <label><input type="checkbox" id="fed-contexto" disabled> Ambiente ilustrativo · Apresentação</label>
    <button type="button" id="fed-remover">Ocultar sobreposição</button>
    <button type="button" id="fed-listar">Revisões desta sessão</button></div>
    <div id="fed-status" role="status">100% fictício · acervo em memória, apagado ao reiniciar o beta. Preserve os arquivos nativos e de intercâmbio.</div>
    <label>Componente CAD <select id="fed-componente" disabled><option value="">Selecione uma peça nativa</option></select></label>
    <div id="fed-componente-props"></div>
    <div id="fed-resultado"></div>`;
  const $ = s => el.querySelector(s), msg = t => { $('#fed-status').textContent = t; };
  const invalidar = () => { previa = null; $('#fed-publicar').disabled = true; $('#fed-carregar-glb').disabled = true; };
  const falha = e => { invalidar(); msg(`Revisão não publicada: ${e.message || String(e)}`); };
  function propriedades(c) {
    $('#fed-componente').value = c?.componente_id || '';
    document.getElementById('cad-propriedades-lateral')?.remove();
    if (!c) { $('#fed-componente-props').innerHTML = ''; return; }
    const p = c.parametros_mm;
    const html = `<section class="ficha-cad"><h3>${esc(c.nome)}</h3><p>Componente CAD · fictício · ${esc(c.tipo_nativo)}</p>
      <dl><dt>ID CAD estável</dt><dd>${esc(c.componente_id)}</dd><dt>Atividade</dt><dd>${esc(c.atividade_id)}</dd>
      <dt>Material</dt><dd>${esc(c.material)}</dd><dt>Comprimento × largura × altura</dt><dd>${num(p.Length / 1000, 3)} × ${num(p.Width / 1000, 3)} × ${num(p.Height / 1000, 3)} m</dd>
      <dt>Volume geométrico</dt><dd>${num(c.volume_m3, 4)} m³</dd><dt>Área das faces</dt><dd>${num(c.area_m2, 3)} m²</dd></dl>
      <p class="nota-contexto">Derivados declarados pelo CAD. Não são quantidade contratual ou medição. A ficha 4D abaixo continua da referência.</p></section>`;
    $('#fed-componente-props').innerHTML = html;
    const lateral = document.querySelector('#aba-modelo [data-detalhes]');
    if (lateral) {
      const ficha = document.createElement('div'); ficha.id = 'cad-propriedades-lateral'; ficha.innerHTML = html;
      lateral.prepend(ficha);
    }
  }
  $('#fed-componente').addEventListener('change', () => {
    const c = componentes.get($('#fed-componente').value);
    if (!c) return;
    opcoes.selecionar(c.atividade_id, 'federacao');
    opcoes.viewer().selecionarComponenteRevisao(c.componente_id);
    if (opcoes.viewer().revisaoIsolada) opcoes.viewer().enquadrarRevisao();
  });
  document.querySelector('#v-experiencia').addEventListener('change', () => {
    if (document.querySelector('#v-experiencia').value !== 'apresentacao') {
      opcoes.viewer()?.setAmbienteRevisao(false); $('#fed-contexto').checked = false;
    }
  });
  for (const [id, alvo] of [['#fed-base', 'base'], ['#fed-revisao', 'revisao']]) {
    $(id).addEventListener('change', async () => {
      invalidar();
      try {
        const f = $(id).files[0];
        if (!f) { if (alvo === 'base') baseline = null; else revisao = null; return; }
        if (f.size > 9 * 1024 * 1024) throw new Error('arquivo maior que 9 MiB; reduza o pacote antes de importar');
        const d = JSON.parse(await f.text());
        if (alvo === 'base') baseline = d; else revisao = d;
        msg(`${f.name} carregado. Clique em Conferir revisão; nada foi publicado.`);
      } catch (e) { if (alvo === 'base') baseline = null; else revisao = null; falha(e); }
    });
  }
  $('#fed-exportar').addEventListener('click', async () => {
    try {
      baseline = await api.federacaoExportar($('#fed-app').value); invalidar();
      const url = URL.createObjectURL(new Blob([JSON.stringify(baseline, null, 2)], { type: 'application/geo+json' }));
      const a = document.createElement('a'); a.href = url; a.download = `infra4d-${$('#fed-app').value}-base.geojson`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      msg('Base carregada e baixada. Edite no aplicativo, exporte a revisão com metadados e selecione o arquivo de retorno.');
    } catch (e) { falha(e); }
  });
  function mostrar(r) {
    registroExibido = r;
    const mudancas = r.relatorio.mudancas || [];
    const nativa = r.geojson.features.some(f => f.properties.geometria_local_m);
    if (nativa && !opcoes.viewer().revisaoComContexto && document.querySelector('#v-experiencia').value !== 'tecnico') {
      const experiencia = document.querySelector('#v-experiencia');
      experiencia.value = 'tecnico'; experiencia.dispatchEvent(new Event('change'));
    }
    const qtos = Object.entries(r.relatorio.derivados_geometricos || {});
    const resumoCad = qtos.length ? `<h3>Derivados geométricos CAD · declarados e fictícios</h3>
      <table><thead><tr><th>Atividade</th><th>Peças</th><th>Volume anterior → atual (m³)</th><th>Δ volume (m³)</th></tr></thead><tbody>
      ${qtos.map(([id, q]) => `<tr><td>${esc(id)}</td><td>${num(q.componentes_contagem)}</td><td>${typeof q.volume_anterior_m3 === 'number' ? num(q.volume_anterior_m3, 4) : '—'} → ${num(q.volume_m3, 4)}</td><td>${typeof q.delta_volume_m3 === 'number' ? num(q.delta_volume_m3, 4) : '—'}</td></tr>`).join('')}
      </tbody></table><p>Somados uma vez por componente do trecho modelado; não multiplicados pela quantidade da atividade. Anterior é a abertura do FCStd antes da edição automatizada do job, quando disponível; não uma comparação automática entre publicações. Unidades, avanço físico e quantidades de planejamento permanecem separados.</p>` : '';
    $('#fed-resultado').innerHTML = `<p><b>${esc(r.source_app)} · revisão ${esc(r.revision)}</b> · ${num(r.relatorio.ids_preservados)} IDs preservados</p>
      <p>Referência: <b>${dataBR(r.termino_antes)}</b> → revisão: <b>${dataBR(r.termino_depois)}</b>
      (${r.delta_dias_corridos > 0 ? '+' : ''}${num(r.delta_dias_corridos)} dias corridos). <b>${r.publicado ? 'PUBLICADA EM CÓPIA' : 'PRÉVIA — ainda não publicada'}</b></p>
      <p>${nativa ? 'Magenta = geometria recebida do arquivo de retorno, em metros e sem exagero. A edição no aplicativo depende da evidência que acompanha o arquivo.' : 'Magenta = marcador esquemático da linha revisada, deslocado para legibilidade; não é a malha nativa.'} Blender permite comparar também o GLB exportado. FreeCAD retorna a tesselação do FCStd; STEP é intercâmbio geométrico, sem promessa de preservar a árvore paramétrica. Selecione uma atividade abaixo para comparar quantidades e datas; timeline e cores de avanço continuam sendo da referência.</p>
      <table><thead><tr><th>Atividade</th><th>Alteração</th><th>Antes</th><th>Depois / efeito</th></tr></thead><tbody>
      ${mudancas.map(m => `<tr><td><button type="button" data-fed-id="${esc(m.atividade_id)}">${esc(m.atividade_id)}</button></td><td>${esc(m.campo)}</td><td>${typeof m.antes === 'number' ? num(m.antes, 2) : '—'}</td><td>${typeof m.depois === 'number' ? `${num(m.depois, 2)} ${esc(m.unidade || '')}` : esc(m.efeito || 'geometria revisada')}</td></tr>`).join('') || '<tr><td colspan="4">Nenhuma alteração geométrica ou quantitativa.</td></tr>'}</tbody></table>
      ${resumoCad}<p class="nota-contexto">${esc(r.aviso)}</p>`;
    $('#fed-resultado').querySelectorAll('[data-fed-id]').forEach(b => b.addEventListener('click', () => {
      opcoes.selecionar(b.dataset.fedId, 'federacao');
      if (opcoes.viewer().revisaoIsolada) opcoes.viewer().enquadrarRevisao();
      const a = r.resultado_4d.atividades[b.dataset.fedId], f = r.geojson.features.find(f => f.properties.atividade_id === b.dataset.fedId);
      msg(`${b.dataset.fedId} · quantidade revisada: ${f ? num(f.properties.quantidade_total, 2) + ' ' + f.properties.unidade : '—'} · término da revisão: ${a ? dataBR(a.termino) : '—'} · ficha lateral e timeline permanecem da referência.`);
    }));
    componentes = new Map(r.geojson.features.flatMap(f => f.properties.componentes_nativos || []).map(c => [c.componente_id, c]));
    $('#fed-componente').innerHTML = '<option value="">Selecione uma peça nativa</option>' + [...componentes.values()].map(c => `<option value="${esc(c.componente_id)}">${esc(c.nome)} · ${esc(c.atividade_id)}</option>`).join('');
    $('#fed-componente').disabled = !componentes.size;
    opcoes.viewer().aoSelecionarComponenteRevisao = propriedades;
    opcoes.viewer().mostrarRevisao(r);
    $('#fed-enquadrar').disabled = !opcoes.viewer().pecasRevisao?.length;
    $('#fed-isolar').disabled = $('#fed-enquadrar').disabled;
    $('#fed-isolar').checked = !!opcoes.viewer().revisaoIsolada;
    $('#fed-contexto').disabled = !componentes.size;
    $('#fed-contexto').checked = !!opcoes.viewer().revisaoComContexto;
  }
  $('#fed-validar').addEventListener('click', async () => {
    invalidar();
    try {
      if (!baseline || !revisao) throw new Error('selecione a base original e a revisão retornada');
      msg('Conferindo IDs, unidades, proveniência e impacto no prazo…');
      previa = await api.federacaoReceber(baseline, revisao, false);
      mostrar(previa); $('#fed-publicar').disabled = false;
      $('#fed-carregar-glb').disabled = previa.source_app !== 'Blender';
      msg('Prévia validada. Confira as diferenças e publique somente se quiser manter a cópia nesta sessão.');
    } catch (e) { falha(e); }
  });
  $('#fed-publicar').addEventListener('click', async () => {
    if (!previa) return;
    $('#fed-publicar').disabled = true;
    try { const r = await api.federacaoReceber(baseline, revisao, true); mostrar(r); msg('Revisão publicada isoladamente em memória. Base e simulação da demo preservadas.'); }
    catch (e) { falha(e); }
  });
  $('#fed-carregar-glb').addEventListener('click', async () => {
    try {
      if (!registroExibido || registroExibido.source_app !== 'Blender') throw new Error('confira primeiro a revisão JSON do Blender');
      const arquivo = $('#fed-glb').files[0];
      if (!arquivo) throw new Error('selecione o GLB exportado da revisão nativa');
      if (arquivo.size > 50 * 1024 * 1024) throw new Error('GLB maior que 50 MiB; publique um trecho menor');
      const resumo = await opcoes.viewer().carregarRevisaoGlb(await arquivo.arrayBuffer(), registroExibido);
      msg(`GLB nativo carregado: ${resumo.atividades} atividades com IDs preservados, em metros e sem exagero. Geometria ilustrativa Blender; quantidades continuam explícitas no JSON. A timeline permanece da referência.`);
    } catch (e) { msg(`Malha não carregada: ${e.message || String(e)}`); }
  });
  $('#fed-enquadrar').addEventListener('click', () => {
    msg(opcoes.viewer().enquadrarRevisao()
      ? 'Revisão enquadrada. Geometria, quantidades e cronograma permanecem inalterados.'
      : 'Nenhuma geometria de revisão disponível para enquadrar.');
  });
  $('#fed-isolar').addEventListener('change', () => {
    const ativo = $('#fed-isolar').checked;
    if (!opcoes.viewer().isolarRevisao(ativo)) $('#fed-isolar').checked = false;
    msg(ativo ? 'Só a revisão 3D está visível. Ficha, timeline e cálculo continuam da referência.'
      : 'Referência 3D restaurada junto à revisão; dados e filtros preservados.');
  });
  $('#fed-contexto').addEventListener('change', () => {
    const ativo = $('#fed-contexto').checked;
    opcoes.viewer().setAmbienteRevisao(ativo);
    if (ativo) {
      opcoes.viewer().isolarRevisao(true); $('#fed-isolar').checked = true;
      const experiencia = document.querySelector('#v-experiencia');
      experiencia.value = 'apresentacao'; experiencia.dispatchEvent(new Event('change'));
      opcoes.viewer().enquadrarRevisao();
    }
    msg('Ambiente sintético separado do modelo CAD. Terreno e vegetação não fornecem quantitativos.');
  });
  $('#fed-remover').addEventListener('click', () => { opcoes.viewer().mostrarRevisao(null); opcoes.viewer().setAmbienteRevisao(false); $('#fed-contexto').checked = false; $('#fed-contexto').disabled = true; $('#fed-componente').disabled = true; $('#fed-enquadrar').disabled = true; $('#fed-isolar').disabled = true; $('#fed-isolar').checked = false; msg('Sobreposição ocultada; a revisão publicada permanece no acervo desta sessão.'); });
  $('#fed-listar').addEventListener('click', async () => {
    try {
      const r = await api.federacaoListar();
      $('#fed-resultado').innerHTML = (r.revisoes || []).map(x => `<p><button type="button" data-fed-revisao="${esc(x.id)}">${esc(x.source_app)} · ${esc(x.revision)}</button> · ${dataBR(x.termino_depois)}</p>`).join('') || '<p>Nenhuma revisão publicada nesta sessão.</p>';
      $('#fed-resultado').querySelectorAll('[data-fed-revisao]').forEach(b => b.addEventListener('click', async () => {
        try {
          invalidar(); const r = await api.federacaoConsultar(b.dataset.fedRevisao);
          mostrar({ ...r, publicado: true }); $('#fed-carregar-glb').disabled = r.source_app !== 'Blender';
        } catch (e) { falha(e); }
      }));
    } catch (e) { falha(e); }
  });
}
