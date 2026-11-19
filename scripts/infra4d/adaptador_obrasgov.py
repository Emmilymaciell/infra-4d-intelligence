"""Adaptador PROTÓTIPO: JSON no formato da API pública do Obrasgov.br → esquema do INFRA 4D.

Formato de entrada: o esquema OpenAPI oficial (``https://api-publica.obrasgov.gestao.gov.br/obras/openapi.json``,
lido em 2026-11-12; ver docs/research/R10-obrasgov.md). Um dicionário com as respostas PAGINADAS
(``{"data": [...], "total_pages", "total_items", "page_number", "page_size"}``) de cada recurso:

    {"projeto_investimento": {...}, "execucao_fisica": {...}, "contrato": {...},
     "geometria": {...}, "historico_situacao_cancelada_paralisada": {...}}

Só ``projeto_investimento`` é obrigatório. Este módulo NÃO acessa a rede: quem busca na API é outro
componente, que ainda não existe. Os testes usam só a fixture FICTÍCIA ``examples/fixtures/obrasgov_sintetico.json``.

O que sai (dicionário), e o que NÃO sai:
- ``meta``, ``ferrovia`` (a chave que o código usa para "a obra") e ``lotes`` (um por contrato) no esquema do projeto;
- ``marcos``: início e término previstos e efetivos do projeto de investimento;
- ``avanco_fisico``: série de percentual físico GLOBAL do Obrasgov por data, para confronto com o avanço do
  painel e como EV do Earned Schedule no nível da obra;
- ``situacoes``, ``localizacao``, ``financeiro`` (contratos), ``rastreio`` (id de origem de cada item);
- ``lacunas``: o que falta para virar um ``cenarios.Projeto``. O Obrasgov NÃO traz atividades, relações,
  quantidades, boletins por serviço, calendários nem km. Este adaptador NÃO inventa nada disso.

Dado real: ``meta.ficticio`` só é True quando a entrada declara ``"_infra4d_ficticio": true`` (ADR-0005).
Dado vindo da API real sai SEM a marca, e os geradores sintéticos do projeto se recusam a usá-lo.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime

RECURSOS = ("projeto_investimento", "execucao_fisica", "contrato", "geometria",
            "historico_situacao_cancelada_paralisada")
FONTE = "Obrasgov.br — API de dados abertos (formato openapi.json de 2026-11-12)"
_RE_ID = re.compile(r"^\d{5}\.\d{2}-\d{2}$")  # formato observado: 99999.99-99


class ErroObrasgov(ValueError):
    """Entrada fora do formato esperado do Obrasgov.br."""


def _data(v, campo: str) -> str | None:
    """Aceita 'AAAA-MM-DD' ou 'AAAA-MM-DDThh:mm:ss[.ffffff]' (formatos vistos na API) → 'AAAA-MM-DD'."""
    if v in (None, ""):
        return None
    if not isinstance(v, str):
        raise ErroObrasgov(f"{campo}: data deve ser texto ISO, recebido {v!r}")
    try:
        if "T" in v:
            return datetime.fromisoformat(v).date().isoformat()
        return date.fromisoformat(v).isoformat()
    except ValueError:
        raise ErroObrasgov(f"{campo}: data inválida {v!r}") from None


def _lista(entrada: dict, recurso: str, avisos: list[str]) -> list[dict]:
    """Registros-objeto do envelope paginado. Registro que não é objeto é ignorado COM aviso (nunca em silêncio)."""
    bloco = entrada.get(recurso)
    if bloco is None:
        return []
    if not isinstance(bloco, dict) or not isinstance(bloco.get("data"), list):
        raise ErroObrasgov(f"{recurso}: esperado o envelope paginado {{'data': [...], ...}}")
    total = bloco.get("total_items")
    if isinstance(total, int) and not isinstance(total, bool) and len(bloco["data"]) < total:
        # só parte das páginas: o adaptador não pagina (não acessa a rede); quem busca junta as páginas
        raise ErroObrasgov(f"{recurso}: {len(bloco['data'])} de {total} registros; junte todas as páginas antes "
                           "de adaptar")
    itens = [x for x in bloco["data"] if isinstance(x, dict)]
    ignorados = len(bloco["data"]) - len(itens)
    if ignorados:
        avisos.append(f"{recurso}: {ignorados} registro(s) ignorado(s) por não serem objetos JSON")
    return itens


def _objetos(v, campo: str) -> list[dict]:
    """Lista aninhada que deve conter só objetos (eixos_tipos, executores, pins, motivos...). Ausente/None → []."""
    if v is None:
        return []
    if not isinstance(v, list) or not all(isinstance(x, dict) for x in v):
        raise ErroObrasgov(f"{campo}: esperado lista de objetos JSON, recebido {v!r:.80}")
    return v


def _valor(v, campo: str) -> float | int | None:
    """Valor monetário: número finito ou ausente. Texto ('R$ 10', '1.000,00'), booleano e NaN/inf são recusados."""
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ErroObrasgov(f"{campo}: valor monetário deve ser número, recebido {v!r:.80}")
    if not math.isfinite(v):
        raise ErroObrasgov(f"{campo}: valor monetário não finito {v!r}")
    return v


def _id_inteiro(v, campo: str) -> int:
    """Ids numéricos da API (id_contrato, id_execucao_fisica): inteiro; texto/booleano/ausente → erro.
    Garante também que a ordenação por id nunca compare tipos misturados."""
    if isinstance(v, bool) or not isinstance(v, int):
        raise ErroObrasgov(f"{campo}: esperado inteiro, recebido {v!r:.80}")
    return v


def _tipo_obra(proj: dict) -> str:
    textos = " ".join(str(e.get(k) or "") for e in _objetos(proj.get("eixos_tipos"), "eixos_tipos")
                      for k in ("tipo", "subtipo"))
    textos += " " + str(proj.get("desc_nome") or "")
    t = textos.lower()
    if "ferrov" in t:
        return "ferrovia"
    if "rodov" in t or re.search(r"\bbr-", t):
        return "rodovia"
    return "desconhecido"


def converter(entrada: dict) -> dict:
    """Converte o JSON no formato do Obrasgov.br para o esquema parcial do INFRA 4D (ver docstring)."""
    if not isinstance(entrada, dict):
        raise ErroObrasgov("a entrada deve ser um objeto JSON")
    avisos: list[str] = []
    projs = _lista(entrada, "projeto_investimento", avisos)
    if len(projs) != 1:
        raise ErroObrasgov(f"esperado exatamente 1 projeto de investimento, recebidos {len(projs)}")
    p = projs[0]
    pid = p.get("id_projeto_investimento")
    if not isinstance(pid, str) or not _RE_ID.match(pid):
        raise ErroObrasgov(f"id_projeto_investimento fora do formato 99999.99-99: {pid!r}")

    outros = {r: _lista(entrada, r, avisos) for r in RECURSOS[1:]}
    for r, itens in outros.items():
        alheios = sorted({str(x.get("id_projeto_investimento")) for x in itens} - {pid})
        if alheios:
            raise ErroObrasgov(f"{r}: registros de outro projeto ({', '.join(alheios)}); filtre por {pid}")

    ficticio = entrada.get("_infra4d_ficticio") is True

    # ---- avanço físico (série global)
    serie = []
    for e in outros["execucao_fisica"]:
        id_exec = _id_inteiro(e.get("id_execucao_fisica"), "execucao_fisica.id_execucao_fisica")
        pct = e.get("percentual_execucao_fisica")
        if isinstance(pct, bool) or not isinstance(pct, (int, float)) or not math.isfinite(pct) or not 0 <= pct <= 100:
            raise ErroObrasgov(f"execucao_fisica {e.get('id_execucao_fisica')}: percentual inválido {pct!r}")
        ref = (_data(e.get("dt_final_execucao"), "dt_final_execucao")
               or _data(e.get("dt_atualizacao_execucao"), "dt_atualizacao_execucao"))
        if ref is None:
            raise ErroObrasgov(f"execucao_fisica {e.get('id_execucao_fisica')}: sem data de referência")
        serie.append({"data": ref, "percentual": float(pct),
                      "atualizado_em": _data(e.get("dt_atualizacao_execucao"), "dt_atualizacao_execucao"),
                      "forma_execucao": e.get("tipo_forma_execucao"),
                      "motivos": [m.get("descricao_motivo")
                                  for m in _objetos(e.get("motivos"), f"execucao_fisica {id_exec}.motivos")],
                      "indicativos": [i.get("descricao_indicativo")
                                      for i in _objetos(e.get("indicativos"), f"execucao_fisica {id_exec}.indicativos")],
                      "id_origem": id_exec})
    serie.sort(key=lambda x: (x["data"], x["id_origem"]))
    for a, b in zip(serie, serie[1:]):
        if b["percentual"] < a["percentual"]:
            avisos.append(f"avanço físico DIMINUI de {a['percentual']:g}% ({a['data']}) para "
                          f"{b['percentual']:g}% ({b['data']}): revisão de medição ou erro de cadastro")

    # ---- lotes = contratos
    lotes = []
    contratos = [(_id_inteiro(c.get("id_contrato"), "contrato.id_contrato"), c) for c in outros["contrato"]]
    for id_c, c in sorted(contratos, key=lambda x: x[0]):
        lotes.append({"id": f"C{id_c}", "nome": c.get("objeto_contrato") or c.get("numero_contrato"),
                      "construtora": c.get("fornecedor_contrato"), "km_ini": None, "km_fim": None,
                      "contrato": {"numero": c.get("numero_contrato"), "situacao": c.get("situacao_contrato"),
                                   "vigencia_inicio": _data(c.get("vigencia_inicio_contrato"), "vigencia_inicio_contrato"),
                                   "vigencia_fim": _data(c.get("vigencia_fim_contrato"), "vigencia_fim_contrato"),
                                   "valor_global": _valor(c.get("valor_global_contrato"),
                                                          f"contrato {id_c}.valor_global_contrato"),
                                   "valor_acumulado": _valor(c.get("valor_acumulado_contrato"),
                                                             f"contrato {id_c}.valor_acumulado_contrato")},
                      "id_origem": id_c})

    # ---- marcos
    marcos = []
    for chave, campo, tipo in (("M-INICIO-PREVISTO", "dt_inicial_prevista", "marco_inicio"),
                               ("M-FIM-PREVISTO", "dt_final_prevista", "marco_termino"),
                               ("M-INICIO-EFETIVO", "dt_inicial_efetiva", "marco_inicio"),
                               ("M-FIM-EFETIVO", "dt_final_efetiva", "marco_termino")):
        d = _data(p.get(campo), campo)
        if d:
            marcos.append({"id": chave, "tipo": tipo, "data": d, "campo_origem": campo})

    inicio = _data(p.get("dt_inicial_efetiva"), "dt_inicial_efetiva") or _data(p.get("dt_inicial_prevista"),
                                                                                 "dt_inicial_prevista")
    data_status = max((x["atualizado_em"] or x["data"] for x in serie), default=None)
    tipo = _tipo_obra(p)
    aviso = ("DADOS FICTÍCIOS — fixture no formato do Obrasgov.br" if ficticio else
             "Dados do Obrasgov.br (origem pública). Tratar conforme o ADR de dado real.")

    return {
        "meta": {"aviso": aviso, "ficticio": ficticio, "fonte": FONTE, "tipo_obra": tipo,
                 "inicio_projeto": inicio, "data_status": data_status,
                 "termino_contratual": _data(p.get("dt_final_prevista"), "dt_final_prevista"),
                 "situacao": p.get("situacao"), "ind_bim": p.get("ind_bim")},
        "ferrovia": {"id": pid, "nome": p.get("desc_nome"), "tipo": tipo, "extensao_km": None,
                     "uf": p.get("uf_principal"), "orgao_responsavel": p.get("organizacao_resp"),
                     "executores": [x.get("organizacao_executor") for x in _objetos(p.get("executores"), "executores")]},
        "lotes": lotes,
        "marcos": marcos,
        "avanco_fisico": serie,
        "situacoes": [{"data": _data(h.get("data_historico_situacao_investimento"), "data_historico_situacao_investimento"),
                       "situacao": h.get("descricao_historico_situacao_investimento"),
                       "justificativa": h.get("justificativa_cancelada_paralisada"),
                       "fase_tratativas": h.get("fase_tratativas_situacao_investimento"),
                       "id_origem": h.get("id_historico_situacao_investimento")}
                      for h in outros["historico_situacao_cancelada_paralisada"]],
        "localizacao": {"municipios": [{"uf": g.get("sg_uf"), "municipio": g.get("no_municipio"),
                                        "cod_ibge": g.get("cod_ibge")} for g in outros["geometria"]],
                        "pins": [{"pin": x.get("pin"), "lat": x.get("latitude"), "lon": x.get("longitude")}
                                 for x in _objetos(p.get("pins"), "pins")]},
        "financeiro": {"investimento_previsto": sum(
                           (_valor(x.get("vl_investimento_previsto"), "investimentos_previstos.vl_investimento_previsto") or 0)
                           for x in _objetos(p.get("investimentos_previstos"), "investimentos_previstos")),
                       "valor_global_contratos": sum((c["contrato"]["valor_global"] or 0) for c in lotes)},
        "rastreio": {"id_projeto_investimento": pid,
                     "execucoes": [x["id_origem"] for x in serie], "contratos": [x["id_origem"] for x in lotes]},
        "lacunas": [
            "atividades, relações e calendários (o Obrasgov não publica cronograma): importar MSPDI/XER da obra",
            "quantidades, produtividade e boletins por serviço (só há percentual físico GLOBAL)",
            "km/estaca dos lotes e eixo (só municípios e pins pontuais)",
        ],
        "avisos": avisos,
    }
