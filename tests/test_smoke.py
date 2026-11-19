"""Testes de fumaca: o projeto declara a verdade sobre si mesmo?

Este arquivo e o teste que a politica de verificacao exige que exista desde o
primeiro dia (VERIFICATION-POLICY 4.4: pasta de verificacao vazia nao conta).
Ele nao testa o programa - testa o CONTRATO do projeto, que e a unica coisa
que ja existe quando o projeto acabou de nascer.

O que ele guarda, e por que cada um custou tempo de verdade nesta plataforma:

- O manifesto e legivel e nao ficou com placeholder. Na Fase 1, `INFRA 4D INTELLIGENCE`
  sobreviveu em dois arquivos porque a substituicao filtrava por extensao.
- O comando de teste declarado aponta para um arquivo que existe. Comando de
  teste documentado e nunca executado foi a lacuna mais irritante do teste de
  aceitacao da Fase 1.
- Existe codigo deterministico sem nenhum teste proprio? Isso reprova. E a
  unica forma de a pasta `tests/` deixar de ser decoracao conforme o projeto
  cresce, sem depender de alguem lembrar.

Este arquivo pode ficar como esta pelo resto da vida do projeto. Nao apague:
ele e o unico teste que continua valendo quando todos os outros forem
reescritos.
"""

from pathlib import Path

import pytest

# A MESMA lista de tests/suites/smoke.ps1. Divergir aqui significa que a
# politica 4.4 vale conforme a linguagem do harness, nao conforme o codigo:
# um scripts/analise.R nao exigiria teste num projeto PowerShell, e um
# scripts/util.psm1 nao exigiria num projeto Python. Achado do qa-reviewer.
EXTENSOES_DE_CODIGO = (".py", ".ps1", ".psm1", ".js", ".ts", ".sql", ".r")


def test_manifesto_e_legivel_e_se_identifica(manifesto):
    assert manifesto.get("identidade", {}).get("nome"), (
        "project.yaml sem identidade.nome. /os:status e /os:handoff leem daqui: "
        "manifesto sem nome faz os dois mentirem."
    )


def test_nao_sobrou_placeholder_no_manifesto(projeto_raiz):
    texto = (projeto_raiz / "project.yaml").read_text(encoding="utf-8")
    assert "{{" not in texto, (
        "project.yaml ainda tem placeholder {{...}}: a instanciacao nao terminou. "
        "Nao filtre por extensao ao substituir - varra todo arquivo de texto."
    )


def test_o_comando_de_teste_declarado_aponta_para_arquivo_que_existe(
    projeto_raiz, manifesto
):
    comando = manifesto.get("verificacao", {}).get("comando", "")
    assert comando, "project.yaml nao declara verificacao.comando"

    # O comando canonico e '.\\tests\\run-tests.ps1'. Extrair o caminho do
    # primeiro token e conferir que ele existe: comando que aponta para nada
    # e pior que comando ausente, porque parece resolvido.
    alvo = comando.split()[0].lstrip(".\\/").replace("\\", "/")
    assert (projeto_raiz / alvo).is_file(), (
        f"verificacao.comando aponta para '{alvo}', que nao existe neste projeto."
    )


def test_a_trilha_de_teste_deste_projeto_e_uma_so(projeto_raiz):
    """Duas trilhas ao mesmo tempo significa instanciacao incompleta.

    O template traz a trilha Python e a trilha PowerShell; o /os:new-project
    apaga a que nao se aplica. Se as duas sobreviverem, o runner recusa rodar
    (saida 2) - e melhor descobrir isso por aqui, com a mensagem certa.
    """
    tests = projeto_raiz / "tests"
    tem_python = any(tests.glob("test_*.py"))
    tem_powershell = any((tests / "suites").glob("*.ps1")) if (tests / "suites").is_dir() else False
    assert not (tem_python and tem_powershell), (
        "tests/ tem a trilha Python E a trilha PowerShell. Apague a que este "
        "projeto nao usa - ver tests/README.md."
    )


def test_campo_inexistente_no_manifesto_FALHA_em_vez_de_devolver_vazio():
    """O par negativo do leitor de manifesto (politica 4.1).

    Sem este caso, um leitor que devolvesse None em silencio passaria por
    todos os outros - e criterio ausente viraria criterio atendido. A trilha
    PowerShell ja tinha o equivalente e esta nao tinha: o qa-reviewer apontou
    que todo projeto PowerShell nascia com teste negativo do detector e todo
    projeto Python nascia sem.

    Usa a API do conftest diretamente, nao a fixture, porque o que se testa
    aqui e o comportamento de FALHA - e a fixture falharia o proprio caso.
    """
    import conftest

    manifesto = conftest.ler_manifesto(Path(__file__).resolve().parents[1] / "project.yaml")

    with pytest.raises(BaseException) as erro:
        conftest._exigir(manifesto, "verificacao", "campo_que_nao_existe")
    assert "nao declara" in str(erro.value), (
        "campo ausente deveria falhar dizendo o que falta, e nao devolver valor"
    )

    # Bloco onde se esperava valor tambem falha: 'limites: {}' e declarado e
    # vazio, e devolver {} faria a assercao comparar contra um dicionario.
    with pytest.raises(BaseException) as erro:
        conftest._exigir(manifesto, "verificacao", "limites")
    assert "bloco" in str(erro.value)


def test_codigo_deterministico_sem_teste_proprio_reprova(projeto_raiz):
    """Politica 4.4 aplicada ao projeto conforme ele cresce.

    Projeto recem-criado tem `scripts/` vazio e passa: nao ha o que testar
    ainda. No minuto em que entra o primeiro script, este caso exige que
    exista ao menos um teste que nao seja este arquivo de fumaca.
    """
    scripts = projeto_raiz / "scripts"
    codigo = []
    if scripts.is_dir():
        codigo = [
            f for f in scripts.rglob("*")
            if f.is_file() and f.suffix.lower() in EXTENSOES_DE_CODIGO
        ]
    if not codigo:
        pytest.skip("scripts/ ainda nao tem codigo: nada a exigir")

    tests = projeto_raiz / "tests"
    proprios = [
        f for f in tests.glob("test_*.py") if f.name != Path(__file__).name
    ]
    assert proprios, (
        "existe codigo em scripts/ ("
        + ", ".join(f.name for f in codigo[:5])
        + ") e nenhum teste alem do de fumaca. "
        "Pasta de verificacao vazia nao conta - VERIFICATION-POLICY 4.4."
    )
