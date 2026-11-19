# IMPLANTAÇÃO REAL — do beta fictício à operação com dado real

> Data: 2026-11-12. Ponto de partida: o que está em `docs/ARQUITETURA.md`, um beta local com **dados fictícios**,
> sem autenticação e ouvindo só em `127.0.0.1`.
> Regra deste documento: cada fase tem um **critério de saída testável** e nenhuma fase alega o que ainda não foi
> executado e observado (`docs/VERIFICATION-POLICY.md` do Project OS: verificado = executado e observado).
> Nada aqui contrata serviço, instala componente no sistema nem envia dado a terceiro. Cada um desses passos é uma
> decisão da titular (§9).

## 0. Onde estamos (linha de base desta trilha)

| Tema | Hoje | Evidência |
|---|---|---|
| Dados | Só fictícios. `meta.ficticio: true` trava todo gerador derivado | ADR-0004, ADR-0005, `test_revisao_adversarial_r6.py` |
| Manifesto | `dados_sensiveis: false`, `criticidade: baixa`, `revisao_independente: nenhuma` | `project.yaml` |
| Segurança | CSP estrito, `nosniff`, `no-referrer`, HTML do relatório escapado; uploads limitados (cronograma 20 MB, IFC 100 MB, 1000 fotos por registro); XML com DOCTYPE recusado | `test_api_seguranca.py`, `importadores/rotas.py`, `ifc/rotas.py`, `fiscalizacao.py` |
| Identidade | **Nenhuma.** A auditoria grava "quem" como texto informado | `persistencia.py` |
| Interoperabilidade | MSPDI e XER testados só com ida e volta própria e fixtures escritas à mão; IFC só com o próprio exportador | `test_importadores_*.py`, `test_ifc.py`, R07 |
| Números de engenharia | Premissas [OG] (sem fonte) em R03 e R06 | `docs/research/R03`, `R06` |
| Defeitos abertos | xfail das revisões r7 (frontend) e r8 (ES, MC v2, persistência) | `tests/test_revisao_adversarial_r7.py`, `_r8.py` |

## Fase 1 — Governança para dado real (antes de qualquer arquivo real entrar)

**Objetivo:** o projeto pode *receber* dado real sem vazá-lo, sem confundi-lo com fictício e sem que ele entre no Git.

1. **Novo ADR substituindo o ADR-0004**, com:
   - escopo do dado (que obra, que contrato, quem forneceu e sob que autorização);
   - onde ele mora: armazenamento externo de dados brutos (fora do Git), conforme o ADR-0001, nunca
     no Git;
   - retenção e descarte.
2. **Manifesto:** `dados_sensiveis: true` e `revisao_independente: "qa+security"` (o próprio `project.yaml` diz que
   dado sensível força pelo menos isso). A criticidade deve ser revista com a titular.
3. **Carga fora do repositório:**
   - a API passa a aceitar obras de uma pasta configurável fora do Git; hoje descobre só `examples/synthetic/*_ficticia.json`;
   - a obra real **não** leva `meta.ficticio`, então os geradores derivados recusam por construção (ADR-0005).
4. **LGPD** (premissas a validar com o jurídico; isto não é parecer). Os dados pessoais previsíveis são:
   - nome de fiscal, responsável técnico e encarregado no diário;
   - **fotos** com pessoas e placas de veículo;
   - **geolocalização** das fotos;
   - assinatura e login dos usuários.

   Medidas:
   - inventário desses campos;
   - base legal a definir com o jurídico (candidatas: execução de contrato e cumprimento de obrigação legal — o
     art. 117 §1º da Lei 14.133/2021 manda o fiscal registrar as ocorrências; R05 §2);
   - minimização: o sistema guarda **referência e hash** da foto (o esquema de `fiscalizacao.py` já é assim), e o
     arquivo fica no repositório de origem;
   - prazo de retenção e direito de acesso e correção;
   - registro do tratamento.
5. **Varredura** `/os:security` limpa (working tree, histórico, `.gitignore`).

**Critério de saída (testável):**
- [ ] ADR novo aceito, e o ADR-0004 marcado como substituído.
- [ ] `project.yaml` com `dados_sensiveis: true` e `qa+security`; `/os:doctor` sem divergência.
- [ ] Teste novo falha se algum `.json`, `.xer`, `.xml`, `.ifc` ou imagem fora de `examples/` (sintético) ou de
  `tests/` entrar no índice do Git.
- [ ] Teste novo: uma obra carregada da pasta externa, sem `meta.ficticio`, recebe 409 em `/api/fiscalizacao/*` e
  422 em `/api/orcamento/resumo`. Os testes dessa trava já existem para dicionários em memória; falta ligá-los à
  pasta externa.
- [ ] `/os:security` sem achado.

## Fase 2 — Validar o motor contra Primavera P6 e MS Project REAIS

**Objetivo:** só nesta fase pode-se escrever "compatível com P6/Project", e só na extensão testada (ADR-0003).
Cronograma real costuma ter pouco dado pessoal, por isso é a primeira entrada real de menor risco.

1. Coletar de **pelo menos 2 obras**: arquivos MSPDI e XER exportados pelos programas reais, junto com as **datas
   calculadas por eles** (relatório ou colunas Early/Late Start/Finish e folga total) na mesma data de status.
2. Teste de ida e volta, em três etapas:
   - importar;
   - recalcular no motor;
   - comparar atividade por atividade com o P6/Project (início, término, folga total, crítico).
3. Declarar no `project.yaml` → `verificacao.limites` a tolerância (ex.: `divergencia_termino_dias`). Toda
   divergência acima dela tem que ser **explicada** por uma limitação já listada em `LIMITACOES_MSPDI` ou
   `LIMITACOES_XER` (por exemplo: calendário com horas, *must finish*, LOE, lag em %), ou então vira defeito.
4. Os arquivos ficam no Drive. O teste lê de uma pasta configurada e **pula** (com motivo) quando a pasta não existe.
   Exit 2 não pode ser confundido com verde.

**Critério de saída:**
- [ ] Para cada arquivo real: 100% das atividades importadas ou recusadas com motivo; término do projeto dentro da
  tolerância do manifesto; lista de divergências por atividade com causa.
- [ ] Política de progresso confirmada por arquivo (*retained logic* × *progress override*). O motor tem as duas;
  o MSPDI não carrega essa informação (limitação declarada).
- [ ] A frase de compatibilidade no README e na interface só aparece depois disso, citando versões e recursos
  testados.

## Fase 3 — Calibração dos números de engenharia

**Objetivo:** trocar premissas [OG] por fontes nos pontos em que elas ainda influenciam o resultado.

Com dado real, a produtividade efetiva vem dos **boletins da própria obra** e a planejada vem do **cronograma da
construtora**. As faixas de R03/R06 ficam só como **alerta de plausibilidade** (ex.: produtividade medida 5× acima
do teto da faixa).

1. Para cada serviço: faixa com fonte. Candidatas:
   - composição SICRO ("produção da equipe"), lida do arquivo que o usuário baixou;
   - especificações DNIT (R04 §3);
   - histórico de obras da própria empresa.
2. Coerência física, que já existe para terraplenagem (`massas.py`, que aponta os ~23% da ferrovia).

**Critério de saída:**
- [ ] Toda premissa usada como **alerta** tem fonte com URL ou documento, ou continua marcada [OG] e o alerta diz
  isso na tela.
- [ ] Teste: um boletim fora da faixa gera aviso e nunca altera o cálculo.

## Fase 4 — Ingestão de medições reais (boletim e diário)

**Objetivo:** o cenário independente passa a usar medições reais auditáveis.

1. **SIAC sem API pública conhecida** (R05 §2). A integração é **por arquivo**: planilha ou CSV da ficha de medição
   e dos Resumos A, B e C que a fiscalização já produz. O importador é novo e passa pelas mesmas regras de
   `fiscalizacao.validar`: data AAAA-MM-DD, km no trecho e no sentido, chuva ≤ 24 h, `aprovado` exige memória de
   cálculo, transições de estado.
2. Só boletim com estado `aprovado` (ou `conferido_fiscal`, configurável) alimenta a produtividade efetiva. A regra
   precisa ser declarada e testada: hoje o Monte Carlo e os cenários **não filtram por estado**.
3. Conciliação diário × boletim (já existe). Produção sem boletim conta como divergência (corrigido na r6).
4. Coleta em campo, opcional: ODK Central (Apache-2.0) com XLSForm via pyxform (BSD-2), exportando JSON/OData e
   anexos. Licenças GPL/AGPL (QField, servidor do KoboToolbox) só como **serviço externo**, nunca embutidas (R05 §2).

**Critério de saída:**
- [ ] Importador com teste de cada regra de recusa, usando arquivo de exemplo **anonimizado** no Drive.
- [ ] Teste: boletim `lancado` não altera a produtividade efetiva quando a regra exige `aprovado`.
- [ ] Conciliação de um mês real com `ok = true`, ou com cada divergência explicada.

## Fase 5 — Segurança e multiusuário

**Objetivo:** mais de uma pessoa usa o sistema com identidade, papel e trilha.

1. **Autenticação.** Hoje não existe. Opções sem custo de licença: login local com senha forte e hash (biblioteca
   padrão ou dependência permissiva), ou o provedor de identidade que a empresa já tiver. A escolha é da titular.
2. **Autorização por papel.** A matriz mínima abaixo deve ser testada rota a rota:

   | Ação | Construtora | Fiscal | Gestor |
   |---|---|---|---|
   | Lançar diário/boletim (`lancado`) | sim | sim | não |
   | Conferir (`conferido_fiscal`) e aprovar | não | sim | não |
   | Importar cronograma da construtora | sim | sim | não |
   | Simular e salvar cenário | não | sim | sim |
   | Ver painel, relatório e previsões | só a própria obra | sim | sim |
   | Ler auditoria | não | sim | sim |

3. **Trilha de auditoria:**
   - a tabela já existe (`persistencia.py`); o campo "quem" passa a vir da sessão, nunca do corpo da requisição;
   - registros só podem ser acrescentados, nunca editados (append-only);
   - cópia de segurança periódica.
4. **Estado de simulação:** hoje é **um por processo e por obra**, compartilhado entre quem acessa. Em multiusuário
   ele precisa ser por sessão, ou só existir como cenário salvo.
5. **Transporte e borda:**
   - HTTPS;
   - limite de corpo e de taxa no proxy reverso. O limite de bytes do `/validar` tem de ficar na borda, porque o
     FastAPI lê o corpo antes da rota (registrado na r6);
   - CSP mantido.
6. **Fechar** os xfail abertos das revisões r7 (XSS e escape no frontend) e r8.

**Critério de saída:**
- [ ] Teste por rota × papel (permitido → 2xx; proibido → 403; sem sessão → 401).
- [ ] Teste: "quem" da auditoria = usuário da sessão, mesmo que o corpo diga outro.
- [ ] Zero xfail aberto nas revisões; nova rodada adversarial focada em autenticação, sem defeito aberto.
- [ ] Revisão independente `qa+security` aprovada (ADR-0007 da plataforma).

## Fase 6 — Hospedagem (decisão, sem contratar nada agora)

| Opção | Como | Prós | Contras | Pré-requisito |
|---|---|---|---|---|
| **Local** (hoje) | `run-beta.ps1`, `127.0.0.1` | Zero custo, zero exposição | Um usuário, uma máquina, sem cópia de segurança automática | — |
| **Servidor da empresa** | Serviço uvicorn atrás de proxy reverso com HTTPS, na rede interna | Dado dentro da empresa; sem custo de nuvem | Exige servidor, administração e cópias; instalar serviço precisa de autorização | Fase 5 concluída |
| **Nuvem** | Contêiner ou VM com proxy e HTTPS | Acesso remoto, escalável | Custo recorrente; dado pessoal fora da empresa (LGPD: operador e contrato); exige contratação | Fase 5 + decisão de custo + avaliação LGPD do provedor |

Persistência: o SQLite serve para um servidor com poucos usuários. PostGIS/PostgreSQL só se houver concorrência
real ou necessidade de consulta espacial no servidor (R01, R05 §6). Hoje não há.

**Critério de saída:** a opção escolhida tem um runbook em `docs/runbooks/` (subir, parar, cópia, restauração), e
a **restauração foi executada e observada** uma vez.

## Fase 7 — Integrações com arquivos reais

| Integração | Situação | Próximo passo verificável |
|---|---|---|
| MS Project (MSPDI) | Importador e exportador prontos, só biblioteca padrão | Fase 2 |
| Primavera P6 (XER) | Importador pronto (PROJECT, CALENDAR, TASK, TASKPRED) | Fase 2. PMXML e `.mpp` só via MPXJ (LGPL, JVM) se aparecer a necessidade (R02/R04) |
| IFC 4.3 | Exportador, importador de vínculo e GLB testados com o próprio IFC | Rodar `Infra-Rail.ifc` e `Infra-Road.ifc` (CC BY 4.0) e os modelos de alinhamento da buildingSMART, **baixados no teste e fora do Git** (R05 §1). Depois, o IFC do cliente |
| Validação IFC | `ifcopenshell.validate` local (0 erros no IFC exportado) | Modelo de cliente **nunca** no validador online; se for preciso o laudo da buildingSMART, usar o serviço local via Docker (código MIT) (R05 §1) |
| SIAC | Sem API pública conhecida | Importador de arquivo (Fase 4) |
| Coleta de campo | Esquema pronto (fiscalização) | ODK Central (Fase 4), se a titular decidir |
| Custos (SICRO/SINAPI) | O 5D é **fictício** de propósito | Parecer sobre a CC BY-ND 3.0 do SICRO; termos do SINAPI não verificados. Ler só o arquivo que o usuário baixou, sem redistribuir base nem tabela derivada |

## 8. Custos e licenças

| Componente | Licença (verificada em R04/R05/R07) | Custo hoje | Pode exigir licença/custo quando |
|---|---|---|---|
| Python, FastAPI, uvicorn, three.js, SQLite | permissivas (MIT/BSD/PSF/domínio público) | zero | — |
| IfcOpenShell (opcional) | LGPL-3.0-or-later, sem modificação | zero | Se o código dela for modificado (aí as modificações têm de ser publicadas) |
| ODK Central / pyxform | Apache-2.0 / BSD-2 | zero | Hospedagem do servidor ODK |
| QField, QGIS, Bonsai | GPL | zero (bancada) | Nunca embutir no produto |
| Validador buildingSMART | MIT (código); serviço online exige conta | zero | — |
| MS Project, Primavera P6, Revit/Civil 3D | proprietárias | **não usadas** | A validação da Fase 2 precisa de **arquivos** exportados por quem tem licença; o projeto não precisa comprar. Licença estudantil não pode ser usada para fim comercial (BACKLOG #15) |
| SICRO | portal sob CC BY-ND 3.0 | zero | Redistribuição ou base derivada: parecer jurídico |
| SINAPI | termos **não verificados** | — | Antes de qualquer importador |
| Hospedagem em servidor ou nuvem | — | zero (local) | Fase 6 |
| Certificado HTTPS | — | zero (local) | Servidor/nuvem: pode ser gratuito (autoridade automatizada) ou corporativo |

## 9. Decisões que dependem da titular

1. **Qual obra real** e com que autorização entra primeiro, e se o contrato muda o ownership. O ADR-0004 diz para
   rever o ownership "só se entrar contrato, cliente ou dado de terceiro".
2. **Aprovar o ADR que substitui o ADR-0004** e a mudança do manifesto para `dados_sensiveis: true` /
   `qa+security`, com revisão da criticidade.
3. **Base legal e retenção LGPD**: consultar o jurídico? Quem é controlador e quem é operador?
4. **Fotos:** guardar só referência e hash (recomendado), ou guardar o arquivo?
5. **Ordem das fases 2 a 4**: recomendação de começar pela Fase 2 (cronograma real, pouco dado pessoal).
6. **Tolerância** de divergência contra P6/Project, a declarar no manifesto.
7. **Regra de estado** para alimentar a produtividade: só `aprovado`, ou também `conferido_fiscal`?
8. **Autenticação:** login próprio ou provedor da empresa.
9. **Matriz de papéis** (§Fase 5): confirmar ou ajustar.
10. **Hospedagem:** local, servidor da empresa ou nuvem. Qualquer custo recorrente é decisão dela.
11. **Coleta em campo:** adotar ODK Central agora, depois ou nunca.
12. **5D com preço real:** pedir parecer sobre o SICRO (CC BY-ND) e verificar os termos do SINAPI, ou manter o 5D
    fictício.
13. **Push para o remoto e publicação:** hoje nada foi enviado; exige pedido explícito.
