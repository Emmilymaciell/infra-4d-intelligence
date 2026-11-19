"""Peças comuns aos adaptadores de cronograma (MSPDI e XER).

Os adaptadores só TRADUZEM formato. Quem calcula datas é sempre o motor
próprio (``motor.calcular``), conforme o ADR-0003.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime

from ..calendario import HORIZONTE_FIM, HORIZONTE_INICIO


class ErroImportacao(ValueError):
    """Arquivo de cronograma ilegível ou fora do subconjunto suportado."""


@dataclass
class Avisos:
    """Coleta avisos sem repetir a mesma mensagem mil vezes."""

    itens: list[str] = field(default_factory=list)
    _contagem: dict[str, int] = field(default_factory=dict)
    maximo_por_tipo: int = 5

    def add(self, tipo: str, texto: str) -> None:
        n = self._contagem.get(tipo, 0) + 1
        self._contagem[tipo] = n
        if n <= self.maximo_por_tipo:
            self.itens.append(texto)
        elif n == self.maximo_por_tipo + 1:
            self.itens.append(f"[{tipo}] mais ocorrências omitidas")

    def lista(self) -> list[str]:
        return list(self.itens)


# Teto de dias úteis numa duração/lag: o horizonte dos calendários (2020–2040) tem ~6.600 dias
# úteis num calendário de 6 dias; valor maior só pode ser erro ou entrada hostil.
MAXIMO_DIAS = 10_000
# Tetos de volume (rodada 5: 2.000 calendários próprios levavam 3,4 s só para montar)
MAXIMO_ATIVIDADES = 20_000
MAXIMO_CALENDARIOS = 200  # calendários efetivamente USADOS por atividades
MAXIMO_CALENDARIOS_ARQUIVO = 1_000  # declarados no arquivo (inclui calendários de recurso)
MAXIMO_NIVEIS = 50  # herança de calendário (MSPDI) e aninhamento do clndr_data (XER)


def numero_finito(v: float, contexto: str) -> float:
    if not math.isfinite(v):
        raise ErroImportacao(f"{contexto}: número não finito ({v})")
    return v


def _dias_finitos(horas: float, horas_por_dia: float, contexto: str) -> float:
    numero_finito(horas, contexto)
    numero_finito(horas_por_dia, contexto)
    if horas_por_dia <= 0:
        raise ErroImportacao(f"{contexto}: horas por dia inválidas ({horas_por_dia})")
    dias = horas / horas_por_dia
    if not math.isfinite(dias) or abs(dias) > MAXIMO_DIAS:
        raise ErroImportacao(f"{contexto}: {horas:g} h = {dias:g} dia(s), fora do limite de "
                             f"{MAXIMO_DIAS} dias úteis")
    return dias


def recortar_ao_horizonte(de: date, ate: date) -> tuple[date, date] | None:
    """Recorta [de, ate] ao horizonte dos calendários ANTES de iterar dia a dia (rodada 5:
    exceção 0001..9998 iterava 3,6 milhões de dias). None se não houver interseção."""
    de, ate = max(de, HORIZONTE_INICIO), min(ate, HORIZONTE_FIM)
    return (de, ate) if de <= ate else None


def dias_de_horas(horas: float, horas_por_dia: float, avisos: Avisos, contexto: str) -> int:
    """Converte horas em dias úteis inteiros (o motor trabalha em dias).

    Fração de dia é arredondada para CIMA (duração) com aviso: o motor não
    agenda meio dia."""
    dias = _dias_finitos(horas, horas_por_dia, contexto)
    inteiro = round(dias)
    if abs(dias - inteiro) < 1e-6:
        return int(inteiro)
    arred = math.ceil(dias - 1e-9) if dias > 0 else -math.ceil(-dias - 1e-9)
    avisos.add("fracao", f"{contexto}: {horas:g} h = {dias:.3f} dia(s); arredondado para {arred} "
                         f"(o motor trabalha em dias inteiros)")
    return int(arred)


def lag_de_horas(horas: float, horas_por_dia: float, avisos: Avisos, contexto: str) -> int:
    """Lag em horas → dias inteiros, arredondado ao mais próximo, com aviso."""
    dias = _dias_finitos(horas, horas_por_dia, contexto)
    inteiro = round(dias)
    if abs(dias - inteiro) > 1e-6:
        avisos.add("lag_fracao", f"{contexto}: lag de {horas:g} h = {dias:.3f} dia(s); "
                                 f"arredondado para {int(inteiro)}")
    return int(inteiro)


def data_de_texto(texto: str | None) -> date | None:
    """Aceita 'AAAA-MM-DD', 'AAAA-MM-DDTHH:MM:SS' e 'AAAA-MM-DD HH:MM'."""
    if texto is None:
        return None
    t = texto.strip()
    if not t:
        return None
    try:
        if len(t) == 10:
            return date.fromisoformat(t)
        return datetime.fromisoformat(t.replace(" ", "T")).date()
    except ValueError as e:
        raise ErroImportacao(f"data ilegível: {texto!r}") from e


def datahora_de_texto(texto: str | None) -> datetime | None:
    if texto is None or not texto.strip():
        return None
    try:
        return datetime.fromisoformat(texto.strip().replace(" ", "T"))
    except ValueError as e:
        raise ErroImportacao(f"data/hora ilegível: {texto!r}") from e


def no_horizonte(d: date) -> bool:
    return HORIZONTE_INICIO <= d <= HORIZONTE_FIM


LIMITACOES_COMUNS = [
    "Compatibilidade com MS Project / Primavera P6 reais NÃO é alegada: validado por ida e volta com o "
    "próprio exportador e por fixtures sintéticas escritas à mão conforme a especificação pública.",
    "Datas são recalculadas pelo motor CPM próprio (ADR-0003); datas gravadas no arquivo (Start/Finish, "
    "early_start_date...) não são usadas no cálculo.",
    "Granularidade em dias inteiros: horas fracionárias de duração/lag são arredondadas (com aviso); "
    "horário de trabalho dentro do dia é ignorado.",
    "Lag contado no calendário da PREDECESSORA (padrão do P6, regra do motor). O MS Project pode contar "
    "de outra forma: divergência possível, não verificada.",
    "Sem recursos, custos, WBS/estrutura de resumo, restrições além de SNET, lag em porcentagem ou "
    "dias corridos, nem exceções de calendário que tornam dia útil (o Calendario só retira dias).",
]
