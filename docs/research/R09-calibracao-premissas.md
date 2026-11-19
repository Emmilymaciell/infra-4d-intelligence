# R09 — Calibração das premissas de engenharia (risco RK5)

> Data: **2026-11-12**. Objetivo: confrontar as premissas **[OG]** que os geradores e os módulos usam com fontes
> públicas. As premissas vêm de `scripts/infra4d/dados_sinteticos.py`, `dados_sinteticos_rodovia.py`, `massas.py`
> e `produtividade_terraplenagem.py`, lidas nesta rodada.
> Convenção: **[V]** = número visto nesta rodada em documento oficial ou primário (URL citada); **[B]** = visto em
> resumo de busca ou em réplica de terceiros (ex.: Orçamentor, que reproduz o SICRO); **[NV]** = não verificado.
> **SICRO:** só cito número e código. A base é CC BY-ND 3.0 (R05 §5) e não foi copiada. Os valores de composição
> vieram do Orçamentor (referência 202604, SP) e **precisam ser conferidos na base oficial**. Os manuais do SICRO
> estão no gov.br em `.7z` (inclusive o **Volume 04 — Fator de Influência de Chuvas**), e não há ferramenta de
> descompactação nesta máquina: não foram abertos.
> **Unidade de tempo da "produção da equipe" do SICRO:** a página não diz. Inferi que é **por hora** pela coerência
> custo horário ÷ produção. Na composição 5502165: custo horário de execução R$ 1.705,65 ÷ 230,19 m³ = R$ 7,41/m³,
> perto do custo unitário de R$ 7,93/m³ [B]. Para comparar com as premissas (por equipe·dia), multipliquei por
> **8 h** (`ParametrosFrota.horas_dia`). Com 9–10 h o dia rende 12–25% a mais.
> Nada foi alterado nos geradores nem nos datasets. As recomendações estão na §6, para o backlog.

## 1. Produtividades por equipe (un/equipe·dia)

| Serviço (obra) | Valor usado | Referência encontrada | Fonte | Veredito | Recomendação |
|---|---|---|---|---|---|
| **TER** terraplenagem (ferrovia 2.400; rodovia 2.200 m³ TER/equipe·dia; 2 equipes) | 2.400 / 2.200 (m³ de corte + aterro, ver nota) | SICRO 5502165: escavação, carga e transporte de 1ª categoria, DMT 800–1.000 m, 1 escavadeira de 1,56 m³ + **4** caminhões de 14 m³ = **230,19 m³/h** → ≈ **1.840 m³/dia** (8 h) de material escavado [B] | https://orcamentor.com/sicro/composicoes/5502165/ | **Dentro da ordem de grandeza, sem comparação direta.** Nosso número é por m³ de **corte + aterro** (definição de `massas.coerencia`); o SICRO é por m³ escavado e transportado. Em m³ de corte, nossa frota modelada (`producao_frota`, DMT 900 m) dá **1.246 m³/dia**, ≈ 0,68× a referência SICRO por dia | Declarar a unidade (TER = corte + aterro) no dataset; calibrar a frota (§3) e comparar em m³ de corte |
| **SUB** sublastro (ferrovia) | 650 m³ | Nenhuma composição SICRO de sublastro achada; INFRA S.A. tem especificação de sublastro (não aberta) [NV] | https://www.infrasa.gov.br/wp-content/uploads/2023/11/80_ES_028A_20_8010_R01_Sub_Lastro.pdf | **Sem fonte** | Buscar a composição SICRO de sublastro na base oficial |
| **DOR** distribuição de dormentes (ferrovia) | 1.400 un ≈ 0,84 km/dia | Projetos brasileiros reportam **~1 km/dia** de dormente + trilho (Norte-Sul, FMT) [B, notícia] | https://en.clickpetroleoegas.com.br/the-ferrovia-norte-sul-the-logistical-backbone-of-brazil-dragged-on-for-more-than-four-decades-has-finally-reached-73-physical-completion-no-davila/ · https://datamarnews.com/?p=65915 | **Dentro** | Manter |
| **GRA** assentamento de grade (ferrovia) | **0,45 km/dia** | Máquina de construção de via: **1,5 km/dia** em operação contínua (Harsco, fornecedor) [B]; recorde de **1,69 km/dia** na Transnordestina [B, notícia]; **~1 km/dia** de ritmo na Norte-Sul e na FMT [B, notícia] | https://harscorail.com/equipment/track-construction-and-renewal/new-track-construction · https://en.clickpetroleoegas.com.br/transnordestina-sets-record-by-installing-169-km-of-tracks-in-a-single-day-reaches-81-completion-and-plans-to-deliver-an-additional-100-km-o-mhbb01/ | **Fora para mecanizado** (0,3–0,5× a referência); dentro só para grade manual ou semimecanizada (faixa [OG] do R03: 0,3–0,8) | Declarar o MÉTODO no dataset. Se for mecanizado, usar 1,0 km/dia (ver §5, efeito na narrativa) |
| **LAS** lastro, levante e socaria (ferrovia) | 560 m³ | SICRO 3009091, lastro com caminhão: **25,46 m³/h** ≈ 204 m³/dia [B] (R04); SICRO 2607206, lastro mecânico em AMV: **133,85 m³/h** ≈ 1.070 m³/dia [B]; socadora 09-32 CSM: **~1.600 m/h nominais** (CIFI) [B]; R03 [OG], trem hopper: 1.000–3.000 m³/dia | https://orcamentor.com/sicro/composicoes/3009091/ · https://orcamentor.com/sicro/composicoes/2607206/ · https://cifi.it/UplDocumenti/bologna30102014/02%20-%203%20decenni%20di%20rincalzatura%20a%20ciclo%20continuo.pdf | **Dentro** da faixa entre o caminhão e o mecânico, mas o método não está declarado. A socadora não limita: 1,6 km/h ≫ 0,28 km/dia equivalentes | Declarar o método (caminhão × hopper) e separar descarga de socaria se o cronograma real separar |
| **SOL** solda aluminotérmica (ferrovia) | 6,0 soldas | SICRO 3009323, TR-68, cadinho descartável, 1 soldador + 2 trabalhadores de via: **0,82 un/h** ≈ **6,6 soldas/dia** [B] | https://orcamentor.com/sicro/composicoes/3009323/ | **Dentro** (0,91×) | Manter |
| **BGS** base de brita graduada (rodovia) | 600 m³ | SICRO 4011276, BGS com brita comercial: **113,18 m³/h** ≈ **905 m³/dia** [B] | https://orcamentor.com/sicro/composicoes/4011276/ | **Abaixo** (0,66×): conservador | Opcional: subir para ~800–900 m³, ou declarar que o limite é a usina de solos |
| **IMP** imprimação (rodovia) | 9.000 m² | SICRO 4011352, imprimação com emulsão: **1.038,46 m²/h** ≈ **8.300 m²/dia** [B] | https://orcamentor.com/sicro/composicoes/4011352/ | **Dentro** (1,08×) | Manter |
| **CBU** CBUQ (rodovia) | 650 t | SICRO 4011464 (faixa C-12,5) e 6416247 (asfalto polímero, faixa C): usinagem de **99,60 t/h** ≈ **800 t/dia** [B]; o SICRO lista usina gravimétrica de **100/140 t/h** (6416217) [B]; o dataset declara usina de 120 t/h | https://orcamentor.com/sicro/composicoes/4011464/ · https://orcamentor.com/sicro/composicoes/6416217/ | **Dentro** (0,82×) | Manter. O fator 0,60 do L2 (narrativa da usina limitada) fica em ~390 t/dia, o que é plausível como cenário |
| SUP, DRE, SBB, SHV, SVV, DEF | 2,0 ha; 35/30 m; 650 m³; 4.000 m; 3 un; 100 m | Não pesquisado nesta rodada | — | **Sem fonte** | Próxima rodada, mesmo método |

## 2. Quantitativos por km

| Item | Valor usado | Referência | Fonte | Veredito | Recomendação |
|---|---|---|---|---|---|
| Dormentes (ferrovia) | 1.667 un/km (espaçamento 0,60 m) | Espaçamento de **600 mm** entre eixos (especificação INFRA S.A.) e **60 cm** em vias principais (procedimento INFRA S.A. de superelevação) [B] | https://infrasa.gov.br/wp-content/uploads/2023/11/80-ES-000F-11-8006.pdf · https://infrasa.gov.br/wp-content/uploads/2024/02/PRO_00019_Superelevacao_em_Curvas_Ferroviarias.pdf | **Dentro** | Manter |
| Trilho TR-68, bitola larga | 1 km de grade = 2 filas | Bitola larga no Brasil = 1,600 m (glossário do Ministério dos Transportes) [B] | https://www.gov.br/transportes/pt-br/centrais-de-conteudo/glossariotermosferroviarios.pdf | Coerente | — |
| Soldas por km | 8,4 un/km | Faixa [OG] do R03: 6–10. Fonte pública não encontrada | — | **Sem fonte** | Derivar do comprimento da barra fornecida (ex.: 240 m → ~8,3 soldas/km por fila; [NV]) |
| Lastro (ferrovia) | 2.000 m³/km | Lastro com espessura **mínima de 300 mm** abaixo do dormente (especificação INFRA S.A.) [B]; **ombro mínimo de 30 cm** em trilho longo soldado (ISF-212) [B]. Volume por km não achado | https://infrasa.gov.br/wp-content/uploads/2023/11/80-ES-000F-11-8006.pdf · https://www.gov.br/dnit/pt-br/ferrovias/instrucoes-e-procedimentos/instrucoes-de-servicos-ferroviarios/isf-212-projeto-de-superestrutura-da-via-permanente-lastro-e-sublastro.pdf | **Sem fonte direta** (geometria compatível com [OG]) | Calcular a seção-tipo a partir da ISF-212 (espessura por classe) e do dormente |
| Sublastro (ferrovia) | 2.200 m³/km | ISF-212 dimensiona lastro e sublastro pela pressão admissível do subleito [B]; espessura não extraída | ISF-212 (acima) | **Sem fonte** | Idem |
| **TER (ferrovia)** | **70.000 m³/km** | **`massas.coerencia`, executado no beta: o terreno sintético dá ~23% a menos em todos os segmentos** (R06). R03 [OG]: 40.000–150.000 de corte por km. Nenhuma fonte pública dá volume por km (depende do relevo) | R06 §massas (interno) | **Fora do próprio terreno sintético** (incoerência interna, não de mercado) | Ver §5: alinhar a quantidade ao terreno (~54.000 m³/km) ou o terreno à quantidade |
| TER (rodovia) | 60.000 m³/km | Coerência −6%, 12 de 12 segmentos dentro de ±20% (R06) | interno | Coerente | Manter |
| Camadas de pavimento (rodovia) | IMP 12.200 m²/km; BGS 2.200 m³/km; SBB 2.600 m³/km; CBU 2.000 t/km | Pela geometria declarada (12,2–13 m de largura): BGS ≈ 17–18 cm, SBB ≈ 20 cm, CBUQ ≈ 6,8 cm **se a densidade for 2,4 t/m³ [NV]**. Taxa de imprimação usual de 0,8–1,6 l/m² [B] (não afeta a área). Espessuras das normas DNIT 031 (CBUQ, versão 2024 citada por terceiros) e DNIT 141 (BGS) **não extraídas** (certificado inválido ou 404) | https://orse.cehop.se.gov.br/esp/ES00195.pdf · https://www.gov.br/dnit/pt-br/assuntos/planejamento-e-pesquisa/ipr/coletanea-de-normas/coletanea-de-normas/especificacao-de-servico-es/dnit144_2014_es.pdf | **Sem fonte** para espessuras (coerentes com pavimento flexível comum) | Na Fase 3, tirar do projeto de pavimento da obra real |

## 3. Parâmetros de frota (`ParametrosFrota`) e terraplenagem (`massas.py`)

| Parâmetro | Valor usado | Referência | Fonte | Veredito | Recomendação |
|---|---|---|---|---|---|
| **Eficiência** | **0,70** (~42 min/h) | SICRO: **0,83** (50 min/60 min) para obras de construção, ajustado pelo FIT (módulo ENAP sobre o Manual de Custos, edição 2017) [B]. A 2ª edição do manual é de 17/11/2025 e o valor precisa ser confirmado nela | https://bibliotecadigital.enap.gov.br/bitstream/1/7644/3/M%c3%b3dulo%202%20-%20Composi%c3%a7%c3%a3o%20de%20Custos.pdf · https://agenciainfra.com/blog/wp-content/uploads/2026/10/038.123-2020-7-BZ-inspecao_Dnit_Sicro.pdf | **Fora** (0,84× do SICRO): pessimista | Usar 0,83 como padrão e manter 0,70 como cenário |
| Caçamba da escavadeira | 2,0 m³ | SICRO 5502165 usa escavadeira de **1,56 m³** (118 kW) [B] | https://orcamentor.com/sicro/composicoes/5502165/ | Diferente (equipamento maior que o da composição) | Declarar o modelo de equipamento; 2,0 m³ é plausível para uma de 35 t [NV] |
| Caminhões | 8 × 10 m³ (solto) | SICRO 5502165: **4 × 14 m³** para DMT 800–1.000 m [B] | idem | **Superdimensionado** para DMT curta: no nosso modelo a escavadeira limita até DMT ~1,5 km (calculado com `producao_frota`) | Dimensionar n pela DMT (como no SICRO) ou declarar a frota fixa |
| Ciclo da escavadeira | 22 s | Não encontrado | — | **Sem fonte** | — |
| Velocidades (carregado / vazio) | 15 / 25 km/h | O SICRO separa as composições de transporte por tipo de caminho (leito natural, revestimento primário, pavimentado) [B]; velocidades não encontradas (estão no Manual de Custos, em `.7z`) | https://bibliotecadigital.enap.gov.br/bitstream/1/7644/3/M%c3%b3dulo%202%20-%20Composi%c3%a7%c3%a3o%20de%20Custos.pdf | **Sem fonte** | Abrir o Volume 01 do manual SICRO (ver BACKLOG) |
| Empolamento | 0,25 | Caderno da SUDECAP/PBH: fator médio de conversão de **1,18** (18%) para quantitativos de projeto; o empolamento já está embutido nas composições de terraplenagem [B] | https://prefeitura.pbh.gov.br/sites/default/files/estrutura-de-governo/sudecap/normas-padroes/VA-CADERNO/Capitulo03/CAP03-25-07-31.pdf | **Acima** de uma referência municipal; depende do solo | Manter 0,25 como premissa declarada; **não somar empolamento a volumes medidos** (risco de dupla contagem apontado pela SUDECAP) |
| Fator de homogeneização (Fh) | **1,25** (aterro × Fh = corte equivalente) | DNIT, Ofício Circular 3959/2025: Fh = **0,80 para rocha de 3ª categoria**, "valor referencial utilizado no SICRO, obtido a partir da Tabela 2 do Manual de Custos de Infraestrutura de Transportes, Volume 1", aplicado como V_aterro = V_corte ÷ Fh (27.000 / 0,80 = 33.750 m³) [V]. **Mesma definição** do nosso Fh (corte/aterro). O valor para solo de 1ª categoria está na Tabela 2 (não aberta) [NV] | https://www.gov.br/dnit/pt-br/assuntos/planejamento-e-pesquisa/desenvolvimento-e-projetos/referencias-tecnicas/sei_21475158_oficio_circular_3959.pdf | Definição **confirmada**; valor de solo **sem fonte** | Ler a Tabela 2 do Volume 01 do SICRO e usar o Fh por categoria de material |
| DMT externa (empréstimo / bota-fora) | 3.000 m | Projeto-dependente | — | Sem fonte (por natureza) | Parâmetro de obra, não premissa geral |
| Seção-tipo | plataforma de 12 m (ferrovia) e 13 m (rodovia), taludes 1:1,5 | Não pesquisado | — | Sem fonte | Do projeto geométrico real |

## 4. Chuva

| Premissa | Valor usado | Referência | Fonte | Veredito | Recomendação |
|---|---|---|---|---|---|
| Ferrovia: dia perdido por chuva | dez–mar, p = 0,33 por dia (~10 dias/mês) | Brasília (estação 83377): normal 1991–2020 de **206,0 mm em janeiro** e **621,7 mm no verão** [B]. Contagens de dias com chuva ≥ 1 mm só para anos isolados: **23 dias** em jan/2023 (Brasília); **20** em fev/2024 e **14** em mar/2024 (Goiânia) [B]. **A normal de nº de dias de chuva não foi obtida** (as planilhas do INMET não abriram nesta rodada) | https://portal.inmet.gov.br/servicos/normais-climatológicas · https://portal.inmet.gov.br/noticias/balan%C3%A7o-bras%C3%ADlia-registrou-chuvas-acima-da-m%C3%A9dia-em-janeiro | **Sem fonte** para "dia PERDIDO". Dia com chuva ≥ 1 mm (15–23/mês nos exemplos) não é dia perdido | Usar o **Fator de Influência de Chuvas (FIC) do SICRO, Volume 04**, por UF e mês (é o referencial do DNIT); a UFT critica a média mensal estadual [B]: https://core.ac.uk/download/289275568.pdf |
| Rodovia: chuva | nov–mar p = 0,30; out/abr p = 0,12; pavimentação perde o dia seguinte em 60% dos casos | Idem. A restrição de não executar CBUQ com chuva está na DNIT 031 [NV, PDF não aberto] | — | **Sem fonte** | Idem; manter o "dia úmido" como premissa declarada |
| Regime (Centro-Oeste, out–abr) | sazonal | Normais do INMET 1991–2020 publicadas [B] | https://portal.inmet.gov.br/servicos/normais-climatológicas | Coerente em forma; intensidade sem fonte | — |

## 5. O que muda materialmente a narrativa da demo

1. **TER da ferrovia (70.000 m³/km × terreno sintético ≈ 54.000).** É incoerência **interna**, achada pelo próprio
   `massas.coerencia`, e não um desvio de mercado. Hoje a cadeia crítica é a terraplenagem L3-S03/S04 (STATE). Ao
   baixar a quantidade de TER em ~23%, a duração de TER cai na mesma proporção e o término independente da ferrovia
   **antecipa**; o caminho crítico pode migrar para via permanente ou OAE.
   - Alternativa que preserva a narrativa: tornar o terreno mais severo (amplitude) até a coerência ficar em ±20%.
   - Antes de escolher, rodar os dois cenários e comparar término e caminho crítico. Isso não foi feito nesta
     rodada, porque os geradores não podem ser alterados.
2. **Grade (0,45 km/dia)** é método manual. Projetos brasileiros reportam ~1 km/dia, e máquinas, 1,5 km/dia. Se o
   método declarado for mecanizado, a via permanente encurta. Sem efeito no término se TER continuar crítico (a
   conferir; o L3 também tem a restrição do trilho em trânsito).
3. **Eficiência da frota 0,70 × 0,83 do SICRO.** A produtividade pela DMT (`/api/produtividade/terraplenagem`)
   recomenda números ~16% mais baixos que o referencial do DNIT. Na demo, a frase precisa ser "premissa
   conservadora" ou mudar o padrão.
4. **Chuva:** o modelo de dias perdidos não tem fonte. O referencial correto existe (FIC, Volume 04 do SICRO).
   Enquanto não for aplicado, a tela deve dizer "chuva sintética".
5. **O que segue calibrado:** solda (6,0 contra ≈6,6/dia), imprimação (9.000 contra ≈8.300 m²/dia), CBUQ (650
   contra ≈800 t/dia), dormentes (1.667/km, espaçamento de 0,60 m) e distribuição de dormentes (~0,84 contra ~1
   km/dia). Isso pode ser dito na demo como "ordem de grandeza conferida com referências públicas (SICRO via
   réplica, especificações INFRA S.A.)", com a ressalva de que as composições foram vistas numa réplica de
   terceiros.

## 6. Recomendações para o BACKLOG (texto pronto)

```markdown
| CAL1 | Alinhar TER da ferrovia ao terreno sintético (70.000 → ~54.000 m³/km) OU endurecer o terreno até ±20% — decidir comparando término e caminho crítico dos dois | `massas.coerencia` dentro de ±20% nos 12 segmentos; diferença de término registrada no CHANGELOG | muda a narrativa da demo |
| CAL2 | Declarar o MÉTODO por serviço no dataset (grade manual × mecanizada; lastro caminhão × hopper) e, se mecanizado, GRA ≈ 1,0 km/dia | campo `metodo` em `servicos` + fonte | R09 §1 |
| CAL3 | `ParametrosFrota.eficiencia` padrão 0,83 (SICRO, a confirmar na 2ª ed. do manual) e frota dimensionada pela DMT | teste: com 0,83 a produção sobe 0,83/0,70 | R09 §3 |
| CAL4 | Abrir os volumes 01 (Tabela 2: Fh por material; velocidades) e 04 (FIC por UF/mês) do Manual de Custos SICRO (.7z no gov.br) — precisa de descompactador (decisão: instalar 7-Zip ou não) | valores citados com página | R09 §3–4 |
| CAL5 | Calendário de chuva pelo FIC do SICRO (UF/mês) em vez de p sorteado; marcar "chuva sintética" na UI enquanto isso | teste: dias perdidos/mês = FIC declarado ± tolerância do manifesto | R09 §4 |
| CAL6 | Conferir na base OFICIAL do SICRO (não na réplica) as composições citadas: 5502165, 3009091, 2607206, 3009323, 4011276, 4011352, 4011464, 6416217 | tabela com código, produção e data-base | R09 §1 |
| CAL7 | Unidade de TER declarada no dataset ("corte + aterro geométricos") para não comparar com o SICRO (m³ escavado) por engano | campo/nota no JSON e no relatório | R09 §1 |
```

## 7. Não verificado nesta rodada

- Unidade de tempo oficial da "produção da equipe" do SICRO (inferida como hora).
- Tabela 2 do Volume 01 (Fh de solo) e velocidades.
- Volume 04 (FIC).
- Normais do INMET de número de dias de chuva.
- Espessuras nas normas DNIT 031/2024 e 141/2022.
- Composições SICRO de sublastro e grade em dormente de concreto.
- SUP, DRE, SBB, SHV, SVV, DEF.

---

## Resumo (10 linhas)

1. Conferi 16 linhas de produtividade e quantitativo, 9 de frota e terraplenagem e 3 de chuva contra fontes públicas, com [V]/[B]/[NV] e URL em cada número.
2. Dentro da referência: solda (6,0 contra ≈6,6/dia), imprimação (9.000 contra ≈8.300 m²/dia), CBUQ (650 contra ≈800 t/dia), dormentes (0,60 m, 1.667/km) e distribuição (~1 km/dia).
3. Conservador: BGS (600 contra ≈905 m³/dia) e eficiência de frota (0,70 contra 0,83 do SICRO).
4. Fora para método mecanizado: grade a 0,45 km/dia contra ~1 km/dia em obras brasileiras e 1,5 km/dia de máquina.
5. TER da ferrovia: a incoerência é interna (70.000 m³/km contra ~54.000 do terreno sintético). Corrigir muda o caminho crítico da demo.
6. Fh: a definição foi confirmada num ofício do DNIT (0,80 para rocha, Tabela 2 do Volume 01); o valor de solo segue sem fonte.
7. Chuva: nenhuma premissa de "dia perdido" tem fonte. O referencial é o FIC (Volume 04 do SICRO), não aberto por falta de descompactador.
8. Todas as composições SICRO foram vistas em réplica de terceiros (Orçamentor); falta conferir na base oficial (CAL6).
9. Não copiei a base SICRO: só código e número, por causa da CC BY-ND.
10. Sete recomendações (CAL1 a CAL7) prontas para o BACKLOG. Geradores e datasets não foram alterados.
