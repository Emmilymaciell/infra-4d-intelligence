# R06 — Premissas da rodovia fictícia (BR-FIC 999)

> Caso sintético 2 (`scripts/infra4d/dados_sinteticos_rodovia.py`, premissas `P-2026.11-rod-a`, semente 20261113).
> Ordem de grandeza, sem fonte conferida: tudo é **[OG]**. Base: R03 §5. Verificar contra DNIT-ES e SICRO antes de dado real.

| Item | Valor no caso | Faixa [OG] |
|---|---|---|
| Obra | duplicação, 48 km, 3 lotes × 4 segmentos de 4 km; pista nova 7,2 m + acostamentos 2 × 2,5 m | plataforma duplicada 25–35 m |
| Supressão | 3,5 ha/km; 2,0 ha/equipe·dia | faixa de 30–40 m |
| Terraplenagem | 60.000 m³/km; 2.200 m³/equipe·dia × 2 frotas | mesmas frotas da ferrovia (R03) |
| Drenagem (bueiros + dispositivos) | 320 m/km; 30 m/dia | — |
| Reforço/sub-base granular | 2.600 m³/km (≈0,20 m × 13 m); 650 m³/dia | sub-base 15–20 cm; 500–1.500 m³/dia |
| Base BGS | 2.200 m³/km (≈0,18 m × 12 m); 600 m³/dia | base 15–20 cm; 500–1.500 m³/dia |
| Imprimação | 12.200 m²/km; 9.000 m²/dia | distribuidor 8.000–15.000 m²/dia |
| CBUQ (binder + capa) | 2.000 t/km; 650 t/dia | usina de 80–200 t/h → 500–1.500 t/dia |
| Sinalização horizontal | 3.000 m de faixa/km; 4.000 m/dia | — |
| Sinalização vertical | 6 placas/km; 3/dia | — |
| Defensas metálicas | 250 m/km; 100 m/dia | — |
| OAEs | 3 (4–6 vãos); estacas 2/dia, meso 0,12 un/dia, super 0,10 vão/dia | iguais à ferrovia |

**Lógica (por segmento):** SUP→TER SS5; TER→DRE SS10/FF5; TER→SBB SS15/FF5; DRE→SBB SS10; SBB→BGS SS5/FF2;
BGS→IMP SS3/FF1; IMP→CBU SS3/FF2 (cura da imprimação, ~72 h); CBU→SHV FS5 (cura antes da pintura definitiva);
CBU→SVV e CBU→DEF SS5. Frente única por lote em todos os serviços (FS entre segmentos). OAE: SUP→FUN SS10,
FUN→MES→SUE FS, SUE→CBU do segmento FS10 (lajes de aproximação antes do pavimento).

**Usina central compartilhada (L2 e L3):** recurso único modelado por lógica, `L2-S04-CBU → L3-S01-CBU FS3`.
É a premissa da narrativa: o CBUQ do L2 rende 60% do planejado (fator simulado) e empurra o L3.

**Calendários:** CAL-TERRA perde chuva (nov–mar ~30% dos dias; out/abr ~12%). CAL-PAV (imprimação, CBUQ, pintura)
perde os mesmos dias **e** o dia seguinte em ~60% dos casos (superfície úmida). BGS, placas, defensas e OAEs: CAL-OBRA.
Todos 6×1 com feriados nacionais fixos.

**Restrições (SNET, sintéticas):** LI do L3 (+70 d); desapropriação km 20–24 (+140 d); jazida do L1 (+150 d);
usina do L1 (+260 d); usina central (+300 d); defensas do L3 (+400 d, **pendente** na data de status).

**Limitações:** sem restauração da pista existente, sem desvio de tráfego, sem acostamento separado do CBUQ;
usina compartilhada é lógica e não nivelamento de recurso; fatores de desempenho escolhidos à mão para a demo.

## Terraplenagem e diagrama de massas (`scripts/infra4d/massas.py`)

Método: **diagrama de massas de Brückner**, por conhecimento técnico geral de projeto de terraplenagem.
Nenhuma fonte foi verificada nesta rodada; conferir no Manual de Implantação Básica / projeto de terraplenagem
do DNIT antes de usar com dado real. Tudo **[OG]**:

| Premissa | Valor |
|---|---|
| Seção-tipo | terreno transversal plano, plataforma de 12 m (ferrovia) ou 13 m (rodovia), taludes 1(V):1,5(H) em corte e aterro, sem seção mista |
| Área | `|h|·(L + n·|h|)`, com `h = greide − terreno` (h > 0 é aterro) |
| Volume | média das áreas entre estacas de 20 m (`passo_m` configurável); intervalo com passagem corte/aterro dividido no ponto de passagem, com compensação local min(Vc, Fh·Va) a DMT (d1+d2)/3 (revisão r9) |
| Homogeneização | Fh = 1,25: aterro × Fh = corte equivalente. Empolamento de 25% só no volume solto de bota-fora |
| Brückner | `O = Σ(Vc − Fh·Va)`. A linha de compensação é horizontal em O = 0. Cada onda é um trecho compensado (volume = pico, DMT = área ÷ volume). A ponta final aberta vira bota-fora ou empréstimo |
| Conservação | volume da onda = soma das subidas da ordenada (não o pico; revisão r9): corte = compensado + bota-fora e Fh·aterro = compensado + empréstimo, verificados em teste |
| Terreno | **SINTÉTICO**: greide − (−0,3 m + 4,5·sen(2πkm/1,7) + 1,8·sen(2πkm/0,45 + 1,1)). O deslocamento de 0,3 m deixa o greide ≈ compensado |

Confronto com o dataset (`/api/massas/coerencia`): corte + aterro geométrico por segmento contra o `quantidade_total`
da atividade TER. Resultado no beta:
- **rodovia:** 6% abaixo, 12 de 12 segmentos dentro de ±20%;
- **ferrovia:** cerca de 23% abaixo em todos os segmentos. A premissa de 70.000 m³/km do R03 pede uma seção ou um
  terreno mais severos que os sintéticos.

O dataset não é alterado: o relatório só aponta a diferença.
