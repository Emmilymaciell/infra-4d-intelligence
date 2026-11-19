# Portão de autorização — piloto do Programa

Data: 13/11/2026. Estado desta missão: **C0 — exclusivamente fictício**. Este documento não autoriza acesso, extração ou divulgação. Nenhuma fonte do Programa foi acessada nesta auditoria.

O beta não contém modelos BIM do Programa compartilhados ou homologados. Candidatos citados na missão não provam existência, atualidade, completude ou permissão de uso. Não criar catálogo como se tivesse ocorrido uma consulta.

## Portões C0 a C5

| Portão | Permissão necessária / evidência | Ação permitida após cumprir | O que continua vedado |
|---|---|---|---|
| C0 — demonstração fictícia | ADR-0004/0005 e dados reprodutíveis com marca booleana fictícia | Trabalhar nos pilotos sintéticos, visual, código, testes e formatos abertos | Acessar SharePoint/Graph do Programa, baixar documentos ou usar valores/fotos/localizações corporativas |
| C1 — descoberta de metadados | Autorização explícita da titular para conta, fonte, escopo e finalidade; acesso por ferramenta adequada, sem credencial em prompts/log/Git | Inventariar metadados mínimos dos locais autorizados, em catálogo restrito fora do Git | Ler conteúdos por inferência da permissão de listar, baixar em massa, publicar catálogo ou enviar metadados a terceiros |
| C2 — extração selecionada | Autorização institucional/contratual de tratamento e finalidade; arquivos/revisões escolhidos; armazenamento aprovado; novo ADR/manifesto conforme política de dado real | Extrair somente campos necessários, com arquivo/versão/página/aba/célula, classificação e revisão | OCR/conversor/LLM externo sem aprovação; cópia de bruto/evidência para Git; reutilização para outra finalidade |
| C3 — base de prova | Conferência do conteúdo autorizado e da qualidade: eixo/CRS, trechos, quantidades, rede, calendários, data de status, medições, revisões e responsáveis | Relatar cobertura e lacunas; selecionar caso por dados efetivamente disponíveis | Tratar PDF sem predecessoras como rede CPM oficial; inferir atualidade apenas pelo título; inventar BIM executivo |
| C4 — piloto privado | C1/C2/C3 cumpridos; ambiente segregado; autorização por papel, fonte somente leitura, auditoria, retenção e responsáveis aprovados | Integrar um piloto privado nos limites contratados, com revisões e aprovação | Uso público, acesso de várias pessoas sem controle ou mistura de dados com a demo fictícia |
| C5 — demonstração externa | Autorização específica para circulação externa por material, público e finalidade; sanitização/validação conferida | Mostrar somente o material expressamente liberado | Presumir que acesso à fonte permite divulgar a Pessoa A; reproduzir documentos/fotos/valores/nomes/localização detalhada sem permissão |

Os portões não devem ser reduzidos a um botão de confirmação. Cada autorização deve ter escopo verificável, responsável, data, finalidade e evidência em armazenamento aprovado. A implantação real exige substituir o ADR-0004 antes da primeira carga de dado real, rever manifesto/criticidade/revisão de segurança e cumprir os critérios de saída aplicáveis.

## Campos e separação pública/privada

A arquitetura de entrada deverá carregar, por registro ou pacote, `origem_evidencia`, `classificacao`, `acesso`, `visibilidade_demo` e `tipo_dado` (`real`, `ficticio`, `derivado`), além de revisão, checksum e fonte. Estes são **requisitos da missão**, não controles todos implementados no beta atual.

Regras propostas para implementação/teste antes de C4/C5:

- Ausência ou ambiguidade de permissão não habilita exibição pública.
- `derivado` não significa público: a derivação conserva as restrições da fonte até revisão/autorização específica.
- Nome de arquivo ou texto livre “fictício” não substitui a marca booleana nem comprova direito de divulgação.
- Modo demo usa uma lista explícita de pacotes fictícios aprovados, não descobre automaticamente documentos privados.
- Erros, relatórios, logs, downloads, thumbnails e capturas respeitam a mesma separação; ocultar um cartão na UI não protege a API.
- Upload de um pacote restrito em modo público deve ser recusado antes da publicação; caso adverso deve comprovar a recusa.
- A auditoria de acesso deve obter identidade da sessão autenticada; o texto “quem” do beta não fornece essa garantia.

O estado C0 não exige inventar controles empresariais para bloquear a melhoria da demo. Permite continuar com as duas obras fictícias, sem contas externas e sem acesso à fonte do Programa.

## Geometria indicativa a partir de documentos

Mesmo após C2, uma geometria criada a partir de informações documentais pode ser apenas indicativa. Deve declarar **“sem BIM de origem / geometria ilustrativa”**, origem e revisão. Não apresentá-la como projeto executivo BIM, as-built, geometria compatibilizada ou fonte contratual de quantitativos sem a prova e aprovação correspondentes.

Se faltarem eixo, CRS, datum vertical, unidades, predecessoras ou medições aprovadas, marcar a lacuna e solicitar o dado ao responsável. O sistema não deve preencher silenciosamente essas ausências para produzir aparência de completude.

## Solicitação agrupada quando a frente real for priorizada

Sem executar os acessos, preparar uma única solicitação que identifique:

1. Fonte/conta e escopo de metadados desejados em C1.
2. Arquivos selecionados e autorização institucional/contratual necessária para C2.
3. Local aprovado de guarda, responsáveis, finalidade, retenção e ferramentas locais autorizadas.
4. Quem valida engenharia e quem aprova publicação privada/externa.
5. Limites de licença, segurança e distribuição que dependam de decisão.

Enquanto isso, avançar nas frentes fictícias autorizadas. Não acessar Graph/SharePoint “só para conferir” antes da autorização.

Referências: missão mestre §8/§16/§17; ADR-0004 e ADR-0005; `docs/IMPLANTACAO-REAL.md`; contrato do registry; [plano de recebimento](../implantar/PLANO-PROJETISTA-CONSTRUTORA-FISCALIZACAO.md). O catálogo e a demo do Programa interna permanecem pendentes dos portões aplicáveis.
