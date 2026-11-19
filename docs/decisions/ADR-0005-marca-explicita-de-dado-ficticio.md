# ADR-0005 — Marca booleana explícita de dado fictício (`meta.ficticio`)

- **Data:** 2026-11-12
- **Status:** Aceita (em implementação durante a missão autônoma)

## Contexto

Vários módulos **inventam** dados derivados quando a obra é fictícia: diários de obra (fiscalização), custo real
sintético (orçamento) e lista de riscos sintética (Monte Carlo v2). A revisão adversarial da rodada 6 mostrou que a
trava da fiscalização procurava a palavra "fictício" no texto livre de `meta.aviso`. Textos como "DADOS REAIS — este
arquivo NÃO é fictício" ou "Medição real da Rodovia Fictícia Ltda" passavam pela trava, e o módulo inventaria
2.510 diários sobre uma obra real.

## Decisão

1. Toda base sintética declara `meta.ficticio: true` (booleano), gravado pelo gerador.
2. Todo código que **gera dado inventado** sobre uma obra exige `meta.ficticio is True`, com identidade booleana e
   nunca por texto. Sem a marca, o código recusa com mensagem clara, mesmo que o aviso diga "fictício".
3. `meta.aviso` continua existindo para pessoas, e nenhuma decisão de código depende dele.
4. Quando entrar dado real (fim do ADR-0004), a ausência da marca é o estado normal e os geradores derivados ficam
   bloqueados por construção.

## Consequências

- Os dois JSON sintéticos mudam de hash uma vez, por causa do novo campo. Os testes `arquivo == gerar()` continuam
  valendo.
- Testes adversariais em `tests/test_revisao_adversarial_r6.py` cobrem as tentativas de contorno por texto.
