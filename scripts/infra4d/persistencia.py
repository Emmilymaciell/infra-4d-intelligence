"""Persistência (SQLite, biblioteca padrão) e histórico sintético da previsão.

Três coisas, num banco só (padrão ``output/infra4d.sqlite``, ignorado pelo Git):

1. **Cenários nomeados**: obra, nome, ajustes, data de criação, término, hash dos
   dados da obra e o resultado completo. Reabrir devolve o resultado gravado, e
   ``reabrir_e_conferir`` recalcula para provar que ele se reproduz (ou diz que os
   dados da obra mudaram desde a gravação).
2. **Snapshots** de previsão por data de status (obra, data de status, cenário,
   término, avanço, cadeia determinante), para a série "como a previsão evoluiu".
3. **Auditoria**: quem (texto informado; o beta NÃO tem autenticação), quando, ação,
   parâmetros e resultado resumido.

E o **histórico sintético** (só em memória, nada é gravado nem o dataset é alterado):
recalcula os cenários independente e construtora "como se" a data de status fosse o
primeiro dia de cada mês do passado, truncando boletins e status àquela data.

Simplificações do histórico sintético (declaradas também em ``SIMPLIFICACOES_HISTORICO``):
- boletim: os dias trabalhados são os ``equipes_dias ÷ equipes`` primeiros dias úteis a partir de
  ``semana_inicio`` (regra do gerador); boletim cortado pela data é RATEADO pelos dias trabalhados
  anteriores a ela (quantidade e equipes·dia proporcionais);
- status na data T: não iniciada se o início real é >= T; concluída se o término real é < T;
  senão em andamento (com o término real apagado);
- quantidade executada em T = soma dos boletins até T (limitada à quantidade total);
- atividade de duração fixa: percentual interpolado linearmente em dias corridos entre o
  início real e o término real (ou a data de status atual);
- a "construtora" do passado é o MESMO critério da construtora de hoje (remanescente na
  produtividade planejada) aplicado aos dados truncados: não é um cronograma que ela de
  fato tenha enviado naquela data;
- lógica, calendários, durações planejadas e restrições são os de hoje (não há versões
  anteriores do cronograma no dataset sintético).
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
import threading
from datetime import date, datetime, timezone
from pathlib import Path

from .calendario import iso, ordinal
from .cenarios import Ajuste, Projeto, executar
from .obra import tipo_obra

RAIZ = Path(__file__).resolve().parents[2]
BANCO_PADRAO = RAIZ / "output" / "infra4d.sqlite"
VARIAVEL_AMBIENTE = "INFRA4D_BANCO"

SIMPLIFICACOES_HISTORICO = [
    "Histórico SINTÉTICO, calculado em memória a partir dos dados fictícios atuais; não é registro de "
    "previsões feitas no passado.",
    "Boletim cortado pela data T é rateado pelos dias trabalhados antes de T (os equipes_dias ÷ equipes primeiros "
    "dias úteis a partir de semana_inicio, regra do gerador sintético): quantidade e equipes·dia proporcionais.",
    "Status em T: não iniciada se início real >= T; concluída se término real < T; senão em andamento.",
    "Quantidade executada em T = soma dos boletins até T; atividade de duração fixa tem o percentual "
    "interpolado linearmente em dias corridos.",
    "A 'construtora' de cada mês aplica o critério atual dela (remanescente na produtividade planejada) aos "
    "dados truncados; não é um cronograma que ela tenha de fato enviado.",
    "Lógica, calendários, durações planejadas e restrições são os de hoje (sem versões anteriores do "
    "cronograma).",
]


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_dados(projeto: Projeto) -> str:
    """SHA-256 do JSON canônico dos dados da obra."""
    bruto = json.dumps(projeto.dados, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def chave_obra(obra: str | None, projeto: Projeto) -> str:
    """Id da obra para gravação: o informado, ou o tipo de obra do meta (ferrovia por padrão)."""
    return obra or tipo_obra(projeto)  # sem ?obra=: o tipo DECLARADO (P8), nunca "ferrovia" por padrão


def _json(v) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


class ErroPersistencia(ValueError):
    """Operação de persistência inválida (nome duplicado, id inexistente...)."""


# =============================================================================
# Banco
# =============================================================================
_ESQUEMA = """
CREATE TABLE IF NOT EXISTS cenarios_salvos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    obra TEXT NOT NULL,
    nome TEXT NOT NULL,
    ajustes_json TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    quem TEXT,
    data_status TEXT,
    termino TEXT,
    hash_dados TEXT NOT NULL,
    resultado_json TEXT NOT NULL,
    UNIQUE (obra, nome)
);
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    obra TEXT NOT NULL,
    data_status TEXT NOT NULL,
    cenario TEXT NOT NULL,
    termino TEXT,
    avanco REAL,
    cadeia_json TEXT NOT NULL,
    hash_dados TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    UNIQUE (obra, data_status, cenario, hash_dados)
);
CREATE TABLE IF NOT EXISTS auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    obra TEXT,
    quem TEXT,
    quando TEXT NOT NULL,
    acao TEXT NOT NULL,
    parametros_json TEXT NOT NULL,
    resultado_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_auditoria_obra ON auditoria (obra, id);
"""


class Banco:
    """Acesso ao SQLite. Uma conexão por operação (seguro entre threads); escrita serializada
    por lock no processo e por transação no SQLite. O arquivo só é criado no primeiro uso."""

    def __init__(self, caminho: Path | str | None = None):
        self.caminho = Path(caminho or os.environ.get(VARIAVEL_AMBIENTE) or BANCO_PADRAO)
        # RLock: a primeira escrita cria o esquema DENTRO do lock de escrita (com Lock simples
        # isso travava o processo — achado ao rodar o teste pela primeira vez)
        self._lock = threading.RLock()
        self._pronto = False

    def _conectar(self) -> sqlite3.Connection:
        if not self._pronto:
            with self._lock:
                if not self._pronto:
                    self.caminho.parent.mkdir(parents=True, exist_ok=True)
                    con = sqlite3.connect(self.caminho, timeout=30)
                    try:
                        con.executescript(_ESQUEMA)
                        con.commit()
                    finally:
                        con.close()
                    self._pronto = True
        con = sqlite3.connect(self.caminho, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    def _escrever(self, sql: str, params: tuple) -> int:
        with self._lock:
            con = self._conectar()
            try:
                with con:
                    cur = con.execute(sql, params)
                    return cur.lastrowid
            finally:
                con.close()

    def _ler(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        con = self._conectar()
        try:
            return con.execute(sql, params).fetchall()
        finally:
            con.close()

    # ------------------------------------------------------------ cenários nomeados
    def salvar_cenario(self, obra: str, nome: str, ajustes: list[Ajuste], resultado: dict, hash_obra: str,
                       quem: str | None = None) -> int:
        nome = (nome or "").strip()
        if not nome:
            raise ErroPersistencia("nome do cenário é obrigatório")
        try:
            return self._escrever(
                "INSERT INTO cenarios_salvos (obra, nome, ajustes_json, criado_em, quem, data_status, termino, "
                "hash_dados, resultado_json) VALUES (?,?,?,?,?,?,?,?,?)",
                (obra, nome, _json([a.__dict__ for a in ajustes]), agora_iso(), quem, resultado.get("data_status"),
                 resultado.get("termino"), hash_obra, _json(resultado)))
        except sqlite3.IntegrityError:
            raise ErroPersistencia(f"já existe cenário salvo com o nome {nome!r} na obra {obra}") from None

    def listar_cenarios(self, obra: str) -> list[dict]:
        rows = self._ler("SELECT id, obra, nome, ajustes_json, criado_em, quem, data_status, termino, hash_dados "
                         "FROM cenarios_salvos WHERE obra = ? ORDER BY id", (obra,))
        return [{**{k: r[k] for k in r.keys() if k != "ajustes_json"}, "ajustes": json.loads(r["ajustes_json"])}
                for r in rows]

    def obter_cenario(self, id_: int) -> dict:
        rows = self._ler("SELECT * FROM cenarios_salvos WHERE id = ?", (id_,))
        if not rows:
            raise ErroPersistencia(f"cenário salvo {id_} inexistente")
        r = rows[0]
        d = {k: r[k] for k in r.keys() if k not in ("ajustes_json", "resultado_json")}
        d["ajustes"] = json.loads(r["ajustes_json"])
        d["resultado"] = json.loads(r["resultado_json"])
        return d

    # ------------------------------------------------------------------ snapshots
    def gravar_snapshot(self, obra: str, cenario: str, resultado: dict, avanco: float | None,
                        hash_obra: str) -> int:
        """Grava (ou substitui) o snapshot da obra/data de status/cenário para estes dados."""
        return self._escrever(
            "INSERT OR REPLACE INTO snapshots (obra, data_status, cenario, termino, avanco, cadeia_json, "
            "hash_dados, criado_em) VALUES (?,?,?,?,?,?,?,?)",
            (obra, resultado.get("data_status") or "", cenario, resultado.get("termino"), avanco,
             _json(resultado.get("cadeia_determinante", [])), hash_obra, agora_iso()))

    def listar_snapshots(self, obra: str, cenario: str | None = None) -> list[dict]:
        sql = "SELECT * FROM snapshots WHERE obra = ?"
        params: tuple = (obra,)
        if cenario:
            sql += " AND cenario = ?"
            params += (cenario,)
        rows = self._ler(sql + " ORDER BY data_status, cenario, id", params)
        return [{**{k: r[k] for k in r.keys() if k != "cadeia_json"},
                 "cadeia_determinante": json.loads(r["cadeia_json"])} for r in rows]

    # ------------------------------------------------------------------ auditoria
    def auditar(self, acao: str, obra: str | None, quem: str | None, parametros: dict, resultado: dict) -> int:
        return self._escrever(
            "INSERT INTO auditoria (obra, quem, quando, acao, parametros_json, resultado_json) VALUES (?,?,?,?,?,?)",
            (obra, (quem or "").strip() or "anônimo (beta sem autenticação)", agora_iso(), acao,
             _json(parametros), _json(resultado)))

    def listar_auditoria(self, obra: str | None = None, limite: int = 200) -> list[dict]:
        if obra:
            rows = self._ler("SELECT * FROM auditoria WHERE obra = ? ORDER BY id DESC LIMIT ?", (obra, limite))
        else:
            rows = self._ler("SELECT * FROM auditoria ORDER BY id DESC LIMIT ?", (limite,))
        return [{"id": r["id"], "obra": r["obra"], "quem": r["quem"], "quando": r["quando"], "acao": r["acao"],
                 "parametros": json.loads(r["parametros_json"]), "resultado": json.loads(r["resultado_json"])}
                for r in rows]


# =============================================================================
# Operações de alto nível (usadas pelas rotas)
# =============================================================================
def salvar_cenario_nomeado(banco: Banco, projeto: Projeto, obra: str, nome: str, ajustes: list[Ajuste],
                           quem: str | None = None) -> dict:
    """Calcula o cenário simulado com os ajustes, grava e audita."""
    resultado = executar(projeto, "simulado", ajustes)
    publico = {k: v for k, v in resultado.items() if not k.startswith("_")}
    id_ = banco.salvar_cenario(obra, nome, ajustes, publico, hash_dados(projeto), quem)
    resumo = {"id": id_, "termino": publico["termino"]}
    banco.auditar("salvar_cenario", obra, quem, {"nome": nome, "ajustes": [a.__dict__ for a in ajustes]}, resumo)
    return {"id": id_, "nome": nome, "obra": obra, "termino": publico["termino"],
            "data_status": publico["data_status"]}


def reabrir_e_conferir(banco: Banco, projeto: Projeto, id_: int) -> dict:
    """Devolve o cenário gravado e confere se ele se reproduz com os dados atuais da obra."""
    salvo = banco.obter_cenario(id_)
    mesmos_dados = salvo["hash_dados"] == hash_dados(projeto)
    recalc = executar(projeto, "simulado", [Ajuste(**a) for a in salvo["ajustes"]])
    recalc = json.loads(_json({k: v for k, v in recalc.items() if not k.startswith("_")}))
    salvo["conferencia"] = {
        "dados_da_obra_iguais": mesmos_dados,
        "reproduz_identico": recalc == salvo["resultado"],
        "termino_recalculado": recalc["termino"],
        "nota": ("resultado gravado e recálculo atual são idênticos" if recalc == salvo["resultado"] else
                 "o recálculo atual DIFERE do gravado" + ("" if mesmos_dados else
                                                          " (os dados da obra mudaram desde a gravação)")),
    }
    return salvo


# =============================================================================
# Histórico sintético
# =============================================================================
def _medicoes_ate(projeto: Projeto, medicoes: list[dict], t: int) -> list[dict]:
    """Boletins "como se" a data de status fosse ``t``.

    Regra (revisão adversarial r10): os dias TRABALHADOS de um boletim são os ``equipes_dias ÷ equipes``
    primeiros dias úteis do calendário da atividade a partir de ``semana_inicio``, dentro da janela do
    boletim (até o próximo boletim da atividade ou +7 dias). É a mesma regra do gerador sintético e de
    ``fiscalizacao.gerar_diarios_sinteticos``. Boletim inteiramente antes de ``t`` fica igual; boletim
    cortado por ``t`` fica só com os dias trabalhados antes de ``t``, com quantidade e equipes·dia
    PROPORCIONAIS; sem nenhum dia antes de ``t``, sai. Antes, o boletim cortado ficava inteiro e trazia
    até 6 dias "do futuro"."""
    por_ativ: dict[str, list[dict]] = {}
    for m in medicoes:
        por_ativ.setdefault(m["atividade_id"], []).append(m)
    proxima: dict[int, int] = {}
    for ms in por_ativ.values():
        ordem = sorted(ms, key=lambda m: m["semana_inicio"])
        for i, m in enumerate(ordem):
            s = ordinal(m["semana_inicio"])
            proxima[id(m)] = min(s + 7, ordinal(ordem[i + 1]["semana_inicio"])) if i + 1 < len(ordem) else s + 7
    saida = []
    for m in medicoes:
        s = ordinal(m["semana_inicio"])
        if s >= t:
            continue
        fim_jan = proxima[id(m)]
        if fim_jan <= t:
            saida.append(m)  # boletim inteiro antes de t
            continue
        a = projeto.atividades.get(m["atividade_id"]) or {}
        cal = projeto.calendarios.get(a.get("calendario"))
        eqs = max(1, int(a.get("equipes") or 1))
        eqd = float(m.get("equipes_dias") or 0)
        n = int(round(eqd / eqs)) if eqd > 0 else 0
        if cal is None or n <= 0:
            if s < t:
                saida.append(m)  # sem como ratear (sem calendário ou sem equipe): mantém (declarado)
            continue
        uteis, d = [], s
        while len(uteis) < n and d < fim_jan:
            if cal.eh_util(d):
                uteis.append(d)
            d += 1
        k = sum(1 for x in uteis if x < t)
        if k == len(uteis):
            saida.append(m)
        elif k > 0:
            frac = k / len(uteis)
            saida.append({**m, "quantidade": round(float(m["quantidade"]) * frac, 6),
                          "equipes_dias": round(eqd * frac, 6) if eqd != n * eqs else k * eqs,
                          "rateado_ate": iso(t)})
    return saida


def projeto_na_data(projeto: Projeto, t: int) -> Projeto:
    """Cópia do projeto "como se" a data de status fosse ``t`` (ordinal). Não altera o original."""
    ds_atual = projeto.data_status
    if t > ds_atual:
        raise ValueError(f"data {iso(t)} posterior à data de status atual {iso(ds_atual)}: não há dados do futuro")
    dados = copy.deepcopy(projeto.dados)
    dados["meta"]["data_status"] = iso(t)
    medicoes = _medicoes_ate(projeto, dados.get("medicoes", []), t)
    dados["medicoes"] = medicoes
    soma: dict[str, float] = {}
    for m in medicoes:
        soma[m["atividade_id"]] = soma.get(m["atividade_id"], 0.0) + m["quantidade"]
    for a in dados["atividades"]:
        ini = ordinal(a.get("inicio_real"))
        fim = ordinal(a.get("termino_real"))
        status_orig = a.get("status", "nao_iniciada")
        if status_orig == "nao_iniciada" or ini is None or ini >= t:
            a["status"] = "nao_iniciada"
            for k in ("inicio_real", "termino_real"):
                a.pop(k, None)
            for k in ("quantidade_executada", "percentual_executado"):
                if k in a:
                    a[k] = 0.0
            continue
        if fim is not None and fim < t and status_orig == "concluida":
            continue  # concluída antes de T: igual a hoje
        a["status"] = "em_andamento"
        a.pop("termino_real", None)
        if a.get("quantidade_total"):
            a["quantidade_executada"] = round(min(a["quantidade_total"], soma.get(a["id"], 0.0)), 6)
        elif a.get("duracao_fixa") is not None:
            pct_final = 100.0 if status_orig == "concluida" else float(a.get("percentual_executado", 0.0))
            fim_ref = (fim + 1) if status_orig == "concluida" else ds_atual
            frac = (t - ini) / max(1, fim_ref - ini)
            a["percentual_executado"] = round(min(pct_final, pct_final * frac), 4)
    # âncora: na data de status atual a truncagem não muda nada (garantido por teste)
    return Projeto(dados)


def datas_mensais(projeto: Projeto) -> list[int]:
    """Primeiro dia de cada mês após o início do projeto, até a data de status atual (inclusive ela)."""
    ini = date.fromordinal(projeto.inicio_projeto)
    fim = projeto.data_status
    datas = []
    ano, mes = ini.year, ini.month
    while True:
        mes += 1
        if mes > 12:
            ano, mes = ano + 1, 1
        d = date(ano, mes, 1).toordinal()
        if d >= fim:
            break
        datas.append(d)
    datas.append(fim)
    return datas


def evolucao_previsao(projeto: Projeto, datas: list[int] | None = None) -> dict:
    """Série "como a previsão evoluiu": independente × construtora × linha de base, mês a mês."""
    from .painel import avanco  # import tardio: painel importa cenarios

    datas = datas or datas_mensais(projeto)
    lb = executar(projeto, "linha_base")
    pontos = []
    anterior = None
    for t in datas:
        pt = projeto_na_data(projeto, t)
        ind = executar(pt, "independente")
        con = executar(pt, "construtora")
        p = {
            "data_status": iso(t),
            "termino_independente": ind["termino"],
            "termino_construtora": con["termino"],
            "termino_linha_base": lb["termino"],
            "diferenca_dias_corridos": ordinal(ind["termino"]) - ordinal(con["termino"]),
            "avanco_real_pct": round(100 * avanco(pt, ind, t), 2),
            "avanco_previsto_lb_pct": round(100 * avanco(projeto, lb, t), 2),
            "cadeia_determinante_independente": ind["cadeia_determinante"],
            "n_boletins": len(pt.dados.get("medicoes", [])),
        }
        if anterior:
            p["escorregamento_independente_dias"] = ordinal(p["termino_independente"]) - ordinal(
                anterior["termino_independente"])
            p["escorregamento_construtora_dias"] = ordinal(p["termino_construtora"]) - ordinal(
                anterior["termino_construtora"])
        pontos.append(p)
        anterior = p
    return {
        "pontos": pontos,
        "narrativa": narrativa(pontos),
        "simplificacoes": list(SIMPLIFICACOES_HISTORICO),
        "aviso": projeto.dados["meta"].get("aviso"),
    }


def narrativa(pontos: list[dict]) -> list[str]:
    """Frases objetivas para a fiscalização, derivadas só da série."""
    if len(pontos) < 2:
        return []
    frases = []
    # maior sequência em que a construtora repetiu a mesma data
    melhor, ini_seq, n = (1, 0), 0, 1
    for i in range(1, len(pontos)):
        if pontos[i]["termino_construtora"] == pontos[i - 1]["termino_construtora"]:
            n += 1
        else:
            n, ini_seq = 1, i
        if n > melhor[0]:
            melhor = (n, ini_seq)
    if melhor[0] >= 2:
        a, b = pontos[melhor[1]], pontos[melhor[1] + melhor[0] - 1]
        esc = ordinal(b["termino_independente"]) - ordinal(a["termino_independente"])
        frases.append(f"A construtora manteve o término em {a['termino_construtora']} por {melhor[0]} datas de "
                      f"status seguidas ({a['data_status']} a {b['data_status']}); no mesmo período a previsão "
                      f"independente andou {esc:+d} dias corridos.")
    p0, p1 = pontos[0], pontos[-1]
    frases.append(f"De {p0['data_status']} a {p1['data_status']}: independente {p0['termino_independente']} → "
                  f"{p1['termino_independente']} ({ordinal(p1['termino_independente']) - ordinal(p0['termino_independente']):+d} d); "
                  f"construtora {p0['termino_construtora']} → {p1['termino_construtora']} "
                  f"({ordinal(p1['termino_construtora']) - ordinal(p0['termino_construtora']):+d} d).")
    frases.append(f"Na última data de status a previsão independente está {p1['diferenca_dias_corridos']:+d} dias "
                  f"corridos em relação à da construtora; avanço real {p1['avanco_real_pct']}% contra "
                  f"{p1['avanco_previsto_lb_pct']}% previstos na linha de base.")
    return frases
