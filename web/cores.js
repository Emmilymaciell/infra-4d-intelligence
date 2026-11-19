// Cor por serviço, por obra: atribuída na ORDEM FIXA da lista de serviços da obra (a cor segue a entidade,
// não muda com filtro). As 8 primeiras usam a paleta categórica validada; acima disso, tons neutros
// distintos (não se gera um 9º matiz) — a identidade também vem do rótulo/tooltip.

const PALETA = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'];
const EXTRA = ['#52514e', '#a39e93', '#7a6a55', '#3f6e75', '#8c8c8c'];
export const COR_OAE = '#12263f';
const COR_RESTO = '#807f7a';

let mapa = new Map();

export function definirServicos(projeto) {
  const ids = (projeto.servicos || []).map(s => s.id);
  for (const a of projeto.atividades || []) {
    if (a.servico_id && !a.oae_id && !String(a.servico_id).startsWith('OAE') && !ids.includes(a.servico_id)) ids.push(a.servico_id);
  }
  mapa = new Map(ids.map((id, i) => [id, i < PALETA.length ? PALETA[i] : EXTRA[i - PALETA.length] || COR_RESTO]));
}

export function corServico(id) {
  if (!id) return COR_RESTO;
  if (String(id).startsWith('OAE')) return COR_OAE;
  return mapa.get(id) || COR_RESTO;
}
