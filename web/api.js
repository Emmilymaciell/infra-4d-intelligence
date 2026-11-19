// Cliente da API local. Todas as chamadas passam por aqui para padronizar erros e repassar ?obra=.

export class ErroApi extends Error {
  constructor(mensagem, status = 0) {
    super(mensagem);
    this.status = status;
  }
}

let obraAtual = null; // id da obra; null = padrão do servidor

export function definirObra(id) { obraAtual = id || null; }
export function obraSelecionada() { return obraAtual; }

/** Acrescenta ?obra= (ou &obra=) ao caminho, se houver obra escolhida. */
function comObra(caminho) {
  if (!obraAtual) return caminho;
  return `${caminho}${caminho.includes('?') ? '&' : '?'}obra=${encodeURIComponent(obraAtual)}`;
}

async function req(metodo, caminho, corpo, { semObra = false, bruto = false } = {}) {
  const url = semObra ? caminho : comObra(caminho);
  let r;
  try {
    r = await fetch(url, {
      method: metodo,
      // bruto: o corpo vai como está (File/Blob/ArrayBuffer — ex.: MSPDI .xml ou P6 .xer)
      headers: corpo ? { 'Content-Type': bruto ? 'application/octet-stream' : 'application/json' } : undefined,
      body: corpo ? (bruto ? corpo : JSON.stringify(corpo)) : undefined,
    });
  } catch (e) {
    throw new ErroApi('A API local não respondeu. O servidor está rodando? (uvicorn infra4d.api:app)', 0);
  }
  let dados = null;
  let json = true;
  try { dados = await r.json(); } catch { json = false; /* corpo não-JSON */ }
  if (!r.ok) {
    throw new ErroApi(mensagemDeDetalhe(dados && dados.detail) || `Erro HTTP ${r.status} em ${caminho}`, r.status);
  }
  if (!json) throw new ErroApi(`Resposta inválida da API (não é JSON) em ${caminho}`, r.status);
  return dados;
}

/**
 * Texto legível do `detail` de erro, em qualquer forma que o backend use: texto; lista do pydantic
 * ([{loc, msg}]); ou OBJETO (ex.: importadores: {erro, avisos} / {mensagem}).
 */
export function mensagemDeDetalhe(det) {
  if (det === null || det === undefined) return '';
  if (typeof det === 'string') return det;
  if (Array.isArray(det)) {
    return det.map(d => (d && typeof d === 'object' ? `${(d.loc || []).slice(1).join('.')}: ${d.msg ?? JSON.stringify(d)}` : String(d))).join('; ');
  }
  if (typeof det === 'object') {
    const base = det.erro || det.mensagem || det.message || det.detail;
    const avisos = Array.isArray(det.avisos) && det.avisos.length ? ` (avisos: ${det.avisos.map(String).join('; ')})` : '';
    return base ? `${typeof base === 'string' ? base : JSON.stringify(base)}${avisos}` : JSON.stringify(det);
  }
  return String(det);
}

export const api = {
  federacaoExportar: (sourceApp = 'QGIS') => req('GET', `/api/federacao/exportar?source_app=${encodeURIComponent(sourceApp)}`),
  federacaoReceber: (baseline, revisao, publicar = false) => req('POST', `/api/federacao/revisoes?publicar=${publicar ? 'true' : 'false'}`, { baseline, revisao }),
  federacaoListar: () => req('GET', '/api/federacao/revisoes'),
  federacaoConsultar: (id) => req('GET', `/api/federacao/revisoes/${encodeURIComponent(id)}`),
  obras: () => req('GET', '/api/obras', null, { semObra: true }),
  saude: () => req('GET', '/api/saude'),
  projeto: () => req('GET', '/api/projeto'),
  cenario: (c) => req('GET', `/api/cenarios/${encodeURIComponent(c)}`),
  comparacao: (ref, alvo) => req('GET', `/api/comparacao?ref=${ref}&alvo=${alvo}`),
  simulacao: () => req('GET', '/api/simulacao'),
  simular: (ajustes) => req('POST', '/api/simulacao', { ajustes }),
  limparSimulacao: () => req('DELETE', '/api/simulacao'),
  estado4d: (data, cenario) => req('GET', `/api/estado4d?data=${data}&cenario=${encodeURIComponent(cenario)}`),
  previsaoProbabilistica: (iteracoes = 200) => req('GET', `/api/previsao-probabilistica?iteracoes=${iteracoes}`),
  painel: (lote) => req('GET', lote ? `/api/painel?lote=${encodeURIComponent(lote)}` : '/api/painel'),
  // ---- recursos
  recursosHistograma: (cenario, lote, agrupar = 'semana') =>
    req('GET', `/api/recursos/histograma?cenario=${encodeURIComponent(cenario)}&agrupar=${agrupar}${lote ? `&lote=${encodeURIComponent(lote)}` : ''}`),
  /** capacidades: {"*\/TER": 2, "L1/TER": 3} -> ?capacidade=*\/TER:2&capacidade=L1/TER:3 (repetível). */
  recursosNivelamento: (cenario, capacidades = {}) => {
    const cap = Object.entries(capacidades).map(([k, v]) => `&capacidade=${encodeURIComponent(`${k}:${v}`)}`).join('');
    return req('GET', `/api/recursos/nivelamento?cenario=${encodeURIComponent(cenario)}${cap}`);
  },
  recursosConflitos: (cenario, bufferKm = 1, bufferDias = 0, lote) =>
    req('GET', `/api/recursos/conflitos-balanco?cenario=${encodeURIComponent(cenario)}&buffer_km=${bufferKm}&buffer_dias=${bufferDias}${lote ? `&lote=${encodeURIComponent(lote)}` : ''}`),
  // ---- referência linear (km/estaca/ponto)
  referenciaKm: (km) => req('GET', `/api/referencia/km?km=${encodeURIComponent(km)}`),
  referenciaPonto: (x, y) => req('GET', `/api/referencia/ponto?x=${encodeURIComponent(x)}&y=${encodeURIComponent(y)}`),
  // ---- cronograma externo (MSPDI / P6 XER)
  urlExportarMspdi: (cenario) => comObra(`/api/cronograma/exportar/mspdi?cenario=${encodeURIComponent(cenario)}`),
  /** Baixa o MSPDI exportado como ArrayBuffer (para reenviar ao /comparar no exemplo). */
  exportarMspdi: async (cenario) => {
    let r;
    try { r = await fetch(comObra(`/api/cronograma/exportar/mspdi?cenario=${encodeURIComponent(cenario)}`)); } catch {
      throw new ErroApi('A API local não respondeu.', 0);
    }
    if (!r.ok) {
      let det = null;
      try { det = (await r.json()).detail; } catch { /* corpo não-JSON */ }
      throw new ErroApi(mensagemDeDetalhe(det) || `Erro HTTP ${r.status} ao exportar MSPDI`, r.status);
    }
    return r.arrayBuffer();
  },
  importarCronograma: (corpo) => req('POST', '/api/cronograma/importar', corpo, { bruto: true }),
  compararCronograma: (corpo, cenario) => req('POST', `/api/cronograma/comparar?cenario=${encodeURIComponent(cenario)}`, corpo, { bruto: true }),
  // ---- fiscalização (sintética)
  fiscDiario: (atividadeId) => req('GET', `/api/fiscalizacao/diario?atividade_id=${encodeURIComponent(atividadeId)}`),
  fiscProdutividade: (lote) => req('GET', `/api/fiscalizacao/produtividade${lote ? `?lote=${encodeURIComponent(lote)}` : ''}`),
  fiscConciliacao: (lote) => req('GET', `/api/fiscalizacao/conciliacao${lote ? `?lote=${encodeURIComponent(lote)}` : ''}`),
  fiscLinhaReal: (lote) => req('GET', `/api/fiscalizacao/linha-real${lote ? `?lote=${encodeURIComponent(lote)}` : ''}`),
  fiscValidar: (diario) => req('POST', '/api/fiscalizacao/validar', diario),
  // ---- previsões
  earnedSchedule: (lote) => req('GET', `/api/previsao/earned-schedule${lote ? `?lote=${encodeURIComponent(lote)}` : ''}`),
  /** opcoes: {rho, com_riscos, com_chuva} — qualquer um deles liga a v2 (resposta com v2/faixa_v1/faixa_v2). */
  previsaoProbabilisticaV2: (iteracoes = 200, opcoes = {}) => {
    const q = [`iteracoes=${iteracoes}`];
    if (opcoes.rho != null) q.push(`rho=${opcoes.rho}`);
    if (opcoes.com_riscos) q.push('com_riscos=true');
    if (opcoes.com_chuva) q.push('com_chuva=true');
    return req('GET', `/api/previsao-probabilistica?${q.join('&')}`);
  },
  // ---- modelo IFC (GLB + vínculo GlobalId → atividade)
  urlIfcGlb: () => comObra('/api/ifc/glb'),
  ifcVinculo: () => req('GET', '/api/ifc/vinculo'),
  // ---- análises
  sensibilidade: (p, equipes) => req('GET', `/api/sensibilidade?p=${encodeURIComponent(p)}&equipes=${encodeURIComponent(equipes)}`),
  recuperacao: ({ prazo, marco, folga_max } = {}) => {
    const q = [];
    if (prazo) q.push(`prazo=${encodeURIComponent(prazo)}`);
    if (marco) q.push(`marco=${encodeURIComponent(marco)}`);
    if (folga_max !== undefined && folga_max !== null && folga_max !== '') q.push(`folga_max=${encodeURIComponent(folga_max)}`);
    return req('GET', `/api/recuperacao${q.length ? `?${q.join('&')}` : ''}`);
  },
  massasDiagrama: (passoM) => req('GET', `/api/massas/diagrama?passo_m=${encodeURIComponent(passoM)}`),
  massasCoerencia: () => req('GET', '/api/massas/coerencia'),
  produtividadeTerraplenagem: () => req('GET', '/api/produtividade/terraplenagem'),
  exportarTabelas: () => req('GET', '/api/exportar/tabelas'),
  urlExportarCsv: (tabela) => comObra(`/api/exportar/${encodeURIComponent(tabela)}.csv`),
  urlExportarPacote: () => comObra('/api/exportar/pacote.zip'),
  // ---- DCMA 14 pontos
  dcma: (cenario) => req('GET', `/api/dcma?cenario=${encodeURIComponent(cenario)}`),
  dcmaImportado: (corpo) => req('POST', '/api/dcma/importado', corpo, { bruto: true }),
  // ---- histórico (SINTÉTICO) e cenários salvos
  historicoEvolucao: () => req('GET', '/api/historico/evolucao'),
  cenariosSalvos: () => req('GET', '/api/historico/cenarios-salvos'),
  salvarCenario: (nome, ajustes) => req('POST', '/api/historico/cenarios-salvos', { nome, ajustes }),
  abrirCenarioSalvo: (id) => req('GET', `/api/historico/cenarios-salvos/${encodeURIComponent(id)}`),
  // ---- clima e riscos ao prazo
  clima: (intensidade, deslocamentoSemanas) =>
    req('GET', `/api/clima?intensidade=${encodeURIComponent(intensidade)}&deslocamento_semanas=${encodeURIComponent(deslocamentoSemanas)}`),
  riscos: () => req('GET', '/api/riscos?rapido=true'),
  /** URL (com ?obra=) de uma evidência {rota, params} devolvida por /api/riscos. Só rotas /api/ da própria API. */
  urlEvidencia: (ev) => {
    if (!ev || typeof ev.rota !== 'string' || !ev.rota.startsWith('/api/')) return null;
    const q = Object.entries(ev.params || {}).filter(([k, v]) => k !== 'obra' && v !== null && v !== undefined)
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
    return comObra(`${ev.rota}${q.length ? `?${q.join('&')}` : ''}`);
  },
  // ---- tendência dos marcos (MTA), GIS e XER
  tendencia: () => req('GET', '/api/tendencia'),
  urlGeojson: (camada = 'todas', cenario = 'independente') =>
    comObra(`/api/gis/geojson?camada=${encodeURIComponent(camada)}&cenario=${encodeURIComponent(cenario)}`),
  urlExportarXer: (cenario) => comObra(`/api/cronograma/exportar/xer?cenario=${encodeURIComponent(cenario)}`),
  // ---- curva S física/financeira, backtest e aceleração
  curvaS: (base, lote) => req('GET', `/api/curva-s?base=${encodeURIComponent(base)}${lote ? `&lote=${encodeURIComponent(lote)}` : ''}`),
  backtest: () => req('GET', '/api/backtest'),
  aceleracao: (prazo, limiteExtra) => {
    const q = [`limite_extra=${encodeURIComponent(limiteExtra)}`];
    if (prazo) q.push(`prazo=${encodeURIComponent(prazo)}`);
    return req('GET', `/api/aceleracao?${q.join('&')}`);
  },
  // ---- confiança por marco, revisões de cronograma, IFC com cronograma
  cobertura: () => req('GET', '/api/cobertura'),
  revisoesComparar: (a, b) => req('GET', `/api/revisoes/comparar?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`),
  /** corpo: {a: {conteudo_base64}|{cenario}, b: …, efeitos_isolados: true} — JSON, pois a API não aceita multipart. */
  revisoesCompararArquivos: (corpo) => req('POST', '/api/revisoes/comparar', corpo),
  urlIfcExportar: (incluir4d = true) => comObra(`/api/ifc/exportar?incluir_4d=${incluir4d ? 'true' : 'false'}`),
  // ---- Monte Carlo com incerteza alargada para frente sem medição (P4) e atribuição do erro do backtest
  previsaoP4: (iteracoes = 200, alargamento = 0.5) =>
    req('GET', `/api/previsao-probabilistica?iteracoes=${iteracoes}&incerteza_sem_medicao=true&por_marco=true&alargamento=${encodeURIComponent(alargamento)}`),
  backtestAtribuicao: (marco, data) => req('GET', `/api/backtest/atribuicao?marco=${encodeURIComponent(marco)}&data=${encodeURIComponent(data)}`),
  /** URL do relatório técnico HTML imprimível da obra atual. */
  urlRelatorio: () => comObra('/api/relatorio'),
};
