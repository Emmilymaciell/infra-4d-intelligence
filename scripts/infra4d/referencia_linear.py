"""Referência linear (km / estaca / coordenada) sobre o eixo de uma obra. Python puro.

Convenções (declaradas, para não haver ambiguidade):
- **Estaca** de 20 m: ``N+d`` com ``0 <= d < 20``, formatada ``"1234+15,00"``. Os 20 m são CONVENÇÃO
  (material didático; nenhuma norma DNIT encontrada que a fixe — R05 §6), não norma. A estaca 0 fica no
  km 0, a menos que ``meta.estaca_origem`` diga outro número. ``meta.equacoes_estaca`` =
  ``[{"km": X, "estaca": "99+10,00"}, ...]`` são equações de estacas (IFC 4.3 ``IncomingStation``);
  as regras de trecho, ambiguidade e salto estão em ``Estaqueamento``.
- **Eixo**: ``alinhamento.pontos`` = ``[km, x, y, cota]`` com km estritamente crescente. O km é a
  MEDIDA do eixo (como a coordenada M de uma linha medida), não o comprimento geométrico: entre dois
  pontos, km, x, y e cota são interpolados linearmente.
- **Rumo**: azimute em graus, 0 = norte (+y), crescendo no sentido horário, na direção do km crescente.
- **Afastamento**: distância perpendicular ao eixo, com sinal **positivo à DIREITA** (LD) e negativo à
  esquerda (LE) de quem anda no sentido do km crescente.
- **Fora do eixo**: km fora de [km_inicial, km_final] é ERRO (``ErroReferencia``). Um ponto (x, y) cuja
  projeção cai antes do início ou depois do fim é projetado no extremo e a resposta traz ``aviso``.
"""

from __future__ import annotations

import math
import re
from bisect import bisect_right
from dataclasses import dataclass

ESTACA_M = 20.0
# número da estaca com no máximo 9 dígitos (revisão r6: 400 dígitos davam OverflowError, 5.000 o limite do int)
NUMERO_MAXIMO = 999_999_999
_RE_ESTACA = re.compile(r"^\s*(-?\d{1,9})\s*\+\s*(\d{1,2}(?:[.,]\d{1,9})?)\s*$")


class ErroReferencia(ValueError):
    """Referência linear inválida ou fora do eixo."""


def _numero(v, nome: str) -> float:
    """float finito, ou ErroReferencia (nunca ValueError/OverflowError cru). Texto e bool são recusados."""
    if isinstance(v, (str, bool)) or v is None:
        raise ErroReferencia(f"{nome} deve ser número: {v!r}")
    try:
        f = float(v)
    except (TypeError, ValueError, OverflowError):
        raise ErroReferencia(f"{nome} inválido: {v!r}") from None
    if not math.isfinite(f):
        raise ErroReferencia(f"{nome} não finito: {v!r}")
    return f


# ------------------------------------------------------------------ estaca
@dataclass(frozen=True)
class Estaca:
    """Estaca ``numero + mais_m`` (``0 <= mais_m < 20``). ``trecho`` = zona do estaqueamento
    (0 antes da 1ª equação, i depois da i-ésima); só importa quando há equação de estacas.

    ``mais_m`` NÃO é arredondado no objeto (a ida e volta é identidade); só o texto arredonda ao cm.
    """

    numero: int
    mais_m: float
    trecho: int | None = None

    def __post_init__(self):
        if not isinstance(self.numero, int) or isinstance(self.numero, bool):
            raise ErroReferencia(f"número de estaca deve ser inteiro: {self.numero!r}")
        if abs(self.numero) > NUMERO_MAXIMO:
            raise ErroReferencia(f"estaca inválida: número fora de ±{NUMERO_MAXIMO}")
        if not (math.isfinite(self.mais_m) and 0 <= self.mais_m < ESTACA_M):
            raise ErroReferencia(f"estaca inválida: '{self.numero}+{self.mais_m}' (a fração deve estar em [0, 20) m)")

    @property
    def metros(self) -> float:
        """Valor do estaqueamento em metros (o "station" do IFC), não a medida no eixo."""
        return self.numero * ESTACA_M + self.mais_m

    @classmethod
    def de_metros(cls, metros: float, trecho: int | None = None) -> "Estaca":
        if not math.isfinite(metros):
            raise ErroReferencia(f"estaqueamento não finito: {metros!r}")
        if abs(metros) > (NUMERO_MAXIMO + 1) * ESTACA_M:
            raise ErroReferencia(f"estaqueamento fora do limite: {metros!r} m")
        n = math.floor(metros / ESTACA_M)
        mais = metros - n * ESTACA_M
        if mais >= ESTACA_M:   # erro de ponto flutuante na divisão
            n, mais = n + 1, mais - ESTACA_M
        if mais < 0:
            n, mais = n - 1, mais + ESTACA_M
        return cls(int(n), max(0.0, mais), trecho)

    @classmethod
    def de_texto(cls, texto: str, trecho: int | None = None) -> "Estaca":
        m = _RE_ESTACA.match(str(texto))
        if not m:
            raise ErroReferencia(f"estaca inválida: {texto!r} (formato esperado: '1234+15,00')")
        d = float(m.group(2).replace(",", "."))
        if not 0 <= d < ESTACA_M:
            raise ErroReferencia(f"estaca inválida: {texto!r} (a fração deve estar em [0, 20) m)")
        return cls(int(m.group(1)), d, trecho)

    def texto(self) -> str:
        n, d = self.numero, round(self.mais_m, 2)
        if d >= ESTACA_M:  # 19,996 m arredonda para 20,00: fecha a estaca (nunca "N+20,00")
            n, d = n + 1, 0.0
        return f"{n}+{d:05.2f}".replace(".", ",")

    def __str__(self) -> str:
        return self.texto()


class Estaqueamento:
    """Conversão medida no eixo (km) <-> estaca, com EQUAÇÕES DE ESTACAS.

    Uma equação ``(km, estaca)`` diz: a partir deste km, o estaqueamento passa a valer ``estaca``
    (é o ``Pset_Stationing.IncomingStation`` do IFC 4.3). Entre equações a estaca cresce 1 m por m.

    Regras declaradas:
    - o ponto exato da equação pertence ao trecho NOVO (vale a estaca "à frente"/incoming);
    - o trecho i cobre a medida [km da equação i, km da equação i+1); o trecho 0 vale também antes do km 0;
    - equação que RECUA a estaca cria valores repetidos: estaca -> km sem ``trecho`` é ERRO de
      ambiguidade (a mensagem lista os candidatos); com ``trecho`` explícito resolve. Com ``trecho``
      explícito, a estaca "atrás" no ponto exato da equação também é aceita (limite fechado);
    - equação que AVANÇA a estaca cria um salto: estaca dentro do salto é ERRO (não existe no terreno).
    """

    def __init__(self, estaca_origem: int = 0, equacoes: list | None = None):
        try:
            self.estaca_origem = int(estaca_origem)
        except (TypeError, ValueError, OverflowError):
            raise ErroReferencia(f"estaca_origem inválida: {estaca_origem!r}") from None
        if abs(self.estaca_origem) > NUMERO_MAXIMO:
            raise ErroReferencia(f"estaca_origem fora de ±{NUMERO_MAXIMO}")
        # trecho 0: estaca = origem + medida; trecho i: estaca = s_i + (medida − m_i)
        zonas = [(-math.inf, self.estaca_origem * ESTACA_M)]
        for eq in equacoes or []:
            if isinstance(eq, dict):
                km, est = eq.get("km"), eq.get("estaca", eq.get("estaca_m"))
            elif isinstance(eq, (list, tuple)) and len(eq) == 2:
                km, est = eq
            else:
                raise ErroReferencia(f"equação de estacas deve ser {{km, estaca}} ou (km, estaca): {eq!r}")
            if km is None or est is None:
                raise ErroReferencia(f"equação de estacas incompleta: {eq!r}")
            try:
                km = _numero(km, "km da equação de estacas")
                s = est.metros if isinstance(est, Estaca) else (
                    Estaca.de_texto(est).metros if isinstance(est, str) else _numero(est, "estaca da equação"))
            except ErroReferencia:
                raise
            except (TypeError, ValueError, OverflowError):
                raise ErroReferencia(f"equação de estacas inválida: {eq!r}") from None
            if not (math.isfinite(km) and math.isfinite(s)):
                raise ErroReferencia(f"equação de estacas não finita: {eq!r}")
            if km * 1000.0 <= zonas[-1][0]:
                raise ErroReferencia("equações de estacas devem ter km estritamente crescente")
            zonas.append((km * 1000.0, s))
        self.zonas = zonas
        self._inicios = [z[0] for z in zonas]

    @property
    def tem_equacoes(self) -> bool:
        return len(self.zonas) > 1

    def _fim(self, i: int) -> float:
        return self.zonas[i + 1][0] if i + 1 < len(self.zonas) else math.inf

    def _medida(self, i: int, s: float) -> float:
        m0, s0 = self.zonas[i]
        return (s - s0) if i == 0 else m0 + (s - s0)

    def km_para_estaca(self, km: float) -> Estaca:
        m = _numero(km, "km") * 1000.0
        if not math.isfinite(m):
            raise ErroReferencia(f"km não finito: {km!r}")
        i = bisect_right(self._inicios, m) - 1
        m0, s0 = self.zonas[i]
        return Estaca.de_metros(s0 + m if i == 0 else s0 + (m - m0), trecho=i)

    def candidatos(self, estaca: Estaca) -> list[tuple[int, float]]:
        """[(trecho, km)] de todos os trechos em que a estaca existe (limite superior aberto)."""
        out = []
        for i in range(len(self.zonas)):
            m = self._medida(i, estaca.metros)
            if m >= self.zonas[i][0] - 1e-9 and m < self._fim(i) - 1e-9:
                out.append((i, m / 1000.0))
        return out

    def estaca_para_km(self, estaca: "Estaca | str", trecho: int | None = None) -> float:
        e = Estaca.de_texto(estaca) if isinstance(estaca, str) else estaca
        trecho = e.trecho if trecho is None else trecho
        if trecho is not None:
            if not 0 <= trecho < len(self.zonas):
                raise ErroReferencia(f"trecho de estaqueamento inexistente: {trecho} (há {len(self.zonas)})")
            m = self._medida(trecho, e.metros)
            if m < self.zonas[trecho][0] - 1e-9 or m > self._fim(trecho) + 1e-9:
                raise ErroReferencia(f"estaca {e} não existe no trecho {trecho} do estaqueamento")
            return m / 1000.0
        cand = self.candidatos(e)
        if not cand:
            raise ErroReferencia(f"estaca {e} não existe: cai no salto de uma equação de estacas")
        if len(cand) > 1:
            op = "; ".join(f"trecho {i} → km {k:.6f}" for i, k in cand)
            raise ErroReferencia(f"estaca {e} é ambígua (a equação de estacas recua o estaqueamento): {op}. "
                                 f"Informe o trecho.")
        return cand[0][1]


def km_para_estaca(km: float, estaca_origem: int = 0) -> str:
    """Atalho sem equação de estacas: km -> texto ``"N+dd,dd"``."""
    return Estaqueamento(estaca_origem).km_para_estaca(km).texto()


def estaca_para_km(estaca: str, estaca_origem: int = 0) -> float:
    """Atalho sem equação de estacas: texto -> km."""
    return Estaqueamento(estaca_origem).estaca_para_km(Estaca.de_texto(estaca))


# ------------------------------------------------------------------ eixo
class Eixo:
    def __init__(self, pontos: list, estaca_origem: int = 0, equacoes: list | None = None):
        if not pontos or len(pontos) < 2:
            raise ErroReferencia("alinhamento precisa de pelo menos 2 pontos [km, x, y, cota]")
        pts = []
        for p in pontos:
            if not isinstance(p, (list, tuple)) or len(p) < 3:
                raise ErroReferencia(f"ponto de alinhamento incompleto: {p!r}")
            # todos os campos numéricos e finitos (revisão r6: NaN/inf em x/y eram aceitos)
            pts.append(tuple(_numero(v, f"campo {j} do ponto de alinhamento") for j, v in
                             enumerate(list(p[:4]) + [0.0] * (4 - len(p[:4])))))
        for a, b in zip(pts, pts[1:]):
            if not b[0] > a[0]:
                raise ErroReferencia(f"km do alinhamento não é estritamente crescente ({a[0]} → {b[0]})")
            if a[1] == b[1] and a[2] == b[2]:
                raise ErroReferencia(f"pontos repetidos no alinhamento entre km {a[0]} e {b[0]}")
        self.pontos = pts
        self.kms = [p[0] for p in pts]
        self.estaqueamento = Estaqueamento(estaca_origem, equacoes)

    @classmethod
    def da_obra(cls, dados: dict) -> "Eixo":
        alin = dados.get("alinhamento") or {}
        meta = dados.get("meta", {})
        return cls(alin.get("pontos") or [], meta.get("estaca_origem", 0), meta.get("equacoes_estaca"))

    @property
    def km_inicial(self) -> float:
        return self.kms[0]

    @property
    def km_final(self) -> float:
        return self.kms[-1]

    def estaca(self, km: float) -> str:
        return self.estaqueamento.km_para_estaca(km).texto()

    def km_da_estaca(self, estaca: "str | Estaca", trecho: int | None = None) -> float:
        return self.estaqueamento.estaca_para_km(estaca, trecho)

    def _info_estaca(self, km: float) -> dict:
        e = self.estaqueamento.km_para_estaca(km)
        info = {"estaca": e.texto()}
        if self.estaqueamento.tem_equacoes:
            info["estaca_trecho"] = e.trecho
        return info

    def _trecho(self, km: float) -> int:
        """Índice i do trecho [i, i+1] que contém km (o último trecho contém o km final)."""
        return min(max(bisect_right(self.kms, km) - 1, 0), len(self.kms) - 2)

    def ponto_em(self, km: float) -> dict:
        try:
            km = float(km)
        except (TypeError, ValueError, OverflowError):
            raise ErroReferencia(f"km inválido: {km!r}") from None
        if not math.isfinite(km) or km < self.km_inicial - 1e-9 or km > self.km_final + 1e-9:
            raise ErroReferencia(f"km {km} fora do eixo [{self.km_inicial}, {self.km_final}]")
        i = self._trecho(km)
        (k0, x0, y0, z0), (k1, x1, y1, z1) = self.pontos[i], self.pontos[i + 1]
        t = (km - k0) / (k1 - k0)
        return {"km": km, **self._info_estaca(km),
                "x": x0 + t * (x1 - x0), "y": y0 + t * (y1 - y0), "cota": z0 + t * (z1 - z0),
                "rumo_graus": _azimute(x1 - x0, y1 - y0)}

    def localizar(self, x: float, y: float) -> dict:
        """(x, y) -> km, estaca e afastamento (projeção ortogonal no trecho mais próximo)."""
        try:
            x, y = float(x), float(y)
        except (TypeError, ValueError, OverflowError):
            raise ErroReferencia(f"coordenada inválida: {x!r}, {y!r}") from None
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ErroReferencia("coordenada não finita")
        melhor = None
        n = len(self.pontos)
        for i in range(n - 1):
            (k0, x0, y0, _), (k1, x1, y1, _) = self.pontos[i], self.pontos[i + 1]
            dx, dy = x1 - x0, y1 - y0
            t_bruto = ((x - x0) * dx + (y - y0) * dy) / (dx * dx + dy * dy)
            t = min(1.0, max(0.0, t_bruto))
            px, py = x0 + t * dx, y0 + t * dy
            dist = math.hypot(x - px, y - py)
            if melhor is None or dist < melhor[0] - 1e-9:
                melhor = (dist, i, t, t_bruto, px, py)
        dist, i, t, t_bruto, px, py = melhor
        (k0, x0, y0, _), (k1, x1, y1, _) = self.pontos[i], self.pontos[i + 1]
        dx, dy = x1 - x0, y1 - y0
        cruz = dx * (y - y0) - dy * (x - x0)  # > 0: à esquerda do sentido do km
        km = k0 + t * (k1 - k0)
        aviso = None
        if i == 0 and t_bruto < 0:
            aviso = f"ponto antes do início do eixo: projetado no km {self.km_inicial}"
        elif i == n - 2 and t_bruto > 1:
            aviso = f"ponto depois do fim do eixo: projetado no km {self.km_final}"
        if aviso:
            # fora das pontas, a "perpendicular" não existe: afastamento = distância até a ponta,
            # com o lado dado pelo prolongamento do trecho extremo
            lado_sinal = -1.0 if cruz > 0 else 1.0
            afast = lado_sinal * dist if abs(cruz) > 1e-9 else 0.0
        elif dist < 1e-9:
            afast = 0.0
        else:
            v = i + 1 if t >= 1.0 else (i if t <= 0.0 else None)   # projeção caiu num vértice interno?
            deflexao = 0.0
            if v is not None and 0 < v < n - 1:
                (_, ax, ay, _), (_, bx, by, _), (_, cx, cy, _) = self.pontos[v - 1], self.pontos[v], self.pontos[v + 1]
                deflexao = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)   # > 0: curva à esquerda
            if abs(deflexao) > 1e-12:
                # só o lado de FORA da curva projeta no vértice: curva à esquerda => direito (revisão r6:
                # com deflexão > 90°, o prolongamento do trecho anterior dava o lado errado)
                afast = dist if deflexao > 0 else -dist
            else:
                afast = -dist if cruz > 0 else dist
        return {"km": km, **self._info_estaca(km), "afastamento_m": afast,
                "lado": "eixo" if abs(afast) < 1e-6 else ("direito" if afast > 0 else "esquerdo"),
                "distancia_m": dist, "x_eixo": px, "y_eixo": py, "aviso": aviso}


def _azimute(dx: float, dy: float) -> float:
    return math.degrees(math.atan2(dx, dy)) % 360.0


# ------------------------------------------------------------------ km -> obra
def _cobre(ini, fim, km: float, km_max: float) -> bool:
    if ini is None or fim is None:
        return False
    ini, fim = min(ini, fim), max(ini, fim)   # trecho executado em sentido decrescente (revisão r6)
    return ini <= km < fim or (km == fim and abs(fim - km_max) < 1e-9)


def cobertura(dados: dict, km: float) -> dict:
    """Lote, segmento e atividades cujo intervalo [km_ini, km_fim) contém ``km``
    (o km final da obra pertence ao último trecho)."""
    km_max = max([max(s["km_ini"], s["km_fim"]) for s in dados.get("segmentos", [])]
                 + [max(l["km_ini"], l["km_fim"]) for l in dados.get("lotes", [])] or [km])
    lote = next((l for l in dados.get("lotes", []) if _cobre(l["km_ini"], l["km_fim"], km, km_max)), None)
    seg = next((s for s in dados.get("segmentos", []) if _cobre(s["km_ini"], s["km_fim"], km, km_max)), None)
    ativs = [a for a in dados.get("atividades", []) if _cobre(a.get("km_ini"), a.get("km_fim"), km, km_max)]
    return {"lote": lote, "segmento": seg, "atividades": ativs}
