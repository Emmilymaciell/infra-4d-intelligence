# ADR-0012 — Gabarito do mundo sintético isolado da previsão

- **Data:** 2026-11-13
- **Status:** Aceita. Atualizada em 2026-11-13 com o P9 (gabarito fora do dataset), já implementado.
- **Numeração:** 0006–0010 ficam reservados para evitar confusão com os ADRs do Project OS citados no manifesto.

## Contexto

O gerador sintético sorteia um fator de desempenho por (lote, serviço). Até o P9, esses fatores eram publicados
no próprio JSON da obra (`meta.fatores_desempenho_simulados`), por transparência de dado fictício. Também sabe recalcular o "futuro" da
obra (`realidade_simulada`), que o backtest usa como referência não circular (`backtest.py`) e a atribuição do erro
usa como verdade (`atribuicao_erro.py`).

Se um módulo de **previsão** lesse esse gabarito, a previsão independente ficaria circular, e o backtest
continuaria "bom" sem ninguém perceber. A r19 mostrou que a primeira guarda (procurar o texto da chave) era
contornável: a chave em pedaços, a varredura do `meta` inteiro e o import do gerador ou da avaliação passavam.

## Decisão

1. Só podem chegar ao gabarito:
   - quem gera: `dados_sinteticos.py`, `dados_sinteticos_rodovia.py` e `sintetico_comum.py`;
   - quem avalia contra a verdade: `backtest.py` e `atribuicao_erro.py`;
   - quem expõe ou exibe a avaliação: `rotas_backtest.py`, `rotas_atribuicao.py` e `relatorio.py`.

   Lista em `PERMITIDOS`, `tests/test_gabarito_isolado.py`.
2. **Duas camadas de proteção:**
   - **guarda estática** (`tests/test_gabarito_isolado.py`): acusa, fora da lista, a chave inteira ou em
     pedaços, o recálculo do futuro, os fatores fixos do gerador, a varredura do `meta` e o import de gerador ou
     avaliação. O detector foi visto falhar contra 8 "trapaças" (`TRAPACAS`);
   - **teste contrafactual** (`tests/test_revisao_adversarial_r19.py`): três mundos com os mesmos dados
     observáveis e gabarito diferente (original; fatores × 0,5; sem os fatores) têm de dar previsões idênticas.
     É a proteção contra caminhos que nenhuma regra textual antecipa.
3. **Gabarito fora do dataset (P9):** os fatores verdadeiros e os términos da realidade simulada saíram de
   `examples/synthetic/*_ficticia.json` (o dataset publicado não tem mais a chave) e foram para
   `examples/synthetic/gabarito/<obra>_gabarito.json`, marcados FICTÍCIOS.
4. **Acessor único** `sintetico_comum.gabarito(dados)`:
   - exige `meta.ficticio is True` e um gerador reconhecido em `meta.gerador`;
   - RECALCULA o gabarito pela `meta.semente` com o próprio gerador, que é a fonte da verdade;
   - se o arquivo publicado é da mesma semente e do mesmo gerador, exige que seja idêntico ao recalculado; senão,
     levanta `ErroGabarito`.

   A atribuição recusa fatores adulterados ou malformados (422).
5. A guarda estática também acusa a **leitura direta do arquivo de gabarito** (`_gabarito.json`, o caminho
   `synthetic/gabarito`, a constante `GABARITO`).

## Alternativas consideradas

- **Só a guarda textual:** descartada. A r19 mostrou cinco contornos.
- **Manter o gabarito dentro do dataset, protegido só pelas guardas:** era a 1ª versão desta decisão.
  Substituída pelo P9 porque as duas camadas não pegavam a leitura direta do JSON do disco (BACKLOG, P9: das 8
  evasões testadas, 6 eram pegas pelo contrafactual).
- **Apagar o gabarito publicado:** descartada. O arquivo fica por transparência de dado fictício, e o acessor o
  confere contra o gerador.

## Consequências

- Um módulo novo de previsão que importe o gerador ou a avaliação, ou que leia o arquivo de gabarito, reprova a
  suíte.
- O formato do dataset mudou uma vez: os hashes dos JSON sintéticos mudaram, e o gabarito ganhou arquivo próprio.
  Backtest, sementes e atribuição deram números idênticos aos de antes, comparados com o HEAD (CHANGELOG, "Alterado
  (P9 …)").
- Resta uma lacuna (BACKLOG, P9): um módulo de previsão consumir **`/api/backtest`** indiretamente é coberto só
  por regra de revisão de código, não por teste.
- O backtest contra a `realidade_simulada` continua não circular **por construção verificada**. Mesmo assim, a
  realidade sintética tem fatores estacionários por (lote, serviço), o que favorece o cenário independente (R12
  §5): um backtest bom aqui é condição necessária, não prova.

## Evidência

- `scripts/infra4d/sintetico_comum.py` (`gabarito`, `ErroGabarito`) e `examples/synthetic/gabarito/`
  (`ferrovia_gabarito.json`, `rodovia_gabarito.json`).
- `tests/test_gabarito_isolado.py`: `test_so_gerador_e_avaliacao_chegam_ao_gabarito` e
  `test_o_detector_acusa_cada_caminho_conhecido` (10 trapaças, inclusive a leitura direta do arquivo).
- `tests/test_dados_rodovia.py`: `test_dataset_publicado_nao_contem_o_gabarito` e
  `test_gabarito_publicado_e_o_do_gerador_e_marcado_ficticio`.
- `tests/test_atribuicao_erro.py`:
  - `test_gabarito_adulterado_e_recusado`;
  - `test_gabarito_ilegivel_obra_nao_ficticia_e_gerador_desconhecido`;
  - `test_gabarito_com_fatores_malformados_e_422`;
  - `test_dataset_publicado_nao_traz_mais_o_gabarito`.
- `tests/test_revisao_adversarial_r19.py`:
  - `test_contrafactual_trocar_o_gabarito_nao_muda_nenhuma_previsao`;
  - `test_hoje_nenhum_modulo_de_previsao_importa_o_gerador_nem_a_avaliacao`;
  - `test_atribuicao_recusa_fatores_que_nao_sao_os_do_gerador`;
  - `test_atribuicao_com_fatores_malformados_e_422`.
- `docs/research/R12-previsao-validacao.md` §5 (limitações) e `docs/BACKLOG.md` P9.
- `CHANGELOG.md` [Não lançado]: "Atribuição do erro da previsão"; Corrigido "Atribuição (r19)"; "Alterado (P9,
  depois da auditoria de 2026-11-13)".
