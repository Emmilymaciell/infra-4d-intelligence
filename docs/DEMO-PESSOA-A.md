# INFRA 4D INTELLIGENCE — roteiro da demonstração

> **Todos os dados são FICTÍCIOS.** As duas obras (uma ferrovia e uma rodovia), os consórcios, as quantidades e os
> boletins foram gerados por programa com semente fixa e trazem a marca `meta.ficticio: true`. Nenhum número
> representa obra, contrato ou empresa real.
>
> **De onde vêm os números deste documento.** Todos foram lidos da API pelo script
> `scripts/infra4d/numeros_demo.py`, executado em **13/11/2026** (auditados um a um no R14). Para regenerar antes da reunião:
>
> ```powershell
> cd scripts; ..\.venv\Scripts\python.exe -m infra4d.numeros_demo          # texto
> cd scripts; ..\.venv\Scripts\python.exe -m infra4d.numeros_demo --json   # JSON
> ```
>
> O script roda a API em memória (sem servidor e sem rede), aplica e desfaz as simulações e não grava nada no
> repositório. Leva cerca de 50 s. Se algum valor divergir do texto abaixo, **vale o da execução**. A apresentação
> guiada também lê os números da API na hora.

## A ideia em uma frase

A plataforma recalcula o prazo da obra **de forma independente da construtora**, a partir do que o campo
realmente produz, e mostra no 3D/4D, no cronograma, na linha de balanço e no painel **por que** a data mudou.

## Como iniciar

```powershell
.\bootstrap.ps1     # só na primeira vez: cria o .venv e instala as dependências
.\run-beta.ps1      # abre http://127.0.0.1:8765/  (só nesta máquina, sem login)
```

A API documentada fica em `http://127.0.0.1:8765/docs`. Dois desvios do roteiro (histórico e DCMA) ainda não têm
tela e são mostrados por ali.

## Roteiro (cerca de 15 minutos)

A espinha é o botão **"▶ Apresentação guiada"** (`web/tour.js`): uns 13 passos que **executam** a ação (trocam
de aba, selecionam a frente, movem a linha do tempo, simulam, comparam o cronograma) e escrevem os números lidos
da API. Avance com → e saia com Esc. Os desvios (D1 a D5) entram nos pontos marcados.

### Parte 1: a ferrovia (cerca de 9 min)

| # | Passo do tour | O que dizer (números da execução) |
|---|---|---|
| 1 | A obra | Ferrovia Fictícia Vale do Sintético: **<!-- n:ferrovia.obra.extensao_km -->60 km, <!-- n:ferrovia.obra.lotes -->3 lotes, <!-- n:ferrovia.obra.atividades -->113 atividades, <!-- n:ferrovia.obra.relacoes -->264 relações**. Data de status **<!-- n:ferrovia.obra.data_status -->09/11/2026**. "Todos os dados são fictícios." |
| 2 | Painel: o problema | A construtora prevê **<!-- n:ferrovia.painel.termino_construtora -->23/07/2027**. A análise independente, com a produtividade **medida** nos boletins, prevê **<!-- n:ferrovia.painel.termino_independente -->09/09/2027**: **<!-- n:ferrovia.painel.delta_dias -->48 dias corridos depois**. Avanço real de **<!-- n:ferrovia.painel.avanco_real_pct -->71,69%** contra **<!-- n:ferrovia.painel.avanco_lb_pct -->80,9%** previstos na linha de base |
| 3 | Painel: a causa | Alerta do motor: "**<!-- n:ferrovia.painel.alerta_atividade -->L3-S03-TER é CRÍTICA e produz <!-- n:ferrovia.painel.alerta_pct -->78% do planejado** (medida na própria atividade, 6 boletins)" |
| 4 | Três métodos de previsão | Earned Schedule: SPI **<!-- n:ferrovia.es.spi -->0,884** → **<!-- n:ferrovia.es.termino -->11/08/2027**, ou seja, **<!-- n:ferrovia.es.diferenca_dias_abs -->29 dias antes** do CPM. O avanço agregado dilui um atraso concentrado no caminho crítico. Monte Carlo: P50 **<!-- n:ferrovia.mc.p50 -->10/09/2027**, P80 **<!-- n:ferrovia.mc.p80 -->13/09/2027**, faixa P10–P90 de **<!-- n:ferrovia.mc.largura_dias -->10 dias** (estreita por construção). A criticidade aponta <!-- n:ferrovia.mc.criticidade.0.id -->L3-S04-LAS, <!-- n:ferrovia.mc.criticidade.1.id -->L3-S04-TER e <!-- n:ferrovia.mc.criticidade.2.id -->L3-S03-TER como críticas em **<!-- n:ferrovia.mc.criticidade.2.indice -->100%** das iterações |
| 5–6 | Modelo 3D/4D e linha do tempo | **<!-- n:ferrovia.painel.n_criticas -->10 atividades críticas** contornadas em vermelho. No seletor "Geometria", dá para trocar a vista esquemática pelo **Modelo IFC (GLB)** gerado pela própria plataforma (ver D5) |
| 7 | Simulação crítica | Terraplenagem L3-S04 a **1.500 m³/equipe·dia**: o término vai de <!-- n:ferrovia.simulacao.0.termino_antes_curta -->09/09 para **<!-- n:ferrovia.simulacao.0.termino_depois -->06/10/2027 (<!-- n:ferrovia.simulacao.0.delta -->+27 dias)**. A tela mostra a conta e a cadeia determinante |
| 8 | Simulação com folga | Lastro L2-S04 a **250 m³/equipe·dia**: o término **não muda (<!-- n:ferrovia.simulacao.1.delta -->+0)**. "Gerir pelo caminho crítico, não pelo percentual." |
| — | **D1: tornado** (aba Análises, ~1 min) | Entre **<!-- n:ferrovia.sensibilidade.grupos -->21 grupos** (<!-- n:ferrovia.sensibilidade.execucoes -->64 execuções do motor), o maior efeito é a **terraplenagem do L3**: piorar 10% atrasa **<!-- n:ferrovia.sensibilidade.piorar -->+21 dias**, melhorar 10% antecipa **<!-- n:ferrovia.sensibilidade.melhorar -->−17**, e **+1 equipe antecipa <!-- n:ferrovia.sensibilidade.mais_1_equipe -->−62 dias** |
| — | **D2: plano de recuperação** (aba Análises, ~1 min) | O prazo contratual de **<!-- n:ferrovia.recuperacao.prazo -->27/05/2027** é alcançável com um plano mínimo de **<!-- n:ferrovia.recuperacao.frentes -->6 frentes do L3**, mas exige quase dobrar a terraplenagem (até **<!-- n:ferrovia.recuperacao.razao_max_melhor_semana -->1,8× a melhor semana já medida**): **só com mudança de método**. Comprando equipes inteiras, a aceleração (`/api/aceleracao`) chega a **<!-- n:ferrovia.aceleracao.termino -->25/05/2027** por **<!-- n:ferrovia.aceleracao.custo_mi -->R$ 1,71 mi fictícios**. Dizer exatamente isso: o sistema separa o que é possível no papel do que é viável com o método atual |
| 9 | Linha de balanço | **<!-- n:ferrovia.balanco.conflitos -->8 conflitos** previstos entre frentes sucessivas (menos de 1 km de distância), marcados com "!" e com o cruzamento calculado analiticamente. **<!-- n:ferrovia.balanco.conflitos_reais -->0 conflitos reais** na linha executada |
| 10 | Cronograma da construtora | O MSPDI do cenário da construtora, recalculado no motor, termina em **<!-- n:ferrovia.cronograma.termino_arquivo -->23/07/2027**; o independente, em **09/09/2027**: **<!-- n:ferrovia.cronograma.delta_dias -->+48 dias**, com **<!-- n:ferrovia.cronograma.atividades_diferentes -->39 atividades** diferentes |
| — | **D3: DCMA 14 pontos** no cronograma da construtora (`/docs` → `GET /api/dcma?obra=ferrovia&cenario=construtora`, ~1 min) | **<!-- n:ferrovia.dcma.aprovados -->6 aprovados, <!-- n:ferrovia.dcma.reprovados -->7 reprovados, <!-- n:ferrovia.dcma.nao_avaliados -->1 não avaliado.** Reprovados: lags positivos (<!-- n:ferrovia.dcma.lags_pct -->63,6%), relações não FS, folga alta, duração alta, tarefas perdidas, CPLI e BEI. Dizer que os limites do DCMA são **ponto de partida de análise**, não critério de conformidade (aviso da própria resposta) |
| — | **D6: a previsão acerta?** (`/api/backtest?obra=ferrovia`, ~1 min) | Refazendo a previsão em cada semana passada só com o que se sabia então, contra o futuro que o gerador sorteou e não exporta: no fim do **L1**, erro médio da construtora **<!-- n:ferrovia.backtest.L1.mae.construtora -->54,9 dias**, da independente **<!-- n:ferrovia.backtest.L1.mae.independente -->8,5** (Earned Schedule <!-- n:ferrovia.backtest.L1.mae.es_pf1 -->70,1 e <!-- n:ferrovia.backtest.L1.mae.es_spi -->27,5). **Dizer sempre: referência sintética**; mede o método contra um mundo inventado |
| 11 | Relatório técnico | Abre o relatório imprimível, gerado do mesmo motor; traz também riscos, tendência, recuperação, backtest e cobertura |

### Parte 2: a rodovia (cerca de 5 min)

No último passo do tour, **"Repetir o tour na rodovia"** troca de obra e mostra que nada é específico de ferrovia.

| O que mostrar | Números da execução |
|---|---|
| A obra | BR-FIC 999 (duplicação fictícia): **<!-- n:rodovia.obra.extensao_km -->48 km, <!-- n:rodovia.obra.lotes -->3 lotes, <!-- n:rodovia.obra.atividades -->137 atividades, <!-- n:rodovia.obra.relacoes -->301 relações** |
| O problema | Construtora **<!-- n:rodovia.painel.termino_construtora -->01/06/2027** × independente **<!-- n:rodovia.painel.termino_independente -->12/07/2027**: **<!-- n:rodovia.painel.delta_dias_sinal -->+41 dias**. Alerta: "**<!-- n:rodovia.painel.alerta_atividade -->L2-S02-CBU é CRÍTICA e produz <!-- n:rodovia.painel.alerta_pct -->60% do planejado**" (usina do L2 limitada). Esse número é de 1 boletim; dizer que o CBUQ do L2 inteiro confirma **<!-- n:rodovia.produtividade.L2_CBU.indice -->0,588 em <!-- n:rodovia.produtividade.L2_CBU.boletins -->6 boletins** |
| Três métodos | Earned Schedule **<!-- n:rodovia.es.termino -->13/07/2027**: concorda com o CPM (**<!-- n:rodovia.es.diferenca_dias_sinal -->+1 dia**). Monte Carlo P50 **<!-- n:rodovia.mc.p50_curta -->12/07**, P80 **<!-- n:rodovia.mc.p80 -->14/07/2027** |
| **D4: "a construtora repetiu a mesma data por 8 meses"** (`/docs` → `GET /api/historico/evolucao?obra=rodovia`, ~1,5 min) | "A construtora manteve o término em **<!-- n:rodovia.historico.termino_repetido -->21/05/2027** por **<!-- n:rodovia.historico.datas_repetidas -->8 datas de status seguidas (<!-- n:rodovia.historico.repetiu_de -->01/01 a <!-- n:rodovia.historico.repetiu_ate -->01/08/2026)**; no mesmo período a previsão independente andou <!-- n:rodovia.historico.independente_no_periodo -->−3 dias." Depois disso, de 01/01 a 09/11/2026: independente **<!-- n:rodovia.historico.independente_total -->+44 dias**, construtora **<!-- n:rodovia.historico.construtora_total -->+11 dias**. **Dizer a ressalva da própria resposta:** é um histórico **sintético**, recalculado aplicando o critério atual da construtora aos dados de cada mês, e não cronogramas que ela tenha de fato enviado |
| Recuperação | Cumpre o prazo de **<!-- n:rodovia.recuperacao.prazo -->21/05/2027** no papel, mas o plano é **"inviável sem mudança de método"**: **<!-- n:rodovia.recuperacao.frentes_inviaveis -->4 das <!-- n:rodovia.recuperacao.frentes -->8 frentes do plano exigem de <!-- n:rodovia.recuperacao.razao_min_inviaveis -->1,36× a <!-- n:rodovia.recuperacao.razao_max_inviaveis -->1,50× a melhor semana já medida**. Comprando equipes, a aceleração chega a **<!-- n:rodovia.aceleracao.termino -->20/05/2027** por **<!-- n:rodovia.aceleracao.custo_mi -->R$ 3,79 mi fictícios** |
| **Cobertura da previsão** (`/api/cobertura?obra=rodovia`) | O término da obra sai com confiança **"<!-- n:rodovia.cobertura.obra.confianca -->baixa"**: o CBUQ do L3 ainda não tem medição e usa a média da obra. Estressar o que não foi medido move o fim **<!-- n:rodovia.cobertura.obra.delta_sem_medicao_dias -->50 dias** (contra <!-- n:rodovia.cobertura.obra.delta_medida_dias -->49 do que foi medido); **<!-- n:rodovia.cobertura.obra.frentes_alerta_sem_medicao -->8 frentes** no alerta "sem medição perto do caminho". Na ferrovia, todos os marcos saem "<!-- n:ferrovia.cobertura.confianca_todos_marcos -->alta". "O sistema diz quando a própria previsão é frágil." |
| **Tendência** (`/api/tendencia?obra=rodovia`) | A previsão independente passa a divergir da construtora em **<!-- n:rodovia.tendencia.obra.divergencia_desde -->05/10/2026**, a semana do 1º boletim de CBUQ do L2 |
| Tornado | O maior efeito é o **CBUQ do L2**: −10% → **<!-- n:rodovia.sensibilidade.piorar -->+9 dias**; +1 equipe → **<!-- n:rodovia.sensibilidade.mais_1_equipe -->−34 dias** |
| Linha de balanço | **<!-- n:rodovia.balanco.conflitos -->22 conflitos** previstos (ex.: CBUQ × defensas no L1-S04), <!-- n:rodovia.balanco.conflitos_reais -->0 reais |

### Fecho (cerca de 1 min): D5, IFC 4.3

- A plataforma **exporta** cada obra em **IFC 4.3 (IFC4X3_ADD2)**, com alinhamento, elementos vinculados às
  atividades e o cronograma 4D nativo (IfcTask).
  - Ferrovia: **<!-- n:ferrovia.ifc.elementos -->537 elementos**, <!-- n:ferrovia.ifc.com_vinculo -->537 vinculados, **<!-- n:ferrovia.ifc.tarefas -->339 IfcTask** (113 atividades × 3 cronogramas: linha de base,
    construtora e independente), 1 IfcAlignment.
  - Rodovia: **<!-- n:rodovia.ifc.elementos -->531 elementos**, **<!-- n:rodovia.ifc.tarefas -->411 IfcTask** (137 × 3).
  - Reimportar o IFC e recalcular no motor dá exatamente as mesmas datas da API.
  - Validação `ifcopenshell.validate` com regras EXPRESS: **<!-- n:ferrovia.ifc.erros_validacao -->0 erros** nas duas.
- Frase obrigatória: o IFC é **gerado** a partir da base sintética. Ainda não lemos IFC de cliente.

## O que funciona hoje (verificado por teste automatizado)

Cada item tem o arquivo de teste que o verifica (pytest, em `tests/`). "Verificado" quer dizer executado e
observado, sempre com dados fictícios.

| Capacidade | Teste |
|---|---|
| Motor CPM próprio: FS/SS/FF/SF com lag, calendários com feriados e chuva, marcos, SNET/FNLT, data de status (*progress override* ou *retained logic*), folgas, caminho crítico | `test_motor_cpm.py`, `test_revisao_adversarial_motor.py`, `_r2` a `_r4` |
| Duração pela produtividade medida, com memória de cálculo; o vertical slice ponta a ponta pela API (produtividade → duração → rede → término → painel → 4D) | `test_vertical_slice.py`, `test_smoke.py` |
| Duas obras pela mesma API (`?obra=`), com módulos opcionais que não derrubam a API | `test_api_obras.py`, `test_dados_sinteticos.py`, `test_dados_rodovia.py` |
| Earned Schedule; Monte Carlo v1/v2 com criticidade | `test_previsao_es.py`, `test_montecarlo.py` |
| Sensibilidade (tornado) e plano de recuperação | `test_sensibilidade.py`, `test_recuperacao.py` |
| Linha de balanço com conflitos (cruzamento analítico e linha real), histograma e nivelamento | `test_recursos.py` |
| Importar e exportar MSPDI, importar XER, comparar com o motor; DCMA 14 pontos | `test_importadores_mspdi.py`, `test_importadores_xer.py`, `test_dcma.py` |
| Fiscalização no modelo da IN 57/DNIT (diário, chuva, km executado, estados, conciliação). Conciliação: **<!-- n:ferrovia.fiscalizacao.divergencias -->0 divergências** em <!-- n:ferrovia.fiscalizacao.boletins -->463 e <!-- n:rodovia.fiscalizacao.boletins -->427 boletins | `test_fiscalizacao.py` |
| Histórico, cenários salvos e auditoria (SQLite fora do Git) | `test_persistencia.py` |
| Diagrama de massas e produtividade pela DMT | `test_massas.py`, `test_produtividade_terraplenagem.py` |
| IFC 4.3: exportar, reimportar o vínculo, GLB, validação | `test_ifc.py` (dá SKIP sem `ifcopenshell`) |
| 5D fictício (curva S financeira, EVM de custo) e exportação para BI (<!-- n:ferrovia.bi.tabelas -->11 tabelas CSV/ZIP) | `test_orcamento.py`, `test_exportacao.py` |
| Relatório técnico e cabeçalhos de segurança (CSP) | `test_relatorio.py`, `test_api_seguranca.py` |
| Interface no navegador, inclusive o tour (os números do texto conferidos contra a API) | `tests/e2e/verificar_interface.py` (Chrome headless, fora do pytest) |
| Revisão adversarial independente em 17 rodadas; cada defeito vira teste de regressão | `test_revisao_adversarial_*.py` |
| Os números deste roteiro | `test_numeros_demo.py` |

## O que é simulado ou ainda não existe

- **Dados fictícios.** As duas obras, os boletins, o cenário "construtora", o histórico mensal, os diários de
  fiscalização, os preços do 5D e o custo real (AC) são gerados. Nenhum dado real entrou.
- **Geometria esquemática.** O 3D é gerado do eixo e das atividades. O "Modelo IFC" também é **gerado por nós**,
  não é IFC de projeto.
- **Sem arquivo real de MS Project ou Primavera.** Os importadores foram validados com ida e volta própria e
  arquivos escritos à mão. **A compatibilidade com P6/Project não é alegada.**
- **Sem login, sem multiusuário, sem servidor.** Roda nesta máquina; a auditoria grava "quem" como texto livre.
- **Premissas de engenharia em ordem de grandeza.** O R09 conferiu parte delas com referências públicas: solda,
  imprimação, CBUQ e dormentes ficam dentro; a grade manual fica abaixo do método mecanizado. Na ferrovia, o
  terreno sintético gera **<!-- n:ferrovia.massas.diferenca_pct_abs -->23,5% menos** volume que a quantidade de terraplenagem do cronograma (<!-- n:ferrovia.massas.coerentes -->0 de 12
  segmentos coerentes; na rodovia, <!-- n:rodovia.massas.coerentes -->12 de 12).
- **Chuva sintética:** probabilidade sorteada, ainda não é o fator de chuva do SICRO.
- **Histórico da construtora sintético** (ver D4) e **5D sem SICRO/SINAPI** (por licença: CC BY-ND e termos não
  verificados).

## Posicionamento (R08)

Frases que podem ser ditas, cada uma demonstrável na tela ou num documento:
1. "O INFRA 4D recalcula o término a partir da produtividade medida nos boletins e mostra, para cada data, de onde
   veio o número."
2. "Quando a previsão muda, o sistema explica, atividade por atividade, quanto aquela mudança sozinha move o término."
3. "Três métodos lado a lado (caminho crítico, Earned Schedule e Monte Carlo). Quando eles divergem, isso também é
   informação."
4. "O cronograma da construtora, em MS Project XML ou Primavera XER, é recalculado no nosso próprio motor para
   auditoria. Hoje, validado com arquivos de teste; a validação com arquivos reais é o próximo passo."
5. "Para obra linear, a linha de balanço tempo-km aponta onde e quando duas frentes vão se encontrar, junto do
   caminho crítico e do 4D."
6. "A fiscalização segue o modelo de medição do DNIT (IN 57/2021): diário, chuva, km executado e aprovação do fiscal.
   Complementa o SIAC; não o substitui."
7. "Tudo o que você está vendo roda nesta máquina, sem licença paga e com dados fictícios."
8. "Exportamos a obra para IFC 4.3, com alinhamento e cronograma, e o arquivo passa no validador do IfcOpenShell sem
   erros. O teste com modelo de cliente ainda não foi feito."

**O que NÃO dizer:**
- "compatível com P6/Project";
- "substitui SYNCHRO, Navisworks, TILOS ou o SIAC";
- "mais preciso que o mercado";
- "pronto para produção";
- qualquer número de economia, acerto ou ganho de prazo;
- "a construtora X fez Y": nada aqui é de construtora real.

## Caminho para a implantação real (resumo de `docs/IMPLANTACAO-REAL.md`)

| Fase | O que entrega | Critério de saída (testável) | Depende de |
|---|---|---|---|
| 1. Governança | Novo ADR para dado real, `dados_sensiveis: true`, dado no Drive (fora do Git), LGPD (fotos e nomes) | `/os:security` limpo; teste que impede arquivo real no Git | decisão da titular |
| 2. P6/Project reais | Ida e volta com arquivos de ≥ 2 obras contra as datas do P6/Project | término dentro da tolerância do manifesto; divergências explicadas | arquivos reais |
| 3. Calibração | Faixas de plausibilidade com fonte (R09: CAL1–CAL7) | alerta não muda o cálculo; [OG] declarado | — |
| 4. Medições reais | Importador por arquivo (SIAC sem API pública), filtro por estado aprovado | regras de recusa testadas com arquivo anonimizado | Fases 1–2 |
| 5. Multiusuário | Login, papéis (construtora/fiscal/gestor), auditoria pela sessão | matriz rota × papel testada | decisão de autenticação |
| 6. Hospedagem | Local, servidor da empresa ou nuvem (nada contratado) | restauração executada uma vez | decisão de custo |
| 7. Integrações | IFC de cliente com validação local, coleta de campo (ODK) | por integração | — |

## Perguntas prováveis da Pessoa A e respostas honestas

**"Isso funciona com o cronograma real da minha obra?"**
Lemos MS Project XML e Primavera XER, mas só testamos com arquivos de teste. O primeiro passo é rodar um arquivo
real e comparar, atividade por atividade, com as datas que o P6/Project calcula. Até lá, não afirmamos
compatibilidade.

**"Por que eu confiaria nessa previsão mais do que na da construtora?"**
Não se trata de confiar. Cada data mostra a conta: quantidade restante ÷ (produtividade medida × equipes), qual
boletim alimentou e qual cadeia determina o término. E há três métodos para confrontar; na ferrovia o Earned
Schedule fica <!-- n:ferrovia.es.diferenca_dias_abs -->29 dias antes do CPM, e o sistema explica por quê.

**"Os <!-- n:ferrovia.painel.delta_dias -->48 dias são reais?"**
Não. São de uma obra fictícia, construída para ter um atraso concentrado na terraplenagem do Lote 3. O que é real
é o método.

**"Substitui o P6, o SYNCHRO ou o SIAC?"**
Não. É uma segunda opinião independente e auditável sobre o cronograma e a medição que já existem.

**"E o modelo BIM do projeto?"**
Exportamos e reimportamos IFC 4.3 com 0 erros no validador, mas com um modelo gerado por nós. O teste com IFC de
projeto real é a próxima etapa (há arquivos oficiais de teste da buildingSMART já integrados aos testes).

**"Quanto custa?"**
Hoje, zero de licença: tudo roda localmente com componentes de licença permissiva. Hospedagem, suporte e
integração com dado real são custos a decidir (Fase 6).

**"Os dados da fiscalização (fotos, nomes) ficam seguros?"**
Hoje não há dado real nem login: é demonstração. Para operar, o plano prevê LGPD, papéis por usuário, auditoria
pela sessão e foto guardada só como referência + hash (Fases 1 e 5).

**"O plano de recuperação não dizia inviável por 1 dia?"**
Dizia, e estava errado: acelerar TODAS as frentes empatadas ao mesmo tempo atrasava o término (ligações de
término e de início entre atividades — o "paradoxo da atividade reversa"). A aceleração por custo mostrou que
acelerar só 4 frentes cumpre o prazo. Hoje a recuperação só mantém um encurtamento que não piora o término e,
antes de dizer "inviável", confere com a aceleração. Achado e corrigido com teste de regressão (2026-11-13).

**"Os números de produtividade são de onde?"**
São premissas de ordem de grandeza (R03/R06). O R09 conferiu parte delas com referências públicas: solda,
imprimação, CBUQ e dormentes dentro; grade e terraplenagem com ressalvas. Com dado real, a produtividade vem dos
boletins da própria obra.
