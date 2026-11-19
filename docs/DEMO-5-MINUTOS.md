# Demonstração de 5 minutos — INFRA 4D INTELLIGENCE (beta)

> Extensão opcional da demonstração: a [OAE196 editável no FreeCAD](interop/FREECAD-OAE-RETORNO.md)
> já retorna ao visualizador com seleção por peça, materiais e ambiente ilustrativo.
> O guia contém os caminhos exatos de base/retorno/FCStd. Mostrar esse fluxo depois
> do roteiro preserva os números abaixo. A GUI FreeCAD ainda exige observação manual.

> Versão curta do roteiro completo `docs/DEMO-PESSOA-A.md`. Os números citados aqui saem do mesmo sistema e estão
> no roteiro completo, onde `tests/test_roteiro_demo.py` os confere automaticamente. Se a tela mostrar outro valor,
> **vale o da tela**: rode a suíte e veja qual teste falhou.
> **Todos os dados são FICTÍCIOS.** Diga isso na primeira frase.

## Antes de começar (2 minutos, uma vez)

```powershell
cd C:\caminho\exemplo\infra-4d-intelligence
.\run-beta.ps1
```

1. Abra **http://127.0.0.1:8765/** no Chrome ou no Edge. Use tela cheia (F11) e zoom de 90% se a tela for pequena.
2. No seletor **Obra** (topo), confira se está em **Ferrovia Fictícia Vale do Sintético**.
3. Na aba **Simulação**, se o botão **Limpar simulação** estiver ativo, clique nele. A demo começa sem simulação.
4. Deixe a janela do PowerShell aberta: fechar a janela encerra o beta.

Plano B, se algo falhar ao vivo: o botão **▶ Apresentação guiada** (topo) executa sozinho uma sequência parecida e
lê os números da API.

## Roteiro (5 minutos)

| Tempo | Onde clicar | O que selecionar/fazer | O que dizer |
|---|---|---|---|
| 0:00–0:30 | aba **Apresentação** | nada | "Ferrovia fictícia de 60 km, 3 lotes e 113 atividades, com data de status 09/11/2026. Todos os dados são fictícios. A pergunta é: **quando a obra termina de verdade?**" |
| 0:30–1:30 | aba **Painel** | ler os cartões de término e o primeiro alerta | "A construtora prevê **23/07/2027**. Recalculando com a produtividade **medida** nos boletins, o término vai para **09/09/2027**: **48 dias depois**. A causa aparece no alerta: a terraplenagem L3-S03 é crítica e produz **78% do planejado**." |
| 1:30–2:15 | aba **Modelo 3D/4D** | arrastar a **linha do tempo** da esquerda para a direita; clicar numa peça contornada em vermelho | "Cada peça está ligada a uma atividade. A cor mostra o estado na data: não iniciado, em execução, concluído. As contornadas em vermelho são as **10 atividades críticas**. Clicar na peça seleciona a atividade no cronograma." |
| 2:15–3:30 | aba **Simulação** | em **Atalhos de demonstração**, clicar em **"Exemplo: terraplenagem L3-S04 (crítica) a 1.500 m³/equipe·dia"** | "Se essa frente crítica render 1.500 m³ por equipe·dia, o término vai de 09/09 para **06/10/2027: +27 dias**. A tela mostra a conta e quais atividades empurraram a data." |
| 3:30–4:00 | aba **Simulação** | clicar em **"Exemplo: lastro L2-S04 (com folga) a 250 m³/equipe·dia"** | "Já o lastro do L2 tem folga: piorar a produtividade dele **não muda o término (+0)**. Isto é gerir pelo caminho crítico, não pelo percentual." |
| 4:00–4:30 | aba **Linha de balanço** | apontar os "!" no gráfico | "Tempo × km. Os **8 '!'** são frentes que vão se encontrar a menos de 1 km. O sistema calcula onde e quando." |
| 4:30–5:00 | aba **Simulação** → **Limpar simulação**; depois o botão **Relatório técnico** (topo) | mostrar o relatório que abre em outra aba | "Tudo isso vira um relatório imprimível, gerado do mesmo motor. Próximo passo: rodar com o cronograma e os boletins **reais** de uma obra." |

## Perguntas prováveis (respostas curtas)

- **"Isso abre no Primavera ou no Project?"** "Exporta e importa XER e MS Project XML, e a ida e volta no próprio
  sistema dá as mesmas datas. Ainda **não** foi aberto num P6 ou num Project reais."
- **"E o BIM?"** "Exporta IFC 4.3 com alinhamento, peças posicionadas pelo eixo e o cronograma dentro do arquivo.
  Ainda não lemos IFC de cliente."
- **"A previsão acerta?"** "Num teste contra um 'futuro' sintético, a previsão independente errou bem menos que a da
  construtora (roteiro completo, D6). Isso mede o método num mundo inventado; a prova de verdade é com dado real."
- **"Quantas pessoas usam?"** "Hoje roda numa máquina, sem login. É um beta para validar a ideia."

## O que NÃO mostrar nesta versão

- Dados reais (não existem).
- Abertura em software comercial (não testada).
- A tendência de marcos da ferrovia: a divergência aparece já nas primeiras semanas, com pouco dado, e parece
  artefato (auditoria R14).
- O backtest do lote 2 da rodovia: o erro é alto e não serve de vitrine (R14).

## Capturas e vídeo desta versão

Em `output/demo/2026-11-13/`, fora do Git por regra do `.gitignore`. O destino das evidências pelo Ambient OS é o
Drive: armazenamento externo (fora do Git) (ADR-0015 da plataforma). Copie a pasta para lá
se quiser guardá-la.
