# ADR-0014 — `tipo_obra` declarado, sem padrão silencioso

- **Data:** 2026-11-13
- **Status:** Aceita
- **Numeração:** 0006–0010 ficam reservados para evitar confusão com os ADRs do Project OS citados no manifesto.

## Contexto

Composições, BDI, reajuste, seção de terraplenagem, classes IFC, georreferência e nome do arquivo exportado
dependem do tipo da obra (ferrovia ou rodovia). Até a missão, `api`, `gis`, `exportacao`, `persistencia`,
`massas`, `rotas_backtest`, `rotas_referencia`, `xer_exportar` e `ifc/exportar` faziam
`meta.get("tipo_obra", "ferrovia")`.

Assim, uma obra sem tipo, ou com tipo errado, era tratada como ferrovia **sem erro**. O próprio
`ferrovia_ficticia.json` não declarava `meta.tipo_obra` até 2026-11-13: funcionava só por causa do padrão.

## Decisão

1. Um helper ÚNICO em `scripts/infra4d/obra.py`: `tipo_obra(dados_ou_projeto)`, `TIPOS_OBRA = ("ferrovia",
   "rodovia")` e `ErroTipoObra`. Tipo ausente, vazio, não-texto ou desconhecido é ERRO; nenhum módulo "assume
   ferrovia".
2. As rotas que dependem do tipo respondem **422 com o motivo**. `/api/obras` lista a obra mal declarada com
   `tipo: null`, em vez de escondê-la ou assumir ferrovia.
3. Os módulos com erro próprio convertem o erro sem perder a mensagem. O orçamento faz `ErroTipoObra →
   ErroOrcamento` (`orcamento.tipo_obra`), e as rotas do orçamento passam o tipo por `_executar`, inclusive
   `/classificacao-ifc` (r21).
4. O gerador da ferrovia declara `meta.tipo_obra = "ferrovia"`, como o da rodovia já fazia.
5. Uma guarda estática impede o padrão de voltar.

## Alternativas consideradas

- **Manter o padrão "ferrovia":** descartada. Esconde dado mal declarado e é incompatível com o ADR-0005, que
  prefere a marca explícita à dedução.
- **Deduzir o tipo de outro campo** (`ferrovia.tipo`, nome da obra): descartada pelo mesmo motivo. É dedução por
  convenção, e a ferrovia não tinha esse campo.
- **Corrigir módulo a módulo sem helper:** descartada. Nove leituras divergentes do mesmo campo.

## Consequências

- Dataset sem `meta.tipo_obra` deixa de funcionar nas rotas que dependem do tipo, e isso é intencional. O hash do
  `ferrovia_ficticia.json` mudou uma vez.
- Testes que montavam dado à mão sem `tipo_obra` precisaram declará-lo (`tests/test_orcamento.py`,
  `tests/test_aceleracao.py`).

## Evidência

- `scripts/infra4d/obra.py`.
- `tests/test_obra_tipo.py`:
  - `test_helper`;
  - `test_helper_aceita_projeto_e_recusa_sem_meta`;
  - `test_nenhum_modulo_assume_ferrovia_por_padrao` (guarda estática);
  - `test_rota_com_obra_sem_tipo_e_422_claro`;
  - `test_mesmas_rotas_funcionam_com_o_tipo_declarado`;
  - `test_lista_de_obras_nao_esconde_as_outras_nem_assume_ferrovia`;
  - `test_historico_sem_obra_explicita_e_422_e_com_obra_funciona`.
- `tests/test_orcamento.py`: `test_obra_sem_tipo_obra_e_erro_nunca_ferrovia_por_padrao` e
  `test_classificacao_ifc_com_tipo_invalido_e_422`.
- `tests/test_revisao_adversarial_r21.py`.
- `docs/BACKLOG.md` P8 e `CHANGELOG.md` [Não lançado] → "Alterado (P8 e P10)".
