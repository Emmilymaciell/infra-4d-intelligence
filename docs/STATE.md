# STATE — INFRA 4D INTELLIGENCE

## PAUSADO — AGUARDANDO REVISÃO DETALHADA DA TITULAR · 16/11/2026

**PRÓXIMA SESSÃO: NÃO INICIAR DESENVOLVIMENTO AUTOMATICAMENTE. PRIMEIRO RECEBER E CONSOLIDAR A REVISÃO DA TITULAR.** Esta ordem suspende a execução automática da missão V3. Não é arquivamento permanente.

Snapshot formal: **INFRA 4D INTELLIGENCE — SNAPSHOT DE PAUSA PARA REVISÃO DA TITULAR**, em `docs/SNAPSHOT-PAUSA-2026-11-16.md` (interno, não publicado). Base preservada: branch `codex/demo-interop-vnext`, HEAD inicial `1fa6445e3ab62ac933347c6d26957cae4dfb43ea` mais WIP inventariado. O commit de preservação está no histórico privado; resultado e SHA final nos recibos de encerramento (não publicados). Não é uma versão profissional homologada. Todo dado é fictício; do Programa real continua proibido nesta fase.

- Missão atual somente de preservação/encerramento: nenhuma funcionalidade, correção FreeCAD, melhoria visual ou refatoração. Documentos e artefatos de recuperação são as únicas adições desta sessão.
- Scanner inicial: 0 ALTA / 1 MEDIA histórica, exit 1, contato institucional em `docs/research/R10-obrasgov.md`, blob `2f6fc389`. A titular **autorizou posteriormente retirar apenas esse bloqueio** para esta preservação privada, mantendo o tratamento definitivo pendente para a retomada. Exceção exata registrada no `project.yaml` e ADR-0017; achado continua visível, sem reclassificação ou supressão. Checkpoint/push sujeitos aos testes e à nova varredura; nenhuma autorização para outros achados, reescrever histórico, force push ou publicação. Remoto privado oficial confirmado; sem nova tag.
- Primeiro backup oficial Drive confirmado: manifesto `20261116T092303Z`, Git bundle + WIP, exit 0. Artefatos ignorados não entram nesse backup; preservação complementar, inventário, hashes, SQLite consistente e recibos em `output/pausa/2026-11-16/`. Destino autorizado armazenamento externo (fora do Git). Resultado final deve ser lido nos recibos; não presumir conclusão de operação pendente.
- `eos mirror` não tem `data[] cloud-mirror` neste contrato e recusou a operação; registry/plataforma não alterados. Banco `output/infra4d.sqlite` não declarado no registry, preservado separadamente pelo snapshot consistente.
- Pendência nova **relatada pela titular, sem investigação nesta missão**: FreeCAD abriu `modelo-revisado.FCStd`, mas a geometria não apareceu inicialmente. Rever visibilidade, hierarquia, câmera, formas e parâmetros na próxima fase. Provas de kernel anteriores não provam GUI.
- Próxima ação única: receber e consolidar a revisão detalhada da titular (incluindo visual, dashboards, requisitos Pessoa A, integrações e validação nativa), sem implementar até nova instrução. Itens de revisão completos no snapshot; pendências antigas continuam abertas.
- Subagentes anteriores estão concluídos; nenhum agente foi acionado para desenvolver. Não fechar automaticamente a interface Codex, apagar arquivos ou worktrees. Os blocos abaixo são históricos e não autorizam continuidade durante a pausa.
- Preservação comprovada de resultados: **722 arquivos, 365 conteúdos únicos**, ZIP 68.009.352 bytes, SHA-256 `5c2b7bac723fbdf3e133a8083c898f041467252fcfcf85663f8491a88b959edc`. Enviado ao Drive e baixado/restaurado em pasta nova, todos os hashes iguais; SQLite restaurado com integrity_check ok. Inclui 11 FCStd, 7 STEP, 4 BLEND, 4 QGZ, 4 GPKG, 11 IFC, 5 GLB, 4 MP4, 423 PNG e demais resultados. Não é prova de GUI.
- Segundo backup oficial `20261116T093053Z`: bundle + WIP da pausa baixados novamente, SHA-256 conferidos, bundle verify passou, sem pendências do backup. Dois blobs sem referência apontados pelo fsck também preservados separadamente, sem descarte. Código funcional (215 arquivos comparados com snapshot anterior) intacto. Ownership 7 PASS/1 WARN/0 FAIL, declaração Three.js pendente na plataforma, não alterada.
- Resultados finais de checkpoint, commit isolado, push, backup e certificação são evidências geradas após o congelamento documental: `output/pausa/2026-11-16/RELATORIO-FINAL.md`, recibos JSON e logs, copiados ao Drive autorizado. Não interpretar passo em execução como PASS; o relatório final registra cada resultado real. Esta referência evita commits documentais recursivos apenas para citar o próprio SHA.

## Continuação atual — OAE196 e retorno do FCStd existente (14/11/2026)

- Branch `codex/demo-interop-vnext`, HEAD `1fa6445`; sem staging/commit/tag/push. WIP herdado e snapshots anteriores preservados. Dados exclusivamente fictícios; nenhum acesso ao Programa, serviço pago ou alteração de outro projeto.
- Guia atual: `docs/interop/FREECAD-OAE-RETORNO.md`. O pacote anterior tinha **dois FCStd e três componentes**. Novos arquivos em `output/releases/freecad-oae-retorno-20261114/`, separados dos anteriores.
- FreeCAD oficial 1.1.4 abriu FCStd existente, editou parâmetros, salvou outro arquivo, fechou/reabriu, exportou/reimportou STEP. Fragmento antigo: tabuleiro 1250→1500 mm, volume 120→144 m³, planejamento continua 3 un.
- Nova OAE paramétrica: **196 Part::Box**, 196 IDs nativos em seis atividades; 108 IDs da publicação preservados. Trecho reto de 36 m, três vãos de 12 m, não toda a atividade de 400 m. Fundações, pilares, apoios, vigas, tabuleiro, guarda-corpos, lastro, dormentes e trilhos simplificados. Sem dimensionamento estrutural/IFC/Bonsai.
- Guarda-corpo `OAE3_SUE_CORRIMAO_V01_E`: Height 100→150 mm, 0,116→0,174 m³. Arquivo recomendado `detalhada-validada/modelo-revisado.FCStd`; STEP com 196 sólidos válidos, volumes e caixas conferidos. Fonte preservada por hash. FCStd permanece fonte paramétrica; STEP não preserva a árvore.
- API retorna derivados geométricos separados do planejamento; não multiplica volume pela quantidade contratual. Sem alteração de executado, cronograma/CPM, previsão ou dataset de referência. Comparativo de volume é antes/depois da edição do job; retorno já editado sem comparativo não inventa delta.
- Web: malha individual por componente, materiais nativos no isolamento, seleção e ficha CAD lateral; bbox agregado por atividade. Ambiente ilustrativo permite terreno/água/árvores sem duplicar engenharia procedural. Modo Técnico desliga o ambiente.
- Crítica independente identificou manifesto autodeclarado e delta de volume ambíguo. Correções: mapa confiável regenerado da base/descritores, ID por nome verificado; comparativo anterior omitido sem edição do job. Grupo FreeCAD com Shape agregada excluído para não duplicar peças; regressão própria. Novos módulos têm testes.
- **GUI FreeCAD não observada:** Computer Use sem pipe nativo, três tentativas incluindo recuperação. Evidência `gui-status.json`; nenhuma automação de interface alternativa. Prova é runtime oficial, não teste manual. Navegadores usam headless/CDP com renderização por software.
- Verificação já concluída nesta onda: 224 PASS Python focados (contrato/API/CAD/OAE); 26 PASS + 6 SKIP em segurança frontend/r23/gabarito/contrato; Chrome 43 PASS focados. Os resultados finais adicionais são registrados no bloco de fechamento desta onda. Não repetir 2040 como suíte completa atual; sem commit isolado.
- Próximo fluxo avaliado por agente independente: Blender com os mesmos componentes, como derivado visual, menor risco que ProjectLibre. O exportador Blender antigo recria faixas e **não deve receber diretamente OAE196**. Necessário fatiar malha por peça e revisar agrupamento GLB/contrato; não homologado para esta nova OAE. Prioridade pendente: GUI FreeCAD e revisão de engenheiro.

Os blocos abaixo são históricos; não substituem o estado acima.

### Fechamento desta onda

- Bateria final **289 PASS, 6 SKIP**, exit 0, 50,14 s (`python-final-02.log`): contrato CAD, OAE, retorno, federação/API, frontend/r23/gabarito, smoke/OpenAPI/vertical slice/roteiro/números. Não é a suíte pytest completa; nenhuma validação de commit isolado. Os seis skips continuam explícitos, não contam como PASS.
- Chrome **43 PASS focados**; Edge **231 PASS completos**, ambos sem falhas e com arquivos reais. Escopo e capturas nos respectivos JSONs. Imagens do modelo nativo inspecionadas; materiais, seleção e ambiente legíveis. Não é prova GPU/GUI FreeCAD.
- API: três retornos reais (fragmento antigo, OAE196 com edição e OAE196 já editada sem novo job de edição). 108 vínculos, derivados conferidos, referência/simulação intactas, acervo vazio após reinício. Caso sem edição tem volume atual e **não** tem delta inventado.
- Dois detectores de adulteração falharam ao remover guardas **só na memória de subprocesso**; fonte original permaneceu com mesmo hash. Guardas reais: 15 PASS. Evidência `detector-isolado.log`; as duas falhas esperadas pertencem apenas à prova de detector, não à bateria final.
- Segurança: scanner exit 1, **0 ALTA / 1 MEDIA histórica**, 288 arquivos examinados, cobertura parcial explicitada no relatório (limites/blobs não textuais). Sem exceção, sanitização de histórico ou publicação autorizada. Ownership read-only: 7 PASS / 1 WARN / 0 FAIL; Three.js continua sem declaração no registry da plataforma. Aviso Starlette/httpx e aviso Git CRLF continuam sem alteração global.
- `eos check` read-only: **L1 / AT_RISK**, remoto/backup/recovery pendentes. Não apagar sessão/clone ou trocar de máquina inferindo proteção completa. Snapshot local não substitui backup/certificação canônicos. Nenhum comando mutável da plataforma foi executado.
- Pacote local desta onda: `output/releases/infra4d-oae196-20261114.zip`, com base original, FCStd/STEP/retornos, guia e evidências; manifesto SHA-256. Proteção local das fontes/WIP/Git em `output/protecao/freecad-oae-retorno-verificado-20261114/`. Conferir os manifestos antes de mover. A pasta `freecad-oae-retorno-20261114` em proteção é tentativa parcial, sem manifesto final: a checagem encontrou os placeholders versionados output/logs README, foi ajustada sem excluir ou sobrescrever a tentativa. Pacotes anteriores preservados; sem redistribuir FreeCAD/Blender.

## Continuação de 14/11/2026 — FreeCAD paramétrico e inspeção de revisões

Este é o estado mais recente; o bloco V3 abaixo é o snapshot anterior.

- Missão continuada por “CONTINUA MAIS COISA”. Branch `codex/demo-interop-vnext`,
  HEAD `1fa6445`, sem staging/commit/tag/push. Motor CPM, cenários e datasets sem
  alterações; somente dados fictícios, nenhum acesso ao Programa ou serviço pago.
- FreeCAD 1.1.4 **portátil**, permitido como ambiente local da missão §16:
  pacote oficial extraído em `output/tools/`, SHA-256 e assinatura Valid conferidos,
  configuração/dados do aplicativo dentro de `output/tools/freecad-1.1.4/profile/`.
  Não foi usado instalador Windows nem alterado PATH/associações globais.
- FCStd r0/r1 reais com três Part::Box (Bloco, Pilar, Tabuleiro), três IDs nativos
  verificados após fechar/reabrir. Height do tabuleiro 1000 → 1250 mm; volume
  geométrico 96 → 120 m³; quantidade de planejamento 3 un e executada preservadas.
  STEP exportado/reimportado: três sólidos válidos, volume e bbox conferidos.
- `interop_freecad.py` executado no runtime Python próprio do CAD; servidor segue
  no `.venv` 3.13 sem carregar DLLs FreeCAD. API reconhece `source_app=FreeCAD` e
  a malha retornada em metros, com nova publicação isolada, prazo igual e referência
  idêntica. São 108 IDs da publicação JSON, não 108 peças no FCStd.
- Interface: **Enquadrar revisão** e **Só revisão**, com restauração da referência
  e seleção que ignora objetos ocultos. Captura inicial mostrou oclusão pela base;
  inspeção visual confirmou as três peças legíveis após foco/isolamento.
- Auditoria r23: revisão sem mudanças após isolamento escondia a referência.
  Reproduzida com Three.js real em cópia isolada: falha assertiva observada,
  XFAIL(strict), correção → XPASS(strict), marca removida. Regressão também passou
  por upload real no navegador. Selecionar a peça isolada preserva enquadramento.
- Verificação desta onda: **116 PASS, 6 SKIP**, exit 0 (31,43 s), regressão de
  contrato/API/CAD/r7/r23; **37 PASS**, exit 0 (53,65 s), smoke/API/vertical slice/
  roteiro/números da demo. JS e Python com sintaxe conferida; diff sem erros.
- Navegadores: **Chrome 227 PASS**, interface completa incluindo o novo fluxo;
  **Edge 218 PASS** completo antes dos controles de foco/isolamento, seguido de
  **39 PASS** focados na versão final (escopo registrado no JSON). Ambos headless
  por software, sem GUI CAD manual ou GPU real. Suíte pytest completa de 2040
  PASS pertence ao incremento anterior; não foi repetida nesta onda nem verificado
  commit isolado. Se houver pedido de checkpoint, cumprir novamente a política.
- Artefatos: `output/releases/freecad-parametrico-20261114/nativo-verificado/`,
  provas, JSONs e capturas nas pastas adjacentes. Guia canônico:
  `docs/interop/FREECAD-PARAMETRICO.md`. Pacote local de revisão:
  `output/releases/freecad-parametrico-pacote-20261114.zip`; proteção das fontes:
  `output/protecao/freecad-parametrico-20261114/` (conferir manifestos/hashes).
- Segurança: contato institucional permanece somente no histórico; nenhuma
  reescrita/exceção/publicação autorizada. Varredura da onda registrada em
  `output/releases/freecad-parametrico-20261114/security-report-freecad.md`.
  Não inferir aprovação global ou certificação de recuperação; EOS anterior L1.
- Limites: fragmento ilustrativo de três peças; não é OAE executiva, IFC/Bonsai,
  importador geral de FCStd/STEP ou sincronização bidirecional. STEP não promete
  preservar árvore paramétrica/IDs customizados. Metadados do upload são declaração
  da fonte; reabertura oficial exige evidência própria. Limites superiores de
  coordenadas/transformações continuam pendência conhecida de endurecimento.
- Próxima frente: ensaiar ProjectLibre ZIP/JAR + JRE/JDK portátil, sem instalação
  global, confirmando o escritor/leitor POD verdadeiro antes de alegar suporte.
  Pesquisa confirmou CPAL 1.0, registrada na matriz; runtime/roundtrip ainda não
  executados. Bonsai e validação profissional/manual continuam separados. P2/P3,
  dados do Programa, commit e backup externo não foram autorizados por esta continuação.

## Snapshot anterior — incremento demonstrável V3, 13–14/11/2026

Este bloco prevalece sobre os snapshots históricos abaixo. Missão:
`INFRA4D_CODEX_PROMPT_MASTER_V3.md` (interno, não publicado). Somente dados fictícios; nenhum acesso ao Programa,
instalação global, commit, tag, push ou envio externo foi feito nesta sessão.

- Branch de evolução: `codex/demo-interop-vnext`, criada sobre `1fa6445`; `main`
  preservada. Git operacional fora do sandbox. A árvore inicial já tinha STATE,
  HANDOFF-CODEX, SESSIONS e a missão mestre sem commit; esse WIP foi preservado.
- Proteção local: `output/protecao/pre-missao-20261113-170327/`: bundle completo
  verificado (`git bundle verify`), `head.tar`, patch binário, documentos WIP,
  evidências da demo anterior e hashes. Isso não substitui backup externo.
- Antes de editar: smoke/API/vertical slice/roteiro → **35 PASS**, 47,81 s.
- API experimental de federação: exportar base, conferir revisão e publicar cópia
  isolada em memória, sem alterar referência ou simulação. API/OpenAPI → **25 PASS**
  antes da revisão r22; resultados posteriores devem ser registrados ao concluir.
- Runtimes oficiais executados: QGIS 3.40.14 (.qgz/.gpkg, editar/salvar/reabrir) e
  Blender 5.2.3 LTS (.blend/GLB, escala/salvar/reabrir). Retorno QGIS: 108 IDs,
  L3-S04-TER 350.000 → 385.000 m³, cópia CPM 09/09 → 21/09/2027. Retorno Blender:
  escala ilustrativa z 1 → 1,25; quantidade e término de referência preservados.
- Evidências nativas: `output/releases/demo-ferrovia-vNext/`. Execução por API
  oficial/batch é distinta de GUI observada. Controle desktop falhou por serviço
  nativo indisponível; não alegar validação manual, Bonsai ou GPU real.
- Visual: variante apresentação, ponte, terreno, dormentes instanciados, reunião,
  câmera local, técnico 1:1, baixo consumo e fallback 2D implementados e
  verificados no E2E.
  Primeira rodada Chrome expôs recusa de baseline após normalização JS de 0.0→0;
  corrigida no contrato por comparação estrutural sem aceitar bool como número.
- Auditoria independente r22 observou quatro XFAIL (meta não objeto e unidades
  divergentes) e depois XPASS das correções. Marcas retiradas; regressão focada
  final com interop/federação/planilha/r22/OpenAPI: **65 PASS**, exit 0, 46,24 s.
- Chrome 157.0.8103.52: **214 PASS, 0 FAIL**, exit 0, incluindo retorno QGIS;
  `output/demo/vNext-2026-11-13/chrome-prioridade4d/resultado-e2e.json`.
- Edge 157.0.4341.46: **220 PASS, 0 FAIL**, exit 0, incluindo malha e GLB reais
  Blender, espessura 0,5 m e 108 IDs; cabeçalho em 1366 px e modo visual entre
  obras. Evidência: `output/demo/vNext-2026-11-14/edge-validado/resultado-e2e.json`.
  Ambos headless/CDP, software: não comprovam GPU real nem GUI nativa manual.
- Vídeo conferido: `output/releases/demo-ferrovia-vNext/10-demo/demo-ferrovia-vnext-capturas-35s.mp4`,
  35 s, 350 quadros, 1440×1000; montagem de capturas reais com rótulos de fictício
  e configuração futura. Não é gravação contínua. Capturas e JSONs copiados a
  `09-evidencias/`. Primeira tentativa de vídeo com dimensões variáveis preservada.
- Primeira suíte completa oficial: **2 FAIL, 2037 PASS, 6 SKIP**, exit 1,
  1285,97 s. Detectou fallback literal ferroviário na nova rota e quatro strings
  internas novas sem revisão XSS registrada. Fallback corrigido para tipo declarado;
  destinos `userData`/hover `textContent` revisados. Auditor aprovou por leitura.
  Regressão das correções: **57 PASS, 6 SKIP**, exit 0, 41,88 s.
- Segunda suíte completa **2040 PASS, 6 SKIP, 1 aviso, exit 0**, 1195,64 s,
  executada sozinha, sem navegadores/FFmpeg:
  `output/verificacao/missao-v3-2026-11-14/suite-completa-pos-correcao.log`;
  sessão 25335 concluída. O aviso é depreciação Starlette/httpx; os seis skips
  exigem navegador e foram cobertos pelo E2E separado. Não é verificação de
  commit isolado: este WIP não foi commitado.
- Segurança: varredura anterior **0 ALTA, 1 MEDIA**, exit 1. Em 14/11 a titular
  respondeu SIM à substituição do contato de `docs/research/R10-obrasgov.md:51`
  pelo link oficial. Substituição executada; HTTP 200 e ausência de e-mails nesse
  documento conferidos. Histórico e snapshots anteriores preservados, sem exceção
  ou reescrita Git. Resultado da revarredura em
  `output/verificacao/missao-v3-2026-11-14/security-report-pos-contato.md`;
  remover do disco atual não remove o contato dos commits antigos. Sem aprovação
  global/publicação; instalações, commit e envio externo não foram autorizados.
- `eos check`: L1/AT_RISK, operação OK; remoto/backup/recuperação FAIL. Não apagar
  a sessão ou pasta nem presumir portabilidade. `ownership-check`: WARN Three.js
  herdado, registry não alterado. Snapshots locais não são backup externo canônico.
- Matrizes de requisitos, contratos, licenças, retorno real e auditoria UX estão
  gravadas. Relatório: `docs/missao/RELATORIO-CODEX-V3-2026-11-14.md` (interno, não publicado).
  Pacote local para revisão: `output/releases/demo-ferrovia-vNext/`;
  hashes em `00-manifesto/SHA256SUMS-final.txt`, snapshot complementar em
  `output/protecao/pos-missao-v3-20261114/` (conferir manifesto desse diretório).
  Planejador gratuito, FreeCAD e Bonsai continuam sem instalação autorizada.
- Correção documental autorizada tem proteção incremental em
  `output/protecao/contato-autorizado-20261114/`; somar ao snapshot V3 anterior.
  O pacote V3 já gerado é um snapshot anterior: o adendo atual fica em
  `output/verificacao/missao-v3-2026-11-14/ADENDO-CONTATO-AUTORIZADO.md`.
- Próxima unidade: ensaio manual no notebook/GPU e decisões pendentes de instalação,
  histórico/segurança, checkpoint/backup externo. Conferir hashes/snapshot antes
  de migrar. Missão completa segue aberta; não iniciar P2/P3 nem acessar o Programa.

### Registro histórico do beta e da missão Claude

> A memória do projeto. Quem chega — pessoa, máquina ou Claude novo — lê isto primeiro.
> Atualizar **antes** de cada checkpoint, nunca depois.

- **Última atualização:** 2026-11-13 (auditoria completa: `docs/AUDITORIA-2026-11-13.md`)
- **Versão:** 0.2.0 no manifesto (tag `v0.2.0`); tudo depois está em `CHANGELOG.md` → `[Não lançado]` (19 commits)
- **Branch:** `main` (única; sem worktrees extras)
- **Remoto:** (repositório privado de origem). **Nada enviado:** `origin/main`
  parado no commit de nascimento; `main` está 20 commits à frente. Push só por pedido da titular.
- **Modo de execução atual:** multiagente (orquestrador + 8 agentes por especialidade, ver "Agentes")
- **Testes (reexecutados na auditoria de 2026-11-13):** `.\tests\run-tests.ps1` → **1918 passando, 6 pulados, 0
  falhas, exit 0** (16min30, com rede; os 6 pulados são casos da r7 que exigem navegador e são cobertos pelo e2e);
  e2e da interface → **189 PASS, 0 FAIL, exit 0** (3min43).

---

## Missão autônoma em andamento (registro vivo)

- **Início:** 2026-11-12 18:59:37 −03:00. Meta: ~5 h efetivas, se a sessão permitir. Autorizada pela titular, com
  commits de checkpoint permitidos. Tag só com critério de aceite comprovado; sem push.
- **Recurso:** ~1,7 GB de RAM livre. Só um processo pesado por vez (suíte completa ou Chrome e2e).
- **Onda 1 (iniciada 19:00):**

  | Agente | Frente | Arquivos |
  |---|---|---|
  | rodovia | caso rodoviário fictício | `dados_sinteticos_rodovia.py` |
  | cronogramas | MSPDI e XER | `scripts/infra4d/importadores/` |
  | bim-ifc | IFC 4.3 com IfcOpenShell | `scripts/infra4d/ifc/` |
  | recursos | histograma, nivelamento SGS e conflitos de balanço | `recursos.py` |
  | pesquisa-r05 | pesquisa | `docs/research/R05` |

  O orquestrador cuida da API multi-obra e da integração das rotas.
- **Andamento (≈19:15):**
  - Concluído e verificado:
    - rodovia fictícia (BR-FIC 999, 137 atividades), servida pela API multi-obra;
    - importadores MSPDI e XER (ida e volta exata; falta ligar por obra);
    - recursos (histograma, nivelamento SGS e conflitos de balanço);
    - pesquisa R05;
    - frontend da onda 1 (seletor de obra, relatório, 3D genérico, marcos e sensibilidade): e2e 53/53;
    - motor: FNLT e lógica retida, com a rodada 4 da revisão (5 defeitos, todos corrigidos).
  - Suíte: 295 passando.
  - Em andamento:
    - rodovia: código comum dos geradores e referência linear com equação de estacas;
    - recursos: Earned Schedule, Monte Carlo v2 e cruzamento analítico;
    - cronogramas: ligação por obra e rota de comparação;
    - pesquisa-r05: módulo de fiscalização;
    - bim-ifc: IFC 4.3;
    - frontend: aba Recursos.
  - Checkpoint Git adiado até um momento sem edições concorrentes.
- **Andamento (≈19:50):** cinco commits de checkpoint, cada um verificado em isolamento (git archive + suíte):

  | Commit | Conteúdo | Snapshot |
  |---|---|---|
  | `8f1e9cc` + `d70bd52` | API multi-obra, rodovia, importadores, FNLT e retida | — |
  | `652328b` | fiscalização e estacas | — |
  | `187e548` | recursos, ES, MC v2, histórico e abas da UI | — |
  | `e4b9be5` | massas, 5D sintético, CSP, correções r5/r6 | 563 passando |

  - Revisão cruzada: 8 rodadas. A r7 (XSS do frontend) está sendo corrigida pelo frontend; a r8 (persistência, ES e MC)
    está em andamento.
  - Incidente: suítes paralelas travaram (0% de CPU). Mitigação: `pytest.ini` com faulthandler e proibição de suítes
    completas simultâneas. O py-spy foi negado pelo ambiente e NÃO foi contornado.
- **Interrupção (19:55–20:10):** todos os agentes atingiram o limite de uso de 5 h da conta e pararam no meio
  das tarefas. A missão foi retomada às 20:11 (56 min efetivos até ali, 18:59→19:55; um registro anterior dizia 72 por
  engano). Ao retomar, a suíte deu 837 passando e
  42 falhando, quase tudo XPASS de defeitos corrigidos antes da parada. Cada agente foi retomado com o ponto exato.
- **Andamento (≈20:40):**
  - Commits pós-retomada:

    | Commit | Conteúdo | Snapshot |
    |---|---|---|
    | `57118f9` | IFC rodovia/GLB, recuperação, sensibilidade, exportação BI | 667 passando |
    | `247af11` | massas conservando volume, orçamento, produtividade pela DMT | 704 passando |
    | `d8446a3` | criticidade no MC e fechamento das r7–r9 | **inconsistente** |

    O `d8446a3` levou os testes estáticos da r7, que leem `web/`, sem o `web/` corrigido: 12 falham no snapshot
    isolado. O complemento é commitar `web/` quando o frontend congelar. NÃO reescrever o histórico.
  - Prontos no disco e ainda sem commit:
    - DCMA 14 pontos (limites conferidos na doc da Deltek);
    - correção do truncamento do histórico (r10);
    - cenários climáticos;
    - roteiro da demo reescrito, com `numeros_demo.py`;
    - R09 (calibração) e pesquisa;
    - `web/` com as correções de XSS da r7 (e2e 102/102), a aba Análises e o modelo IFC no 3D.
  - Revisão cruzada: 12 rodadas concluídas, mais de 70 defeitos achados no total; a r13 (clima) está em andamento.
  - Suíte no disco: ~940 passando.
- **Andamento (≈21:10, ~1h55 efetiva):**
  - Commits: `fe9a548` (medições CSV, Obrasgov, painel 5x), `9577865` (web/ da r7, Análises, IFC, tour; snapshot
    1045 passando, 29 pulados, 17 xfail, exit 0; fecha a inconsistência do `d8446a3`), e o checkpoint de riscos, GIS, IFC etapa 4 e r11–r13.
  - Revisão r14 (medições e Obrasgov): 6 defeitos, 1 alto (obra real aceitava arquivo que se declara fictício em
    grafia não reconhecida). Em correção por recursos e pesquisa-verificada.
  - Em andamento: XER de saída (cronogramas), tendência de marcos (rodovia), plano do cronograma nativo no IFC
    (bim-ifc), r15 sobre riscos e IFC etapa 4 (revisor), interface (frontend).
- **Segunda interrupção (21:14–01:10):** limite de uso de 5 h de novo, logo depois do commit `f73d199`.
  Efetivo até ali: ~2 h (56 + 63 min). Retomada em 2026-11-13 01:11, com cada agente no ponto exato. A primeira
  verificação do `f73d199` não rodou (o `git archive | tar` pelo pipe do PowerShell corrompe o tar); refeita com
  `git archive -o arquivo.tar`: **1168 passando, 29 pulados, exit 0** (snapshot isolado, 5 min).
- **Andamento (≈01:35 de 13/11, ~2h25 efetivas):** commit `fdf6a26` (backtest, curva S, aceleração, r14/r15,
  painel com dados incompletos, interface 153/153) verificado em snapshot: **1348 passando, 29 pulados, 12 xfail
  (r15 aberta), exit 0**. No disco, ainda sem commit: XER/OpenAPI de rotas, comparação de revisões agrupada,
  auditoria de caches, BDI por obra (TCU) e reajuste, recuperação corrigida (ferrovia cumpre só com mudança de
  método), cobertura da previsão, IFC etapa 5 (em andamento).
- **Andamento (≈01:50 de 13/11, ~2h40 efetivas):** checkpoint grande com: comparação de revisões, cobertura da
  previsão, BDI por obra e reajuste, recuperação corrigida, IFC etapa 5 (cronograma nativo por cenário) e r15 do
  IFC, relatório técnico com 5 análises novas, OpenAPI completo (PENDENTES vazia), `simulacao_do_usuario` + selo
  na interface (e2e 169/169), restrição na fotografia da MTA sem dado futuro, ES e várias sementes no backtest,
  r15/r16 fechadas. Abertos: r17 (18 xfail: orçamento 4, cobertura 2, IFC 1), na fila dos donos.
- **Snapshot do `e5fa630`:** 1617 passando, 29 pulados, 18 xfail (r17), **1 falha**: a guarda estática da r8
  (`test_nenhum_outro_teste_usa_as_rotas_de_historico_sem_banco_proprio`) exigia uma lista fixa de arquivos e
  dois testes novos citam `/api/historico`. Não havia risco real (a fixture autouse isola o banco); a guarda foi
  trocada pela verificação da proteção real e entra no checkpoint seguinte. Prevista antes do resultado.
- **Incidente de processo (13/11):** vários agentes faziam teste de mutação editando o arquivo REAL por segundos
  e restaurando; a r17 chegou a ver Δ=0 falso na cobertura. Nenhum arquivo mutado entrou em commit (os snapshots
  de `f73d199`, `fdf6a26` e `e5fa630` teriam falhado). Regra nova, adotada por todos: mutação só em cópia carregada
  por import isolado ou monkeypatch em memória.
- **Andamento (≈02:16 de 13/11, ~3h05 efetivas):** checkpoint com r17–r19 fechadas (0 xfail em todas as
  revisões), guarda da r8 corrigida, atribuição do erro (P5), Monte Carlo P4 corrigido e recalibrado, roteiro da demo
  com 104 números testados, contrato interface × API, orçamento sem tipo de obra padrão, interface 181/181.
- **Snapshot do `682c4a0`: 1794 passando, 29 pulados, 0 xfail, exit 0** (10 min). Nenhuma revisão adversarial
  tem defeito aberto.
- **Terceira interrupção (02:17–06:10):** limite de uso de 5 h, logo depois do commit `682c4a0`. Efetivo até ali:
  ~3h05 (56 + 63 + 66 min). Retomada às 06:11.
- **Andamento (≈06:35 de 13/11, ~3h25 efetivas):** r20 (varredura de robustez de todas as rotas) fechada com 2
  correções no `api.py`; interface com P4, "Por que errou?" e "indeterminada" (e2e 189/189); HANDOFF reescrito;
  relatório da missão em `docs/missao/RELATORIO-MISSAO-AUTONOMA.md` (interno, não publicado), revisado criticamente. Todas as revisões
  (motor, r2–r20) sem xfail aberto.
- **Snapshot do `670a040`: 1844 passando, 29 pulados, 0 xfail, exit 0** (11 min).
- **Snapshot do `4fc3e36` (P8 + r21): 1894 passando, 29 pulados, 0 xfail, exit 0.**
- **Encerramento (≈07:25 de 13/11):** ~4h19 efetivas. Último commit: P10 (teto do Monte Carlo) e documentos
  finais. Relatório: `docs/missao/RELATORIO-MISSAO-AUTONOMA.md` (interno, não publicado).
- **Snapshot do `41cdb42` (último código da missão): 1895 passando, 29 pulados, 0 xfail, exit 0** (10 min).
- **Auditoria (13/11 10:04–10:40):** relatório em `docs/AUDITORIA-2026-11-13.md`. Suíte reexecutada: 1918 passando,
  6 pulados, exit 0; e2e 189/189. Missão × implementado: 7/10 entregáveis operacionais (3 parciais documentais).
  Achados: nenhum link do Reddit (bloqueado, não contornado); `INFRA4D_CLAUDE_KICKOFF.md` não existe no repositório;
  faltam filtro de segmento/km e período, teste do play, ADRs das decisões da missão, banco espacial e AMV.
- **Depois da auditoria (13/11 10:40–11:05), no disco e SEM commit (aguardando autorização da titular):**
  - ADR-0011 a 0015 (decisões da missão);
  - P9: gabarito fora do dataset (`examples/synthetic/gabarito/`, acessor `sintetico_comum.gabarito`); números
    idênticos ao HEAD;
  - interface: filtros por segmento, km e período e teste do play (e2e 196/196);
  - não conformidade como entidade (`nao_conformidade.py`, `/api/fiscalizacao/nao-conformidades`) e como fonte do
    registro de riscos.
  - Verificação: suíte oficial 1930 passando, 6 pulados, exit 0 (iniciada 10:44); os testes das mudanças posteriores
    (NC, riscos, OpenAPI, contrato, fiscalização, r15, gabarito) rodados depois: 198 passando.
- **Congelamento para demo e transferência ao Codex (13/11, autorizado pela titular):**
  - commit `12219c3` com os 32+ arquivos pós-auditoria; snapshot isolado: **1982 passando, 7 pulados, exit 0**;
  - e2e: **196 PASS, 0 FAIL**, com 27 capturas reais em `output/demo/2026-11-13/capturas/` e um vídeo de 44 s
    montado delas (`output/demo/2026-11-13/demo-5min-capturas.mp4`); `output/` fica fora do Git. Destino das
    evidências pelo OS: armazenamento externo (fora do Git);
  - beta conferido no ar pelo `.\run-beta.ps1` (10 rotas principais com 200);
  - documentos novos: `docs/DEMO-5-MINUTOS.md`, `docs/HANDOFF-CODEX.md` (interno, não publicado) e `AGENTS.md` atualizado.
  - **Versão congelada para a demo:** P2/P3 NÃO implementados (mudariam os números).
- **Retomada se a sessão cair:** ver a seção "Próximo passo" no fim deste arquivo e o `git log`. O que não foi
  commitado está no disco; rode `git status`.

## Em uma frase

Plataforma BIM 4D de monitoramento físico, análise de caminho crítico e previsão independente de conclusão para
obras ferroviárias e rodoviárias. Hoje é um **beta local com dados FICTÍCIOS** de uma ferrovia.

## Como rodar

```powershell
.\bootstrap.ps1            # 1ª vez: .venv + requirements.txt
.\run-beta.ps1             # http://127.0.0.1:8765/   (-Regenerar refaz a base sintética)
.\tests\run-tests.ps1      # suíte (pytest no .venv)
```

Roteiro da demonstração: `docs/DEMO-PESSOA-A.md`.

## Concluído (executado e observado)

- **Motor CPM próprio** (`scripts/infra4d/motor.py` e `calendario.py`, ADR-0003):
  - relações FS/SS/FF/SF com lag ±;
  - calendários por atividade, inclusive mistos;
  - feriados e chuva;
  - marcos e restrição SNET;
  - data de status (*progress override* coerente na ida e na volta);
  - folga total e folga livre;
  - crítico = folga ≤ 0 ou caminho mais longo; cadeia determinante;
  - validação: ciclos, datas reais incoerentes, horizonte.
- **Revisão adversarial em 3 rodadas** por agente independente: **42 defeitos** confirmados, todos corrigidos e
  transformados em regressão (`tests/test_revisao_adversarial_motor.py`, `_r2.py`, `_r3.py`). Inclui propriedades
  em milhares de redes aleatórias com calendários mistos, feriados, progresso e marcos, além de testes de
  robustez e concorrência da API.
- **Cenários** (`cenarios.py`): linha de base, construtora (produtividade planejada), independente (produtividade
  medida, com a fonte declarada) e simulado (ajustes do usuário). Cada atividade traz a memória de cálculo.
  A explicação da mudança de término usa o efeito contrafactual isolado, inclusive o paradoxo da atividade reversa.
- **Vertical slice ponta a ponta** (`tests/test_vertical_slice.py`, pela API HTTP): produtividade → duração →
  rede → término → painel → estado 4D, com o tempo de recálculo checado contra `verificacao.limites` do manifesto.
- **Previsão probabilística** (`montecarlo.py`): P10/P50/P80/P90 reprodutíveis e centrados no determinístico.
- **Base sintética** (`dados_sinteticos.py` → `examples/synthetic/ferrovia_ficticia.json`): 60 km, 3 lotes,
  12 segmentos, 113 atividades, 264 relações, 463 boletins, semente 20261112, premissas `P-2026.11-a`.
  Um teste garante que o JSON versionado é idêntico à saída do gerador.
- **API FastAPI** (`api.py`): projeto, cenários, comparação, simulação (POST/DELETE), estado 4D, painel e previsão
  probabilística. OpenAPI em `/docs`.
- **Interface web** (`web/`, three.js vendorizado), testada no Chrome headless pelo agente de frontend e conferida
  em captura própria do orquestrador:
  - abas: Apresentação, Painel, Modelo 3D/4D, Gantt e Simulação;
  - filtros e seleção bidirecional entre 3D e Gantt;
  - timeline 4D e explicação "por que o término mudou".
- **Interface, rodada 2:**
  - vista 3D inicial na frente crítica (km 55), com atalhos L1, L2, L3 e frente crítica;
  - aba **Linha de balanço** (tempo × km);
  - selo "caminho mais longo".
- **Verificação e2e da interface:** `.\.venv\Scripts\python.exe tests\e2e\verificar_interface.py` (Chrome) dá
  **41 PASS, 0 FAIL, exit 0 (2026-11-12)**. O orquestrador executou e conferiu as capturas. O detector foi visto
  falhar (exit 1) e "não rodou" sai com exit 2. O script fica fora do pytest porque depende do Chrome.
- **Pesquisa** R01–R04 (`docs/research/`). O R04 tem licenças e versões **verificadas na web** e prevalece sobre
  R01–R03.

### Números da demo (base sintética, data de status 09/11/2026)

| Cenário | Término previsto |
|---|---|
| Linha de base | 27/05/2027 |
| Construtora (fictícia) | 23/07/2027 |
| Independente | 09/09/2027 (+48 dias corridos vs construtora) |
| Monte Carlo (200 iterações) | P50 10/09/2027 · P80 13/09/2027 |

Avanço real: 71,7% (LB previa 80,9%). Caminho crítico: terraplenagem L3-S03 e L3-S04, que produzem cerca de 78% do planejado.

## Parcial

- **Interface:** testada só no Chrome headless com SwiftShader (Edge, Firefox e GPU real não). O *play* da timeline e
  o "Enquadrar tudo" não têm checagem automática. Em 1280 px, a barra do 3D quebra em duas linhas.
- **Riscos conhecidos sem teste (rodada 3):**
  - o alerta "CRÍTICA e produz X%" pode apontar o sentido errado numa atividade **reversa**, em que produzir menos
    antecipa o término. No dataset, L3-S04-DOR escapa por pouco (índice de 0,85);
  - a propriedade "folga exata" com instantes ainda não está garantida em todas as topologias.
- **Monte Carlo:** faixa estreita de propósito (sem correlação entre serviços, risco discreto ou chuva estocástica).
  Também não filtra por lote.

## Pendências (ordenadas pelo que mais desbloqueia)

1. **Push para o remoto:** não foi feito. Exige pedido explícito.
2. Backlog técnico em `docs/BACKLOG.md`: importadores MSPDI/XER, persistência, IFC 4.3 e o alerta da atividade
   reversa no painel.

Discovery fechado (ADR-0004):
- critério de pronto: o vertical slice;
- dados: só sintéticos;
- cálculo determinístico;
- contratante: ownership inalterado, por decisão da titular;
- missão: `docs/missao/INFRA4D_PROMPT_EXECUCAO_COMPLETO.md` (interno, não publicado).

## Agentes (missão de 12–13/11)

| Agente | Papel | Arquivos de que é dono |
|---|---|---|
| orquestrador | API, motor, cenários, painel, relatório, integração, commits | `api.py`, `motor.py`, `cenarios.py`, `painel.py`, `docs/` |
| rodovia | 2ª obra e análises lineares | geradores, `gis.py`, `tendencia.py`, `curva_s.py`, `backtest.py` |
| cronogramas | interoperabilidade de cronograma | `importadores/`, `dcma.py`, `exportacao.py`, `comparar_revisoes.py`, `atribuicao_erro.py`, `obra.py`, `relatorio.py` |
| bim-ifc | IFC 4.3 | `ifc/` |
| recursos | recursos e previsão | `recursos.py`, `montecarlo.py`, `recuperacao.py`, `aceleracao.py`, `clima.py`, `riscos_prazo.py`, `importar_medicoes.py` |
| frontend | interface | `web/`, `tests/e2e/` |
| revisor-cpm | revisão adversarial (r4–r21 na missão) | `tests/test_revisao_adversarial_*.py` |
| pesquisa-r05 | pesquisa e 5D | `orcamento.py`, R05/R11/R13 |
| pesquisa-verificada | pesquisa com fonte aberta | `cobertura.py`, `adaptador_obrasgov.py`, R04/R12/R14 |

Regras de processo vigentes: congelar com o dono antes do commit; verificar o commit isolado (`git archive -o` +
suíte); nunca duas suítes completas em paralelo; mutação só em cópia ou monkeypatch.

## Riscos

| ID | Risco | Situação | Mitigação |
|---|---|---|---|
| RK1 | Motor divergir de P6/Project | aberto | compatibilidade **não** alegada; divergências conhecidas: *progress override* (P6 usa *retained logic*), só SNET, dia inteiro |
| RK2 | Dado fictício confundido com real | mitigado | faixa permanente na UI, `meta.aviso`, origem em cada boletim |
| RK3 | Copyleft por dependência | mitigado | R04: núcleo só MIT/BSD/Apache; IfcOpenShell LGPL na fase 2 sem modificação |
| RK4 | Geometria sintética passar por BIM real | mitigado | aba Apresentação separa o que é implementado do que é simulado |
| RK5 | Números de engenharia sem fonte | aberto | R03 marcado [OG]; o R04 achou só fontes parciais |

## Decisões recentes

- ADR-0002 — Arquitetura do beta local-first (Python + web estática, sem dependência comercial)
- ADR-0003 — Motor CPM próprio e independente
- ADR-0004 — Discovery: só dados sintéticos, cálculo determinístico, critério de pronto
- ADR-0005 — Marca de fictício só booleana (`meta.ficticio is True`); aplicada também ao CSV de medições (estrita)
- ADR-0011 — BDI pela fórmula do TCU por obra e reajuste com anualidade
- ADR-0012 — Gabarito sintético isolado da previsão (P9 em aberto)
- ADR-0013 — Simulação do usuário fora das análises de referência
- ADR-0014 — `tipo_obra` sem padrão silencioso
- ADR-0015 — Commit verificado em snapshot isolado e mutação só em cópia
- Numeração: 0006–0010 ficam reservados para não confundir com os ADR-0006/0007 do Project OS citados no
  `project.yaml` e no `CLAUDE.md`.

## Próximo passo

**Encerramento da sessão Claude (13/11, `/session-close`):** `main` em `1fa6445`, 22 commits **não enviados** ao
GitHub; `eos check` diz "Posso apagar esta sessão? SIM". Histórico da sessão: `docs/sessions/SESSIONS.md` (interno, não publicado). Quem
retomar (Claude ou Codex) começa por `AGENTS.md`/`CLAUDE.md` → este arquivo → `docs/HANDOFF-CODEX.md` (interno, não publicado).

**Próxima unidade executável (uma só):** com a autorização da titular, publicar e proteger o que já está pronto, nesta
ordem:
1. `git push origin main`;
2. `py -3.13 -m eos backup infra-4d-intelligence`;
3. copiar `output/demo/2026-11-13/` para o armazenamento externo (fora do Git).

**Critério de conclusão:** `eos check` com `remote` e `backup` em PASS, e a pasta de evidências no Drive conferida
contra `output/demo/2026-11-13/SHA256SUMS.txt`.

Depois disso, o desenvolvimento segue pela lista abaixo.

A missão autônoma terminou (relatório: `docs/missao/RELATORIO-MISSAO-AUTONOMA.md` (interno, não publicado); retomada: `docs/HANDOFF.md`).
Decisões que dependem da titular: (1) teste manual no Bonsai (R13 §4); (2) enviar ou não a issue do IfcOpenShell
(`docs/research/R13-anexo-issue-ifcopenshell.md`); (3) tag de versão — exige declarar o critério de aceite desta
fase no `project.yaml`; (4) push para o GitHub.

Técnico, em ordem (lacunas da auditoria de 2026-11-13, todas seguras e sem dado real):
1. ~~ADRs das decisões da missão~~ — feito (ADR-0011 a 0015, 13/11).
2. ~~Interface: filtro por segmento/km e período (§7.1) e teste do play (§7.3)~~ — feito (13/11, e2e 196/196).
3. ~~P9 (gabarito em arquivo separado do dataset)~~ — feito (13/11).
3b. ~~Não conformidade como entidade (§3.5)~~ — feito (13/11).
4. P2/P3 (analogia pela usina e coerência do gerador) — mudam os números da demo; o `test_roteiro_demo.py` acusa.
5. Capturas de tela da demo como material de apoio (fora do Git, por regra do `.gitignore`, ou decisão da titular).

## Último checkpoint

- **2026-11-13 — `12219c3` + documentação de transferência:** versão congelada para a demonstração do fim de semana
  e para o Codex assumir (`docs/HANDOFF-CODEX.md` (interno, não publicado)). Snapshot isolado 1982 passando; e2e 196/196. Nada enviado ao
  GitHub; sem tag nova.

- **2026-11-13 — `eea379d`:** fim da missão autônoma (19 commits sobre a `v0.2.0`), auditado em 13/11: suíte 1918
  passando e e2e 189/189.

- **2026-11-12 — v0.2.0:** beta local com o vertical slice verificado: 143/143 testes e e2e da interface com 41/41.
