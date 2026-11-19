"""O gabarito do mundo sintético não pode vazar para a previsão.

O JSON publica `meta.fatores_desempenho_simulados` (os fatores verdadeiros que o gerador usou), por transparência
de dado fictício, e o gerador sabe recalcular o futuro (`realidade_simulada`). Só o próprio gerador e as
ferramentas de AVALIAÇÃO (backtest, atribuição do erro, e o relatório/rotas que as exibem) podem chegar a isso;
qualquer módulo de previsão que chegasse tornaria a previsão independente circular sem ninguém perceber.

Duas camadas (r19):
- esta guarda ESTÁTICA, barata, que acusa os caminhos conhecidos: a chave (inteira ou em pedaços), o recálculo do
  futuro, os fatores fixos do gerador, varrer o `meta` inteiro e importar gerador/avaliação;
- o teste CONTRAFACTUAL em `test_revisao_adversarial_r19.py` (trocar o gabarito e exigir previsões idênticas),
  que é a proteção de verdade contra caminhos que nenhuma regra textual antecipa.
"""

import re
from pathlib import Path

PERMITIDOS = {
    "dados_sinteticos.py", "dados_sinteticos_rodovia.py", "sintetico_comum.py",  # quem gera
    "backtest.py", "atribuicao_erro.py",                                        # quem avalia contra a verdade
    "rotas_backtest.py", "rotas_atribuicao.py", "relatorio.py",                 # quem expõe/exibe a avaliação
}

RAIZ = Path(__file__).resolve().parents[1] / "scripts" / "infra4d"

PADROES = {
    "chave do gabarito (inteira ou em pedaços)": re.compile(r"desempenho_simulados|fatores_desempenho"),
    "recalcula o futuro do gerador": re.compile(r"realidade_simulada\s*\(|realidade_da_obra|\bgabarito\s*\("),
    # P9: o gabarito saiu do dataset e foi para examples/synthetic/gabarito/; ler o arquivo direto é trapaça
    "lê o arquivo de gabarito": re.compile(r"_gabarito\.json|synthetic[\\/\"' ]+gabarito|\bGABARITO\b"),
    "fatores fixos do gerador": re.compile(r"FATOR_DESEMPENHO|FAIXA_FATOR_SORTEADO|termino_realidade_simulada"),
    "varre o meta inteiro": re.compile(r"""meta["']?\]?\s*\)?\s*\.\s*(items|values)\s*\("""),
    "importa gerador ou avaliação": re.compile(
        r"(from\s+\.+\s*|from\s+infra4d\s*\.\s*|import\s+(infra4d\s*\.\s*)?)"
        r"(dados_sinteticos\w*|sintetico_comum|backtest|atribuicao_erro)\b"
        r"|from\s+\.+\s+import\s+[^\n]*\b(dados_sinteticos\w*|sintetico_comum|backtest|atribuicao_erro)\b"),
}


def acusados(pasta: Path, permitidos=PERMITIDOS) -> dict[str, list[str]]:
    """{arquivo: [motivos]} dos módulos fora da lista permitida que chegam ao gabarito por um caminho conhecido."""
    saida = {}
    for p in sorted(pasta.rglob("*.py")):
        if p.name in permitidos:
            continue
        texto = p.read_text(encoding="utf-8")
        motivos = [m for m, rx in PADROES.items() if rx.search(texto)]
        if motivos:
            saida[p.relative_to(pasta).as_posix()] = motivos
    return saida


def test_so_gerador_e_avaliacao_chegam_ao_gabarito():
    assert acusados(RAIZ) == {}, "módulos fora da avaliação chegando ao gabarito"


TRAPACAS = {
    "literal.py": "f = meta['fatores_desempenho_simulados']\n",
    "pedacos.py": "f = meta['fatores_' + 'desempenho_simulados']\n",
    "varre_meta.py": "for k, v in meta.items():\n    pass\n",
    "varre_meta2.py": "x = [v for v in dados['meta'].values()]\n",
    "fator_fixo.py": "from .dados_sinteticos import FATOR_DESEMPENHO\n",
    "futuro.py": "from . import dados_sinteticos\nr = dados_sinteticos.realidade_simulada(7)\n",
    "avaliacao.py": "from .backtest import realidade_da_obra\n",
    "absoluto.py": "import infra4d.backtest as b\n",
    "arquivo.py": "import json\ng = json.load(open('examples/synthetic/gabarito/rodovia_gabarito.json'))\n",
    "acessor.py": "from .sintetico_comum import gabarito\nf = gabarito(dados)\n",
}


def test_o_detector_acusa_cada_caminho_conhecido(tmp_path):
    """Visto falhar: cada módulo de 'previsão' trapaceiro é acusado; um módulo limpo não."""
    for nome, codigo in TRAPACAS.items():
        (tmp_path / nome).write_text(codigo, encoding="utf-8")
    (tmp_path / "limpo.py").write_text("x = meta.get('data_status')\n", encoding="utf-8")
    achados = acusados(tmp_path)
    assert set(achados) == set(TRAPACAS), achados
