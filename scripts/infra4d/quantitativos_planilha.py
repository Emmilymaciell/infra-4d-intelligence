"""XLSX de quantitativos fictícios com fórmulas editáveis, sem dependência adicional.

Fallback OOXML: artifact-tool não está disponível neste host. Não calcula CPM na
planilha. Saldo e avanço são fórmulas; totais de unidades distintas não se somam.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from .cenarios import Projeto

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'


def _texto(ref, valor, estilo=0):
    return f'<c r="{ref}" t="inlineStr" s="{estilo}"><is><t>{escape(str(valor))}</t></is></c>'


def _numero(ref, valor, estilo=1):
    return f'<c r="{ref}" s="{estilo}"><v>{float(valor):.15g}</v></c>'


def _formula(ref, formula, cache, estilo=1):
    return f'<c r="{ref}" s="{estilo}"><f>{escape(formula)}</f><v>{float(cache):.15g}</v></c>'


def gerar_xlsx(projeto: Projeto, destino: Path):
    """Gera um arquivo novo; recusa sobrescrever uma revisão ou dado não fictício."""
    if projeto.dados.get('meta', {}).get('ficticio') is not True:
        raise ValueError('planilha da demo aceita somente dados fictícios')
    destino = Path(destino)
    if destino.exists():
        raise FileExistsError(destino)
    atividades = [a for a in projeto.dados['atividades'] if a.get('quantidade_total', 0) > 0]
    if not atividades:
        raise ValueError('sem atividades com quantidade')
    linhas = []
    def linha(n, celulas, altura=22):
        linhas.append(f'<row r="{n}" ht="{altura}" customHeight="1">' + ''.join(celulas) + '</row>')
    linha(2, [_texto('A2', 'Quantitativos da ferrovia fictícia', 4)])
    linha(3, [_texto('A3', '100% FICTÍCIO. Quantidade de planejamento; não é volume da malha nem medição contratual.')])
    linha(4, [_texto('A4', 'Fonte: examples/synthetic/ferrovia_ficticia.json. Data de status: ' + projeto.dados['meta']['data_status'])])
    linha(5, [_texto('A5', 'Amarelo: total editável. Executado: fonte preservada. Saldo e avanço recalculam; prazo é calculado no INFRA 4D.')])
    cab = ['Atividade', 'Lote', 'Serviço', 'Unidade', 'Total', 'Executado', 'Saldo', 'Avanço']
    linha(7, [_texto(f'{chr(65+i)}7', t, 3) for i, t in enumerate(cab)])
    for n, a in enumerate(atividades, 8):
        qtd, exe = a['quantidade_total'], a.get('quantidade_executada', 0)
        linha(n, [_texto(f'A{n}', a['id']), _texto(f'B{n}', a.get('lote_id', '')),
                  _texto(f'C{n}', a.get('servico_id', '')), _texto(f'D{n}', a['unidade']),
                  _numero(f'E{n}', qtd, 5), _numero(f'F{n}', exe),
                  _formula(f'G{n}', f'E{n}-F{n}', qtd-exe),
                  _formula(f'H{n}', f'IF(E{n}=0,0,F{n}/E{n})', exe/qtd, 2)])
    fim = len(atividades) + 7
    unidades = sorted({a['unidade'] for a in atividades})
    resumo = []
    for i, unidade in enumerate(unidades, 8):
        subtotal = [a for a in atividades if a['unidade'] == unidade]
        valores = [sum(a.get(k, 0) for a in subtotal) for k in ('quantidade_total', 'quantidade_executada')]
        resumo.append(f'<row r="{i}">' + _texto(f'A{i}', unidade) +
                      _formula(f'B{i}', f'SUMIFS(Quantitativos!E$8:E${fim},Quantitativos!D$8:D${fim},A{i})', valores[0]) +
                      _formula(f'C{i}', f'SUMIFS(Quantitativos!F$8:F${fim},Quantitativos!D$8:D${fim},A{i})', valores[1]) +
                      _formula(f'D{i}', f'B{i}-C{i}', valores[0]-valores[1]) + '</row>')
    resumo_ini = [f'<row r="2">{_texto("A2", "Resumo por unidade", 4)}</row>',
                  f'<row r="3">{_texto("A3", "100% FICTÍCIO. Unidades diferentes são totalizadas separadamente.")}</row>',
                  f'<row r="7">' + ''.join(_texto(f'{chr(65+i)}7', t, 3) for i, t in enumerate(['Unidade', 'Total', 'Executado', 'Saldo'])) + '</row>']
    def folha(rows, colunas, filtro=''):
        return (f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{NS}">'
                '<sheetViews><sheetView workbookViewId="0" showGridLines="0"><pane ySplit="7" topLeftCell="A8" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
                '<sheetFormatPr defaultRowHeight="22"/><cols>' + colunas + '</cols><sheetData>' + ''.join(rows) + '</sheetData>' + filtro + '</worksheet>')
    colunas = ''.join(f'<col min="{i}" max="{i}" width="{largura}" customWidth="1"/>' for i, largura in enumerate([22, 12, 13, 12, 18, 18, 18, 15], 1))
    styles = (f'<styleSheet xmlns="{NS}"><numFmts count="2"><numFmt numFmtId="164" formatCode="#,##0.00"/><numFmt numFmtId="165" formatCode="0.0%"/></numFmts>'
              '<fonts count="3"><font><sz val="11"/><name val="Arial"/><color rgb="FF223344"/></font><font><b/><sz val="11"/><name val="Arial"/><color rgb="FFFFFFFF"/></font><font><b/><sz val="15"/><name val="Arial"/></font></fonts>'
              '<fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF243B53"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFF1C2"/><bgColor indexed="64"/></patternFill></fill></fills>'
              '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="6">'
              '<xf fontId="0" fillId="0" borderId="0"/><xf numFmtId="164" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"/><xf numFmtId="165" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"/>'
              '<xf fontId="1" fillId="2" borderId="0" applyFill="1" applyFont="1"/><xf fontId="2" fillId="0" borderId="0" applyFont="1"/><xf numFmtId="164" fontId="0" fillId="3" borderId="0" applyNumberFormat="1" applyFill="1"/>'
              '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
    arquivos = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml': f'<workbook xmlns="{NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Resumo" sheetId="1" r:id="rId1"/><sheet name="Quantitativos" sheetId="2" r:id="rId2"/></sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>',
        'xl/_rels/workbook.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        'xl/styles.xml': styles,
        'xl/worksheets/sheet1.xml': folha(resumo_ini+resumo, colunas),
        'xl/worksheets/sheet2.xml': folha(linhas, colunas, f'<autoFilter ref="A7:H{fim}"/>'),
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destino, 'x', compression=ZIP_DEFLATED) as z:
        for nome, texto in arquivos.items():
            z.writestr(nome, texto.encode('utf-8'))
    return {'arquivo': str(destino), 'atividades': len(atividades), 'unidades': unidades,
            'formulas': True, 'homologacao_aplicativo': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--destino', type=Path, required=True)
    print(gerar_xlsx(Projeto.carregar(), p.parse_args().destino))
