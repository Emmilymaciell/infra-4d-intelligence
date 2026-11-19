# ADR-0011 — BDI pela fórmula do TCU, declarado por obra, e reajuste com anualidade

- **Data:** 2026-11-13
- **Status:** Aceita (5D fictício). Reavaliar ao entrar orçamento real.
- **Numeração:** 0006–0010 ficam reservados para evitar confusão com os ADRs do Project OS citados no manifesto.

## Contexto

O 5D sintético (`scripts/infra4d/orcamento.py`, ADR-0004: só dado fictício) usava um BDI único de 25% para
qualquer obra. A pesquisa R11 (`docs/research/R11-bdi-reajuste.md`) mostrou que esse valor fica **acima do 3º
quartil** da faixa do TCU para "construção de rodovias e ferrovias". A faixa do Acórdão 2622/2013 é 19,60% (1º
quartil), 20,97% (médio) e 24,23% (3º quartil), vista em planilhas públicas que citam o acórdão ([B] no R11). O
texto do acórdão não foi aberto.

O EVM de custo também não tinha reajuste. A IN 01/DNIT/2023 (art. 5º) define `R = V × (Ii − I0)/I0`, com índices
por disciplina, e a lei exige periodicidade anual a partir da data-base (Lei 10.192, art. 2º §1º; Lei 14.133, art.
25 §7º). Essas fontes estão no R11 §2, com [V] e URL.

A revisão adversarial r17 achou quatro defeitos na primeira versão:
- anualidade contada por mês, ignorando o dia;
- data-base inválida dava 500;
- tipo de obra sem composição dava 500;
- a nota do BDI descrevia o BDI da obra quando a chamada passava outro.

O mesmo trabalho incorporou a recusa de BDI inválido (NaN e negativo eram aceitos).

## Decisão

1. **BDI declarado por obra** em `BDI_DECLARADO`, calculado por `bdi_tcu(c) = (1+AC+S+G+R)·(1+DF)·(1+L)/(1−I) − 1`.
   Os componentes são FICTÍCIOS, escolhidos dentro da faixa: ferrovia 23,48% e rodovia 22,22%. Cada declaração
   leva a marca `ficticio: True` e a fonte (`_FONTE_BDI`).
2. O BDI **nunca é deduzido do texto** do código da composição. O tipo vem da CHAVE de `COMPOSICOES`, gravada em
   `comp["tipo_obra"]`, e tipo sem declaração é ERRO (`ErroOrcamento`), nunca valor padrão.
3. Um BDI explícito (`bdi=`) substitui o declarado. Precisa ser número real finito e ≥ 0 (`validar_bdi`), e a
   nota (`bdi_nota`) passa a dizer que o BDI foi informado e qual.
4. **Reajuste por índice SINTÉTICO por disciplina** (`TAXA_MENSAL_FICTICIA`, `indice_sintetico`), com
   anualidade pela **data inteira** (`anos_completos`): o aniversário é o mesmo dia e mês da data-base. Uma
   data-base em 29/02 completa o ano em 01/03 nos anos não bissextos.
5. A data-base vem de `meta.data_base_orcamento` (texto AAAA-MM-DD). Valor malformado é `ErroOrcamento` (422);
   se o campo estiver ausente, vale o dia 1 do mês de início.
6. EV, PV, AC e BAC são calculados **a preços iniciais e reajustados, lado a lado** (`resumo`, `curva_s`).

## Alternativas consideradas

- **Manter 25% único:** descartada. Fica fora da faixa do TCU (R11 §1).
- **Deduzir o tipo de obra do texto do código** (`FIC-FER-…`): descartada. Por convenção textual, um código mal
  escrito muda o preço sem erro.
- **Usar a série real dos índices DNIT/FGV ou a base SICRO:** descartada no beta. Seria dado real (ADR-0004), e a
  base SICRO está sob CC BY-ND 3.0 (R05). Nenhuma série real foi baixada ou embutida (R11, cabeçalho).
- **Anualidade por mês** (versão inicial): era o defeito da r17. Reajustava antes de completar 12 meses quando a
  data-base não era dia 1.

## Consequências

- Os números da demo que dependem do custo mudaram uma vez (BAC e aceleração, por exemplo). O roteiro é conferido
  por `tests/test_roteiro_demo.py` e `tests/test_numeros_demo.py`.
- Fica declarado na lista do que é sintético: BDI e índice de reajuste não são de contrato nem do DNIT
  (`docs/ARQUITETURA.md` §7, item 9).

## Evidência

- `scripts/infra4d/orcamento.py`: `BDI_DECLARADO`, `bdi_tcu`, `FAIXA_BDI_TCU`, `validar_bdi`, `bdi_nota`,
  `data_base`, `anos_completos` e `fator_reajuste`.
- `tests/test_orcamento.py`:
  - `test_bdi_pela_formula_do_tcu_confere_com_planilha_publica`, que reproduz os 26,93% do exemplo da planilha
    pública;
  - `test_bdi_declarado_com_fonte_e_marca_e_sem_deducao_por_texto`;
  - `test_preco_padrao_usa_o_bdi_da_obra_e_bdi_explicito_substitui`;
  - `test_indice_e_fator_de_reajuste_a_mao`;
  - `test_anualidade_pela_data_inteira`;
  - `test_bdi_explicito_invalido_e_recusado`;
  - `test_data_base_invalida_e_erro_de_orcamento_e_422`.
- `tests/test_revisao_adversarial_r17.py` (rodada 17), `docs/research/R11-bdi-reajuste.md` e `CHANGELOG.md`
  ([Não lançado] → Adicionado "BDI por obra pela fórmula do TCU"; Corrigido "Orçamento (r17)").
