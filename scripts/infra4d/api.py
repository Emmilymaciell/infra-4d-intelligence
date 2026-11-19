"""API local do beta (FastAPI). Serve também a interface em /.

Execução:  .\\run-beta.ps1   (ou: python -m uvicorn infra4d.api:app --app-dir scripts)

Várias obras FICTÍCIAS: cada arquivo `examples/synthetic/<id>_ficticia.json` vira uma
obra (`ferrovia`, `rodovia`, ...). Toda rota aceita `?obra=<id>`; sem o parâmetro, vale
a ferrovia (compatível com a v0.2.0).

Estado: por obra, a simulação corrente (lista de ajustes) fica em memória do processo;
os cenários linha_base/construtora/independente são determinísticos e cacheados.

Rotas de módulos (importadores, IFC, recursos) são ligadas por `registrar_rotas`, que
lhes entrega `obter_estado(obra)` — o único ponto de acesso ao projeto e aos resultados.
"""

from __future__ import annotations

import base64
import hashlib
import re
import threading
from pathlib import Path

import math

from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .calendario import ErroCalendario, ordinal
from .cenarios import CENARIOS, DATASET_PADRAO, Ajuste, ErroAjuste, Projeto, comparar, executar
from .motor import ErroRede
from .obra import ErroTipoObra
from .obra import tipo_obra as _tipo_obra_declarado
from .painel import (alertas, avanco, curva_s, estado_4d, marcos_contratuais, producao_semanal, produtividades,
                     termino_lote)

WEB = Path(__file__).resolve().parents[2] / "web"
SINTETICOS = DATASET_PADRAO.parent
OBRA_PADRAO = "ferrovia"
# P10: orçamento do Monte Carlo (iterações ponderadas). 2000 iterações simples cabem; com as 5 opções pesadas
# (fator 3,5), até 1142 — cerca de 13 s pela medida da r20 (2000 com todas as opções = 22,9 s).
ORCAMENTO_MC = 4000


class AjusteIn(BaseModel):
    # r20: NaN/±inf/1e400 viravam 500 ao serializar a resposta; e true/"3" eram aceitos em silêncio.
    # Estrito: número finito de verdade, sem booleano e sem texto.
    atividade_id: str | None = None
    servico_id: str | None = None
    lote_id: str | None = None
    produtividade: float | None = Field(default=None, gt=0, allow_inf_nan=False, strict=True)
    equipes: int | None = Field(default=None, ge=1, le=20, strict=True)


class SimulacaoIn(BaseModel):
    ajustes: list[AjusteIn]


class Estado:
    def __init__(self, projeto: Projeto):
        self.projeto = projeto
        self.lock = threading.Lock()
        self.ajustes: list[Ajuste] = []
        self.cache: dict[str, dict] = {}

    def resultado(self, cenario: str) -> dict:
        if cenario not in CENARIOS:
            raise HTTPException(404, f"cenário desconhecido: {cenario}")
        with self.lock:
            if cenario not in self.cache:
                self.cache[cenario] = executar(self.projeto, cenario, self.ajustes if cenario == "simulado" else None)
            return self.cache[cenario]

    def resultado_logica_retida(self) -> dict:
        """Cenário independente com retained logic (cacheado à parte)."""
        with self.lock:
            if "independente:retida" not in self.cache:
                self.cache["independente:retida"] = executar(self.projeto, "independente",
                                                             logica_progresso="retida")
            return self.cache["independente:retida"]

    def simular(self, ajustes: list[Ajuste]) -> tuple[list[Ajuste], dict]:
        """Calcula o cenário simulado ANTES de gravar: um ajuste que estoura o cálculo é
        recusado e o estado anterior fica intacto (rodada 3: antes, gravava e envenenava
        painel/cenários/4D até um DELETE). Devolve (ajustes, resultado) lidos sob o lock."""
        resultado = executar(self.projeto, "simulado", ajustes)  # pode levantar: nada foi gravado
        with self.lock:
            self.ajustes = ajustes
            self.cache["simulado"] = resultado
            return list(self.ajustes), resultado


def descobrir_obras(pasta: Path = SINTETICOS) -> dict[str, Path]:
    """`<id>_ficticia.json` → {id: caminho}. Ordem estável: ferrovia primeiro."""
    achadas = {p.name[: -len("_ficticia.json")]: p for p in sorted(pasta.glob("*_ficticia.json"))}
    return dict(sorted(achadas.items(), key=lambda kv: (kv[0] != OBRA_PADRAO, kv[0])))


class Obras:
    """Registro de obras com carga preguiçosa (só lê o JSON quando a obra é usada)."""

    def __init__(self, fontes: dict[str, Path | Projeto]):
        """Aplica ajustes de produtividade/equipes (em memória) e devolve a comparação simulado × independente."""
        if not fontes:
            raise RuntimeError("nenhuma obra sintética encontrada em examples/synthetic/")
        self._fontes = fontes
        self._estados: dict[str, Estado] = {}
        self._lock = threading.Lock()

    @property
    def ids(self) -> list[str]:
        return list(self._fontes)

    def estado(self, obra: str | None) -> Estado:
        obra = obra or (OBRA_PADRAO if OBRA_PADRAO in self._fontes else self.ids[0])
        if obra not in self._fontes:
            raise HTTPException(404, f"obra desconhecida: {obra} (disponíveis: {', '.join(self.ids)})")
        with self._lock:
            if obra not in self._estados:
                f = self._fontes[obra]
                self._estados[obra] = Estado(f if isinstance(f, Projeto) else Projeto.carregar(f))
            return self._estados[obra]


def tipo_obra(projeto: Projeto) -> str:
    """Tipo DECLARADO da obra (P8): sem padrão "ferrovia"; ausente/desconhecido → ErroTipoObra → 422."""
    return _tipo_obra_declarado(projeto)


def criar_app(projeto: Projeto | None = None, fontes: dict[str, Path | Projeto] | None = None) -> FastAPI:
    app = FastAPI(title="INFRA 4D INTELLIGENCE — beta (dados fictícios)", version=__version__)
    if projeto is not None:
        fontes = {OBRA_PADRAO: projeto}
    obras = Obras(fontes or descobrir_obras())
    app.state.obras = obras

    def obter_estado(obra: str | None = None) -> Estado:
        return obras.estado(obra)

    app.state.obter_estado = obter_estado
    # compatibilidade: app.state.estado = obra padrão (testes da v0.2.0)
    app.state.estado = obras.estado(None)

    def _publico(r: dict) -> dict:
        return {k: v for k, v in r.items() if not k.startswith("_")}

    Q_OBRA = Query(default=None, description="id da obra (ferrovia, rodovia...); padrão: ferrovia")

    @app.get("/api/saude")
    def saude():
        """Saúde da API: versão, aviso de dados fictícios, obras disponíveis e módulos de rotas ligados/indisponíveis."""
        P = obras.estado(None).projeto
        return {"ok": True, "versao": __version__, "aviso": P.dados["meta"]["aviso"], "obras": obras.ids,
                "modulos": {"ligados": getattr(app.state, "rotas_ligadas", []),
                            "indisponiveis": getattr(app.state, "rotas_indisponiveis", {})}}

    @app.get("/api/obras")
    def listar_obras():
        """Lista as obras disponíveis (id, tipo, nome, extensão, data de status, lotes e atividades)."""
        saida = []
        for oid in obras.ids:
            P = obras.estado(oid).projeto
            d = P.dados
            try:
                tipo = tipo_obra(P)
                erro_tipo = None
            except ErroTipoObra as e:  # uma obra mal declarada não esconde as outras da lista (P8)
                tipo, erro_tipo = None, str(e)
            saida.append({"id": oid, "tipo": tipo, **({"erro_tipo_obra": erro_tipo} if erro_tipo else {}),
                          "nome": d["ferrovia"]["nome"],
                          "extensao_km": d["ferrovia"].get("extensao_km"), "data_status": d["meta"]["data_status"],
                          "lotes": len(d["lotes"]), "atividades": len(d["atividades"]), "aviso": d["meta"]["aviso"]})
        return saida

    @app.get("/api/projeto", responses={404: {"description": "Obra desconhecida"}})
    def projeto_info(obra: str | None = Q_OBRA):
        """Dados de cadastro da obra: meta, lotes, segmentos, serviços, calendários, atividades e relações."""
        P = obras.estado(obra).projeto
        d = P.dados
        return {k: d[k] for k in ("meta", "ferrovia", "lotes", "segmentos", "servicos", "restricoes", "oaes",
                                  "alinhamento")} | {
            "obra": {"id": obra or OBRA_PADRAO, "tipo": tipo_obra(P)},
            "calendarios": [{"id": c["id"], "nome": c["nome"], "dias_nao_uteis": len(c["nao_uteis"])}
                            for c in d["calendarios"]],
            "atividades": [{k: v for k, v in a.items()} for a in d["atividades"]],
            "relacoes": d["relacoes"],
        }

    @app.get("/api/cenarios/{cenario}", responses={404: {"description": "Obra ou cenário desconhecido"}})
    def cenario(cenario: str, obra: str | None = Q_OBRA):
        """Resultado do motor CPM para um cenário (linha_base, construtora, independente, simulado): datas, folgas, crítica e memória de cálculo por atividade."""
        return _publico(obras.estado(obra).resultado(cenario))

    @app.get("/api/comparacao", responses={404: {"description": "Obra ou cenário desconhecido"}})
    def comparacao(ref: str = "construtora", alvo: str = "independente", obra: str | None = Q_OBRA):
        """Compara dois cenários (ref × alvo): Δ do término, durações alteradas com efeito isolado e explicação auditável."""
        est = obras.estado(obra)
        return comparar(est.projeto, est.resultado(ref), est.resultado(alvo))

    def _resposta_simulacao(est: Estado, ajustes: list[Ajuste], sim: dict) -> dict:
        return {"ajustes": [a.__dict__ for a in ajustes],
                "comparacao": comparar(est.projeto, est.resultado("independente"), sim)}

    @app.get("/api/simulacao", responses={404: {"description": "Obra desconhecida"}})
    def simulacao_atual(obra: str | None = Q_OBRA):
        """Ajustes de simulação ativos e a comparação do cenário simulado com o independente."""
        est = obras.estado(obra)
        with est.lock:
            ajustes = list(est.ajustes)
        return _resposta_simulacao(est, ajustes, est.resultado("simulado"))

    @app.post("/api/simulacao", responses={404: {"description": "Obra desconhecida"}, 422: {"description": "Ajuste inválido, sem atividade alvo ou que invalida a rede (estado anterior mantido)"}})
    def simular(body: SimulacaoIn, obra: str | None = Q_OBRA):
        """Aplica ajustes de produtividade/equipes (em memória) e devolve a comparação simulado × independente."""
        est = obras.estado(obra)
        P = est.projeto
        try:
            ajustes = [Ajuste.de_dict(a.model_dump()) for a in body.ajustes]
        except ErroAjuste as e:
            raise HTTPException(422, str(e))
        # só atividades por QUANTIDADE e ainda não concluídas respondem a produtividade/equipes;
        # ajuste que não atinge nenhuma é recusado (antes era aceito e ignorado em silêncio)
        def ajustavel(x):
            return bool(x.get("quantidade_total")) and x.get("status") != "concluida"
        sem_alvo = [a for a in ajustes if not any(a.aplica_a(x) and ajustavel(x) for x in P.dados["atividades"])]
        if sem_alvo:
            raise HTTPException(422, "ajuste não corresponde a nenhuma atividade por quantidade em aberto "
                                     "(atividade inexistente, concluída, marco ou de duração fixa)")
        try:
            gravados, sim = est.simular(ajustes)
        except (ErroAjuste, ErroRede, ErroCalendario, ValueError, OverflowError) as e:
            raise HTTPException(422, f"simulação recusada, estado anterior mantido: {e}")
        return _resposta_simulacao(est, gravados, sim)

    @app.delete("/api/simulacao", responses={404: {"description": "Obra desconhecida"}})
    def limpar(obra: str | None = Q_OBRA):
        """Remove os ajustes de simulação da obra (o simulado volta a ser igual ao independente)."""
        est = obras.estado(obra)
        gravados, sim = est.simular([])
        return _resposta_simulacao(est, gravados, sim)

    @app.get("/api/estado4d", responses={404: {"description": "Obra ou cenário desconhecido"}, 422: {"description": "Data inválida (use AAAA-MM-DD)"}})
    def estado4d(data: str, cenario: str = "independente", obra: str | None = Q_OBRA):
        """Estado 4D de cada atividade numa data: progresso previsto/real para colorir o modelo 3D."""
        est = obras.estado(obra)
        try:
            t = ordinal(data)
        except ValueError:
            t = None
        if t is None:
            raise HTTPException(422, "data inválida (use AAAA-MM-DD)")
        P = est.projeto
        return {"data": data, "cenario": cenario, "data_status": P.dados["meta"]["data_status"],
                "atividades": estado_4d(P, est.resultado(cenario), est.resultado("linha_base"), t)}

    @app.get("/api/painel", responses={404: {"description": "Obra ou lote desconhecido"}})
    def painel(lote: str | None = Query(default=None), obra: str | None = Q_OBRA):
        """Painel gerencial: avanço real × planejado, términos por cenário, críticas, produtividades, curva S, alertas e marcos."""
        est = obras.estado(obra)
        P = est.projeto
        if lote and lote not in {l["id"] for l in P.dados["lotes"]}:
            raise HTTPException(404, f"lote desconhecido: {lote}")
        res = {c: est.resultado(c) for c in CENARIOS}
        ds = P.data_status
        term = (lambda r: termino_lote(r, lote)) if lote else (lambda r: r["termino"])
        return {
            "obra": obra or OBRA_PADRAO,
            "lote": lote,
            "data_status": P.dados["meta"]["data_status"],
            "avanco_real": round(100 * avanco(P, res["independente"], ds, lote), 2),
            "avanco_planejado_lb": round(100 * avanco(P, res["linha_base"], ds, lote), 2),
            "terminos": {c: term(r) for c, r in res.items()},
            # sem o campo no meta, o prazo contratual é o término calculado da linha de base (r15: era 500)
            "termino_contratual": P.dados["meta"].get("termino_linha_base") or res["linha_base"]["termino"],
            "criticas_independente": [a for a in res["independente"]["caminho_critico"]
                                      if not lote or P.atividades[a].get("lote_id") == lote],
            "produtividades": produtividades(P, lote),
            "producao_semanal": producao_semanal(P, lote),
            "alertas": alertas(P, res["independente"], res["construtora"], lote),
            "curva_s": curva_s(P, {c: res[c] for c in ("linha_base", "construtora", "independente", "simulado")}, lote),
            "simulacao_ativa": bool(est.ajustes),
            "marcos_contratuais": marcos_contratuais(P, res, lote),
            "sensibilidade_logica": {
                "descricao": "término do cenário independente conforme a lógica de progresso das atividades em "
                             "andamento: 'sobrepor' (progress override, padrão do beta) x 'retida' "
                             "(retained logic, padrão do Primavera P6)",
                "sobrepor": res["independente"]["termino"],
                "retida": est.resultado_logica_retida()["termino"],
            },
        }

    @app.get("/api/previsao-probabilistica", responses={404: {"description": "Obra desconhecida"}, 422: {"description": "Parâmetro fora da faixa ou simulação recusada"}})
    def previsao_probabilistica(iteracoes: int = Query(default=200, ge=10, le=2000),
                                semente: int = Query(default=7, ge=0, le=2**31 - 1),
                                rho: float = Query(default=0.0, ge=0.0, le=1.0,
                                                   description="correlação entre frentes do mesmo serviço (v2)"),
                                com_riscos: bool = Query(default=False, description="eventos de risco discretos (v2)"),
                                com_chuva: bool = Query(default=False, description="chuva estocástica (v2)"),
                                com_criticidade: bool = Query(default=False,
                                                              description="índice de criticidade por atividade/grupo"),
                                so_aprovados: bool = Query(default=False,
                                                           description="só boletins aprovados/conferidos pela fiscalização"),
                                incerteza_sem_medicao: bool = Query(
                                    default=False, description="frente sem boletim próprio sorteia o fator da "
                                                               "distribuição observada na obra, alargada (P4)"),
                                alargamento: float | None = Query(
                                    default=None, ge=0.0, le=0.6,
                                    description="alargamento do fator sorteado; padrão do módulo (0,50, calibrado "
                                                "no backtest); teto 0,6 (acima disso a faixa vira ruído)"),
                                por_marco: bool = Query(default=False, description="percentis por marco"),
                                obra: str | None = Q_OBRA):
        """Previsão probabilística (Monte Carlo) do término: P10/P50/P80/P90, com opções v2 (correlação, riscos,
        chuva, criticidade) e incerteza alargada para frente sem medição (P4, desligada por padrão)."""
        from .montecarlo import simular as mc
        est = obras.estado(obra)
        # P10 (r20): 2000 iterações com todas as opções levaram 22,9 s e podem passar de 30 s com a máquina
        # carregada. Orçamento declarado: iterações × (1 + 0,5 por opção pesada) ≤ ORCAMENTO_MC.
        pesadas = sum((com_criticidade, com_chuva, com_riscos, incerteza_sem_medicao, por_marco))
        custo = iteracoes * (1 + 0.5 * pesadas)
        if custo > ORCAMENTO_MC:
            maximo = int(ORCAMENTO_MC // (1 + 0.5 * pesadas))
            raise HTTPException(422, f"Monte Carlo pesado demais: {iteracoes} iterações com {pesadas} opção(ões) "
                                     f"pesada(s) (custo {custo:.0f} > {ORCAMENTO_MC}). Use iteracoes <= {maximo}.")
        extra = {}
        if incerteza_sem_medicao or por_marco:
            from .montecarlo import ALARGAMENTO_PADRAO
            extra = {"incerteza_sem_medicao": incerteza_sem_medicao, "por_marco": por_marco,
                     "alargamento": ALARGAMENTO_PADRAO if alargamento is None else alargamento}
        chave = (f"mc:{iteracoes}:{semente}:{rho:.4f}:{int(com_riscos)}:{int(com_chuva)}:"
                 f"{int(com_criticidade)}:{int(so_aprovados)}"
                 + (f":{int(incerteza_sem_medicao)}:{int(por_marco)}:{extra['alargamento']:.4f}" if extra else ""))
        with est.lock:
            if chave not in est.cache:
                # cache limitado: no máximo 8 resultados de Monte Carlo (rodada 3: crescia sem limite)
                antigas = [k for k in est.cache if k.startswith("mc:")]
                for k in antigas[: max(0, len(antigas) - 7)]:
                    est.cache.pop(k, None)
                try:
                    est.cache[chave] = mc(est.projeto, iteracoes, semente, rho=rho, com_riscos=com_riscos,
                                          com_chuva=com_chuva, com_criticidade=com_criticidade,
                                          estados=("aprovado", "conferido_fiscal") if so_aprovados else None,
                                          **extra)
                except ValueError as e:
                    raise HTTPException(422, str(e))
            # o MC roda sobre a produtividade medida (independente); a simulação do usuário não entra de propósito
            return {**est.cache[chave],
                    "simulacao_do_usuario": "não aplicada: o Monte Carlo varia a produtividade medida do cenário "
                                            "independente; ajustes da simulação não entram"}

    @app.exception_handler(ErroTipoObra)
    def erro_tipo_obra(_req, exc: ErroTipoObra):
        """P8: obra sem meta.tipo_obra (ou desconhecido) é erro do DADO, 422 com a causa — nunca 500 e nunca
        "assumiu ferrovia"."""
        return JSONResponse(status_code=422, content={"detail": f"tipo de obra inválido: {exc}"})

    @app.exception_handler(ErroRede)
    def erro_rede(_req, exc: ErroRede):
        return JSONResponse(status_code=422, content={"detail": f"rede inválida: {exc}"})

    @app.exception_handler(RequestValidationError)
    def erro_validacao(_req, exc: RequestValidationError):
        """422 padrão do FastAPI, mas sem ecoar valores que não cabem em JSON (r20: NaN/±inf e corpo não UTF-8
        no `input` do erro faziam a própria resposta de erro estourar em 500)."""
        def limpo(v):
            if isinstance(v, float) and not math.isfinite(v):
                return repr(v)
            if isinstance(v, bytes):
                return v.decode("utf-8", "replace")
            if isinstance(v, dict):
                return {str(k): limpo(x) for k, x in v.items()}
            if isinstance(v, (list, tuple)):
                return [limpo(x) for x in v]
            return v if isinstance(v, (str, int, float, bool, type(None))) else str(v)
        return JSONResponse(status_code=422, content={"detail": limpo(list(exc.errors()))})

    @app.exception_handler(ErroCalendario)
    def erro_calendario(_req, exc: ErroCalendario):
        """Dado que leva o cálculo para fora do horizonte dos calendários (ex.: boletim com produtividade
        implausível, achado da r17) é erro do dado, não do servidor: 422 com o motivo, em qualquer rota."""
        return JSONResponse(status_code=422, content={
            "detail": f"o cálculo saiu do horizonte do calendário: {exc}. Confira boletins com produtividade "
                      "implausível ou durações fora de escala."})

    @app.middleware("http")
    async def cabecalhos_de_seguranca(request, call_next):
        """CSP + nosniff (auditoria do frontend, rodada 7, defeito 6). A interface só carrega o próprio
        site; o único script inline permitido é o importmap, por hash recalculado do index.html atual.
        O relatório não executa script nenhum."""
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        caminho = request.url.path
        if caminho == "/" or caminho.startswith("/static/"):
            resp.headers["Content-Security-Policy"] = csp_interface()
        elif caminho == "/api/relatorio":
            resp.headers["Content-Security-Policy"] = (
                "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; "
                "form-action 'none'; frame-ancestors 'none'")
        return resp

    registrar_rotas(app, obter_estado)

    if WEB.is_dir():
        app.mount("/static", StaticFiles(directory=WEB), name="static")

        @app.get("/")
        def index():
            """Interface web (página inicial)."""
            return FileResponse(WEB / "index.html")

    return app


_RE_IMPORTMAP = re.compile(r"<script\s+type=\"importmap\"\s*>(.*?)</script>", re.S)


def csp_interface() -> str:
    """Content-Security-Policy da interface. Hash SHA-256 de cada importmap inline do index.html
    ATUAL (lido a cada chamada: o frontend pode mudar o arquivo com o servidor no ar)."""
    hashes = ""
    try:
        html = (WEB / "index.html").read_text(encoding="utf-8")
        hashes = " ".join("'sha256-" + base64.b64encode(hashlib.sha256(m.group(1).encode("utf-8")).digest()).decode()
                          + "'" for m in _RE_IMPORTMAP.finditer(html))
    except OSError:
        pass
    return ("default-src 'self'; "
            f"script-src 'self' {hashes}".rstrip() + "; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; "
            "worker-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


def registrar_rotas(app: FastAPI, obter_estado) -> list[str]:
    """Liga os routers dos módulos que existirem. Cada módulo expõe `ligar(app, obter_estado)`
    ou um `router` + `configurar(obter_estado)`. Módulo ausente (ex.: ifcopenshell não
    instalado) não derruba a API: fica registrado em app.state.rotas_indisponiveis."""
    ligados, indisponiveis = [], {}
    for nome in ("importadores.rotas", "ifc.rotas", "rotas_recursos", "rotas_referencia", "rotas_previsao",
                 "rotas_fiscalizacao", "rotas_massas", "rotas_persistencia", "rotas_orcamento",
                 "rotas_recuperacao", "rotas_produtividade", "rotas_exportacao", "rotas_sensibilidade", "rotas_dcma", "rotas_clima", "rotas_medicoes", "rotas_riscos", "rotas_gis", "rotas_tendencia", "rotas_curva_s", "rotas_revisoes", "rotas_backtest", "rotas_aceleracao", "rotas_cobertura", "rotas_atribuicao",
                 "relatorio", "rotas_federacao"):
        try:
            mod = __import__(f"infra4d.{nome}", fromlist=["*"])
        except Exception as e:  # noqa: BLE001 — módulo opcional quebrado não derruba a API
            indisponiveis[nome] = f"{type(e).__name__}: {e}"
            continue
        try:
            if hasattr(mod, "ligar"):
                mod.ligar(app, obter_estado)
            elif hasattr(mod, "router"):
                if hasattr(mod, "configurar"):
                    mod.configurar(obter_estado)
                app.include_router(mod.router)
            else:
                indisponiveis[nome] = "módulo sem `ligar` nem `router`"
                continue
        except Exception as e:  # noqa: BLE001 — contrato de ligação violado: módulo fica indisponível
            indisponiveis[nome] = f"falha ao ligar ({type(e).__name__}: {e})"
            continue
        ligados.append(nome)
    app.state.rotas_ligadas = ligados
    app.state.rotas_indisponiveis = indisponiveis
    return ligados


app = criar_app()
