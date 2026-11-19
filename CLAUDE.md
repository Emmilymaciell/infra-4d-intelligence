# INFRA 4D INTELLIGENCE

> Pausa determinada pela titular em 16/11/2026: consulte primeiro o topo de `docs/STATE.md`
> e `docs/SNAPSHOT-PAUSA-2026-11-16.md`. Não iniciar desenvolvimento automaticamente;
> primeiro receber e consolidar a revisão da titular. Este adaptador não substitui o estado canônico.

Plataforma BIM 4D de monitoramento fisico, analise de caminho critico e previsao independente de conclusao para obras rodoviarias e ferroviarias

## Antes de mudar qualquer coisa

Leia `docs/STATE.md` (onde o projeto está) e `docs/decisions/` (o que já foi decidido).
**Não reabra decisão registrada sem motivo técnico novo.**

## Regra de ouro do Git

Nunca `git add` / `git commit` / `git tag` por iniciativa própria. Só quando a Emmily pedir explicitamente ("salva essa versão", "commita", `/os:checkpoint`).

Nunca `git add .` às cegas: `status` → `diff` → varredura de segredos → resumo → `add` seletivo.

## O que NUNCA entra no Git deste projeto

<!-- Ajustar por projeto. O padrão abaixo é conservador de propósito. -->
- Documentos operacionais (`.xlsx`, `.docx`, `.pdf`, `.pptx`) — o `.gitignore` já bloqueia.
- Saídas de execução (`output/`, `logs/`).
- Credenciais, tokens, `.env`, caches de autenticação.
- Dados pessoais de terceiros.

## Ciclo de trabalho

```
INSPECT → PLAN → EXPLAIN → APPROVAL → IMPLEMENT → TEST → QA → SECURITY
→ DIFF → UPDATE STATE → CHECKPOINT → NEXT STEP
```

## Verificação deste projeto

- **Tests:** suíte de fumaça do contrato em `tests/` (pytest no `.venv`); código novo em `scripts/` exige teste próprio — rodar com `.\tests\run-tests.ps1` (o comando é o mesmo em todo projeto; o valor canônico está em `project.yaml` → `verificacao.comando`)
- **Evals:** não se aplica: nenhuma saída depende de julgamento de modelo (componente_llm false); reavaliar se mudar
- **Security check:** `/os:security` antes de push, release ou handoff; nenhum dado sensível declarado
- **Revisão independente:** nenhuma — derivada da criticidade, ver ADR-0007

A regra do que conta como verificado é do Project OS, não deste projeto: `docs/VERIFICATION-POLICY.md`. O resumo que importa aqui: **verificado = executado e observado**. Comando documentado e nunca rodado não conta; teste que nunca foi visto falhar não é detector.

**Critério de aceite vem do manifesto, nunca de um número cravado na asserção.** Declare em `project.yaml` → `verificacao.criterio_de_pronto` e `verificacao.limites`, e leia com a fixture `limite("nome")` (Python) ou `Get-LimiteDoManifesto` (PowerShell). Limite ausente faz o teste **falhar**, não passar. Ver `tests/README.md`.

**Saída `2` da suíte significa que ela não rodou** — terceiro estado, não uma variação de falha. Não trate como verde.

## Ambiente

Windows 11, PowerShell 5.1. Python **3.13** (a máquina tem 3.12 e 3.13 — não deixar implícito qual). Para scripts COM/Office, usar scratchpad em `Temp`, **nunca** pasta sincronizada pelo OneDrive.

## Decisões

Registrar em `docs/decisions/ADR-NNNN-titulo.md`. Referenciar o ADR na mensagem de commit quando a mudança implementar uma decisão.

## Estado canônico

Neutro de provedor: `docs/STATE.md`, `docs/HANDOFF.md` e `docs/decisions/`. Este arquivo e o `AGENTS.md` são adaptadores.
