# OAE editável e retorno do FCStd existente — 14/11/2026

Todos os dados são fictícios. Continuação de [FreeCAD paramétrico](FREECAD-PARAMETRICO.md), preservando seus arquivos e ZIP. Nenhum commit, push, instalador global, dado do Programa ou upload externo.

## O que foi efetivamente executado

FreeCAD 1.1.4 portátil oficial abriu um FCStd existente, editou dimensões, salvou **outro** FCStd, fechou e reabriu o documento. Exportou STEP e reimportou pelo kernel do próprio aplicativo. Conferiu sólidos válidos, volumes, caixas espaciais, parâmetros e vínculos. A tesselação da forma reaberta retornou ao INFRA 4D; a API e os navegadores recebem o arquivo real, sem simular edição nativa.

**Não houve observação da GUI FreeCAD.** O canal Computer Use falhou com pipe ausente, inclusive após a recuperação prevista na skill. Isso não foi contornado com outra automação de interface. As capturas são do INFRA 4D em navegador headless/CDP, renderizado por software; não provam GUI CAD manual ou desempenho da GPU.

O pacote anterior tinha **dois FCStd, três componentes**, e um STEP; não três arquivos FCStd. Esta continuação acrescenta arquivos reais, sem modificar aqueles originais.

## Arquivos para abrir

Na raiz do repositório:

```powershell
.\run-beta.ps1
```

Abra http://127.0.0.1:8765/. Em outro PowerShell, para a abertura manual pendente no CAD:

```powershell
& '.\output\tools\freecad-1.1.4\FreeCAD_1.1.4-Windows-x86_64-py311\bin\FreeCAD.exe' '.\output\releases\freecad-oae-retorno-20261114\detalhada-validada\modelo-revisado.FCStd'
```

O comando de GUI acima é instrução para a titular, **não teste de GUI concluído**. O teste automatizado usou `freecadcmd.exe`, perfil isolado e Python próprio do CAD. O beta continua no `.venv` Python 3.13, sem DLLs FreeCAD.

Arquivos em `output/releases/freecad-oae-retorno-20261114/`:

| Caminho | Conteúdo |
|---|---|
| `existente/modelo-revisado.FCStd` | Continuação dos três componentes antigos; tabuleiro 1250 → 1500 mm, 120 → 144 m³ |
| `detalhada/ponte-r0.FCStd` | OAE com 196 caixas paramétricas antes da edição |
| `detalhada/modelo-revisado.FCStd` | Primeira edição da OAE detalhada, salva e reaberta |
| `detalhada-validada/modelo-revisado.FCStd` | Retorno do FCStd r0 existente, com validação reforçada do manifesto original |
| `detalhada-validada/modelo-revisado.step` | 196 sólidos exportados/reimportados; não contém a árvore paramétrica FCStd |
| `detalhada-validada/revisao-freecad.geojson` | Retorno federado correspondente ao FCStd e STEP acima |
| `detalhada-validada/prova-retorno.json` | Resultados nativos, hashes, edição e limites aplicados |
| `chrome/`, `edge-completo/` | Capturas reais do navegador e resultados com escopo explícito |

Base original para a conferência: `output/releases/freecad-parametrico-20261114/atividades-freecad.geojson`. Não substitua a base original pelo retorno.

## Modelo e roteiro curto

Trecho reto de **36 m, três vãos de 12 m**, dentro da atividade de 400 m; não modela os 400 m completos nem reconstrói curva/rampa/superelevação. Envelope com fundações de 40 m. Não é dimensionamento estrutural ou projeto executivo. Cada componente é `Part::Box` editável, com material, dimensões, identidade estável e atividade.

- Fundações: 28 peças; mesoestrutura: 24; superestrutura: 57.
- Lastro: 9 camadas/trechos; dormentes: 60; trilhos: 18 caixas formando perfis simplificados.
- Guarda-corpo `OAE3_SUE_CORRIMAO_V01_E`: Height 100 → 150 mm; volume 0,116 → 0,174 m³, preservando contatos do exemplo.

Modelo 3D/4D → Revisões federadas → selecione base e revisão → Conferir revisão → Enquadrar revisão → Só revisão. O seletor **Componente CAD** mostra as peças individuais e a ficha lateral apresenta dimensões/material/volume. Ative **Ambiente ilustrativo** para terreno, água e vegetação com a geometria CAD em escala 1:1. A engenharia procedural antiga fica oculta, evitando duas pontes sobrepostas. Voltar ao modo Técnico remove o ambiente. Publicar revisão isolada é opcional e mantém apenas uma cópia em memória até reiniciar.

Para o teste manual pendente: abra r0, selecione o guarda-corpo citado na árvore, altere Height para 150 mm e use Salvar como em um **novo caminho**. Preserve nomes, propriedades INFRA4D e manifesto. O retorno aceita FCStd desse protocolo; não é importador genérico de documentos arbitrários. Não prometa suporte a novos componentes sem mapear e revisar explicitamente.

## Vínculos, quantitativos e limites

São **196 IDs nativos**, agregados em seis atividades, dentro dos **108 IDs da publicação JSON**. FCStd usa mm; malha usa metros, convertidos uma vez. A matriz posiciona a geometria no eixo fictício; a web converte Z-up para Y-up. Limites do `project.yaml`: 0,01 m para caixas espaciais e 0,000001 m³ para volume STEP.

O mapa confiável nome → atividade é regenerado dos descritores do piloto e da base; não é aceito apenas porque o próprio FCStd declara um manifesto coerente. IDs trocados e alteração de quantidade/unidade do planejamento são recusados. O grupo FreeCAD pode expor Shape agregada: é excluído da contagem para não duplicar todas as peças.

Volume/área são derivados geométricos **declarados pelo CAD**, somados uma vez por componente. O servidor valida a estrutura e cobertura das faces, mas não recalcula BRep nem autentica a autoria de JSON arbitrário. O delta compara o volume ao abrir o FCStd **antes da edição feita pelo job**. Se o arquivo já voltou editado e `editar={}`, há volume atual, sem comparação anterior: não apresentar delta zero como mudança entre publicações.

Quantidade contratual OAE3-SUE permanece **3 un**; executado, avanço, cronograma e previsões de referência ficam preservados. Espessura ou volume de um componente não determinam automaticamente unidades contratuais, produtividade ou duração. A ficha 4D/timeline continuam da referência; a ficha CAD e a tabela federada distinguem os dados retornados.

## Reexecutar sem sobrescrever

`scripts/infra4d/interop_freecad_retorno.py` recebe job JSON por `INFRA4D_FREECAD_JOB`. Exemplos reais: `job-existente.json`, `job-detalhada.json`, `job-final.json`. Use destino **novo**; os destinos existentes são recusados. O runner usa `runpy.run_path(..., run_name='__main__')`. Para retornar um FCStd já editado, aponte `fonte_fcstd` ao arquivo novo e use `editar={}`. Não é necessário repetir o gerador original.

`freecadcmd` pode encerrar com código zero apesar de exceção Python: aceite exige `prova-retorno.json` com `status=pass`, hashes conferidos e provas API/navegador. Preserve o log de falhas; a primeira tentativa encontrou a Shape do grupo, foi corrigida e ganhou regressão própria.

## Verificações e pacote desta onda

Bateria final Python: **289 PASS, 6 SKIP**, exit 0, 50,14 s. Chrome **43 PASS focados**; Edge **231 PASS completos**, sem falhas. API validou três retornos reais, incluindo `retorno-sem-edicao/`, que reabriu o FCStd já editado e retornou o volume atual sem delta anterior inventado. Não foi repetida a suíte pytest completa nem validado commit isolado. Detectores de IDs/manifesto acusaram duas falhas esperadas em subprocesso com guardas desativadas só em memória; fonte intacta, guardas reais com 15 PASS.

Pacote local `output/releases/infra4d-oae196-20261114.zip`, acompanhado de SHA-256; dentro dele, base original, guia, modelos, provas nativas/API, capturas e resultados. Não inclui o aplicativo FreeCAD ou Blender. Proteção local das fontes em `output/protecao/freecad-oae-retorno-verificado-20261114/`; nenhum snapshot anterior foi substituído. A tentativa parcial sem sufixo `verificado` não é a proteção final; consulte o STATE.

Os dois avisos permanecem: segurança com um contato institucional no histórico Git (0 ALTA/1 MEDIA, scanner exit 1; cobertura parcial no relatório) e autoria Three.js sem declaração no registry (ownership WARN). `eos check` continua L1/AT_RISK: remoto, backup canônico e recuperação não certificados. Os arquivos locais não são autorização para apagar o clone/sessão ou mudar de máquina.

### Avaliação do próximo fluxo

Blender já disponível é a opção de menor risco para apresentação dos mesmos componentes, sem instalar outro aplicativo; deve conservar IDs por peça e agrupar corretamente por atividade no retorno GLB. O fluxo Blender anterior já abriu/editou/salvou/reabriu BLEND e retornou GLB/JSON, mas **não representa esta OAE196**. Bonsai/IFC 4.3 é outra validação. ProjectLibre requer provar leitura/escrita do arquivo nativo e preservar o contrato CPM antes de ser chamado integração. QGIS já tem retorno oficial comprovado e agrega mais valor para contexto territorial que para editar sólidos.

Prioridade remanescente: observação GUI da OAE no FreeCAD; revisão de engenheiro; depois ampliar a interoperabilidade. Não chamar simples exportação de homologação.
