# R11 — BDI e reajuste no 5D fictício

> Data: **2026-11-13**. Convenção: **[V]** = visto nesta rodada em documento oficial (URL citada); **[B]** = visto só
> em resumo de busca ou em documento de terceiro que cita a fonte; **[NV]** = não verificado.
> **Nenhuma série real de índice foi baixada nem embutida.** O índice de reajuste do código é SINTÉTICO e está
> marcado FICTÍCIO. Os percentuais de BDI do código são fictícios, escolhidos para ficar dentro da faixa do TCU.
> Implementação: `scripts/infra4d/orcamento.py` (BDI por obra, reajuste, EVM com e sem reajuste); testes em
> `tests/test_orcamento.py`.

## Resumo

1. **Fórmula do BDI (TCU, Acórdão 2622/2013):** `BDI = ((1+AC+S+G+R)·(1+DF)·(1+L)) / (1−I) − 1`. Vista na planilha
   orçamentária do Conselho da Justiça Federal, que a atribui ao acórdão [V]. O exemplo da própria planilha (AC 4%,
   S+G 0,8%, R 1,27%, DF 1,23%, L 7,40%, I 9,15% → **26,93%**) virou teste de regressão do código.
2. **Faixa para "construção de rodovias e ferrovias":** **19,60%** (1º quartil), **20,97%** (médio) e **24,23%** (3º
   quartil) [B]. Os mesmos valores aparecem em planilhas públicas que citam o acórdão; o texto do acórdão no TCU não
   foi aberto.
3. **O BDI antigo do 5D (25%) estava FORA dessa faixa** (acima do 3º quartil). Agora o BDI é **declarado por obra**:
   ferrovia **23,48%** e rodovia **22,22%**, pela fórmula do TCU com componentes fictícios.
4. **Reajuste (IN 01/DNIT/2023, art. 5º):** `R = V × (Ii − I0)/I0`, em que R é a parcela de reajustamento, I0 o
   índice do mês-base, Ii o índice do mês de reajustamento e V o valor a preços iniciais [V]. Os índices do DNIT são
   calculados mensalmente pelo **IBRE/FGV** e divulgados pelo DNIT, **por disciplina** (terraplenagem, drenagem,
   pavimentação, sinalização, OAE, via permanente etc.), e não são intercambiáveis [V].
5. **Data-base e anualidade:** Lei 14.133, art. 25 §7º, exige índice com "data-base vinculada à data do orçamento
   estimado" [V, via TCU]. A Lei 10.192, art. 2º §1º, torna nula a periodicidade inferior a um ano [V, via TCU]. O art.
   92, V, da Lei 14.133 põe data-base e periodicidade entre as cláusulas necessárias do contrato [V, via TCU].
6. **No código:** EV, AC, PV e BAC são calculados **a preços iniciais e com reajuste, lado a lado**.
   - Ferrovia: o 1º aniversário (01/11/2026) é anterior à data de status, então há reajuste no EV (≈ R$ 0,88 mi
     fictícios).
   - Rodovia: o aniversário (01/12/2026) é posterior, então o EV ainda não tem reajuste, e o BAC projetado tem.

## 1. BDI

| Item | Valor | Fonte | Situação |
|---|---|---|---|
| Fórmula | `BDI = ((1+AC+S+G+R) × (1+DF) × (1+L)) / (1−I) − 1` ("FÓRMULA: BDI = (((1+AC+SG+R) X (1+DF) X (1+L)) / (1-I))-1"; "desenvolvido pelo Tribunal de Contas da União - TCU, apresentado no âmbito do acórdão TC 2622/2013") | https://www.cjf.jus.br/cjf/unidades/gestao-de-obras/calculo-do-bdi/view/++widget++form.widgets.arquivo/@@download/Planilha+Or%C3%A7ament%C3%A1ria+-+BDI.pdf | [V] (documento oficial do CJF; o acórdão em si não foi aberto) |
| Exemplo numérico do CJF | AC 4,00%, S+G 0,80%, R 1,27%, DF 1,23%, L 7,40%, I 9,15% (ISS 1%, PIS 0,65%, COFINS 3%, CPRB 4,5%) → **26,93%** | idem | [V], reproduzido no teste `test_bdi_pela_formula_do_tcu_confere_com_planilha_publica` |
| Faixa do BDI, construção de rodovias e ferrovias | 1º quartil **19,60%**, médio **20,97%**, 3º quartil **24,23%** | resumo de busca de planilhas públicas que citam o acórdão (ex.: https://www.pmerechim.rs.gov.br/uploads/licitacoes/adeb15e6001b19f45cb80f5b119aeab7.pdf, https://transparencia.navirai.ms.gov.br/wp-content/uploads/2021/06/bdi.pdf) | [B] |
| Componentes nessa tipologia (1Q / médio / 3Q) | AC 5,29 / 5,92 / 7,93%; S+G 0,25 / 0,51 / 0,56%; R 1,00 / 1,48 / 1,97%; DF 0,94 / 1,02 / 1,33%; L 7,14 / 8,40 / 10,43% | idem (extração de PDF desordenada; uma fonte traz R 1,46 / 2,32 / 3,16%, provavelmente de outra tipologia) | [B] |
| Texto oficial do acórdão | não aberto (a cópia no MPF devolveu HTML) | https://www.mpf.mp.br/o-mpf/unidades/pr-to/transparencia/licitacoes-novo/2016/12Acordao26222013BDI.pdf | [NV] |

**BDI declarado (FICTÍCIO), `orcamento.BDI_COMPONENTES`:**

| Obra | AC | S+G | R | DF | L | I (PIS 0,65 + COFINS 3,00 + ISS 2,00 fictício; sem CPRB) | BDI |
|---|---|---|---|---|---|---|---|
| Ferrovia | 5,5% | 0,5% | 1,3% | 1,0% | 7,5% | 5,65% | **23,48%** |
| Rodovia | 5,0% | 0,5% | 1,2% | 1,0% | 7,0% | 5,65% | **22,22%** |

Todos os componentes caem dentro das faixas [B] por componente acima, e os dois BDIs ficam entre 19,60% e 24,23%. Um
`bdi` explícito na chamada (ex.: `resumo(projeto, bdi=0.25)`) substitui o da obra. Os testes de conta redonda usam
isso. O preço padrão (`preco_venda(comp)`) usa o BDI da obra da composição, para o custo pelo modelo IFC
(`ifc/requisitos.py`) continuar igual ao BAC.

## 2. Reajuste

| Item | Conteúdo | Fonte | Situação |
|---|---|---|---|
| Fórmula e variáveis | R = parcela de reajustamento; I0 = índice do mês-base do contrato; Ii = índice do mês de reajustamento; V = valor a preços iniciais da parcela. No PDF, a fórmula é imagem; a forma `R = V × (Ii − I0)/I0` é a que decorre das variáveis definidas | IN nº 1/DNIT SEDE, de 24/01/2023, art. 5º: https://www.gov.br/dnit/pt-br/assuntos/planejamento-e-pesquisa/custos-referenciais/indices-de-reajustamentos/in-01-2023_indices-de-reajustamento-de-contratos-de-obras.pdf | [V] variáveis; forma algébrica inferida |
| Quem calcula | "sistemática e mensalmente calculados pelo Instituto Brasileiro de Economia da Fundação Getulio Vargas e divulgados pela Coordenação-Geral de Custos de Infraestrutura de Transportes" (art. 2º §1º) | idem | [V] |
| Por disciplina | Obras rodoviárias: terraplenagem, drenagem, sinalização horizontal e vertical, pavimentação, pavimentos de concreto, conservação, OAE com e sem aço, obras complementares (inclui defensas)… Obras ferroviárias: superestrutura de via permanente com e sem fornecimento de material (art. 3º). "não podendo ser, portanto, intercambiáveis entre si" (§2º) | idem | [V] |
| Canteiro e edificações | INCC (art. 4º) | idem | [V] |
| Aplicação legal | contratos sob a Lei 8.666 (c/c Lei 10.192, art. 3º §1º) ou sob a Lei 14.133, art. 25 §§7º e 8º, I (art. 1º, parágrafo único) | idem | [V] |
| Data-base | Lei 14.133, art. 25 §7º: índice "com data-base vinculada à data do orçamento estimado" | https://licitacoesecontratos.tcu.gov.br/6-2-2-1-2-reajuste-em-sentido-estrito/ | [V] (via TCU) |
| Anualidade | Lei 10.192, art. 2º §1º: "É nula de pleno direito qualquer estipulação de reajuste ou correção monetária de periodicidade inferior a um ano"; o TCU: "não deve ser aplicado em prazo inferior a um ano da data-base" | idem | [V] (via TCU) |
| Cláusula necessária | Lei 14.133, art. 92, V: "o preço e as condições de pagamento, os critérios, a data-base e a periodicidade do reajustamento de preços" | idem | [V] (via TCU) |
| Séries reais | **não baixadas** (decisão da tarefa e ADR-0004) | — | — |

**Implementação (fictícia), `orcamento.py`:**
- **Disciplina por serviço** (`DISCIPLINA_REAJUSTE`), com os nomes da IN 01/2023:
  - SUP/TER → TERRAPLENAGEM; DRE → DRENAGEM;
  - SBB/BGS/IMP/CBU → PAVIMENTACAO;
  - SHV/SVV → sinalização horizontal/vertical;
  - DEF/LIB → OBRAS_COMPLEMENTARES;
  - via permanente da ferrovia → VIA_PERMANENTE;
  - OAE → OAE.

  O SUB (sublastro) foi para PAVIMENTACAO por **analogia declarada** (camada granular).
- **Índice sintético:** `I(m) = 100 × (1 + taxa)^m`, com taxas mensais FICTÍCIAS de 0,35% a 0,60% por disciplina
  (`TAXA_MENSAL_FICTICIA`).
- **Data-base:** `meta.data_base_orcamento` ou o 1º dia do mês de início da obra.
- **Anualidade:** no ano k ≥ 1 após a data-base, `Ii` é o índice do k-ésimo aniversário, fixo pelos 12 meses
  seguintes. No 1º ano, R = 0.
- **Valores com reajuste:** cada parcela de PV, EV e AC é multiplicada por `Ii/I0` do dia em que foi (ou seria)
  executada.
  - `resumo()` devolve `evm` (preços iniciais) e `reajuste.evm_com_reajuste`, mais `reajuste_ev_ate_data_status` (=
    R acumulado).
  - `curva_s()` traz `pv/ev/ac` e `pv/ev/ac_reajustado`, além de `bac_reajustado`.

## 3. Verificação (executada)

- Testes novos em `tests/test_orcamento.py`:
  - fórmula do TCU contra o exemplo do CJF (26,93%);
  - BDI da ferrovia e da rodovia calculados à mão e dentro da faixa;
  - preço padrão pelo BDI da obra e BDI explícito;
  - índice e fator de reajuste à mão, inclusive a anualidade (dez/2026 = 1,0; jan/2027 = 1,0045¹²; dez/2027 =
    1,0045¹²; jan/2028 = 1,0045²⁴);
  - EV, PV, AC e BAC com e sem reajuste numa rede à mão;
  - coerência das duas obras com a data-base.
- Os testes antigos de conta redonda passam `bdi=0.25` explícito.
- Resultado: `pytest tests/test_orcamento.py -k "not ifc_exportado"` dá **35 passed**.
- Mutações (uma de cada vez, arquivo restaurado e conferido com `cmp`):

  | Mutação | Testes que caíram |
  |---|---|
  | BDI como soma simples dos componentes | 2 |
  | reajuste proporcional ao mês, sem anualidade | 3 |
  | EV sem reajuste | 2 |
  | preço padrão ignorando o BDI da obra | 2 |

## 4. Impacto em outros arquivos (avisado ao orquestrador)

- `tests/test_revisao_adversarial_r9.py` (do revisor) crava **23,125 R$/m³** (BDI 25%) em
  `test_evm_calculado_a_mao` e `test_ev_do_evm_e_o_executado_vezes_o_preco`. Com o BDI da obra, esses testes passam a
  falhar. A correção mínima é passar `bdi=0.25` em `O.resumo(...)`.
- `ifc/requisitos.py` (custo pelo modelo) usa `preco_venda(comp)` sem BDI. Ele continua coerente, porque o padrão
  agora é o BDI da obra da composição, o mesmo do BAC.
- O BAC fictício das obras muda (ferrovia ≈ R$ 497,9 mi; rodovia ≈ R$ 214,7 mi, a preços iniciais).
  `numeros_demo` lê da API, e o roteiro da demo não cita BAC.

## 5. Para o BACKLOG

```markdown
| BR1 | Ler o texto oficial do Acórdão 2622/2013 no TCU e confirmar a faixa de rodovias e ferrovias (hoje [B]) | tabela com página citada | — |
| BR2 | Com dado real: BDI do contrato (proposta) em vez do declarado; alerta se fora da faixa do TCU | teste com BDI fora da faixa → aviso | ADR de dado real |
| BR3 | Com dado real: índices DNIT/FGV por disciplina lidos de arquivo fornecido pelo usuário (sem embutir série) | R = V × (Ii − I0)/I0 conferido com um reajuste real publicado | ADR de dado real |
```
