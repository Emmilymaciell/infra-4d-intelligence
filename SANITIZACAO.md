# Sanitização desta versão pública

Cópia sanitizada de um projeto em uso real. Nada aqui é dado de cliente ou de terceiro: o que aparece como exemplo é inventado. Detalhe completo da sanitização: relatório interno da autora.

## O que foi removido

Dado bruto e evidências de demonstração com contexto do cliente.

## O que foi trocado

Cliente → `Consultoria Parceira`; rodovias → `RD-xxx`; citações do repositório privado de origem e da árvore de armazenamento externo → texto genérico.

## O que é fictício

Todos os dados de exemplo e de teste são sintéticos.

## Diferenças de código em relação à origem (19/11/2026)

Correções feitas só nesta versão pública, para a suíte ficar verde em Python 3.12 e sem IfcOpenShell. Nenhuma veio da sanitização; nenhuma asserção foi enfraquecida no ambiente completo.

- `scripts/infra4d/rotas_federacao.py`: JSON aninhado demais levantava `RecursionError` no Python 3.12 e virava 500; agora é 400 como os demais JSON inválidos.
- `requirements.txt`: piso do FastAPI subiu para a versão testada (`>=0.162`); a 0.141 trata corpo JSON `null` como ausente e quebra o contrato de `POST /api/fiscalizacao/validar`.
- `tests/ifc_opcional.py` (novo) e 6 arquivos de teste: o que depende do IfcOpenShell dá SKIP com motivo explícito quando ele não está instalado, como o `requirements.txt` já prometia. Com ele instalado, tudo roda inteiro.

## Imagens

`docs/img/*.png`: capturas da interface com a obra sintética (Edge headless, 19/11/2026). Conferidas uma a uma: só dados fictícios.

## Como verificar

```bat
py -3.12 -m venv .venv && .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m pytest tests -q        # 2236 passed, 6 skipped (navegador), ~12 min
```

Varreduras (2026-11-19): gitleaks `dir` sem vazamentos; busca por caminho local, e-mail, nomes do cliente e links privados sem ocorrências.

## Adendo 2026-11-19 (coordenador)

- Retirados da versão pública por serem material operacional interno (prompts de missão, handoff do Codex, snapshot de pausa, registros de sessão): `INFRA4D_CODEX_PROMPT_MASTER_V3.md`, `docs/HANDOFF-CODEX.md`, `docs/SNAPSHOT-PAUSA-2026-11-16.md`, `docs/missao/`, `docs/sessions/` (preservados fora do repositório). Referências a eles em documentos narrativos podem ficar sem destino.
- Suíte completa reexecutada pelo coordenador no ambiente do `requirements.txt`: **2236 passed, 6 skipped, 0 failed** (skips: `exige navegador`, cobertos pelo E2E).
