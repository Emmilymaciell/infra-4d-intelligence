# R14 — Auditoria do roteiro da demo (docs/DEMO-PESSOA-A.md) contra o sistema de 2026-11-13

> Data: 2026-11-13. Nenhum código foi editado e nada foi feito no git.
>
> **Método.** Rodei `python -m infra4d.numeros_demo` e `--json`, a partir de `scripts/`, com o `.venv`: 25 módulos
> ligados, nenhum indisponível, ~52 s. Depois chamei in-process (TestClient sobre `api.criar_app()`) as rotas que o
> roteiro cita e as novas:
> `/api/recuperacao`, `/api/aceleracao`, `/api/tendencia`, `/api/backtest`, `/api/cobertura`,
> `/api/orcamento/resumo`, `/api/riscos?rapido=true`, `/api/dcma`, `/api/recursos/conflitos-balanco`,
> `/api/historico/evolucao` e `/api/ifc/exportar`. O IFC foi aberto com ifcopenshell.
>
> Legenda: **✔ confere** · **✘ diverge** (com o valor atual) · **? não verificável** por esta via (exige navegador,
> tela ou leitura humana).

## 0. Resumo

- Quase todos os números da ferrovia e da rodovia **conferem** com a execução de hoje, inclusive os que mudaram
  hoje: recuperação "só com mudança de método", aceleração 25/05/2027 por R$ 1,71 mi e as 4 frentes do FAQ.
- **Divergências reais (4):**
  - contagem de IfcTask: o arquivo tem 113 × 3 cronogramas;
  - número de rodadas de revisão adversarial: 17, não 11;
  - data e duração do `numeros_demo`;
  - o comando de regeneração **quebra com saída redirecionada** no Windows (cp1252).
- **Frágeis:**
  - o alerta da rodovia apoiado em **1 boletim**;
  - a frase "+46% sobre a melhor semana", também de 1 semana, e que não é o maior multiplicador do plano.
- **Novos que valem entrar:**
  - cobertura da rodovia: M-FIM "baixa", com o CBUQ do L3 por analogia;
  - backtest da ferrovia L1: MAE de 55 contra 8 dias;
  - MTA da rodovia, em que a divergência começa no 1º boletim de CBUQ do L2;
  - BDI por obra dentro da faixa do TCU;
  - aceleração da rodovia: R$ 3,79 mi.

## 1. Cabeçalho e "como iniciar"

| Afirmação | Situação | Valor atual / nota |
|---|---|---|
| Números lidos pelo `numeros_demo.py`, "executado em 12/11/2026" | ✘ | Reexecutado em **13/11/2026**. Atualizar a data. |
| "Leva cerca de 40 s" | ✘ (leve) | **~52 s** medidos, com a máquina dividida com outros agentes. Dizer "menos de 1 minuto". |
| Comando `..\.venv\Scripts\python.exe -m infra4d.numeros_demo` | ✘ (frágil) | No console funciona. **Com a saída redirecionada para arquivo ou pipe**, termina em `UnicodeEncodeError: 'charmap' codec can't encode character '→'` (exit 1). Com `$env:PYTHONIOENCODING="utf-8"` roda, exit 0. Acrescentar essa linha ao roteiro, ou o script deve forçar UTF-8 (fica para o dono do script). |
| 2 obras fictícias, `meta.ficticio: true` | ✔ | `ficticio: true` nas duas. |
| `/docs` documenta a API | ✔ | 25 módulos ligados. |
| Tour com "uns 13 passos" | ✔ | `web/tour.js` tem 13 entradas `titulo`, incluindo "O mesmo motor numa {tipo}". O comportamento na tela é **?**. |

## 2. Parte 1 — ferrovia

| # | Afirmação do roteiro | Situação | Valor atual |
|---|---|---|---|
| 1 | 60 km, 3 lotes, 113 atividades, 264 relações; status 09/11/2026 | ✔ | idem |
| 2 | Construtora 23/07/2027; independente 09/09/2027; +48 d; avanço 71,69 % × 80,9 % | ✔ | idem |
| 3 | "L3-S03-TER é CRÍTICA e produz 78% do planejado (… 6 boletins)" | ✔ | idem |
| 4 | ES: SPI 0,884 → 11/08/2027, 29 d antes do CPM | ✔ | SPI 0,8837; −29 d |
| 4 | MC: P50 10/09, P80 13/09/2027, faixa P10–P90 10 d | ✔ | idem (200 iterações) |
| 4 | Criticidade 100 % em L3-S04-LAS, L3-S04-TER, L3-S03-TER | ✔ | idem |
| 5–6 | 10 atividades críticas | ✔ (número) / ? (contorno no 3D) | `n_criticas` = 10 |
| 5–6 | Seletor "Modelo IFC (GLB)" | ? | Precisa de navegador. |
| 7 | L3-S04-TER a 1.500 m³/eq·dia → 06/10/2027 (+27) | ✔ | +27 (o ajuste usa 2 equipes, como no script) |
| 8 | L2-S04-LAS a 250 → +0 | ✔ | +0 |
| D1 | 21 grupos, 64 execuções; TER L3: +21 / −17 / +1 equipe −62 | ✔ | idem |
| D2 | Prazo 27/05/2027 alcançável com plano mínimo de **6 frentes do L3**, só com mudança de método | ✔ | `viabilidade = inviavel_sem_mudanca_de_metodo`, 6 frentes, todas do L3 |
| D2 | "até **1,8×** a melhor semana já medida" | ✔ | L3-S03-TER 1,826×; L3-S04-TER 1,657× |
| D2 | Aceleração chega a **25/05/2027** por **R$ 1,71 mi** | ✔ | 2027-05-25, R$ 1.714.224,90 (fictício), 4 ajustes finais, verificação `confere: true` |
| 9 | 8 conflitos previstos, 0 reais | ✔ | idem |
| 10 | MSPDI da construtora 23/07/2027 × 09/09/2027, +48, 39 atividades diferentes | ✔ | idem |
| D3 | DCMA: 6 aprovados, 7 reprovados, 1 não avaliado; lags 63,6 % | ✔ | 6/7/1; lags 63,64 % (77 de 121 relações vivas) |
| 11 | Relatório imprimível | ? | Precisa de navegador. |

## 3. Parte 2 — rodovia

| Afirmação | Situação | Valor atual |
|---|---|---|
| 48 km, 3 lotes, 137 atividades, 301 relações | ✔ | idem |
| Construtora 01/06/2027 × independente 12/07/2027: +41 | ✔ | idem |
| Alerta "L2-S02-CBU é CRÍTICA e produz 60% do planejado" | ✔ / **frágil** | O texto completo da API é "(medida na própria atividade (**1 boletins**))". O número se apoia numa semana. O lote todo confirma: o índice do CBUQ do L2 é **0,588 em 6 boletins** (`/api/cobertura`, `fator_estresse_origem`). Sugestão: "produz 60 % do planejado; o CBUQ do L2 inteiro mede 59 % em 6 boletins". |
| ES 13/07/2027 (+1); MC P50 12/07, P80 14/07 | ✔ | idem (faixa P10–P90 de 11 d) |
| D4: término de 21/05/2027 repetido por 8 datas (01/01 a 01/08/2026); independente −3 d | ✔ | idem |
| D4: de 01/01 a 09/11/2026, independente +44 d e construtora +11 d | ✔ | idem |
| D4: ressalva "histórico sintético" | ✔ | `simplificacoes[0]`: "Histórico SINTÉTICO, calculado em memória… não é registro de previsões feitas no passado." |
| Recuperação: cumpre 21/05/2027 no papel, "inviável sem mudança de método" | ✔ | idem, plano de **8 frentes** |
| "uma frente de CBUQ do L2 precisa de **+46%** sobre a melhor semana medida" | ✔ / **frágil** | L2-S02-CBU: 1,459×, mas a "melhor semana" vem de **1 semana** da própria atividade. Ainda no plano: L2-S03 e L2-S04-CBU a 1,363× e **L3-S04-SHV a 1,50×**, o maior multiplicador. Sugestão: "4 das 8 frentes exigem de 1,36× a 1,50× a melhor semana medida". |
| Tornado: CBU L2 −10 % → +9; +1 equipe → −34 | ✔ | idem (23 grupos, 70 execuções) |
| 22 conflitos previstos (ex.: CBUQ × defensas no L1-S04), 0 reais | ✔ | 22/0; o L1-S04 tem CBU×DEF e CBU×SVV |

## 4. Fecho (IFC) e tabelas

| Afirmação | Situação | Valor atual |
|---|---|---|
| IFC4X3_ADD2, 0 erros de validação nas duas obras | ✔ | idem (2.278 kB e 2.605 kB) |
| Ferrovia: 537 elementos, 537 vinculados, 1 IfcAlignment | ✔ | idem |
| Ferrovia: "**113 IfcTask**" | ✘ | O arquivo tem **339 IfcTask** = 113 atividades × **3 IfcWorkSchedule** (linha de base, construtora, independente), com 113 identificações distintas. O `numeros_demo` reporta 339 (`tarefas_ifc`). Sugestão: "113 tarefas em cada um dos 3 cronogramas (linha de base, construtora e independente)". |
| Rodovia: 531 elementos, "**137 IfcTask**" | ✘ | 531 ✔; **411 IfcTask** = 137 × 3. Mesma correção. |
| Conciliação: 0 divergências em 463 e 427 boletins | ✔ | idem |
| Massas: ferrovia −23,5 %, 0 de 12 coerentes; rodovia 12 de 12 | ✔ | −0,235 e 0/12; rodovia −0,06 e 12/12 |
| "Revisão adversarial independente em **11 rodadas**" | ✘ | Existem **17** arquivos `test_revisao_adversarial_*` (motor e r2 a r17). Atualizar para "17 rodadas". |
| Arquivos de teste citados na tabela "O que funciona hoje" | ✔ | Todos os 25 citados existem, mais `tests/e2e/verificar_interface.py`. O resultado do e2e é **?** (Chrome, fora desta via). |
| FAQ: "acelerar só 4 frentes cumpre o prazo" | ✔ | `ajustes_finais` = 4 |
| FAQ: "na ferrovia o ES fica 29 dias antes do CPM" | ✔ | −29 |
| FAQ / posicionamento: frases qualitativas (o que não dizer, implantação, LGPD) | ? | Não são números. Não há o que medir. |

## 5. O que vale ENTRAR (número + rota)

1. **Cobertura da previsão, rodovia** (`GET /api/cobertura?obra=rodovia`)
   - M-FIM e M-L3-FIM com confiança **"baixa"**: o CBUQ do L3 ainda não foi medido e usa a média da obra.
   - Estressar o que não foi medido (× 0,588, o pior índice já observado, que é o CBUQ do L2) move o fim
     **+50 dias**; estressar o que foi medido move +49.
   - **8 frentes sem medição** no alerta (folga ≤ 10 dias úteis).
   - O M-L2-FIM está "alta" porque o CBUQ do L2 já é medido no lote.
   - Na ferrovia, os 4 marcos estão "alta".
   - Frase: "o sistema diz em que evidência a data se apoia".
2. **Backtest, ferrovia** (`GET /api/backtest?obra=ferrovia`)
   - M-L1-FIM: erro absoluto médio **construtora 54,9 d × independente 8,5 d**. O ES PF=1 erra 70,1 e o ES SPI 27,5.
   - A 10 % de avanço: construtora −79, independente +2.
   - Dizer sempre: a referência é o "futuro" do gerador sintético, e a realidade sintética favorece o método (R12 §5).
3. **MTA, rodovia** (`GET /api/tendencia?obra=rodovia`)
   - A independente passa a divergir da construtora em M-FIM a partir de **05/10/2026**: a 1ª semana em que o
     boletim de CBUQ do L2 é conhecido.
   - Inclinação do M-FIM: independente 0,60 d/semana, construtora 0,20.
   - Mostra a convergência uma semana depois do dado novo (R12 §4).
4. **Aceleração, rodovia** (`GET /api/aceleracao?obra=rodovia`)
   - Chega a **20/05/2027** (prazo 21/05) por **R$ 3,79 mi fictícios**, com 5 ajustes e verificação `confere: true`.
   - Junto com a ferrovia (R$ 1,71 mi), mostra o custo de cumprir o prazo nas duas obras.
5. **BDI por obra** (`GET /api/orcamento/resumo`)
   - Ferrovia **23,48 %** e rodovia **22,22 %**, pela fórmula do TCU com componentes declarados.
   - As duas dentro da faixa **19,60 %–24,23 %** (Acórdão 2622/2013-Plenário, construção de rodovias e ferrovias).
   - Fictício, declarado na resposta. Vale **uma linha** no D2, porque a aceleração usa esse BDI.
6. **Registro de riscos** (`GET /api/riscos?obra=…&rapido=true`, ~0,3–0,5 s)
   - Ferrovia: 17 riscos; o 1º é "TER do L3: risco ao prazo confirmado por 2 fontes" (alto).
   - Rodovia: 21 riscos, com "CBU do L2 … confirmado por 2 fontes" (alto).
   - Bom resumo de 30 s antes do fecho, se houver tela.

## 6. O que deveria SAIR ou ser reescrito (frágil)

1. **"113 IfcTask" / "137 IfcTask"**: reescrever como "113 / 137 tarefas em cada um dos 3 cronogramas".
   O número atual contradiz o `numeros_demo`.
2. **"11 rodadas"** de revisão adversarial: trocar por 17.
3. **Alerta da rodovia apoiado em 1 boletim**: manter o 60 %, mas dizer que o lote confirma (59 % em 6 boletins).
   Sem isso, a pergunta "60 % de uma semana?" derruba o argumento.
4. **"+46% sobre a melhor semana"**: a base é 1 semana, e não é o maior multiplicador (SHV do L3 1,50×). Usar a
   faixa 1,36–1,50× em 4 das 8 frentes.
5. **Não acrescentar** a "divergência desde 2025-11-24/12-01" da MTA da ferrovia. Ela aparece na 1ª ou 2ª semana da
   obra, com pouquíssimo dado, e soa como artefato.
6. **Não usar** o backtest do M-L2-FIM da rodovia como vitrine: MAE de 63 contra 50, e a independente só converge
   depois do 1º boletim de CBUQ (R12 §4–5). Se perguntarem, é o caso honesto de choque não observável.
7. **Comando de regeneração**: acrescentar `$env:PYTHONIOENCODING="utf-8"` antes, para não quebrar ao salvar
   em arquivo na véspera.

## 7. Não verificável por esta via (fica para o e2e no Chrome)

- Contorno vermelho das 10 críticas no 3D e a troca para o "Modelo IFC (GLB)".
- O tour em si: cliques, abas e textos escritos na tela.
- O relatório imprimível.
- O botão "Repetir o tour na rodovia".
- O resultado atual de `tests/e2e/verificar_interface.py`, que não rodei: Chrome headless e um processo pesado por vez.
