# ADR-0016 — Revisões nativas publicadas em cópia, separadas da demonstração

- Data: 2026-11-13.
- Status: aceita para o incremento experimental da missão mestre V3.
- Autorização de escopo: missão entregue pela titular; somente dados fictícios (ADR-0004 preservado).

## Contexto

Os uploads IFC existentes validam requisitos, vínculos e cronogramas, mas não
publicam uma revisão geométrica na cena. A missão pede editar em aplicativo real,
retornar e comparar, preservando os números do beta congelado em `12219c3`.

## Decisão

1. O arquivo nativo é a fonte da geometria autorável. O intercâmbio inicial usa
   GeoJSON de atividades lineares com contrato `infra4d.interop/1`, origem,
   checksum, unidade, identidade, classificação fictícia e revisão. A identidade
   não muda quando a revisão muda. Atividade agregada não é GlobalId de peça IFC.
2. QGIS e Blender executam como programas externos. Seus módulos GPL não são
   incorporados ao FastAPI. Isso descreve a separação técnica, não um parecer
   jurídico ou autorização para redistribuir programas de terceiros.
3. A base recebida deve reproduzir a publicação calculada a partir do Projeto.
   Base incompatível, IDs acrescentados/removidos, vínculos/unidades alterados e
   quantidades inválidas exigem recusa, sem mescla silenciosa.
4. Uma prévia calcula o efeito da revisão em um `Projeto` novo. A publicação
   explícita conserva essa cópia em memória do app. Dataset, cenário independente
   de referência, simulação do usuário e arquivo nativo não são sobrescritos.
5. Alteração explícita de quantidade de planejamento pode recalcular a cópia.
   Geometria/escala ilustrativa não altera medição, quantidade contratual ou CPM
   automaticamente. A cena identifica a revisão em camada própria; a timeline de
   referência continua identificada como tal.
6. O acervo inicial é limitado e volátil. Reiniciar o servidor o elimina; os
   arquivos de origem/revisão e manifestos são preservados em `output/releases/`,
   fora do Git. Persistência profissional e autenticação ficam para outro incremento.
7. CRS GIS e datum vertical são declarados como fictícios. Nenhuma prova de
   preservar coordenadas significa georreferenciamento de engenharia homologado.

## Evidência exigida e limites

- Testes de recusa, não mutação da referência, cálculo isolado, consulta por obra,
  acervo isolado por app, upload limitado e publicação idempotente.
- Executar scripts no runtime oficial do app e registrar logs/arquivos/hashes.
- Observar GUI e editar/salvar/reabrir manualmente é uma camada adicional: não
  inferir sua execução a partir de um script em modo batch.
- Não alegar edição BIM paramétrica no Bonsai por ter criado um `.blend` no Blender.
- Não alegar sincronização bidirecional geral, compatibilização ou uso em obra real.

## Consequências

As previsões da revisão são comparáveis e auditáveis sem alterar a demo antiga.
Conflitos que exigem novo mapeamento são recusados. A primeira federação é
deliberadamente agregada por atividade linear, com fidelidade e perdas declaradas
em `docs/interop/`; autoria IFC de componentes exige prova própria.
