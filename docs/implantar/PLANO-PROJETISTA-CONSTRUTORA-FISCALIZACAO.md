# Plano de recebimento — projetista, construtora e fiscalização

Data: 13/11/2026. **Proposta de protocolo técnico**, derivada da missão mestre e do beta fictício. Não representa acordo contratual, homologação de software, aprovação de engenheiro ou autorização para tratar dado real.

O escopo prioritário é BIM 4D. Orçamento 5D é opcional e não impede o aceite de um pacote 4D.

## Papéis e fontes de verdade

- **Projetista:** entrega e mantém o modelo nativo editável, os arquivos abertos publicados, identificadores, classificação, geometria, unidades, quantitativos e revisões.
- **Construtora/consórcio:** entrega cronograma executivo, rede lógica, calendários, recursos, produtividades, atualização de campo e justificativas das revisões. Sua previsão é uma trilha identificada, distinta da previsão independente.
- **Fiscalização:** fornece ou confere medições e evidências, registra impedimentos/não conformidades e aprova os estados de medição definidos pelo contrato.
- **Equipe BIM 4D:** valida o pacote, reconcilia IDs e revisões, liga elementos/serviços às atividades, calcula a previsão independente e emite relatório com premissas e limitações.
- **Titular/coordenação:** decide aceites, finalidade de uso, autorizações e divulgação; designa quem aprova engenharia e tratamento de dados.

O arquivo nativo é a fonte autorizada da geometria. O sistema é a fonte das suas análises independentes, comentários e vínculos aprovados. Edição geométrica deve gerar revisão no aplicativo de origem. Nenhuma publicação de revisão está implicitamente aprovada porque um arquivo pôde ser aberto.

## Pacotes mínimos

| Pacote / fornecedor | Conteúdo exigido | Conferência na entrada |
|---|---|---|
| Modelo / projetista | Nativo legítimo e editável; IFC quando aplicável; identificação da obra/modelo/revisão/app/versão; unidades; CRS e transformação; datum vertical ou ausência declarada; eixo e km/estaca; IDs; disciplina; serviço; quantidades e método; parâmetros e limitações | Abrir no app correspondente; conferir unidades/escala; validar classes e propriedades; comparar IDs; registrar objetos novos, alterados e removidos; preservar fonte |
| Planejamento / construtora | Nativo do planejador; XML/XER conforme capacidade comprovada; data de status; linha de base; IDs; WBS; durações; FS/SS/FF/SF e lag/calendário; restrições; marcos; progresso; recursos; produtividades e hipóteses | Importar sem inventar rede; reportar campos/entidades recusados; comparar datas e folgas quando referência externa existir; identificar política de progresso e divergências |
| Medições / construtora e fiscalização | Atividade/serviço/trecho; quantidade/unidade; período; equipes·dia; data de execução; origem e revisão; evidência; estado de conferência/aprovação; correções e motivo | Validar datas, unidade, trecho e referência; conciliar acumulado e saldo; recusar duplicidade ambígua; não usar medição não elegível sem regra explícita |
| Impedimentos / fiscalização | Identificação, atividade/trecho, período, responsável, estado, evidência, decisão e revisão | Separar fato, hipótese e risco; vincular a evidência e registrar quando deixa de restringir |
| Publicação 4D / equipe BIM 4D | Modelos abertos aprovados, tabela de vínculos, resultados dos cenários, relatório de validação, diferenças, manifestos e hashes | Garantir mesma revisão nas telas/relatórios; conservar versão anterior; demonstrar seleção cruzada e explicação da previsão |

Um PDF sem predecessoras pode servir como documento de referência, mas não como rede CPM oficial. Não inventar relações para preencher a ausência. Classificar como **rede não fornecida**, solicitar o arquivo estruturado e manter qualquer rede de estudo separada e fictícia.

## Manifesto e IDs

Cada pacote deverá declarar `model_id`, `source_app`, `source_version`, `revision`, `checksum`, `created_from`, `origin`, `classification`, unidades e data de status quando aplicável. Por elemento/vínculo: ID estável, disciplina, código do serviço, km inicial/final, quantidade/unidade, `schedule_task_id` e última validação.

Quando presente e preservado, usar `GlobalId` IFC como identificador do elemento. Em outros formatos, preservar a chave nativa e a identidade estável do modelo. **Revisão é atributo da versão, não motivo para atribuir outro ID ao mesmo elemento.** Se o app regenerar IDs, exigir mapa de correspondência revisável; não fazer correspondência apenas pela posição sem evidenciar ambiguidade.

Quantidades geométricas, quantidades de serviço/contratuais, executadas e ilustrativas devem ser campos distintos com método/fonte. Um render ou malha de apresentação não é base automática para medição.

## Cadência proposta

| Evento | Entrega / regra proposta |
|---|---|
| Recebimento inicial | Modelo, cronograma, mapa de IDs e boletim inicial da mesma data de corte; validação antes da primeira publicação |
| Atualização ordinária | Pacote semanal de avanço e impedimentos com data de status explícita; periodicidade final a aprovar com responsáveis |
| Alteração geométrica/lógica relevante | Nova revisão identificada, diferença e justificativa; analisar impacto antes de substituir a versão publicada |
| Fechamento de medição | Quantidades elegíveis conferidas/aprovadas segundo regra contratual ainda a definir; conciliação e trilha de correções |
| Reunião gerencial | Congelar a fotografia utilizada, indicar revisões e data de status; relatório e demo leem o mesmo pacote |

## Fluxo de aceite e tratamento de conflitos

1. **Receber em área segregada:** fonte somente leitura, hash, manifesto, classificação e permissão de tratamento. Hoje a área de trabalho é exclusivamente fictícia (C0).
2. **Validar estrutura:** formato, tamanho, segurança, unidades, CRS, calendário, referências e entidades suportadas. Campo obrigatório ausente produz pendência explícita.
3. **Reconciliar:** comparar com a publicação anterior; listar IDs preservados/novos/removidos, diferenças geométricas, quantidades e vínculos.
4. **Classificar conflito:** `reject` para entrada incompatível; `manual review` para ambiguidade; `approved merge` somente após aprovação identificável. Esses rótulos são o contrato proposto; não representam motor de mesclagem já implementado.
5. **Calcular em separado:** preservar previsão da construtora, independente e hipóteses de simulação. A simulação do usuário não altera análises de referência (ADR-0013).
6. **Publicar revisão aprovada:** conservar fonte e versão anterior, registrar quem aprovou e permitir consulta às diferenças. Não afirmar que o upload IFC atual realiza esta etapa: ele valida/compara, sem publicar geometria revisada.
7. **Emitir relatório:** origem, revisão, data de status, fontes de produtividade, evidência, incertezas e decisões pendentes.

Tolerâncias numéricas de aceite devem ser declaradas no `project.yaml` e lidas pelos testes. Não criar margem silenciosa ou prometer exatidão entre motores com semânticas diferentes. Diferenças de calendário/progresso devem ser explicadas ou tratadas como defeito.

## RACI proposta

R = executa; A = aprova/responde pelo aceite; C = consultado; I = informado. A designação efetiva depende de aprovação da coordenação e dos contratos.

| Atividade | Projetista | Construtora | Fiscalização | Equipe BIM 4D | Titular/coordenação |
|---|---|---|---|---|---|
| Publicar revisão do modelo | R | C | C | C | A |
| Entregar cronograma executivo | C | R | C | C | A |
| Coletar/entregar avanço | I | R | A | C | I |
| Conferir evidências/medição | C | C | R | C | A |
| Validar formato e reconciliar vínculos | C | C | C | R | A |
| Calcular previsão independente | I | C | C | R | A |
| Aprovar alteração de engenharia | R | C | C | C | A |
| Autorizar uso/divulgação de dados | C | C | C | I | R/A |
| Preparar relatório/demo fictícia | I | I | C | R | A |

## Ensaio obrigatório antes de homologar um adaptador

Com pacote fictício: abrir nativo no aplicativo real → alterar uma propriedade/parâmetro → salvar → fechar → reabrir → reexportar → validar → retornar ao INFRA 4D → conferir IDs/unidades/quantidades/vínculos e a revisão publicada. Incluir conflito deliberado em cópia e comprovar rejeição/revisão manual sem sobrescrever a fonte. Arquivos, logs e capturas ficam em `output/`, com hashes; resultado e perdas ficam na matriz de interoperabilidade.

O motor CPM permanece independente; não assumir que editar o calendário no aplicativo externo conserva as mesmas datas. O R13 documenta divergências conhecidas na leitura/cálculo do cronograma IFC pelo IfcOpenShell/Bonsai e exige teste real antes de afirmar compatibilidade.

## Portões ainda não vencidos

- Dado real: ADR substituindo ADR-0004, autorização adequada, armazenamento aprovado e requisitos de `IMPLANTACAO-REAL.md`.
- Aplicativo externo: instalação/licença e fluxo de edição comprovados; nenhuma autorização comercial pode ser inferida de licença estudantil Autodesk.
- Uso multiusuário: autenticação, autorização e auditoria real; o campo “quem” informado no beta não autentica o responsável.
- Aceite técnico de engenharia: profissional designado, critérios e evidência. Um arquivo que valida num parser não é projeto executivo aprovado.

Referências: [matriz Pessoa A](../requisitos/MATRIZ-PESSOA-A.md), [portão do Programa](../prog/PORTAO-DE-AUTORIZACAO.md), `docs/IMPLANTACAO-REAL.md`, `docs/research/R13-interoperabilidade-4d.md`, missão mestre e ADRs vigentes. Nenhum dado corporativo foi consultado para produzir este plano.
