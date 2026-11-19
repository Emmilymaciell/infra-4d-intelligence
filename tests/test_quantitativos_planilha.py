"""Conferência independente de totais/unidades e fórmulas OOXML editáveis."""
import copy
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from infra4d.cenarios import Projeto
from infra4d.quantitativos_planilha import NS, gerar_xlsx


def test_planilha_preserva_fontes_e_fecha_unidades_sem_somar_m_com_m3(tmp_path):
    p = Projeto.carregar()
    antes = copy.deepcopy(p.dados)
    arquivo = tmp_path/'quantitativos.xlsx'
    resultado = gerar_xlsx(p, arquivo)
    assert p.dados == antes
    ns = {'s': NS}
    with ZipFile(arquivo) as z:
        for nome in z.namelist():
            ET.fromstring(z.read(nome))
        resumo = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
        detalhe = ET.fromstring(z.read('xl/worksheets/sheet2.xml'))
        rows = resumo.findall('s:sheetData/s:row', ns)[3:]
        for row in rows:
            unidade = row.find('s:c/s:is/s:t', ns).text
            fontes = [a for a in p.dados['atividades'] if a.get('unidade') == unidade and a.get('quantidade_total', 0) > 0]
            total_cache = float(row.findall('s:c', ns)[1].find('s:v', ns).text)
            assert total_cache == pytest.approx(sum(a['quantidade_total'] for a in fontes))
            assert row.findall('s:c', ns)[1].find('s:f', ns).text.startswith('SUMIFS(')
        primeira = detalhe.find("s:sheetData/s:row[@r='8']", ns)
        assert primeira.find("s:c[@r='G8']/s:f", ns).text == 'E8-F8'
        assert primeira.find("s:c[@r='H8']/s:f", ns).text == 'IF(E8=0,0,F8/E8)'
        assert resultado['atividades'] == len(detalhe.findall('s:sheetData/s:row', ns))-5


def test_nao_sobrescreve_arquivo_nem_aceita_dado_real(tmp_path):
    p = Projeto.carregar()
    arquivo = tmp_path/'nativo.xlsx'
    arquivo.write_bytes(b'preservar')
    with pytest.raises(FileExistsError):
        gerar_xlsx(p, arquivo)
    assert arquivo.read_bytes() == b'preservar'
    p.dados['meta']['ficticio'] = False
    with pytest.raises(ValueError, match='fictícios'):
        gerar_xlsx(p, tmp_path/'real.xlsx')
