# R10 — Integração com o Obrasgov.br (API de dados abertos)

> Data: **2026-11-12**. Convenção: **[V]** = visto nesta rodada em fonte oficial (URL citada); **[B]** = visto só em
> busca ou fonte de terceiro; **[NV]** = não verificado.
> **Regra de dado (ADR-0004):** nenhum dado real foi baixado nem gravado no repositório ou em teste. Li o
> `openapi.json` oficial (documentação) e inspecionei a **estrutura** de **uma** resposta pública de
> `/execucao-fisica` (nomes de campo e forma dos valores, sem os valores), sem gravá-la.
> O protótipo usa só a fixture FICTÍCIA escrita à mão.

## Resumo executivo

1. **API pública oficial e aberta.** O endereço é `https://api-publica.obrasgov.gestao.gov.br/obras`, com OpenAPI 3.1
   em `/obras/openapi.json` e Swagger em `/obras/docs` [V]. O OpenAPI **não declara autenticação** (`security`
   ausente), e uma consulta pública funcionou sem credencial [V].
2. **Recursos (todos GET, filtros opcionais, paginados até 200 por página):** `projeto-investimento`,
   `execucao-fisica`, `contrato`, `empenho`, `geometria`, `historico-situacao-cancelada-paralisada`,
   `estudo-viabilidade`, `data-atualizacao` [V].
3. **O que serve ao INFRA 4D:** identificação da obra, prazos previstos e efetivos (marcos), **percentual de
   execução física global por data**, contratos (lote, construtora, vigência e valor), situação e paralisações com
   justificativa, municípios e pins [V].
4. **O que NÃO existe no Obrasgov:** cronograma (atividades, relações, calendário), quantidades, produtividade,
   boletins por serviço e km [V, pelo esquema]. Ou seja, o Obrasgov **não substitui** o MSPDI/XER nem o boletim:
   ele dá o contexto e uma série de avanço para confronto.
5. **Uso de maior valor:** confrontar o **% físico declarado no Obrasgov** com o **avanço calculado pelo INFRA 4D** e
   usar a série como EV do Earned Schedule no nível da obra. É o mesmo tipo de achado da demo ("a data/o percentual
   declarado não acompanha o medido").
6. **Protótipo:** `scripts/infra4d/adaptador_obrasgov.py` converte o JSON paginado no formato do Obrasgov para o
   esquema parcial do projeto. Os testes (`tests/test_adaptador_obrasgov.py`, 16) usam
   `examples/fixtures/obrasgov_sintetico.json` (FICTÍCIA) e não acessam a rede.
7. **Pendências:**
   - termos de uso dos dados e limite de requisições não declarados [NV];
   - a página do gov.br avisa que a API antiga conviveu até **31/08/2026** [V];
   - o dicionário de dados (zip) não foi aberto [NV].

## 1. O que a documentação oficial diz

| Item | Valor | Fonte | Situação |
|---|---|---|---|
| URL base | `https://api-publica.obrasgov.gestao.gov.br` (servidor `/obras`) | https://www.gov.br/obrasgov/pt-br/ferramentas-de-gestao-e-transparencia/api-de-dados-abertos-obrasgov-br_novo · https://api-publica.obrasgov.gestao.gov.br/obras/openapi.json | [V] |
| Especificação | OpenAPI **3.1.0**, "API de dados abertos do Obrasgov", versão **1.0** | openapi.json | [V] |
| Autenticação | nenhuma declarada (sem `security` nem `securitySchemes`); GET público funcionou sem credencial | openapi.json; consulta de estrutura em 2026-11-12 | [V] |
| Paginação | `pagina` (≥ 1, padrão 1) e `tamanho_da_pagina` (1–200, padrão 50). Envelope `{data, total_pages, total_items, page_number, page_size}` | openapi.json | [V] |
| Volume observado | `/execucao-fisica`: **74.411** registros no total (`total_items`) na data da consulta | consulta de estrutura | [V] |
| Formatos de data | `AAAA-MM-DDThh:mm:ss` (início e fim da execução), `AAAA-MM-DDThh:mm:ss.ffffff` (cadastro), `AAAA-MM-DD` (atualização) | consulta de estrutura | [V] |
| Formato do id | `99999.99-99` (ex. no pacote R: "134851.26-07") | consulta de estrutura; https://cran.r-universe.dev/obrasgovr/doc/manual.html | [V]/[B] |
| Convivência com a API antiga | "O prazo será até dia 31/08/2026" | página gov.br acima | [V] |
| API antiga (CIPI) | serviços de **escrita** protegidos (`/api/protected/execucao/fisica`, POST/PUT), que exigem permissão | https://www.gov.br/transferegov/pt-br/obrasgov/doc/documentacao-dos-web-services-obrasgov-v-1-4-2_final.pdf (HTTP 401 ao abrir; conteúdo visto em busca) | [B] |
| Dicionário de dados | zip "modelo_dados_api_obrasgov.zip" citado no OpenAPI | https://www.gov.br/transferegov/pt-br/ferramentas-gestao/paineis-gerenciais/arquivos/modelo_dados_api_obrasgov.zip/@@display-file/file | [NV] (não aberto) |
| Termos de uso dos dados | a página declara **CC BY-ND 3.0** para "todo o conteúdo deste site"; não diz se vale para os dados da API | página gov.br acima | [NV] para os dados |
| Limite de requisições | não declarado | openapi.json | [NV] |
| Contato | [Página oficial da API e orientações de contato](https://www.gov.br/obrasgov/pt-br/ferramentas-de-gestao-e-transparencia/api-de-dados-abertos-obrasgov-br_novo) | gov.br / Obrasgov | HTTP 200 em 14/11/2026; e-mail substituído por autorização da titular |
| Cliente aberto de terceiros | pacote R `obrasgovr` (MIT, v0.1.1), mesmos recursos e paginação | https://cran.r-universe.dev/obrasgovr/doc/manual.html | [B] |

### 1.1 Recursos e campos (do `openapi.json`) [V]

| Recurso | Campos principais |
|---|---|
| `GET /projeto-investimento` | `id_projeto_investimento`, `desc_nome`, `desc_projeto`, `desc_meta_global`, `dt_inicial_prevista`, `dt_final_prevista`, `dt_inicial_efetiva`, `dt_final_efetiva`, `natureza_intervencao`, `especie_intervencao`, `situacao`, `uf_principal`, `organizacao_resp`, `cnpj_organizacao_resp`, `qtd_empregos_gerados`, **`ind_bim`**, `possui_estudo_viabilidade`. Listas aninhadas: `executores`, `repassadores`, `tomadores`, `investimentos_previstos` (valor e fonte), `ppas`, `eixos_tipos` (eixo/tipo/subtipo), `fotos` (só `ind_foto`), `pins` (lat/lon), `areas_restricao` |
| `GET /execucao-fisica` | `id_projeto_investimento`, `id_execucao_fisica`, **`percentual_execucao_fisica`**, `dt_inicial_execucao`, `dt_final_execucao`, `tipo_instrumento`, `tipo_forma_execucao`, `dt_criacao_instrumento`, `dt_cadastro_execucao`, `dt_atualizacao_execucao`, `indicativos[]`, `motivos[]` |
| `GET /contrato` | `id_contrato`, `numero_contrato`, `vigencia_inicio_contrato`, `vigencia_fim_contrato`, `data_assinatura_contrato`, `modalidade_contrato`, `objeto_contrato`, `fornecedor_contrato`, `cnpj_fornecedor_contrato`, `situacao_contrato`, `valor_global_contrato`, `valor_acumulado_contrato`, `valor_utilizado_pi_contrato`, `link_transparencia` |
| `GET /empenho` | `nr_empenho`, `valor_empenho`, `liquidado`, `pago`, restos a pagar, `programa_trabalho`, `acao_orcamentaria`, `credor`… |
| `GET /geometria` | `id_geometria`, `sg_uf`, `no_municipio`, `cod_ibge`, `origem_geometria` (**sem** a geometria em si no esquema) |
| `GET /historico-situacao-cancelada-paralisada` | `data_historico_situacao_investimento`, `descricao_…`, `justificativa_cancelada_paralisada`, `possui_tratativas_…`, `fase_tratativas_…` |
| `GET /estudo-viabilidade` | `tipo_estudo_viabilidade`, `especificacao_estudo_viabilidade` |
| `GET /data-atualizacao` | `data_ultima_atualizacao` |

Na resposta inspecionada, `tipo_instrumento`, `tipo_forma_execucao` e `dt_criacao_instrumento` vieram nulos, e
`indicativos` e `motivos`, vazios [V]. **Nenhum recurso traz medição por item, cronograma ou quantidades.**

## 2. Mapeamento campo a campo: Obrasgov.br → INFRA 4D

Implementado em `adaptador_obrasgov.converter`. "Saída" usa o esquema do projeto (`ferrovia` é a chave que o código
usa para "a obra").

| Conceito INFRA 4D | Campo de saída | Origem no Obrasgov | Regra |
|---|---|---|---|
| Obra: id | `ferrovia.id` | `projeto_investimento.id_projeto_investimento` | exige o formato `99999.99-99` |
| Obra: nome / UF / órgão | `ferrovia.nome`, `.uf`, `.orgao_responsavel`, `.executores` | `desc_nome`, `uf_principal`, `organizacao_resp`, `executores[].organizacao_executor` | cópia |
| Tipo de obra | `meta.tipo_obra` | `eixos_tipos[].tipo/subtipo` e `desc_nome` ("ferrov", "rodov", "BR-") | heurística; senão `desconhecido`. Valores reais dos eixos [NV] |
| Início do projeto | `meta.inicio_projeto` | `dt_inicial_efetiva`, senão `dt_inicial_prevista` | AAAA-MM-DD |
| Prazo contratual | `meta.termino_contratual` e marco `M-FIM-PREVISTO` | `dt_final_prevista` | marco de término |
| Marcos | `marcos[]` | `dt_inicial_prevista`, `dt_final_prevista`, `dt_inicial_efetiva`, `dt_final_efetiva` | só os preenchidos |
| Data de status | `meta.data_status` | maior `dt_atualizacao_execucao` (ou fim da execução) | — |
| Avanço físico (série) | `avanco_fisico[]` {data, percentual, motivos, indicativos} | `execucao_fisica[]`: `dt_final_execucao`, `percentual_execucao_fisica`, `motivos`, `indicativos` | 0–100, ordenado; queda de percentual vira **aviso** |
| Lote | `lotes[]` {id `C<id_contrato>`, nome, construtora, contrato} | `contrato[]`: `id_contrato`, `objeto_contrato`, `fornecedor_contrato`, vigência e valores | 1 contrato = 1 lote (hipótese: obra dividida por contrato). `km_ini`/`km_fim` = None (não há no Obrasgov) |
| Situação / paralisação | `situacoes[]` | `historico_situacao_cancelada_paralisada[]` | data, situação, justificativa, fase das tratativas |
| Localização | `localizacao.municipios`, `.pins` | `geometria[]` (município, IBGE), `projeto.pins` (lat/lon) | pontos, não eixo |
| Financeiro (contexto) | `financeiro.investimento_previsto`, `.valor_global_contratos` | `investimentos_previstos[]`, `contrato.valor_global_contrato` | soma |
| Rastreabilidade | `rastreio` | ids de projeto, execuções e contratos | toda saída aponta o id de origem |
| Marca de fictício | `meta.ficticio` | **não existe no Obrasgov**; só `"_infra4d_ficticio": true` na fixture | dado real sai sem a marca (ADR-0005) |
| Atividade, relação, calendário | — | **não existe** | lacuna: vem do MSPDI/XER da construtora |
| Boletim (quantidade, equipes·dia) | — | **não existe** | lacuna: vem da medição/SIAC (por arquivo) ou do diário |

## 3. Lacunas

**O Obrasgov tem e o INFRA 4D não:**
- empenhos, liquidação e pagamento (execução **financeira** real);
- repassadores, tomadores e fontes de recurso;
- histórico de paralisação e cancelamento com justificativa e tratativas;
- estudos de viabilidade;
- indicador de uso de BIM (`ind_bim`);
- empregos gerados e população beneficiada;
- cobertura nacional (dezenas de milhares de registros de execução).

**O INFRA 4D tem e o Obrasgov não:**
- cronograma com lógica (CPM) e calendários;
- quantidades, produtividade e boletins por serviço;
- referência linear (km/estaca);
- previsão independente de término (CPM, ES, MC) e explicação contrafactual;
- linha de balanço;
- 4D/IFC;
- fiscalização no modelo da IN 57.

**Consequência:** o Obrasgov é **fonte de contexto e de confronto**, não de cálculo. Para recalcular o prazo continuam
necessários o cronograma (MSPDI/XER) e as medições da obra.

## 4. Protótipo (executado)

| Arquivo | Conteúdo |
|---|---|
| `examples/fixtures/obrasgov_sintetico.json` | Fixture **FICTÍCIA** no formato paginado do Obrasgov: 1 projeto (rodovia fictícia de 48 km, coerente com a BR-FIC 999), 3 execuções físicas (12,5% → 48% → 81,9%), 2 contratos, 2 municípios e 1 paralisação. CNPJs zerados e ids inexistentes. Marcada com `_aviso` e `_infra4d_ficticio: true` |
| `scripts/infra4d/adaptador_obrasgov.py` | `converter(entrada)` → `meta`, `ferrovia`, `lotes`, `marcos`, `avanco_fisico`, `situacoes`, `localizacao`, `financeiro`, `rastreio`, `lacunas`, `avisos`. Recusa com `ErroObrasgov`: projeto ausente ou múltiplo, id fora do formato, registro de outro projeto, percentual fora de 0–100 ou booleano, data inválida, envelope incompleto (menos registros que `total_items`). **Não acessa a rede** e não inventa atividade nem boletim |
| `tests/test_adaptador_obrasgov.py` | 16 testes: ida e conferência campo a campo, marca de fictício (só booleano), aviso de percentual que diminui, 8 recusas, ausência de bibliotecas de rede e entrada não alterada. **16 passed**; 3 mutações (marca por "truthiness", aceitar outro projeto, tirar a faixa de percentual) derrubaram 1 teste cada |

## 5. Próximos passos (para o BACKLOG)

```markdown
| OG1 | Cliente da API pública do Obrasgov (GET, paginação até 200, sem credencial) que junte as páginas e entregue ao adaptador — SÓ depois do ADR de dado real (ADR-0004) | teste com servidor falso local (sem rede); nada gravado no Git | decisão da titular |
| OG2 | Confronto "% físico declarado no Obrasgov × avanço calculado" e ES no nível da obra a partir de `avanco_fisico` | divergência > tolerância do manifesto vira alerta | OG1 |
| OG3 | Ler o dicionário de dados oficial (modelo_dados_api_obrasgov.zip) e confirmar os valores de `eixos_tipos` para o tipo de obra | heurística substituída por tabela de códigos | — |
| OG4 | Confirmar termos de uso dos DADOS da API (a página declara CC BY-ND 3.0 para o site) e eventual limite de requisições | registro com fonte | — |
```

## Fontes

- https://api-publica.obrasgov.gestao.gov.br/obras/openapi.json
- https://api-publica.obrasgov.gestao.gov.br/obras/docs
- https://www.gov.br/obrasgov/pt-br/ferramentas-de-gestao-e-transparencia/api-de-dados-abertos-obrasgov-br_novo
- https://www.gov.br/transferegov/pt-br/obrasgov/doc/documentacao-dos-web-services-obrasgov-v-1-4-2_final.pdf
- https://www.gov.br/transferegov/pt-br/obrasgov/doc/webservice-obrasgov-execucao-fisica.pdf (HTTP 401 nesta rodada)
- https://cran.r-universe.dev/obrasgovr/doc/manual.html
