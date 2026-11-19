"""Exportação para BI (Power BI, Excel, Superset como DESTINO), só biblioteca padrão.

Tabelas "tidy" para modelo estrela: dimensões (obra, lote, segmento, serviço,
atividade) e fatos (cronograma por cenário, boletins, curva S, marcos e, se os
módulos existirem, conflitos do balanço e histograma de recursos).

CSV:
- separador e decimal configuráveis (padrão pt-BR: ``;`` e ``,``); separador e decimal iguais
  são recusados;
- UTF-8 COM BOM (o Excel brasileiro precisa do BOM para acentuar certo);
- datas ISO (AAAA-MM-DD); booleanos 1/0; vazio = sem valor;
- proteção contra *CSV injection*: célula de TEXTO que começa com ``= + - @``, TAB ou CR
  recebe um apóstrofo na frente (recomendação OWASP), para o Excel não a tratar como fórmula.
  Colunas numéricas não são alteradas.

Nada é gravado em disco por este módulo: tudo sai como texto/bytes (resposta HTTP).
"""

from __future__ import annotations

import csv
import io
import re
import json
import math
import zipfile
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable
from .obra import tipo_obra

CENARIOS_EXPORTADOS = ("linha_base", "construtora", "independente", "simulado")
SEPARADORES = {";": ";", ",": ",", "tab": "\t", "\t": "\t", "|": "|"}
DECIMAIS = (",", ".")
PREFIXOS_PERIGOSOS = ("=", "+", "-", "@", "\t", "\r")


class ErroExportacao(ValueError):
    """Parâmetro de exportação inválido."""


@dataclass(frozen=True)
class Coluna:
    nome: str
    tipo: str  # texto | data | inteiro | decimal | booleano
    unidade: str
    origem: str


def C(nome, tipo, unidade, origem):
    return Coluna(nome, tipo, unidade, origem)


@dataclass
class Tabela:
    nome: str
    descricao: str
    colunas: list[Coluna]
    linhas: list[dict]


# =============================================================================
# Formatação CSV
# =============================================================================
# formas de largura total (o Excel/LibreOffice podem normalizar para o ASCII)
PREFIXOS_LARGURA_TOTAL = ("＝", "＋", "－", "＠")


def neutralizar(texto: str) -> str:
    """Anti CSV injection: prefixa apóstrofo em texto que o Excel interpretaria como fórmula.

    Defesa em profundidade (r11): olha também o 1º caractere DEPOIS dos espaços/quebras iniciais
    (" =cmd", "\\n=cmd") e as formas de largura total (＝ ＋ － ＠)."""
    if not texto:
        return texto
    inicio = texto.lstrip()
    perigoso = texto.startswith(PREFIXOS_PERIGOSOS) or (
        inicio != "" and inicio.startswith(PREFIXOS_PERIGOSOS[:4] + PREFIXOS_LARGURA_TOTAL)) or \
        texto.startswith(PREFIXOS_LARGURA_TOTAL)
    return "'" + texto if perigoso else texto


def nome_seguro(texto: str, padrao: str = "obra") -> str:
    """Trecho de nome de arquivo só com [A-Za-z0-9._-] (cabeçalho Content-Disposition, r11)."""
    limpo = re.sub(r"[^A-Za-z0-9._-]+", "_", texto or "").strip("._")
    return limpo[:80] or padrao


def _fmt(valor, tipo: str, decimal: str) -> str:
    if valor is None or valor == "":
        return ""
    if tipo == "booleano":
        return "1" if valor else "0"
    if tipo == "inteiro" and isinstance(valor, int):  # sem passar por float: exato em qualquer tamanho (r11)
        return str(int(valor))
    if tipo == "inteiro" and isinstance(valor, str) and re.fullmatch(r"-?\d+", valor.strip()):
        return str(int(valor.strip()))
    if tipo in ("inteiro", "decimal"):
        try:
            v = float(valor)
        except (TypeError, ValueError):
            return neutralizar(str(valor))  # dado fora do tipo declarado: sai como texto neutralizado
        if not math.isfinite(v):
            return ""
        if tipo == "inteiro" and v == int(v):
            return str(int(v))
        txt = repr(round(v, 9))
        if "e" in txt or "E" in txt:  # notação científica não é lida pelo Excel/Power BI pt-BR
            txt = format(Decimal(txt), "f")
            if "." in txt:
                txt = txt.rstrip("0").rstrip(".")
        if txt.endswith(".0"):
            txt = txt[:-2]
        return txt.replace(".", decimal)
    texto = valor if isinstance(valor, str) else (json.dumps(valor, ensure_ascii=False)
                                                  if isinstance(valor, (list, dict)) else str(valor))
    return neutralizar(texto)


def parametros_csv(sep: str | None, decimal: str | None) -> tuple[str, str]:
    s = SEPARADORES.get(sep if sep is not None else ";")
    if s is None:
        raise ErroExportacao(f"separador inválido {sep!r}; use ';', ',', '|' ou 'tab'")
    d = decimal if decimal is not None else ","
    if d not in DECIMAIS:
        raise ErroExportacao(f"decimal inválido {decimal!r}; use ',' ou '.'")
    if s == d:
        raise ErroExportacao("separador e decimal não podem ser o mesmo caractere")
    return s, d


def para_csv(tabela: Tabela, sep: str = ";", decimal: str = ",") -> bytes:
    """CSV em UTF-8 com BOM."""
    s, d = parametros_csv(sep, decimal)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=s, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    w.writerow([c.nome for c in tabela.colunas])
    for linha in tabela.linhas:
        w.writerow([_fmt(linha.get(c.nome), c.tipo, d) for c in tabela.colunas])
    return buf.getvalue().encode("utf-8-sig")


# =============================================================================
# Montagem das tabelas
# =============================================================================
def chave_obra(obra: str | None, projeto) -> str:
    return obra or tipo_obra(projeto)  # sem ?obra=: o tipo DECLARADO (P8), nunca "ferrovia" por padrão


def _obra(projeto, oid: str) -> Tabela:
    d = projeto.dados
    meta = d["meta"]
    tipo = tipo_obra(projeto)
    info = d.get("ferrovia") or {}  # bloco de identificação da obra (chave do esquema, vale para os 2 tipos)
    cols = [C("obra_id", "texto", "", "id da obra na API (?obra=)"),
            C("nome", "texto", "", "dados.ferrovia.nome (bloco de identificação da obra)"),
            C("tipo_obra", "texto", "", "meta.tipo_obra (declarado: ferrovia ou rodovia)"),
            C("extensao_km", "decimal", "km", "extensao_km da obra"),
            C("inicio_projeto", "data", "", "meta.inicio_projeto"),
            C("data_status", "data", "", "meta.data_status"),
            C("termino_linha_base", "data", "", "meta.termino_linha_base"),
            C("ficticio", "booleano", "", "meta.ficticio (dados sintéticos)"),
            C("versao_premissas", "texto", "", "meta.versao_premissas")]
    linha = {"obra_id": oid, "nome": info.get("nome"), "tipo_obra": tipo, "extensao_km": info.get("extensao_km"),
             "inicio_projeto": meta.get("inicio_projeto"), "data_status": meta.get("data_status"),
             "termino_linha_base": meta.get("termino_linha_base"), "ficticio": bool(meta.get("ficticio")),
             "versao_premissas": meta.get("versao_premissas")}
    return Tabela("dim_obra", "Uma linha por obra.", cols, [linha])


def _dims(projeto, oid: str) -> list[Tabela]:
    d = projeto.dados
    lotes = Tabela("dim_lote", "Lotes de construção.", [
        C("obra_id", "texto", "", "dim_obra"), C("lote_id", "texto", "", "lotes.id"),
        C("nome", "texto", "", "lotes.nome"), C("km_ini", "decimal", "km", "lotes.km_ini"),
        C("km_fim", "decimal", "km", "lotes.km_fim"), C("construtora", "texto", "", "lotes.construtora (fictícia)")],
        [{"obra_id": oid, "lote_id": x["id"], **{k: x.get(k) for k in ("nome", "km_ini", "km_fim", "construtora")}}
         for x in d.get("lotes", [])])
    segs = Tabela("dim_segmento", "Segmentos (trechos) de cada lote.", [
        C("obra_id", "texto", "", "dim_obra"), C("segmento_id", "texto", "", "segmentos.id"),
        C("lote_id", "texto", "", "segmentos.lote_id → dim_lote"), C("km_ini", "decimal", "km", "segmentos.km_ini"),
        C("km_fim", "decimal", "km", "segmentos.km_fim"), C("estaca_ini", "decimal", "estaca", "segmentos.estaca_ini"),
        C("estaca_fim", "decimal", "estaca", "segmentos.estaca_fim")],
        [{"obra_id": oid, "segmento_id": x["id"],
          **{k: x.get(k) for k in ("lote_id", "km_ini", "km_fim", "estaca_ini", "estaca_fim")}}
         for x in d.get("segmentos", [])])
    servs = Tabela("dim_servico", "Serviços (tipos de trabalho) e premissas de produtividade.", [
        C("obra_id", "texto", "", "dim_obra"), C("servico_id", "texto", "", "servicos.id"),
        C("nome", "texto", "", "servicos.nome"), C("disciplina", "texto", "", "servicos.disciplina"),
        C("unidade", "texto", "", "servicos.unidade"),
        C("produtividade_planejada", "decimal", "unidade/equipe·dia", "servicos.produtividade_planejada"),
        C("equipes_padrao", "inteiro", "equipes", "servicos.equipes_padrao"),
        C("calendario", "texto", "", "servicos.calendario"),
        C("cadastrado", "booleano", "", "1 = está em servicos; 0 = derivado das atividades (sem cadastro)")],
        [{"obra_id": oid, "servico_id": x["id"],
          **{k: x.get(k) for k in ("nome", "disciplina", "unidade", "produtividade_planejada", "equipes_padrao",
                                   "calendario")}, "cadastrado": True}
         for x in d.get("servicos", [])])
    # integridade da estrela: serviço usado por atividade mas ausente do cadastro (ex.: SIN na ferrovia,
    # LIB na rodovia, de duração fixa) entra como linha derivada, marcada cadastrado = 0
    conhecidos = {x["id"] for x in d.get("servicos", [])}
    for a in d["atividades"]:
        sid = a.get("servico_id")
        if sid and sid not in conhecidos:
            conhecidos.add(sid)
            servs.linhas.append({"obra_id": oid, "servico_id": sid, "nome": a.get("disciplina") or sid,
                                 "disciplina": a.get("disciplina"), "unidade": a.get("unidade"),
                                 "produtividade_planejada": None, "equipes_padrao": None,
                                 "calendario": a.get("calendario"), "cadastrado": False})
    campos_ativ = ("nome", "tipo", "lote_id", "segmento_id", "servico_id", "disciplina", "km_ini", "km_fim",
                   "unidade", "quantidade_total", "produtividade_planejada", "equipes", "calendario", "inicio_lb",
                   "termino_lb", "status", "inicio_real", "termino_real", "quantidade_executada")
    ativ = Tabela("dim_atividade", "Atividades do cronograma (dados de cadastro e progresso na data de status).", [
        C("obra_id", "texto", "", "dim_obra"), C("atividade_id", "texto", "", "atividades.id"),
        C("nome", "texto", "", "atividades.nome"),
        C("tipo", "texto", "", "atividades.tipo (tarefa, marco_inicio, marco_termino)"),
        C("lote_id", "texto", "", "→ dim_lote"), C("segmento_id", "texto", "", "→ dim_segmento"),
        C("servico_id", "texto", "", "→ dim_servico"), C("disciplina", "texto", "", "atividades.disciplina"),
        C("km_ini", "decimal", "km", "atividades.km_ini"), C("km_fim", "decimal", "km", "atividades.km_fim"),
        C("unidade", "texto", "", "atividades.unidade"),
        C("quantidade_total", "decimal", "unidade da atividade", "atividades.quantidade_total"),
        C("produtividade_planejada", "decimal", "unidade/equipe·dia", "atividades.produtividade_planejada"),
        C("equipes", "inteiro", "equipes", "atividades.equipes"), C("calendario", "texto", "", "atividades.calendario"),
        C("inicio_lb", "data", "", "atividades.inicio_lb (linha de base)"),
        C("termino_lb", "data", "", "atividades.termino_lb (linha de base)"),
        C("status", "texto", "", "atividades.status na data de status"),
        C("inicio_real", "data", "", "atividades.inicio_real"), C("termino_real", "data", "", "atividades.termino_real"),
        C("quantidade_executada", "decimal", "unidade da atividade", "atividades.quantidade_executada (soma dos boletins)")],
        [{"obra_id": oid, "atividade_id": a["id"], **{k: a.get(k) for k in campos_ativ}}
         for a in d["atividades"]])
    return [lotes, segs, servs, ativ]


def _fato_cronograma(oid: str, resultados: dict[str, dict]) -> Tabela:
    cols = [C("obra_id", "texto", "", "dim_obra"), C("atividade_id", "texto", "", "→ dim_atividade"),
            C("cenario", "texto", "", "linha_base | construtora | independente | simulado"),
            C("data_status", "data", "", "data de status do cenário (vazia na linha de base)"),
            C("inicio", "data", "", "motor CPM próprio: início exibido"),
            C("termino", "data", "", "motor CPM próprio: término exibido (último dia trabalhado)"),
            C("es", "data", "", "início cedo (fronteira)"), C("ef", "data", "", "término cedo (fronteira exclusiva)"),
            C("ls", "data", "", "início tarde (fronteira)"), C("lf", "data", "", "término tarde (fronteira exclusiva)"),
            C("duracao", "inteiro", "dias úteis", "duração remanescente usada no cálculo"),
            C("folga_total", "inteiro", "dias úteis", "motor CPM"), C("folga_livre", "inteiro", "dias úteis", "motor CPM"),
            C("critica", "booleano", "", "folga total ≤ 0 ou caminho mais longo"),
            C("caminho_mais_longo", "booleano", "", "motor CPM (cadeia que determina o término)"),
            C("status", "texto", "", "status da atividade no cenário"),
            C("regra_duracao", "texto", "", "memória de cálculo: quantidade | duração fixa | marco | concluída"),
            C("produtividade", "decimal", "unidade/equipe·dia", "memória de cálculo (produtividade usada)"),
            C("fonte_produtividade", "texto", "", "memória de cálculo: de onde veio a produtividade"),
            C("quantidade_remanescente", "decimal", "unidade da atividade", "memória de cálculo")]
    linhas = []
    for cen, r in resultados.items():
        for aid, a in r["atividades"].items():
            mem = a.get("memoria") or {}
            linhas.append({"obra_id": oid, "atividade_id": aid, "cenario": cen, "data_status": r.get("data_status"),
                           **{k: a.get(k) for k in ("inicio", "termino", "es", "ef", "ls", "lf", "duracao",
                                                    "folga_total", "folga_livre", "critica", "caminho_mais_longo",
                                                    "status")},
                           "regra_duracao": mem.get("regra"), "produtividade": mem.get("produtividade"),
                           "fonte_produtividade": mem.get("fonte_produtividade"),
                           "quantidade_remanescente": mem.get("quantidade_remanescente")})
    return Tabela("fato_cronograma", "Atividade × cenário: datas, duração, folgas e criticidade calculadas pelo "
                                     "motor CPM próprio.", cols, linhas)


def _fato_boletim(projeto, oid: str) -> Tabela:
    ativ = projeto.atividades
    cols = [C("obra_id", "texto", "", "dim_obra"), C("atividade_id", "texto", "", "→ dim_atividade"),
            C("semana_inicio", "data", "", "medicoes.semana_inicio"),
            C("quantidade", "decimal", "unidade da atividade", "medicoes.quantidade"),
            C("unidade", "texto", "", "dim_atividade.unidade"),
            C("equipes_dias", "decimal", "equipe·dia", "medicoes.equipes_dias"),
            C("produtividade", "decimal", "unidade/equipe·dia", "quantidade ÷ equipes_dias (vazio se 0)"),
            C("origem", "texto", "", "medicoes.origem")]
    linhas = []
    for m in projeto.dados.get("medicoes", []):
        if m.get("atividade_id") not in ativ:
            continue  # órfão: fica fora do fato (chave estrangeira íntegra) e é contado nas NOTAS do LEIAME
        ed = m.get("equipes_dias") or 0
        linhas.append({"obra_id": oid, "atividade_id": m["atividade_id"], "semana_inicio": m.get("semana_inicio"),
                       "quantidade": m.get("quantidade"), "unidade": (ativ.get(m["atividade_id"]) or {}).get("unidade"),
                       "equipes_dias": ed, "produtividade": (m["quantidade"] / ed) if ed else None,
                       "origem": m.get("origem")})
    return Tabela("fato_boletim", "Boletins de medição semanais (produção por atividade).", cols, linhas)


def _fato_curva_s(projeto, oid: str, resultados: dict[str, dict]) -> Tabela:
    from .painel import curva_s

    cs = curva_s(projeto, resultados)
    linhas = [{"obra_id": oid, "data": dt, "cenario": cen, "avanco_pct": serie[i]}
              for cen, serie in cs["series"].items() for i, dt in enumerate(cs["datas"])]
    return Tabela("fato_curva_s", "Curva S: avanço físico acumulado por data e cenário (peso = esforço planejado).", [
        C("obra_id", "texto", "", "dim_obra"), C("data", "data", "", "datas a cada 14 dias (painel.curva_s)"),
        C("cenario", "texto", "", "cenário"),
        C("avanco_pct", "decimal", "%", "painel.avanco: média ponderada por esforço planejado (equipe·dia)")], linhas)


def _fato_marcos(projeto, oid: str, resultados: dict[str, dict]) -> Tabela:
    from .painel import marcos_contratuais

    ms = marcos_contratuais(projeto, resultados)
    linhas = [{"obra_id": oid, "marco_id": m.get("id"), "nome": m.get("nome"), "lote_id": m.get("lote_id"),
               "prazo": m.get("prazo"), "termino_construtora": m.get("construtora"),
               "desvio_construtora_dias": m.get("desvio_construtora"),
               "termino_independente": m.get("independente"),
               "desvio_independente_dias": m.get("desvio_independente")} for m in ms]
    return Tabela("fato_marcos", "Marcos contratuais: prazo × previsões e desvios.", [
        C("obra_id", "texto", "", "dim_obra"), C("marco_id", "texto", "", "→ dim_atividade"),
        C("nome", "texto", "", "nome do marco"), C("lote_id", "texto", "", "→ dim_lote"),
        C("prazo", "data", "", "prazo contratual (fictício)"),
        C("termino_construtora", "data", "", "previsão do cenário construtora"),
        C("desvio_construtora_dias", "inteiro", "dias corridos", "término construtora − prazo"),
        C("termino_independente", "data", "", "previsão do cenário independente"),
        C("desvio_independente_dias", "inteiro", "dias corridos", "término independente − prazo")], linhas)


def _fato_conflitos(projeto, oid: str, resultados: dict[str, dict]) -> Tabela | None:
    try:
        from .recursos import conflitos_balanco
    except Exception:  # noqa: BLE001 — módulo opcional
        return None
    linhas = []
    for cen in ("construtora", "independente"):
        c = conflitos_balanco(projeto, resultados[cen])
        for tipo, chave in (("previsto", "conflitos"), ("real", "conflitos_reais")):
            for x in c.get(chave) or []:
                if not isinstance(x, dict):
                    continue
                servs = x.get("servicos") or [None, None]
                ativs = x.get("atividades") or [None, None]
                linhas.append({"obra_id": oid, "cenario": cen, "tipo": tipo, "lote_id": x.get("lote"),
                               "segmento_id": x.get("segmento"), "servico_antecessor": servs[0],
                               "servico_sucessor": servs[-1], "atividade_antecessora": ativs[0],
                               "atividade_sucessora": ativs[-1], "data": x.get("data"), "data_fim": x.get("data_fim"),
                               "km": x.get("km"), "distancia_km_min": x.get("distancia_km_min"),
                               "dias": x.get("dias"), "espacial": x.get("espacial"), "temporal": x.get("temporal"),
                               "ultrapassagem": x.get("ultrapassagem")})
    return Tabela("fato_conflitos", "Conflitos de frentes no balanço (linha de balanço km × tempo).", [
        C("obra_id", "texto", "", "dim_obra"), C("cenario", "texto", "", "construtora | independente"),
        C("tipo", "texto", "", "previsto (a partir da data de status) | real"),
        C("lote_id", "texto", "", "→ dim_lote"), C("segmento_id", "texto", "", "→ dim_segmento"),
        C("servico_antecessor", "texto", "", "→ dim_servico"), C("servico_sucessor", "texto", "", "→ dim_servico"),
        C("atividade_antecessora", "texto", "", "→ dim_atividade"),
        C("atividade_sucessora", "texto", "", "→ dim_atividade"),
        C("data", "data", "", "início do conflito"), C("data_fim", "data", "", "fim do conflito"),
        C("km", "decimal", "km", "posição da frente sucessora"),
        C("distancia_km_min", "decimal", "km", "menor distância entre frentes"),
        C("dias", "inteiro", "dias corridos", "duração do conflito"),
        C("espacial", "booleano", "", "frentes mais próximas que o buffer em km"),
        C("temporal", "booleano", "", "frentes mais próximas que o buffer em dias"),
        C("ultrapassagem", "booleano", "", "sucessora ultrapassa a antecessora")], linhas)


def _fato_recursos(projeto, oid: str, resultados: dict[str, dict]) -> Tabela | None:
    try:
        from .recursos import histograma
    except Exception:  # noqa: BLE001 — módulo opcional
        return None
    linhas = []
    for cen in ("construtora", "independente"):
        h = histograma(projeto, resultados[cen], agrupar="semana")
        for s in h.get("series", []):
            for p in s.get("periodos", []):
                linhas.append({"obra_id": oid, "cenario": cen, "recurso": s.get("recurso"), "lote_id": s.get("lote"),
                               "servico_id": s.get("servico"), "semana": p.get("periodo"),
                               "equipes_pico": p.get("equipes"), "equipes_dia": p.get("equipes_dia"),
                               "capacidade": s.get("capacidade")})
    return Tabela("fato_recursos", "Histograma semanal de equipes por recurso (lote/serviço).", [
        C("obra_id", "texto", "", "dim_obra"), C("cenario", "texto", "", "construtora | independente"),
        C("recurso", "texto", "", "lote/serviço"), C("lote_id", "texto", "", "→ dim_lote"),
        C("servico_id", "texto", "", "→ dim_servico"), C("semana", "data", "", "segunda-feira da semana"),
        C("equipes_pico", "inteiro", "equipes", "pico diário de equipes na semana"),
        C("equipes_dia", "inteiro", "equipe·dia", "soma de equipes·dia na semana"),
        C("capacidade", "inteiro", "equipes", "capacidade declarada do recurso")], linhas)


def montar_tabelas(projeto, obra: str | None, resultado: Callable[[str], dict]) -> tuple[dict[str, Tabela], list[str]]:
    """Todas as tabelas da obra. ``resultado(cenario)`` → dict de ``cenarios.executar`` (ex.: ``Estado.resultado``).
    Devolve (tabelas, notas). Fato opcional cujo módulo falta ou falha é omitido e registrado nas notas."""
    oid = chave_obra(obra, projeto)
    resultados = {c: resultado(c) for c in CENARIOS_EXPORTADOS}
    tabs = [_obra(projeto, oid), *_dims(projeto, oid), _fato_cronograma(oid, resultados),
            _fato_boletim(projeto, oid), _fato_curva_s(projeto, oid, resultados),
            _fato_marcos(projeto, oid, resultados)]
    notas = []
    orfaos = [m for m in projeto.dados.get("medicoes", []) if m.get("atividade_id") not in projeto.atividades]
    if orfaos:
        ids = sorted({str(m.get("atividade_id")) for m in orfaos})
        notas.append(f"fato_boletim: {len(orfaos)} boletim(ns) de atividade inexistente na obra excluído(s) "
                     f"(também ignorados nos cálculos): {', '.join(ids[:20])}{' ...' if len(ids) > 20 else ''}")
    for nome, f in (("fato_conflitos", _fato_conflitos), ("fato_recursos", _fato_recursos)):
        try:
            t = f(projeto, oid, resultados)
        except Exception as e:  # noqa: BLE001 — módulo opcional não derruba a exportação
            t = None
            notas.append(f"{nome} omitida: falha no módulo ({type(e).__name__}: {e})")
        if t is None:
            if not any(n.startswith(nome) for n in notas):
                notas.append(f"{nome} omitida: módulo recursos indisponível")
        else:
            tabs.append(t)
    return {t.nome: t for t in tabs}, notas


TIPOS_DESC = {"texto": "texto", "data": "data ISO AAAA-MM-DD", "inteiro": "número inteiro",
              "decimal": "número decimal (separador decimal conforme o parâmetro)", "booleano": "1 = sim, 0 = não"}


def leiame(tabelas: dict[str, Tabela], notas: list[str], sep: str, decimal: str, projeto) -> str:
    meta = projeto.dados["meta"]
    nome_sep = {";": "ponto e vírgula (;)", ",": "vírgula (,)", "\t": "tabulação", "|": "barra vertical (|)"}[sep]
    linhas = [
        "INFRA 4D INTELLIGENCE — pacote de dados para BI",
        "=" * 50,
        "",
        f"Obra: {next(iter(tabelas['dim_obra'].linhas))['obra_id']}  |  data de status: {meta.get('data_status')}",
        f"Aviso: {meta.get('aviso', '')}",
        "",
        "FORMATO",
        f"- CSV em UTF-8 com BOM; separador de campo: {nome_sep}; separador decimal: '{decimal}'.",
        "- Datas em ISO (AAAA-MM-DD). Booleanos: 1/0. Campo vazio = sem valor.",
        "- Proteção contra CSV injection: texto que começaria com = + - @ (ou TAB/CR) recebe um apóstrofo (') na "
        "frente, para o Excel não executá-lo como fórmula. Colunas numéricas não são alteradas.",
        "- Modelo estrela: ligue os fatos às dimensões por obra_id + atividade_id / lote_id / segmento_id / "
        "servico_id.",
        "- Datas e durações vêm do motor CPM próprio (ADR-0003). 'es/ef/ls/lf' são fronteiras: ef/lf são o INÍCIO "
        "do dia seguinte ao último dia trabalhado; use 'termino' para exibir.",
        "",
        "TIPOS",
        *[f"- {k}: {v}" for k, v in TIPOS_DESC.items()],
        "",
        "DICIONÁRIO DE DADOS (tabela / coluna | tipo | unidade | origem)",
    ]
    for t in tabelas.values():
        linhas += ["", f"[{t.nome}.csv] {t.descricao} ({len(t.linhas)} linhas)"]
        for c in t.colunas:
            linhas.append(f"  {c.nome} | {c.tipo} | {c.unidade or '-'} | {c.origem.replace('|', '/')}")
    if notas:
        linhas += ["", "NOTAS"] + [f"- {n}" for n in notas]
    return "\n".join(linhas) + "\n"


def pacote_zip(tabelas: dict[str, Tabela], notas: list[str], projeto, sep: str = ";", decimal: str = ",") -> bytes:
    s, d = parametros_csv(sep, decimal)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for t in tabelas.values():
            z.writestr(f"{t.nome}.csv", para_csv(t, s, d))
        z.writestr("LEIAME.txt", leiame(tabelas, notas, s, d, projeto).encode("utf-8-sig"))
        meta = projeto.dados["meta"]
        if meta.get("ficticio"):
            z.writestr("aviso.txt", ("DADOS FICTÍCIOS\n\n" + meta.get("aviso", "") +
                                     "\n\nGerados para demonstração; não use para decisão real.\n").encode("utf-8-sig"))
    return buf.getvalue()
