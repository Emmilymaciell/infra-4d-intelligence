# ADR-0004 — Discovery da PoC: dados só sintéticos, cálculo determinístico, critério de pronto

- **Data:** 2026-11-12
- **Status:** Aceita. Fecha os itens 1 a 4 das pendências de discovery do STATE.

## Contexto

O STATE de nascimento pedia que o discovery fosse fechado antes de entrar material. A missão de execução
entregue pela titular em 2026-11-12 responde a três dos itens.

## Decisão

1. **Critério de pronto:** é o *critério mínimo de aceite do primeiro vertical slice* da missão, gravado em
   `project.yaml` → `verificacao.criterio_de_pronto`. Limite numérico: `tempo_maximo_recalculo_s: 2.0`.
2. **Dados:** só dados **sintéticos**, gerados por `scripts/infra4d/dados_sinteticos.py` (semente fixa e
   premissas versionadas `P-2026.11-a`). Proibido usar dado real nesta fase. Por isso continuam
   `dados_sensiveis: false`, `security_check: false` e `revisao_independente: nenhuma`. **Quando entrar dado real,
   este ADR é substituído** e o manifesto passa para `qa+security`.
3. **Componente de modelo:** a previsão é cálculo determinístico (CPM mais produtividade medida). `componente_llm: false`.
4. **Contratante (fechado em 2026-11-12):** a demonstração é para Pessoa A. A titular declarou que o papel dele
   "não importa" para o projeto, então o ownership fica **inalterado**: Emmily Maciel é titular e criadora, sem
   `employer_or_client`. Rever só se entrar contrato, cliente ou dado de terceiro.
5. **Arquivo de missão:** a missão executada é `docs/missao/INFRA4D_PROMPT_EXECUCAO_COMPLETO.md` (versionado).
   O `INFRA4D_CLAUDE_KICKOFF.md` citado nela não existe e não é necessário.

## Consequências

- A base sintética é versionada em `examples/synthetic/` (CSV e JSON liberados pelo `.gitignore`). Um teste
  garante que ela é idêntica à saída do gerador.
- Todo número fictício tem origem rastreável: semente, fator de desempenho simulado (declarado em `meta`) e boletim.
