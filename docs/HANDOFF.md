# HANDOFF — INFRA 4D INTELLIGENCE

> **PAUSADO — AGUARDANDO REVISÃO DETALHADA DA TITULAR (16/11/2026).**
> **PRÓXIMA SESSÃO: NÃO INICIAR DESENVOLVIMENTO AUTOMATICAMENTE. PRIMEIRO RECEBER E CONSOLIDAR A REVISÃO DA TITULAR.**
> Leia `SNAPSHOT-PAUSA-2026-11-16.md` e o topo de STATE antes dos blocos históricos.
> Base `1fa6445` + WIP preservado; commit da pausa identificado por `git log -1 -- docs/SNAPSHOT-PAUSA-2026-11-16.md`.
> Titular liberou somente o achado médio histórico para esta preservação privada (ADR-0017);
> reapresentar o tratamento definitivo da informação na retomada, antes de novos trabalhos.
> Backup Git/WIP inicial Drive confirmado; dados ignorados, banco, modelos e provas
> têm inventário e recibos em `output/pausa/2026-11-16/`. Não supor que estão no Git.
> FreeCAD com geometria inicialmente não visível foi relatado pela titular e não
> investigado/corrigido no fechamento. Sem produto homologado ou autorização do Programa real.
> Resultados finais e SHA exato nos recibos/RELATORIO-FINAL de `output/pausa/2026-11-16/`,
> também no Drive autorizado. Não confundir intenção/etapa em curso com operação aprovada.

> **Continuação mais recente — OAE196:** leia primeiro o novo topo de STATE e
> `docs/interop/FREECAD-OAE-RETORNO.md`. FreeCAD abriu/editou/salvou/reabriu FCStd
> existente; nova OAE196 retornou via STEP/malha/API, com peças selecionáveis e
> propriedades CAD separadas da ficha 4D. Artefatos em
> `output/releases/freecad-oae-retorno-20261114/`; recomendado `detalhada-validada/`.
> GUI CAD não observada (pipe Computer Use indisponível), somente runtime oficial.
> Não sobrescrever destinos; conservar base original e hashes. Sem commits/push.
> Quantidades e CPM de referência intactos. Exportador Blender antigo não aceita
> diretamente a OAE196; detalhes e próximos passos no guia. Resultados finais no STATE.

> **Atualização posterior — FreeCAD (14/11):** leia o novo topo do STATE e
> `docs/interop/FREECAD-PARAMETRICO.md`. Portátil oficial produziu três peças
> paramétricas em FCStd, edição/salvamento/reabertura, STEP reimportado e retorno
> federado; controles de enquadrar/isolar verificados. 116 PASS de regressão +
> 37 PASS de referência; Chrome 227 completo, Edge 39 focados após 218 completos
> no estágio anterior dos controles. Sem commit/push ou instalação global.
> Proteção e pacote desta onda têm sufixo `freecad-parametrico-20261114`; snapshots
> anteriores permanecem preservados. Não citar 2040 como suíte completa desta onda.

> **Retomada Codex V3 (13/11/2026):** trabalho em andamento na branch
> `codex/demo-interop-vnext`, sem commit/push. Leia primeiro o bloco atual no topo
> de `STATE.md`. O beta `main`/`1fa6445` está preservado em bundle e snapshot local
> em `output/protecao/pre-missao-20261113-170327/`. Há um incremento de apresentação
> e federação por revisão, com Chrome 214 PASS e Edge 220 PASS. Duas falhas da
> primeira suíte completa foram corrigidas (57 PASS focados); segunda: **2040 PASS,
> 6 SKIP, exit 0**, 1195,64 s. Snapshot complementar em
> `output/protecao/pos-missao-v3-20261114/`; conferir manifesto e hashes do pacote.
> Correção documental autorizada: e-mail institucional substituído pelo link
> oficial no disco; histórico preservado. Revarredura e adendo no topo do STATE;
> sem autorização de publicação, commit ou instalação. Relatório atual:
> `docs/missao/RELATORIO-CODEX-V3-2026-11-14.md`. Os números abaixo são históricos.

> Para outra pessoa, máquina ou conta assumir o projeto **sem acesso a nenhuma conversa**.
> **Codex CLI:** comece por `AGENTS.md` e `docs/HANDOFF-CODEX.md` (estado verificado em `12219c3`: 1982 testes
> passando no snapshot isolado; e2e 196/196). Este arquivo segue como a referência detalhada.
> Atualizado em 2026-11-13. Base: commit `682c4a0` (snapshot isolado: 1794 passando, 29 pulados, 0 xfail).
> Ver `git status`: o que não foi commitado existe só no disco. Relatório da missão: `docs/missao/RELATORIO-MISSAO-AUTONOMA.md`.

- **Projeto:** `infra-4d-intelligence` (Consultoria Parceira), nascido em 2026-11-12 por `py -3.13 -m eos new`.
- **Contrato canônico:** `registry/projects/infra-4d-intelligence.yaml` no Emmily AI Project OS.
- **Local:** `${AI_WORKSPACE}\work\parceira\infra-4d-intelligence` (resolva com `py -3.13 -m eos resolve`).
- **Remoto:** (repositório privado de origem) (privado). **Nada foi enviado:**
  push só por pedido explícito da titular.
- **Dado bruto:** armazenamento externo de dados brutos (fora do Git), nunca no Git (ADR-0015 da
  plataforma). **Hoje todo dado do sistema é FICTÍCIO** (ADR-0004), com a marca `meta.ficticio: true` (ADR-0005).
- **Versão:** `0.2.0` no `project.yaml`. Tudo o que veio depois está em `CHANGELOG.md` → `[Não lançado]`. Tag só
  com o critério de aceite comprovado.

## Como retomar

1. Ler `docs/STATE.md` (onde parou; o registro da missão autônoma está no topo) e `docs/decisions/`
   (ADR-0001 a 0005; não reabrir sem motivo técnico novo).
2. `git log --oneline` e `git status`.
3. Preparar a máquina e rodar (seção abaixo). Conferir `exit 0` da suíte.
4. O retrato do que existe, módulo a módulo, com rota, teste e limitações, está em `docs/ARQUITETURA.md`. O que
   falta está em `docs/BACKLOG.md` e em `docs/IMPLANTACAO-REAL.md`.

## Como rodar (Windows 11, PowerShell 5.1, Python 3.13)

```powershell
.\bootstrap.ps1                  # 1ª vez: cria o .venv e instala requirements.txt
.\run-beta.ps1                   # API + interface em http://127.0.0.1:8765/   (-Porta 8800)
.\run-beta.ps1 -Regenerar        # regenera SÓ a ferrovia (python -m infra4d.dados_sinteticos) antes de subir
.\tests\run-tests.ps1            # suíte pytest no .venv: 0 = passou, 1 = falhou, 2 = NÃO RODOU (não é verde)
```

- **IFC é opcional:** o módulo `ifc/` precisa do `ifcopenshell` no `.venv`; sem ele, `test_ifc.py` dá SKIP e
  `/api/ifc` fica indisponível (o estado aparece em `/api/saude`). Os testes com arquivos OFICIAIS da
  buildingSMART baixam para `output/ifc/externos` (fora do Git, conferidos por SHA-256) e dão SKIP sem rede ou com
  `INFRA4D_SEM_REDE=1`.
- **Banco SQLite** do histórico: `output/infra4d.sqlite`, ou o caminho de `INFRA4D_BANCO`. Os testes usam um banco
  isolado em tmp.
- **E2E da interface** (Chrome headless, fora do pytest, um processo pesado por vez):
  `.\.venv\Scripts\python.exe tests\e2e\verificar_interface.py`. A última contagem registrada no CHANGELOG é
  **181/181**. Exit 2 = não rodou.
- **Números do roteiro da demo** (`docs/DEMO-PESSOA-A.md`), lidos da API em memória, sem rede e sem gravar
  nada, em cerca de 50 s:
  ```powershell
  cd scripts; ..\.venv\Scripts\python.exe -m infra4d.numeros_demo          # texto
  cd scripts; ..\.venv\Scripts\python.exe -m infra4d.numeros_demo --json   # JSON
  ```
  **Dica de UTF-8:** com a saída redirecionada (`> arquivo`), o stdout do Python no Windows é cp1252 e o `→`
  quebrava com `UnicodeEncodeError`. O script já faz `sys.stdout.reconfigure(encoding="utf-8")` (R14). Mesmo
  assim, no PowerShell 5.1 o `>` grava UTF-16; para um arquivo UTF-8, use `| Out-File -Encoding utf8` ou leia
  com `Get-Content -Encoding UTF8`. `test_numeros_demo.py` e `test_roteiro_demo.py` conferem os números contra o
  sistema.
- **Ambiente:** a máquina tem Python 3.12 e 3.13; o projeto fixa **3.13** (`project.yaml` → `ambiente.python`).
  Escrever arquivos do repositório em **LF** (`.gitattributes`: `* text=auto eol=lf`, `.ps1/.bat/.cmd` em CRLF).

## O que existe (por área; uma linha cada, com a rota)

Todas as rotas aceitam `?obra=ferrovia|rodovia`. As obras são descobertas em
`examples/synthetic/*_ficticia.json`. Os módulos opcionais entram por `registrar_rotas` em `api.py`, que hoje
registra 26 nomes (`docs/ARQUITETURA.md` §3). Um módulo quebrado não derruba a
API.

| Área | O que faz | Rota |
|---|---|---|
| Motor CPM e cenários | CPM próprio (FS/SS/FF/SF, lag ±, calendários, SNET/FNLT, *progress override* ou *retained logic*); cenários linha de base, construtora, independente e simulado | `/api/projeto`, `/api/cenarios/{c}`, `/api/comparacao`, `/api/simulacao` (GET/POST/DELETE) |
| Painel e 4D | Avanço ponderado, estado 4D por data, marcos contratuais, sensibilidade à lógica | `/api/painel`, `/api/estado4d` |
| Previsão probabilística | Monte Carlo v1/v2 com criticidade; incerteza alargada para frente sem medição (desligada por padrão) | `/api/previsao-probabilistica` (`?incerteza_sem_medicao=true`) |
| Earned Schedule | SPI(t), IEAC(t), IECD | `/api/previsao/earned-schedule` |
| Tendência de marcos (MTA) | Término por cenário em datas passadas, sem dado futuro | `/api/tendencia` |
| Backtest e atribuição | Erro da previsão contra a `realidade_simulada`; várias sementes; qual frente explica o erro | `/api/backtest`, `/api/backtest/sementes`, `/api/backtest/atribuicao` |
| Cobertura da previsão | Em que evidência se apoia cada marco; confiança; alerta de frente sem medição | `/api/cobertura` |
| Curva S | Física e financeira por obra e lote | `/api/curva-s` |
| Riscos ao prazo | Registro consolidado de 9 fontes, com evidência reconsultável | `/api/riscos` |
| Recuperação e aceleração | Menor esforço para cumprir o prazo; aceleração por menor custo/dia (custo fictício) | `/api/recuperacao`, `/api/aceleracao` |
| Sensibilidade | Tornado por (lote, serviço) e +equipes | `/api/sensibilidade` |
| Clima | Término com outro regime de chuva | `/api/clima` |
| DCMA 14 pontos | Qualidade do cronograma nosso ou importado | `/api/dcma`, `POST /api/dcma/importado` |
| Recursos | Histograma, nivelamento SGS, conflitos de balanço | `/api/recursos/histograma`, `/nivelamento`, `/conflitos-balanco` |
| Fiscalização (IN 57/DNIT) | Diário e boletim sintéticos, conciliação, produtividade, linha real, validação | `/api/fiscalizacao/diario`, `/boletins`, `/conciliacao`, `/produtividade`, `/linha-real`, `POST /validar` |
| Medições por CSV | Importa e recalcula EM MEMÓRIA; marca de fictício estrita | `POST /api/medicoes/importar` |
| Cronograma de terceiro | MSPDI (entrada e saída), XER (entrada e saída), comparação com o motor | `/api/cronograma/exportar/mspdi`, `/exportar/xer`, `POST /importar`, `POST /comparar` |
| Revisões de cronograma | Comparação forense de duas versões | `/api/revisoes/comparar` (GET/POST) |
| IFC 4.3 (opcional) | Exportação por tipo de obra, `IfcLinearPlacement`, cronograma nativo, vínculo, GLB, requisitos | `/api/ifc/exportar`, `/glb`, `/vinculo`, `/requisitos` (GET/POST), `POST /cronograma`, `POST /vinculos` |
| GIS | GeoJSON RFC 7946 com georreferência FICTÍCIA | `/api/gis/geojson` |
| Referência linear | km ↔ estaca com equações; xy → km | `/api/referencia/km`, `/api/referencia/ponto` |
| Massas e produtividade | Brückner, DMT; produtividade de terraplenagem pela DMT | `/api/massas/diagrama`, `/api/massas/coerencia`, `/api/produtividade/terraplenagem` |
| 5D fictício | Composições, BDI do TCU por obra, reajuste sintético, EVM de custo, mapa IFC | `/api/orcamento/composicoes`, `/resumo`, `/curva-s-financeira`, `/classificacao-ifc` |
| Exportação BI | CSV pt-BR em modelo estrela e ZIP com dicionário | `/api/exportar/tabelas`, `/{tabela}.csv`, `/pacote.zip` |
| Histórico (SQLite) | Cenários salvos, snapshots, evolução, auditoria | `/api/historico/cenarios-salvos`, `/snapshots`, `/evolucao`, `/auditoria` |
| Relatório | HTML imprimível com CSP sem script | `/api/relatorio` |
| Saúde e obras | Módulos ligados e lista de obras | `/api/saude`, `/api/obras` |
| Obrasgov.br | Adaptador do JSON da API pública para o esquema parcial; **sem rota**, sem rede | — (`adaptador_obrasgov.py`) |
| Interface | Abas, 3D/4D com GLB do IFC, Gantt, linha de balanço, tour guiado, selo de simulação | `/` (servida pelo próprio processo) |

## Como verificar um commit

1. **Congelar com os donos** os arquivos que vão entrar. Commit só por pedido explícito da titular ("salva essa
   versão", "commita", `/os:checkpoint`). Nunca `git add .`: `status` → `diff` → varredura de segredos → resumo
   → `add` seletivo.
2. **Verificar o commit ISOLADO, não o disco:**
   ```powershell
   git archive -o <scratchpad>\snap.tar HEAD      # NÃO use 'git archive | tar' no PowerShell: o pipe corrompe o tar
   # extrair em pasta vazia no scratchpad e rodar a suíte lá com o .venv do projeto
   ```
   Foi assim que se pegou o `d8446a3`, inconsistente (12 falhas só no snapshot; corrigido pelo `9577865`, sem
   reescrever histórico). O `e5fa630` deu 1 falha prevista (guarda da r8), corrigida no `682c4a0`, que deu
   1794 passando, 0 xfail.
3. **Nunca duas suítes completas ao mesmo tempo.** Três em paralelo travaram com 0% de CPU. `pytest.ini` tem
   `faulthandler_timeout = 300`. Também um processo pesado por vez (suíte ou e2e/Chrome); a RAM da máquina é curta.
4. **Teste de mutação só em cópia:** import isolado de uma cópia ou monkeypatch em memória (por exemplo, um
   plugin pytest carregado com `-p`), **nunca** editando o arquivo real, nem por segundos. Isso já gerou um
   falso Δ=0 visto pela r17 (STATE, "Incidente de processo").
5. **Saída 2 da suíte = não rodou.** Teste que nunca foi visto falhar não é detector. O critério de aceite vem de
   `project.yaml` → `verificacao.limites` (fixture `limite("nome")`); limite ausente faz o teste falhar.
6. **Revisão adversarial:** defeito confirmado nasce como `xfail(strict=True, reason="DEFEITO: ...")` em
   `tests/test_revisao_adversarial_*.py` (dono: o revisor). Quando corrigido, vira XPASS(strict) e falha até o
   revisor tirar a marca; isso é esperado.
7. Antes de push, release ou handoff: `/os:security`.

## O que está aberto

- **BACKLOG P1–P8** (previsão independente; `docs/BACKLOG.md`), com o estado pelo CHANGELOG `[Não lançado]`:
  - P1 cobertura por marco: **implementado** (`/api/cobertura`). Limite honesto (R12): em 30/03 nenhum sinal
    justo marca "baixa" no L2 da rodovia;
  - P2 analogia pelo recurso compartilhado (usina): aberto;
  - P3 gerador coerente na restrição da usina L2/L3: aberto (muda os números da demo);
  - P4 Monte Carlo com incerteza alargada: **implementado e desligado por padrão**; a 1ª versão antecipava a
    previsão (r19), corrigida e recalibrada (alargamento 0,5, teto 0,6). No M-L2-FIM em 30/03 a realidade ainda
    fica fora da faixa;
  - P5 atribuição automática do erro: **implementado** (`/api/backtest/atribuicao`);
  - P6 sinal antecedente fora dos boletins: aberto;
  - P7 chuva futura na fotografia: **decidido manter e declarar**;
  - P8 `tipo_obra` sem padrão silencioso: **feito** (`scripts/infra4d/obra.py`, `tests/test_obra_tipo.py`);
    obra sem tipo → 422 nas rotas que dependem dele; a interface mostra "tipo não declarado";
  - P10 (teto do Monte Carlo pesado): **feito** (`ORCAMENTO_MC` em `api.py`);
  - P9 (gabarito lido do disco ou via `/api/backtest`): aberto.
- **R13-2 — issue para o IfcOpenShell NÃO ENVIADA.** O rascunho está em
  `docs/research/R13-anexo-issue-ifcopenshell.md`, sem dado do projeto. Defeito em `is_day_in_work_time`
  (0.9.0): a exceção de calendário torna não úteis todos os dias anteriores ao término dela. Enviar é ação externa
  e **só a titular decide**.
- Calibração CAL1–CAL7 (R09), Fases 2 e 3, e IR1–IR14 para implantação real: `docs/BACKLOG.md` e
  `docs/IMPLANTACAO-REAL.md`. Dado real exige um ADR que substitua o ADR-0004 (IR1).
- Revisões adversariais: a contagem de xfail muda a cada rodada. Conferir com
  `pytest --collect-only -q -m xfail tests/test_revisao_adversarial_*.py`.
- P9: o gabarito pode ser lido do JSON em disco ou via `/api/backtest` sem que as guardas peguem: regra de
  revisão de código (BACKLOG).

## Riscos

| ID | Risco | Situação |
|---|---|---|
| RK1 | Motor divergir de P6/Project | aberto; compatibilidade **não** alegada; MSPDI/XER só com ida e volta própria (IR5 pede arquivo real) |
| RK2 | Dado fictício confundido com real | mitigado: faixa na UI, `meta.aviso`, `meta.ficticio` booleano (ADR-0005) |
| RK3 | Copyleft por dependência | mitigado (R04): núcleo MIT/BSD/Apache; IfcOpenShell LGPL opcional, sem modificação |
| RK4 | Geometria sintética passar por BIM real | mitigado: Apresentação separa implementado e simulado |
| RK5 | Premissas de engenharia sem fonte | aberto: R03/R06 [OG]; R09 calibrou parte e listou CAL1–CAL7 |
| RK6 | Arquivo de exemplo sem licença clara no Git | baixar no teste, SHA-256, nunca versionar |
| RK7 | Modelo de cliente no validador online da buildingSMART | só arquivos públicos online |
| — | Realidade sintética com fatores estacionários favorece a previsão independente (R12) | backtest bom aqui é condição necessária, não prova |
| — | Travamento de suítes em paralelo (IR14) | mitigado (faulthandler, uma suíte por vez); causa raiz não achada |

## Decisões tomadas hoje (2026-11-13)

- **ADR-0005 estrito:** a marca de fictício é só booleana (`meta.ficticio is True`) ou, no CSV de medições, só
  `#ficticio=true|false`, uma vez. Grafias alternativas são recusadas, e obra real exige `false` explícito
  (achado alto da r14). A sensibilidade à chuva é só pela marca booleana `sensivel_chuva`.
- **BDI pela fórmula do TCU (Acórdão 2622/2013), declarado por obra:** ferrovia 23,48%, rodovia 22,22%, dentro da
  faixa q1 19,60% – q3 24,23% para "construção de rodovias e ferrovias" (R11). Nunca é deduzido do texto do
  código. Tipo sem declaração é erro, e o 25% fica só como `bdi=` explícito. Reajuste por índice sintético com
  anualidade pela data inteira. BDI inválido (NaN, ±inf, negativo, bool, texto) é recusado.
- **Gabarito isolado:** `meta.fatores_desempenho_simulados` e a `realidade_simulada` só podem ser alcançados pelo
  gerador e pelas ferramentas de avaliação (`backtest.py`, `atribuicao_erro.py`) e por quem as expõe
  (`rotas_backtest.py`, `rotas_atribuicao.py`, `relatorio.py`). A proteção tem duas camadas (r19):
  - a guarda estática `tests/test_gabarito_isolado.py`, que acusa chave inteira ou em pedaços, recálculo do
    futuro, fatores fixos do gerador, varredura do `meta` e import de gerador ou avaliação, e foi vista falhar
    com 8 trapaças;
  - o teste contrafactual em `tests/test_revisao_adversarial_r19.py`: troca o gabarito e exige previsões
    idênticas.
- **Simulação do usuário não entra nas análises de referência:** o orçamento (EVM) usa linha de base e executado
  medido. As rotas que usam o cenário independente de propósito declaram `simulacao_do_usuario` (clima,
  aceleração, recuperação, riscos, ES, atribuição), e a interface mostra o selo (`aviso_simulacao.py`,
  `test_simulacao_do_usuario.py`).
- **Mutação só em cópia** (regra de processo; ver "Como verificar um commit").
- **R13-2 não publicado:** decisão da titular.
- **Normalização de fim de linha:** diagnóstico feito; não há blob com CRLF no HEAD, então não há commit de
  normalização.

## Recuperar em outra máquina

Na plataforma: `py -3.13 -m eos restore infra-4d-intelligence --para <diretório vazio>`. Depois, `.\bootstrap.ps1`
e `.\tests\run-tests.ps1`. Instalar o `ifcopenshell` no `.venv` só se for usar o IFC.
