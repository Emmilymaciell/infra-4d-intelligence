# Softwares e licenças — rodada de interoperabilidade

Consulta: 13/11/2026. Esta matriz registra o que foi aberto nas fontes oficiais e o que foi executado localmente. Não constitui parecer jurídico. Não houve serviço pago, assinatura, conta nova ou acesso ao Programa.

| Ferramenta | Versão / disponibilidade | Licença e uso nesta arquitetura | Teste/decisão | Fonte oficial |
|---|---|---|---|---|
| QGIS | Instalado 3.40.14-Bratislava, runtime confirmado | GPL; aplicativo externo gratuito, sem incorporar PyQGIS ao FastAPI | GPKG/QGZ reais, edição/salvamento/reabertura via API; escolhido para primeiro retorno GIS | [licença](https://qgis.org/license/), [API de vetores](https://docs.qgis.org/3.40/en/docs/pyqgis_developer_cookbook/vector.html), [projetos](https://docs.qgis.org/3.40/en/docs/pyqgis_developer_cookbook/loadproject.html) |
| Blender | Instalado 5.2.3 LTS, build 22/10/2026 | GPL v2 ou posterior conforme copyright instalado; dependências sob licenças compatíveis; app externo gratuito | BLEND/GLB reais e retorno de propriedades/malha por bpy; não comprova Bonsai | [código/licença](https://raw.githubusercontent.com/blender/blender/main/COPYING), `copyright.txt` da instalação |
| Bonsai / IfcOpenShell | IfcOpenShell Python já faz parte do projeto; Bonsai GUI não confirmado | Usar extensão GPL como ferramenta externa; IfcOpenShell conforme decisão existente LGPL sem modificação | Não instalar extensão sem autorização; pacote precisa corresponder ao Python 3.13/Blender instalado | [downloads oficiais](https://ifcopenshell.org/downloads.html), [instalação oficial](https://docs.ifcopenshell.org/ifcopenshell-python/installation.html) |
| ProjectLibre Desktop | Release 1.9.8, arquivo MSI 76,9 MB listado no repositório oficial; não instalado nesta rodada | Desktop anunciado gratuito e open source; licença completa deve ser conferida no pacote antes da instalação/distribuição; não incorporar ao core | Instalação Windows aguarda autorização; XML de troca pronto; nada de serviço Cloud/trial | [Desktop](https://projectlibre.com/projectlibre-desktop/), [arquivos 1.9.8](https://sourceforge.net/projects/projectlibre/files/ProjectLibre/1.9.8/) |
| FreeCAD | 1.1.4 portátil executado em 14/11, sem instalador Windows | `doc/LICENSE.html` do pacote: LGPL2+, com dependências listadas; app externo, binários não redistribuídos | SHA-256 oficial e assinatura Valid conferidos; três Part::Box em FCStd, editar/salvar/reabrir, STEP reimportado e retorno pela API. GUI não observada | [release](https://github.com/FreeCAD/FreeCAD/releases/tag/1.1.4), [artefatos](https://github.com/FreeCAD/FreeCAD/releases/expanded_assets/1.1.4), `docs/interop/FREECAD-PARAMETRICO.md` |
| Excel | COM16 disponível e executado pelo orquestrador | Software instalado existente; não contratado/adquirido nesta missão | XLSX/fórmulas comprovados em cópia; Calc segue não comprovado | Evidência local `06-quantitativos/prova-excel.json` |
| LibreOffice Calc | Instalação não confirmada | Não redistribuído ou instalado | Adiar por prioridade demo; não confundir teste Excel com Calc | Sem alegação de versão/licença de pacote não inspecionado |
| three.js | Biblioteca já vendorizada no projeto | MIT segundo NOTICE/pesquisa existente | Preservada; sem migração de visualizador nesta rodada | NOTICE e pesquisa R04 do repositório |
| pypdfium2 | 5.15.2, isolado em `output/tools/pdf-render` | METADATA do wheel declara BSD-3-Clause, Apache-2.0 e licenças das dependências; não incorporado ao FastAPI | Renderizou os PDFs do Excel para QA; sem instalação Windows global ou dependência do beta | [API oficial](https://pypdfium2.readthedocs.io/en/stable/python_api.html), METADATA e LICENSES do wheel instalado |

Navegadores executados: Chrome 157.0.8103.52 (214 PASS) e Edge 157.0.4341.46
(220 PASS), headless/CDP com renderização por software. Não é homologação GPU
real. Benchmark do mesmo cenário: 2167 instâncias/38018 triângulos; baixo consumo
326/11318. Intervalo mediano observado de quadros sob software: Chrome 149,9 ms,
Edge 66,6 ms, em rodadas diferentes; não tratar como benchmark comparativo
controlado ou promessa de fluidez no notebook.

## Downloads candidatos para autorização

Registro inicial de 13/11. Em 14/11, o portátil FreeCAD foi baixado e executado
no ambiente local permitido pela missão §16; não houve instalação Windows/admin.
ProjectLibre tem ZIP/JAR portáteis, ainda sem execução. Não confundir pendência
de instalação global com impossibilidade de investigar uma distribuição local.

- **ProjectLibre 1.9.8:** o projeto oficial aponta para SourceForge. Candidatos Windows: `ProjectLibre-1.9.8.msi`; também há ZIP e JAR 1.9.8. Nenhum foi instalado; Java e termos do pacote precisam ser conferidos antes da execução.
- **FreeCAD 1.1.4:** `FreeCAD_1.1.4-Windows-x86_64-py311-installer.exe`, 495 MB; SHA-256 publicado `845f7101d33faf257a82a0cadc5f4f3804441f46ee493eb32b92fcf9c7147a24`. Alternativa portátil `.7z`, 399 MB, SHA-256 `4828741fc91ee37fafcdb97a1abacb18b04ba451ac4372d9ff7a7349b36f4d6d`. A release alerta sobre correções de segurança ao abrir FCStd não confiável.
- **Bonsai:** selecionar pacote oficial para Blender/Python efetivamente instalados, conferir manifesto e hash; não assumir que o primeiro pacote do catálogo corresponde ao Blender 5.2/Python 3.13. A página de extensão retornou erro 402 na ferramenta; não foi usado isso como prova de compatibilidade.

### Próximo planejador — pesquisa de 14/11, ainda não executado

SourceForge oficial fornece ZIP de 20,5 MB e JAR de 22,6 MB do ProjectLibre 1.9.8.
Licença conferida no [código oficial](https://sourceforge.net/p/projectlibre/code/ci/master/tree/projectlibre_build/license/license.txt):
**CPAL 1.0**, com atribuição e condições de uso em rede; não presumir GPL/LGPL.
Manter app externo, sem embutir classes no servidor. Runtime Java portátil pode
ser obtido nos [arquivos oficiais Temurin](https://adoptium.net/installation/archives),
mas versão, checksum e compatibilidade ainda precisam de execução local.
O [build oficial](https://sourceforge.net/p/projectlibre/code/ci/master/tree/projectlibre_build/build.properties)
cita Java 8 no Windows e OpenJDK 21 no macOS; isso não comprova headless em qualquer JVM.
Próximo ensaio: inspecionar o JAR real com jar/javap e confirmar o leitor/escritor
nativo POD. Não renomear XML nem serializar um objeto arbitrário para alegar POD.
Swing pode exigir GUI; importação/edição/salvamento/retorno permanecem sem prova.

## Custos, manutenção e limites da pesquisa

QGIS e Blender já estavam instalados e foram executados localmente, sem custo adicional ou rede durante as provas. A arquitetura conserva core Python puro e ferramentas externas; mudar essa fronteira exige nova análise de licença/distribuição. Não incorporar bibliotecas GPL/AGPL ao produto proprietário por conveniência.

Documentação web do Blender retornou 402/403; utilizou-se o aplicativo oficial instalado e seu copyright, com prova runtime persistida. As páginas QGIS 3.40 avisam que a versão documental chegou ao fim de vida; a prova desta rodada é especificamente da instalação 3.40.14, sem atualização automática.

Experiências comunitárias não servem como prova de licença ou compatibilidade.
Nenhuma dependência foi adotada por popularidade. Scouting amplo de ferramentas
comerciais, terreno público e 5D oficial continua fora do aceite desta demo.

## Consulta complementar — 14/11/2026

Pesquisa feita enquanto a suíte executava, sem instalar dependências, abrir
serviços ou alterar o núcleo. Estes candidatos **não foram experimentados** nesta
rodada; não confundir a consulta com as provas reais QGIS/Blender/Excel acima.

| Candidato | Fonte primária consultada / licença declarada | Aplicação possível e decisão nesta demo |
|---|---|---|
| That Open Engine / Fragments | [Engine oficial](https://thatopen.com/bim-software-open-source/engine/): MIT; distingue biblioteca aberta de plataforma/serviços comerciais | Candidato para indexação e modelos maiores. Preservar three.js e vínculos existentes; não migrar sem benchmark reproduzível. Nenhum pacote/versão executado |
| MPXJ | [Documentação oficial](https://www.mpxj.org/): LGPL; ler termos e licenças de dependências no pacote. Documenta leitura de MSPDI/XER e formatos de planejadores, além de escrita de formatos de troca | Candidato a adaptador/oráculo externo, preservando CPM próprio. Não equivale a homologação P6/Project. Nenhum pacote/versão executado |
| OR-Tools | [Repositório oficial](https://github.com/google/or-tools): Apache-2.0 | Candidato para comparar nivelamento/otimização com SGS. Não substituir a heurística na demo sem caso pequeno independente e medição de custo. Nenhum pacote/versão executado |

### Relatos comunitários — sinais para investigação, não prova técnica

A busca pública Reddit desta rodada retornou conteúdo indexado, diferentemente
do bloqueio relatado na pesquisa antiga. Não houve contorno de bloqueio, postagem,
mensagem ou download de extensão sugerida por participantes.

- [Relato sobre união de IFCs no Blender/Bonsai](https://www.reddit.com/r/bim/comments/1s908ye/has_anybody_ever_used_blender_to_merge_ifc_files/), março/abril de 2026: participantes relatam encerramentos ao unir arquivos. Versões, hardware e causalidade não foram reproduzidos aqui. Serve para exigir ensaio de memória/volume antes de prometer modelos grandes.
- [Discussão sobre IFC/IDS/BCF e aprovação](https://www.reddit.com/r/bim/comments/1rcdfp1/new_to_bim_how_do_you_actually_use_ifc_ids_bcf_in/), fevereiro de 2026: relatos levantam papéis e etapas de aprovação. Não são norma; os gates propostos do projeto continuam definidos pelo contrato e pela titular.

Os experimentos reais deste incremento compararam dois retornos de geometria:
vértices/matriz extraídos do BLEND reaberto e GLB exportado pelo aplicativo. O Edge
conferiu IDs e a caixa da edição de espessura nos dois caminhos. Isso fundamenta
a decisão local de federação sem adotar biblioteca nova por popularidade.
