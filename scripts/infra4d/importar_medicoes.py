"""Importação de medições (boletins semanais e diários) por planilha CSV — ponte para a fase de dado real.

Só biblioteca padrão. NUNCA grava no dataset: o resultado é um relatório e, se aprovado, um projeto
em MEMÓRIA com os boletins novos somados aos existentes, para recalcular o cenário independente.

Formato do arquivo
------------------
- UTF-8 (com ou sem BOM). Outro encoding é recusado com mensagem clara ("salve como CSV UTF-8").
- Linhas iniciais ``#chave=valor`` são metadados (ex.: ``#ficticio=true``, ``#origem=...``). As linhas do
  arquivo são separadas só por ``\r\n``, ``\r`` ou ``\n`` (nunca por U+2028 e afins).
- Separador detectado no cabeçalho: ``;`` (padrão pt-BR), ``,`` ou TAB. Com ``;``/TAB o decimal é a
  vírgula e o ponto só é aceito como separador de milhar (``1.234,5``); com ``,`` o decimal é o ponto.
  Número ambíguo (``1.5`` num arquivo de vírgula decimal) é recusado.
- Colunas (nomes sem diferença de maiúsculas): ``atividade_id``; ``data`` (diário) OU ``semana_inicio``
  (boletim semanal); ``quantidade``; ``equipes_dias``; opcionais ``periodo_fim``, ``km_ini_exec``,
  ``km_fim_exec``, ``horas_chuva``, ``estado`` (padrão ``lancado``), ``ref_memoria_calculo``, ``origem``,
  ``observacao``. Coluna desconhecida gera aviso.

Regras de validação
-------------------
- Cada linha é validada por ``fiscalizacao.validar`` (as MESMAS regras do diário/boletim da API):
  frente existente e não marco, datas AAAA-MM-DD dentro do projeto e não no futuro, quantidade e
  equipes·dia numéricos e não negativos, produção sem equipe, chuva, km no trecho e no sentido, estado e
  ``aprovado`` com memória de cálculo. Boletim semanal: ``periodo_fim`` = semana_inicio + 6 dias, limitado
  à data de status.
- Regras próprias da importação: data na própria data de status é recusada (a data de status é o
  início do dia: ainda não houve execução nela); linha com ``data`` e ``semana_inicio`` ao mesmo tempo, ou
  com nenhuma, é recusada; chave (atividade, data/semana_inicio) repetida no arquivo ou já existente nos
  boletins da obra é recusada (evita somar duas vezes); sobreposição com a janela de um boletim existente
  gera AVISO.
- Segurança: até ``MAX_BYTES`` e ``MAX_LINHAS``; célula até ``MAX_CELULA`` caracteres; nenhuma fórmula é
  avaliada; célula numérica que começa com ``= + @`` (ou contém fórmula) é recusada como "texto, não
  número"; célula de texto que começa com ``= + - @`` é mantida como TEXTO literal e gera aviso.
- Dado fictício × real (ADR-0005, revisão r14): a marca é a linha ``#ficticio=true`` ou ``#ficticio=false``,
  EXATAMENTE assim (chave ``ficticio`` sem acento, ``=``, valor ``true``/``false`` minúsculo; só espaços em volta
  da linha), UMA vez. Qualquer outra grafia de linha que mencione a marca (``#fictício=``, ``#ficticio: true``,
  ``=True``, ``=sim``, ``="true"``, comentário depois do valor) ou marca repetida é ERRO do arquivo, nunca
  "falso". Obra com ``meta.ficticio is True`` só aceita ``#ficticio=true``; obra real EXIGE ``#ficticio=false``
  explícito (arquivo sem marca é recusado).
- CSV ESTRITO: aspas não fechadas, ou qualquer célula com quebra de linha (``\r``, ``\n``, U+2028, U+2029,
  U+0085), recusam o arquivo — uma linha nunca some dentro da célula de outra. O limite global
  ``csv.field_size_limit`` não é alterado (o tamanho da célula é conferido aqui, ``MAX_CELULA``).
- Números: só dígitos ASCII ``0-9``; dígitos de outros alfabetos (``١٢٣``, ``１２３``) são recusados. Num arquivo de
  vírgula decimal, ``1.234`` (ponto seguido de exatamente 3 dígitos, sem vírgula) é lido como MILHAR (1234) e
  gera AVISO na linha.
- Encoding: UTF-8 com no máximo UM BOM; BOM duplicado é recusado com mensagem clara.
- Aprovação: o arquivo é aprovado só se NENHUMA linha for rejeitada (tudo ou nada, como numa medição).
  Estado da linha não filtra: lançado, conferido e aprovado entram na simulação (contagem no relatório).

Efeito no projeto em memória
----------------------------
- Cada linha vira um boletim ``{atividade_id, semana_inicio, quantidade, equipes_dias, origem}``
  (diário: ``semana_inicio`` = data), que entra na produtividade medida.
- ``quantidade_executada`` da atividade soma as quantidades novas (limitada ao total, com aviso).
- Atividade não iniciada com produção passa a ``em_andamento`` com início real = 1ª data importada.
- Atividade concluída recebe o boletim (conta na produtividade do serviço), mas não muda de situação.
"""

from __future__ import annotations

import copy
import csv
import io
import re

from .calendario import iso, ordinal
from .cenarios import Projeto
from .fiscalizacao import obra_ficticia, validar

MAX_BYTES = 5 * 1024 * 1024
MAX_LINHAS = 50_000
MAX_CELULA = 1_000
OBRIGATORIAS = ("atividade_id", "quantidade", "equipes_dias")
OPCIONAIS = ("data", "semana_inicio", "periodo_fim", "km_ini_exec", "km_fim_exec", "horas_chuva", "estado",
             "ref_memoria_calculo", "origem", "observacao")
NUMERICAS = ("quantidade", "equipes_dias", "km_ini_exec", "km_fim_exec", "horas_chuva")
PREFIXOS_FORMULA = ("=", "+", "-", "@")
_RE_MILHAR_VIRGULA = re.compile(r"^-?[0-9]{1,3}(\.[0-9]{3})+(,[0-9]+)?$")
_RE_DEC_VIRGULA = re.compile(r"^-?[0-9]+(,[0-9]+)?$")
_RE_DEC_PONTO = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")
_RE_MILHAR_AMBIGUO = re.compile(r"^-?[0-9]{1,3}\.[0-9]{3}$")  # '1.234': milhar ou decimal de quem trocou o separador?
_RE_MARCA = re.compile(r"^#ficticio=(true|false)$")
_RE_CHAVE = re.compile(r"^[#\s\"']*([^=:]*)")


def _menciona_marca(linha: str) -> bool:
    """A CHAVE da linha de metadado (antes de '=' ou ':') é alguma grafia de 'ficticio'?"""
    import unicodedata
    chave = _RE_CHAVE.match(linha).group(1)
    chave = "".join(ch for ch in unicodedata.normalize("NFKD", chave) if not unicodedata.combining(ch))
    return re.sub(r"[\s\"'_-]", "", chave).lower() in ("ficticio", "ficticia", "fictício")
_QUEBRAS = {"\r": "\\r", "\n": "\\n", "\u2028": "U+2028", "\u2029": "U+2029", "\x85": "U+0085",
            "\x0b": "U+000B", "\x0c": "U+000C"}
_RE_LINHAS = re.compile(r"\r\n|\r|\n")


class ErroArquivo(ValueError):
    """Arquivo inteiro recusado (encoding, tamanho, cabeçalho, marca de fictício)."""


def _decodificar(dados: bytes | str) -> str:
    if isinstance(dados, str):
        texto = dados[1:] if dados.startswith("\ufeff") else dados
        if texto.startswith("\ufeff"):
            raise ErroArquivo(_MSG_BOM)
        return texto
    if len(dados) > MAX_BYTES:
        raise ErroArquivo(f"arquivo com {len(dados)} bytes; o limite é {MAX_BYTES}")
    try:
        texto = dados.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ErroArquivo(f"o arquivo não está em UTF-8 (byte inválido na posição {e.start}). No Excel, use "
                          "'Salvar como → CSV UTF-8 (delimitado por vírgulas)'") from None
    if texto.startswith("\ufeff"):
        raise ErroArquivo(_MSG_BOM)
    return texto


_MSG_BOM = ("marca de byte UTF-8 (BOM) DUPLICADA no início do arquivo: ele foi salvo/convertido duas vezes. "
            "Abra num editor de texto e salve de novo como 'CSV UTF-8'")


def _numero(txt: str, decimal: str) -> float | None | str:
    """float, None (vazio) ou str com o motivo da recusa."""
    t = txt.strip().replace(" ", "").replace(" ", "")
    if t == "":
        return None
    # operador em qualquer posição ('-1+3', '=2*3'), ou '-' que não seja o sinal inicial
    if not t.isascii():
        return (f"número com caractere não ASCII {txt!r}: use só os dígitos 0-9 (dígitos de outros alfabetos "
                "não são aceitos)")
    if t.startswith(("=", "+", "@")) or any(c in t for c in "=+@()*/^&") or "-" in t[1:]:
        return "célula com aparência de fórmula: tratada como TEXTO (não é avaliada) e recusada como número"
    if decimal == ",":
        if _RE_MILHAR_VIRGULA.match(t):
            t = t.replace(".", "").replace(",", ".")
        elif _RE_DEC_VIRGULA.match(t):
            t = t.replace(",", ".")
        else:
            return f"número inválido ou ambíguo {txt!r} (arquivo com vírgula decimal; ponto só como milhar)"
    elif not _RE_DEC_PONTO.match(t):
        return f"número inválido {txt!r} (arquivo com ponto decimal)"
    return float(t)


def ler_csv(dados: bytes | str) -> tuple[dict, list[str], list[tuple[int, dict]], str, str]:
    """→ (metadados #chave=valor, colunas, [(nº da linha no arquivo, {coluna: texto})], separador, decimal)."""
    texto = _decodificar(dados)
    if len(texto.encode("utf-8")) > MAX_BYTES:
        raise ErroArquivo(f"arquivo maior que {MAX_BYTES} bytes")
    linhas = _RE_LINHAS.split(texto)  # NUNCA splitlines(): ele quebra em U+2028, U+0085, \x0b...
    if linhas and linhas[-1] == "":
        linhas.pop()
    meta, i = {}, 0
    while i < len(linhas) and (not linhas[i].strip() or linhas[i].lstrip().startswith("#")):
        bruta = linhas[i].strip()
        if _menciona_marca(bruta):
            m = _RE_MARCA.match(bruta)
            if not m:
                raise ErroArquivo(f"marca de fictício inválida na linha {i + 1}: {bruta[:80]!r}. Use exatamente "
                                  "'#ficticio=true' ou '#ficticio=false' (chave sem acento, '=', valor true ou false "
                                  "minúsculo, sem comentário)")
            if "ficticio" in meta:
                raise ErroArquivo(f"marca '#ficticio' repetida (linha {i + 1}): declare uma única vez")
            meta["ficticio"] = m.group(1)
        else:
            ln = bruta.lstrip("#").strip()
            if "=" in ln:
                k, v = ln.split("=", 1)
                meta[k.strip().lower()] = v.strip()
        i += 1
    if i >= len(linhas):
        raise ErroArquivo("arquivo sem linha de cabeçalho")
    cab = linhas[i]
    sep = max((";", "\t", ","), key=lambda s: cab.count(s))
    if cab.count(sep) == 0:
        raise ErroArquivo("cabeçalho sem separador reconhecível (';', ',' ou TAB)")
    decimal = "." if sep == "," else ","
    corpo = "\n".join(linhas[i:]) + "\n"
    # strict: aspas não fechadas e lixo depois de aspas são erro. O limite global do csv NÃO é alterado.
    leitor = csv.reader(io.StringIO(corpo, newline="\n"), delimiter=sep, strict=True)
    try:
        colunas = [c.strip().lower() for c in next(leitor)]
    except csv.Error as e:
        raise ErroArquivo(f"cabeçalho ilegível: {e}") from None
    if len(set(colunas)) != len(colunas):
        raise ErroArquivo("cabeçalho com coluna repetida")
    faltam = [c for c in OBRIGATORIAS if c not in colunas]
    if faltam or not ({"data", "semana_inicio"} & set(colunas)):
        falta = faltam + ([] if {"data", "semana_inicio"} & set(colunas) else ["data ou semana_inicio"])
        raise ErroArquivo(f"coluna(s) obrigatória(s) ausente(s): {', '.join(falta)}")
    registros = []
    try:
        for n, row in enumerate(leitor, start=i + 2):
            for c in row:
                if len(c) > MAX_CELULA * 4:
                    raise ErroArquivo(f"célula com {len(c)} caracteres perto da linha {i + leitor.line_num}: muito "
                                      f"acima do limite de {MAX_CELULA} (arquivo recusado; até {MAX_CELULA * 4} a "
                                      "linha é só rejeitada)")
                q = next((nome for ch, nome in _QUEBRAS.items() if ch in c), None)
                if q:
                    raise ErroArquivo(f"célula com quebra de linha ({q}) perto da linha {i + leitor.line_num}: "
                                      "aspas não fechadas ou texto com Enter dentro da célula. Uma célula não pode "
                                      "ter quebra de linha")
            if not any(c.strip() for c in row):
                continue
            if len(registros) >= MAX_LINHAS:
                raise ErroArquivo(f"mais de {MAX_LINHAS} linhas de dados")
            registros.append((n, {colunas[k]: (row[k] if k < len(row) else "") for k in range(len(colunas))}
                              | ({"_excedente": row[len(colunas):]} if len(row) > len(colunas) else {})))
    except csv.Error as e:
        raise ErroArquivo(f"CSV malformado perto da linha {leitor.line_num + i}: {e}") from None
    return meta, colunas, registros, sep, decimal


def _bool(txt) -> bool:
    return str(txt).strip().lower() in ("true", "1", "sim", "s", "yes", "verdadeiro")


def importar(projeto: Projeto, dados: bytes | str, nome_arquivo: str = "planilha.csv") -> dict:
    """Valida o CSV e devolve o relatório. ``relatorio["_projeto"]`` traz o projeto em memória com as
    medições novas quando o arquivo é aprovado (chave privada: a rota não a devolve)."""
    meta_arq, colunas, regs, sep, decimal = ler_csv(dados)
    marca = meta_arq.get("ficticio")  # já validada: None, "true" ou "false"
    ficticio_arq = marca == "true"
    if obra_ficticia(projeto) and marca != "true":
        raise ErroArquivo("esta obra é FICTÍCIA (meta.ficticio = true): só aceita arquivo marcado com a linha "
                          "'#ficticio=true' (para não misturar dado real com sintético)")
    if not obra_ficticia(projeto) and marca != "false":
        raise ErroArquivo("arquivo marcado '#ficticio=true' não pode ser importado numa obra real" if marca == "true"
                          else "obra real: o arquivo precisa declarar explicitamente a linha '#ficticio=false' "
                               "(ADR-0005: sem a marca, não se sabe se o dado é real)")
    meta = projeto.dados["meta"]
    ds = ordinal(meta.get("data_status"))
    origem_arq = (meta_arq.get("origem") or f"importação CSV: {nome_arquivo}")[:MAX_CELULA]

    avisos_gerais = []
    desconhecidas = [c for c in colunas if c not in OBRIGATORIAS + OPCIONAIS]
    if desconhecidas:
        avisos_gerais.append(f"colunas ignoradas (desconhecidas): {', '.join(desconhecidas)}")
    if "estado" not in colunas:
        avisos_gerais.append("sem coluna 'estado': todas as linhas entram como 'lancado'")

    existentes = {(m["atividade_id"], m["semana_inicio"]) for m in projeto.dados.get("medicoes", [])}
    janelas: dict[str, list[tuple[int, int, str]]] = {}
    for m in projeto.dados.get("medicoes", []):
        s = ordinal(m["semana_inicio"])
        janelas.setdefault(m["atividade_id"], []).append((s, s + 7, m["semana_inicio"]))
    vistos: dict[tuple, int] = {}
    aceitas, rejeitadas, avisos, novas = [], [], [], []
    por_estado: dict[str, int] = {}

    for n, row in regs:
        erros, av = [], []

        def erro(campo, regra, msg):
            erros.append({"campo": campo, "regra": regra, "mensagem": msg})

        if "_excedente" in row:
            erro("", "formato", f"linha com {len(colunas) + len(row['_excedente'])} colunas; o cabeçalho tem "
                                f"{len(colunas)}")
        for c, v in row.items():
            if c == "_excedente":
                continue
            if len(v) > MAX_CELULA:
                erro(c, "tamanho", f"célula com {len(v)} caracteres; o limite é {MAX_CELULA}")
                row[c] = v[:MAX_CELULA]
            elif c not in NUMERICAS and v.strip().startswith(PREFIXOS_FORMULA):
                av.append(f"coluna {c}: célula começa com {v.strip()[0]!r}; tratada como TEXTO literal, "
                          "nenhuma fórmula é avaliada")
        reg = {"atividade_id": row.get("atividade_id", "").strip(), "origem": origem_arq,
               "estado": (row.get("estado") or "").strip() or "lancado",
               "ref_memoria_calculo": (row.get("ref_memoria_calculo") or "").strip() or None,
               "ocorrencias": [row["observacao"].strip()] if (row.get("observacao") or "").strip() else []}
        if (row.get("origem") or "").strip():
            reg["origem"] = row["origem"].strip()
        for c in NUMERICAS:
            if c not in row:
                continue
            v = _numero(row[c], decimal)
            if decimal == "," and _RE_MILHAR_AMBIGUO.match(row[c].strip()) and not isinstance(v, str):
                av.append(f"coluna {c}: {row[c].strip()!r} lido como {v:g} (ponto = separador de MILHAR neste "
                          f"arquivo de vírgula decimal); se era decimal, escreva com vírgula")
            if isinstance(v, str):
                erro(c, "numero", v)
            elif v is not None:
                reg[c] = v
            elif c in ("quantidade", "equipes_dias"):
                reg[c] = None  # validar acusa "obrigatório"
        data, semana = (row.get("data") or "").strip(), (row.get("semana_inicio") or "").strip()
        if data and semana:
            erro("data", "formato", "preencha 'data' (diário) OU 'semana_inicio' (boletim), não os dois")
        elif not data and not semana:
            erro("data", "data", "linha sem 'data' nem 'semana_inicio'")
        if semana and not data:
            reg["tipo"] = "boletim"
            reg["periodo_ini"] = semana
            pf = (row.get("periodo_fim") or "").strip()
            s_ord = ordinal(semana) if re.match(r"^\d{4}-\d{2}-\d{2}$", semana) and _data_ok(semana) else None
            if pf:
                reg["periodo_fim"] = pf
            elif s_ord is not None:
                fim = s_ord + 6 if ds is None else min(s_ord + 6, ds)
                reg["periodo_fim"] = iso(fim)
            else:
                reg["periodo_fim"] = semana
            chave_data = semana
        else:
            reg["tipo"] = "diario"
            reg["data"] = data
            chave_data = data
        if "horas_chuva" not in reg:
            reg["horas_chuva"] = 0

        v = validar(projeto, reg)
        ja = {(e["campo"], e["regra"]) for e in erros}
        erros += [e for e in v["erros"] if (e["campo"], e["regra"]) not in ja]  # sem repetir o mesmo defeito
        av += [a for a in v["avisos"] if not a.startswith("obra FICTÍCIA")]

        d_ord = ordinal(chave_data) if _data_ok(chave_data) else None
        if d_ord is not None and ds is not None and d_ord == ds:
            erro("data" if reg["tipo"] == "diario" else "semana_inicio", "na_data_status",
                 f"{chave_data} é a própria data de status (início do dia): ainda não houve execução")
        chave = (reg["atividade_id"], chave_data)
        if chave in existentes:
            erro("data" if reg["tipo"] == "diario" else "semana_inicio", "duplicado",
                 f"já existe boletim de {chave[0]} com início em {chave_data} na obra (somaria duas vezes)")
        elif chave in vistos:
            erro("data" if reg["tipo"] == "diario" else "semana_inicio", "duplicado",
                 f"mesma atividade e data já na linha {vistos[chave]} do arquivo")
        if d_ord is not None and chave not in existentes:
            for s, f, txt in janelas.get(reg["atividade_id"], []):
                if s <= d_ord < f:
                    av.append(f"cai na janela do boletim existente de {txt} ({reg['atividade_id']}): confira se não "
                              "é a mesma produção")
                    break
        if erros:
            rejeitadas.append({"linha": n, "atividade_id": reg["atividade_id"], "erros": erros})
        else:
            vistos[chave] = n
            aceitas.append(n)
            por_estado[reg["estado"]] = por_estado.get(reg["estado"], 0) + 1
            novas.append({"atividade_id": reg["atividade_id"], "semana_inicio": chave_data,
                          "quantidade": reg["quantidade"], "equipes_dias": reg["equipes_dias"],
                          "origem": reg["origem"], "estado": reg["estado"], "linha_csv": n,
                          "tipo": reg["tipo"]})
        for a in av:
            avisos.append({"linha": n, "mensagem": a})

    aprovado = bool(aceitas) and not rejeitadas
    relatorio = {
        "arquivo": nome_arquivo, "ficticio": ficticio_arq, "separador": sep, "decimal": decimal,
        "linhas": len(regs), "aceitas": len(aceitas), "rejeitadas": rejeitadas, "avisos": avisos,
        "avisos_gerais": avisos_gerais, "por_estado": por_estado, "aprovado": aprovado,
        "motivo": ("" if aprovado else ("arquivo sem linhas de dados" if not regs else
                                        "há linhas rejeitadas: a importação é tudo ou nada")),
        "medicoes_novas": novas,
        "regras": "ver docstring de infra4d.importar_medicoes (validação por fiscalizacao.validar + regras "
                  "próprias: data de status, duplicidade, fictício × real, tudo ou nada)",
    }
    if aprovado:
        relatorio["_projeto"], relatorio["efeitos"] = aplicar_em_memoria(projeto, novas)
    return relatorio


def _data_ok(txt: str) -> bool:
    try:
        return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", txt)) and ordinal(txt) is not None
    except ValueError:
        return False


def aplicar_em_memoria(projeto: Projeto, novas: list[dict]) -> tuple[Projeto, list[str]]:
    """Projeto NOVO (cópia) com os boletins somados; o original não é tocado."""
    dados = copy.deepcopy(projeto.dados)
    ativ = {a["id"]: a for a in dados["atividades"]}
    efeitos = []
    soma: dict[str, float] = {}
    primeira: dict[str, str] = {}
    for m in novas:
        dados.setdefault("medicoes", []).append({k: m[k] for k in ("atividade_id", "semana_inicio", "quantidade",
                                                                    "equipes_dias", "origem")})
        soma[m["atividade_id"]] = soma.get(m["atividade_id"], 0.0) + float(m["quantidade"] or 0)
        primeira[m["atividade_id"]] = min(primeira.get(m["atividade_id"], m["semana_inicio"]), m["semana_inicio"])
    for aid, q in soma.items():
        a = ativ[aid]
        if a.get("status") == "concluida":
            efeitos.append(f"{aid}: concluída; o boletim entra só na produtividade medida")
            continue
        if a.get("quantidade_total"):
            antes = float(a.get("quantidade_executada") or 0.0)
            novo = antes + q
            if novo > a["quantidade_total"]:
                efeitos.append(f"{aid}: executado {novo:g} passaria do total {a['quantidade_total']:g}; limitado ao "
                               "total (a atividade segue em andamento até ter término real)")
                novo = float(a["quantidade_total"])
            a["quantidade_executada"] = round(novo, 6)
            efeitos.append(f"{aid}: executado {antes:g} → {novo:g} {a.get('unidade', '')}".rstrip())
        if a.get("status", "nao_iniciada") == "nao_iniciada" and q > 0:
            a["status"], a["inicio_real"] = "em_andamento", primeira[aid]
            efeitos.append(f"{aid}: não iniciada → em andamento (início real {primeira[aid]})")
    return Projeto(dados), efeitos
