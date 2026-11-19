"""Cabeçalhos de segurança (auditoria do frontend, rodada 7, defeito 6)."""

import base64
import hashlib
import re

from fastapi.testclient import TestClient

from infra4d.api import WEB, criar_app
from infra4d.cenarios import Projeto


def _cliente():
    return TestClient(criar_app(Projeto.carregar()))


def test_interface_tem_csp_estrito_com_hash_do_importmap():
    c = _cliente()
    r = c.get("/")
    csp = r.headers["content-security-policy"]
    assert "default-src 'self'" in csp and "object-src 'none'" in csp and "frame-ancestors 'none'" in csp
    assert "'unsafe-inline'" not in csp.split("script-src", 1)[1].split(";", 1)[0], "script-src não pode ter unsafe-inline"
    html = (WEB / "index.html").read_text(encoding="utf-8")
    for m in re.finditer(r"<script\s+type=\"importmap\"\s*>(.*?)</script>", html, re.S):
        h = base64.b64encode(hashlib.sha256(m.group(1).encode("utf-8")).digest()).decode()
        assert f"'sha256-{h}'" in csp
    assert r.headers["x-content-type-options"] == "nosniff"


def test_estaticos_e_api_tem_nosniff():
    c = _cliente()
    assert c.get("/static/app.js").headers["x-content-type-options"] == "nosniff"
    assert c.get("/api/saude").headers["x-content-type-options"] == "nosniff"


def test_relatorio_nao_executa_script():
    c = _cliente()
    r = c.get("/api/relatorio")
    csp = r.headers["content-security-policy"]
    assert "default-src 'none'" in csp and "script-src" not in csp
    assert "<script" not in r.text.lower() and "onclick" not in r.text.lower()
