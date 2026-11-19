# FreeCAD portátil — fragmento paramétrico e retorno federado

14/11/2026. Todos os dados são fictícios. O arquivo é um fragmento de três
componentes ilustrativos, não uma OAE completa nem dimensionamento estrutural.

## Prova nativa executada

FreeCAD **1.1.4**, pacote portátil oficial Windows py311, extraído exclusivamente
em `output/tools/freecad-1.1.4/`. Nenhum instalador, associação de arquivo ou
mudança no PATH global. Configuração e dados do aplicativo direcionados a
`output/tools/freecad-1.1.4/profile/`. O runtime Python 3.11 do CAD é externo;
o motor e os testes do projeto continuam no `.venv` Python 3.13.

- SHA-256 do arquivo oficial `.7z` conferido:
  `4828741fc91ee37fafcdb97a1abacb18b04ba451ac4372d9ff7a7349b36f4d6d`.
- Assinatura Authenticode de `bin/freecadcmd.exe`: **Valid**, The FreeCAD project
  association AISBL. Licença inspecionada: `doc/LICENSE.html`, LGPL2+; bibliotecas
  de terceiros constam do pacote. Aplicativo externo, sem incorporar DLLs ao core
  ou redistribuir o programa no pacote de demonstração.
- Três `Part::Box` nativos: Bloco, Pilar e Tabuleiro, ligados a OAE3-FUN/MES/SUE.
- Tabuleiro: parâmetro Height **1000 → 1250 mm**, salvo em r1; documento fechado
  e reaberto. Tipo paramétrico, parâmetro, IDs, quantidades publicadas e formas
  válidas conferidos pelo aplicativo. XML interno dos FCStd r0/r1 também inspecionado
  por parser independente: parâmetro e propriedade de planejamento preservados.
- Volume geométrico ilustrativo do tabuleiro: **96 → 120 m³**. Quantidade de
  planejamento OAE3-SUE continua **3 un**; quantidade executada não foi alterada.
- STEP exportado e reimportado: **três sólidos válidos**, volume e caixa espacial
  comparados aos objetos fonte. STEP não comprova preservação da árvore paramétrica
  ou de IDs customizados: os vínculos ficam no FCStd e no JSON de intercâmbio.
- **Três IDs nativos** realmente salvos/reabertos no CAD; **108 IDs da publicação**
  preservados por cópia no JSON. Essas contagens representam coisas diferentes.

Arquivos recomendados em `output/releases/freecad-parametrico-20261114/`:
`atividades-freecad.geojson`, `nativo-verificado/oae-r0.FCStd`, `oae-r1.FCStd`,
`oae-r1.step`, `revisao-freecad.geojson`, `prova-freecad.json`.
Tentativas anteriores permanecem em `nativo/` e nos logs, sem substituir a prova final.

## Retorno ao INFRA 4D

`source_app="FreeCAD"` é uma autoridade própria, não uma publicação falsamente
rotulada Blender. A API recebe a base e a revisão, verifica o contrato existente
e publica uma cópia em memória somente após ação explícita.

`geometria_local_m` contém a tesselação da forma reaberta. O FreeCAD opera em mm;
vértices são divididos por 1000 uma única vez. Placement local já está na Shape;
a matriz comum posiciona o fragmento no eixo sintético em metros. Caixas espaciais
da tesselação e da Shape são comparadas nos três eixos para detectar escala ou
posição duplicada. A web converte Z-up para Y-up como no contrato existente.

Limites em `project.yaml`: `tolerancia_visual_federacao_m=0.01` e
`tolerancia_volume_cad_m3=0.000001`. Não são tolerâncias de projeto ou medição
contratual. Limite ausente impede a prova; o job deve carregar os valores declarados.

Prova API: três mudanças de malha, 108 IDs da publicação, cópia publicada,
**delta de prazo zero** e cenário de referência idêntico. A timeline, ficha e
cores de avanço continuam sendo da referência, conforme indicado na interface;
o painel federado mostra os dados da revisão. O acervo desaparece ao reiniciar.

Na interface: Modelo 3D/4D → Revisões federadas → base e retorno acima →
Conferir revisão → **Enquadrar revisão** → **Só revisão** para ver as três peças
sem a oclusão do corredor. Selecionar OAE3-SUE mantém o foco e mostra a ficha da
referência; desmarcar restaura a referência. **Publicar revisão isolada** é uma
ação separada. A opção FreeCAD também permite
baixar uma nova publicação. GLB separado continua sendo recurso do Blender;
não foi inventado um GLB FreeCAD nem suporte automático a upload de FCStd/STEP.

## Reprodução no aplicativo oficial

Usar diretório nativo novo: o script recusa qualquer destino já existente.
Job JSON: `{entrada, destino, limites}` com caminhos locais e os limites do
manifesto. O arquivo `job-freecad-verificado.json` registra a rodada executada.

FreeCADCmd importa arquivos Python com semântica distinta de `python arquivo.py`:
a primeira execução direta saiu 0 sem chamar o guard `__main__`. Ela **não** foi
tratada como sucesso. O runner `executar-no-freecad.py` contém:

```python
import os, runpy
runpy.run_path(os.environ['INFRA4D_FREECAD_SCRIPT'], run_name='__main__')
```

Na raiz do repositório, após preparar um job apontando para um destino novo:

```powershell
$perfil = Join-Path (Get-Location) 'output/tools/freecad-1.1.4/profile'
$env:FREECAD_USER_HOME = $perfil
$env:FREECAD_USER_DATA = $perfil
$env:INFRA4D_FREECAD_SCRIPT = Join-Path (Get-Location) 'scripts/infra4d/interop_freecad.py'
$env:INFRA4D_FREECAD_JOB = '<job-novo.json>'
& './output/tools/freecad-1.1.4/FreeCAD_1.1.4-Windows-x86_64-py311/bin/freecadcmd.exe' `
  --user-cfg "$perfil/user.cfg" --system-cfg "$perfil/system.cfg" `
  --log-file "$perfil/freecad-novo.log" '<executar-no-freecad.py>'
```

Exigir `prova-freecad.json` com status pass e conferir arquivos/hashes. Saída 0 do
processo, isoladamente, não comprova execução. Testes próprios:
`tests/test_interop_freecad.py`; resultados atuais ficam no topo do STATE e nos
logs desta rodada. A primeira regressão focada teve uma expectativa errada de
que a rodovia não possuía IDs OAE3; o caso foi corrigido para testar ausência real
da atividade obrigatória, sem bloquear uma publicação válida por tipo de obra.
Reexecução: **115 PASS, 6 SKIP**, exit 0, 43,62 s.

Regressão final com r23: **116 PASS, 6 SKIP**, exit 0, 31,43 s; referência
smoke/API/vertical slice/roteiro/números: **37 PASS**, 53,65 s. Chrome final:
**227 PASS**, interface completa; Edge: **218 PASS** completos antes dos novos
controles, depois **39 PASS** focados finais. Os JSONs registram o escopo; a opção
`--somente-federacao` não substitui o E2E completo. A suíte pytest completa anterior
de 2040 PASS não foi reexecutada nesta onda, nem houve validação de commit isolado.

R23 viu a referência desaparecer ao carregar revisão sem mudanças depois de
isolar. Teste em cópia, com Three.js real e Node, falhou assertivamente antes da
correção; XFAIL(strict) virou XPASS e a marca saiu. O caso também passou no browser.
Node é usado só por essa regressão auxiliar; sem ele, o caso é skip explícito,
com cobertura de navegador separada. Nenhuma mutação no código original.

O limite `ocupacao_linear_minima_revisao_viewport=0.1` vem do manifesto. O teste
projeta os vértices no viewport, exige que estejam dentro da tela e mede fração
linear; observou aproximadamente 0,71 após foco. Isso não avalia GPU/desempenho.
Capturas foram inspecionadas: enquadrar sozinho ainda sofria oclusão pela base;
Só revisão tornou Bloco/Pilar/Tabuleiro legíveis, inclusive seleção e ficha.

## Limites e fontes

GUI não observada, GPU não homologada e nenhum arquivo de cliente utilizado.
É autoria automática de um exemplo com edição paramétrica comprovada; não é
importador geral de FCStd, projeto executivo, IFC/Bonsai ou sincronização
bidirecional arbitrária. Metadados enviados continuam sendo declarações da fonte;
o servidor não emite selo de homologação por aceitar o JSON.

Limites superiores das transformações e coordenadas recebidas continuam pendência
de endurecimento do contrato. Nenhuma publicação externa ou mudança no histórico
foi autorizada pelo ensaio local; o achado institucional histórico segue separado.

Fontes oficiais consultadas: [release e avisos](https://github.com/FreeCAD/FreeCAD/releases/tag/1.1.4),
[arquivos e hashes](https://github.com/FreeCAD/FreeCAD/releases/expanded_assets/1.1.4),
[configuração](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Start_up_and_Configuration.md),
[Part Box](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Part_Box.md),
[TopoShape](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Part_TopoShape.md).
