"""Rotas de comparação de revisões de cronograma: ``/api/revisoes``.

Ligação (contrato multi-obra): ``ligar(app, obter_estado)``.

- ``GET  /api/revisoes/comparar?obra=&a=linha_base&b=construtora``: duas versões da própria obra
  (cenários do motor).
- ``POST /api/revisoes/comparar?obra=``: duas versões em ARQUIVO (MSPDI ou XER). Como o ambiente não
  tem ``python-multipart``, o corpo é JSON::

      {"a": {"conteudo": "<texto do .xml/.xer>"}, "b": {"conteudo_base64": "<bytes em base64>"},
       "efeitos_isolados": true}

  Cada lado aceita ``conteudo`` (texto) OU ``conteudo_base64`` (bytes; use para XER em cp1252), e
  ``formato`` opcional (``mspdi``/``xer``; padrão: detectado). Um lado pode ser também
  ``{"cenario": "construtora"}`` (versão do motor da obra).

O prefixo é ``/api/revisoes`` e não ``/api/cronograma/comparar`` porque essa rota já existe
(importado × cenário do motor, em ``importadores/rotas.py``).
"""

from __future__ import annotations

import base64
import binascii
import json

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request

from .calendario import ErroCalendario
from .comparar_revisoes import ErroComparacao, comparar_revisoes, versao_do_cenario, versao_importada
from .motor import ErroRede

router = APIRouter(prefix="/api/revisoes", tags=["revisões de cronograma"],
                   responses={404: {"description": "Obra desconhecida"}, 503: {"description": "Rotas não ligadas ao app"}})
_ATTR = "revisoes_obter_estado"
CENARIOS = ("linha_base", "construtora", "independente", "simulado")
MAX_CORPO = 40 * 1024 * 1024


def ligar(app: FastAPI, obter_estado) -> None:
    setattr(app.state, _ATTR, obter_estado)
    app.include_router(router)


def _estado(request: Request, obra):
    f = getattr(request.app.state, _ATTR, None)
    if f is None:
        raise HTTPException(503, "rotas de revisões não ligadas: chame rotas_revisoes.ligar(app, obter_estado)")
    return f(obra)


def _versao_cenario(est, cenario: str):
    if cenario not in CENARIOS:
        raise HTTPException(422, f"cenário inválido: {cenario!r}; use um de {', '.join(CENARIOS)}")
    ajustes = getattr(est, "ajustes", None) if cenario == "simulado" else None
    return versao_do_cenario(est.projeto, cenario, ajustes)


def _comparar(a, b, efeitos: bool, agrupar: bool = True) -> dict:
    try:
        return comparar_revisoes(a, b, efeitos_isolados=efeitos, agrupar_progresso_=agrupar)
    except (ErroRede, ErroCalendario) as e:
        raise HTTPException(422, f"uma das versões é uma rede inválida para o motor: {e}") from None
    except ErroComparacao as e:
        raise HTTPException(422, str(e)) from None


@router.get("/comparar", responses={422: {"description": "Cenário inválido ou versão que o motor rejeita"}})
def comparar_cenarios(request: Request, obra: str | None = Query(None), a: str = Query("linha_base"),
                      b: str = Query("construtora"), efeitos_isolados: bool = Query(True),
                      agrupar_progresso: bool = Query(True)):
    """Compara duas versões da própria obra (cenários do motor): mudanças, término A × B, efeito isolado por mudança, resíduo de interação, reconstrução e alertas."""
    est = _estado(request, obra)
    return _comparar(_versao_cenario(est, a), _versao_cenario(est, b), efeitos_isolados, agrupar_progresso)


def _versao_arquivo(est, lado: str, spec) -> object:
    from .importadores.comum import ErroImportacao
    from .importadores.mspdi import importar_mspdi
    from .importadores.xer import importar_xer

    if not isinstance(spec, dict):
        raise HTTPException(422, f"'{lado}' deve ser um objeto")
    if "cenario" in spec:
        return _versao_cenario(est, str(spec["cenario"]))
    if "conteudo_base64" in spec:
        try:
            dados = base64.b64decode(str(spec["conteudo_base64"]), validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(422, f"'{lado}.conteudo_base64' não é base64 válido") from None
    elif isinstance(spec.get("conteudo"), str):
        dados = spec["conteudo"].encode("utf-8")
    else:
        raise HTTPException(422, f"'{lado}' precisa de 'conteudo', 'conteudo_base64' ou 'cenario'")
    fmt = spec.get("formato")
    if fmt is None:
        inicio = dados[:64].lstrip(b"\xef\xbb\xbf \t\r\n")
        fmt = "xer" if inicio.startswith(b"ERMHDR") else "mspdi" if inicio.startswith(b"<") else None
    if fmt not in ("mspdi", "xer"):
        raise HTTPException(415, f"'{lado}': formato não reconhecido (esperado MSPDI ou XER)")
    try:
        imp = importar_xer(dados) if fmt == "xer" else importar_mspdi(dados)
    except ErroImportacao as e:
        raise HTTPException(422, f"'{lado}': arquivo {fmt.upper()} não importado: {e}") from None
    return versao_importada(imp, f"versão {lado.upper()}")


@router.post("/comparar", responses={413: {"description": "Corpo acima do limite"}, 415: {"description": "Formato de arquivo não reconhecido"}, 422: {"description": "JSON inválido, lado ausente, base64 ruim, arquivo não importado ou rede rejeitada pelo motor"}})
async def comparar_arquivos(request: Request, obra: str | None = Query(None)):
    """Compara duas versões enviadas como arquivo (MSPDI ou XER, em JSON: conteudo ou conteudo_base64) ou cenário da obra."""
    est = _estado(request, obra)
    corpo = bytearray()
    async for parte in request.stream():
        corpo.extend(parte)
        if len(corpo) > MAX_CORPO:
            raise HTTPException(413, f"corpo maior que {MAX_CORPO // (1024 * 1024)} MB")
    try:
        js = json.loads(bytes(corpo) or b"null")
    except (ValueError, RecursionError):
        raise HTTPException(422, "corpo não é JSON válido (multipart não é suportado; veja a documentação da rota)") \
            from None
    if not isinstance(js, dict) or "a" not in js or "b" not in js:
        raise HTTPException(422, "corpo JSON precisa de 'a' e 'b'")
    opcoes = {}
    for chave in ("efeitos_isolados", "agrupar_progresso"):
        v = js.get(chave, True)
        if not isinstance(v, bool):  # r16: o texto "false" virava True
            raise HTTPException(422, f"'{chave}' deve ser booleano JSON (true/false), não {v!r}")
        opcoes[chave] = v
    va, vb = _versao_arquivo(est, "a", js["a"]), _versao_arquivo(est, "b", js["b"])
    return _comparar(va, vb, opcoes["efeitos_isolados"], opcoes["agrupar_progresso"])
