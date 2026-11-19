# ADR-0001 — Nascimento protegido

- **Data:** 2026-11-12
- **Status:** Aceita

## Contexto

Projeto criado por `eos new`: um projeto novo nunca nasce L0 (só local).

## Decisão

1. Workspace `${AI_WORKSPACE}\work\parceira\infra-4d-intelligence`, fora de pasta sincronizada.
2. Git em `main` desde o primeiro commit; remoto GitHub **privado**: (repositório privado de origem).
3. Dado bruto no armazenamento externo de dados brutos (fora do Git), nunca no Git.
4. Estado canônico neutro de provedor em `docs/STATE.md` e `docs/HANDOFF.md`; `CLAUDE.md` e `AGENTS.md` são adaptadores.
5. Titularidade declarada em `OWNERSHIP.md`, `PROVENANCE.md` e `AUTHORS.md`.

## Consequências

- Alvo de portabilidade L6: falta só a certificação por restauração (`eos certify infra-4d-intelligence`).
