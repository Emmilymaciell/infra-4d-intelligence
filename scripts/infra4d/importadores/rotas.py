"""Rotas FastAPI de cronograma: exportar MSPDI, importar MSPDI/XER e comparar com o motor.

Ligação (contrato multi-obra do ``api.py``, que chama ``registrar_rotas``):

    from infra4d.importadores import rotas
    rotas.ligar(app, obter_estado)

``obter_estado(obra: str | None)`` devolve um objeto com ``.projeto`` (``cenarios.Projeto``)
e ``.resultado(cenario)`` (dict de ``cenarios.executar``); para obra desconhecida ele
mesmo levanta HTTPException 404. ``ligar`` guarda o provedor em ``app.state`` (cada app
tem o seu; dois apps no mesmo processo não se misturam). ``configurar(obter_estado)`` +
``router`` também funciona (provedor global de reserva).

Upload: o ambiente NÃO tem ``python-multipart``; as rotas POST recebem o arquivo no
CORPO bruto (``Content-Type`` text/xml, application/xml, text/plain ou
application/octet-stream). Formato detectado pelo conteúdo, ou forçado com
``?formato=mspdi|xer``. Exemplo:

    curl -X POST --data-binary @cronograma.xer -H "Content-Type: text/plain" \
         "http://127.0.0.1:8765/api/cronograma/comparar?obra=ferrovia"
"""

from __future__ import annotations

from datetime import date
from typing import Callable

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import Response

from ..calendario import ErroCalendario, iso
from ..motor import ErroRede, calcular
from .comum import ErroImportacao
from .mspdi import exportar_mspdi, importar_mspdi
from .xer import importar_xer

router = APIRouter(prefix="/api/cronograma", tags=["cronograma"],
                   responses={404: {"description": "Obra desconhecida (parâmetro obra)"}, 503: {"description": "Rotas não ligadas ao app (ligar não foi chamado)"}})

TAMANHO_MAXIMO = 20 * 1024 * 1024  # 20 MB
CENARIOS_VALIDOS = ("linha_base", "construtora", "independente", "simulado")
_ATRIBUTO_APP = "cronograma_obter_estado"
_reserva: dict[str, Callable | None] = {"obter_estado": None}


def ligar(app: FastAPI, obter_estado: Callable) -> None:
    """Inclui o router no ``app`` e guarda ``obter_estado`` no ``app.state``."""
    setattr(app.state, _ATRIBUTO_APP, obter_estado)
    app.include_router(router)


def configurar(obter_estado: Callable) -> None:
    """Forma alternativa do contrato (``router`` + ``configurar``): provedor global."""
    _reserva["obter_estado"] = obter_estado


def _estado(request: Request, obra: str | None):
    f = getattr(request.app.state, _ATRIBUTO_APP, None) or _reserva["obter_estado"]
    if f is None:
        raise HTTPException(503, "rotas de cronograma não ligadas: chame rotas.ligar(app, obter_estado)")
    return f(obra)


@router.get("/exportar/mspdi", responses={422: {"description": "Cenário inválido"}})
def exportar(request: Request, cenario: str = Query("independente"), obra: str | None = Query(None)):
    """Baixa o cronograma do cenário em MS Project XML (MSPDI). Validado só por ida e volta com o importador próprio; compatibilidade com o MS Project real não é alegada."""
    if cenario not in CENARIOS_VALIDOS:
        raise HTTPException(422, f"cenário inválido: {cenario!r}; use um de {', '.join(CENARIOS_VALIDOS)}")
    est = _estado(request, obra)
    xml = exportar_mspdi(est.projeto, est.resultado(cenario))
    nome = f"infra4d-{_nome_seguro(obra)}-{cenario}.xml"
    return Response(content=xml.encode("utf-8"), media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


def _nome_seguro(texto: str | None) -> str:
    """Trecho de nome de arquivo para o Content-Disposition: só [A-Za-z0-9._-]."""
    import re
    return (re.sub(r"[^A-Za-z0-9._-]+", "_", texto or "").strip("._") or "obra")[:80]


@router.get("/exportar/xer", responses={422: {"description": "Cenário inválido"}})
def exportar_xer_rota(request: Request, cenario: str = Query("independente"), obra: str | None = Query(None)):
    """XER (Primavera P6) do cenário. Validado só por ida e volta com o importador próprio."""
    from .xer_exportar import exportar_xer

    if cenario not in CENARIOS_VALIDOS:
        raise HTTPException(422, f"cenário inválido: {cenario!r}; use um de {', '.join(CENARIOS_VALIDOS)}")
    est = _estado(request, obra)
    xer = exportar_xer(est.projeto, est.resultado(cenario))
    nome = f"infra4d-{_nome_seguro(obra)}-{cenario}.xer"
    return Response(content=xer.encode("utf-8"), media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


def _detectar(corpo: bytes) -> str | None:
    inicio = corpo[:64].lstrip(b"\xef\xbb\xbf \t\r\n")
    if inicio.startswith(b"ERMHDR"):
        return "xer"
    if inicio.startswith(b"<"):
        return "mspdi"
    return None


async def _ler_corpo(request: Request) -> bytes:
    ctype = (request.headers.get("content-type") or "").lower()
    if ctype.startswith("multipart/"):
        raise HTTPException(415, "upload multipart não suportado (python-multipart não está instalado); "
                                 "envie o arquivo no corpo bruto (text/xml, text/plain ou application/octet-stream)")
    corpo = bytearray()
    async for parte in request.stream():
        corpo.extend(parte)
        if len(corpo) > TAMANHO_MAXIMO:
            raise HTTPException(413, f"arquivo maior que {TAMANHO_MAXIMO // (1024 * 1024)} MB")
    if not bytes(corpo).strip():
        raise HTTPException(400, "corpo vazio: envie o conteúdo do .xml (MSPDI) ou do .xer")
    return bytes(corpo)


def _importar(corpo: bytes, formato: str | None):
    fmt = formato or _detectar(corpo)
    if fmt is None:
        raise HTTPException(415, "formato não reconhecido: esperado MSPDI (XML) ou XER (começa com ERMHDR)")
    try:
        return importar_xer(corpo) if fmt == "xer" else importar_mspdi(corpo)
    except ErroImportacao as e:
        raise HTTPException(422, f"arquivo {fmt.upper()} não importado: {e}") from None
    except (LookupError, OverflowError, RecursionError, ValueError, TypeError) as e:
        # rede de segurança: os importadores já convertem; nada de 500 por entrada ruim (rodada 5)
        raise HTTPException(422, f"arquivo {fmt.upper()} não importado: {type(e).__name__}") from None


def _calcular(dados):
    ativs, rels, cals, meta = dados
    try:
        return calcular(ativs, rels, cals, meta["inicio_projeto"], data_status=meta.get("data_status"))
    except (ErroRede, ErroCalendario, OverflowError, RecursionError, ValueError) as e:
        raise HTTPException(422, {"erro": f"rede importada rejeitada pelo motor: {e}",
                                  "avisos": meta.get("avisos", [])}) from None


def resumir(atividades, relacoes, calendarios, metadados, res=None) -> dict:
    """Resumo da importação com o término recalculado pelo motor próprio."""
    if res is None:
        res = calcular(atividades, relacoes, calendarios, metadados["inicio_projeto"],
                       data_status=metadados.get("data_status"))
    contagem = {}
    for a in atividades:
        contagem[a.status] = contagem.get(a.status, 0) + 1
    return {
        "formato": metadados["formato"],
        "nome": metadados.get("nome"),
        "n_atividades": len(atividades),
        "n_relacoes": len(relacoes),
        "n_calendarios": len(calendarios),
        "por_status": contagem,
        "inicio_projeto": iso(metadados["inicio_projeto"]),
        "data_status": iso(metadados.get("data_status")),
        "termino_calculado": iso(res.termino_projeto_data),
        "n_criticas": len(res.caminho_critico),
        "cadeia_determinante": res.cadeia_determinante,
        "calculado_por": "motor CPM próprio (ADR-0003); datas do arquivo não são usadas",
        "avisos": metadados.get("avisos", []),
        "limitacoes": metadados.get("limitacoes", []),
    }


@router.post("/importar", responses={400: {"description": "Corpo vazio"}, 413: {"description": "Arquivo acima do limite de tamanho"}, 415: {"description": "Formato não reconhecido ou multipart (envie o arquivo no corpo bruto)"}, 422: {"description": "Arquivo inválido, recusado pela validação ou rede rejeitada pelo motor"}})
async def importar(request: Request, formato: str | None = Query(None, pattern="^(mspdi|xer)$"),
                   obra: str | None = Query(None)):
    """Importa e recalcula. ``obra`` é aceita por uniformidade; não entra no cálculo."""
    dados = _importar(await _ler_corpo(request), formato)
    return resumir(*dados, res=_calcular(dados))


def comparar_com_cenario(dados, res, resultado_ref: dict) -> dict:
    """Compara o cronograma importado (tratado como 'o da construtora') com um resultado do motor.

    Casa atividades pelo id. Diferenças de término em dias CORRIDOS (positivo = o motor
    prevê depois do cronograma importado)."""
    ativs, _rels, cals, meta = dados
    por_id = {a.id: a for a in ativs}
    ref_ativs = resultado_ref["atividades"]
    linhas, so_importado = [], []
    for aid, r in res.atividades.items():
        a = por_id[aid]
        termino_imp = r.data_termino(cals[a.calendario], a)
        inicio_imp = r.data_inicio(cals[a.calendario], a)
        ref = ref_ativs.get(aid)
        if ref is None:
            so_importado.append(aid)
            continue
        t_ref = date.fromisoformat(ref["termino"]).toordinal()
        linhas.append({
            "id": aid,
            "nome": meta.get("nomes", {}).get(aid, aid),
            "status_importado": a.status, "status_motor": ref["status"],
            "duracao_importada": a.duracao, "duracao_motor": ref["duracao"],
            "delta_duracao": ref["duracao"] - a.duracao,
            "inicio_importado": iso(inicio_imp), "inicio_motor": ref["inicio"],
            "termino_importado": iso(termino_imp), "termino_motor": ref["termino"],
            "delta_termino_dias_corridos": t_ref - termino_imp,
            "critica_motor": ref.get("critica"),
            "fonte_produtividade_motor": (ref.get("memoria") or {}).get("fonte_produtividade"),
        })
    linhas.sort(key=lambda x: (-abs(x["delta_termino_dias_corridos"]), x["id"]))
    so_motor = sorted(set(ref_ativs) - set(res.atividades))
    t_imp = res.termino_projeto_data
    t_ref = date.fromisoformat(resultado_ref["termino"]).toordinal()
    return {
        "cenario_motor": resultado_ref["cenario"],
        "termino_importado": iso(t_imp),
        "termino_motor": resultado_ref["termino"],
        "delta_termino_dias_corridos": t_ref - t_imp,
        "n_casadas": len(linhas),
        "n_com_diferenca": sum(1 for x in linhas if x["delta_termino_dias_corridos"] or x["delta_duracao"]),
        "so_no_importado": so_importado,
        "so_no_motor": so_motor,
        "atividades": linhas,
        "leitura": ("Cronograma importado recalculado pelo motor próprio com as durações DO ARQUIVO; "
                    "comparado ao cenário do motor, cujas durações vêm da produtividade (medida no "
                    "independente). delta > 0: o motor prevê término mais tarde que o arquivo."),
    }


@router.post("/comparar", responses={400: {"description": "Corpo vazio"}, 413: {"description": "Arquivo acima do limite de tamanho"}, 415: {"description": "Formato não reconhecido ou multipart (envie o arquivo no corpo bruto)"}, 422: {"description": "Arquivo inválido, recusado pela validação ou rede rejeitada pelo motor"}})
async def comparar(request: Request, cenario: str = Query("independente"),
                   formato: str | None = Query(None, pattern="^(mspdi|xer)$"), obra: str | None = Query(None)):
    """Auditoria: 'a construtora manda o cronograma → comparamos com o cenário do motor'."""
    if cenario not in CENARIOS_VALIDOS:
        raise HTTPException(422, f"cenário inválido: {cenario!r}; use um de {', '.join(CENARIOS_VALIDOS)}")
    est = _estado(request, obra)  # 404 de obra desconhecida antes de ler o corpo
    dados = _importar(await _ler_corpo(request), formato)
    res = _calcular(dados)
    saida = comparar_com_cenario(dados, res, est.resultado(cenario))
    saida["importacao"] = resumir(*dados, res=res)
    return saida
