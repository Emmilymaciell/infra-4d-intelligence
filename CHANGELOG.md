# CHANGELOG — INFRA 4D INTELLIGENCE

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Semantic Versioning (`MAJOR.MINOR.PATCH`). Tag só depois de validação ponta a ponta.

<!--
  Atualizado por /os:checkpoint, antes do commit — nunca depois.

  Uma entrada por versão, agrupada em: Adicionado · Alterado · Corrigido ·
  Removido · Segurança.

  Registre também o que foi TENTADO E REVERTIDO. É a informação que se perde
  primeiro, e a que mais economiza tempo de quem vier depois — inclusive você
  em três meses.

  Em "Corrigido", diga COMO o bug foi descoberto, não só o que era. Se um
  teste passava e o bug existia, isso é informação sobre a suíte.
-->

## [Não lançado]

### Pausa para revisão da titular — 16/11/2026

- Desenvolvimento suspenso por ordem expressa; nenhuma funcionalidade, refatoração,
  correção nativa ou melhoria visual feita neste encerramento. Versão permanece 0.2.0.
- Snapshot de pausa, inventário e continuidade Codex/Claude documentados; próxima
  sessão começa pela revisão da titular, sem implementar automaticamente a missão V3.
- Preservação Git/WIP e resultados fora do Git, banco consistente, manifestos e hashes
  executados somente nos destinos autorizados; resultados reais constam dos recibos.
- Segurança: achado médio histórico bloqueou inicialmente checkpoint/push; após
  consulta, a titular liberou somente esse caso para a preservação privada, mantendo
  a decisão definitiva para a retomada (ADR-0017). Sem reescrita ou supressão do achado.
  FreeCAD inicialmente sem geometria visível registrado como relato da
  titular, sem investigar ou corrigir agora. Sem homologação ou dados reais do Programa.

### Continuação local — OAE editável e retorno FCStd existente (14/11/2026)

- OAE fictícia de 196 componentes paramétricos FreeCAD, seis atividades e 108 IDs
  da publicação preservados; 36 m parciais, sem dimensionamento estrutural.
- Retorno de FCStd existente com edição/salvamento/reabertura, STEP reimportado e
  malhas por componente; derivados de volume/área separados do planejamento e CPM.
- Seleção e propriedades CAD laterais, materiais e ambiente ilustrativo sem
  duplicar a ponte procedural. Referência e números da demonstração preservados.
- Correções de revisão: grupo com Shape agregada não duplica peças, manifesto
  comparado ao mapa confiável, IDs verificados; sem delta fictício para FCStd já editado.
- GUI FreeCAD indisponível pelo canal Computer Use; comprovação é runtime oficial.
  Guia, limitações, resultados e evidências em `docs/interop/FREECAD-OAE-RETORNO.md`
  e no topo do STATE. Sem commit/push, instalação global ou dados do Programa.

### FreeCAD paramétrico e inspeção de revisões — 14/11/2026

- Adaptador externo FreeCAD: fragmento com três Part::Box, propriedades de vínculo
  e quantidades de planejamento, editar Height/salvar/reabrir FCStd, exportar e
  reimportar STEP e tesselação convertida mm→m. Três IDs nativos verificados;
  108 IDs conservados na publicação, sem inferência de quantidade pela malha.
- Contrato/API/UI reconhecem FreeCAD com sua própria autoridade. Enquadrar revisão
  e Só revisão resolvem distância/oclusão observadas nas capturas; picking respeita
  visibilidade de ancestrais e seleção isolada mantém o fragmento enquadrado.
- R23 detectou isolamento persistente em revisão vazia: teste com Three.js real
  em cópia falhou antes, passou após correção e ficou sem marca xfail. Caso também
  verificado no navegador. Não altera referência, dados ou cálculos da demo.
- Verificação: 116 PASS (+6 skips), 37 PASS de referência, Chrome 227 completo;
  Edge 218 completo no estágio inicial +39 focados nos controles finais.
  Native CAD via API oficial/headless; GUI/GPU/projeto executivo não homologados.

### Correção documental autorizada — 14/11/2026

- Titular autorizou substituir o e-mail institucional em R10-obrasgov pelo link
  oficial (HTTP 200 conferido). Histórico e evidências anteriores preservados;
  sem exceção de segurança, commit, instalação ou publicação. Revarredura e adendo
  registrados no STATE; código e dados da demonstração inalterados.

### Missão Codex V3 — incremento validado localmente (13–14/11/2026)

- Variante visual de apresentação com terreno sintético, detalhe de ponte,
  dormentes instanciados, câmera local, modo reunião/técnico 1:1/baixo consumo e
  fallback 2D; modo de análise e números congelados preservados.
- Contrato de revisão agregada por atividade linear e API de federação em cópia
  isolada (ADR-0016), com recusa de conflitos de IDs, unidades e baseline.
- Scripts de autoria externos para QGIS e Blender, pacote de intercâmbio e
  planilha de quantitativos com fórmulas. Provas de runtime oficial separadas de
  observação GUI; nenhum dado do Programa ou compatibilidade comercial alegada.
- Auditoria r22 encontrou metadados inválidos virando HTTP 500 e unidades de
  origem alteráveis; regressões criadas antes da correção. E2E encontrou diferença
  int/float na serialização browser da baseline; comparação estrutural preserva
  equivalência numérica sem aceitar booleanos como números.

- Partida fria com cena cinza corrigida ao priorizar estado4D sobre análises
  opcionais. Suíte completa detectou fallback ferroviário na nova rota: corrigido
  para tipo declarado, com regressão rodoviária; interpolações internas novas
  revisadas no detector XSS, sem exceção geral.
- Verificação final: **2040 PASS, 6 SKIP, exit 0**; Chrome **214 PASS** e Edge
  **220 PASS**. Evidências de runtimes oficiais, planilha renderizada e vídeo
  de capturas em pacote local. Segurança: contato institucional herdado pendente
  de decisão; sem liberação de publicação, commit ou envio externo.

### Adicionado

- **API multi-obra:** `?obra=` em todas as rotas e `GET /api/obras`. As obras são descobertas em
  `examples/synthetic/*_ficticia.json`. Os módulos opcionais entram por `registrar_rotas`, e um módulo quebrado
  ou ausente não derruba a API (o estado aparece em `/api/saude`).
- **Relatório técnico imprimível** em `GET /api/relatorio`: resumo, explicação construtora → independente, cadeia
  determinante, alertas, produtividades, restrições, simulação ativa, método e limitações. É gerado do mesmo motor
  e escapa o HTML.
- **Motor:**
  - `restricao_termino` (FNLT, "término não depois de"), com folga negativa legítima;
  - `logica_progresso="retida"` (retained logic, padrão do P6) como alternativa ao *progress override*.
- **Painel:**
  - `marcos_contratuais`: prazo da linha de base contra cada previsão, com desvio em dias;
  - `sensibilidade_logica`: término independente com *progress override* e com *retained logic*.
- **Rodovia fictícia BR-FIC 999** (agente rodovia): 48 km, 137 atividades, 301 relações, 427 boletins, com o
  mesmo esquema da ferrovia. Serve pela API multi-obra sem nenhuma alteração no motor. A narrativa é o CBUQ crítico
  limitado pela usina compartilhada entre L2 e L3.
- **`sintetico_comum.py`:** a ferrovia e a rodovia passam a usar o mesmo código de realidade simulada e boletins.
  Os dois JSON ficaram byte a byte idênticos (sha256 conferido antes e depois).
- **Referência linear** (`referencia_linear.py`, `/api/referencia`): km ↔ estaca de 20 m (declarada como
  convenção), km → xy/cota/rumo, xy → km + afastamento com lado e cobertura de lote/segmento/atividades.
- **Importadores de cronograma** (`importadores/`, só biblioteca padrão; agente cronogramas):
  - MSPDI: exporta e importa, com ida e volta exata nos três cenários;
  - P6 XER: importação;
  - `POST /api/cronograma/comparar`: audita o cronograma da construtora contra o motor independente.

  Compatibilidade com MS Project e P6 reais **não é alegada**.
- **Fiscalização** (`fiscalizacao.py`, `/api/fiscalizacao`): diário e boletim no modelo da IN 57/DNIT/2021 (estados,
  chuva, km executado, memória de cálculo), validação campo a campo, conciliação, perda por chuva e linha real tempo-km.
- **Recursos** (`recursos.py`, `/api/recursos`):
  - histograma de equipes e equipamentos;
  - nivelamento por SGS serial (heurístico, declarado), com capacidades e frota compartilhada `*/SERV`;
  - conflitos de balanço com cruzamento ANALÍTICO de frentes (E1) e conflitos reais pela linha executada.
- **Previsões:**
  - Earned Schedule (`previsao_es.py`, `/api/previsao/earned-schedule`): SPI(t) e IEAC(t), fórmulas conferidas
    com a R05;
  - Monte Carlo v2: correlação entre frentes, riscos discretos e chuva estocástica. Com os padrões, reproduz a v1
    bit a bit.
- **Relatório:** tabela com os três métodos de previsão (CPM, Earned Schedule e Monte Carlo).
- **Persistência e histórico** (`persistencia.py`, `/api/historico`, SQLite em `output/`, ignorado pelo Git):
  - cenários salvos com conferência de reprodução;
  - snapshots e auditoria;
  - evolução mensal sintética da previsão. Na rodovia, a construtora manteve a mesma data por 8 meses.
- **Interface:**
  - seletor de obra;
  - relatório;
  - 3D genérico com serviços da rodovia;
  - abas Recursos, Cronograma da construtora (exportar, importar e comparar) e Fiscalização;
  - linha real e conflitos na linha de balanço;
  - km e estaca no 3D;
  - três métodos de previsão e Monte Carlo v1 × v2 no painel;
  - e2e com 77 checagens.
- ADR-0005: marca booleana explícita `meta.ficticio` como trava contra a geração de dado inventado sobre obra real.
- **Diagrama de massas (Brückner)** (`massas.py`, `/api/massas`, agente rodovia):
  - seção trapezoidal, volumes por média das áreas, Fh e empolamento;
  - ondas de compensação, DMT e momento de transporte;
  - coerência contra a quantidade de TER do dataset. A ferrovia fica cerca de 23% abaixo: a premissa de 70.000 m³/km
    pede terreno ou seção mais severos. O relatório só aponta a diferença; o dataset não foi alterado.
- **BIM 5D SINTÉTICO** (`orcamento.py`, `/api/orcamento`, experimento E7):
  - composições e preços FICTÍCIOS, sem nenhum dado do SICRO ou SINAPI (CC BY-ND e termos não verificados);
  - curva S financeira e EVM de custo (CPI, SPI, EAC);
  - recusa obra sem `meta.ficticio`.
- Cabeçalhos de segurança: CSP estrito na interface (script só do próprio site e importmap por hash) e CSP sem
  script no relatório; `nosniff` e `no-referrer` em todas as respostas.
- `pytest.ini` com `faulthandler_timeout = 300`. Três suítes completas rodando em paralelo travaram com 0% de CPU e
  sem pilha disponível; a instalação do py-spy foi negada pela política do ambiente e não foi contornada. Agora um
  travamento imprime a pilha de todas as threads. A suíte rodando sozinha não trava (130 s).

- **IFC 4.3** (`ifc/`, `/api/ifc`; IfcOpenShell LGPL, usado sem modificação):
  - exporta a ferrovia (IfcRailway) e a rodovia (IfcRoad, com classes de pavimento, sinalização e defensas), com 0
    erros na validação do IfcOpenShell, inclusive as regras EXPRESS;
  - alinhamento semântico e 4D nativo (IfcTask + IfcRelAssignsToProduct);
  - tabela de vínculo GlobalId ↔ atividade; GLB com o GlobalId nos nós;
  - teste opcional baixa arquivos OFICIAIS da buildingSMART para `output/` (fora do Git, SHA-256 registrado):
    0 erros, e "sem alinhamento" é declarado em vez de inventado.
- **Plano de recuperação de prazo** (`recuperacao.py`, `/api/recuperacao`): menor esforço para cumprir o prazo, com
  viabilidade frente à melhor semana medida, verificado aplicando o plano no simulado.
  - Ferrovia: prazo inviável por 1 dia, mesmo com 2× a produtividade.
  - Rodovia: viável com mudança de método.
- **Sensibilidade (tornado)** (`sensibilidade.py`, `/api/sensibilidade`): ±p por (lote, serviço) e +1 equipe;
  marca assimetria, efeito zero e atividade reversa.
- **Exportação para BI** (`exportacao.py`, `/api/exportar`): modelo estrela em CSV pt-BR (UTF-8 com BOM e `;`),
  neutralização de injeção de fórmula, ZIP com dicionário de dados.
- **Pesquisa e documentação:** R07 (experimento IFC), R08 (benchmark de mercado e posicionamento, com fonte em cada
  afirmação) e `docs/IMPLANTACAO-REAL.md` (7 fases com critérios de saída e as decisões da titular).
- Testes: banco SQLite isolado por sessão (`INFRA4D_BANCO` em tmp), achado da revisão r8.
- **Monte Carlo:**
  - índice de criticidade por atividade e por grupo, com correlação duração × término. A rede à mão bate com o
    analítico (0,251 contra 0,25), com tolerância declarada no manifesto;
  - opção de usar só boletins aprovados/conferidos pela fiscalização;
  - na rota: `com_criticidade` e `so_aprovados`.
- **Diagrama de massas:** conserva volume exatamente; a ferrovia agora tem DMT média de 653 m e compensado igual ao
  corte. **Orçamento:** EV ancorado no executado.

- **DCMA 14 pontos** (`dcma.py`, `/api/dcma`, `/api/dcma/importado`):
  - qualidade do cronograma importado da construtora e dos nossos cenários;
  - limites conferidos na documentação Deltek Acumen 8.11; os não confirmados estão marcados;
  - o teste do caminho crítico (ponto 12) é EXECUTADO no motor.
- **Cenários climáticos** (`clima.py`, `/api/clima`): chuvoso, seco e deslocado sobre os calendários sensíveis à chuva,
  com âncora na data de status. Rodovia +30% de chuva: +21 dias.
- **IFC etapa 3:**
  - `Qto_*BaseQuantities` oficiais calculados da geometria;
  - requisitos de informação 4D/5D. As duas obras aprovam; os arquivos oficiais da buildingSMART reprovam onde devem;
  - classificação com o código de composição fictício, e o custo pelo modelo é igual ao BAC do orçamento, atividade
    por atividade.
- **Roteiro da demo reescrito** (`docs/DEMO-PESSOA-A.md`), com todos os números gerados por
  `python -m infra4d.numeros_demo`, testado. R09: calibração das premissas contra fontes públicas.
- **Registro de riscos ao prazo** (`riscos_prazo.py`, `GET /api/riscos`): consolida 9 fontes já calculadas
  (produtividade, restrições, clima, tornado, criticidade do MC, ES×CPM, recuperação, balanço, DCMA), deduplica
  por frente, ordena por exposição Δ×p declarada, e cada risco traz a evidência (rota + caminho no JSON) que o
  teste reconsulta pela API. Fonte quebrada vai para `fontes_omitidas`. Ferrovia: 20 riscos; rodovia: 23.
- **GeoJSON para QGIS** (`gis.py`, `GET /api/gis/geojson`): RFC 7946 (lon/lat, mão direita), georreferência
  FICTÍCIA declarada no `meta` (âncora no interior do Brasil, plano tangente WGS84 sem dependência nova), camadas
  eixo, lotes, segmentos, atividades com estado 4D, marcos, restrições, conflitos de balanço no cruzamento, estacas e
  faixa de domínio. Ida e volta até o km dentro de `tolerancia_georef_m`.
- **IFC etapa 4:** todas as peças com `IfcLinearPlacement` sobre o eixo (mesma posição que antes, 1,5e-11 m;
  `tolerancia_posicao_ifc_m`) e `IfcReferent` com `Pset_Stationing` a cada km e nas equações de estacas, conferidos
  contra `/api/referencia/km`. Exportação de 23–41 s para 2–3 s (avaliação por segmento). Limite registrado no R07:
  o IFC não tem fator de escala de estaqueamento, então entre referentes a estaca lida por terceiros diverge até 18 m.
- **Exportação XER** (`importadores/xer_exportar.py`, `GET /api/cronograma/exportar/xer`): PROJECT, CALENDAR,
  TASK e TASKPRED; ida e volta pelo próprio importador idêntica nos 3 cenários das 2 obras (ES/EF, término,
  caminho crítico). O importador passa a ler FNLT (CS_MEOB) e o 2º par de restrição. Não se alega compatibilidade
  com o P6 real; o que não é exportado fica declarado em `NAO_EXPORTADO`.
- **Tendência de marcos (MTA)** (`tendencia.py`, `GET /api/tendencia`): término por cenário a cada data de status
  passada, reconstruído só com o que se sabia naquela data (teste que adultera o futuro e não muda nada),
  inclinação em dias/semana e data em que a independente divergiu da construtora. Limite: numa obra real, a
  fotografia deveria vir do histórico versionado, não ser reconstruída.
- **Curva S física e financeira** (`curva_s.py`, `GET /api/curva-s`): planejado, previsto (construtora e
  independente) e realizado por obra e lote; na data de status o físico bate com o painel e o financeiro com o EV.
- **Backtest da previsão** (`backtest.py`, `GET /api/backtest`): erro do término previsto em cada data passada contra
  duas referências declaradas — o término independente atual (circular, medida) e a `realidade_simulada` que o
  gerador sorteia e não exporta (não circular). M-FIM: independente com MAE de 26 d (ferrovia) e 32 d (rodovia)
  contra 75 d e 41 d da construtora, melhor desde a 2ª–3ª semana.
- **Aceleração com custo** (`aceleracao.py`, `GET /api/aceleracao`): guloso por menor custo por dia ganho, com
  passo composto em caminhos paralelos e mobilização; ajustes prontos para `/api/simulacao`. Revelou que o
  "inviável por 1 dia" da recuperação na ferrovia era falso (paradoxo da atividade reversa no passo de empate).
- **Interface:** tendência de marcos, downloads GeoJSON e XER, cartão de riscos, DCMA, clima nas Análises,
  salvar/reabrir cenário. e2e 153/153.
- **Atribuição do erro da previsão** (`atribuicao_erro.py`, `/api/backtest/atribuicao`): numa data passada, troca a
  produtividade de uma frente por vez pela verdadeira do mundo sintético e mede quanto o erro cai, com resíduo de
  interação. Rodovia, M-L2-FIM em 30/03/2026: o CBUQ do L2 explica −59 → −1 dia. `test_gabarito_isolado.py` só
  permite ler os fatores verdadeiros no gerador e nas ferramentas de avaliação.
- **Monte Carlo com incerteza alargada para frente sem medição** (P4, desligado por padrão, exposto em
  `/api/previsao-probabilistica?incerteza_sem_medicao=true`). A 1ª versão ANTECIPAVA a previsão (r19: P50 da
  ferrovia 6 dias mais cedo, porque trocava a analogia do mesmo serviço pela obra inteira); corrigida para manter a
  analogia como centro e só alargar. Alargamento recalibrado no backtest para 0,5 (teto 0,6 na rota): a realidade
  cai em P10–P90 em 26/28 datas×marcos na rodovia e 21/28 na ferrovia (6/28 e 14/28 sem o modo); 28 casos por
  obra, mundo sintético.
- **Roteiro da demo à prova de envelhecimento:** 96 números do `DEMO-PESSOA-A.md` com marcador, conferidos contra
  o sistema por `test_roteiro_demo.py`; o roteiro foi reescrito pela auditoria R14.
- **Contrato interface × API** (`test_contrato_interface.py`): as 52 chamadas de `web/api.js` existem no OpenAPI com
  método e parâmetros declarados.
- **Interface:** confiança por marco, comparação de revisões (cenários ou arquivos), download do IFC com cronograma,
  selo de simulação coberto no e2e (181/181).
- **Comparação de revisões de cronograma** (`comparar_revisoes.py`, `/api/revisoes/comparar`): inventário de
  mudanças entre duas versões (cenários, MSPDI ou XER), efeito isolado de cada uma no término com resíduo de
  interação declarado, reconstrução exata de B como prova de completude, "data de status + progresso" agrupados por
  padrão, alertas para o fiscal (lag negativo novo, restrição nova no crítico, lead aumentado, calendário trocado...)
  e teto de 2000 execuções do motor.
- **Cobertura da previsão** (`cobertura.py`, `/api/cobertura`): por marco, origem da produtividade do remanescente
  (medida, analogia, planejada), confiança por estresse no motor (f = pior índice já observado até a data, nunca o
  fator escondido do gerador) e alerta de frentes sem medição com folga ≤ `folga_alerta_sem_medicao_du` até o marco.
  Limite honesto registrado no R12: em 30/03 nenhum sinal justo marca "baixa" no L2 da rodovia.
- **BDI por obra pela fórmula do TCU** (ferrovia 23,48%, rodovia 22,22%, dentro da faixa do Acórdão 2622/2013) e
  **reajuste por índice sintético** com anualidade (R11). O BDI antigo de 25% estava acima do 3º quartil.
- **OpenAPI:** todas as rotas fora do IFC com descrição e erros 4xx documentados; `test_openapi.py` só deixa a lista
  de pendências encolher.
- **`simulacao_do_usuario`** nas rotas que usam o cenário independente de propósito, com selo na interface; auditoria
  de caches (`test_caches_coerentes.py`) sem nenhum dado velho encontrado.
- **R13:** interoperabilidade 4D. Achado um defeito no IfcOpenShell 0.9 (exceção de calendário torna não úteis
  todos os dias anteriores ao término dela); rascunho de issue preparado e NÃO enviado (decisão da titular).
- **Orçamento ↔ IFC:** o mapa IFC do orçamento deixa de ser mantido à mão e passa a ser derivado do exportador;
  teste confere classe e tipo em mais de 500 elementos realmente exportados por obra.

### Transferência para o Codex e demo (2026-11-13)

- `docs/DEMO-5-MINUTOS.md`: roteiro de 5 minutos com a ordem de navegação, as seleções e as simulações (números do
  roteiro completo, conferidos por teste).
- `docs/HANDOFF-CODEX.md` (interno, não publicado): estado verificado, arquitetura, comandos, limitações e próximos passos para o Codex CLI.
- `AGENTS.md`: adaptador do Codex atualizado, sem contradizer o `CLAUDE.md`. Aponta para o registry e para os
  arquivos canônicos.

### Alterado (P9, depois da auditoria de 2026-11-13)

- **Gabarito sintético fora do dataset (P9, ADR-0012):** os fatores verdadeiros e os términos da realidade simulada
  saíram de `examples/synthetic/*_ficticia.json` para `examples/synthetic/gabarito/<obra>_gabarito.json`, marcados
  FICTÍCIOS. Só se chega a eles pelo acessor `sintetico_comum.gabarito(dados)`, que recalcula pelo gerador e recusa
  arquivo adulterado. Backtest, sementes e atribuição dão números idênticos aos de antes (comparação com o HEAD).
  A guarda `test_gabarito_isolado.py` passou a acusar leitura direta do arquivo de gabarito.
- **ADR-0011 a 0015** registram as decisões da missão (0006–0010 reservados para não colidir com os ADRs do OS).
- **Auditoria completa** em `docs/AUDITORIA-2026-11-13.md` (suíte 1918 passando, e2e 189/189).

### Alterado (P8 e P10)

- **Teto de custo do Monte Carlo (P10):** a r20 mediu 22,9 s para 2000 iterações com todas as opções. A rota agora
  aplica um orçamento declarado (iterações × (1 + 0,5 por opção pesada) ≤ 4000) e responde 422 com o número de
  iterações que cabe, antes de rodar. O padrão simples (até 2000 iterações) não muda.

- **`tipo_obra` sem padrão silencioso:** helper único `scripts/infra4d/obra.py`; obra sem tipo ou com tipo
  desconhecido deixa de ser tratada como ferrovia em api, gis, exportação, persistência, massas, referência, XER,
  IFC, orçamento e na interface. Rotas que dependem do tipo respondem 422 com o motivo; `/api/obras` lista a obra
  mal declarada com `tipo: null`. Guarda estática impede o padrão de voltar. Revisado pela r21 (2 defeitos
  baixos, corrigidos: `classificacao-ifc` dava 500; a interface ainda assumia ferrovia em dois pontos).

### Corrigido (rodadas 19 e 20)

- **Varredura de robustez (r20):** todas as 64 rotas do OpenAPI, nas duas obras, com 17 entradas de borda por
  parâmetro e 8 corpos inválidos por POST: nenhum 500 nem chamada acima de 30 s, exceto dois casos, agora
  corrigidos: `POST /api/simulacao` com NaN/±inf/1e400 (a validação recusava, mas a resposta de erro ecoava o valor e
  estourava) e corpo não UTF-8 em `cenarios-salvos`. Ajustes da simulação agora estritos (sem booleano nem texto).
- **Atribuição (r19):** fatores do gabarito conferidos contra o próprio gerador; malformados → 422.
- **Monte Carlo P4 (r19):** deixou de antecipar a previsão (ver Adicionado).
- **Relatório (r18):** Monte Carlo com parâmetros fixos e declarados; dado incompleto não derruba mais o relatório;
  `cenarios.comparar` tolera atividade sem nome (derrubava `/api/comparacao`).
- **Sementes do backtest (r18):** só para a obra sintética; orçamento de custo declarado (422 com o passo mínimo).

### Corrigido (rodadas 17 e 18)

- **Orçamento (r17):** anualidade do reajuste contada por mês, ignorando o dia; data-base inválida e tipo de obra sem
  composição davam 500; nota do BDI descrevia o da obra com BDI explícito; BDI NaN/negativo aceito.
- **Cobertura (r17):** confiança "alta" sem nenhuma evidência (f = 1 e a cadeia sem medição) passa a "indeterminada";
  boletim ínfimo derrubava a rota.
- **Cronograma IFC de terceiro (r17):** 7 variações com atributo opcional ausente davam 500.
- **Boletim implausível derrubava a previsão independente** (achado pela pesquisa-verificada ao corrigir a r17):
  `ErroCalendario` agora vira 422 com o motivo em qualquer rota.
- **Recuperação (r18):** `?prazo=` vazio dava 500; `fator_max` não era validado.
- **Guarda da r8** trocada de lista fixa de arquivos pela verificação da proteção real do banco (a lista fixa
  derrubou o snapshot do `e5fa630`, sem risco real).
- **Processo:** teste de mutação editando o arquivo real (por segundos) era prática de vários agentes e gerou um
  falso Δ=0 visto pela r17. Agora só em cópia/monkeypatch.

### Corrigido (rodadas 15 e 16)

- **Recuperação da ferrovia dava "inviável por 1 dia", e era falso.** Descoberto pela aceleração com custo, que
  cumpria o prazo acelerando só 4 frentes: o passo de empate encurtava todas as frentes empatadas, inclusive as que,
  por FF/SS, atrasam o término (paradoxo da atividade reversa). Agora só mantém encurtamento que não piora o término
  e, antes de declarar inviável, confere com a aceleração. A ferrovia passa a "cumpre só com mudança de método".
- **Riscos (r15):** evidência do balanço apontava outro conflito; restrição em atividade concluída virava risco alto;
  marcos se fundiam; fontes repetidas contavam como confirmação; a ordem dependia do modo (agora pelo Δ).
- **Aceleração (r16):** platô do arredondamento declarava inalcançável um prazo alcançável; custo podia sair
  negativo; prazo vazio dava 500. Custo da ferrovia na demo: R$ 1,71 mi (era 1,65).
- **Comparação de revisões (r16):** alerta falso de manipulação quando a duração caiu por medição; "false" em
  texto virava verdadeiro.
- **Painel (r16):** restrição sem `data_liberacao` derrubava o `/api/painel`.
- A r16 procurou vazamento de dado futuro na fotografia da MTA e do backtest por contrafactual e não encontrou.

### Corrigido (rodadas 14 e 15)

- **Importação de medições (r14, ALTA):** numa obra real, arquivo que se declarava fictício em grafia não
  reconhecida (`#ficticio: true`, acento, `=verdade`, marca repetida) era aceito. Agora a marca é estrita (ADR-0005):
  só `#ficticio=true|false`, uma vez; obra real exige `false` explícito. Também: CSV estrito (aspas não fechadas
  engoliam uma medição), o limite global do módulo `csv` não é mais alterado, só dígitos 0-9.
- **Adaptador Obrasgov (r14):** campo aninhado fora do tipo dava AttributeError/TypeError; NaN no valor do contrato
  passava. Agora ErroObrasgov com o nome do campo; ids de contrato precisam ser inteiros.
- **Painel (r15):** `/api/painel` respondia 500 com restrição sem atividade ou meta sem `termino_linha_base`, e
  restrição pendente em atividade concluída virava alerta alto com "folga None".
- **Interface:** a falha de "salvar a simulação" era corrida do próprio e2e, não defeito da tela.

### Corrigido (rodadas 11 a 13)

- **Clima (r13):** sensibilidade à chuva só pela marca booleana `sensivel_chuva` (ADR-0005; texto é recusado);
  dias de chuva só nos meses chuvosos (feriado local em mês seco deixa de virar chuva); meio dia arredonda para cima.
  Achado pelo revisor; quatro testes xfail viraram regressão.
- **r11 e r12:** sensibilidade com p alto, boletim órfão, inteiro grande e nome do arquivo na exportação; DCMA com
  calendários diferentes e par SS/FF; volume externo no Brückner; frota sem sentido. Os 13 casos passaram com
  `--runxfail` antes de as marcas saírem.
- **IfcOpenShell 0.9 contornado:** PIs colineares derrubavam o alinhamento para polilinha em silêncio; arcos à
  direita com comprimento negativo.

### Corrigido (rodadas 7 a 10)

- **Frontend (r7):**
  - XSS por id de lote, id de serviço e data sem validação;
  - estaca calculada no navegador, que divergia da API e agora vem sempre da API;
  - % executado de duração fixa;
  - `detail` em objeto, falta de tratador global e campos ausentes.

  O e2e tem roteiros com dados maliciosos injetados (102/102).
- **Earned Schedule e Monte Carlo (r8):**
  - lote não iniciado aparecia "adiantado" (SPI 3,04), por causa da regra do patamar sem limite em AT;
  - obra no plano com status no fim de semana;
  - lote sem atividades dava 500;
  - risco incompleto dava 500.
- **Massas e orçamento (r9):**
  - o volume da onda composta era o pico e não a soma das subidas, então o volume não se conservava;
  - a passagem corte/aterro não era dividida;
  - o EV vinha dos boletins e não do executado.

  O revisor também corrigiu um esperado antigo errado dele mesmo, depois de refazer a conta.
- **Monte Carlo (r10):** o substituto sem boletim era descentrado em relação ao determinístico.

### Corrigido (rodadas 5 e 6 da revisão cruzada)

- **Importadores** (agente cronogramas):
  - entrada malformada dava 500 ou travava (inf/nan, 1e999, encoding desconhecido, herança e `clndr_data`
    recursivos, exceção de calendário gigante);
  - um DTD em UTF-16 ou tardio escapava da checagem;
  - um XER sem coluna essencial era importado em silêncio.

  Agora: recorte ao horizonte, limites declarados, rede de segurança para `ErroImportacao` e validação de colunas.
- **Recursos:** com lógica retida, o consumo contava desde a data de status, e não desde o remanescente; a linha de
  balanço tinha falsos negativos.
- **Fiscalização:**
  - a trava contra obra real lia o TEXTO do aviso e era contornável ("NÃO é fictício" passava); agora vale a marca
    booleana (ADR-0005);
  - OverflowError dava 500;
  - produção sem boletim não contava como divergência;
  - datas aceitavam formatos não declarados.
- **Referência linear:** estaca gigante dava 500, NaN/inf no eixo era aceito, o lado ficava errado em vértice de curva
  fechada e a cobertura ignorava trecho invertido.
- O teste do banco fora do Git falhava fora de um repositório; agora dá SKIP (achado ao verificar commit isolado).

### Corrigido

- Rodada 4 da revisão adversarial (`tests/test_revisao_adversarial_r4.py`): 5 defeitos.
  - O FNLT era anulado no marco final da obra, justamente o marco contratual.
  - Marco de término em feriado ficava com folga negativa.
  - Na lógica retida, a duração da sucessora era recuada no calendário errado.
  - Na lógica retida, uma predecessora concluída ainda segurava o remanescente; a escolha está declarada.
  - O router do relatório era global: um segundo app sequestrava o relatório do primeiro.
- `registrar_rotas` derrubava a API inteira quando o contrato de ligação de um módulo opcional era violado (achado
  pelo revisor e pelo frontend durante a missão). Agora o módulo fica indisponível e isso aparece em `/api/saude`.

## [0.2.0] - 2026-11-12

### Adicionado

- Estrutura inicial do projeto, criada por `/os:new-project`.
- Missão de execução versionada em `docs/missao/INFRA4D_PROMPT_EXECUCAO_COMPLETO.md` (interno, não publicado) (veio da raiz, onde estava
  sem rastreio e com nome que tinha espaço e parênteses).
- Verificação e2e da interface (`tests/e2e/verificar_interface.py`, Chrome headless, 41 checagens, fora do pytest).
- Aba Linha de balanço (tempo × km), vista 3D inicial na frente crítica e selo de caminho mais longo.
- Beta local executável (ADR-0002): motor CPM próprio (`scripts/infra4d/motor.py`, `calendario.py`), cenários
  linha de base / construtora / independente / simulado com memória de cálculo (`cenarios.py`), painel e estado 4D
  (`painel.py`), Monte Carlo P50/P80 (`montecarlo.py`), API FastAPI (`api.py`), interface web com three.js
  vendorizado (`web/`), `run-beta.ps1`.
- Base sintética determinística da ferrovia fictícia (`dados_sinteticos.py` → `examples/synthetic/ferrovia_ficticia.json`):
  3 lotes, 12 segmentos, 113 atividades, 264 relações, 463 boletins semanais.
- Pesquisa R01–R04 (`docs/research/`), ADR-0002 a 0004, `docs/BACKLOG.md`, `docs/DEMO-PESSOA-A.md`.
- Critério de pronto e limite `tempo_maximo_recalculo_s` no `project.yaml`, lidos pelos testes.

### Corrigido

- `progresso_em` lia a data de status do dicionário da atividade, onde a chave não existe: antes da data de status
  o 4D e o avanço mostravam previsão no lugar do real. Descoberto pelo teste que confere o avanço do painel contra o
  executado medido (diferença de 0,04 p.p.); regressão em `test_regressao_4d_usa_o_real_ate_a_data_de_status`.
- Soma dos boletins sintéticos estourava o total por arredondamento (2100,003 de 2100). Descoberto pelo teste de
  coerência da base.
- 22 defeitos do motor e da explicação, achados pela revisão adversarial (`tests/test_revisao_adversarial_motor.py`,
  escritos primeiro como `xfail(strict=True)`, hoje regressão): FF/SF e folga com calendários mistos (a passada para
  trás agora usa inversas exatas `inicio_mais_tardio`/`fim_mais_tardio`), progress override incoerente entre ida e volta,
  folga livre maior que a total, exibição de marcos de término, datas reais incoerentes aceitas, ciclo a jusante,
  rede vazia, horizonte do calendário, ponto flutuante na duração fixa, produtividade medida zero, explicação que dizia
  "absorvido"/"inalterado" indevidamente. Crítico passa a incluir o caminho mais longo (como o *Longest Path* do P6).
  A suíte anterior passava com todos esses defeitos: ela só usava calendário único e não tinha progresso com SS/SF.

- Rodada 2 da revisão adversarial (`tests/test_revisao_adversarial_r2.py`): 14 defeitos.
  - **Instantes de duração 0:** marcos e tarefas sem trabalho não tinham forma canônica (sáb e seg, que são
    equivalentes em tempo de trabalho, eram tratados como instantes diferentes). Isso dava folga negativa com lag
    negativo, um degrau de 1 dia criado pela regra "marco no piso acontece no fim do dia" (introduzida na correção da
    rodada 1 e removida) e marco exibido antes do evento que o dispara. Correção: cada fronteira tem tipo (fim de dia ou
    início de dia), e a volta usa a inversa de início para instantes.
  - **Explicação:** "excedem e se propagam" para atividade ligada só pelo início, e "COMPARTILHADA" sem outra
    alteração. Correção: o texto é decidido pelo efeito isolado contrafactual.
  - **Monte Carlo e painel:** não tinham herdado as defesas da rodada 1 (boletim zero, boletim órfão, falta de
    `lote_id`). O Monte Carlo passou a usar bootstrap ponderado com a mesma hierarquia de fontes, centrado no
    determinístico.
  - **Estado 4D:** marcava "concluído" com 99,95 %.
- Ao conferir a explicação pelo contrafactual, apareceu o **paradoxo da atividade reversa** no dataset: alongar
  L3-S04-DOR em +1 dia antecipa o término em 1 dia útil (FF de entrada, SS de saída). É CPM correto e agora é explicado
  como tal; regressão em `test_atividade_reversa_alongar_antecipa_o_termino`.

- Rodada 3 da revisão adversarial (`tests/test_revisao_adversarial_r3.py`): 6 defeitos, com marcos incluídos no
  gerador aleatório (3.000 redes) e testes da API.
  - **Instantes:** folga -1 em cadeia de marcos após uma sexta-feira. Instante solto com folga que movia o término
    exibido. SF/FF para marco de início com feriado. Empate de tipo de fronteira.
  - **API:** ajuste extremo dava 500 e **envenenava o estado** até um DELETE. Agora o cenário é calculado antes de
    gravar e o erro vira 422 com o estado mantido. `?data=` vazio passou a dar 422. O cache do Monte Carlo
    ficou limitado.

### Tentado e revertido

- Primeira calibração da base sintética (início em 2025-04-07): na data de status 95 de 113 atividades estavam concluídas
  e a simulação não tinha o que mostrar. As restrições passaram a ser relativas ao início, e o início foi para 2025-11-03.
