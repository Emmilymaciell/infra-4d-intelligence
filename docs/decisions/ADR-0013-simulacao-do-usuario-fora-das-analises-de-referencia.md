# ADR-0013 — A simulação do usuário não entra nas análises de referência

- **Data:** 2026-11-13
- **Status:** Aceita
- **Numeração:** 0006–0010 ficam reservados para evitar confusão com os ADRs do Project OS citados no manifesto.

## Contexto

A simulação (`POST /api/simulacao`) cria o cenário "simulado" com os ajustes do usuário. Ela vale uma por processo
e por obra, compartilhada (IR10 no BACKLOG). Várias análises partem de propósito do cenário **independente**
(produtividade medida): clima, aceleração, recuperação, riscos, Earned Schedule, backtest, atribuição, tendência e
o orçamento (EVM sobre linha de base e executado).

Sem aviso, quem simulava e abria essas abas achava que a tela "não atualizou". Se, ao contrário, essas análises
seguissem a simulação, uma hipótese do usuário contaminaria a previsão de referência e o EVM.

## Decisão

1. As análises de referência **não aplicam** a simulação corrente; usam o cenário independente ou a linha de base
   e o executado medido.
2. Toda resposta dessas rotas traz o campo **`simulacao_do_usuario`**. O texto diz que a simulação não foi
   aplicada, por quê, e se há uma ativa (`scripts/infra4d/aviso_simulacao.py`: `simulacao_do_usuario`,
   `com_aviso`). O cache guarda a resposta SEM o aviso, porque o aviso depende do estado atual.
3. O orçamento declara o seu (`orcamento.SIMULACAO_DO_USUARIO`): ajustes de simulação não mudam BAC, PV, EV nem
   AC. A atribuição também declara o seu (`rotas_atribuicao.SIMULACAO_DO_USUARIO`).
4. A interface mostra um **selo "não segue a simulação"** nos blocos correspondentes, conferido contra a API no
   e2e.

## Alternativas consideradas

- **Fazer as análises seguirem a simulação:** descartada. Misturaria hipótese com previsão de referência, e o
  backtest e o EVM perderiam o sentido.
- **Não avisar:** descartada. Era a situação anterior, e a tela parecia desatualizada.

## Consequências

- Uma rota nova que use o cenário independente de propósito precisa incluir o aviso. A cobertura atual é
  conferida rota a rota por `tests/test_simulacao_do_usuario.py`.
- A simulação continua visível onde ela é o objeto: painel do simulado, Gantt, 3D, "Por que o término mudou?" e
  linha de balanço do simulado (e2e).

## Evidência

- `scripts/infra4d/aviso_simulacao.py`; uso em `rotas_aceleracao.py`, `rotas_clima.py`, `rotas_recuperacao.py`,
  `rotas_riscos.py`, `rotas_previsao.py`, `rotas_backtest.py`, `rotas_tendencia.py`, `rotas_atribuicao.py`,
  `rotas_orcamento.py` e outras (grep `simulacao_do_usuario`).
- `tests/test_simulacao_do_usuario.py`: `test_texto_sem_e_com_simulacao` e
  `test_rota_declara_que_a_simulacao_nao_foi_aplicada`.
- `tests/test_orcamento.py::test_resumo_e_curva_declaram_que_nao_usam_a_simulacao`.
- e2e `tests/e2e/verificar_interface.py`: "selo 'não segue a simulação' do cenário do motor conforme a API" e
  "selo 'não segue a simulação' no Monte Carlo, nos riscos e na confiança conforme a API".
- `CHANGELOG.md` [Não lançado]: "`simulacao_do_usuario` nas rotas que usam o cenário independente de propósito,
  com selo na interface".
