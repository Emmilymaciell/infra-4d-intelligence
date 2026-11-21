# INFRA 4D INTELLIGENCE

> **PAUSADO — AGUARDANDO REVISÃO DETALHADA DA TITULAR (16/11/2026).**
> Não iniciar desenvolvimento automaticamente. Primeiro receber e consolidar a revisão da titular.
> Estado e preservação: [STATE](STATE.md) (o snapshot de pausa é material interno, não publicado).
> Beta fictício, sem homologação profissional ou autorização para dados reais do Programa.

Plataforma BIM 4D de monitoramento fisico, analise de caminho critico e previsao independente de conclusao para obras rodoviarias e ferroviarias

## O problema

A previsão de término de uma obra linear costuma vir de quem a executa. Este projeto recalcula o prazo **de forma
independente**: a produtividade **medida** nos boletins gera as durações, um motor CPM próprio propaga o efeito pela
rede, e o resultado aparece no painel, no Gantt e no modelo 3D/4D, junto com a explicação auditável de **por que** a
data mudou.

**Como se sabe que está resolvido:** pelo critério de pronto em `project.yaml` → `verificacao.criterio_de_pronto`,
verificado ponta a ponta por `tests/test_vertical_slice.py`.

> **Beta com dados FICTÍCIOS.** A ferrovia, os lotes, os consórcios e os boletins são sintéticos
> (`scripts/infra4d/dados_sinteticos.py`). Nenhum dado real entra antes de nova decisão (ADR-0004).

## Como rodar

```powershell
.\bootstrap.ps1
```

O bootstrap verifica Git, Python, `.env` e estrutura, cria o `.venv` com as dependências, **roda a suíte de testes** e diz o que falta. É idempotente — pode rodar quantas vezes quiser.

Rodar os testes isoladamente:

```powershell
.\tests\run-tests.ps1
```

Um comando só, igual em todo projeto governado pelo Project OS. Saída `0` passou, `1` falhou, `2` **a suíte não rodou** — e `2` não é uma variação de `1`. Ver [tests/README.md](../tests/README.md).

Depois do bootstrap, o comando principal do projeto:

```powershell
.\run-beta.ps1          # abre em http://127.0.0.1:8765/  (API em /docs)
```

Roteiro de demonstração: [docs/DEMO-PESSOA-A.md](DEMO-PESSOA-A.md).

## Estrutura

```
infra-4d-intelligence/
├── CLAUDE.md        como trabalhar neste projeto
├── project.yaml     cartão de identidade (lido por /os:status e /os:handoff)
├── bootstrap.ps1    preparar a máquina
├── run-beta.ps1     sobe o beta local
├── docs/
│   ├── STATE.md     onde o projeto está agora  ← leia primeiro
│   ├── decisions/   por que está assim (ADR-0001..0004)
│   ├── research/    pesquisa de ferramentas e licenças (R04 = verificada)
│   ├── BACKLOG.md   próximos passos, riscos, 5D futuro
│   └── DEMO-PESSOA-A.md
├── scripts/infra4d/ motor CPM, calendários, cenários, painel, Monte Carlo, API, gerador sintético
├── web/             interface (HTML/JS + three.js vendorizado, MIT)
├── examples/synthetic/ base FICTÍCIA versionada
└── tests/           suíte deste projeto  ← rodar com .\tests\run-tests.ps1
```

## Estado

Ver [docs/STATE.md](STATE.md).

## Assumir este projeto

Quem chegar depois — outra pessoa, outra máquina, outro Claude — deve conseguir continuar lendo `docs/STATE.md`, `docs/decisions/` e este README, sem depender de nenhum histórico de conversa.

Se algo essencial só existir na cabeça de alguém ou num chat, isso é um bug do projeto. Gere o documento de transferência com `/os:handoff`.
