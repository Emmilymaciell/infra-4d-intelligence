"""Router FastAPI ``/api/ifc`` — ligado pelo ``registrar_rotas`` do ``api.py`` via ``ligar``.

Contrato (orquestrador): ``ligar(app, obter_estado)``, com ``obter_estado(obra) -> Estado``
(``Estado.projeto`` é o ``cenarios.Projeto``; obra desconhecida → HTTPException 404).
O ``obter_estado`` fica em ``app.state`` (não em global de módulo), então vários apps no mesmo
processo — caso dos testes — não se misturam.

Sem ``ifcopenshell`` instalado, importar este módulo levanta ``ImportError`` (import explícito
abaixo): o ``registrar_rotas`` registra o módulo como indisponível sem derrubar a API.

Endpoints (todos aceitam ``?obra=``; sem ela, a obra padrão do ``obter_estado``):

- ``GET  /api/ifc/exportar`` → download ``.ifc`` (IFC4X3_ADD2: IfcRailway ou IfcRoad conforme a obra).
- ``GET  /api/ifc/glb``      → download ``.glb`` (glTF 2.0 binário). Um nó por elemento, ``node.name``
  = GlobalId do IFC. Y para cima: glTF (x, y, z) = IFC (x, z, −y), em metros; origem = (0, 0, 0) do
  IFC = coordenadas ``alinhamento.pontos`` [x, y, cota] do JSON da obra (sem deslocamento).
- ``GET  /api/ifc/vinculo``  → tabela GlobalId → atividade/elemento/km da MESMA exportação do GLB.
- ``GET  /api/ifc/requisitos`` → requisitos de informação 4D/5D (R1–R6) do modelo exportado, mais a
  coerência das quantidades por atividade e o custo pelo modelo × orçamento (FICTÍCIO).
- ``POST /api/ifc/requisitos`` → os mesmos requisitos sobre um ``.ifc`` enviado no corpo (binário).
- ``POST /api/ifc/cronograma?cenario=`` → lê o cronograma nativo (IfcWorkSchedule do cenário) de um
  ``.ifc`` enviado, recalcula pelo motor e compara o término com o da API da obra.
- ``POST /api/ifc/vinculos`` → corpo = bytes de um ``.ifc`` qualquer (``application/octet-stream``,
  sem multipart). Devolve resumo, alinhamentos, tabela de vínculo e verificação contra a obra.

Os GlobalIds são determinísticos (uuid5 de obra + ElementoId), e as três rotas GET usam o mesmo
cache por obra + assinatura dos dados: GLB e vínculo sempre casam.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import threading
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

import ifcopenshell  # noqa: F401 — ImportError aqui é o sinal de "módulo indisponível" para a API
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import Response

from ..cenarios import Projeto
from . import exportar as _exp
from . import importar as _imp
from . import requisitos as _req

LIMITE_BYTES = 100 * 1024 * 1024  # 100 MB por upload no beta local
CHAVE_ESTADO = "ifc_obter_estado"
MAX_CACHE = 4  # exportações em memória (IFC ~1,5 MB + GLB ~0,7 MB cada)

router = APIRouter(prefix="/api/ifc", tags=["ifc"],
                   responses={404: {"description": "obra desconhecida (parâmetro ?obra=)"}})


def ligar(app: FastAPI, obter_estado) -> None:
    """Forma 1 do contrato de integração."""
    setattr(app.state, CHAVE_ESTADO, obter_estado)
    app.include_router(router)


@lru_cache(maxsize=1)
def _projeto_padrao() -> Projeto:
    return Projeto.carregar()


def obter_ajustes(request: Request, obra: str | None = Query(None)) -> list:
    """Ajustes da simulação corrente da obra (o cenário ``simulado`` só vai para o IFC quando há)."""
    obter_estado = getattr(request.app.state, CHAVE_ESTADO, None)
    if obter_estado is None:
        return []
    return list(getattr(obter_estado(obra), "ajustes", None) or [])


def obter_projeto(request: Request, obra: str | None = Query(None)) -> Projeto:
    """Projeto da obra pedida. Fora do ``api.py`` (sem ``ligar``), cai na base sintética padrão.
    Também substituível via ``app.dependency_overrides``."""
    obter_estado = getattr(request.app.state, CHAVE_ESTADO, None)
    if obter_estado is None:
        return _projeto_padrao()
    return obter_estado(obra).projeto  # obra desconhecida: o próprio obter_estado levanta 404


# ---------------------------------------------------------------------------
# Cache de exportação por (assinatura dos dados, incluir_4d)
# ---------------------------------------------------------------------------

class _Exportacao:
    def __init__(self, dados: dict, incluir_4d: bool, ajustes: list | None = None):
        self.dados = dados
        self.incluir_4d = incluir_4d
        self.ajustes = list(ajustes or [])
        self.lock = threading.Lock()
        self._texto: str | None = None
        self._glb: bytes | None = None
        self._vinculo: dict | None = None
        self._requisitos: dict | None = None

    def texto(self) -> str:
        with self.lock:
            if self._texto is None:
                self._texto = _exp.para_texto(self.dados, incluir_4d=self.incluir_4d, ajustes=self.ajustes)
            return self._texto

    def glb(self) -> bytes:
        with self.lock:
            if self._glb is None:
                # Mesma geometria e MESMOS GlobalIds do .ifc (testado: diferença ≤ 1e-10 m), mas com
                # IfcLocalPlacement: triangular peças com IfcLinearPlacement faz o núcleo C++ do
                # IfcOpenShell 0.9.0.post1 escrever uma linha de depuração por peça no stdout do servidor.
                f, _ = _exp.construir(self.dados, incluir_4d=False, posicionamento="local")
                with tempfile.TemporaryDirectory(prefix="infra4d-glb-") as d:
                    caminho = Path(d) / "modelo.glb"  # o serializador exige caminho em disco
                    _imp.exportar_glb(f, caminho)
                    self._glb = caminho.read_bytes()
            return self._glb

    def requisitos(self) -> dict:
        texto = self.texto()
        with self.lock:
            if self._requisitos is None:
                f = ifcopenshell.file.from_string(texto)
                self._requisitos = {"requisitos": _req.verificar(f, self.dados),
                                    "quantidades": _req.coerencia(f, self.dados),
                                    "custo_modelo": _req.custo_modelo(f, self.dados, _exp.tipo_obra(self.dados))}
            return self._requisitos

    def vinculo(self) -> dict:
        texto = self.texto()
        with self.lock:
            if self._vinculo is None:
                f = ifcopenshell.file.from_string(texto)
                linhas = _imp.tabela_vinculo(f)
                self._vinculo = {"resumo": _imp.resumo(f, linhas), "alinhamentos": _imp.alinhamentos(f),
                                 "vinculos": linhas}
            return self._vinculo


_cache: OrderedDict[tuple, _Exportacao] = OrderedDict()
_cache_lock = threading.Lock()


def _assinatura(dados: dict) -> str:
    return hashlib.sha256(json.dumps(dados, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _exportacao(projeto: Projeto, incluir_4d: bool = True, ajustes: list | None = None) -> _Exportacao:
    tipo = _exp.tipo_obra(projeto.dados)
    if tipo not in _exp.INSTALACAO:
        raise HTTPException(422, f"exportação IFC cobre {sorted(_exp.INSTALACAO)}; tipo de obra '{tipo}' sem mapeamento")
    chave = (_assinatura(projeto.dados), incluir_4d, repr(list(ajustes or [])))
    with _cache_lock:
        ex = _cache.get(chave)
        if ex is None:
            ex = _cache[chave] = _Exportacao(projeto.dados, incluir_4d, ajustes)
            while len(_cache) > MAX_CACHE:
                _cache.popitem(last=False)
        else:
            _cache.move_to_end(chave)
        return ex


def _nome(projeto: Projeto, ext: str) -> str:
    return f"{projeto.dados['ferrovia']['id']}.{ext}"


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------

_R422_TIPO = {422: {"description": "tipo de obra sem mapeamento IFC, ou eixo/peça sem projeção válida "
                                   "dentro da tolerância (ErroExportacao)"}}
_R_UPLOAD = {400: {"description": "corpo vazio: envie o .ifc no corpo da requisição"},
             413: {"description": f"arquivo acima de {LIMITE_BYTES // (1024 * 1024)} MB"},
             415: {"description": "Content-Type não aceito: envie o .ifc cru (application/octet-stream, "
                                  "application/x-step, application/ifc ou text/plain), não multipart nem JSON"},
             422: {"description": "o conteúdo não é um IFC STEP legível"}}
TIPOS_ACEITOS = ("application/octet-stream", "application/x-step", "application/ifc", "text/plain", "model/ifc")


def _conferir_tipo(request: Request) -> None:
    tipo = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if tipo and tipo not in TIPOS_ACEITOS:
        raise HTTPException(415, f"Content-Type {tipo!r} não aceito; envie o .ifc cru ({', '.join(TIPOS_ACEITOS)})")


@router.get("/exportar", response_class=Response,
            responses={200: {"content": {"application/x-step": {}}, "description": "Arquivo IFC4X3_ADD2"},
                       **_R422_TIPO})
def exportar(incluir_4d: bool = True, projeto: Projeto = Depends(obter_projeto),
             ajustes: list = Depends(obter_ajustes)):
    """Baixa o modelo IFC 4.3 (IFC4X3_ADD2) da obra: IfcRailway ou IfcRoad, IfcAlignment com estacas,
    peças com IfcLinearPlacement, quantidades, classificação FICTÍCIA e — com ``incluir_4d`` — o cronograma
    nativo por cenário (linha de base, construtora, independente e, se houver simulação ativa, simulado)."""
    try:
        texto = _exportacao(projeto, incluir_4d, ajustes).texto()
    except _exp.ErroExportacao as e:
        raise HTTPException(422, str(e)) from e
    return Response(content=texto.encode("latin-1", errors="replace"), media_type="application/x-step",
                    headers={"Content-Disposition": f'attachment; filename="{_nome(projeto, "ifc")}"'})


@router.get("/glb", response_class=Response,
            responses={200: {"content": {"model/gltf-binary": {}}, "description": "glTF 2.0 binário; node.name = GlobalId"},
                       **_R422_TIPO})
def glb(projeto: Projeto = Depends(obter_projeto)):
    """Baixa a malha da obra em glTF binário (GLB) para o visualizador: um nó por peça com ``name`` = GlobalId
    (o mesmo do .ifc e de ``/api/ifc/vinculo``), Y para cima, metros, origem = coordenadas do eixo do JSON."""
    try:
        dados = _exportacao(projeto).glb()
    except _exp.ErroExportacao as e:
        raise HTTPException(422, str(e)) from e
    return Response(content=dados, media_type="model/gltf-binary",
                    headers={"Content-Disposition": f'attachment; filename="{_nome(projeto, "glb")}"'})


@router.get("/vinculo", responses=_R422_TIPO)
def vinculo(projeto: Projeto = Depends(obter_projeto)):
    """Tabela GlobalId → atividade/elemento/serviço/lote/km da MESMA exportação do GLB, mais o sistema de
    coordenadas do GLB e os alinhamentos (estacas inicial e final)."""
    try:
        v = _exportacao(projeto).vinculo()
    except _exp.ErroExportacao as e:
        raise HTTPException(422, str(e)) from e
    return {
        "obra": projeto.dados["ferrovia"]["id"],
        "tipo_obra": _exp.tipo_obra(projeto.dados),
        "sistema": {"unidade": "m", "glb_y_up": True,
                    "glb_de_ifc": "glTF (x, y, z) = IFC (x, z, -y)",
                    "origem": "IFC (0,0,0) = alinhamento.pontos [x, y, cota] do JSON, sem deslocamento",
                    "glb_no": "node.name = global_id"},
        "resumo": v["resumo"],
        "alinhamentos": v["alinhamentos"],
        "elementos": [{k: l[k] for k in ("global_id", "elemento_id", "atividade_id", "classe", "servico_id",
                                         "lote_id", "km_ini", "km_fim")} for l in v["vinculos"]],
    }


def _corpo_ifc(corpo: bytes):
    if not corpo:
        raise HTTPException(400, "envie o arquivo .ifc no corpo (application/octet-stream)")
    if len(corpo) > LIMITE_BYTES:
        raise HTTPException(413, f"arquivo acima de {LIMITE_BYTES // (1024 * 1024)} MB")
    try:
        return _imp.abrir(corpo)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/requisitos", responses=_R422_TIPO)
def requisitos_modelo(projeto: Projeto = Depends(obter_projeto)):
    """Requisitos de informação 4D/5D (R1–R6: GlobalId único, vínculo com atividade, classificação,
    quantidade na unidade do serviço, posicionamento no eixo e cobertura do cronograma) do modelo exportado,
    com a coerência das quantidades por atividade e o custo pelo modelo × orçamento (FICTÍCIO)."""
    try:
        r = _exportacao(projeto).requisitos()
    except _exp.ErroExportacao as e:
        raise HTTPException(422, str(e)) from e
    from .. import orcamento
    try:
        bac = {l["atividade_id"]: l["bac"] for l in orcamento.orcar_atividades(projeto)}
    except orcamento.ErroOrcamento as e:  # orçamento inconsistente não esconde os requisitos
        bac, r = {}, {**r, "custo_modelo": {**r["custo_modelo"], "erro_orcamento": str(e)}}
    cm = r["custo_modelo"]
    com_peca = set(cm["por_atividade_contratual"])
    return {"obra": projeto.dados["ferrovia"]["id"], "origem": "modelo exportado pelo INFRA 4D",
            **r["requisitos"], "quantidades": r["quantidades"],
            "custo": {"ficticio": True,
                      "modelo_contratual": cm["total_contratual"], "modelo_geometrico": cm["total_geometrico"],
                      "orcamento_atividades_com_peca": sum(v for k, v in bac.items() if k in com_peca),
                      "orcamento_total": sum(bac.values()),
                      "atividades_sem_peca": sorted(set(bac) - com_peca),
                      "nota": ("contratual = Σ QuantidadeContratual × preço; deve igualar o orçamento das "
                               "atividades com peça. geométrico usa a geometria esquemática (só indicativo).")}}


@router.post("/requisitos", responses=_R_UPLOAD)
async def requisitos_upload(request: Request, projeto: Projeto = Depends(obter_projeto)):
    """Verifica os requisitos de informação 4D/5D (R1–R6) num ``.ifc`` enviado no corpo (binário cru).
    Um IFC de terceiro sem 4D REPROVA, e o relatório diz em quais requisitos e por quê."""
    _conferir_tipo(request)
    f = _corpo_ifc(await request.body())
    return {"obra": projeto.dados["ferrovia"]["id"], "origem": "arquivo enviado",
            **_req.verificar(f, projeto.dados)}


@router.post("/cronograma",
             responses={**_R_UPLOAD, 422: {"description": "não é IFC legível, o cenário não existe no arquivo "
                                                          "(a mensagem lista os que existem) ou o cronograma "
                                                          "não fecha (duração fora de P{n}D, rede inválida)"}})
async def cronograma_upload(request: Request, cenario: str = Query("independente"),
                            projeto: Projeto = Depends(obter_projeto)):
    """Lê o cronograma nativo (IfcWorkSchedule do ``cenario``) de um ``.ifc`` enviado, recalcula pelo motor
    CPM (datas, término e caminho crítico) e compara o término com o da API para a obra."""
    from ..calendario import iso
    from ..cenarios import CENARIOS, executar
    from ..motor import ErroRede, calcular
    _conferir_tipo(request)
    f = _corpo_ifc(await request.body())
    try:
        ativs, rels, cals, meta = _imp.ler_cronograma(f, cenario)
        res = calcular(ativs, rels, cals, meta["inicio_projeto"], data_status=meta["data_status"])
    except (_imp.ErroCronograma, ErroRede, ValueError) as e:
        raise HTTPException(422, str(e)) from e
    except (TypeError, KeyError, AttributeError, OverflowError) as e:  # rede de segurança: nunca 500
        raise HTTPException(422, f"cronograma IFC fora do suportado: {type(e).__name__}: {str(e)[:200]}") from e
    termino_api = executar(projeto, cenario)["termino"] if cenario in CENARIOS and cenario != "simulado" else None
    termino = iso(res.termino_projeto_data)
    return {"obra": projeto.dados["ferrovia"]["id"], "cenario": cenario,
            "cenarios_no_arquivo": _imp.cenarios_no_arquivo(f),
            "n_atividades": len(ativs), "n_relacoes": len(rels), "calendarios": sorted(cals),
            "inicio_projeto": iso(meta["inicio_projeto"]), "data_status": iso(meta["data_status"]),
            "termino_calculado": termino, "termino_api": termino_api,
            "confere_com_api": None if termino_api is None else termino == termino_api,
            "caminho_critico": sorted(res.caminho_critico), "avisos": meta.get("avisos", [])}


@router.post("/vinculos", responses=_R_UPLOAD)
async def vinculos(request: Request, projeto: Projeto = Depends(obter_projeto)):
    """Lê um ``.ifc`` enviado no corpo e devolve a tabela de vínculo elemento ↔ atividade (Pset
    INFRA4D_Vinculo, IfcRelAssignsToProduct ou IfcRelAssignsToProcess), os alinhamentos e a verificação
    contra as atividades da obra (casados, sem atividade, atividades sem elemento, obra trocada)."""
    _conferir_tipo(request)
    corpo = await request.body()
    if not corpo:
        raise HTTPException(400, "envie o arquivo .ifc no corpo (application/octet-stream)")
    if len(corpo) > LIMITE_BYTES:
        raise HTTPException(413, f"arquivo acima de {LIMITE_BYTES // (1024 * 1024)} MB")
    try:
        return _imp.ler(corpo, projeto.dados)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
