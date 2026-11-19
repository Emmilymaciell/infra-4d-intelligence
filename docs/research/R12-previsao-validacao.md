# R12 — Como validar a previsão independente retroativamente (backtest)

> Data: 2026-11-13. Só pesquisa: nenhum código foi escrito e nada foi feito no git.
> Regra de citação: só entra como **[A]** (aberto) o que eu abri e li, seja na página, seja no PDF convertido com `pdftotext`.
> O que vi só em resumo de busca ou em resumo de catálogo aparece como **[R]** e não sustenta número nenhum.
> Os números do backtest local (§4) saíram de uma execução de `backtest.backtest(..., passo_dias=28)` sobre os dois
> JSON de `examples/synthetic/`, rodada em 2026-11-13. É leitura do código existente, não código novo.

## 0. Resumo (8 linhas)

1. Na literatura de EVM/ES, o padrão para medir acurácia de prazo é o **MAPE** entre a duração prevista em cada
   período de controle e a **duração real final**, com média sobre todos os períodos e corte por fração concluída.
2. O ES (Lipke) é o *benchmark* a vencer. A melhor marca empírica citada é **MAPE 8,2 % (ESM-1, projetos regulares)**.
3. A acurácia depende da forma da rede: rede mais **serial** prevê melhor, e a curva PV **irregular** piora o erro em cerca de 8 pontos.
4. A **estabilidade** é métrica separada da acurácia, e as duas tendem a ser **inversamente correlacionadas**. É preciso medir as duas.
5. A MTA alemã é uma ferramenta **qualitativa de leitura**: linha horizontal = no prazo, subindo = atraso, descendo =
   adiantamento. Não é validação. A nossa MTA é calculada, então pode virar backtest.
6. O projeto já tem o que precisa: `tendencia.fotografia` (sem dado futuro), `realidade_simulada` (o futuro oculto
   do gerador) e `backtest.py` / `GET /api/backtest`.
7. A limitação dominante é que a realidade sintética tem **fatores de produtividade estacionários por (lote, serviço)**.
   Isso favorece o cenário independente por construção. Um backtest bom aqui é condição necessária, não prova.
8. Recomendação: MAE e MAPE por faixa de fração concluída, viés com sinal, estabilidade (variação entre datas
   consecutivas, reversões, data de convergência), comparação contra 3 previsores de referência (construtora,
   ES PF=1, ES PF=SPI(t)) e um conjunto de várias sementes.

## 1. O que a literatura diz (fontes abertas)

### 1.1 Earned Schedule e IEAC(t)

- **Lipke, "Testing Earned Schedule Forecasting Reliability", PM World Journal, vol. III, n.º VII, jul. 2014** [A]
  https://www.earnedschedule.com/Docs/Testing%20Earned%20Schedule%20Forecasting%20Reliability.pdf
  - Define SPI(t) = ES/AT e IEAC(t) = PD/SPI(t). A "porcentagem concluída de prazo" é **ES ÷ PD × 100** (nota 9).
  - **Método:** em cada data de status, classifica o par (SPI(t), RD versus PD) em 9 cenários agrupados em
    *true / misleading / false* e soma por faixas de **10 % de conclusão**.
  - Depois aplica a **regra dos 10 %**: previsão a até 10 % de RD é reclassificada como *true*.
  - **Critério de confiabilidade:** "reliable when the value from the linear fit of True% is approximately 60 percent
    at 25 percent schedule completion".
  - **Dados:** 16 projetos reais, 12 de alta tecnologia (mensais) e 4 de TI (semanais), **sem replanejamento**.
  - **Resultado sem a margem:** cerca de 60 % confiável a 25 % concluído e cerca de 80 % a 75 %.
  - **Resultado com a margem de 10 %:** 60 % já a cerca de 5 % concluído e 80 % a cerca de 50 %.
  - **Não há obra de infraestrutura** no conjunto.
- **Vanhoucke & Vandevoorde, "Forecasting a Project's Duration under Various Topological Structures", The Measurable
  News, primavera de 2009** [A]
  https://www.earnedschedule.com/Docs/Forecasting%20Project%20Duration%20%5BVanhoucke%20&%20Vandevoorde%5D.pdf
  - Simulação com 100 repetições por execução. Compara os métodos PV, ED e ES e mede o erro como desvio percentual
    entre a previsão média ao longo do projeto e a duração final simulada. Negativo = subestima.
  - "The ES method clearly outperforms the two other duration forecasting methods … both for projects finishing early and late."
  - "The more serial the project network, the better the average forecast accuracy of all duration forecasting methods."
- **Vanhoucke & Vandevoorde (2007), JORS 58(10):1361–1374** [R, só o resumo do catálogo IAOR]: o estudo de simulação
  original controla incerteza, estrutura da rede e horizonte de tempo, e assume rede conhecida, sem eventos
  imprevisíveis. https://ftp.iaorifors.com/paper/59636
- **Vandevoorde & Vanhoucke (2006), IJPM 24(4)** [R, página RePEc]: comparação entre SV/SPI e SV(t)/SPI(t), com
  fórmula genérica de previsão e dados reais. https://econpapers.repec.org/RePEc:rug:rugwps:05/312

### 1.2 Acurácia empírica e métrica (MAPE)

- **Batselier & Vanhoucke, "Project regularity…", J. Systems Science and Systems Engineering 26(1):100–120, 2017**
  (preprint UCL) [A] https://discovery.ucl.ac.uk/1506210/1/Waterfield_Project%20regularity.pdf
  - **Fórmula (4):** MAPE = (1/p) Σₜ |A − Fₜ| / A, onde A = duração real (RD), Fₜ = EAC(t) no período de controle t
    e p = número de períodos.
  - **Base:** 51 projetos reais de vários setores (construção, eventos, TI, produção, educação), publicada pelo grupo OR-AS.
  - O texto cita o resultado do artigo de 2015 (JCEM 141(11)): o melhor método de prazo, **ESM-1 (PF = 1)**, teve
    **MAPE 8,2 %** em projetos regulares.
  - Projetos **irregulares** (curva PV que foge da curva S típica) pioram o MAPE real em **8,1 pontos** em média.
    O efeito da regularidade (R² 54,5 %) é maior que o da serialidade SP (R² 30,1 %).
  - O artigo de 2015 em si (core.ac.uk) devolveu **403** e não foi lido.
- **Barrientos-Orellana, Ballesteros-Pérez, Mora-Melià, González-Cruz & Vanhoucke, "Stability and accuracy of
  deterministic project duration forecasting methods in EVM", ECAM 29(3):1449–1469, 2022** [A, página do artigo]
  https://emerald.com/insight/content/doi/10.1108/ECAM-12-2020-1045/full/html
  - 27 métodos determinísticos e 4.100 redes artificiais, com métricas em **10 faixas percentuais de avanço**.
  - Acurácia por MSE e MAPE. **Estabilidade** por correlações de Pearson, Spearman e Kendall. A fórmula exata não
    estava na página.
  - Achado: "stability and accuracy are inversely correlated for most forecasting methods". As duas pioram com redes
    mais **paralelas**. O método "AT + PD − ESmin" saiu como o mais acurado e confiável.
- **Hurtado, "Analysis of the Earned Schedule Forecasting Accuracy", AACE Source, 2021** [A, página]
  https://source.aacei.org/?p=3340
  - 8 obras reais de refinaria. Usa MAPE por período e divide em **fases**: inicial 0–30 %, intermediária 30–70 % e
    final 70–100 %.
  - PF = 1 foi o mais acurado no início das 8 obras. Com atraso e baixa produtividade, PF = SPI(t) tende a ganhar.
  - A conclusão do próprio texto fala em "six projects" e contradiz as 8 obras descritas.

### 1.3 Infraestrutura linear (evidência fraca)

- **Widowati & Resita, Jurnal Pensil 14(3), 2025, CC BY-SA 4.0** [A] (duplicação ferroviária Wonokromo–Jombang,
  Indonésia, 121 semanas) https://journal.unj.ac.id/unj/index.php/jpensil/article/download/59154/21248/173654
  - Analisa **só as semanas 1–28**. Não houve backtest contra o término real.
  - Houve **aditivo contratual na semana 21**, e o SPI(t) mudou de patamar. É um exemplo direto de replanejamento,
    que os estudos de Lipke excluem.
- **Tzaveas, Katsavounis & Kalfakakou, PM-05, Creta, 2010** [A, lido parcialmente] (viaduto da Egnatia Odos):
  https://www.earnedschedule.com/Docs/Tzaveas%20-%20Analysis%20of%20Project%20Performance.pdf
  - EV e ES dão resultados parecidos no início e às vezes no meio da obra. Os autores alertam que essa afirmação
    "can be misleading" mais adiante.
  - A análise por elemento do caminho crítico (pilar e balanços) muda o diagnóstico.
- Não encontrei estudo aberto com **backtest de término de obra ferroviária ou rodoviária contra a data real**, com
  vários pontos de controle. Achei só estudos de caso de um projeto, sem MAPE contra o término real.

### 1.4 MTA (Meilensteintrendanalyse)

- **Lück-Schneider, HWR Berlin, material didático "Zeitcontrolling – Meilenstein-Trend-Analyse"** [A]
  https://www.hwr-berlin.de/fileadmin/portal/Dokumente/Prof-Seiten/Lueck-Schneider/Lueck-Schneider-Lehre-Zeitcontrolling-MST-Trendanalyse.pdf
  - **Pré-requisitos:** "ein realistischer Terminplan", marcos significativos e "regelmäßige Rückmeldung".
  - **Eixos:** "Die horizontale Achse kennzeichnet das aktuelle Datum", e no vertical vão os términos estimados
    naquela data. Na versão alemã clássica, **a estimativa é feita pelos responsáveis**: "Die Schätzung erfolgt durch
    die verantwortlichen Projektmitarbeiter".
  - **Leitura:** subindo = Terminverzug; horizontal = plangemäß; descendo = adiantamento. A diagonal ("Trendlinie") é
    onde o marco encontra a data de status, ou seja, onde ele se conclui.
  - O exercício insiste em datas concretas nos relatórios em vez de prazos relativos.
- **microTOOL, "What is a Milestone Trend Analysis?"** [A]
  https://www.microtool.de/en/knowledge-base/milestone-trend-analysis/
  - **Padrões:** escada (subestimação sistemática), ziguezague (plano instável), "vertical wall" (linha plana e
    salto tardio, o "watermelon reporting") e "runway" (estabiliza perto da diagonal).
  - Regra "Update interval ≤ Reporting cycle".
  - Uma linha plana pode ser estabilidade **ou** falta de atualização.

**Leitura para o INFRA 4D:** a MTA alemã mede a **honestidade e estabilidade** das estimativas ao longo do tempo, não
o acerto. O "vertical wall" é justamente o padrão que a previsão independente deveria antecipar. É por isso que o
backtest compara construtora e independente na mesma fotografia.

## 2. Métricas recomendadas

Notação: d = data de status passada, F_c(d) = término previsto pelo cenário c na fotografia de d, R = término de
referência, D = duração real (R − início + 1). Erro e(d) = F_c(d) − R em dias corridos (positivo = previu tarde,
mesma convenção do `backtest.py`).

| # | Métrica | Definição | Por quê |
|---|---|---|---|
| A1 | **MAE** por marco e cenário | média de \|e(d)\| sobre as datas | Já está no `backtest.py`. Em dias, é legível para o fiscal. |
| A2 | **MAPE** sobre a duração | (1/p) Σ \|e(d)\| / D | É a métrica da literatura (Batselier & Vanhoucke). Torna obras de tamanhos diferentes comparáveis e é o único jeito de comparar com os 8,2 % do ESM-1. |
| A3 | **Erro por fração concluída** | e(d) na 1ª data em que o avanço atinge 10, 20, … 90 % | Já está no `backtest.py` (`por_fracao_concluida`). Recomendo reportar também a fração de **prazo** ES/PD (Lipke, nota 9), porque o avanço físico ponderado e a fração de prazo divergem em obra atrasada. |
| A4 | **Erro por fase** | MAPE em 0–30 %, 30–70 % e 70–100 % | É a divisão de Hurtado. Resume A3 em 3 números para o painel. |
| A5 | **Viés** | média de e(d) com sinal | Separa "erra para cedo" de "erra aleatoriamente". O otimismo sistemático da construtora aparece aqui. |
| A6 | **Taxa de acerto em ±10 %** | fração das datas com \|e(d)\| ≤ 0,10·D, por faixa | É a margem de Lipke. Critério de aceite candidato: ≥ 60 % das datas a 25 % concluído (o patamar de Lipke). |
| E1 | **Estabilidade (variação)** | média de \|F(dᵢ) − F(dᵢ₋₁)\| por semana | É a magnitude do "zigue-zague" da MTA. Complementa a inclinação de `/api/tendencia`, que só mede tendência. |
| E2 | **Reversões** | número de trocas de sinal de F(dᵢ) − F(dᵢ₋₁) | Ziguezague da microTOOL: previsão que vai e volta não dá decisão. |
| E3 | **Data de convergência** | 1ª d a partir da qual \|e\| ≤ X dias até o fim | Responde "a partir de quando posso confiar". O `independente_melhor_desde` atual é a versão relativa: desde quando a independente é sempre ≥ construtora. |
| C1 | **Ganho sobre referência** | 1 − MAE_indep / MAE_ref | A referência vem em 3 versões: construtora, ES PF=1 e ES PF=SPI(t). |

Observação sobre E1/E2: o ECAM 2022 mede estabilidade por correlação, mas não vi a fórmula, então não a adoto.
E1 e E2 são definições nossas, declaradas como tal.

**Critério de pronto sugerido (vai em `project.yaml` → `verificacao.limites`, nunca cravado no teste):**
`mape_independente_max`, `acerto_10pct_a_25pct_min` (0,60, de Lipke) e `ganho_sobre_construtora_min`.
Os valores devem ser fixados pela titular **depois** de olhar a distribuição sobre várias sementes, não antes.

## 3. Como fazer o backtest com o que já existe

O que já existe no repositório, conferido no código em 2026-11-13:
- `tendencia.fotografia(dados, d)`: estado da obra em d sem dado futuro. Entra só boletim de semana encerrada e só
  data real anterior a d. Em duração fixa, o % é estimado como dias úteis ÷ duração (máximo 99 %).
- `GET /api/tendencia?obra=&passo_dias=`: série MTA por marco de término (construtora × independente), inclinação em
  dias por semana e a 1ª divergência acima do limiar. **Não traz erro**: não conhece o futuro.
- `dados_sinteticos*.realidade_simulada(semente)`: término de cada atividade no "futuro" que o gerador sorteou e não
  exporta.
- `backtest.py` + `GET /api/backtest?obra=&passo_dias=`: junta os dois e já entrega erro por data, MAE, erro por faixa
  de avanço, `independente_melhor_desde` e a medida de circularidade (`sobreposicao_boletins`).

**Roteiro recomendado:**
1. **Referência:** usar **só `realidade_simulada`** para julgar acurácia. A `final_independente` é parcialmente
   circular (erro 0 na última data por construção) e serve apenas para conferir a coerência.
2. **Passo:** usar 7 dias. É o ciclo dos boletins, e a regra microTOOL "update interval ≤ reporting cycle" pede isso.
   Usar 28 só em exploração.
3. **Conjunto:** rodar sobre **N sementes** (por exemplo 30) de cada gerador, não sobre os 2 JSON versionados.
   - Com 1 semente por obra não há estatística: um MAE é uma amostra.
   - `gerar(semente)` já recebe a semente. Falta só poder levar a `DATA_STATUS` até o fim da obra (ver §5), para
     avaliar a fase de 70–100 %.
4. **Previsores comparados na mesma fotografia:** construtora, independente, ES PF=1 e ES PF=SPI(t) (`previsao_es.py`).
   O backtest atual só compara os dois primeiros. Incluir o ES é o que permite confrontar com a literatura (§1).
5. **Saída:** reportar A1–A6, E1–E3 e C1 por marco e por cenário, mais o avanço físico e a fração de prazo ES/PD em
   cada d. No painel, mostrar a MTA com a faixa de ±10 % de D em volta da referência.
6. **Teste do detector:** antes de confiar, ver o backtest **falhar**. Por exemplo, injetar um evento futuro que a
   produtividade observada não revela (restrição liberada tarde, chuva) e conferir que o MAE da independente sobe.

## 4. O que o backtest atual já mostra (execução local, passo 28, 2026-11-13)

Referência = `realidade_simulada`. Erro = previsto − real em dias, negativo = previu cedo.

| Obra / marco | Real | MAE construtora | MAE independente | Erro a 10 % (constr. / indep.) | Erro a 60 % (constr. / indep.) |
|---|---|---|---|---|---|
| Ferrovia M-L1-FIM | 2027-05-17 | 54,8 | 10,9 | −68 / 0 | −19 / +3 |
| Ferrovia M-L3-FIM | 2027-09-02 | 74,6 | 29,9 | −86 / +8 | −44 / +13 |
| Rodovia M-L1-FIM | 2027-01-11 | 24,2 | 9,3 | −37 / −3 | −12 / −3 |
| Rodovia M-L2-FIM | 2027-04-20 | 63,0 | 49,8 | −66 / −59 | −59 / −52 |

Leitura:
- **A construtora é sempre otimista.** O viés é negativo e encolhe com o avanço: é o "vertical wall" previsto pela MTA.
- **A independente acerta cedo onde o atraso é de produtividade** (ferrovia L1 e rodovia L1).
- **Na rodovia L2 e L3 a independente erra quase tanto quanto a construtora até cerca de 70 %**: −59 dias a 10 % e
  ainda −52 a 60 %. Ela só converge na data atual. Há algum atraso que a produtividade observada não revela antes de
  acontecer. A causa não foi investigada nesta pesquisa: verificar restrições e clima da rodovia antes de usar esse
  marco como vitrine.
- O avanço só chega a 71,7 % (ferrovia) e 81,9 % (rodovia) na data de status. **Não há como avaliar a fase final**
  com os datasets atuais.

## 5. Limitações (importantes)

1. **A realidade sintética favorece o método.** Os fatores de desempenho são **constantes por (lote, serviço)**.
   Um cenário que projeta a produtividade observada converge para a verdade por construção.
   - Na obra real, a produtividade muda: curva de aprendizado, chuva, troca de equipe, aditivo.
   - Backtest sintético bom é condição necessária, não prova.
   - **Mitigação:** sortear fatores **não estacionários** (degrau, deriva, sazonalidade) num conjunto de teste
     separado e reportar à parte.
2. **Uma semente por obra** não dá distribuição de erro. Ver §3, item 3.
3. **Fase final não avaliável:** a `DATA_STATUS` é constante do gerador (2026-11-09), e os términos reais ficam em 2027.
4. **Aproximações da fotografia:** o % das atividades de duração fixa é linear e limitado a 99 %. Além disso, a
   situação das restrições é recalculada na data, mas a data de liberação vem do dataset atual. Se ela foi
   "descoberta" depois, isso é dado futuro. Conferir com o dono do `tendencia.py`.
5. **Sem replanejamento:** a literatura de confiabilidade (Lipke) usa projetos **sem rebaseline**. Obra pública
   brasileira tem aditivo de prazo (veja a semana 21 do caso ferroviário indonésio). O backtest precisa declarar
   contra qual linha de base mede.
6. **Estrutura da rede:** rede paralela (vários lotes simultâneos) prevê pior (Vanhoucke & Vandevoorde 2009; ECAM 2022),
   e curva PV irregular também (Batselier & Vanhoucke 2017). Comparar MAPE entre obras sem dizer SP e regularidade engana.
7. **A MTA não é métrica de acerto:** a versão alemã é julgamento humano com leitura visual. Nossa MTA calculada só
   vira validação quando é cruzada com a referência real (§3).
8. **Dados reais públicos limitados:**
   - O **Obrasgov** (R10) traz série de % físico global e datas efetivas de obras concluídas. Isso permitiria um
     backtest **real**, mas só de uma previsão por extrapolação do % global, porque não há curva PV de linha de base
     nem atividades.
   - A base **DSLIB / OR-AS** (Ghent) tem mais de 180 projetos reais, mas a página **não declara licença** [A]
     (https://www.projectmanagement.ugent.be/research/data). Não redistribuir sem esclarecer.
9. **Evidência de infraestrutura fraca:** não achei estudo aberto com MAPE de previsão de término contra a data real
   em ferrovia ou rodovia. Os números de referência (8,2 %, 60 % a 25 %) vêm de construção geral, TI e alta tecnologia.
10. **Choque não observado não é previsível (caso rodovia L2, medido em 2026-11-13 com `cobertura.py`).**
    - Na fotografia de 2026-03-30, o M-L2-FIM é determinado pela terraplenagem do L2, que já tem medição.
    - Os CBUQ S01–S03 do L2 não têm medição e ficam a **5 dias úteis** de folga do marco. Por isso estão fora da
      cadeia determinante.
    - O fator de estresse justo é o pior índice medido/planejado observado até ali: **0,85**, da terraplenagem do L3.
      Estressar em × 0,85 o que não foi medido move o marco 7 dias. Estressar o que foi medido move 59. A confiança
      sai **"alta"**.
    - O fator real do CBUQ do L2 é 0,60. Ele está abaixo de tudo o que os dados mostravam e só aparece no 1º boletim
      (conhecido em 2026-10-05).
    - **Nenhum sinal justo marca "baixa" ali.** O que o método consegue dizer é o **alerta**: "o marco depende de 3
      segmentos de CBUQ sem medição a 5 dias úteis de virar determinantes" (`/api/cobertura`,
      `alerta_sem_medicao`).
    - Usar 0,60 no estresse seria calibrar no gabarito escondido do gerador. Foi recusado.

## 6. Fontes não abertas (não sustentam nada acima)

- Batselier & Vanhoucke (2015), JCEM 141(11) — core.ac.uk devolveu 403. O número 8,2 % vem da citação no artigo de 2017.
- Lipke, CrossTalk 2015 (versão da revista do mesmo estudo) — baixado, não lido.
- Estudo indonésio de rodovia pedagiada e de Andrade, Martens & Vanhoucke — vistos só no resumo da busca.
- Reddit — bloqueado para o agente (ver R04).
