# Demonstração pública — ferrovia fictícia, variante visual vNext

O roteiro congelado continua em `docs/DEMO-5-MINUTOS.md`. Esta variante acrescenta apresentação local 1:1 e
retorno de autoria externa, preservando os números e os cálculos da referência. **100% fictício.** Não é projeto
executivo, dimensionamento estrutural nem comprovação de desempenho em uma obra real.

## Preparar

```powershell
.\run-beta.ps1
```

Abra `http://127.0.0.1:8765/` na ferrovia e limpe a simulação. Mantenha o terminal aberto. O sistema não exige
internet para servir seus arquivos locais. A preparação inicial e os testes de IFC com exemplos externos podem
precisar de downloads; não faça a preparação durante a reunião.

## Cinco minutos

| Tempo | Ação | Mensagem |
|---|---|---|
| 0:00–0:45 | Apresentação e Painel | Ferrovia fictícia de 60 km, 3 lotes, 113 atividades. Construtora fictícia: 23/07/2027; independente: 09/09/2027, 48 dias depois. Produtividade medida nos boletins alimenta o CPM próprio. |
| 0:45–1:45 | Modelo 3D/4D → Experiência → Apresentação → Detalhe da ponte → Modo reunião | Terreno, via e OAE ilustrativos. A geometria de detalhe está ligada às atividades; a timeline usa o cálculo da API. Mova a data até o fim para mostrar a configuração futura e volte à data de status para distinguir executado de remanescente. |
| 1:45–2:15 | Experiência → Análise 4D; selecionar uma peça | Cores mostram avanço na data escolhida. Contorno vermelho significa criticidade; atraso é outra informação, no modo Desvio vs linha de base. A ficha traz quantidade, saldo, calendário e memória de produtividade. |
| 2:15–3:15 | Simulação → exemplo terraplenagem L3-S04 a 1.500 m³/equipe·dia | Término passa a 06/10/2027: +27 dias. O efeito é propagado pela rede e explicado. |
| 3:15–3:45 | Exemplo lastro L2-S04 a 250 m³/equipe·dia | Atividade com folga: +0 dias no término. Limpar simulação. |
| 3:45–4:30 | Linha de balanço; Modelo 3D/4D → Revisões federadas | Oito conflitos previstos. Mostrar o pacote editável no aplicativo disponível e a revisão retornada, se o teste real deste pacote tiver sido concluído. |
| 4:30–5:00 | Relatório técnico | O relatório usa o mesmo motor. Explicar responsabilidades: projetista entrega modelos e IDs; construtora fornece cronograma/rede e boletins; a equipe 4D concilia, calcula independentemente e reporta. |

## Retorno de QGIS e Blender (desvio de dois minutos)

1. Expanda **Revisões federadas**. Selecione a base original e o GeoJSON retornado pelo aplicativo.
2. Clique **Conferir revisão**. Leia IDs preservados, mudanças, quantidades explícitas e término calculado da cópia.
3. **QGIS:** magenta é marcador da linha revisada, elevado apenas para legibilidade; não é malha executiva.
4. **Blender:** quando o retorno contém `geometria_local_m`, a web transforma os vértices e a `matrix_world`
   extraídos do `.blend` reaberto, em metros e sem exagero. São caixas autoráveis ilustrativas por atividade,
   não componentes paramétricos Bonsai. O GLB exportado pode ser carregado separadamente e conferido contra
   os IDs e a caixa da revisão. A alteração de espessura não altera automaticamente o quantitativo de planejamento.
5. Selecione uma mudança. A ficha compartilhada mostra a referência; o painel federado mostra os números e datas
   da revisão. **Timeline e cores de avanço continuam da referência.**
6. Clique **Publicar revisão isolada** somente após conferir a prévia. Nada sobrescreve o dataset da demonstração.
   O acervo é em memória e desaparece ao reiniciar o beta: preserve os arquivos nativos e de intercâmbio.

## Limites a dizer espontaneamente

- Todos os dados, custos, posições geográficas e objetos são fictícios; a OAE não foi dimensionada.
- O visual natural é um modo de apresentação. O estado 4D vem da API; terreno, água e vegetação não fornecem quantidades.
- GLB é malha de visualização editável no Blender; não comprova IFC paramétrico, Bonsai ou compatibilidade Autodesk.
- Abertura, edição e salvamento por APIs oficiais em background são provas diferentes de operação manual na GUI.
- Nenhum arquivo corporativo do Programa integra este material. Nenhum piloto do Programa está autorizado por esta demonstração.
- Não há homologação Primavera P6/MS Project nem uso multiusuário. Não prometer sincronização bidirecional automática.

## Evidências desta rodada

As capturas e resultados finais são registrados em `output/demo/vNext-2026-11-13/` e copiados ao pacote
`output/releases/demo-ferrovia-vNext/09-evidencias/`. O vídeo de reserva em `10-demo/` é uma montagem de
capturas reais, identificada como tal; não é gravação contínua da tela. Consulte a matriz de interoperabilidade
e o STATE para o resultado executado mais recente. Evidências não são versionadas no Git.
