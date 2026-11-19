"""Não conformidade (NC) da fiscalização como ENTIDADE própria (missão §3.5).

Uma NC é registrada pelo fiscal sobre uma atividade (e, opcionalmente, um elemento BIM) e segue o ciclo
``aberta → em_tratamento → encerrada``. Campos::

    {"id": str, "atividade_id": str, "elemento_id"?: str, "km"?: float,
     "data_abertura": "AAAA-MM-DD", "descricao": str, "gravidade": "baixa"|"media"|"alta",
     "prazo": "AAAA-MM-DD", "situacao": "aberta"|"em_tratamento"|"encerrada",
     "data_encerramento"?: "AAAA-MM-DD",            # obrigatória só se encerrada; proibida senão
     "evidencias"?: [{"ref": str, "sha256"?: hex64, "descricao"?: str}]}

Fontes:
- **dataset**: a lista opcional ``nao_conformidades`` da obra. Ausente ou vazia = nenhuma NC (não é erro);
- **exemplos sintéticos** (``exemplos_ficticios``): só em obra com ``meta.ficticio is True`` (ADR-0005), cada um
  marcado ``ficticio: True``. Não há evidência fictícia (nada que pareça prova real).

Regras (testadas em ``tests/test_nao_conformidade.py``):
- evidência é só REFERÊNCIA + hash: nenhum campo de conteúdo (bytes, base64, foto) é aceito;
- NC **vencida** = não encerrada e ``prazo`` anterior à data de status; ``dias_vencida`` em dias corridos;
- **alerta** = NC não encerrada (aberta ou em tratamento) numa atividade CRÍTICA e não concluída do cenário
  independente;
- ``fonte_riscos(projeto, ind, obra)`` tem a assinatura das fontes de ``riscos_prazo.FONTES``: o dono do registro
  de riscos pode consumi-la sem adaptação. Cada sinal traz evidência reconsultável em
  ``/api/fiscalizacao/nao-conformidades``.
"""

from __future__ import annotations

import math
import re
from datetime import date

from .calendario import iso
from .cenarios import Projeto

GRAVIDADES = ("baixa", "media", "alta")
SITUACOES = ("aberta", "em_tratamento", "encerrada")
CAMPOS = {"id", "atividade_id", "elemento_id", "km", "data_abertura", "descricao", "gravidade", "prazo",
          "situacao", "data_encerramento", "evidencias", "ficticio", "origem"}
CAMPOS_EVIDENCIA = {"ref", "sha256", "descricao"}
ORIGEM_EXEMPLO = "exemplo SINTÉTICO (nao_conformidade.exemplos_ficticios); não é registro de fiscalização"
ROTA = "/api/fiscalizacao/nao-conformidades"

_RE_DATA = re.compile(r"\d{4}-\d{2}-\d{2}")
_RE_SHA = re.compile(r"[0-9a-f]{64}")
_RE_GLOBALID = re.compile(r"[0-9A-Za-z_$]{22}")


class ErroNaoConformidade(ValueError):
    """Cadastro de NC inválido (lista todos os erros) ou parâmetro inválido."""


class ExemploEmObraReal(ErroNaoConformidade):
    """Exemplos sintéticos pedidos em obra sem ``meta.ficticio is True`` (ADR-0005)."""


def _data(v, campo: str, erros: list, nc_id) -> date | None:
    if not isinstance(v, str) or not _RE_DATA.fullmatch(v):
        erros.append(f"{nc_id}: {campo} deve ser texto AAAA-MM-DD ({v!r})")
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        erros.append(f"{nc_id}: {campo} é data inexistente ({v!r})")
        return None


def _num(v) -> bool:
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)


def validar(projeto: Projeto, registros) -> tuple[list[dict], list[str]]:
    """(NCs normalizadas, erros). Valida TODAS e devolve todos os erros (nada é aceito pela metade)."""
    erros: list[str] = []
    if registros is None:
        return [], []
    if not isinstance(registros, list):
        return [], [f"nao_conformidades deve ser lista ({type(registros).__name__})"]
    ds = date.fromordinal(projeto.data_status)
    vistos, saida = set(), []
    for i, r in enumerate(registros):
        if not isinstance(r, dict):
            erros.append(f"item {i}: não é objeto")
            continue
        nc_id = r.get("id")
        if not isinstance(nc_id, str) or not nc_id.strip():
            erros.append(f"item {i}: id ausente ou vazio")
            nc_id = f"item {i}"
        elif nc_id in vistos:
            erros.append(f"{nc_id}: id repetido")
        vistos.add(nc_id)
        extras = sorted(set(r) - CAMPOS)
        if extras:
            erros.append(f"{nc_id}: campo(s) desconhecido(s) {extras}")
        aid = r.get("atividade_id")
        ativ = projeto.atividades.get(aid) if isinstance(aid, str) else None
        if ativ is None:
            erros.append(f"{nc_id}: atividade_id inexistente ({aid!r})")
        el = r.get("elemento_id")
        if el is not None:
            ok = isinstance(el, str) and (_RE_GLOBALID.fullmatch(el) or
                                          (isinstance(aid, str) and re.fullmatch(re.escape(aid) + r"-E\d+", el)))
            if not ok:
                erros.append(f"{nc_id}: elemento_id {el!r} não é '<atividade_id>-E<nn>' da mesma atividade "
                             "nem GlobalId IFC (22 caracteres)")
        km = r.get("km")
        if km is not None:
            if not _num(km):
                erros.append(f"{nc_id}: km deve ser número finito ({km!r})")
            elif ativ is not None and _num(ativ.get("km_ini")) and _num(ativ.get("km_fim")):
                lo, hi = sorted((ativ["km_ini"], ativ["km_fim"]))
                if not lo <= km <= hi:
                    erros.append(f"{nc_id}: km {km} fora do trecho da atividade {aid} ({lo}–{hi})")
        desc = r.get("descricao")
        if not isinstance(desc, str) or not desc.strip():
            erros.append(f"{nc_id}: descricao ausente ou vazia")
        if r.get("gravidade") not in GRAVIDADES:
            erros.append(f"{nc_id}: gravidade {r.get('gravidade')!r} fora de {GRAVIDADES}")
        sit = r.get("situacao")
        if sit not in SITUACOES:
            erros.append(f"{nc_id}: situacao {sit!r} fora de {SITUACOES}")
        ab = _data(r.get("data_abertura"), "data_abertura", erros, nc_id)
        pz = _data(r.get("prazo"), "prazo", erros, nc_id)
        if ab and ab > ds:
            erros.append(f"{nc_id}: data_abertura {ab} depois da data de status {ds}")
        if ab and pz and pz < ab:
            erros.append(f"{nc_id}: prazo {pz} antes da abertura {ab}")
        enc = None
        if sit == "encerrada":
            enc = _data(r.get("data_encerramento"), "data_encerramento", erros, nc_id)
            if enc and ab and enc < ab:
                erros.append(f"{nc_id}: encerramento {enc} antes da abertura {ab}")
            if enc and enc > ds:
                erros.append(f"{nc_id}: encerramento {enc} depois da data de status {ds}")
        elif r.get("data_encerramento") is not None:
            erros.append(f"{nc_id}: data_encerramento só existe em NC encerrada (situacao={sit!r})")
        evs = r.get("evidencias", [])
        if not isinstance(evs, list):
            erros.append(f"{nc_id}: evidencias deve ser lista")
            evs = []
        for j, ev in enumerate(evs):
            if not isinstance(ev, dict):
                erros.append(f"{nc_id}: evidência {j} não é objeto")
                continue
            if set(ev) - CAMPOS_EVIDENCIA:
                erros.append(f"{nc_id}: evidência {j} com campo(s) {sorted(set(ev) - CAMPOS_EVIDENCIA)}: "
                             "só referência + hash (nenhum conteúdo/foto)")
            if not isinstance(ev.get("ref"), str) or not ev["ref"].strip():
                erros.append(f"{nc_id}: evidência {j} sem ref")
            if "sha256" in ev and not (isinstance(ev["sha256"], str) and _RE_SHA.fullmatch(ev["sha256"])):
                erros.append(f"{nc_id}: evidência {j} com sha256 inválido (64 hex minúsculos)")
        if "ficticio" in r and not isinstance(r["ficticio"], bool):
            erros.append(f"{nc_id}: ficticio deve ser booleano (ADR-0005)")
        saida.append({**r, "evidencias": evs})
    return ([] if erros else saida), erros


def carregar(projeto: Projeto) -> list[dict]:
    """NCs declaradas na obra (``dados["nao_conformidades"]``). Ausente = []. Inválidas = ErroNaoConformidade."""
    ncs, erros = validar(projeto, projeto.dados.get("nao_conformidades"))
    if erros:
        raise ErroNaoConformidade("não conformidades inválidas: " + "; ".join(erros))
    return ncs


def exemplos_ficticios(projeto: Projeto, ind: dict) -> list[dict]:
    """Três NCs SINTÉTICAS e determinísticas para demonstração, só em obra fictícia (ADR-0005):
    uma aberta e vencida na 1ª atividade crítica não concluída, uma em tratamento no prazo numa não crítica e uma
    encerrada. Sem evidência (não há prova fictícia)."""
    if projeto.dados.get("meta", {}).get("ficticio") is not True:
        raise ExemploEmObraReal("exemplos de NC só existem em obra fictícia (meta.ficticio = true)")
    ds = projeto.data_status
    ats = ind["atividades"]
    tarefas = sorted(a for a, x in projeto.atividades.items()
                     if x.get("tipo", "tarefa") == "tarefa" and a in ats and ats[a]["status"] != "concluida")
    crit = [a for a in tarefas if ats[a]["critica"]]
    nao_crit = [a for a in tarefas if not ats[a]["critica"]]
    concl = sorted(a for a, x in ats.items() if x["status"] == "concluida" and
                   projeto.atividades[a].get("tipo", "tarefa") == "tarefa")
    base = {"ficticio": True, "origem": ORIGEM_EXEMPLO, "evidencias": []}
    out = []
    if crit:
        out.append({**base, "id": "NC-FIC-001", "atividade_id": crit[0], "data_abertura": iso(ds - 30),
                    "descricao": "Compactação abaixo do grau especificado (exemplo fictício)", "gravidade": "alta",
                    "prazo": iso(ds - 9), "situacao": "aberta"})
    if nao_crit:
        out.append({**base, "id": "NC-FIC-002", "atividade_id": nao_crit[0], "data_abertura": iso(ds - 10),
                    "descricao": "Drenagem provisória obstruída (exemplo fictício)", "gravidade": "media",
                    "prazo": iso(ds + 14), "situacao": "em_tratamento"})
    if concl:
        out.append({**base, "id": "NC-FIC-003", "atividade_id": concl[0], "data_abertura": iso(ds - 60),
                    "descricao": "Sinalização de obra incompleta (exemplo fictício)", "gravidade": "baixa",
                    "prazo": iso(ds - 45), "situacao": "encerrada", "data_encerramento": iso(ds - 50)})
    return out


def avaliar(projeto: Projeto, ncs: list[dict], ind: dict) -> list[dict]:
    """Cada NC com ``vencida``, ``dias_vencida``, ``critica``, ``lote_id`` e ``alerta`` (bool)."""
    ds = date.fromordinal(projeto.data_status)
    out = []
    for nc in ncs:
        r = ind["atividades"].get(nc["atividade_id"], {})
        aberta = nc["situacao"] != "encerrada"
        pz = date.fromisoformat(nc["prazo"])
        vencida = aberta and pz < ds
        critica = bool(r.get("critica")) and r.get("status") != "concluida"
        out.append({**nc, "lote_id": projeto.atividades[nc["atividade_id"]].get("lote_id"),
                    "vencida": vencida, "dias_vencida": (ds - pz).days if vencida else 0,
                    "critica": critica, "folga_total": r.get("folga_total"), "alerta": aberta and critica})
    return out


def alertas(avaliadas: list[dict]) -> list[dict]:
    return [{"nc_id": n["id"], "atividade_id": n["atividade_id"], "gravidade": n["gravidade"],
             "situacao": n["situacao"], "folga_total": n["folga_total"], "nivel": "alto",
             "texto": f"NC {n['id']} ({n['gravidade']}, {n['situacao']}) na atividade CRÍTICA {n['atividade_id']} "
                      f"(folga total {n['folga_total']} dias úteis no independente): {n['descricao']}"}
            for n in avaliadas if n["alerta"]]


def vencidas(avaliadas: list[dict]) -> list[dict]:
    return sorted((n for n in avaliadas if n["vencida"]), key=lambda n: (-n["dias_vencida"], n["id"]))


def _nivel(n: dict) -> str:
    if n["gravidade"] == "alta" or n["critica"]:
        return "alto"
    return "medio" if n["gravidade"] == "media" else "baixo"


def fonte_riscos(projeto: Projeto, ind: dict, obra: str | None, exemplos: bool = False) -> list[dict]:
    """Sinais de risco das NCs VENCIDAS, no formato das fontes de ``riscos_prazo`` (``chave``, ``fonte``,
    ``atividades``, ``nivel``, ``delta``, ``prob``, ``titulo``, ``texto``, ``evidencias``). Só NCs declaradas,
    a menos que ``exemplos=True`` (obra fictícia). A evidência aponta para ``dias_vencida`` em ``ROTA``."""
    ncs = exemplos_ficticios(projeto, ind) if exemplos else carregar(projeto)
    out = []
    for n in vencidas(avaliar(projeto, ncs, ind)):
        a = projeto.atividades[n["atividade_id"]]
        lote, serv = a.get("lote_id"), a.get("servico_id")
        params = {"obra": obra, "exemplos": "true" if exemplos else None}
        out.append({"chave": ("frente", lote, serv) if serv else ("atividade", n["atividade_id"]),
                    "fonte": "nao_conformidade", "atividades": [n["atividade_id"]], "nivel": _nivel(n),
                    "delta": None, "prob": None,
                    "titulo": f"Não conformidade vencida: {n['descricao']}",
                    "texto": f"NC {n['id']} ({n['gravidade']}) em {n['atividade_id']} venceu em {n['prazo']} e segue "
                             f"{n['situacao']} há {n['dias_vencida']} dia(s) corrido(s)"
                             + (" — atividade crítica no independente." if n["critica"] else "."),
                    "evidencias": [{"rota": ROTA, "params": {k: v for k, v in params.items() if v is not None},
                                    "caminho": ["vencidas", {"id": n["id"]}, "dias_vencida"],
                                    "valor": n["dias_vencida"]}]})
    return out


def relatorio(projeto: Projeto, ind: dict, lote: str | None = None, situacao: str | None = None,
              exemplos: bool = False) -> dict:
    """Resposta da rota: NCs avaliadas (filtradas por lote/situação), vencidas, alertas e regras."""
    if situacao is not None and situacao not in SITUACOES:
        raise ErroNaoConformidade(f"situacao {situacao!r} fora de {SITUACOES}")
    ncs = exemplos_ficticios(projeto, ind) if exemplos else carregar(projeto)
    av = [n for n in avaliar(projeto, ncs, ind)
          if (lote is None or n["lote_id"] == lote) and (situacao is None or n["situacao"] == situacao)]
    return {"fonte_das_ncs": "exemplos sintéticos" if exemplos else "dataset (nao_conformidades)",
            "n": len(av), "nao_conformidades": av, "vencidas": vencidas(av), "alertas": alertas(av),
            "regras": {"vencida": "não encerrada e prazo anterior à data de status (dias corridos)",
                       "alerta": "não encerrada (aberta ou em tratamento) em atividade crítica e não concluída do "
                                 "cenário independente",
                       "evidencia": "só referência + sha256; nenhum conteúdo ou foto é aceito"}}
