# AGENTS.md — INFRA 4D INTELLIGENCE

> Pausa determinada pela titular em 16/11/2026: consulte primeiro o topo de `docs/STATE.md`
> e `docs/SNAPSHOT-PAUSA-2026-11-16.md`. Não iniciar desenvolvimento automaticamente;
> primeiro receber e consolidar a revisão da titular. Este adaptador não substitui o estado canônico.

Adaptador para agentes de código (Codex CLI e outros). O estado canônico é **neutro de provedor** e é declarado no
contrato do projeto no registry do Emmily AI Project OS
(`C:\caminho\exemplo\emmily-ai-project-os\registry\projects\infra-4d-intelligence.yaml`, `ai.canonical`):

1. `docs/STATE.md` — onde o projeto está (leia primeiro);
2. `docs/HANDOFF.md` — como assumir sem nenhuma conversa;
3. `docs/HANDOFF-CODEX.md` — o mesmo, com o foco no Codex: estado verificado, comandos e próximos passos;
4. `docs/decisions/` — o que já foi decidido (ADR-0001 a 0005 e 0011 a 0015; **0006–0010 reservados**, para não
   confundir com os ADR-0006/0007 do Project OS citados no `project.yaml`). Não reabra uma decisão sem motivo técnico
   novo.

`CLAUDE.md` é o adaptador equivalente para o Claude Code. **Nenhum dos dois é fonte de verdade**; se discordarem do
STATE ou de um ADR, valem o STATE e o ADR. Este arquivo não substitui o `CLAUDE.md`.

## Regras de Git (as mesmas do `CLAUDE.md`)

- **Nunca** `git add` / `git commit` / `git tag` por iniciativa própria. Só quando a titular pedir explicitamente
  ("salva essa versão", "commita", `/os:checkpoint`).
- Nunca `git add .` às cegas: `status` → `diff` → varredura de segredos → resumo → `add` seletivo.
- **Nunca** push, `reset --hard`, `checkout --`, `clean -fd`, rebase, amend ou `push --force` sem pedido explícito.
- Não entram no Git: documentos operacionais (`.xlsx`, `.docx`, `.pdf`, `.pptx`), `output/`, `logs/`, imagens
  (`*.png`, `*.gif`), credenciais, `.env`, dados pessoais de terceiros. Dado bruto e evidências vão para o Drive
  (armazenamento externo (fora do Git)), conforme o ADR-0015 da plataforma.

## Ambiente

Windows 11, PowerShell 5.1, **Python 3.13** no `.venv` (a máquina também tem 3.12; não use o do sistema).

| Ação | Comando (na raiz do repositório) |
|---|---|
| Preparar a máquina | `.\bootstrap.ps1` |
| Subir o beta | `.\run-beta.ps1` → http://127.0.0.1:8765/ (API: `/docs`) |
| Suíte de testes | `.\tests\run-tests.ps1` (0 = passou, 1 = falhou, **2 = não rodou**, que não é verde) |
| e2e da interface (Chrome) | `$env:PYTHONPATH="scripts"; .\.venv\Scripts\python.exe tests\e2e\verificar_interface.py` |
| Números da demo | `cd scripts; ..\.venv\Scripts\python.exe -m infra4d.numeros_demo` |

## Como verificar (política do Project OS: `docs/VERIFICATION-POLICY.md` da plataforma)

- **Verificado = executado e observado.** Teste nunca visto falhar não é detector. Critério de aceite e tolerâncias
  vêm do `project.yaml` → `verificacao.limites` (fixture `limite("nome")`); limite ausente faz o teste falhar.
- Código novo em `scripts/` exige teste próprio. Antes de um commit pedido: rode a suíte; depois, verifique o commit
  **isolado** (`git archive -o <tmp>\snap.tar HEAD`, extrair numa pasta vazia, rodar a suíte lá). No PowerShell,
  **não** use `git archive | tar` (o pipe corrompe o tar).
- **Uma suíte completa por vez** (rodadas em paralelo já travaram a máquina).
- **Teste de mutação só em cópia** (import isolado ou monkeypatch), nunca editando o arquivo real (ADR-0015 do
  projeto).
- Defeitos de revisão adversarial nascem como `xfail(strict=True)` em `tests/test_revisao_adversarial_*.py`; quando
  corrigidos viram XPASS, e a marca deve sair.

## Limites deste projeto

- **Todo dado é FICTÍCIO** (ADR-0004 e ADR-0005: `meta.ficticio is True`). Não use dado real sem um ADR novo.
- Não alegue compatibilidade com Primavera P6, MS Project, Bonsai, Revit ou Navisworks: nada foi aberto neles.
- O gabarito do mundo sintético (`examples/synthetic/gabarito/`) só pode ser lido pelo gerador e pelas ferramentas
  de avaliação (ADR-0012); `tests/test_gabarito_isolado.py` acusa o resto.
- Não implemente P2/P3 do backlog sem decisão da titular: mudam os números da demonstração
  (`tests/test_roteiro_demo.py` vai acusar).
