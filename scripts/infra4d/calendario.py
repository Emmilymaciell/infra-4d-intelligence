"""Calendários de trabalho e aritmética em tempo de trabalho.

Convenção de FRONTEIRAS (usada em todo o motor):

- Datas são ordinais inteiros (``date.toordinal()``).
- Um valor ``d`` representa o INÍCIO do dia ``d``.
- Uma atividade com início ``ES`` e término ``EF`` ocupa os dias úteis no
  intervalo semiaberto ``[ES, EF)``. Logo ``EF`` é o início do dia seguinte
  ao último dia trabalhado. A data de término exibida é ``ultimo_dia_util(EF)``.

Com essa convenção:

- ``somar(d, n)``  avança ``n`` dias úteis a partir da fronteira ``d``;
- ``subtrair(d, n)`` recua ``n`` dias úteis a partir da fronteira ``d``;
- ``dias_uteis_entre(a, b)`` conta os dias úteis em ``[a, b)``.

Em calendário único, ``somar`` e ``subtrair`` são inversas entre si. Com
calendários DIFERENTES entre predecessora e sucessora isso não basta (achado da
revisão adversarial): a passada para trás usa ``inicio_mais_tardio`` e
``fim_mais_tardio``, que são as inversas exatas da regra da passada para frente
mesmo quando a data da sucessora cai em dia não útil da predecessora.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import date, timedelta

HORIZONTE_INICIO = date(2020, 1, 1)
HORIZONTE_FIM = date(2040, 12, 31)


class ErroCalendario(ValueError):
    """Calendário inválido ou data fora do horizonte."""


@dataclass
class Calendario:
    """Calendário de dias úteis.

    dias_semana: dias trabalhados, 0=segunda ... 6=domingo.
    nao_uteis: datas específicas sem trabalho (feriados, chuva, paralisações).
    """

    id: str
    nome: str
    dias_semana: tuple[int, ...] = (0, 1, 2, 3, 4)
    nao_uteis: frozenset[date] = field(default_factory=frozenset)
    _uteis: list[int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.dias_semana:
            raise ErroCalendario(f"calendário {self.id}: nenhum dia da semana útil")
        if any(d < 0 or d > 6 for d in self.dias_semana):
            raise ErroCalendario(f"calendário {self.id}: dia da semana fora de 0..6")
        self.nao_uteis = frozenset(self.nao_uteis)
        uteis = []
        d = HORIZONTE_INICIO
        um = timedelta(days=1)
        semana = set(self.dias_semana)
        while d <= HORIZONTE_FIM:
            if d.weekday() in semana and d not in self.nao_uteis:
                uteis.append(d.toordinal())
            d += um
        self._uteis = uteis

    # ------------------------------------------------------------------ básicos
    def _indice(self, d: int) -> int:
        """Quantidade de dias úteis estritamente antes de ``d``.

        Fora do horizonte é ERRO, nunca deslocamento silencioso (achado da
        revisão adversarial: havia tolerância de 366 dias antes de 2020)."""
        if d < HORIZONTE_INICIO.toordinal() or d > HORIZONTE_FIM.toordinal() + 1:
            raise ErroCalendario(
                f"data {date.fromordinal(d)} fora do horizonte do calendário "
                f"({HORIZONTE_INICIO} a {HORIZONTE_FIM})"
            )
        return bisect_left(self._uteis, d)

    def eh_util(self, d: int) -> bool:
        i = bisect_left(self._uteis, d)
        return i < len(self._uteis) and self._uteis[i] == d

    def proximo_util(self, d: int) -> int:
        """Primeiro dia útil >= d (fronteira de início de trabalho)."""
        i = self._indice(d)
        if i >= len(self._uteis):
            raise ErroCalendario("sem dia útil depois de " + str(date.fromordinal(d)))
        return self._uteis[i]

    def fim_ajustado(self, d: int) -> int:
        """Fronteira de término ajustada: (último dia útil < d) + 1."""
        i = self._indice(d)
        if i == 0:
            raise ErroCalendario("sem dia útil antes de " + str(date.fromordinal(d)))
        return self._uteis[i - 1] + 1

    def ultimo_dia_util(self, fronteira_fim: int) -> int:
        """Data exibível de término: o último dia útil antes da fronteira."""
        return self.fim_ajustado(fronteira_fim) - 1

    # ---------------------------------------------------------- aritmética
    def somar(self, d: int, n: int) -> int:
        """Avança ``n`` dias úteis a partir da fronteira ``d``.

        n == 0 devolve ``d`` inalterado. n < 0 equivale a ``subtrair(d, -n)``.
        """
        if n == 0:
            return d
        if n < 0:
            return self.subtrair(d, -n)
        i = self._indice(d)
        j = i + n - 1
        if j >= len(self._uteis):
            raise ErroCalendario("soma ultrapassa o horizonte do calendário")
        return self._uteis[j] + 1

    def subtrair(self, d: int, n: int) -> int:
        """Recua ``n`` dias úteis a partir da fronteira ``d``.

        Devolve o início do n-ésimo dia útil anterior a ``d``.
        """
        if n == 0:
            return d
        if n < 0:
            return self.somar(d, -n)
        i = self._indice(d)
        j = i - n
        if j < 0:
            raise ErroCalendario("subtração ultrapassa o horizonte do calendário")
        return self._uteis[j]

    # ------------------------------------------- limites tardios (passada p/ trás)
    def inicio_mais_tardio(self, t: int, lag: int) -> int:
        """Maior dia útil ``s`` (início) tal que ``somar(s, lag) <= t``.

        Inversa exata da regra da passada para frente para relações que partem
        do INÍCIO da predecessora (SS, SF), qualquer que seja o sinal do lag e
        ainda que ``t`` caia em dia não útil deste calendário.
        """
        if lag > 0:
            return self.subtrair(t, lag)
        k = self._indice(t + 1) - 1 - lag  # lag <= 0
        if k < 0 or k >= len(self._uteis):
            raise ErroCalendario("limite tardio fora do horizonte do calendário")
        return self._uteis[k]

    def fim_mais_tardio(self, t: int, lag: int) -> int:
        """Maior fronteira de término ``e`` (= dia útil + 1) tal que ``somar(e, lag) <= t``.

        Inversa exata para relações que partem do TÉRMINO da predecessora (FS, FF).
        """
        if lag >= 0:
            j = self._indice(t) - 1 - lag
        else:
            j = self._indice(t + 1) - 2 - lag
        if j < 0 or j >= len(self._uteis):
            raise ErroCalendario("limite tardio fora do horizonte do calendário")
        return self._uteis[j] + 1

    def dias_uteis_entre(self, a: int, b: int) -> int:
        """Dias úteis em [a, b). Negativo se b < a."""
        if b < a:
            return -self.dias_uteis_entre(b, a)
        return self._indice(b) - self._indice(a)

    # ------------------------------------------------------------ serialização
    @classmethod
    def de_dict(cls, dados: dict) -> "Calendario":
        return cls(
            id=dados["id"],
            nome=dados.get("nome", dados["id"]),
            dias_semana=tuple(dados.get("dias_semana", (0, 1, 2, 3, 4))),
            nao_uteis=frozenset(date.fromisoformat(x) for x in dados.get("nao_uteis", [])),
        )


def iso(d: int | None) -> str | None:
    return None if d is None else date.fromordinal(d).isoformat()


def ordinal(texto: str | None) -> int | None:
    return None if not texto else date.fromisoformat(texto).toordinal()
