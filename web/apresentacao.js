// Aba de apresentação: conceito, o que é real e o que é simulado, fluxo do cálculo.

import { estado } from './estado.js';
import { esc, dataBR, num } from './util.js';

export function renderApresentacao(el, saude) {
  const p = estado.projeto;
  const m = p ? p.meta : {};
  const nAtiv = p ? p.atividades.length : 0;
  const nTarefas = p ? p.atividades.filter(a => a.tipo === 'tarefa').length : 0;
  el.innerHTML = `
    <h2>O que é o INFRA 4D INTELLIGENCE</h2>
    <p>Uma plataforma de <b>monitoramento físico 4D</b> para obras lineares (rodovias e ferrovias): liga o cronograma
      ao modelo 3D do trecho, mede o que foi executado, identifica o <b>caminho crítico</b> e produz uma
      <b>previsão independente de conclusão</b> — calculada a partir da produtividade efetivamente medida em campo,
      e não da produtividade que o planejamento assumiu.</p>
    <p class="erro" style="background:#fff8e1;border-color:#ffd24a;color:#4a3900">
      <b>Todos os dados desta demonstração são fictícios</b> — ${esc(m.aviso || 'gerados sinteticamente')}
      ${saude ? ` · API ${esc(saude.versao)}` : ''}</p>

    <h3>Do campo ao término: o fluxo do cálculo</h3>
    <div class="fluxo">
      <div class="passo"><b>Produtividade</b><small>medida nos boletins (unid./equipe·dia) — ou a planejada, no cenário da construtora</small></div>
      <div class="seta">→</div>
      <div class="passo"><b>Duração</b><small>remanescente ÷ (produtividade × equipes), em dias úteis do calendário</small></div>
      <div class="seta">→</div>
      <div class="passo"><b>Rede (CPM)</b><small>predecessoras FS/SS com defasagem, restrições, datas reais</small></div>
      <div class="seta">→</div>
      <div class="passo"><b>Caminho crítico</b><small>folga total, cadeia determinante, motivo de início</small></div>
      <div class="seta">→</div>
      <div class="passo"><b>Término</b><small>data prevista + comparação entre cenários, explicada atividade a atividade</small></div>
    </div>

    <div class="cartoes-2">
      <div class="cartao">
        <h3 style="margin-top:0">O que é real (funciona de verdade)</h3>
        <ul>
          <li>O <b>motor de cálculo</b>: CPM com calendários, relações FS/SS, folgas total/livre e cadeia determinante.</li>
          <li>A <b>memória de cálculo</b> de cada atividade (fórmula, fonte da produtividade, motivo do início).</li>
          <li>A <b>comparação de cenários</b> e a explicação de por que o término mudou.</li>
          <li>A <b>simulação</b>: alterar produtividade/equipes recalcula a rede inteira.</li>
          <li>O <b>estado 4D</b> por data (fração executada vs linha de base) que colore o modelo.</li>
        </ul>
      </div>
      <div class="cartao">
        <h3 style="margin-top:0">O que é simulado (fictício)</h3>
        <ul>
          <li>A obra (${p && p.obra && p.obra.tipo ? esc(p.obra.tipo) : 'tipo não declarado'}${p && p.ferrovia ? ` “${esc(p.ferrovia.nome)}”` : ''}), os ${p ? p.lotes.length : 3} lotes, as construtoras e as OAEs — inventados.</li>
          <li>O alinhamento (${p && p.ferrovia ? num(p.ferrovia.extensao_km, 0) : '—'} km) e a <b>geometria 3D</b>: esquemática, gerada a partir do eixo; não é modelo BIM de projeto.</li>
          <li>As quantidades, a linha de base e os boletins de medição — gerados por semente (${esc(m.semente ?? '—')}).</li>
          <li>Os fatores de desempenho que “produziram” os boletins são ocultos do motor (ele não vê o futuro).</li>
        </ul>
      </div>
    </div>

    <h3>Os quatro cenários</h3>
    <table class="tab" style="max-width:900px"><tbody>
      <tr><th>Linha de base</th><td>O plano contratado: datas e produtividades planejadas.</td></tr>
      <tr><th>Construtora</th><td>Datas reais até a data de status; remanescente projetado com a produtividade <b>planejada</b>.</td></tr>
      <tr><th>Independente</th><td>Datas reais até a data de status; remanescente projetado com a produtividade <b>medida</b> (atividade → serviço no lote → serviço na obra → planejada).</td></tr>
      <tr><th>Simulado</th><td>Independente + os ajustes “e se” feitos na aba Simulação.</td></tr>
    </tbody></table>

    <h3>Dados deste exemplo</h3>
    <p>${nAtiv} atividades (${nTarefas} tarefas), ${p ? p.relacoes.length : 0} relações, ${p ? p.oaes.length : 0} obras de arte especiais.
      Início: <b>${dataBR(m.inicio_projeto)}</b> · término da linha de base: <b>${dataBR(m.termino_linha_base)}</b> ·
      data de status: <b>${dataBR(m.data_status)}</b> · premissas ${esc(m.versao_premissas || '—')}.</p>

    <h3>Como usar</h3>
    <ol style="line-height:1.6">
      <li><b>Painel</b>: avanço real vs planejado, términos dos cenários, alertas, produtividade e curva S.</li>
      <li><b>Modelo 3D/4D</b>: arraste a linha do tempo (ou ▶) e veja a obra avançar; clique numa peça para ver a memória de cálculo.</li>
      <li><b>Cronograma</b>: Gantt com linha de base, parte executada, caminho crítico e dependências da atividade selecionada.</li>
      <li><b>Simulação</b>: mude a produtividade de uma atividade crítica e de uma com folga — e compare o efeito no término.</li>
    </ol>
    <p style="color:var(--texto-3);font-size:12px">Os filtros do topo (lote, disciplina, serviço, só caminho crítico, cenário) valem para o Gantt, a tabela e o 3D; o filtro de lote também recarrega o painel. ${p && p.ferrovia ? num(p.ferrovia.extensao_km, 0) : '—'} km de eixo; no 3D, a seção transversal é exagerada (padrão 40×) para ficar visível.</p>`;
}
