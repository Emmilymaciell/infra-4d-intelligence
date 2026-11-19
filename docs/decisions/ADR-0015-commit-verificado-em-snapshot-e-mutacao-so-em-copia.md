# ADR-0015 — Processo: commit verificado em snapshot isolado e mutação só em cópia

- **Data:** 2026-11-12 (snapshot isolado) e 2026-11-13 (mutação só em cópia)
- **Status:** Aceita (regra de processo com vários agentes editando o mesmo repositório)
- **Numeração:** 0006–0010 ficam reservados para evitar confusão com os ADRs do Project OS citados no manifesto.

## Contexto

Na missão autônoma, vários agentes editaram o mesmo diretório de trabalho em paralelo. Quatro fatos registrados no
`docs/STATE.md` e no `docs/missao/RELATORIO-MISSAO-AUTONOMA.md` §6:

1. Um commit (`d70bd52`) capturou um arquivo no meio de um teste de mutação de outro agente. O diretório de
   trabalho passava; só o snapshot do commit falhava.
2. O `d8446a3` levou os testes estáticos da r7, que leem `web/`, sem o `web/` corrigido: 12 falhas no snapshot
   isolado. O `9577865` fechou a inconsistência, sem reescrever o histórico.
3. A primeira verificação do `f73d199` não rodou: `git archive | tar` pelo pipe do PowerShell corrompe o tar.
4. Agentes faziam teste de mutação editando o arquivo REAL por segundos e restaurando. A r17 viu um Δ=0 falso na
   cobertura, provavelmente por isso (não reproduzido).

Três suítes completas rodando em paralelo também travaram com 0% de CPU (STATE, "Incidente").

## Decisão

1. **Congelar com o dono** os arquivos que entram no commit antes de commitar. O commit continua exigindo pedido
   explícito da titular (`CLAUDE.md`).
2. **Verificar o commit isolado, não o diretório de trabalho:** `git archive -o <arquivo>.tar <commit>` (nunca
   pelo pipe no PowerShell), extração em pasta vazia fora do repositório e a suíte completa lá, com
   `INFRA4D_SEM_REDE=1`. O resultado de cada snapshot vai para o `docs/STATE.md`.
3. **Uma suíte completa por vez** (e um processo pesado por vez, suíte ou e2e). `pytest.ini` tem
   `faulthandler_timeout = 300` para que um travamento imprima a pilha.
4. **Teste de mutação só em cópia:** carregar uma cópia por import isolado ou aplicar monkeypatch em memória
   (por exemplo, um plugin pytest carregado com `-p` fora do repositório). **Nunca** editar o arquivo real, nem
   por segundos. Conferir por hash que o arquivo ficou intocado.

## Alternativas consideradas

- **Verificar no diretório de trabalho:** descartada. Foi o que deixou passar os casos 1 e 2.
- **`git worktree` por commit:** não adotada. O guarda de Git da plataforma bloqueia `worktree remove --force`, e o
  contrato preserva worktrees; o `git archive` não cria worktree.
- **Mutação no arquivo real com backup + restauração + `cmp`:** descartada. A janela de segundos basta para outro
  agente ler, testar ou commitar o arquivo mutado (caso 4).

## Consequências

- Cada checkpoint custa ~10 min de suíte no snapshot (STATE: 10–11 min no `682c4a0`, `670a040` e `41cdb42`).
- A partir do `682c4a0`, todos os snapshots registrados deram exit 0 e 0 xfail; o `41cdb42` deu 1895 passando e
  29 pulados.
- A causa raiz do travamento em paralelo segue não achada (IR14 no BACKLOG).

## Evidência

- `docs/STATE.md` (registro da missão: snapshots por commit, "Incidente de processo (13/11)", travamento em
  paralelo) e `docs/missao/RELATORIO-MISSAO-AUTONOMA.md` §6–§7.
- `pytest.ini` (`faulthandler_timeout`).
- `CHANGELOG.md` [Não lançado] → Corrigido (rodadas 17 e 18), "Processo".
