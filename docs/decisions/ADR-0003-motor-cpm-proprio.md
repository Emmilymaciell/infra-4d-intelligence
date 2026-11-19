# ADR-0003 — Motor CPM próprio e independente (construir, não reutilizar)

- **Data:** 2026-11-12
- **Status:** Aceita

## Contexto

O valor do produto está na previsão **independente** da construtora: recalcular o término a partir da
produtividade medida, com explicação auditável. As opções eram reutilizar (MPXJ, ProjectLibre, networkx,
OR-Tools) ou construir.

## Decisão

Construir o CPM em Python puro (`motor.py` e `calendario.py`) e usar bibliotecas externas só como adaptadores
de entrada e saída (backlog).

Suporte implementado e coberto por teste em `tests/test_motor_cpm.py`:

- relações FS, SS, FF e SF com lag positivo ou negativo, com o lag contado no calendário da **predecessora** (padrão do P6);
- calendário por atividade (dias da semana, feriados e dias não úteis explícitos, como chuva);
- marcos de início e de término; restrição *início não antes de* (SNET);
- data de status: concluída usa as datas reais; em andamento usa a duração **remanescente** a partir da data de
  status (*progress override*); não iniciada não começa antes da data de status;
- folga total, folga livre, caminho crítico (folga total ≤ 0) e cadeia determinante;
- recusa de rede inválida: ciclo (com os nós nomeados), referência inexistente, duração negativa e marco com duração.

Datas usam **fronteiras semiabertas** (`[ES, EF)`). Por isso a passada para trás é a inversa exata da passada
para frente em tempo de trabalho.

Duração por produtividade (`cenarios.py`):
`duração = ceil(quantidade_remanescente ÷ (produtividade × equipes))`, com memória de cálculo e fonte da
produtividade por atividade. A fonte segue esta hierarquia: medida na própria atividade → média do serviço no
lote → média do serviço na obra → planejada.

## Fora do escopo (declarado)

- **Nivelamento de recursos:** é camada separada, e o CPM aqui não limita recursos. Candidato futuro: OR-Tools (Apache-2.0).
- *Retained logic*, restrições do tipo *must finish*, *as late as possible*, calendários com horas, lag em
  porcentagem e lag no calendário da sucessora.
- Compatibilidade com P6 e Project **não é alegada**. Só será alegada depois de um teste de ida e volta com arquivos reais.

## Consequências

- Todo número exibido é rastreável até a fórmula e o boletim de origem.
- Divergências em relação ao P6 ficam registradas nos testes adversariais (`tests/test_revisao_adversarial_motor.py`).
