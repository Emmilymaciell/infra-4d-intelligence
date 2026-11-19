"""Revisão adversarial — rodada 7: frontend (web/*.js, web/index.html).

Sem navegador: varredura ESTÁTICA do código-fonte JS e conferência, pela API, de que o dado malicioso
chega cru ao cliente. O que só se prova no navegador está como roteiro em testes ``skip``.

Carga usada nos roteiros:  <img src=x onerror=alert(1)>

Fechamento: os 10 defeitos marcados na rodada 7 foram corrigidos pelo frontend/servidor e as marcas xfail
saíram; os testes ficam como regressão. Os roteiros de navegador continuam em testes ``skip``.
"""

import copy
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra4d.cenarios import Projeto

RAIZ = Path(__file__).resolve().parents[1]
WEB = RAIZ / "web"
CARGA = "<img src=x onerror=alert(1)>"


def fonte(nome):
    return (WEB / nome).read_text(encoding="utf-8")


def arquivos_js():
    return sorted(p.name for p in WEB.glob("*.js"))


# =============================================================================
# 1. XSS — o que está certo
# =============================================================================
def test_funcao_de_escape_existe_e_cobre_os_cinco_caracteres():
    """util.js exporta ``esc`` cuja classe de caracteres e cujo mapa cobrem & < > " ' com as entidades
    &amp; &lt; &gt; &quot; &#39; — o suficiente para texto E para atributo entre aspas."""
    m = re.search(r"export function esc\(s\)\s*\{(.*?)\n\}", fonte("util.js"), re.S)
    assert m, "util.js não exporta esc(s)"
    corpo = m.group(1)
    classe = re.search(r"replace\(/\[([^\]]+)\]/g", corpo)
    assert classe and set(classe.group(1)) == set("&<>\"'")
    for car, ent in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;"), ("'", "&#39;")):
        assert re.search(re.escape(repr(car)[1:-1] if car != "'" else "'") + r"['\"]?\s*:\s*['\"]" + re.escape(ent), corpo), car
    assert "String(s ??" in corpo  # null/undefined viram texto vazio, não "undefined"


def test_nao_ha_sinks_de_execucao_direta():
    """Nenhum .js usa document.write, eval, new Function, outerHTML, insertAdjacentHTML ou srcdoc;
    index.html não tem atributo on*= nem URL javascript:."""
    proibidos = re.compile(r"document\.write|\beval\(|new Function|outerHTML|insertAdjacentHTML|srcdoc")
    for nome in arquivos_js():
        assert not proibidos.search(fonte(nome)), nome
    html = fonte("index.html")
    assert not re.search(r"\son[a-z]+\s*=", html) and "javascript:" not in html


# Interpolações de campo de TEXTO (nome, id, aviso, mensagem...) que NÃO passam por esc() e foram
# revisadas uma a uma: o destino não é HTML, ou o valor é constante do código, ou é escapado depois.
REVISADAS = {
    # V3: identificadores de malha/contexto; não são inseridos em HTML.
    ("cenario_apresentacao.js", "atividade.id"): "elementoId em Mesh.userData; seleção usa ID como chave",
    ("cenario_apresentacao.js", "nome"): "sufixo de elementoId em Mesh.userData; _caixa não escreve no DOM",
    ("cenario_apresentacao.js", "a.id"): "elementoId dos dormentes em InstancedMesh.userData",
    ("cenario_apresentacao.js", "o.id"): "nome interno passado a _caixa, termina em Mesh.userData.elementoId",
    ("api.js", "r.status"): "mensagem de ErroApi (texto)", ("api.js", "k"): "dentro de encodeURIComponent",
    ("app.js", "l.id"): "passa por opt(), que escapa", ("app.js", "l.nome"): "passa por opt(), que escapa",
    ("app.js", "s"): "passa por opt(), que escapa", ("app.js", "r.estaca"): "textContent (#v-hover)",
    ("app.js", "lado"): "textContent (#v-hover)", ("app.js", "ref.lote.id"): "dentro de esc(...)",
    ("app.js", "ref.lote.construtora"): "dentro de esc(...)", ("app.js", "e.message"): "erroGlobal usa textContent",
    ("app.js", "obras[0].id"): "erroGlobal usa textContent",
    ("cronoimport.js", "c"): "constante CENARIOS", ("cronoimport.js", "e.message"): "erro é exibido com esc(erro)",
    ("estado.js", "l.nome"): "rótulo de grupo: textContent no Gantt", ("estado.js", "l.construtora"): "idem",
    ("estado.js", "s.id"): "idem", ("estado.js", "l.id"): "idem / chave interna",
    ("fiscalizacao.js", "id"): "constante CAMPOS", ("fiscalizacao.js", "k"): "constante ESTADOS",
    ("fiscalizacao.js", "tipo"): "constante CAMPOS",
    ("gantt.js", "COR.status"): "constante", ("gantt.js", "id"): "constante local", ("gantt.js", "c"): "número",
    ("linhabalanco.js", "k"): "número em textContent",
    ("painel.js", "a.nivel"): "classe CSS; valor fixo do backend ('alto'/'medio')", ("painel.js", "c"): "classe calculada",
    ("recursos.js", "c"): "constante CENARIOS", ("recursos.js", "aviso"): "HTML montado com esc",
    ("recursos.js", "p.periodo"): "chave de Map", ("recursos.js", "g"): "chave de Map",
    ("simulacao.js", "crit.a.id"): "rótulo exibido com esc(e.rotulo)", ("simulacao.js", "crit.a.unidade"): "idem",
    ("simulacao.js", "folga.a.id"): "idem", ("simulacao.js", "folga.a.unidade"): "idem",
    ("simulacao.js", "a.servico_id"): "descreverAjuste: exibido com esc(t)",
    ("simulacao.js", "a.unidade"): "textContent", ("simulacao.js", "linha.unidade"): "textContent",
    ("simulacao.js", "e.message"): "msg.texto exibido com esc", ("simulacao.js", "texto"): "constante local",
    ("viewer3d.js", "a.id"): "userData", ("viewer3d.js", "l.id"): "rótulo: textContent",
    ("viewer3d.js", "l.construtora"): "rótulo: textContent", ("viewer3d.js", "o.id"): "rótulo: textContent",
    ("viewer3d.js", "k"): "rótulo: textContent",
    # tour.js — revisadas no fechamento da rodada 7 (justificativas do frontend conferidas no código)
    ("tour.js", "o.tipo"): "só no título do passo, que entra no HTML por esc(s.titulo) em render(); a outra "
                           "leitura (estadoTour().titulo) devolve o texto a quem chama, não ao DOM",
    ("tour.js", "k"): "parâmetro de textoSimulacao, chamado só com as constantes 'sim1'/'sim2'; vira chave de "
                      "N(), que a escapa em data-num",
    ("tour.js", "texto"): "HTML montado pelo próprio tour; conferi cada passo: todo dado externo passa por N()/D() "
                          "(que escapam chave e valor), esc() ou num(); o erro do passo entra por esc(erroPasso)",
}
# Confirmadas como defeito e ainda abertas (nenhuma: as duas da rodada 7 — id de lote em simulacao.js e id de
# serviço em viewer3d.js — foram corrigidas e viraram regressão em test_sink_sem_escape_foi_corrigido).
DEFEITOS: set = set()

_CAMPO_TEXTO = (r"(id|nome|descricao|texto|aviso|mensagem|origem|unidade|construtora|estaca|motivo|lado|tipo|regra|"
                r"recurso|servico_id|lote_id|atividade_id|segmento_id|status|nivel|message|erro|nota|rotulo|formato|"
                r"correlacao|fonte_produtividade|formula|periodo|servico|lote|segmento)")
_INTERP = re.compile(r"\$\{\s*((?:[A-Za-z_$][\w$]*)(?:\??\.[A-Za-z_$][\w$]*|\[[^\]]*\])*)\s*\}")


def interpolacoes_de_texto_sem_escape():
    achadas = set()
    for nome in arquivos_js():
        for m in _INTERP.finditer(fonte(nome)):
            e = m.group(1)
            ultimo = re.split(r"[.\[]", e)[-1].rstrip("]")
            if re.fullmatch(_CAMPO_TEXTO, ultimo) or e in ("id", "s", "g", "k", "c", "sv"):
                achadas.add((nome, e))
    return achadas


def test_toda_interpolacao_de_campo_de_texto_sem_esc_foi_revisada():
    """Varre todos os ``${a.b.campo}`` cujo último nome é de campo de texto (nome, id, aviso, mensagem,
    unidade, construtora, status...) e que NÃO estão envolvidos por esc(). O conjunto achado tem de estar
    contido na lista REVISADAS (cada item com a justificativa) mais os dois DEFEITOS conhecidos.
    Interpolação nova sem esc() faz o teste falhar até alguém revisar e justificar."""
    novas = interpolacoes_de_texto_sem_escape() - set(REVISADAS) - DEFEITOS
    assert not novas, f"interpolações de texto sem esc() ainda não revisadas: {sorted(novas)}"


def test_a_api_entrega_o_dado_malicioso_cru_como_json(tmp_path):
    """O backend não deve (nem precisa) higienizar: nome de atividade, término contratual e extensão com a
    carga saem crus em JSON. Logo a defesa é TODA do frontend — é o que os testes seguintes cobram."""
    from infra4d.api import criar_app
    d = copy.deepcopy(Projeto.carregar().dados)
    d["atividades"][5]["nome"] = CARGA
    d["meta"]["termino_linha_base"] = CARGA
    d["ferrovia"]["extensao_km"] = CARGA
    c = TestClient(criar_app(fontes={"ferrovia": Projeto(d)}), raise_server_exceptions=False)
    assert c.get("/api/painel").json()["termino_contratual"] == CARGA
    assert c.get("/api/obras").json()[0]["extensao_km"] == CARGA
    assert CARGA in {a["nome"] for a in c.get("/api/projeto").json()["atividades"]}


# =============================================================================
# 1b. XSS — defeitos da rodada 7, hoje regressão (sinks sem escape com dado dos dados/da API)
# =============================================================================
SINKS = {
    "simulacao.js: id de lote em <option> (valor e texto)":
        ("simulacao.js", r'<option value="\$\{l\.id\}"[^`]*>\$\{l\.id\}</option>'),
    "viewer3d.js: id de serviço na legenda 3D (innerHTML em app.js)":
        ("viewer3d.js", r"</i>\$\{id\}\$\{plano\.genericos\.includes"),
    "viewer3d.js: lista de serviços genéricos na legenda 3D":
        ("viewer3d.js", r"<b>\$\{plano\.genericos\.join\(', '\)\}</b>"),
    "app.js: extensão da obra no seletor de obras":
        ("app.js", r"\$\{esc\(o\.tipo\)\}, \$\{o\.extensao_km\} km</option>"),
    "painel.js: impacto do risco (lista de riscos da v2)":
        ("painel.js", r"\+\$\{r\.impacto_dias_uteis\} d\.u\."),
    "painel.js: meses de chuva":
        ("painel.js", r"\$\{\(chuva\.meses \|\| \[\]\)\.join\(', '\)\}"),
}


@pytest.mark.parametrize("sink", sorted(SINKS))
def test_sink_sem_escape_foi_corrigido(sink):
    """Cada trecho abaixo interpola dado externo direto em HTML. Corrigido = o trecho não existe mais
    nessa forma (passou a usar esc(...) ou num(...))."""
    arquivo, padrao = SINKS[sink]
    assert not re.search(padrao, fonte(arquivo)), f"{arquivo}: {padrao}"


def test_databr_valida_o_formato_ou_escapa():
    """dataBR('<img src=x onerror=alert(1)>') hoje devolve 'undefined/undefined/<img src=x onerror=alert(1)>'.
    Esperado: validar AAAA-MM-DD (devolver '—' se não casar) ou escapar a saída."""
    m = re.search(r"export function dataBR\(iso\)\s*\{(.*?)\n\}", fonte("util.js"), re.S)
    assert m
    corpo = m.group(1)
    assert "esc(" in corpo or re.search(r"\\d\{4\}-\\d\{2\}-\\d\{2\}", corpo)


def test_pagina_e_servida_com_csp():
    """GET / tem de trazer Content-Security-Policy (sem 'unsafe-inline' em script-src) e nosniff."""
    from infra4d.api import criar_app
    r = TestClient(criar_app(), raise_server_exceptions=False).get("/")
    csp = r.headers.get("content-security-policy", "")
    assert csp and "unsafe-inline" not in csp.split("script-src")[-1].split(";")[0]
    assert r.headers.get("x-content-type-options") == "nosniff"


# =============================================================================
# 2. Coerência com o backend
# =============================================================================
def test_o_navegador_nao_calcula_estaca():
    """A estaca mostrada vem SEMPRE da API: nenhum .js de web/ contém a conta local removida (estacaDe,
    metrosEstaca, calibrarEstaca) nem divide por 20 para montar "N+dd,dd"; web/estacas.js existe, busca em
    /api/referencia/km (via api.referenciaKm, cujo caminho é esse) e escapa o texto recebido.
    Histórico: a conta local divergia do backend com estaca de origem != 0 ou equação de estacas
    (km 2 aparecia como 300+00,00 com origem 100; a API dá 200+00,00). A prova em navegador, com
    estaca_origem = 100, está no e2e do frontend."""
    for nome in arquivos_js():
        src = fonte(nome)
        for proibido in ("estacaDe", "metrosEstaca", "calibrarEstaca"):
            assert not re.search(rf"\b{proibido}\b", src), (nome, proibido)
    est = fonte("estacas.js")
    assert "api.referenciaKm(" in est and "esc(" in est
    assert re.search(r"referenciaKm:\s*\(km\)\s*=>\s*req\('GET',\s*`/api/referencia/km\?km=", fonte("api.js"))
    assert not re.search(r"/\s*20\b|\*\s*20\b|toFixed\(2\)\.replace\('\.', ','\)\.padStart", est)


def test_fracao_executada_do_cliente_usa_percentual_executado():
    """A função do cliente tem de considerar ``percentual_executado`` (regra do backend para atividade sem
    quantidade)."""
    m = re.search(r"export function fracaoExecutada\(a\)\s*\{(.*?)\n\}", fonte("estado.js"), re.S)
    assert m and "percentual_executado" in m.group(1)


def test_cliente_trata_detail_em_objeto():
    """O backend tem pelo menos uma resposta de erro cujo detail é objeto; o cliente precisa extrair a
    mensagem (det.erro / det.mensagem / JSON.stringify)."""
    rotas = (RAIZ / "scripts" / "infra4d" / "importadores" / "rotas.py").read_text(encoding="utf-8")
    assert re.search(r"HTTPException\(422, \{", rotas), "o backend deixou de mandar detail em objeto: remova este teste"
    api = fonte("api.js")
    assert re.search(r"typeof det === 'object'|det\.erro|JSON\.stringify\(det\)", api)


# =============================================================================
# 3. Robustez — estático
# =============================================================================
def test_ha_tratador_global_de_excecao_nao_capturada():
    """Algum .js tem de registrar 'unhandledrejection' (e 'error') e levar a mensagem ao #erro-global."""
    tudo = "\n".join(fonte(n) for n in arquivos_js())
    assert "unhandledrejection" in tudo


# =============================================================================
# 4. Roteiros que exigem navegador (para o e2e do agente de frontend)
# =============================================================================
@pytest.mark.skip(reason="exige navegador: XSS por id de lote na aba Simulação (simulacao.js, <option> sem esc)")
def test_roteiro_xss_id_de_lote_na_simulacao():
    """Dado injetado: cópia de examples/synthetic/ferrovia_ficticia.json com
        lotes[0].id = 'L1"><img src=x onerror="window.__xss=1'
      e a mesma troca em todo lote_id que apontava para L1 (atividades, segmentos).
    Passos: subir a API com esse arquivo (criar_app(fontes={'ferrovia': Projeto(d)})); abrir /#simulacao;
      marcar o modo "Serviço + lote".
    Esperado: window.__xss continua undefined; o <select id="s-lote"> tem uma <option> cujo texto é o id
      literal (com os sinais < > visíveis) e document.querySelectorAll('#simulacao img').length === 0.
    (Corrigido após a rodada 7; o roteiro fica como regressão para o e2e.)"""


@pytest.mark.skip(reason="exige navegador: XSS por id de serviço na legenda do 3D (viewer3d.js legendaHTML)")
def test_roteiro_xss_id_de_servico_na_legenda_3d():
    """Dado injetado: no JSON da obra, servicos[0].id = '<img src=x onerror=window.__xss=2>' e o mesmo valor
      em servico_id de todas as atividades daquele serviço.
    Passos: abrir /#modelo; no seletor "Colorir por" escolher "Serviço".
    Esperado: #legenda-3d mostra o id como texto; nenhum <img> dentro de #legenda-3d; window.__xss undefined.
    (Corrigido após a rodada 7; o roteiro fica como regressão para o e2e.)"""


@pytest.mark.skip(reason="exige navegador: XSS por meta.termino_linha_base via dataBR (apresentacao.js e painel.js)")
def test_roteiro_xss_termino_contratual():
    """Dado injetado: meta.termino_linha_base = '<img src=x onerror=window.__xss=3>' (o backend não interpreta
      esse campo: /api/painel devolve-o em termino_contratual; conferido em
      test_a_api_entrega_o_dado_malicioso_cru_como_json).
    Passos: abrir / (aba Apresentação) e depois /#painel.
    Esperado: os dois lugares mostram '—' (ou o texto escapado); window.__xss undefined.
    (Corrigido após a rodada 7; o roteiro fica como regressão para o e2e.)"""


@pytest.mark.skip(reason="exige navegador: nome de atividade malicioso tem de aparecer como texto em TODAS as abas")
def test_roteiro_nome_de_atividade_malicioso_e_inerte():
    """Dado injetado: atividades[i].nome = '<img src=x onerror=window.__xss=4>' numa atividade em andamento
      por quantidade e que esteja na cadeia determinante (ex.: a primeira de /api/cenarios/independente
      .cadeia_determinante que seja em andamento).
    Passos: abrir cada aba (#modelo, #gantt, #balanco, #painel, #simulacao, #recursos, #fiscalizacao,
      #cronograma); no Gantt passar o mouse sobre a barra e clicar nela (tooltip + painel de detalhes);
      na aba Cronograma clicar "Usar exemplo".
    Esperado: em todas, window.__xss undefined e document.querySelectorAll('img[src="x"]').length === 0;
      o nome aparece literal no painel de detalhes e no tooltip.
    Pela leitura do código isso JÁ deve passar (todas as ocorrências de a.nome usam esc ou textContent);
      o roteiro existe para o e2e travar a regressão."""


@pytest.mark.skip(reason="exige navegador: respostas 4xx/5xx e campos ausentes não podem deixar a aba em branco")
def test_roteiro_respostas_de_erro_e_campos_ausentes():
    """Interceptar no navegador (page.route no Playwright), um caso por vez, recarregando a página:
    (a) GET /api/painel -> 200 com corpo {}                     -> esperado: aba Painel mostra mensagem de erro
        legível (não fica em 'Carregando painel…' nem vazia) e o console não tem exceção não tratada.
    (b) GET /api/simulacao -> 200 com {"comparacao": {}}        -> aba Simulação mostra erro; hoje
        `sim.ajustes.length` estoura.
    (c) GET /api/cenarios/independente -> 500 (texto simples)   -> faixa #erro-global visível com
        'Erro HTTP 500' e botão "Tentar de novo" funcionando depois de remover a interceptação.
    (d) GET /api/projeto -> 200 com corpo 'ok' (não JSON)       -> faixa #erro-global visível; hoje req()
        devolve null e `indexarProjeto(null)` estoura (cai no catch de carregar: conferir a mensagem).
    (e) POST /api/cronograma/comparar com um .xer cuja rede tem ciclo -> a mensagem mostrada tem de conter
        o texto do erro do backend, não '[object Object]'.
    (f) GET /api/fiscalizacao/diario -> 409 {"detail": "…só roda sobre obra marcada como FICTÍCIA…"}
        -> a aba Fiscalização mostra essa mensagem no bloco do diário e os outros blocos continuam."""


@pytest.mark.skip(reason="exige navegador: estaca mostrada no tooltip da linha de balanço x /api/referencia/km")
def test_roteiro_estaca_do_tooltip_igual_a_api():
    """Dado injetado: meta.estaca_origem = 100 no JSON da obra.
    Passos: abrir /#balanco; passar o mouse sobre a linha de uma atividade cujo km_ini seja 5;
      ler a estaca do tooltip; chamar fetch('/api/referencia/km?km=5').then(r => r.json()).
    Esperado: a estaca do tooltip é igual a .estaca da API ('350+00,00').
    (Corrigido após a rodada 7; o roteiro fica como regressão para o e2e.)"""
