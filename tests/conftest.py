"""Infraestrutura compartilhada pelos testes deste projeto.

O pytest carrega este arquivo sozinho, antes de qualquer teste. O que mora
aqui e o que TODO projeto governado pelo Emmily AI Project OS repete, e que
por isso nao deve ser reescrito a mao em cada um:

1. `scripts/` no caminho de import. Sem isto, cada arquivo de teste comeca
   com tres linhas de `sys.path.insert`, e a primeira vez que alguem move um
   teste para uma subpasta o import quebra de um jeito que nao explica nada.

2. O criterio de pronto e os limites numericos lidos do `project.yaml`. Este
   e o ponto mais importante do arquivo, e ele nasceu de um defeito real:
   no projeto `conversor-utm`, o criterio "dentro de 1 metro" existia em tres
   lugares - a prosa do README, a docstring do teste, e um `1.0` cravado na
   assercao - e em nenhum deles era fonte de verdade. Numero repetido
   envelhece; numero em um lugar so, nao.

3. Fixtures para as armadilhas de arquivo desta maquina, sendo a primeira o
   BOM que o Excel e o PowerShell colam no inicio de todo CSV que salvam.

REGRA DESTE ARQUIVO: nada aqui devolve valor padrao. Se o manifesto nao
declara o que o teste pediu, o teste FALHA dizendo o que falta. Padrao
silencioso transformaria "o projeto nao declarou seu criterio" em "passou",
que e exatamente a violacao descrita em VERIFICATION-POLICY 4.5.
"""

from pathlib import Path
import re
import sys

import pytest

RAIZ = Path(__file__).resolve().parents[1]

# scripts/ importavel pelos testes, sem boilerplate em cada arquivo.
_SCRIPTS = RAIZ / "scripts"
if _SCRIPTS.is_dir() and str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


# =============================================================================
# Leitura do manifesto
# =============================================================================
#
# Leitor proprio, e de proposito: um projeto de script nao deve ganhar uma
# dependencia de YAML para ler tres campos. O preco esta declarado - o leitor
# entende `chave: valor` aninhado por indentacao e mais nada.
#
# E ele falha FECHADO. A plataforma ja teve um parser de YAML proprio que
# falhava aberto (ADR-0010, emenda de 2026-09-10): ele aceitava silenciosamente
# o que nao entendia. Aqui, o que nao e reconhecido nao entra no resultado, e o
# que nao entrou no resultado faz o teste falhar - nunca passar.


class ManifestoInvalido(Exception):
    """O project.yaml nao pode ser lido para o que o teste precisa."""


class ValorNaoLegivel:
    """Valor que o manifesto declara e este leitor nao sabe ler.

    Ele e REGISTRADO, nao ignorado: ignorar faria a chave parecer ausente, e
    ausente parece "nao declarei" - que e outra coisa. Pedir esta chave falha
    o teste; pedir OUTRA funciona normalmente.

    Isso importa concretamente: o `project.yaml` da propria plataforma tem
    lista em `ambiente.dependencias_externas`, e o ADR-0010 manda preencher
    `classificacao.dados_sensiveis_excecoes` com entradas de lista. Uma versao
    anterior deste leitor levantava excecao em lista EM QUALQUER POSICAO do
    arquivo, o que derrubava a suite inteira de um projeto cujo manifesto
    seguia o schema documentado - enquanto o gemeo PowerShell passava.
    """

    def __init__(self, motivo: str):
        self.motivo = motivo

    def __repr__(self):
        return f"<nao legivel: {self.motivo}>"


# '>' ou '|', opcionalmente com indicador de indentacao (1-9) e de chomping
# (+/-), em qualquer ordem: | |- |+ |2 |2- |-2 > >- >3 ...
#
# A versao anterior listava so as SEIS formas sem digito, e o
# security-reviewer achou o furo: 'criterio_de_pronto: |2' caia no ramo de
# escalar comum e o valor virava a string '|2'. Os dois gemeos erravam igual.
_RE_INDICADOR_DE_BLOCO = re.compile(r"^[>|](?:[1-9][-+]?|[-+][1-9]?)?$")


def _sem_aspas(valor: str) -> str:
    """Remove UM par de aspas nas pontas, e so quando ha par."""
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
        return valor[1:-1]
    return valor


def _limpar_valor(bruto: str) -> str:
    """Tira o comentario de fim de linha. NAO tira aspas.

    A ordem importa e foi divergencia real: este leitor tirava as aspas ANTES
    de testar o indicador de escalar de bloco, entao `algum: ">"` - a string
    '>' entre aspas - virava ValorNaoLegivel aqui e valor normal no gemeo
    PowerShell. O indicador passou a ser testado no valor CRU nos dois.
    """
    valor = bruto.strip()
    # Comentario no fim da linha. Qualquer espaco em branco antes do '#' conta
    # - inclusive TAB, que era a sexta divergencia entre os gemeos: o '\s+#'
    # do PowerShell casava tab e o '" #"' daqui nao. Um '#' COLADO ao valor
    # continua sendo parte do valor.
    # MAS nao dentro de string entre aspas: 'criterio: "roda o passo #3"' e
    # string literal em YAML, e a versao anterior cortava no primeiro
    # espaco-'#' e devolvia 'roda o passo' com aspa orfa - verde sobre um
    # criterio de aceite TRUNCADO. Os dois gemeos erravam igual, entao o caso
    # de comparacao nao alcancava. Achado do qa-reviewer.
    if len(valor) >= 2 and valor[0] in "\"'":
        fecha = valor.find(valor[0], 1)
        if fecha > 0:
            depois = valor[fecha + 1:]
            # r"^\s+#", nao r"^\s#": o manifesto da plataforma alinha os
            # comentarios com varios espacos. Mesma correcao do gemeo.
            if re.match(r"^\s+#", depois):
                valor = valor[: fecha + 1]
    else:
        corte = re.search(r"\s#", valor)
        if corte:
            valor = valor[: corte.start()].strip()
    # Valor que e SO comentario e valor ausente. Em YAML,
    #     criterio_de_pronto:  # preencher depois
    # e null - e os dois leitores devolviam '# preencher depois' como se fosse
    # o criterio. Achado do qa-reviewer; os dois erravam igual.
    if valor.startswith("#"):
        valor = ""
    return valor


def ler_manifesto(caminho: Path = None) -> dict:
    """Devolve o `project.yaml` como dicionario aninhado.

    GEMEO de Read-ManifestoDoProjeto em tests/_harness.ps1. Os dois tem de
    aceitar e recusar as MESMAS coisas, e devolver o MESMO valor: os revisores
    independentes acharam cinco divergencias entre eles ao longo da 2.4, e
    divergencia aqui significa projeto Python e projeto PowerShell com rigor
    diferente sobre o mesmo manifesto.

    Reconhece `chave: valor` e `chave:` abrindo bloco, com indentacao por
    espacos. Lista e escalar de bloco viram ValorNaoLegivel - registrados, com
    os itens e continuacoes pulados. Linha que nao e nenhuma dessas coisas
    levanta excecao: este leitor e estrito de proposito.
    """
    caminho = caminho or (RAIZ / "project.yaml")
    if not caminho.is_file():
        raise ManifestoInvalido(f"project.yaml nao encontrado em {caminho}")

    # utf-8-SIG, nao utf-8. O gemeo PowerShell usa
    # File.ReadAllText(..., Encoding.UTF8), que CONSOME o BOM; este lado nao
    # consumia, e o '\ufeff' nao e whitespace - nem .strip() nem .lstrip() o
    # removem. Consequencia tracada pelo qa-reviewer: num project.yaml salvo
    # com BOM (o PowerShell 5.1 'Out-File -Encoding UTF8' SEMPRE grava BOM, e
    # o Bloco de Notas tambem), a linha 1 e o comentario
    # '# Preenchido por /os:new-project...'. Com o BOM na frente,
    # lstrip().startswith("#") da FALSO, a linha nao e pulada, ela contem ':'
    # (em '/os:new-project') e vira uma chave-lixo na raiz do manifesto. Um
    # leitor cujo contrato e "o que nao entende, recusa" aceitando comentario
    # como dado: fail-open, e a SETIMA divergencia entre os gemeos.
    #
    # A regra ja estava neste arquivo, na docstring da fixture csv_com_bom -
    # "a leitura certa e utf-8-sig". Nao tinha sido aplicada ao manifesto.
    linhas = caminho.read_text(encoding="utf-8-sig").splitlines()

    def _proxima_significativa(inicio: int):
        for j in range(inicio + 1, len(linhas)):
            if linhas[j].strip() and not linhas[j].lstrip().startswith("#"):
                return linhas[j]
        return None

    resultado: dict = {}
    pilha = [(-1, resultado)]
    ultimo_pai = resultado
    ultima_chave = None
    indent_lista = -1      # indentacao do marcador '-' da lista corrente
    indent_escalar = -1    # indentacao da chave do escalar de bloco corrente

    for indice, linha in enumerate(linhas):
        numero = indice + 1
        if not linha.strip() or linha.lstrip().startswith("#"):
            continue

        indent = len(linha) - len(linha.lstrip(" "))
        conteudo = linha.strip()
        eh_item = conteudo.startswith("- ") or conteudo == "-"

        # Dentro de uma lista: pula item irmao no MESMO indent e continuacao
        # mais indentada. Chave irma no indent do marcador ENCERRA a lista.
        #
        # A versao anterior pulava tudo com 'indent >= indent_ignoravel', e no
        # estilo compacto do YAML - saida padrao do yaml.dump, e o estilo que
        # o ADR-0010 produz - a chave irma no MESMO indent do marcador era
        # pulada em SILENCIO: o leitor lia meio manifesto sem dizer.
        if indent_lista >= 0:
            if eh_item and indent == indent_lista:
                continue
            if indent > indent_lista:
                continue
            indent_lista = -1

        if indent_escalar >= 0:
            if indent > indent_escalar:
                continue
            indent_escalar = -1

        if eh_item:
            if ultima_chave is not None:
                ultimo_pai[ultima_chave] = ValorNaoLegivel("lista")
                indent_lista = indent
                # A chave pode ter aberto bloco pelo lookahead; desempilhar
                # para ela nao valer bloco E lista ao mesmo tempo.
                while len(pilha) > 1 and pilha[-1][0] >= indent:
                    pilha.pop()
            continue

        if ":" not in conteudo:
            raise ManifestoInvalido(
                f"linha {numero}: nao e 'chave: valor', nem 'chave:', nem item de lista: "
                f"{conteudo!r}. Este leitor e estrito de proposito."
            )

        chave, _, resto = conteudo.partition(":")
        chave = _sem_aspas(chave.strip())
        if not chave:
            # ': valor' era recusado pelo PowerShell e aceito aqui.
            raise ManifestoInvalido(
                f"linha {numero}: chave vazia. Este leitor recusa; o gemeo PowerShell tambem."
            )

        while pilha and indent <= pilha[-1][0]:
            pilha.pop()
        if not pilha:
            raise ManifestoInvalido(f"linha {numero}: indentacao inconsistente")

        pai = pilha[-1][1]
        bruto = _limpar_valor(resto)

        if _RE_INDICADOR_DE_BLOCO.match(bruto):
            pai[chave] = ValorNaoLegivel(f"escalar de bloco ({bruto!r})")
            indent_escalar = indent
            ultimo_pai, ultima_chave = pai, chave
            continue

        if bruto in ("{}", "[]"):
            novo_bloco: dict = {}
            pai[chave] = novo_bloco
            pilha.append((indent, novo_bloco))
            ultimo_pai, ultima_chave = pai, chave
            continue

        if bruto == "":
            # `chave:` sem valor abre bloco SO se a proxima linha significativa
            # for mais indentada; caso contrario e campo declarado VAZIO, e
            # vazio nao e bloco. Mesma regra do gemeo PowerShell.
            prox = _proxima_significativa(indice)
            if prox is not None and (len(prox) - len(prox.lstrip(" "))) > indent:
                novo_bloco = {}
                pai[chave] = novo_bloco
                pilha.append((indent, novo_bloco))
            else:
                pai[chave] = ""
            ultimo_pai, ultima_chave = pai, chave
            continue

        pai[chave] = _sem_aspas(bruto)
        ultimo_pai, ultima_chave = pai, chave

    return resultado


def _exigir(manifesto: dict, *caminho: str):
    """Busca um campo aninhado, ou falha o teste dizendo exatamente o que falta.

    Nao devolve None, nao devolve padrao, e nao devolve bloco onde se esperava
    valor. Um teste que pergunta o limite ao manifesto e recebe None passaria
    a comparar contra nada; um que recebe {} compara contra um dicionario.
    """
    atual = manifesto
    for parte in caminho:
        if isinstance(atual, ValorNaoLegivel):
            pytest.fail(
                "project.yaml: um trecho de '"
                + ".".join(caminho)
                + "' e "
                + atual.motivo
                + ", que este leitor nao le."
            )
        if not isinstance(atual, dict) or parte not in atual:
            pytest.fail(
                "project.yaml nao declara '"
                + ".".join(caminho)
                + "'. Declare o campo antes de assertar contra ele - "
                "criterio que nao esta no manifesto nao e criterio."
            )
        atual = atual[parte]
    if isinstance(atual, ValorNaoLegivel):
        pytest.fail(
            "project.yaml declara '"
            + ".".join(caminho)
            + "' como "
            + atual.motivo
            + ", que este leitor nao le. Escreva o valor numa linha so, entre aspas."
        )
    if isinstance(atual, dict):
        pytest.fail(
            "project.yaml declara '"
            + ".".join(caminho)
            + "' como bloco"
            + (" vazio" if not atual else "")
            + ", nao como valor. Declare o valor, ou aponte para um campo dentro dele."
        )
    if isinstance(atual, str):
        if atual.strip() == "":
            pytest.fail(
                "project.yaml declara '" + ".".join(caminho) + "' VAZIO. "
                "Campo declarado e vazio nao e criterio declarado."
            )
        if atual.startswith("{{"):
            pytest.fail(
                "project.yaml ainda tem o placeholder em '"
                + ".".join(caminho)
                + "'. O /os:new-project nao terminou a substituicao."
            )
    return atual


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def projeto_raiz() -> Path:
    """A raiz do projeto, para teste que precisa tocar arquivo do repositorio."""
    return RAIZ


@pytest.fixture(scope="session")
def manifesto() -> dict:
    """O `project.yaml` lido. Falha o teste se nao der para ler."""
    try:
        return ler_manifesto()
    except ManifestoInvalido as erro:
        pytest.fail(f"project.yaml ilegivel: {erro}")


@pytest.fixture(scope="session")
def criterio_de_pronto(manifesto) -> str:
    """A frase que define 'pronto', vinda do manifesto e de nenhum outro lugar."""
    return _exigir(manifesto, "verificacao", "criterio_de_pronto")


@pytest.fixture(scope="session")
def limite(manifesto):
    """Devolve `limite("nome")` -> float, lido de `verificacao.limites`.

    Uso:

        def test_fecha_no_criterio(limite):
            assert erro_medido < limite("erro_maximo_m")

    Limite ausente falha o teste. Limite que nao e numero tambem: um
    `erro_maximo_m: "um metro"` compararia string com float e o erro sairia
    longe da causa.
    """

    def buscar(nome: str) -> float:
        bruto = _exigir(manifesto, "verificacao", "limites", nome)
        try:
            return float(bruto)
        except (TypeError, ValueError):
            pytest.fail(
                f"verificacao.limites.{nome} = {bruto!r} nao e numero. "
                "Limite de aceite precisa ser comparavel."
            )

    return buscar


@pytest.fixture
def csv_com_bom(tmp_path):
    """Cria um CSV com BOM, como o Excel e o PowerShell salvam.

    Regressao que vale para qualquer projeto que leia arquivo de escritorio:
    lido como `utf-8` puro, o BOM cola no nome da primeira coluna e o erro sai
    como "coluna ausente" com o arquivo aparentemente correto. A leitura certa
    e `utf-8-sig`. Achado em clone limpo no `conversor-utm`.

    Uso:

        def test_le_csv_do_excel(csv_com_bom):
            caminho = csv_com_bom("A,B\\n1,2\\n")
    """

    def criar(conteudo: str, nome: str = "com_bom.csv") -> Path:
        destino = tmp_path / nome
        destino.write_bytes(b"\xef\xbb\xbf" + conteudo.encode("utf-8"))
        return destino

    return criar


# =============================================================================
# Específico deste projeto (INFRA 4D) — isolamento do banco SQLite nos testes
# =============================================================================
#
# Achado da revisão adversarial (rodada 8): `criar_app()` liga as rotas de
# histórico com o banco PADRÃO (output/infra4d.sqlite), e até um GET o cria.
# Várias suítes em paralelo (ou suíte + servidor de desenvolvimento) passariam
# a disputar o MESMO arquivo — candidata ao travamento de 2026-11-12, em que
# três suítes paralelas pararam com 0% de CPU (sqlite3 espera até 30 s por
# escrita bloqueada). Cada sessão de teste usa agora um banco próprio em tmp,
# salvo se INFRA4D_BANCO já vier definido de fora.


@pytest.fixture(scope="session", autouse=True)
def _banco_isolado_por_sessao(tmp_path_factory):
    import os

    if os.environ.get("INFRA4D_BANCO"):
        yield
        return
    os.environ["INFRA4D_BANCO"] = str(tmp_path_factory.mktemp("banco") / "infra4d.sqlite")
    try:
        yield
    finally:
        os.environ.pop("INFRA4D_BANCO", None)
