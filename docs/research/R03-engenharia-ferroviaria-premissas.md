> **AVISO (2026-11-12):** esta primeira rodada foi escrita quase sem consulta à web. As licenças, versões e correções verificadas estão em `R04-verificacao-web.md`, seção 4, que **prevalece** sobre este arquivo em caso de divergência.

# R03 — Premissas de engenharia ferroviária (caso SINTÉTICO)

> Finalidade: dar plausibilidade a dados **fictícios** para o motor CPM. Nada aqui descreve obra real.
> **Status das fontes:** nesta rodada NÃO houve verificação web. Todos os números estão marcados
> **[OG]** = "estimativa de ordem de grandeza sem fonte verificada" (conhecimento técnico geral de
> engenharia ferroviária/rodoviária). Referências normativas citadas pelo nome (ABNT NBR, DNIT, AREMA)
> são indicações de onde verificar, **não** fontes conferidas. Nenhuma URL foi inventada.
> Próximo passo recomendado: validar as faixas contra o SICRO/DNIT (composições de custo/produção),
> especificações técnicas da VALEC/Infra S.A. e AREMA Manual for Railway Engineering.

Premissas do caso: via singela, bitola larga 1,60 m (ou mista 1,00/1,60 com 3º trilho), trilho TR-68
(~67,6 kg/m), dormente de concreto monobloco (ou aço/madeira em AMV), lastro de brita, carga por eixo
alta (~32,5 tf, padrão heavy haul brasileiro). [OG]

---

## 1. Sequência construtiva e relações lógicas (trecho linear)

| # | Atividade | Predecessora | Relação | Lag típico [OG] | Justificativa |
|---|---|---|---|---|---|
| 1 | Licença de instalação + desapropriação/liberação de faixa | — | marco | — | Restrição externa; sem LI e posse não há mobilização na frente |
| 2 | Supressão vegetal / limpeza / destocamento | 1 | FS | 0 | Exige ASV (autorização de supressão) |
| 3 | Terraplenagem (corte, aterro, compactação) | 2 | SS | 1–3 km ou 2–4 semanas | Frente de limpeza precisa abrir caminho à frente |
| 3→ | Terraplenagem fim | 2 fim | FF | 2–4 semanas | Não termina antes de liberar a faixa toda |
| 4 | Drenagem de grota (bueiros tubulares/celulares) | 2 | SS | pequeno | Bueiros precedem o aterro no talvegue (bueiro → aterro sobre ele) |
| 4b | Aterro sobre bueiro | 4 (local) | FS | 7–28 dias (cura/reaterro) | Concreto/reaterro lateral antes do corpo do aterro |
| 5 | OAEs (pontes/viadutos) | 1 | FS (independente da frente) | — | Caminho crítico frequente; iniciar cedo; aterros de encontro dependem dela |
| 6 | Drenagem superficial (valetas, sarjetas, descidas) | 3 | SS | 3–5 km | Segue a terraplenagem acabada |
| 7 | Sublastro (camada granular/solo-brita) | 3 | SS | 3–5 km | Plataforma acabada e liberada por ensaio (GC) |
| 7→ | Sublastro fim | 3 fim | FF | 2–4 semanas | |
| 8 | Distribuição de dormentes | 7 | SS | 1–3 km | Dormentes lançados sobre sublastro pronto (ou pré-lastro) |
| 9 | Assentamento de grade (dormentes + trilho) | 8 | SS | 0,5–2 km | Frente contínua atrás da distribuição |
| 9a | Travessia de OAE | 5 | FS | — | Grade não passa a OAE inacabada → quebra frente/logística |
| 10 | Lastro 1ª camada (descarga) | 9 | SS | 2–5 km | Trem de lastro precisa da grade montada à frente para circular |
| 11 | Levante + socaria (2–3 passadas) | 10 | SS | 1–3 km | Cada passada levanta 5–10 cm; intercala descarga e socaria |
| 12 | Soldagem (estaleiro → barras longas; aluminotérmica no campo) | 9 | SS | 2–5 km | Barras de estaleiro (~240–360 m) chegam antes; soldas de campo após 1º levante |
| 13 | Regularização / perfilamento final + estabilização dinâmica | 11 | SS / FF | 1–2 km / 1–2 semanas | Fecha geometria |
| 14 | Neutralização de tensões (TLS) | 12, 13 | FS (por trecho) | — | Fixar temperatura neutra após geometria final |
| 15 | AMVs (pátios) | 7 (no pátio) | FS | — | Montados em paralelo; ligam-se à linha corrida após lastro |
| 16 | Sinalização / telecom / energia | 13 (por trecho) | SS | — | Cabeamento pode iniciar com plataforma; equipamentos após via |
| 17 | Inspeção geométrica, testes, comissionamento, liberação | 13, 14, 16 | FS | 2–6 semanas | Carro-controle, ensaios, operação assistida |

Regra geral: entre frentes lineares a relação "certa" é **SS com lag em distância** + **FF com lag**
(evita que a sucessora alcance a predecessora). Em CPM por atividade-trecho (ex.: lotes de 5 km), vira FS entre lotes.

---

## 2. Quantitativos típicos por km de via singela [OG]

| Item | Unidade | Faixa /km | Observação |
|---|---|---|---|
| Corte (escavação 1ª/2ª/3ª cat.) | m³ | 40.000–150.000 | Muito dependente de relevo; greide ferroviário exige rampas ≤ ~1% |
| Aterro compactado | m³ | 40.000–150.000 | Compensação longitudinal parcial; bota-fora/empréstimo |
| Plataforma (largura) | m | 7–9 (singela) | Bitola larga |
| Sublastro (e≈20–30 cm) | m³ | 1.800–2.700 | |
| Lastro (e≈30–35 cm sob dormente, ombros) | m³ | 1.700–2.300 | ≈ 2.800–3.900 t (densidade ~1,6–1,7 t/m³) |
| Dormentes (espaçamento 0,60 m) | un | ~1.667 (1.600–1.700) | Concreto monobloco ~300–400 kg/un |
| Trilho TR-68 (2 filas) | m / t | 2.000 m / ~135 t | Bitola mista: 3 filas → ~3.000 m / ~203 t |
| Fixações elásticas | conj. | ~6.670 (4/dormente) | Mista: mais |
| Soldas aluminotérmicas de campo | un | 6–10 | Barras de 240–360 m; mais nas OAEs/AMVs |
| Bueiros | un | 1–3 | |
| Drenagem superficial | m | 1.000–2.500 | |

---

## 3. Produtividades por equipe/equipamento [OG]

| Serviço | Faixa | Composição típica |
|---|---|---|
| Supressão/limpeza | 1–3 ha/dia | Trator esteira (D6–D8), escavadeira, motosserras, 10–20 pessoas |
| Escavação+transporte (corte) | 1.500–4.000 m³/dia por frota | 1 escavadeira 30–40 t + 6–12 caminhões 14 m³ (ou articulados) + trator |
| Aterro compactado | 1.500–3.500 m³/dia por frota | Motoniveladora, rolo pé-de-carneiro, caminhão-pipa, trator agrícola+grade |
| Rocha (3ª cat.) | 300–1.000 m³/dia | Perfuratriz, explosivos, escavadeira |
| Bueiro tubular (BSTC Ø1,0–1,5) | 10–20 m/dia | Escavadeira, guindauto, 8–12 pessoas |
| Sublastro | 400–1.000 m³/dia (≈0,2–0,5 km/dia) | Motoniveladora, rolo liso, pipa, caminhões |
| Distribuição de dormentes | 1–3 km/dia | Caminhões/trem + pórticos ou carregadeira |
| Grade manual/semimecanizada | 0,3–0,8 km/dia | 30–60 pessoas, guindauto, pórticos rodantes |
| Grade mecanizada (lançadora tipo TCM/PTL) | 1,5–3 km/dia (picos > 3) | Trem lançador, 20–40 pessoas |
| Descarga de lastro | 1.000–3.000 m³/dia (≈0,5–1,5 km/dia) | Trem de lastro (vagões hopper) |
| Socaria mecanizada (socadora linha) | 0,5–1,5 km/dia por passada | Socadora + reguladora + estabilizador; 2–3 passadas |
| Regularização de lastro | 2–4 km/dia | Reguladora |
| Solda aluminotérmica | 4–10 soldas/dia por equipe | 4–6 soldadores + esmerilhadora |
| Solda elétrica (estaleiro, flash-butt) | 30–80 soldas/dia | Estaleiro fixo |
| AMV montado e assentado | 1 AMV a cada 5–15 dias | Equipe dedicada 15–25 pessoas, guindaste |
| OAE (viga pré-moldada, vão 25–40 m) | 1–3 meses/vão incl. fundação | Varia muito — modelar por atividade |

Jornada de referência: 1 turno de 9–10 h, 22–26 dias úteis/mês. [OG]

---

## 4. Restrições típicas [OG]

| Restrição | Efeito no cronograma | Modelagem sugerida |
|---|---|---|
| Período chuvoso (Centro-Oeste/Norte ~out–abr) | Terraplenagem cai a 30–60% ou para; sublastro/compactação quase paralisam | Calendário sazonal com fator de produtividade por mês |
| Dias de chuva > ~10 mm | Perda de 1–2 dias de terraplenagem | Fator estocástico |
| Licenças (LP/LI/ASV, outorga, IPHAN, comunidades) | Bloqueia início por trecho | Marcos restritivos (SNET) por lote |
| Desapropriação/posse | Frente "pula" trechos; descontinuidade | Marco por segmento |
| Entrega de trilho (importado, lead time 4–9 meses) e dormentes (fábrica ~500–1.500 un/dia) | Grade limitada pelo suprimento | Recurso/marco de entrega; estoque mínimo à frente |
| Brita (pedreira, transporte) | Limita lastro | Taxa máxima de suprimento |
| OAE inacabada | Interrompe frente de grade e trem de lastro | FS rígido OAE → grade a jusante |
| Interferências (rodovias, redes, ferrovia existente) | Janelas noturnas/fins de semana | Calendário especial |
| Logística em linha única de obra | Trens de serviço disputam a via | Restrição de recurso único |

---

## 5. Notas para rodovia (expansão futura) [OG]

| Item | Faixa |
|---|---|
| Plataforma pista simples | 10–14 m; duplicada 25–35 m |
| Camadas típicas (flexível) | Reforço/subleito 20–30 cm; sub-base 15–20; base 15–20 (BGS/BGTC); imprimação; CBUQ 5–12 cm |
| Terraplenagem | Mesmas frotas/produtividades da ferrovia; volumes /km com rampas mais permissivas (até 6–8%) |
| Base/sub-base | 500–1.500 m³/dia (≈0,5–1 km/dia pista simples) |
| Usina de asfalto (CBUQ) | 80–200 t/h nominal → 500–1.500 t/dia |
| Vibroacabadora | 1–3 km/dia de faixa (limitada pela usina e caminhões) |
| Relações | Base → imprimação FS (cura 1–3 dias); CBUQ SS sobre base com lag em km; sinalização horizontal FS após cura |
| Restrição | Chuva impede imprimação e CBUQ (não aplicar em superfície molhada) |
| Normas a verificar | Especificações de Serviço DNIT (DNIT-ES); SICRO para produções |
