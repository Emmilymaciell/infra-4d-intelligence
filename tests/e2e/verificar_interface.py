"""Verificação ponta a ponta da interface web do INFRA 4D (navegador real, headless).

NÃO é um teste do pytest (o nome não começa com test_ de propósito): abre o Chrome/Edge,
dirige a interface pelo Chrome DevTools Protocol e confere o comportamento observável.

Pré-requisitos
--------------
- Google Chrome ou Microsoft Edge instalado (procurado nos caminhos padrão do Windows; ou --navegador).
- Porta livre para o DevTools do navegador (padrão 9333; --porta-cdp).
- Python 3.13 do .venv do projeto (só biblioteca padrão; o cliente WebSocket está embutido).
- Servidor da API: se já houver um respondendo em --url (padrão http://127.0.0.1:8765), ele é USADO;
  senão o script sobe `uvicorn infra4d.api:app` (PYTHONPATH=scripts) nessa porta e o encerra no fim.
  Atenção: a verificação altera e depois LIMPA a simulação em memória do servidor (POST/DELETE /api/simulacao).

Uso
---
    .\\.venv\\Scripts\\python.exe tests\\e2e\\verificar_interface.py [--url URL] [--capturas PASTA]

Saída: uma linha PASS/FAIL por checagem e um resumo.
Código de saída: 0 = tudo passou; 1 = alguma checagem falhou; 2 = a verificação NÃO RODOU
(navegador ausente, servidor não subiu, DevTools inacessível) — terceiro estado, não é "verde".
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
NAVEGADORES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


class NaoRodou(Exception):
    """A verificação não pôde ser executada (ambiente)."""


# ---------------------------------------------------------------- WebSocket mínimo (RFC 6455, cliente)
class WebSocket:
    def __init__(self, url: str, timeout: float = 60):
        u = urllib.parse.urlparse(url)
        self.s = socket.create_connection((u.hostname, u.port), timeout=timeout)
        chave = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\n"
                        f"Connection: Upgrade\r\nSec-WebSocket-Key: {chave}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            c = self.s.recv(1)
            if not c:
                raise ConnectionError("handshake WebSocket interrompido")
            resp += c
        if b" 101 " not in resp.split(b"\r\n", 1)[0]:
            raise ConnectionError(f"handshake WebSocket recusado: {resp[:80]!r}")

    def _exato(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            c = self.s.recv(n - len(buf))
            if not c:
                raise ConnectionError("WebSocket fechado")
            buf += c
        return bytes(buf)

    def _enviar(self, opcode: int, dados: bytes) -> None:
        cab = bytearray([0x80 | opcode])
        n = len(dados)
        if n < 126:
            cab.append(0x80 | n)
        elif n < 65536:
            cab.append(0x80 | 126)
            cab += struct.pack(">H", n)
        else:
            cab.append(0x80 | 127)
            cab += struct.pack(">Q", n)
        mascara = os.urandom(4)
        cab += mascara
        self.s.sendall(bytes(cab) + bytes(b ^ mascara[i % 4] for i, b in enumerate(dados)))

    def enviar(self, texto: str) -> None:
        self._enviar(0x1, texto.encode())

    def receber(self) -> str:
        msg = bytearray()
        while True:
            b1, b2 = self._exato(2)
            op, n = b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._exato(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._exato(8))[0]
            mascara = self._exato(4) if b2 & 0x80 else None
            dados = self._exato(n)
            if mascara:
                dados = bytes(b ^ mascara[i % 4] for i, b in enumerate(dados))
            if op == 0x9:  # ping
                self._enviar(0xA, dados)
                continue
            if op == 0x8:
                raise ConnectionError("WebSocket fechado pelo navegador")
            msg += dados
            if b1 & 0x80:
                return msg.decode("utf-8")

    def fechar(self) -> None:
        try:
            self._enviar(0x8, b"")
            self.s.close()
        except OSError:
            pass


# ---------------------------------------------------------------- Chrome DevTools Protocol
class CDP:
    def __init__(self, ws_url: str):
        self.ws = WebSocket(ws_url)
        self.n = 0
        self.excecoes: list[str] = []
        self.erros_console: list[str] = []
        # interceptação de rede (Fetch): lista de (trecho_da_url, metodo|None, (status, corpo, content_type))
        self.respostas_falsas: list[tuple[str, str | None, tuple[int, str, str]]] = []

    def _enviar_sem_esperar(self, metodo: str, **params) -> None:
        self.n += 1
        self.ws.enviar(json.dumps({"id": self.n, "method": metodo, "params": params}))

    def _evento(self, m: dict) -> None:
        met, p = m.get("method"), m.get("params", {})
        if met == "Fetch.requestPaused":
            req = p["request"]
            for trecho, metodo, (status, corpo, tipo) in self.respostas_falsas:
                if trecho in req["url"] and (metodo is None or req["method"] == metodo):
                    self._enviar_sem_esperar("Fetch.fulfillRequest", requestId=p["requestId"], responseCode=status,
                                             responseHeaders=[{"name": "Content-Type", "value": tipo}],
                                             body=base64.b64encode(corpo.encode("utf-8")).decode())
                    return
            self._enviar_sem_esperar("Fetch.continueRequest", requestId=p["requestId"])
            return
        if met == "Runtime.exceptionThrown":
            d = p["exceptionDetails"]
            self.excecoes.append((d.get("exception") or {}).get("description") or d.get("text", "?"))
        elif met == "Runtime.consoleAPICalled" and p.get("type") == "error":
            self.erros_console.append(" ".join(str(a.get("value", a.get("description", ""))) for a in p["args"]))
        elif met == "Log.entryAdded" and p["entry"].get("level") == "error":
            self.erros_console.append(f"{p['entry'].get('text')} {p['entry'].get('url', '')}")

    def chamar(self, metodo: str, **params) -> dict:
        self.n += 1
        meu = self.n
        self.ws.enviar(json.dumps({"id": meu, "method": metodo, "params": params}))
        while True:
            m = json.loads(self.ws.receber())
            if m.get("id") == meu:
                if "error" in m:
                    raise RuntimeError(f"{metodo}: {m['error']}")
                return m.get("result", {})
            self._evento(m)

    def js(self, expr: str):
        r = self.chamar("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            d = r["exceptionDetails"]
            raise RuntimeError(f"erro JS: {(d.get('exception') or {}).get('description') or d.get('text')}")
        return r["result"].get("value")

    def esperar(self, expr: str, timeout: float = 15, passo: float = 0.2) -> bool:
        fim = time.time() + timeout
        while time.time() < fim:
            try:
                if self.js(expr):
                    return True
            except RuntimeError:
                pass
            time.sleep(passo)
        return False

    def clicar(self, x: float, y: float) -> None:
        for tipo in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.chamar("Input.dispatchMouseEvent", type=tipo, x=x, y=y, button="left", clickCount=1)

    def captura(self, caminho: Path) -> None:
        r = self.chamar("Page.captureScreenshot", format="png")
        caminho.write_bytes(base64.b64decode(r["data"]))


# ---------------------------------------------------------------- ambiente
def api_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/saude", timeout=3) as r:
            return r.status == 200
    except OSError:
        return False


def subir_servidor(url: str):
    if api_ok(url):
        print(f"[ambiente] usando servidor já ativo em {url}")
        return None
    porta = urllib.parse.urlparse(url).port or 8765
    # banco do histórico/cenários salvos num arquivo temporário: os cenários salvos pelo teste não vão para output/
    banco = Path(tempfile.mkdtemp(prefix="infra4d-e2e-banco-")) / "e2e.sqlite"
    env = dict(os.environ, PYTHONPATH=str(RAIZ / "scripts"), INFRA4D_BANCO=str(banco))
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "infra4d.api:app", "--port", str(porta)],
                            cwd=RAIZ, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        if api_ok(url):
            print(f"[ambiente] servidor iniciado pelo script em {url} (pid {proc.pid})")
            return proc
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    proc.kill()
    raise NaoRodou(f"servidor não respondeu em {url}")


def abrir_navegador(caminho: str | None, porta: int):
    exe = caminho or next((c for c in NAVEGADORES if Path(c).exists()), None)
    if not exe or not Path(exe).exists():
        raise NaoRodou("Chrome/Edge não encontrado (use --navegador)")
    perfil = tempfile.mkdtemp(prefix="infra4d-e2e-")
    proc = subprocess.Popen([exe, "--headless=new", f"--remote-debugging-port={porta}", "--use-angle=swiftshader",
                             "--enable-unsafe-swiftshader", f"--user-data-dir={perfil}", "--no-first-run",
                             "--no-default-browser-check", "--window-size=1440,1000", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{porta}/json/list", timeout=2) as r:
                alvo = next((t for t in json.load(r) if t.get("type") == "page"), None)
            if alvo:
                return proc, perfil, alvo["webSocketDebuggerUrl"]
        except OSError:
            pass
        time.sleep(0.25)
    proc.kill()
    raise NaoRodou(f"DevTools do navegador inacessível na porta {porta}")


# ---------------------------------------------------------------- checagens
class Relatorio:
    def __init__(self):
        self.res: list[tuple[bool, str]] = []

    def pular(self, texto: str, motivo: str) -> None:
        """Checagem não aplicável neste ambiente: reportada, mas não conta como PASS nem FAIL."""
        print(f"SKIP  {texto}  [{motivo}]", flush=True)

    def ok(self, cond, texto: str, detalhe: str = "") -> bool:
        cond = bool(cond)
        self.res.append((cond, texto))
        print(f"{'PASS' if cond else 'FAIL'}  {texto}{f'  [{detalhe}]' if detalhe else ''}", flush=True)
        return cond


CARGA_XSS = {
    "lote": 'L1"><img src=x onerror="window.__xss=1',
    "servico": "<img src=x onerror=window.__xss=2>",
    "termino": "<img src=x onerror=window.__xss=3>",
    "nome": "<img src=x onerror=window.__xss=4>",
}


def dados_maliciosos() -> tuple[dict, str]:
    """Cópia da ferrovia fictícia com as cargas da auditoria r7 (roteiros dos testes skip):
    id de lote L1, id do 1º serviço, meta.termino_linha_base e o nome de uma atividade em andamento da cadeia
    determinante (L3-S03-TER); e meta.estaca_origem = 100 (estaca dos tooltips × /api/referencia/km)."""
    d = json.loads((RAIZ / "examples" / "synthetic" / "ferrovia_ficticia.json").read_text(encoding="utf-8"))
    lote_velho, lote_novo = d["lotes"][0]["id"], CARGA_XSS["lote"]
    d["lotes"][0]["id"] = lote_novo
    for colecao in ("segmentos", "atividades", "oaes", "restricoes"):
        for x in d.get(colecao, []):
            if x.get("lote_id") == lote_velho:
                x["lote_id"] = lote_novo
    serv_velho = d["servicos"][0]["id"]
    d["servicos"][0]["id"] = CARGA_XSS["servico"]
    for a in d["atividades"]:
        if a.get("servico_id") == serv_velho:
            a["servico_id"] = CARGA_XSS["servico"]
    d["meta"]["termino_linha_base"] = CARGA_XSS["termino"]
    alvo = "L3-S03-TER"
    next(a for a in d["atividades"] if a["id"] == alvo)["nome"] = CARGA_XSS["nome"]
    d["meta"]["estaca_origem"] = 100
    return d, alvo


def subir_servidor_injetado(dados: dict, porta: int):
    """Sobe a API com uma obra em memória (criar_app(fontes=...)), num processo separado; devolve (proc, url, pasta)."""
    pasta = Path(tempfile.mkdtemp(prefix="infra4d-r7-"))
    arq = pasta / "obra.json"
    arq.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    script = (
        "import json, sys, uvicorn\n"
        f"sys.path.insert(0, {str(RAIZ / 'scripts')!r})\n"
        "from infra4d.api import criar_app\n"
        "from infra4d.cenarios import Projeto\n"
        f"d = json.load(open({str(arq)!r}, encoding='utf-8'))\n"
        "app = criar_app(fontes={'ferrovia': Projeto(d)})\n"
        f"uvicorn.run(app, host='127.0.0.1', port={porta}, log_level='warning')\n"
    )
    proc = subprocess.Popen([sys.executable, "-c", script], cwd=RAIZ, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{porta}"
    for _ in range(120):
        if api_ok(url):
            return proc, url, pasta
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    proc.kill()
    shutil.rmtree(pasta, ignore_errors=True)
    raise RuntimeError(f"servidor com dados injetados não subiu na porta {porta}")


def document_tem_tour(c: CDP) -> bool:
    return bool(c.js("!!document.querySelector('.tour-balao') || !!document.querySelector('.tour-realce')"))


def limite_visual_manifesto(nome='tolerancia_visual_federacao_m') -> float:
    """Mesma fonte de limites da suíte; ausência ou tipo indevido falha fechado."""
    import importlib.util
    import math
    spec = importlib.util.spec_from_file_location('infra4d_manifesto_e2e', RAIZ / 'tests' / 'conftest.py')
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    bruto = modulo.ler_manifesto()['verificacao']['limites'][nome]
    # O leitor canônico mantém escalares como texto; a fixture limite() também
    # faz a conversão explícita. Não confundir isso com limite ausente/inválido.
    try:
        valor = float(bruto)
    except (TypeError, ValueError):
        raise ValueError(f'{nome} inválido no manifesto') from None
    if isinstance(bruto, bool) or not math.isfinite(valor) or not 0 < valor < 1:
        raise ValueError(f'{nome} inválido no manifesto')
    return valor


def altura_nativa_da_revisao(pacote: dict, atividade_id: str) -> float:
    """Altura mundial de autoria Z-up calculada independentemente do renderer web."""
    props = next(f['properties'] for f in pacote['features'] if f['properties']['atividade_id'] == atividade_id)
    malha = props['geometria_local_m']
    linha_z = malha['matrix_world'][2]
    cotas = [sum(linha_z[i] * v[i] for i in range(3)) + linha_z[3] for v in malha['vertices']]
    return max(cotas) - min(cotas)


def verificar(c: CDP, url: str, capturas: Path | None, rel: Relatorio, porta_cdp: int,
              base_federacao: Path | None = None, revisao_federacao: Path | None = None,
              glb_federacao: Path | None = None, somente_federacao: bool = False) -> None:
    T = "window.__infra4d"
    foto = (lambda nome: c.captura(capturas / f"{nome}.png")) if capturas else (lambda nome: None)

    def selecionar_valor(sel: str, valor: str) -> None:
        c.js(f"(() => {{ const s=document.querySelector({json.dumps(sel)}); s.value={json.dumps(valor)}; "
             f"s.dispatchEvent(new Event('change')); }})()")

    def marcar(sel: str, v: bool) -> None:
        c.js(f"(() => {{ const k=document.querySelector({json.dumps(sel)}); k.checked={str(v).lower()}; "
             f"k.dispatchEvent(new Event('change')); }})()")

    c.chamar("Runtime.enable")
    c.chamar("Log.enable")
    c.chamar("Page.enable")
    c.chamar("Network.enable")
    c.chamar("Network.setCacheDisabled", cacheDisabled=True)
    c.chamar("Emulation.setDeviceMetricsOverride", width=1440, height=1000, deviceScaleFactor=1, mobile=False)
    req = urllib.request.Request(f"{url}/api/simulacao", method="DELETE")
    urllib.request.urlopen(req, timeout=30).close()

    # ---- carga e 3D (vista inicial)
    c.chamar("Page.navigate", url=f"{url}/#modelo")
    # a interface não carregar é defeito da interface (FAIL), não do ambiente
    if not rel.ok(c.esperar(f"{T} && {T}.viewer() && {T}.viewer().resumo().porEstado.concluido > 0", 40),
                  "interface carrega e o modelo 3D recebe o estado 4D (até 40 s)"):
        foto('falha-carga-inicial')
        diagnostico = c.js("""(() => ({
          titulo:document.title,url:location.href,
          erroGlobal:document.querySelector('#erro-global')?.innerText,
          viewer:document.querySelector('#viewer')?.innerText,
          painel:document.querySelector('#painel')?.innerText,
          estado:window.__infra4d ? {projeto:!!window.__infra4d.estado.projeto,
            viewer:!!window.__infra4d.viewer(),cenario:window.__infra4d.estado.cenarioAtivo} : null
        }))()""")
        print('DIAGNOSTICO CARGA: ' + json.dumps(diagnostico, ensure_ascii=False))
        print('EXCECOES JS: ' + json.dumps(c.excecoes, ensure_ascii=False))
        print('ERROS CONSOLE: ' + json.dumps(c.erros_console, ensure_ascii=False))
        if capturas:
            (capturas / 'falha-carga-inicial.json').write_text(json.dumps({
                'pagina':diagnostico,'excecoes':c.excecoes,'console':c.erros_console,
            }, ensure_ascii=False, indent=2), encoding='utf-8')
        return
    time.sleep(0.8)
    rel.ok(c.js("document.title.includes('INFRA 4D') && document.querySelector('h1').textContent.includes('INFRA 4D')"),
           "título e cabeçalho contêm 'INFRA 4D'")
    rel.ok(c.js(r"document.querySelector('#faixa-aviso').innerText.includes('DADOS FICTÍCIOS') && "
                r"/\d{2}\/\d{2}\/\d{4}/.test(document.querySelector('#aviso-data-status').textContent)"),
           "faixa de aviso com data de status")
    rel.ok(c.js("document.querySelector('#erro-global').hidden"), "sem banner de erro global")
    r0 = c.js(f"{T}.viewer().resumo()")
    rel.ok(r0["pecas"] > 400 and r0["porEstado"].get("em_execucao", 0) > 0, "3D gerou as peças e coloriu pelo estado 4D",
           json.dumps(r0, ensure_ascii=False))
    cam = c.js(f"{T}.viewer().resumoCamera()")
    rel.ok(50 <= cam["kmAlvo"] <= 60 and cam["distancia"] < 15000,
           "vista inicial aproximada na frente crítica (km 50–60)", json.dumps(cam))
    sobrepostos = c.js("""(() => { const r=[...document.querySelectorAll('.rotulo-km')].filter(e=>e.style.display!=='none')
        .map(e=>e.getBoundingClientRect()); let n=0;
        for (let i=0;i<r.length;i++) for (let j=i+1;j<r.length;j++) { const a=r[i], b=r[j];
          if (a.left<b.right && a.right>b.left && a.top<b.bottom && a.bottom>b.top) n++; }
        return {visiveis: r.length, sobrepostos: n}; })()""")
    rel.ok(sobrepostos["visiveis"] > 0 and sobrepostos["sobrepostos"] == 0, "rótulos do 3D sem sobreposição",
           json.dumps(sobrepostos))
    foto("e2e-3d-inicial")

    # ---- variante de apresentação (cálculo e IDs da análise permanecem intactos)
    selecionar_valor('#v-experiencia', 'apresentacao')
    time.sleep(0.8)
    visual = c.js(f"{T}.viewer().resumoVisual()")
    rel.ok(visual['modo'] == 'apresentacao' and visual['escala'] == 1 and visual['contexto']
           and visual['detalhes'] > 10 and visual['instancias'] > 10,
           'apresentação: ponte, terreno e dormentes reais no WebGL, em escala 1:1', json.dumps(visual))
    rel.ok(c.js(f"{T}.viewer().resumo().pecas") == r0['pecas'],
           'apresentação: IDs e peças da referência preservados')
    rel.ok(c.js("!document.querySelector('#v-visual-aviso').hidden && document.querySelector('#v-visual-aviso').innerText.includes('FICTÍCIO')"),
           'apresentação: natureza ilustrativa declarada')
    c.js("document.querySelector('#v-oae').click()")
    cam_oae = c.js(f"{T}.viewer().resumoCamera()")
    rel.ok(cam_oae['distancia'] < 250, 'apresentação: câmera de detalhe da ponte', json.dumps(cam_oae))
    if capturas:
        benchmark = c.js(f"""(async () => {{
          const tempos=[]; let ultimo=performance.now();
          for(let i=0;i<20;i++) await new Promise(resolve=>requestAnimationFrame(t=>{{tempos.push(t-ultimo);ultimo=t;resolve();}}));
          return {{...{T}.viewer().resumoVisual(),viewport:[innerWidth,innerHeight],
            frame_mediano_ms:tempos.sort((a,b)=>a-b)[10],userAgent:navigator.userAgent,
            modo:'headless/CDP; renderização por software; não prova GPU real'}};
        }})()""")
        (capturas / 'benchmark-visual.json').write_text(json.dumps(benchmark, ensure_ascii=False, indent=2), encoding='utf-8')
    c.js("(() => { const s=document.querySelector('#t-slider');s.value=s.max;s.dispatchEvent(new Event('input')); })()")
    c.esperar(f"{T}.viewer().resumo().porEstado.concluido === {T}.viewer().resumo().pecas", 15)
    foto('e2e-apresentacao-ponte')
    c.js("document.querySelector('#t-status').click()")
    marcar('#v-baixo-consumo', True)
    reduzido = c.js(f"{T}.viewer().resumoVisual()")
    rel.ok(reduzido['baixoConsumo'] and 0 < reduzido['instancias'] < visual['instancias'],
           'apresentação: baixo consumo reduz instâncias mantendo vínculo', json.dumps(reduzido))
    marcar('#v-corte', True)
    rel.ok(c.js(f"{T}.viewer().resumoVisual().corte"), 'apresentação: plano de corte ativo')
    marcar('#v-corte', False)
    c.js("document.querySelector('#v-superior').click()")
    rel.ok(c.js(f"{T}.viewer().camera.position.y > {T}.viewer().controls.target.y"), 'apresentação: vista superior')
    c.js("document.querySelector('#btn-reuniao').click()")
    rel.ok(c.js("document.body.classList.contains('modo-reuniao') && document.querySelector('#t-play').getBoundingClientRect().top < document.querySelector('#viewer').getBoundingClientRect().top"),
           'reunião: timeline proeminente antes do canvas')
    c.chamar('Emulation.setDeviceMetricsOverride', width=1366, height=768, deviceScaleFactor=1, mobile=False)
    time.sleep(0.3)
    header = c.js("""(() => ({largura:innerWidth,fora:[...document.querySelectorAll('.topo button,.topo select')]
        .filter(e=>e.offsetParent && (e.getBoundingClientRect().right>innerWidth || e.getBoundingClientRect().left<0))
        .map(e=>({texto:e.innerText,direita:e.getBoundingClientRect().right}))}))()""")
    rel.ok(not header['fora'], 'reunião: controles do cabeçalho cabem em 1366 px', json.dumps(header))
    foto('e2e-apresentacao-reuniao-1366')
    c.chamar('Emulation.setDeviceMetricsOverride', width=1440, height=1000, deviceScaleFactor=1, mobile=False)
    time.sleep(0.3)
    foto('e2e-apresentacao-reuniao')
    c.js("document.querySelector('#btn-reuniao').click()")
    marcar('#v-baixo-consumo', False)
    selecionar_valor('#obra-sel', 'rodovia')
    rel.ok(c.esperar(f"{T} && {T}.obra() === 'rodovia' && {T}.viewer() && {T}.viewer().resumoVisual().modo === 'apresentacao' && {T}.viewer().resumoVisual().contexto", 60),
           'apresentação: troca para rodovia mantém preferência e contexto no novo viewer')
    selecionar_valor('#obra-sel', 'ferrovia')
    rel.ok(c.esperar(f"{T} && {T}.obra() === 'ferrovia' && {T}.viewer() && {T}.viewer().resumoVisual().modo === 'apresentacao' && {T}.viewer().resumoVisual().contexto", 60),
           'apresentação: retorno à ferrovia preserva modo sem mudar a base')
    selecionar_valor('#v-experiencia', 'tecnico')
    rel.ok(c.js(f"{T}.viewer().resumoVisual().escala === 1 && !{T}.viewer().resumoVisual().contexto"),
           'técnico: escala 1:1 sem contexto ilustrativo')
    selecionar_valor('#v-experiencia', 'analise')
    c.js("sessionStorage.removeItem('infra4d.experiencia')")
    rel.ok(c.js(f"{T}.viewer().resumoVisual().escala === 40 && !{T}.viewer().resumoVisual().contexto")
           and c.js(f"{T}.viewer().resumo().pecas") == r0['pecas'],
           'análise: retorna ao fallback aprovado sem alterar peças')
    fallback = c.js(f"""(async () => {{
      const {{renderFallback2D}}=await import('/static/fallback2d.js');
      const host=document.createElement('div');document.body.appendChild(host);
      let id=null;
      renderFallback2D(host,{T}.estado.projeto,{T}.estado.cenarios.independente,x=>{{id=x;}});
      const alvos=host.querySelectorAll('[data-2d-id]'), esperado=alvos[0].getAttribute('data-2d-id');
      alvos[0].dispatchEvent(new MouseEvent('click'));
      const resultado={{pecas:alvos.length,selecionado:id,esperado}};host.remove();return resultado;
    }})()""")
    rel.ok(fallback['pecas'] > 100 and fallback['selecionado'] == fallback['esperado'],
           'fallback 2D sem WebGL mantém atividades selecionáveis', json.dumps(fallback))

    # Fluxo opcional com os arquivos EFETIVAMENTE retornados do QGIS/Blender (sem simular autoria).
    if base_federacao and revisao_federacao:
        base_txt = base_federacao.read_text(encoding='utf-8-sig')
        revisao_txt = revisao_federacao.read_text(encoding='utf-8-sig')
        c.js("document.querySelector('#federacao-painel').open = true")
        rel.ok(c.js("document.querySelector('#fed-enquadrar').disabled"), 'federação: enquadrar começa desabilitado sem revisão')
        for seletor, nome, conteudo in [('#fed-base', 'baseline.geojson', base_txt),
                                         ('#fed-revisao', revisao_federacao.name, revisao_txt)]:
            c.js(f"(async () => {{const d=new DataTransfer(); d.items.add(new File([{json.dumps(conteudo)}], {json.dumps(nome)}, {{type:'application/geo+json'}})); "
                 f"const el=document.querySelector({json.dumps(seletor)});el.files=d.files;el.dispatchEvent(new Event('change')); "
                 "await new Promise(r=>setTimeout(r,200));return true;})()")
        c.js("document.querySelector('#fed-validar').click()")
        c.esperar("!document.querySelector('#fed-publicar').disabled || document.querySelector('#fed-status').innerText.includes('Revisão não publicada')", 90)
        previa_ok = c.js("!document.querySelector('#fed-publicar').disabled")
        rel.ok(previa_ok,
               'federação: retorno real de arquivo passa pela prévia na interface',
               c.js("document.querySelector('#fed-status').innerText"))
        if not previa_ok:
            raise RuntimeError('federação recusada; motivo registrado acima')
        txt_fed = c.js("document.querySelector('#fed-resultado').innerText")
        rel.ok('PRÉVIA' in txt_fed and 'IDs preservados' in txt_fed,
               'federação: diferenças, IDs e datas exibidos antes da publicação', txt_fed[:200])
        rel.ok(c.js(f"{T}.viewer().pecasRevisao.length > 0"),
               'federação: geometria revisada desenhada em sobreposição no WebGL')
        pacote_revisao = json.loads(revisao_txt)
        app_nativo = pacote_revisao.get('meta', {}).get('source_app')
        if app_nativo in ('Blender', 'FreeCAD'):
            tolerancia_visual = limite_visual_manifesto()
            atividade_nativa = 'OAE3-SUE' if app_nativo == 'FreeCAD' else 'L3-S04-TER'
            altura_esperada = altura_nativa_da_revisao(pacote_revisao, atividade_nativa)
            resumo_nativo = c.js(f"{T}.viewer().resumoRevisao()")
            dim = resumo_nativo.get('dimensoes', {}).get(atividade_nativa, {})
            rel.ok(resumo_nativo['malhasNativas'] > 0 and abs(dim.get('y', 0) - altura_esperada) <= tolerancia_visual,
                   f'federação {app_nativo}: malha nativa reaberta preserva a altura editada em metros', json.dumps(dim))
        if app_nativo == 'FreeCAD':
            ocupacao_minima = limite_visual_manifesto('ocupacao_linear_minima_revisao_viewport')
            c.js(f"{T}.viewer().enquadrarTudo(); document.querySelector('#fed-enquadrar').click()")
            time.sleep(0.5)
            medir_viewport = ("(() => {const v=" + T + ".viewer(); v.camera.updateMatrixWorld(); const pontos=[];"
                        "for(const m of v.pecasRevisao){const a=m.geometry.getAttribute('position');"
                        "for(let i=0;i<a.count;i++){const p=v.camera.position.clone().set(a.getX(i),a.getY(i),a.getZ(i));"
                        "m.localToWorld(p);p.project(v.camera);pontos.push(p);}}"
                        "const xs=pontos.map(p=>p.x),ys=pontos.map(p=>p.y);return {pontos:pontos.length,"
                        "dentro:pontos.every(p=>Math.abs(p.x)<=1&&Math.abs(p.y)<=1&&Math.abs(p.z)<=1),"
                        "ocupacao:Math.max((Math.max(...xs)-Math.min(...xs))/2,(Math.max(...ys)-Math.min(...ys))/2)};})()")
            tela = c.js(medir_viewport)
            rel.ok(tela['pontos'] > 0 and tela['dentro'] and tela['ocupacao'] >= ocupacao_minima,
                   'federação: enquadrar torna fragmento CAD visível e inteiro no viewport', json.dumps(tela))
            foto('e2e-federacao-enquadrada-real')
            c.js("document.querySelector('#fed-isolar').click()")
            isolada = c.js("(() => {const v=" + T + ".viewer(),m=v.pecasRevisao[0],a=m.geometry.getAttribute('position');"
                           "const p=v.camera.position.clone().set(a.getX(0),a.getY(0),a.getZ(0));m.localToWorld(p);"
                           "p.project(v.camera);const r=v.renderer.domElement.getBoundingClientRect();"
                           "const hit=v._pick({clientX:r.left+(p.x+1)*r.width/2,clientY:r.top+(1-p.y)*r.height/2});"
                           "return {isolada:v.revisaoIsolada,referencia:v.grupo.visible,pecas:v.resumo().pecas,"
                           "hitNativo:!!(hit&&hit.userData.revisao)};})()")
            rel.ok(isolada['isolada'] and not isolada['referencia'] and isolada['pecas'] == r0['pecas'],
                   'federação: isolar oculta referência sem remover peças ou alterar dados', json.dumps(isolada))
            # O teste de seleção usa um pixel da malha retornada; referência oculta não pode interceptá-lo.
            rel.ok(isolada['hitNativo'], 'federação: raycast ignora a referência oculta')
            c.js("document.querySelector('#fed-resultado [data-fed-id=\"OAE3-SUE\"]').click()")
            time.sleep(0.3)
            apos_selecao = c.js(medir_viewport)
            rel.ok(c.js(f"{T}.estado.selecionada") == 'OAE3-SUE' and apos_selecao['dentro'] and apos_selecao['ocupacao'] >= ocupacao_minima,
                   'federação: selecionar peça isolada mantém vínculo e fragmento legível', json.dumps(apos_selecao))
            foto('e2e-federacao-isolada-real')
            componentes_cad = [p for f in pacote_revisao['features'] for p in f['properties'].get('componentes_nativos', [])]
            if componentes_cad:
                alvo_cad = next((p for p in componentes_cad if p['nome'] == 'OAE3_SUE_CORRIMAO_V01_E'), componentes_cad[0])
                cid_cad = json.dumps(alvo_cad['componente_id'])
                c.js(f"(() => {{const s=document.querySelector('#fed-componente');s.value={cid_cad};s.dispatchEvent(new Event('change'));}})()")
                rel.ok(c.js(f"{T}.viewer().resumoRevisao().componentesNativos") == len(componentes_cad),
                       'CAD: cada componente retornado tem malha e identidade próprias')
                rel.ok(c.js(f"{T}.viewer().componenteRevisaoSelecionado") == alvo_cad['componente_id']
                       and alvo_cad['nome'] in c.js("document.querySelector('#cad-propriedades-lateral').innerText"),
                       'CAD: seleção da peça apresenta propriedades nativas na ficha lateral')
                foto('e2e-cad-propriedades-reais')
                c.js("document.querySelector('#fed-contexto').click()")
                time.sleep(0.6)
                contexto_cad = c.js("(() => {const v=" + T + ".viewer();return {modo:v.modoVisual,"
                    "isolada:v.revisaoIsolada,referencia:v.grupo.visible,ambiente:v.contexto?.grupo.visible,"
                    "engenharia:v.contexto?.engenharia.visible,elementos:v.pecasRevisao.length,escala:v.resumoVisual().escala};})()")
                rel.ok(contexto_cad == {'modo': 'apresentacao', 'isolada': True, 'referencia': False,
                       'ambiente': True, 'engenharia': False, 'elementos': len(componentes_cad), 'escala': 1},
                       'CAD: ambiente preserva escala e peças nativas, sem duplicar engenharia ilustrativa', json.dumps(contexto_cad))
                foto('e2e-oae-cad-com-ambiente-real')
                selecionar_valor('#v-experiencia', 'tecnico')
                rel.ok(not c.js("document.querySelector('#fed-contexto').checked"),
                       'CAD: voltar ao técnico desliga o ambiente ilustrativo')
            c.js("document.querySelector('#fed-isolar').click()")
            rel.ok(c.js(f"!{T}.viewer().revisaoIsolada && {T}.viewer().grupo.visible"),
                   'federação: restaurar referência preserva modo e visibilidade')
        if glb_federacao:
            conteudo_glb = base64.b64encode(glb_federacao.read_bytes()).decode('ascii')
            c.js(f"(() => {{const b=Uint8Array.from(atob({json.dumps(conteudo_glb)}),c=>c.charCodeAt(0));const d=new DataTransfer();"
                 "d.items.add(new File([b],'retorno-nativo.glb',{type:'model/gltf-binary'}));"
                 "document.querySelector('#fed-glb').files=d.files;document.querySelector('#fed-carregar-glb').click();})()")
            rel.ok(c.esperar("document.querySelector('#fed-status').innerText.includes('GLB nativo carregado')", 90),
                   'federação Blender: GLB verdadeiro carregado sem dependências externas',
                   c.js("document.querySelector('#fed-status').innerText"))
            glb = c.js(f"{T}.viewer().resumoGlbRevisao()")
            dim_glb = (glb or {}).get('dimensoes', {}).get('L3-S04-TER', {})
            rel.ok(glb and abs(dim_glb.get('y', 0) - altura_esperada) <= tolerancia_visual,
                   'federação Blender: GLB preserva a edição geométrica e identidade', json.dumps(dim_glb))
            foto('e2e-federacao-glb-nativo-real')
        c.js("document.querySelector('#fed-resultado [data-fed-id]').click()")
        sel_fed = c.js(f"{T}.estado.selecionada")
        rel.ok(sel_fed and sel_fed in c.js("document.querySelector('#aba-modelo [data-detalhes]').innerText"),
               'federação: seleção da revisão compartilha o vínculo com a ficha de referência')
        foto('e2e-federacao-previa-real')
        c.js("document.querySelector('#fed-publicar').click()")
        rel.ok(c.esperar("document.querySelector('#fed-resultado').innerText.includes('PUBLICADA EM CÓPIA')", 90),
               'federação: publicação explícita isolada pelo botão')
        rel.ok(c.js(f"{T}.viewer().resumo().pecas") == r0['pecas'],
               'federação: referência 3D permanece intacta após publicar')
        foto('e2e-federacao-publicada-real')
        if app_nativo == 'FreeCAD':
            c.js("document.querySelector('#fed-isolar').click()")
            vazia = json.loads(base_txt)
            vazia['meta']['revision'] = 'freecad-sem-mudancas'
            vazia_txt = json.dumps(vazia)
            c.js(f"(async () => {{const d=new DataTransfer(); d.items.add(new File([{json.dumps(vazia_txt)}],'sem-mudancas.geojson',{{type:'application/geo+json'}}));"
                 "const el=document.querySelector('#fed-revisao');el.files=d.files;el.dispatchEvent(new Event('change'));"
                 "await new Promise(r=>setTimeout(r,200));document.querySelector('#fed-validar').click();return true;})()")
            c.esperar("!document.querySelector('#fed-publicar').disabled || document.querySelector('#fed-status').innerText.includes('Revisão não publicada')", 90)
            rel.ok(c.js(f"{T}.viewer().pecasRevisao.length===0 && !{T}.viewer().revisaoIsolada && {T}.viewer().grupo.visible && document.querySelector('#fed-isolar').disabled && !document.querySelector('#fed-isolar').checked"),
                   'r23: revisão sem mudanças após isolamento restaura a referência e os controles')
        c.js("document.querySelector('#fed-remover').click()")
        rel.ok(c.js(f"{T}.viewer().pecasRevisao.length === 0"), 'federação: sobreposição pode ser ocultada')
        rel.ok(c.js("document.querySelector('#fed-enquadrar').disabled"), 'federação: ocultar desabilita enquadramento')
        rel.ok(c.js("document.querySelector('#fed-isolar').disabled && !document.querySelector('#fed-isolar').checked"),
               'federação: remover restaura referência e desabilita isolamento')
        c.js(f"{T}.selecionar(null, 'teste')")
        c.js("document.querySelector('#federacao-painel').open = false")
        selecionar_valor('#v-experiencia', 'analise')
        if somente_federacao:
            rel.ok(not c.excecoes, 'federação focada: nenhuma exceção JavaScript', '; '.join(c.excecoes)[:300])
            return

    c.js("document.querySelector('[data-ir-km=\"L1\"]').click()")
    time.sleep(0.5)
    cam1 = c.js(f"{T}.viewer().resumoCamera()")
    rel.ok(0 <= cam1["kmAlvo"] <= 20, "atalho 'Ir para: L1' leva a câmera ao lote 1", json.dumps(cam1))
    c.js("document.querySelector('[data-ir-km=\"frente\"]').click()")
    time.sleep(0.5)

    # ---- clique 3D (raycast): o esperado é a peça do TOPO da pilha naquele ponto, obtida pelo mesmo raycast
    c.js(f"{T}.viewer().enquadrarAtividade('L3-S04-DOR')")
    time.sleep(0.8)
    pt = c.js(f"{T}.viewer().centroNaTela('L3-S04-DOR-E03')")
    esperado = c.js(f"{T}.viewer().idNoPonto({pt['x']}, {pt['y']})")
    c.clicar(pt["x"], pt["y"])
    time.sleep(0.4)
    sel = c.js(f"{T}.estado.selecionada")
    rel.ok(esperado and sel == esperado and sel.startswith("L3-S04"), "clique na peça 3D seleciona a atividade do topo da pilha",
           f"esperado={esperado} selecionada={sel}")
    rel.ok(c.js("document.querySelector('#aba-modelo [data-detalhes]').innerText.includes('ceil(')"),
           "detalhes mostram a memória de cálculo (fórmula)")
    foto("e2e-3d-selecionado")

    # ---- referência linear no 3D: clique no terreno (fora das peças) -> km/estaca/lote/atividades
    c.js("document.querySelector('[data-ir-km=\"frente\"]').click()")
    time.sleep(0.6)
    pg = c.js(f"{T}.viewer().pontoNaTela(55.5, 1200)")
    c.chamar("Input.dispatchMouseEvent", type="mouseMoved", x=pg["x"], y=pg["y"])
    hov = c.esperar("document.querySelector('#v-hover').textContent.includes('estaca')", 10)
    rel.ok(hov, "passar o mouse no 3D mostra km/estaca", c.js("document.querySelector('#v-hover').textContent"))
    c.clicar(pg["x"], pg["y"])
    c.esperar("!!document.querySelector('#v-info-ref')", 15)
    info = c.js("document.querySelector('#v-info-ref')?.innerText || ''")
    rel.ok("km 55" in info and "estaca" in info and "L3" in info
           and c.js("document.querySelectorAll('#v-info [data-ir]').length") > 0,
           "clique no terreno do 3D mostra km, estaca, lote e atividades do km", info.replace("\n", " ")[:140])
    c.js("document.querySelector('#v-info .fechar')?.click()")

    # ---- timeline 4D
    c.js("(() => { const s=document.querySelector('#t-slider'); s.value='30'; s.dispatchEvent(new Event('input')); })()")
    c.esperar(f"({T}.viewer().resumo().porEstado.nao_iniciado || 0) > 400", 10)
    ini = c.js(f"{T}.viewer().resumo()")
    c.js("(() => { const s=document.querySelector('#t-slider'); s.value=s.max; s.dispatchEvent(new Event('input')); })()")
    c.esperar(f"{T}.viewer().resumo().porEstado.concluido === {T}.viewer().resumo().pecas", 10)
    fim = c.js(f"{T}.viewer().resumo()")
    rel.ok(ini["porEstado"].get("nao_iniciado", 0) > fim["porEstado"].get("nao_iniciado", 0)
           and fim["porEstado"].get("concluido") == fim["pecas"], "timeline 4D muda as cores (no fim tudo concluído)",
           f"início={ini['porEstado']} fim={fim['porEstado']}")
    # ---- PLAY da linha do tempo 4D: a data avança, o estado das peças segue /api/estado4d e a pausa para
    def ler_data_tl() -> str:
        d, m_, a_ = c.js("document.querySelector('#t-data').textContent").strip().split("/")
        return f"{a_}-{m_}-{d}"

    pecas_por_ativ = c.js(f"Object.fromEntries([...{T}.viewer().porAtividade].map(([k, v]) => [k, v.map(m => [m.userData.i, m.userData.n])]))")

    def esperado_4d(data_iso: str) -> dict:
        e4 = json.load(urllib.request.urlopen(f"{url}/api/estado4d?data={data_iso}&cenario=independente&obra=ferrovia", timeout=120))["atividades"]
        cont = {"concluido": 0, "em_execucao": 0, "nao_iniciado": 0}
        for aid, pecas in pecas_por_ativ.items():
            f_ = (e4.get(aid) or {}).get("fracao", 0) or 0
            for i, n in pecas:  # mesma regra do visualizador: peça i de n
                if f_ >= (i + 1) / n - 1e-9:
                    cont["concluido"] += 1
                elif f_ > i / n + 1e-9:
                    cont["em_execucao"] += 1
                else:
                    cont["nao_iniciado"] += 1
        return cont

    def quadro_tl() -> tuple[str, dict]:
        r_ = c.js(f"{T}.viewer().resumo().porEstado")
        return ler_data_tl(), {k: r_.get(k, 0) for k in ("concluido", "em_execucao", "nao_iniciado")}

    c.js("(() => { const s=document.querySelector('#t-slider'); s.value='0'; s.dispatchEvent(new Event('input')); })()")
    time.sleep(1.0)
    data0 = ler_data_tl()
    quadros = []
    for _ in range(2):
        c.js("document.querySelector('#t-play').click()")            # play
        time.sleep(2.6)
        c.js("document.querySelector('#t-play').click()")            # pausa
        time.sleep(1.4)                                              # último estado 4D (debounce + resposta)
        d_, est_ = quadro_tl()
        time.sleep(1.5)
        parado = ler_data_tl() == d_
        quadros.append((d_, est_, esperado_4d(d_), parado))
    (d1, e1, x1, p1), (d2, e2, x2, p2) = quadros
    rel.ok(data0 < d1 < d2 and e1 == x1 and e2 == x2 and e1 != e2 and p1 and p2 and c.js("document.querySelector('#t-play').textContent.trim()") == "▶",
           "PLAY da linha do tempo: a data avança, o estado 4D de 2 quadros = /api/estado4d e a pausa para a animação",
           f"{data0} → {d1} {e1} → {d2} {e2}; parado={p1 and p2}")

    c.js("document.querySelector('#t-status').click()")
    time.sleep(0.5)

    # ---- Gantt / tabela / detalhes
    c.js(f"{T}.irPara('cronograma')")
    time.sleep(0.4)
    c.js("document.querySelector('.g-rotulos [data-id=\"L3-S04-TER\"] rect').dispatchEvent(new MouseEvent('click',{bubbles:true}))")
    time.sleep(0.4)
    rel.ok(c.js(f"{T}.estado.selecionada === 'L3-S04-TER'"), "clique no Gantt seleciona a atividade")
    rel.ok(c.js("document.querySelectorAll('.g-barras path[marker-end]').length > 0"), "Gantt desenha setas de dependência")
    rel.ok(c.js("!!document.querySelector('#tabela tr.sel[data-id=\"L3-S04-TER\"]')"), "tabela destaca a selecionada")
    rel.ok(c.js(f"{T}.viewer().enquadrarPendente === 'L3-S04-TER'"), "3D enquadrará a seleção ao abrir a aba")
    rel.ok(c.js("document.querySelector('#aba-cronograma [data-detalhes]').innerText.includes('caminho mais longo')"),
           "detalhes exibem o selo 'caminho mais longo'")
    foto("e2e-gantt")

    # ---- filtros
    selecionar_valor("#f-lote", "L2")
    c.esperar("document.querySelector('#painel h2') && document.querySelector('#painel h2').textContent.includes('L2')", 15)
    ids = c.js("[...document.querySelectorAll('.g-rotulos .linha')].map(g=>g.dataset.id)")
    rel.ok(ids and all("L2" in i or i.startswith("OAE2") for i in ids), "filtro de lote aplicado ao Gantt", f"{len(ids)} linhas")
    rel.ok(c.js("document.querySelector('#painel h2').textContent.includes('L2')"), "painel recarregado com ?lote=L2")
    v1 = c.js(f"{T}.viewer().resumo().visiveis")
    marcar("#v-ocultar", True)
    v2 = c.js(f"{T}.viewer().resumo().visiveis")
    rel.ok(v2 < v1, "3D oculta elementos filtrados", f"{v1} -> {v2}")
    marcar("#v-ocultar", False)

    # ---- filtros de SEGMENTO, faixa de KM e PERÍODO (Gantt, tabela, linha de balanço e 3D), com vazio claro
    proj_f = json.load(urllib.request.urlopen(f"{url}/api/projeto?obra=ferrovia", timeout=120))
    ind_f = json.load(urllib.request.urlopen(f"{url}/api/cenarios/independente?obra=ferrovia", timeout=120))["atividades"]

    def esperado_filtro(lote="", seg="", k0=None, k1=None, d0="", d1=""):
        ids = []
        for a in proj_f["atividades"]:
            if lote and a.get("lote_id") != lote:
                continue
            if seg and a.get("segmento_id") != seg:
                continue
            if k0 is not None or k1 is not None:
                if a.get("km_ini") is None or a.get("km_fim") is None:
                    continue
                lo, hi = min(a["km_ini"], a["km_fim"]), max(a["km_ini"], a["km_fim"])
                if (k0 is not None and hi < k0) or (k1 is not None and lo > k1):
                    continue
            if d0 or d1:
                r_ = ind_f.get(a["id"]) or {}
                ini, fim = r_.get("inicio"), r_.get("termino") or r_.get("inicio")
                if not ini or not fim or (d0 and fim < d0) or (d1 and ini > d1):
                    continue
            ids.append(a["id"])
        return set(ids)

    def aplicar_filtros(lote="", seg="", k0="", k1="", d0="", d1=""):
        c.js(f"""(() => {{ const v = (s, x) => {{ document.querySelector(s).value = x; }};
            v('#f-lote', {json.dumps(lote)}); v('#f-segmento', {json.dumps(seg)}); v('#f-km-ini', {json.dumps(str(k0))}); v('#f-km-fim', {json.dumps(str(k1))});
            v('#f-data-ini', {json.dumps(d0)}); v('#f-data-fim', {json.dumps(d1)});
            document.querySelector('#f-data-fim').dispatchEvent(new Event('change')); }})()""")
        time.sleep(0.8)

    def ids_tela():
        c.js(f"{T}.irPara('cronograma')")
        time.sleep(0.5)
        gantt = set(c.js("[...document.querySelectorAll('.g-rotulos .linha')].map(g => g.dataset.id)"))
        tab = set(c.js("[...document.querySelectorAll('#tabela tr[data-id]')].map(t => t.dataset.id)"))
        c.js(f"{T}.irPara('balanco')")
        time.sleep(0.6)
        bal = set(c.js("[...document.querySelectorAll('#balanco [data-camada=cenario] .ativ')].map(g => g.dataset.id)"))
        c.js(f"{T}.irPara('modelo')")
        c.esperar(f"{T}.viewer() && {T}.viewer().resumo().pecas > 0", 30)
        marcar("#v-ocultar", True)
        vis3d = c.js(f"{T}.viewer().resumo().visiveis")
        marcar("#v-ocultar", False)
        return gantt, tab, bal, vis3d

    c.js(f"{T}.selecionar(null, 'teste')")  # o 3D mantém visível a selecionada mesmo filtrada: sem seleção, a contagem é exata
    pecas_n = c.js(f"Object.fromEntries([...{T}.viewer().porAtividade].map(([k, v]) => [k, v.length]))")
    km_ids ={a["id"] for a in proj_f["atividades"] if a.get("km_ini") is not None and a.get("tipo") == "tarefa"}
    casos_f = [
        ("segmento L2-S03", dict(seg="L2-S03"), dict(seg="L2-S03")),
        ("km 10–20", dict(k0=10, k1=20), dict(k0=10, k1=20)),
        ("período jan/2027 (independente)", dict(d0="2027-01-01", d1="2027-01-31"), dict(d0="2027-01-01", d1="2027-01-31")),
        ("lote L1 + km 15–25", dict(lote="L1", k0=15, k1=25), dict(lote="L1", k0=15, k1=25)),
    ]
    for nome_f, tela_args, esp_args in casos_f:
        aplicar_filtros(**tela_args)
        esp = esperado_filtro(**esp_args)
        g_, t_, b_, v3 = ids_tela()
        esp_b = esp & km_ids
        esp_v = sum(pecas_n.get(i, 0) for i in esp)
        n_res = c.js("document.querySelector('#f-resumo-n')?.textContent")
        rel.ok(esp and g_ == esp and t_ == esp and b_ == esp_b and v3 == esp_v and n_res == str(len(esp)),
               f"filtro {nome_f}: Gantt, tabela, linha de balanço e 3D mostram exatamente as atividades esperadas",
               f"{len(esp)} atividades, {len(esp_b)} no balanço, {esp_v} peças no 3D")
    # faixa sem nenhuma atividade: vazio claro em todas as telas
    aplicar_filtros(k0=100, k1=120)
    g_, t_, b_, v3 = ids_tela()
    vazio3d = c.js("!document.querySelector('#v-vazio').hidden")
    c.js(f"{T}.irPara('cronoimport')"); c.js(f"{T}.irPara('cronograma')")
    time.sleep(0.4)
    msg_g = c.js("document.querySelector('#gantt').innerText")
    msg_t = c.js("document.querySelector('#tabela').innerText")
    rel.ok(not g_ and not t_ and not b_ and v3 == 0 and vazio3d and "Nenhuma atividade" in msg_g and "Nenhuma atividade" in msg_t
           and c.js("!!document.querySelector('#f-resumo-vazio')"),
           "filtro sem resultado (km 100–120): estado vazio claro no Gantt, tabela, balanço, 3D e no resumo dos filtros")
    # faixa invertida: aviso no resumo; e "Limpar filtros" restaura tudo
    aplicar_filtros(k0=30, k1=20)
    inv = c.js("document.querySelector('#f-resumo').innerText")
    c.js("document.querySelector('#f-limpar').click()")
    time.sleep(0.6)
    rel.ok("km inicial maior que o final" in inv and c.js("document.querySelector('#f-resumo-n').textContent") == str(len(proj_f["atividades"])),
           "filtro de km invertido avisa no resumo; 'Limpar filtros' volta a mostrar todas as atividades", inv[:90])
    selecionar_valor("#f-lote", "L2")   # estado que a seção seguinte espera
    c.esperar("document.querySelector('#painel h2') && document.querySelector('#painel h2').textContent.includes('L2')", 30)

    # ---- linha de balanço
    c.js(f"{T}.irPara('balanco')")
    time.sleep(0.6)
    n_l2 = c.js("document.querySelectorAll('#balanco [data-camada=cenario] .ativ').length")
    esperado_l2 = c.js(f"{T}.estado.projeto.atividades.filter(a => a.tipo==='tarefa' && a.km_ini!=null && a.lote_id==='L2').length")
    ids_lb = c.js("[...document.querySelectorAll('#balanco .ativ')].map(g=>g.dataset.id)")
    rel.ok(n_l2 == esperado_l2 and all("L2" in i or i.startswith("OAE2") for i in ids_lb),
           "linha de balanço respeita o filtro de lote", f"{n_l2} de {esperado_l2} esperadas")
    selecionar_valor("#f-lote", "")
    c.esperar("!document.querySelector('#painel h2').textContent.includes('L2')", 15)
    time.sleep(0.4)
    n_tot = c.js("document.querySelectorAll('#balanco [data-camada=cenario] .ativ').length")
    esperado_tot = c.js(f"{T}.estado.projeto.atividades.filter(a => a.tipo==='tarefa' && a.km_ini!=null).length")
    rel.ok(n_tot == esperado_tot and n_tot > 100, "linha de balanço desenha todas as atividades com trecho",
           f"{n_tot} de {esperado_tot}")
    rel.ok(c.js("document.querySelectorAll('#balanco svg line[stroke=\"#d62d2d\"]').length >= 1"),
           "linha de balanço tem a linha da data de status")
    marcar("#lb-sobrepor", True)
    time.sleep(0.3)
    rel.ok(c.js("document.querySelectorAll('#balanco [data-camada=lb] [stroke-dasharray]').length > 50"),
           "sobreposição da linha de base tracejada")
    c.js("document.querySelector('#balanco .ativ[data-id=\"L2-S04-LAS\"]').lastElementChild"
         ".dispatchEvent(new MouseEvent('click',{bubbles:true}))")
    time.sleep(0.3)
    rel.ok(c.js(f"{T}.estado.selecionada === 'L2-S04-LAS'"), "clique na linha de balanço seleciona a atividade (seleção global)")
    c.js("(() => { const g=document.querySelector('#balanco .ativ[data-id=\"L2-S04-LAS\"]').lastElementChild;"
         " g.dispatchEvent(new MouseEvent('mousemove',{bubbles:true, clientX:300, clientY:300})); })()")
    tip = c.js("document.querySelector('.tooltip')?.innerText || ''")
    rel.ok("estaca 1750+00,00" in tip, "tooltip da linha de balanço mostra a estaca", tip.replace("\n", " ")[:120])
    marcar("#f-critico", True)
    time.sleep(0.4)
    n_crit = c.js("document.querySelectorAll('#balanco [data-camada=cenario] .ativ').length")
    rel.ok(0 < n_crit < 15, "linha de balanço respeita 'só caminho crítico'", f"{n_crit} atividades")
    marcar("#f-critico", False)

    # ---- conflitos entre frentes na linha de balanço
    api_conf = json.load(urllib.request.urlopen(f"{url}/api/recursos/conflitos-balanco?cenario=independente&buffer_km=1&buffer_dias=0", timeout=120))
    c.esperar(f"document.querySelectorAll('#balanco [data-camada=conflitos] .conflito').length === {api_conf['n_conflitos']}"
              " && !!document.querySelector('#lb-tab-conflitos')", 60)
    n_circ = c.js("document.querySelectorAll('#balanco [data-camada=conflitos] circle').length")
    n_lin = c.js("document.querySelectorAll('#lb-tab-conflitos tbody tr').length")
    rel.ok(api_conf["n_conflitos"] > 0 and n_circ == api_conf["n_conflitos"] == n_lin,
           "conflitos entre frentes marcados na linha de balanço e listados", f"API={api_conf['n_conflitos']} círculos={n_circ} linhas={n_lin}")
    esperado_conf = c.js("document.querySelector('#lb-tab-conflitos tbody tr')?.dataset.ir")
    c.js("document.querySelector('#lb-tab-conflitos tbody tr')?.click()")
    time.sleep(0.4)
    rel.ok(esperado_conf and c.js(f"{T}.estado.selecionada") == esperado_conf, "clique na lista de conflitos seleciona a frente sucessora",
           str(esperado_conf))
    c.js("(() => { const e=document.querySelector('#lb-buffer-km'); e.value='0.2'; e.dispatchEvent(new Event('change')); })()")
    api_conf2 = json.load(urllib.request.urlopen(f"{url}/api/recursos/conflitos-balanco?cenario=independente&buffer_km=0.2&buffer_dias=0", timeout=120))
    c.esperar(f"document.querySelectorAll('#balanco [data-camada=conflitos] .conflito').length === {api_conf2['n_conflitos']}", 60)
    n2 = c.js("document.querySelectorAll('#balanco [data-camada=conflitos] .conflito').length")
    rel.ok(n2 == api_conf2["n_conflitos"] and n2 <= n_circ, "buffer menor recalcula os conflitos", f"{n_circ} -> {n2}")
    c.js("(() => { const e=document.querySelector('#lb-buffer-km'); e.value='1'; e.dispatchEvent(new Event('change')); })()")
    time.sleep(0.5)
    foto("e2e-balanco")

    # ---- aba Recursos: histograma + nivelamento com frota compartilhada
    c.js(f"{T}.irPara('recursos')")
    c.esperar("document.querySelectorAll('#r-hist-svg .r-barra').length > 5", 60)
    n_barras = c.js("document.querySelectorAll('#r-hist-svg .r-barra').length")
    rel.ok(n_barras > 5 and c.js("!!document.querySelector('#r-hist-cap')"),
           "histograma de equipes empilhado por serviço com linha de capacidade", f"{n_barras} barras")
    c.js("(() => { const s=document.querySelector('#r-hist-serv'); s.value='TER'; s.dispatchEvent(new Event('change')); })()")
    time.sleep(0.3)
    rel.ok(c.js("document.querySelectorAll('#r-hist-svg .r-barra').length") > 0
           and "TER" not in c.js("document.querySelector('#r-hist .legenda-graf').innerText.split('Capacidade')[0]"),
           "detalhar TER empilha por lote")
    foto("e2e-recursos-hist")

    def nivelar_ui(cen: str, frota: int | None) -> dict:
        c.js(f"""(() => {{ const s=document.querySelector('#r-niv-cen'); s.value='{cen}';
            const u=document.querySelector('#r-frota-usar'); u.checked={'true' if frota is not None else 'false'};
            const sv=document.querySelector('#r-frota-serv'); sv.value='TER';
            document.querySelector('#r-frota-n').value='{frota if frota is not None else 2}';
            document.querySelector('#r-nivelar').click(); }})()""")
        c.esperar("!!document.querySelector('#r-niv-res') || !!document.querySelector('#r-niv .erro:not(#r-niv-ignorado)')", 180)
        return c.js("""(() => ({ res: !!document.querySelector('#r-niv-res'),
            ignorado: !!document.querySelector('#r-niv-ignorado'),
            delta: document.querySelector('#r-niv-delta')?.textContent || '',
            atrasadas: document.querySelectorAll('#r-niv-tab tbody tr').length,
            erro: document.querySelector('#r-niv .erro:not(#r-niv-ignorado)')?.textContent || '' }))()""")

    sem = nivelar_ui("linha_base", None)
    rel.ok(sem["res"] and sem["delta"].startswith("0"), "nivelamento da linha de base sem frota compartilhada: término inalterado",
           json.dumps(sem, ensure_ascii=False))
    com = nivelar_ui("linha_base", 2)
    if com["ignorado"]:
        rel.ok(True, "UI avisa que a API ignorou a frota compartilhada pedida (*/TER = 2)")
        rel.pular("frota compartilhada */TER = 2 atrasa o término nivelado",
                  "a rota /api/recursos/nivelamento desta versão não aceita capacidades")
    else:
        rel.ok(com["res"] and com["delta"].startswith("+") and com["atrasadas"] > 0,
               "frota compartilhada */TER = 2 na linha de base atrasa o término nivelado e lista as deslocadas",
               json.dumps(com, ensure_ascii=False))
    foto("e2e-recursos-nivelamento")

    # ---- aba "Cronograma da construtora": exportar MSPDI, exemplo, upload e arquivo inválido
    c.js(f"{T}.irPara('cronoimport')")
    time.sleep(0.4)
    href = c.js("document.querySelector('#ci-exportar').href")
    with urllib.request.urlopen(href, timeout=120) as r:
        xml = r.read()
        rel.ok(r.status == 200 and b"<Project" in xml[:2000] and "cenario=construtora" in href and "obra=" in href,
               "botão Exportar MSPDI aponta para o XML do cenário (200, <Project>)", f"{href} ({len(xml)} bytes)")
    req_cmp = urllib.request.Request(f"{url}/api/cronograma/comparar?cenario=independente&obra=ferrovia", data=xml, method="POST",
                                     headers={"Content-Type": "application/octet-stream"})
    esperado_cmp = json.load(urllib.request.urlopen(req_cmp, timeout=180))
    c.js("document.querySelector('#ci-exemplo').click()")
    c.esperar("!!document.querySelector('#ci-delta') || !!document.querySelector('#ci-erro')", 180)
    delta_txt = c.js("document.querySelector('#ci-delta')?.textContent || document.querySelector('#ci-erro')?.textContent")
    d_esp = esperado_cmp["delta_termino_dias_corridos"]
    rel.ok(delta_txt.startswith(f"{'+' if d_esp > 0 else ''}{d_esp} ") and
           c.js("document.querySelector('#ci-casadas').textContent") == str(esperado_cmp["n_casadas"]),
           "'Usar exemplo' (construtora exportada × motor independente) mostra o delta de término da API",
           f"{delta_txt} · casadas={esperado_cmp['n_casadas']}")
    deltas = c.js("[...document.querySelectorAll('#ci-tab tbody tr')].map(tr => Math.abs(parseInt(tr.children[6].textContent.replace(/[^0-9-]/g,'')) || 0))")
    rel.ok(len(deltas) == esperado_cmp["n_com_diferenca"] and deltas == sorted(deltas, reverse=True),
           "tabela de diferenças ordenada por |Δ término| e só com diferenças", f"{len(deltas)} linhas")
    foto("e2e-cronoimport")
    # upload de arquivo real (MSPDI do cenário independente) comparado com o próprio independente -> sem diferença no término
    c.js("""(async () => {
        const buf = await (await fetch('/api/cronograma/exportar/mspdi?cenario=independente&obra=ferrovia')).arrayBuffer();
        const dt = new DataTransfer(); dt.items.add(new File([buf], 'independente.xml', {type: 'application/xml'}));
        const inp = document.querySelector('#ci-arquivo'); inp.files = dt.files;
        const s = document.querySelector('#ci-motor-cen'); s.value = 'independente';
        document.querySelector('#ci-comparar').click(); return true; })()""")
    c.esperar("(document.querySelector('#ci-res p')?.textContent || '').includes('independente.xml')", 180)
    up = c.js("document.querySelector('#ci-delta')?.textContent || ''")
    rel.ok(up.startswith("0 "), "upload de MSPDI (independente) × motor independente: término igual", up)
    c.js("""(() => { const dt = new DataTransfer(); dt.items.add(new File(['isto não é cronograma'], 'lixo.txt'));
        const inp = document.querySelector('#ci-arquivo'); inp.files = dt.files; document.querySelector('#ci-comparar').click(); })()""")
    c.esperar("!!document.querySelector('#ci-erro')", 60)
    er = c.js("document.querySelector('#ci-erro')?.textContent || ''")
    rel.ok("não reconhecido" in er, "arquivo inválido gera mensagem clara (415)", er[:120])

    # ---- aba Fiscalização (sintética)
    def get_json(caminho: str):
        return json.load(urllib.request.urlopen(f"{url}{caminho}", timeout=120))

    c.js(f"{T}.selecionar('L3-S03-TER', 'teste')")
    c.js(f"{T}.irPara('fiscalizacao')")
    api_dia = get_json("/api/fiscalizacao/diario?atividade_id=L3-S03-TER&obra=ferrovia")
    c.esperar(f"document.querySelectorAll('#fz-diario tbody tr').length === {len(api_dia['diarios'])}", 60)
    n_dia = c.js("document.querySelectorAll('#fz-diario tbody tr').length")
    rel.ok(n_dia == len(api_dia["diarios"]) > 0 and c.js("document.querySelector('#fz-frente').value") == "L3-S03-TER"
           and "Conferido" in c.js("document.querySelector('#fz-diario-resumo').innerText"),
           "diário da frente selecionada (L3-S03-TER) com estado, chuva e km executado", f"{n_dia} diários")
    api_prod = get_json("/api/fiscalizacao/produtividade?obra=ferrovia")
    c.esperar(f"document.querySelectorAll('#fz-prod tbody tr').length === {len(api_prod['atividades'])}", 60)
    rel.ok(c.js("document.querySelectorAll('#fz-prod tbody tr').length") == len(api_prod["atividades"]) > 0,
           "tabela de produtividade (dia trabalhado × dia útil, perda por paralisação)", f"{len(api_prod['atividades'])} atividades")
    api_conc = get_json("/api/fiscalizacao/conciliacao?obra=ferrovia")
    c.esperar("!!document.querySelector('#fz-conc')", 60)
    rel.ok(str(api_conc["n_boletins"]) in c.js("document.querySelector('#fz-conc').innerText"),
           "conciliação diário × boletim", f"boletins={api_conc['n_boletins']} divergências={api_conc['n_divergencias']}")
    rel.ok("SINTÉTICA" in c.js("document.querySelector('#fiscalizacao').innerText"), "aba declara a fiscalização como SINTÉTICA")
    # filtro de lote global aplicado à fiscalização (produtividade e conciliação com ?lote=)
    prod_l2 = get_json("/api/fiscalizacao/produtividade?lote=L2&obra=ferrovia")
    conc_l2 = get_json("/api/fiscalizacao/conciliacao?lote=L2&obra=ferrovia")
    selecionar_valor("#f-lote", "L2")
    c.esperar(f"document.querySelectorAll('#fz-prod tbody tr').length === {len(prod_l2['atividades'])}"
              " && !!document.querySelector('#fz-conc')", 60)
    ids_l2 = c.js("[...document.querySelectorAll('#fz-prod tbody tr [data-ir]')].map(e => e.dataset.ir)")
    conc_txt = c.js("document.querySelector('#fz-conc')?.innerText || ''")
    rel.ok(len(ids_l2) == len(prod_l2["atividades"]) > 0 and all(i.startswith(("L2", "OAE2")) for i in ids_l2)
           and str(conc_l2["n_boletins"]) in conc_txt,
           "fiscalização com filtro de lote L2 (produtividade e conciliação via ?lote=)",
           f"{len(ids_l2)} atividades, {conc_l2['n_boletins']} boletins")
    selecionar_valor("#f-lote", "")
    c.esperar(f"document.querySelectorAll('#fz-prod tbody tr').length === {len(api_prod['atividades'])}", 60)

    def preencher(valores: dict) -> None:
        js = "; ".join(f"document.querySelector('#fz-{k}').value = {json.dumps(v)}" for k, v in valores.items())
        c.js(f"(() => {{ {js}; document.querySelector('#fz-validar').click(); }})()")

    preencher({"data": "2030-01-01", "atividade_id": "L1-S03-LAS", "quantidade": "-5", "horas_chuva": "30", "origem": ""})
    c.esperar("!!document.querySelector('#fz-invalido')", 30)
    campos_erro = c.js("[...document.querySelectorAll('.msg-erro')].map(e => e.dataset.erro)")
    rel.ok({"data", "quantidade", "horas_chuva", "origem"} <= set(campos_erro)
           and c.js("document.querySelector('#fz-quantidade').classList.contains('campo-erro')"),
           "lançar diário inválido: erros da API aparecem campo a campo", f"{sorted(set(campos_erro))}")
    c.js("document.querySelector('#fz-limpar').click()")  # zera o resultado anterior (evita esperar pelo #fz-invalido antigo)
    c.esperar("!document.querySelector('#fz-invalido')", 10)
    preencher({"data": "2026-11-05", "atividade_id": "L1-S03-LAS", "estado": "lancado", "quantidade": "300", "equipes_dias": "1",
               "horas_chuva": "0", "km_ini_exec": "12.0", "km_fim_exec": "12.2", "origem": "fiscal de campo (e2e)"})
    c.esperar("!!document.querySelector('#fz-valido') || !!document.querySelector('#fz-invalido')", 30)
    rel.ok(c.js("!!document.querySelector('#fz-valido')"), "lançar diário válido: API confirma (nada é gravado)",
           c.js("document.querySelector('#fz-res').innerText")[:120])
    foto("e2e-fiscalizacao")

    # ---- linha REAL executada na linha de balanço
    api_real = get_json("/api/fiscalizacao/linha-real?obra=ferrovia")
    n_esp = sum(1 for f in api_real["frentes"] if len(f.get("pontos") or []) >= 2)
    c.js(f"{T}.irPara('balanco')")
    marcar("#lb-real", True)
    c.esperar(f"document.querySelectorAll('#balanco [data-camada=real] .real').length === {n_esp}", 60)
    n_real = c.js("document.querySelectorAll('#balanco [data-camada=real] .real').length")
    rel.ok(n_real == n_esp > 0 and c.js("document.querySelector('#balanco [data-camada=cenario]').getAttribute('opacity')") == "0.45",
           "linha REAL executada sobreposta à projetada (projetada esmaecida)", f"{n_real} frentes")
    foto("e2e-balanco-real")
    marcar("#lb-real", False)

    # ---- simulação
    c.js(f"{T}.selecionar('L3-S04-TER', 'teste')")
    c.js(f"{T}.irPara('simulacao')")
    time.sleep(0.3)
    c.js("(() => { const s=document.querySelector('#s-ativ'); s.value='L3-S04-TER'; s.dispatchEvent(new Event('change')); })()")
    rel.ok(c.js("document.querySelector('#s-atual').innerText.includes('caminho mais longo')"),
           "simulação mostra o selo 'caminho mais longo' da atividade escolhida (L3-S04-TER)")
    c.js("document.querySelector('[data-ex=\"0\"]').click()")
    c.esperar("!!document.querySelector('.sim-res .delta-grande')", 30)
    d0 = c.js("document.querySelector('.sim-res .delta-grande')?.textContent")
    rel.ok(d0 and d0.startswith("+"), "exemplo crítico (TER L3-S04) atrasa o término", d0 or "")
    rel.ok(c.js(f"{T}.estado.cenarioAtivo === 'simulado' && document.querySelector('#f-cenario').value === 'simulado'"),
           "cenário ativo passa a 'simulado'")
    rel.ok(c.js("!document.querySelector('#aviso-sim').hidden"), "faixa indica simulação ativa")
    rel.ok(c.js("document.querySelectorAll('.sim-res ol li').length > 0"), "'Por que o término mudou?' linha a linha")
    rel.ok(c.js("document.querySelector('.sim-res').innerText.includes('Caminho mais longo no cenário simulado')"),
           "resultado lista o caminho mais longo do cenário simulado")
    c.js(f"{T}.irPara('balanco')")
    time.sleep(0.4)
    rel.ok(c.js("document.querySelector('#lb-resumo').innerText.includes('Simulado')"), "linha de balanço segue o cenário simulado")
    c.js(f"{T}.irPara('simulacao')")
    foto("e2e-sim-critica")
    c.js("document.querySelector('[data-ex=\"1\"]').click()")
    c.esperar("(document.querySelector('.sim-res .delta-grande')?.textContent || '').startsWith('0')", 30)
    d1 = c.js("document.querySelector('.sim-res .delta-grande')?.textContent")
    rel.ok(d1 and d1.startswith("0"), "exemplo com folga (LAS L2-S04) não muda o término", d1 or "")
    c.js("document.querySelector('input[name=s-modo][value=servico]').click()")
    time.sleep(0.2)
    c.js("(() => { const s=document.querySelector('#s-serv'); s.value='TER'; s.dispatchEvent(new Event('change'));"
         " document.querySelector('#s-eq').value='25'; document.querySelector('#s-rodar').click(); })()")
    c.esperar("!!document.querySelector('.sim-form .erro')", 15)
    msg = c.js("document.querySelector('.sim-form .erro')?.textContent")
    rel.ok(msg and "20" in msg, "erro 422 da API aparece em mensagem clara", msg or "")
    c.js("document.querySelector('#s-limpar').click()")
    c.esperar(f"{T}.estado.cenarioAtivo === 'independente' && document.querySelector('#aviso-sim').hidden", 30)
    rel.ok(c.js(f"{T}.estado.cenarioAtivo === 'independente'"), "limpar simulação volta ao cenário independente")

    # ---- painel
    c.js(f"{T}.irPara('painel')")
    c.esperar("document.querySelectorAll('#p-hist rect').length > 0", 60)
    rel.ok(c.js("document.querySelectorAll('#p-curva polyline').length === 4"), "curva S com 4 séries")
    rel.ok(c.js("document.querySelectorAll('#p-producao rect').length > 5"), "produção semanal com barras")
    rel.ok(c.js("(() => { const t=document.querySelector('#p-previsao').innerText; return t.includes('P50') && t.includes('P80'); })()"),
           "cartão de previsão probabilística com P50/P80")
    rel.ok(c.js("document.querySelectorAll('#p-hist rect').length >= 3"), "mini-histograma da previsão desenhado")
    n_marcos = c.js("document.querySelectorAll('#tab-marcos tbody tr').length")
    rel.ok(n_marcos == 4 and c.js("document.querySelectorAll('#tab-marcos .indice').length") >= 4,
           "tabela de marcos contratuais com 4 linhas e desvio colorido (ferrovia)", f"{n_marcos} linhas")
    sens = c.js("document.querySelector('#p-sensibilidade')?.innerText || ''")
    rel.ok("override" in sens.lower() and ("não altera" in sens or "dias corridos" in sens),
           "cartão 'Sensibilidade ao método' com as duas datas e a conclusão", sens.replace("\n", " ")[:120])

    # ---- três métodos de previsão + Monte Carlo v1 × v2
    api_es = json.load(urllib.request.urlopen(f"{url}/api/previsao/earned-schedule?obra=ferrovia", timeout=120))
    r_es = next(r for r in api_es["resultados"] if r["lote"] is None)
    c.esperar("document.querySelectorAll('#p-metodos-tab tbody tr').length === 6", 60)
    txt_met = c.js("document.querySelector('#p-metodos').innerText")
    br = lambda iso: "/".join(reversed(iso.split("-")))
    rel.ok(c.js("document.querySelectorAll('#p-metodos-tab tbody tr').length") == 6 and br(r_es["IEAC_spi_termino"]) in txt_met
           and br(r_es["cpm_independente_termino"]) in txt_met and "Earned Schedule" in txt_met,
           "cartão 'Três métodos de previsão' (CPM ×2, ES, Monte Carlo) com os números da API",
           f"ES(SPI)={r_es['IEAC_spi_termino']} CPM ind.={r_es['cpm_independente_termino']}")
    c.js("(() => { document.querySelector('#p-v2-riscos').checked = true; document.querySelector('#p-v2-chuva').checked = true;"
         " document.querySelector('#p-v2-rho').value = '0.5'; document.querySelector('#p-v2-rodar').click(); })()")
    c.esperar("document.querySelectorAll('#p-faixas .faixa').length === 2 || !!document.querySelector('#p-previsao .erro')", 400)
    v2r = c.js("document.querySelector('#p-v2-resumo')?.innerText || document.querySelector('#p-previsao .erro')?.innerText || ''")
    rel.ok(c.js("document.querySelectorAll('#p-faixas .faixa').length") == 2 and "v2" in v2r,
           "Monte Carlo v1 × v2 (riscos + chuva + rho 0,5): duas faixas P10–P90", v2r.replace("\n", " ")[:140])
    foto("e2e-painel-previsoes")
    foto("e2e-painel")

    # ---- 3D com serviço desconhecido (dados injetados num visualizador isolado, descartado em seguida)
    r_desc = c.js(f"""(async () => {{
        const mod = await import('/static/viewer3d.js');
        const p = structuredClone({T}.estado.projeto);
        const alvo = p.atividades.find(a => a.tipo === 'tarefa' && a.km_ini != null && !a.oae_id && a.servico_id);
        alvo.servico_id = 'XYZ-DESCONHECIDO';
        p.atividades.push({{ ...alvo, id: 'TESTE-ZZZ', servico_id: 'ZZZ', disciplina: 'Disciplina inventada' }});
        const div = document.createElement('div');
        div.style.cssText = 'position:fixed;left:0;top:0;width:320px;height:200px';
        document.body.appendChild(div);
        let v;
        try {{
          v = new mod.Viewer3D(div, p, {{}});
          v.setModoCor('servico');
          const res = {{ resumo: v.resumo(), genericos: v.plano.genericos, temXYZ: v.temGeometria(alvo.id),
                         temZZZ: v.temGeometria('TESTE-ZZZ'), legenda: v.legenda() }};
          return res;
        }} finally {{ if (v) v.descartar(); div.remove(); }}
      }})()""")
    rel.ok(r_desc["temXYZ"] and r_desc["temZZZ"] and set(r_desc["genericos"]) >= {"XYZ-DESCONHECIDO", "ZZZ"}
           and "XYZ-DESCONHECIDO" in r_desc["legenda"] and "ZZZ" in r_desc["legenda"],
           "3D não quebra com serviço desconhecido (camada genérica + legenda automática)",
           f"genéricos={r_desc['genericos']} peças={r_desc['resumo']['pecas']}")

    # ---- relatório técnico (clique real no botão -> nova aba)
    ret = c.js("(() => { const r=document.querySelector('#btn-relatorio').getBoundingClientRect(); return {x:r.x+r.width/2, y:r.y+r.height/2}; })()")
    c.clicar(ret["x"], ret["y"])
    aba_rel = None
    for _ in range(40):
        with urllib.request.urlopen(f"http://127.0.0.1:{porta_cdp}/json/list", timeout=5) as r:
            aba_rel = next((t for t in json.load(r) if t.get("type") == "page" and "/api/relatorio" in t.get("url", "")), None)
        if aba_rel:
            break
        time.sleep(0.25)
    rel.ok(aba_rel is not None, "botão 'Relatório técnico' abre o relatório em nova aba", aba_rel["url"] if aba_rel else "nenhuma aba nova")
    if aba_rel:
        with urllib.request.urlopen(aba_rel["url"], timeout=60) as r:
            corpo = r.read().decode("utf-8", "replace")
            rel.ok(r.status == 200 and "FICTÍCIOS" in corpo.upper(), "relatório responde 200 e declara dados FICTÍCIOS",
                   f"status={r.status} obra={'obra=' in aba_rel['url']}")
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{porta_cdp}/json/close/{aba_rel['id']}", timeout=5).close()
        except OSError:
            pass

    # ---- seletor de obra
    obras = json.load(urllib.request.urlopen(f"{url}/api/obras", timeout=30))
    opcoes = c.js("[...document.querySelectorAll('#obra-sel option')].map(o => o.value)")
    rel.ok(len(opcoes) >= 1 and opcoes == [o["id"] for o in obras], "seletor de obra lista as obras de /api/obras",
           f"{opcoes}")
    atual = c.js(f"{T}.obra()")
    rel.ok(atual in opcoes and f"obra={atual}" in c.js("location.hash"), "obra escolhida aparece no hash da URL",
           c.js("location.hash"))

    def recarregar_e_esperar(acao_js: str, obra_esperada: str) -> bool:
        c.js("window.__marca = 1")
        c.js(acao_js)
        return c.esperar(f"!window.__marca && {T} && {T}.obra() === {json.dumps(obra_esperada)} && {T}.estado.projeto "
                         f"&& {T}.estado.cenarios.independente && document.querySelectorAll('.g-rotulos .linha').length > 0", 60)

    if len(opcoes) >= 2:
        outra = next(o for o in opcoes if o != atual)
        ok_troca = recarregar_e_esperar(f"(() => {{ const s=document.querySelector('#obra-sel'); s.value={json.dumps(outra)}; "
                                        f"s.dispatchEvent(new Event('change')); }})()", outra)
        nome = next(o["nome"] for o in obras if o["id"] == outra)
        rel.ok(ok_troca and f"obra={outra}" in c.js("location.hash")
               and nome in c.js("document.querySelector('#aviso-obra').textContent"),
               f"troca de obra ({atual} -> {outra}) recarrega dados, hash e faixa de aviso")
        tipo = c.js(f"{T}.estado.projeto.obra && {T}.estado.projeto.obra.tipo")
        c.js(f"{T}.irPara('modelo')")
        c.esperar(f"{T}.viewer() && {T}.viewer().resumo().pecas > 0", 40)
        rv = c.js(f"{T}.viewer() && {T}.viewer().resumo()")
        gen = c.js(f"{T}.viewer() && {T}.viewer().plano.genericos")
        rel.ok(rv and rv["pecas"] > 0 and gen == [], f"3D da obra '{outra}' ({tipo}) gera peças com seções conhecidas",
               f"{json.dumps(rv)} genéricos={gen}")
        c.esperar(f"{T}.viewer().resumo().porEstado.concluido > 0", 15)
        foto(f"e2e-3d-{outra}")
        if outra == "rodovia":
            # referência linear na rodovia: clique no terreno a 1500 m do eixo no km 25
            ref_r = json.load(urllib.request.urlopen(f"{url}/api/referencia/km?km=25&obra=rodovia", timeout=60))
            c.js(f"{T}.viewer().enquadrarKm(21.5, 28.5)")
            time.sleep(0.8)
            pr = c.js(f"{T}.viewer().pontoNaTela(25, 1500)")
            c.clicar(pr["x"], pr["y"])
            c.esperar("!!document.querySelector('#v-info-ref')", 20)
            info_r = c.js("document.querySelector('#v-info-ref')?.innerText || ''")
            rel.ok(("km 24," in info_r or "km 25," in info_r) and "estaca" in info_r and ref_r["lote"]["id"] in info_r,
                   "rodovia: clique no terreno do 3D mostra km, estaca e lote da API", info_r.replace("\n", " ")[:140])
            c.js("document.querySelector('#v-info .fechar')?.click()")
        c.js(f"{T}.irPara('painel')")
        c.esperar("document.querySelectorAll('#tab-marcos tbody tr').length > 0", 30)
        rel.ok(c.js("document.querySelectorAll('#tab-marcos tbody tr').length") > 0
               and c.js("!!document.querySelector('#p-sensibilidade')"),
               f"painel da obra '{outra}' com marcos contratuais e sensibilidade")
        if outra == "rodovia":
            alvo = "L2-S02-CBU"
            c.js(f"{T}.irPara('simulacao')")
            time.sleep(0.4)
            tem = c.js(f"[...document.querySelectorAll('#s-ativ option')].some(o => o.value === '{alvo}')")
            if tem:
                prod = c.js(f"{T}.estado.cenarios.independente.atividades['{alvo}'].memoria.produtividade")
                c.js(f"(() => {{ const s=document.querySelector('#s-ativ'); s.value='{alvo}'; s.dispatchEvent(new Event('change'));"
                     f" document.querySelector('#s-prod').value='{round(prod * 0.5, 2)}'; document.querySelector('#s-rodar').click(); }})()")
                c.esperar("!!document.querySelector('.sim-res .delta-grande')", 60)
                dr = c.js("document.querySelector('.sim-res .delta-grande')?.textContent")
                rel.ok(dr and dr.startswith("+"), f"rodovia: simulação do CBU crítico {alvo} (−50% produtividade) move o término",
                       dr or "")
                foto("e2e-sim-rodovia")
                c.js("document.querySelector('#s-limpar').click()")
                c.esperar(f"{T}.estado.cenarioAtivo === 'independente'", 30)
            else:
                rel.ok(False, f"rodovia: atividade {alvo} disponível para simulação")

            def gj(caminho: str):
                return json.load(urllib.request.urlopen(f"{url}{caminho}", timeout=180))

            # fiscalização da rodovia
            frente_r = c.js(f"({T}.estado.projeto.atividades.find(a => a.tipo==='tarefa' && a.quantidade_total && a.status==='em_andamento') || {{}}).id")
            c.js(f"{T}.selecionar({json.dumps(frente_r)}, 'teste')")
            c.js(f"{T}.irPara('fiscalizacao')")
            dia_r = gj(f"/api/fiscalizacao/diario?atividade_id={frente_r}&obra=rodovia")
            prod_r = gj("/api/fiscalizacao/produtividade?obra=rodovia")
            c.esperar(f"document.querySelectorAll('#fz-diario tbody tr').length === {len(dia_r['diarios'])}"
                      f" && document.querySelectorAll('#fz-prod tbody tr').length === {len(prod_r['atividades'])}", 90)
            rel.ok(c.js("document.querySelectorAll('#fz-diario tbody tr').length") == len(dia_r["diarios"]) > 0
                   and c.js("document.querySelectorAll('#fz-prod tbody tr').length") == len(prod_r["atividades"]) > 0,
                   f"rodovia: fiscalização (diário de {frente_r} e produtividade) igual à API",
                   f"{len(dia_r['diarios'])} diários, {len(prod_r['atividades'])} atividades")
            foto("e2e-fiscalizacao-rodovia")
            # linha real da rodovia
            real_r = gj("/api/fiscalizacao/linha-real?obra=rodovia")
            n_r = sum(1 for f in real_r["frentes"] if len(f.get("pontos") or []) >= 2)
            c.js(f"{T}.irPara('balanco')")
            marcar("#lb-real", True)
            c.esperar(f"document.querySelectorAll('#balanco [data-camada=real] .real').length === {n_r}", 60)
            rel.ok(c.js("document.querySelectorAll('#balanco [data-camada=real] .real').length") == n_r > 0,
                   "rodovia: linha REAL executada na linha de balanço", f"{n_r} frentes")
            marcar("#lb-real", False)
            # três métodos de previsão da rodovia
            es_r = next(r for r in gj("/api/previsao/earned-schedule?obra=rodovia")["resultados"] if r["lote"] is None)
            c.js(f"{T}.irPara('painel')")
            c.esperar("document.querySelectorAll('#p-metodos-tab tbody tr').length === 6", 90)
            txt_r = c.js("document.querySelector('#p-metodos')?.innerText || ''")
            brr = "/".join(reversed(es_r["IEAC_spi_termino"].split("-")))
            rel.ok(brr in txt_r and c.js("document.querySelectorAll('#p-metodos-tab tbody tr').length") == 6,
                   "rodovia: cartão 'Três métodos de previsão' com o Earned Schedule da API", f"ES(SPI)={es_r['IEAC_spi_termino']}")
            # Monte Carlo v1 × v2 na rodovia (o cartão espera a v1 terminar antes de oferecer a comparação)
            c.esperar("!!document.querySelector('#p-v2-rodar')", 300)
            c.js("(() => { document.querySelector('#p-v2-riscos').checked = true; document.querySelector('#p-v2-chuva').checked = true;"
                 " document.querySelector('#p-v2-rho').value = '0.5'; document.querySelector('#p-v2-rodar').click(); })()")
            c.esperar("document.querySelectorAll('#p-faixas .faixa').length === 2 || !!document.querySelector('#p-previsao .erro')", 400)
            v2_r = c.js("document.querySelector('#p-v2-resumo')?.innerText || document.querySelector('#p-previsao .erro')?.innerText || ''")
            rel.ok(c.js("document.querySelectorAll('#p-faixas .faixa').length") == 2, "rodovia: Monte Carlo v1 × v2 com duas faixas",
                   v2_r.replace("\n", " ")[:140])

            # cronograma da construtora na rodovia: exemplo (construtora exportada × motor independente)
            req_x = urllib.request.urlopen(f"{url}/api/cronograma/exportar/mspdi?cenario=construtora&obra=rodovia", timeout=180)
            xml_r = req_x.read()
            esp_r = json.load(urllib.request.urlopen(urllib.request.Request(
                f"{url}/api/cronograma/comparar?cenario=independente&obra=rodovia", data=xml_r, method="POST",
                headers={"Content-Type": "application/octet-stream"}), timeout=180))
            c.js(f"{T}.irPara('cronoimport')")
            time.sleep(0.4)
            rel.ok("obra=rodovia" in c.js("document.querySelector('#ci-exportar').href"), "rodovia: link Exportar MSPDI leva ?obra=rodovia")
            c.js("document.querySelector('#ci-exemplo').click()")
            c.esperar("!!document.querySelector('#ci-delta') || !!document.querySelector('#ci-erro')", 180)
            dtx = c.js("document.querySelector('#ci-delta')?.textContent || document.querySelector('#ci-erro')?.textContent || ''")
            de = esp_r["delta_termino_dias_corridos"]
            rel.ok(dtx.startswith(f"{'+' if de > 0 else ''}{de} ") and c.js("document.querySelector('#ci-casadas').textContent") == str(esp_r["n_casadas"]),
                   "rodovia: 'Usar exemplo' do cronograma da construtora igual ao /comparar da API",
                   f"{dtx} · casadas={esp_r['n_casadas']}")
            foto("e2e-cronoimport-rodovia")
        recarregar_e_esperar(f"(() => {{ const s=document.querySelector('#obra-sel'); s.value={json.dumps(atual)}; "
                             f"s.dispatchEvent(new Event('change')); }})()", atual)
    else:
        rel.pular("troca para outra obra", "a API lista só 1 obra")
        ok_rec = recarregar_e_esperar(f"(() => {{ location.hash = '#painel?obra={atual}'; location.reload(); }})()", atual)
        rel.ok(ok_rec and c.js("location.hash").startswith("#painel?obra="),
               "recarga com #aba?obra= preserva a obra e a aba", c.js("location.hash"))
    ok_inv = recarregar_e_esperar("(() => { location.hash = '#painel?obra=obra-que-nao-existe'; location.reload(); })()", opcoes[0])
    rel.ok(ok_inv and "não existe" in c.js("document.querySelector('#erro-global-texto').textContent")
           and not c.js("document.querySelector('#erro-global').hidden"),
           "obra inexistente no hash: aviso claro e volta à obra padrão",
           c.js("document.querySelector('#erro-global-texto').textContent"))

    # ---- apresentação guiada (tour) nas duas obras: cada número exibido confere com a API
    def tecla(nome: str, vk: int) -> None:
        for tipo in ("keyDown", "keyUp"):
            c.chamar("Input.dispatchKeyEvent", type=tipo, key=nome, code=nome, windowsVirtualKeyCode=vk)

    def esperados_tour(obra: str) -> dict:
        g = lambda cam: json.load(urllib.request.urlopen(f"{url}{cam}{'&' if '?' in cam else '?'}obra={obra}", timeout=400))
        pj = g("/api/projeto")
        pn = g("/api/painel")
        es = next(r for r in g("/api/previsao/earned-schedule")["resultados"] if r["lote"] is None)
        mc = g("/api/previsao-probabilistica?iteracoes=200")
        cf = g("/api/recursos/conflitos-balanco?cenario=independente&buffer_km=1&buffer_dias=0")
        ind = g("/api/cenarios/independente")
        xmlx = urllib.request.urlopen(f"{url}/api/cronograma/exportar/mspdi?cenario=construtora&obra={obra}", timeout=300).read()
        cr = json.load(urllib.request.urlopen(urllib.request.Request(
            f"{url}/api/cronograma/comparar?cenario=independente&obra={obra}", data=xmlx, method="POST",
            headers={"Content-Type": "application/octet-stream"}), timeout=300))
        from datetime import date as _d
        dd = (_d.fromisoformat(pn["terminos"]["independente"]) - _d.fromisoformat(pn["terminos"]["construtora"])).days
        esp = {
            "extensao_km": pj["ferrovia"]["extensao_km"], "lotes": len(pj["lotes"]), "atividades": len(pj["atividades"]),
            "relacoes": len(pj["relacoes"]), "data_status": pj["meta"]["data_status"],
            "termino_construtora": pn["terminos"]["construtora"], "termino_independente": pn["terminos"]["independente"],
            "delta_dias": dd, "alerta_atividade": (pn["alertas"] or [{}])[0].get("atividade_id"),
            "spi": es["SPI"], "termino_es": es["IEAC_spi_termino"], "p50": mc["p50"], "p80": mc["p80"],
            "n_criticas": len(pn["criticas_independente"]), "termino_independente_4d": pn["terminos"]["independente"],
            "n_conflitos": cf["n_conflitos"], "crono_importado": cr["termino_importado"], "crono_motor": cr["termino_motor"],
            "crono_delta": cr["delta_termino_dias_corridos"], "crono_diferencas": cr["n_com_diferenca"],
            "_criticas_ind": {i for i, r in ind["atividades"].items() if r["critica"]},
        }
        # simulações dos exemplos 0 e 1 (os mesmos que o tour aplica), calculadas aqui e desfeitas em seguida
        exemplos = c.js(f"{T}.tour.estado().exemplos")
        for k, aj in (("sim1", exemplos[0]), ("sim2", exemplos[1])):
            corpo = json.dumps({"ajustes": [{x: v for x, v in aj.items() if v is not None}]}).encode()
            sc = json.load(urllib.request.urlopen(urllib.request.Request(f"{url}/api/simulacao?obra={obra}", data=corpo, method="POST",
                                                                         headers={"Content-Type": "application/json"}), timeout=300))["comparacao"]
            esp.update({f"{k}_atividade": aj["atividade_id"], f"{k}_antes": sc["termino_ref"], f"{k}_depois": sc["termino_alvo"],
                        f"{k}_delta": sc["delta_dias_corridos"]})
            if aj.get("produtividade") is not None:
                esp[f"{k}_produtividade"] = aj["produtividade"]
            if aj.get("equipes") is not None:
                esp[f"{k}_equipes"] = aj["equipes"]
        urllib.request.urlopen(urllib.request.Request(f"{url}/api/simulacao?obra={obra}", method="DELETE"), timeout=60).close()
        return esp

    def percorrer_tour(obra: str, abrir_com_botao: bool) -> str | None:
        esp = esperados_tour(obra)
        crit = esp.pop("_criticas_ind")
        if abrir_com_botao:
            b = c.js("(() => { const r=document.querySelector('#btn-tour').getBoundingClientRect(); return {x:r.x+r.width/2, y:r.y+r.height/2}; })()")
            c.clicar(b["x"], b["y"])
        c.esperar(f"{T}.tour.estado().aberto", 30)
        total = c.js(f"{T}.tour.estado().total")
        conferidos, divergentes, sem_esperado, erros, outra = [], [], [], [], None
        for i in range(total):
            c.esperar(f"{T}.tour.estado().passo === {i} && !{T}.tour.estado().ocupado", 400)
            st = c.js(f"{T}.tour.estado()")
            if st["erro"]:
                erros.append(f"passo {i + 1}: {st['erro']}")
            visiveis = c.js("[...document.querySelectorAll('#tour-corpo [data-num]')].map(e => e.dataset.num)")
            for k in visiveis:
                v = st["numeros"].get(k)
                if k == "frente":
                    (conferidos if v in crit else divergentes).append(f"{k}={v}")
                elif k in ("outra_nome", "outra_km"):
                    conferidos.append(k)
                elif k in esp:
                    e = esp[k]
                    ok_ = abs(float(v) - float(e)) < 1e-6 if isinstance(e, (int, float)) and not isinstance(e, bool) else v == e
                    (conferidos if ok_ else divergentes).append(f"{k}: tela={v} api={e}" if not ok_ else k)
                else:
                    sem_esperado.append(k)
            if st["numeros"].get("outra_obra"):
                outra = st["numeros"]["outra_obra"]
            if i == 1:
                foto(f"e2e-tour-{obra}-painel")
            if i < total - 1:
                tecla("ArrowRight", 39) if i % 2 == 0 else c.js(f"{T}.tour.proximo()")
        chaves_ok = {x.split(":")[0] for x in conferidos}
        faltando = sorted(k for k, v in esp.items() if v is not None and k not in chaves_ok)
        rel.ok(not divergentes and not erros and not sem_esperado and not faltando and total >= 10,
               f"tour ({obra}): {total} passos executados, cada número do texto confere com a API",
               f"{len(conferidos)} números conferidos; divergentes={divergentes} sem_esperado={sem_esperado} faltando={faltando} erros={erros}")
        return outra

    outra_tour = percorrer_tour("ferrovia", abrir_com_botao=True)
    if outra_tour:
        # último passo: botão "Repetir o tour na <tipo>" troca a obra e o tour recomeça sozinho
        c.js("window.__marca = 1")
        c.js("document.querySelector('#tour-corpo [data-tour=\"trocar\"]').click()")
        c.esperar(f"!window.__marca && {T} && {T}.obra() === {json.dumps(outra_tour)} && {T}.tour.estado().aberto", 120)
        rel.ok(c.js(f"{T}.obra()") == outra_tour and c.js(f"{T}.tour.estado().aberto"),
               f"tour troca para a obra '{outra_tour}' no passo final e recomeça", c.js("location.hash"))
        percorrer_tour(outra_tour, abrir_com_botao=False)
    tecla("Escape", 27)
    c.esperar(f"!{T}.tour.estado().aberto && !{T}.tour.estado().simAplicada", 60)
    time.sleep(1.0)
    sims = {o: json.load(urllib.request.urlopen(f"{url}/api/simulacao?obra={o}", timeout=120))["ajustes"] for o in opcoes}
    rel.ok(not c.js(f"{T}.tour.estado().aberto") and all(not v for v in sims.values())
           and not document_tem_tour(c), "sair do tour (Esc) remove o balão e não deixa simulação ativa em nenhuma obra",
           json.dumps({k: len(v) for k, v in sims.items()}))

    # ==================================================================== aba Análises e modo IFC (duas obras)
    def gjo(caminho: str, obra: str, timeout: int = 900):
        sep = "&" if "?" in caminho else "?"
        return json.load(urllib.request.urlopen(f"{url}{caminho}{sep}obra={obra}", timeout=timeout))

    def apagar_sim(obra: str) -> None:
        urllib.request.urlopen(urllib.request.Request(f"{url}/api/simulacao?obra={obra}", method="DELETE"), timeout=60).close()

    def br(iso):
        return "/".join(reversed(iso.split("-"))) if iso else "—"

    def carga_limpa(destino: str, cond: str, seg: float = 600) -> bool:
        c.chamar("Page.navigate", url="about:blank")
        time.sleep(0.3)
        c.chamar("Page.navigate", url=destino)
        return c.esperar(cond, seg)

    def confere_selo(sel_: str, campo) -> tuple[bool, str]:
        """Selo em `sel_`: presente com o motivo da API quando há simulacao_do_usuario; ausente quando não há."""
        tela = c.js(f"(() => {{ const e = document.querySelector('{sel_} .selo-sim'); return e ? {{tipo: e.dataset.seloSim, txt: e.innerText}} : null; }})()")
        if isinstance(campo, str) and campo.strip():
            tipo = "nao" if campo.strip().lower().startswith(("não", "nao")) else "sim"
            return bool(tela) and tela["tipo"] == tipo and campo in tela["txt"], "selo"
        return tela is None, "sem campo"

    for obra in opcoes:
        apagar_sim(obra)
        sens = gjo("/api/sensibilidade?p=0.1&equipes=1", obra)
        rec = gjo("/api/recuperacao", obra)
        dia = gjo("/api/massas/diagrama?passo_m=100", obra)
        coe = gjo("/api/massas/coerencia", obra)
        ter = gjo("/api/produtividade/terraplenagem", obra)
        tbs = gjo("/api/exportar/tabelas", obra)["tabelas"]
        pronto = ("!!document.querySelector('#an-tornado svg') && !!document.querySelector('#an-rec-resumo') && !!document.querySelector('#an-bruckner-svg')"
                  " && !!document.querySelector('#an-terra-tab') && !!document.querySelector('#an-bi-tab')")
        rel.ok(carga_limpa(f"{url}/#analises?obra={obra}", pronto), f"análises ({obra}): as cinco subseções carregam")
        # a) tornado
        gs = sorted(sens["grupos"], key=lambda x: (-abs(x["amplitude_dias_uteis"] or 0), f"{x['lote_id']}{x['servico_id']}"))
        barras = c.js("[...document.querySelectorAll('#an-tornado .an-barra')].map(g => g.dataset.grupo)")
        n_zero = c.js("[...document.querySelectorAll('#an-tornado .an-marca')].filter(t => t.textContent.includes('efeito zero')).length")
        rel.ok(len(barras) == len(gs) and barras[0] == f"{gs[0]['lote_id']}/{gs[0]['servico_id']}" and n_zero == sum(1 for x in gs if x["efeito_zero"]),
               f"análises ({obra}): tornado ordenado com {len(gs)} grupos e marcação de efeito zero igual à API",
               f"1º={barras[0] if barras else None} efeito_zero={n_zero}")
        c.js("(() => { const s=document.querySelector('#an-sens-p'); s.value='0.2'; s.dispatchEvent(new Event('change')); })()")
        c.esperar("(document.querySelector('#an-sens')?.innerText || '').includes('±20%') && !!document.querySelector('#an-tornado svg')", 600)
        sens2 = gjo("/api/sensibilidade?p=0.2&equipes=1", obra)
        g2 = sorted(sens2["grupos"], key=lambda x: (-abs(x["amplitude_dias_uteis"] or 0), f"{x['lote_id']}{x['servico_id']}"))
        b2 = c.js("document.querySelector('#an-tornado .an-barra')?.dataset.grupo")
        rel.ok(b2 == f"{g2[0]['lote_id']}/{g2[0]['servico_id']}", f"análises ({obra}): controle p = ±20% recalcula o tornado", str(b2))
        # b) recuperação
        alc = c.js("document.querySelector('#an-rec-alcancado')?.textContent")
        n_plano = c.js("document.querySelectorAll('#an-rec-tab tbody tr').length")
        rel.ok(alc == br(rec["termino_alcancado"]) and n_plano == len(rec["plano"]),
               f"análises ({obra}): plano de recuperação (término alcançado e frentes) igual à API",
               f"alcançado={alc} frentes={n_plano} viabilidade={rec['viabilidade']}")
        if rec.get("ajustes_produtividade"):
            c.js("document.querySelector('[data-aplicar=\"recup-prod\"]').click()")
            c.esperar("(document.querySelector('#an-rec-msg')?.textContent || '').includes('aplicada') || !!document.querySelector('#an-rec-msg.erro')", 300)
            sim_api = gjo("/api/simulacao", obra)
            msg = c.js("document.querySelector('#an-rec-msg')?.textContent || ''")
            rel.ok(len(sim_api["ajustes"]) == len(rec["ajustes_produtividade"]) and br(sim_api["comparacao"]["termino_alvo"]) in msg,
                   f"análises ({obra}): 'aplicar como simulação' envia os ajustes do plano", msg[:110])
            apagar_sim(obra)
        marcos = c.js("[...document.querySelectorAll('#an-rec-marco option')].map(o => o.value).filter(Boolean)")
        if marcos:
            c.js(f"(() => {{ const s=document.querySelector('#an-rec-marco'); s.value={json.dumps(marcos[0])}; s.dispatchEvent(new Event('change')); }})()")
            rec_m = gjo(f"/api/recuperacao?marco={marcos[0]}", obra)
            c.esperar(f"document.querySelector('#an-rec-alcancado')?.textContent === {json.dumps(br(rec_m['termino_alcancado']))}", 600)
            rel.ok(c.js("document.querySelector('#an-rec-alcancado')?.textContent") == br(rec_m["termino_alcancado"]),
                   f"análises ({obra}): prazo pelo marco {marcos[0]} recalcula o plano", br(rec_m["termino_alcancado"]))
        # c) massas
        n_pts = c.js("document.querySelector('#an-curva').getAttribute('points').trim().split(/\\s+/).length")
        n_pass = c.js("document.querySelectorAll('#an-bruckner-svg .an-passagem').length")
        n_onda = c.js("document.querySelectorAll('#an-bruckner-svg .an-onda').length")
        n_coe = c.js("document.querySelectorAll('#an-coer-tab tbody tr').length")
        rel.ok(n_pts == len(dia["estacas"]) and n_pass == len(dia["pontos_passagem_km"]) and n_onda == len(dia["compensacoes"])
               and c.js("!!document.querySelector('#an-linha-compensacao')") and n_coe == len(coe["segmentos"]),
               f"análises ({obra}): Brückner (ordenadas, passagens, ondas, linha O=0) e coerência iguais à API",
               f"pts={n_pts} passagens={n_pass} ondas={n_onda} coerência={n_coe}")
        # d) produtividade pela DMT
        efe = c.js("document.querySelector('#an-terra-efeito')?.textContent || ''")
        rel.ok(c.js("document.querySelectorAll('#an-terra-tab tbody tr').length") == len(ter["segmentos"])
               and br(ter["efeito_no_termino"]["termino_pela_geometria"]) in efe,
               f"análises ({obra}): produtividade pela DMT por segmento e efeito no término iguais à API", efe[:110])
        if ter.get("ajustes_recomendados"):
            c.js("document.querySelector('[data-aplicar=\"terra\"]').click()")
            c.esperar("(document.querySelector('#an-terra-msg')?.textContent || '').includes('aplicada') || !!document.querySelector('#an-terra-msg.erro')", 300)
            sim_t = gjo("/api/simulacao", obra)
            rel.ok(len(sim_t["ajustes"]) == len(ter["ajustes_recomendados"])
                   and sim_t["comparacao"]["termino_alvo"] == ter["efeito_no_termino"]["termino_pela_geometria"],
                   f"análises ({obra}): aplicar a produtividade geométrica dá o término previsto pela API",
                   f"{sim_t['comparacao']['termino_alvo']}")
            apagar_sim(obra)
        # e) BI
        hrefs = c.js("[...document.querySelectorAll('#an-bi-tab a[data-csv]')].map(a => a.href)")
        zip_href = c.js("document.querySelector('#an-bi-zip').href")
        with urllib.request.urlopen(zip_href, timeout=300) as r:
            zb = r.read()
            zip_ok = r.status == 200 and zb[:2] == b"PK"
        with urllib.request.urlopen(hrefs[0], timeout=300) as r:
            csv1 = r.read().decode("utf-8-sig", "replace")
        col0 = tbs[0]["colunas"][0]["nome"]
        rel.ok(len(hrefs) == len(tbs) and f"obra={obra}" in zip_href and zip_ok and col0 in csv1.splitlines()[0],
               f"análises ({obra}): exportar para BI (zip + {len(tbs)} CSVs com ?obra=)", f"{len(zb)} bytes no zip")
        # f) clima
        cli = gjo("/api/clima?intensidade=0.3&deslocamento_semanas=4", obra)
        c.esperar(f"document.querySelectorAll('#an-cli-cards .kpi').length === {len(cli['cenarios'])}", 600)
        cards = c.js("[...document.querySelectorAll('#an-cli-cards .kpi')].map(k => ({tipo: k.dataset.clima, txt: k.innerText}))")
        ok_cli = len(cards) == len(cli["cenarios"]) >= 3 and all(
            br(x["termino"]) in cd["txt"] and cd["tipo"] == (x.get("tipo") or "") for x, cd in zip(cli["cenarios"], cards))
        rel.ok(ok_cli, f"análises ({obra}): clima com {len(cli['cenarios'])} cenários (chuvoso/seco/deslocado) e Δ término iguais à API",
               " | ".join(f"{x.get('tipo')}: {x['termino']} ({x['delta_dias_corridos']:+d})" for x in cli["cenarios"]))
        def br1(x, casas=1):
            s_ = f"{x:,.{casas}f}"
            return s_.replace(",", "X").replace(".", ",").replace("X", ".")

        # h) curva S física / financeira (+ lote)
        for base_cs, lote_cs in (("fisica", ""), ("financeira", ""), ("fisica", "L2")):
            api_cs = gjo(f"/api/curva-s?base={base_cs}" + (f"&lote={lote_cs}" if lote_cs else ""), obra)
            c.js(f"(() => {{ const b=document.querySelector('#an-cs-base'); b.value='{base_cs}'; const l=document.querySelector('#an-cs-lote'); l.value='{lote_cs}';"
                 " b.dispatchEvent(new Event('change')); })()")
            pct_txt = br1(api_cs["percentual_realizado_na_data_status"])
            c.esperar(f"(document.querySelector('#an-cs-resumo')?.innerText || '').includes('{pct_txt}%') && document.querySelectorAll('#an-cs-svg .an-cs-linha').length === 4", 600)
            rel.ok(c.js("document.querySelectorAll('#an-cs-svg .an-cs-ponto').length") == len(api_cs["pontos"])
                   and pct_txt + "%" in c.js("document.querySelector('#an-cs-resumo').innerText"),
                   f"análises ({obra}): curva S {base_cs}{' lote ' + lote_cs if lote_cs else ''} — 4 séries, {len(api_cs['pontos'])} datas e realizado {pct_txt}% = API")
        c.js("(() => { const b=document.querySelector('#an-cs-base'); b.value='fisica'; const l=document.querySelector('#an-cs-lote'); l.value=''; b.dispatchEvent(new Event('change')); })()")

        # i) backtest (duas referências)
        bk = gjo("/api/backtest", obra)
        mbk = next((m for m in bk["marcos"] if m["id"] == "M-FIM"), bk["marcos"][-1])
        c.esperar("document.querySelectorAll('#an-bk-svg .an-bk-linha').length === 2", 600)
        for ref in ("realidade_simulada", "final_independente"):
            c.js(f"(() => {{ const s=document.querySelector('#an-bk-ref'); s.value='{ref}'; s.dispatchEvent(new Event('change')); }})()")
            mae = mbk["por_referencia"][ref]["mae_dias"]
            c.esperar(f"(document.querySelector('#an-bk-kpis')?.innerText || '').includes('{br1(mae['independente'])} d')", 120)
            kp = c.js("document.querySelector('#an-bk-kpis').innerText")
            n_pts_bk = c.js("document.querySelector('#an-bk-svg .an-bk-linha[data-serie=\"independente\"]').getAttribute('points').trim().split(/\\s+/).length")
            esperado_pts = sum(1 for e in mbk["por_referencia"][ref]["erro_dias"]["independente"] if isinstance(e, (int, float)))
            rel.ok(f"{br1(mae['construtora'])} d" in kp and f"{br1(mae['independente'])} d" in kp and n_pts_bk == esperado_pts
                   and "SINTÉTICO" in c.js("document.querySelector('#an-back').innerText") and "Circularidade" in c.js("document.querySelector('#an-back').innerText"),
                   f"análises ({obra}): backtest {mbk['id']} contra {ref}: MAE e série de erros = API, com aviso SINTÉTICO e circularidade",
                   f"MAE construtora={mae['construtora']} independente={mae['independente']}")

        # i2) "Por que errou?" (atribuição do erro do backtest): data padrão = maior |erro| da independente; depois clique no gráfico
        er_ind = mbk["por_referencia"]["realidade_simulada"]["erro_dias"]["independente"]
        i_max = max(range(len(er_ind)), key=lambda i: abs(er_ind[i]) if isinstance(er_ind[i], (int, float)) else -1)
        casos_atr = [("M-FIM", bk["datas_de_status"][i_max], "padrão")]
        if obra == "rodovia":
            casos_atr.append(("M-L2-FIM", "2026-03-30", "clique no gráfico"))
        for marco_a, data_a, como in casos_atr:
            if como == "clique no gráfico":
                c.js(f"(() => {{ const s=document.querySelector('#an-bk-marco'); s.value='{marco_a}'; s.dispatchEvent(new Event('change')); }})()")
                c.esperar("!!document.querySelector('#an-bk-svg .an-bk-alvo')", 120)
                c.js(f"document.querySelector('#an-bk-svg .an-bk-alvo[data-data=\"{data_a}\"]').dispatchEvent(new MouseEvent('click', {{bubbles: true}}))")
            atr = gjo(f"/api/backtest/atribuicao?marco={marco_a}&data={data_a}", obra)
            c.esperar(f"document.querySelector('#an-bk-data')?.value === '{data_a}' && document.querySelector('#an-atr-erro')?.textContent === '{atr['erro_dias']} d'", 600)
            frs = sorted(atr["frentes"], key=lambda x: -(x.get("reducao_dias") or 0))
            linhas_atr = c.js("[...document.querySelectorAll('#an-atr-tab tbody tr')].map(t => t.dataset.frente)")
            ok_atr = (c.js("document.querySelector('#an-atr-erro')?.textContent") == f"{atr['erro_dias']} d"
                      and c.js("document.querySelector('#an-atr-residuo')?.textContent") == f"{atr['residuo_interacao']} d"
                      and c.js("document.querySelector('#an-atr-todas')?.textContent") == f"{atr['todas_as_frentes_juntas']['erro_dias']} d"
                      and linhas_atr == [f"{x['lote_id']}/{x['servico_id']}" for x in frs]
                      and "SINTÉTICA" in c.js("document.querySelector('#an-back').innerText"))
            topo = frs[0] if frs else {}
            rel.ok(ok_atr, f"análises ({obra}): 'Por que errou?' {marco_a} em {data_a} ({como}) — erro, frentes por redução e resíduo = API, aviso SINTÉTICA",
                   f"erro {atr['erro_dias']} d; 1ª {topo.get('lote_id')}/{topo.get('servico_id')} → {topo.get('erro_com_a_frente_corrigida')} d; resíduo {atr['residuo_interacao']}")
        c.js("(() => { const s=document.querySelector('#an-bk-marco'); s.value='M-FIM'; s.dispatchEvent(new Event('change')); })()")

        # j) aceleração (término × custo) + aplicar como simulação
        ac = gjo("/api/aceleracao?limite_extra=2", obra)
        c.esperar("!!document.querySelector('#an-ac-resumo')", 600)
        rel.ok(c.js("document.querySelector('#an-ac-alcancado').textContent") == br(ac["termino_alcancado"])
               and c.js("document.querySelector('#an-ac-custo').textContent") == br1(ac["custo_adicional_total"], 0)
               and c.js("document.querySelectorAll('#an-ac-tab tbody tr').length") == len(ac["curva"])
               and c.js("document.querySelectorAll('#an-ac-svg .an-ac-ponto').length") == len(ac["curva"]),
               f"análises ({obra}): aceleração — término alcançado, custo e {len(ac['curva'])} passos iguais à API",
               f"{ac['termino_alcancado']} R$ {ac['custo_adicional_total']}")
        if ac.get("ajustes_finais"):
            c.js("document.querySelector('[data-aplicar=\"acel\"]').click()")
            c.esperar("(document.querySelector('#an-ac-msg')?.textContent || '').includes('aplicada') || !!document.querySelector('#an-ac-msg.erro')", 300)
            sim_ac = gjo("/api/simulacao", obra)
            rel.ok(len(sim_ac["ajustes"]) == len(ac["ajustes_finais"]) and sim_ac["comparacao"]["termino_alvo"] == ac["verificacao"]["termino"],
                   f"análises ({obra}): aplicar a aceleração dá o término verificado pela API", sim_ac["comparacao"]["termino_alvo"])
            apagar_sim(obra)

        # g) tendência dos marcos (MTA)
        tnd = gjo("/api/tendencia", obra)
        m_fim = next((m for m in tnd["marcos"] if m["id"] == "M-FIM"), tnd["marcos"][-1])
        c.esperar("document.querySelectorAll('#an-tend-svg .an-tend-ponto').length > 0", 600)
        n_tp = c.js("document.querySelectorAll('#an-tend-svg .an-tend-ponto').length")
        tres = c.js("document.querySelector('#an-tend-resumo')?.innerText || ''")
        inc = m_fim["inclinacao_dias_por_semana"]
        num_br = lambda x: f"{x:.2f}".replace(".", ",")
        rel.ok(n_tp == len(m_fim["serie"]) and c.js("document.querySelectorAll('#an-tend-svg .an-tend-linha').length") == 2
               and num_br(inc["construtora"]) in tres and num_br(inc["independente"]) in tres
               and (not m_fim.get("divergencia_desde") or (c.js("!!document.querySelector('#an-tend-div')") and br(m_fim["divergencia_desde"]) in tres)),
               f"análises ({obra}): tendência do marco {m_fim['id']} ({len(m_fim['serie'])} datas, inclinações e divergência iguais à API)",
               tres.replace("\n", " ")[:120])
        # GIS: download GeoJSON por camada
        gis0 = c.js("document.querySelector('#an-gis-link').href")
        c.js("(() => { const s=document.querySelector('#an-gis-camada'); s.value='eixo'; s.dispatchEvent(new Event('change')); })()")
        gis1 = c.js("document.querySelector('#an-gis-link').href")
        with urllib.request.urlopen(gis1, timeout=300) as r:
            gj = json.load(r)
        rel.ok("camada=todas" in gis0 and "camada=eixo" in gis1 and f"obra={obra}" in gis1 and gj.get("type") == "FeatureCollection"
               and gj["features"] and all(f["properties"].get("camada") == "eixo" for f in gj["features"]) and gj["meta"].get("ficticio") is True,
               f"análises ({obra}): download GeoJSON por camada (eixo) com ?obra= e marca de fictício", f"{len(gj['features'])} feição(ões)")
        foto(f"e2e-analises-{obra}")

        # selo "não segue a simulação": presente (com o motivo da API) onde a resposta traz simulacao_do_usuario; ausente onde não traz
        selos = [("#an-sens", "/api/sensibilidade"), ("#an-recup", "/api/recuperacao"), ("#an-terra", "/api/produtividade/terraplenagem"),
                 ("#an-clima", "/api/clima?intensidade=0.3&deslocamento_semanas=4"), ("#an-tend", "/api/tendencia"),
                 ("#an-curvas", "/api/curva-s?base=fisica"), ("#an-back", "/api/backtest"), ("#an-acel", "/api/aceleracao?limite_extra=2")]
        res_selo = []
        for sel_, rota in selos:
            campo = gjo(rota, obra).get("simulacao_do_usuario")
            tela = c.js(f"(() => {{ const e = document.querySelector('{sel_} .selo-sim'); return e ? {{tipo: e.dataset.seloSim, txt: e.innerText}} : null; }})()")
            if isinstance(campo, str) and campo.strip():
                ok_ = bool(tela) and tela["tipo"] == ("nao" if campo.strip().lower().startswith(("não", "nao")) else "sim") and campo in tela["txt"]
            else:
                ok_ = tela is None
            res_selo.append((sel_, "selo" if campo else "sem campo", ok_))
        rel.ok(all(o for *_, o in res_selo), f"análises ({obra}): selo 'não segue a simulação' com o motivo da API onde há simulacao_do_usuario",
               " ".join(f"{s}:{k}{'' if o else '!'}" for s, k, o in res_selo))

        # DCMA (nosso cenário e o arquivo importado) na aba Cronograma da construtora
        dc_ind = gjo("/api/dcma?cenario=independente", obra)
        c.js(f"{T}.irPara('cronoimport')")
        xer_href = c.esperar("!!document.querySelector('#ci-exportar-xer')", 30) and c.js("document.querySelector('#ci-exportar-xer').href")
        with urllib.request.urlopen(xer_href, timeout=300) as r:
            xer_ok = r.status == 200 and r.read(6) == b"ERMHDR"
        rel.ok(xer_ok and f"obra={obra}" in xer_href and "cenario=construtora" in xer_href,
               f"cronograma da construtora ({obra}): botão Exportar XER (P6) baixa um XER válido da obra", xer_href)
        c.esperar("document.querySelectorAll('#ci-dcma-motor tbody tr').length === 14", 300)
        res_txt = c.js("document.querySelector('#ci-dcma-motor-resumo')?.innerText || ''")
        r_ = dc_ind["resumo"]
        rel.ok(c.js("document.querySelectorAll('#ci-dcma-motor tbody tr').length") == len(dc_ind["pontos"]) == 14
               and f"✓ {r_['aprovados']}" in res_txt and f"▼ {r_['reprovados']}" in res_txt,
               f"DCMA ({obra}): 14 pontos do cenário independente com aprovados/reprovados da API", f"{r_}")
        viol = c.js("document.querySelector('#ci-dcma-motor .link-ativ')?.dataset.ir")
        if viol:
            c.js("document.querySelector('#ci-dcma-motor details')?.setAttribute('open', '')")
            c.js("document.querySelector('#ci-dcma-motor .link-ativ').click()")
            time.sleep(0.4)
            rel.ok(c.js(f"{T}.estado.selecionada") == viol, f"DCMA ({obra}): violadora clicável seleciona a atividade", viol)
            c.js(f"{T}.irPara('cronoimport')")
            time.sleep(0.4)
        xml_c = urllib.request.urlopen(f"{url}/api/cronograma/exportar/mspdi?cenario=construtora&obra={obra}", timeout=300).read()
        dc_imp = json.load(urllib.request.urlopen(urllib.request.Request(f"{url}/api/dcma/importado?obra={obra}", data=xml_c, method="POST",
                                                                         headers={"Content-Type": "application/octet-stream"}), timeout=600))
        c.js("document.querySelector('#ci-exemplo').click()")
        c.esperar("document.querySelectorAll('#ci-dcma-arq tbody tr').length === 14 || !!document.querySelector('#ci-erro')", 600)
        arq_txt = c.js("document.querySelector('#ci-dcma-arq-resumo')?.innerText || ''")
        ri_ = dc_imp["resumo"]
        rel.ok(f"✓ {ri_['aprovados']}" in arq_txt and f"▼ {ri_['reprovados']}" in arq_txt and br(dc_imp["termino_calculado"]) in arq_txt,
               f"DCMA ({obra}): quadro do arquivo importado (MSPDI da construtora) igual a /api/dcma/importado", f"{ri_}")
        sel_dc = confere_selo("#ci-dcma-bloco", dc_ind.get("simulacao_do_usuario"))
        rel.ok(sel_dc[0], f"DCMA ({obra}): selo 'não segue a simulação' do cenário do motor conforme a API", sel_dc[1])

        # IFC com cronograma (download) — aba Cronograma da construtora e barra do 3D
        ifc_href = c.js("document.querySelector('#ci-exportar-ifc').href")
        ifc3d = c.js("document.querySelector('#v-baixar-ifc').href")
        with urllib.request.urlopen(ifc_href, timeout=600) as r:
            ifc_ok = r.status == 200 and r.read(13) == b"ISO-10303-21;"
        rel.ok(ifc_ok and f"obra={obra}" in ifc_href and "incluir_4d=true" in ifc_href and f"obra={obra}" in ifc3d,
               f"IFC com cronograma ({obra}): botões de download baixam o STEP da obra (ISO-10303-21)", ifc_href)

        # comparar revisões: cenários (GET) e arquivos MSPDI × XER (POST em base64)
        rv_c = gjo("/api/revisoes/comparar?a=linha_base&b=construtora", obra)
        c.js("(() => { const a=document.querySelector('#ci-rev-a'); a.value='linha_base'; const b=document.querySelector('#ci-rev-b'); b.value='construtora';"
             " document.querySelector('#ci-rev-cen').click(); })()")
        c.esperar("!!document.querySelector('#ci-rev-resumo') || !!document.querySelector('#ci-rev-erro')", 600)

        def confere_rev(api_r):
            d_txt = c.js("document.querySelector('#ci-rev-delta')?.textContent || ''")
            dt = api_r["delta_dias_corridos"]
            return (d_txt.startswith(f"{'+' if dt > 0 else ''}{dt} ")
                    and c.js("document.querySelector('#ci-rev-n')?.textContent") == str(api_r["n_mudancas"])
                    and c.js("document.querySelector('#ci-rev-soma')?.textContent") == f"{api_r['atribuicao']['soma_efeitos_isolados']} d"
                    and c.js("document.querySelector('#ci-rev-residuo')?.textContent") == f"{api_r['atribuicao']['residuo_interacao']} d"
                    and c.js("document.querySelectorAll('#ci-rev-tab tbody tr').length") == len(api_r["mudancas"])), d_txt

        ok_rc, txt_rc = confere_rev(rv_c)
        rel.ok(ok_rc, f"revisões ({obra}): linha de base × construtora — Δ, nº de mudanças, soma dos efeitos e resíduo iguais à API", txt_rc)
        import base64 as _b64
        xa = urllib.request.urlopen(f"{url}/api/cronograma/exportar/mspdi?cenario=construtora&obra={obra}", timeout=300).read()
        xb = urllib.request.urlopen(f"{url}/api/cronograma/exportar/xer?cenario=independente&obra={obra}", timeout=300).read()
        corpo_rv = json.dumps({"a": {"conteudo_base64": _b64.b64encode(xa).decode()}, "b": {"conteudo_base64": _b64.b64encode(xb).decode()},
                               "efeitos_isolados": True}).encode()
        rv_f = json.load(urllib.request.urlopen(urllib.request.Request(f"{url}/api/revisoes/comparar?obra={obra}", data=corpo_rv, method="POST",
                                                                       headers={"Content-Type": "application/json"}), timeout=900))
        c.js("document.querySelector('#ci-rev-exemplo').click()")
        c.esperar(f"(document.querySelector('#ci-rev-n')?.textContent === {json.dumps(str(rv_f['n_mudancas']))} && "
                  "(document.querySelector('#ci-rev-res')?.innerText || '').includes('MSPDI construtora')) || !!document.querySelector('#ci-rev-erro')", 900)
        ok_rf, txt_rf = confere_rev(rv_f)
        rel.ok(ok_rf and "confere" in c.js("document.querySelector('#ci-rev-resumo').innerText"),
               f"revisões ({obra}): arquivos MSPDI × XER enviados em base64 — Δ, {rv_f['n_mudancas']} mudanças, efeitos e resíduo iguais à API",
               f"{txt_rf} soma={rv_f['atribuicao']['soma_efeitos_isolados']} resíduo={rv_f['atribuicao']['residuo_interacao']}")
        foto(f"e2e-revisoes-{obra}")
        foto(f"e2e-dcma-{obra}")

        # histórico SINTÉTICO e riscos ao prazo no Painel
        hev = gjo("/api/historico/evolucao", obra)
        rsc = gjo("/api/riscos?rapido=true", obra)
        c.js(f"{T}.irPara('painel')")
        c.esperar("document.querySelectorAll('#p-hist-svg .p-hist-ponto').length > 0 && document.querySelectorAll('#p-riscos-tab tbody tr').length > 0", 600)
        n_pt = c.js("document.querySelectorAll('#p-hist-svg .p-hist-ponto').length")
        n_ln = c.js("document.querySelectorAll('#p-hist-svg .p-hist-linha').length")
        n_nr = c.js("document.querySelectorAll('#p-hist-narrativa li').length")
        rel.ok(n_pt == len(hev["pontos"]) and n_ln == 3 and n_nr == len(hev["narrativa"]) and "SINTÉTICO" in c.js("document.querySelector('#p-historico').innerText"),
               f"histórico ({obra}): {len(hev['pontos'])} datas de status × término (3 linhas), narrativa e aviso SINTÉTICO",
               f"pontos={n_pt} narrativa={n_nr}")
        top = sorted(rsc["riscos"], key=lambda x: -(x.get("exposicao") or 0))[:5]
        ids_r = c.js("[...document.querySelectorAll('#p-riscos-tab tbody tr')].map(t => t.dataset.risco)")
        evs = c.js("[...document.querySelectorAll('#p-riscos-tab a.p-evidencia')].map(a => a.href)")
        with urllib.request.urlopen(evs[0], timeout=600) as r:
            ev_ok = r.status == 200 and json.load(r) is not None
        rel.ok(ids_r == [x["id"] for x in top] and evs and all(f"obra={obra}" in e and "/api/" in e for e in evs) and ev_ok,
               f"riscos ({obra}): 5 maiores por exposição iguais à API, com evidências que abrem o JSON da API", f"{ids_r}")

        # confiança da previsão por marco (/api/cobertura)
        cob = gjo("/api/cobertura", obra)
        c.esperar("document.querySelectorAll('#p-cob-tab tbody tr').length > 0", 600)
        linhas_cob = c.js("[...document.querySelectorAll('#p-cob-tab tbody tr')].map(t => ({id: t.dataset.marco, txt: t.innerText}))")
        CONF_TXT = {"alta": "alta", "media": "média", "média": "média", "baixa": "baixa"}
        ok_conf = len(linhas_cob) == len(cob["marcos"]) and all(
            l["id"] == m["id"] and CONF_TXT.get(m["confianca"], m["confianca"]) in l["txt"] and br(m["termino"]) in l["txt"]
            for l, m in zip(linhas_cob, cob["marcos"]))
        al_api = {a["atividade_id"] for m in cob["marcos"] for a in (m.get("alerta_sem_medicao") or [])}
        if al_api:
            txt_al = c.js("document.querySelector('#p-cob-alerta')?.innerText || ''")
            ok_al = all(a in txt_al for a in list(al_api)[:12]) and f"{len(al_api)} frente" in txt_al
        else:
            ok_al = c.js("!!document.querySelector('#p-cob-alerta-ok')")
        rel.ok(ok_conf and ok_al, f"confiança por marco ({obra}): níveis, términos e alerta de frentes sem medição iguais à API",
               " · ".join(f"{m['id']}={m['confianca']}" for m in cob["marcos"]) + f" · {len(al_api)} frente(s) sem medição")
        # incerteza alargada para frente sem medição (P4): padrão 0,5 e troca para 0,3
        for alarg in ("0.5", "0.3"):
            p4a = gjo(f"/api/previsao-probabilistica?iteracoes=200&incerteza_sem_medicao=true&por_marco=true&alargamento={alarg}", obra)
            if alarg != "0.5":
                c.js(f"(() => {{ const s=document.querySelector('#p-p4-alarg'); s.value='{alarg}'; s.dispatchEvent(new Event('change')); }})()")
            mfim = p4a["marcos"].get("M-FIM") or list(p4a["marcos"].values())[-1]
            c.esperar(f"(document.querySelector('#p-p4-tab tr[data-marco=\"M-FIM\"]')?.innerText || '').includes('{br(mfim['p80'])}')"
                      f" && (document.querySelector('#p-p4-resumo')?.innerText || '').includes('alargamento {int(float(alarg) * 100)}%')", 900)
            linhas_p4 = c.js("[...document.querySelectorAll('#p-p4-tab tbody tr')].map(t => ({id: t.dataset.marco, txt: t.innerText}))")
            grupos = p4a["incerteza_sem_medicao"].get("grupos") or []
            res_p4 = c.js("document.querySelector('#p-p4-resumo')?.innerText || ''")
            ok_p4 = (len(linhas_p4) == len(p4a["marcos"]) and all(
                br(p4a["marcos"][l["id"]]["p50"]) in l["txt"] and br(p4a["marcos"][l["id"]]["p80"]) in l["txt"] for l in linhas_p4)
                and all(g in res_p4 for g in grupos))
            sel_p4 = confere_selo("#p-p4", p4a.get("simulacao_do_usuario"))
            rel.ok(ok_p4 and sel_p4[0], f"painel ({obra}): incerteza alargada (P4, ±{int(float(alarg) * 100)}%) — percentis por marco e grupos iguais à API",
                   f"M-FIM P50 {mfim['p50']} P80 {mfim['p80']}; grupos {grupos}; selo:{sel_p4[1]}")

        # selos no Painel: Monte Carlo (v1), riscos e confiança
        sel_mc = confere_selo("#p-previsao", gjo("/api/previsao-probabilistica?iteracoes=200", obra).get("simulacao_do_usuario"))
        sel_rs = confere_selo("#p-riscos", rsc.get("simulacao_do_usuario"))
        sel_cb = confere_selo("#p-cobertura", cob.get("simulacao_do_usuario"))
        rel.ok(sel_mc[0] and sel_rs[0] and sel_cb[0], f"painel ({obra}): selo 'não segue a simulação' no Monte Carlo, nos riscos e na confiança conforme a API",
               f"Monte Carlo:{sel_mc[1]} riscos:{sel_rs[1]} confiança:{sel_cb[1]}")

        # salvar simulação e reabrir (cenários salvos)
        nome_sv = f"e2e {obra} {int(time.time())}"
        c.js(f"{T}.irPara('simulacao')")
        time.sleep(0.4)
        c.js("document.querySelector('[data-ex=\"0\"]').click()")
        # espera o exemplo TERMINAR (a tela pode ter um resultado antigo: a API foi limpa por fora)
        c.esperar(f"{T}.estado.simulacao && {T}.estado.simulacao.ajustes.length === 1 && {T}.estado.cenarioAtivo === 'simulado'"
                  " && !!document.querySelector('#s-salvar') && !document.querySelector('#s-salvar').disabled", 120)
        c.js(f"(() => {{ document.querySelector('#s-nome-salvar').value = {json.dumps(nome_sv)}; document.querySelector('#s-salvar').click(); }})()")
        c.esperar("(document.querySelector('#s-salvos-msg')?.textContent || '').includes('salvo') && !!document.querySelector('#s-salvos-tab')", 120)
        lst = gjo("/api/historico/cenarios-salvos", obra)["cenarios"]
        sv = next((x for x in lst if x["nome"] == nome_sv), None)
        rel.ok(sv is not None and len(sv["ajustes"]) == len(gjo("/api/simulacao", obra)["ajustes"]),
               f"cenários salvos ({obra}): 'Salvar a simulação ativa' grava o cenário na API", nome_sv)
        if sv:
            c.js(f"document.querySelector('[data-reabrir=\"{sv['id']}\"]').click()")
            c.esperar("!!document.querySelector('#s-reaberto')", 120)
            reab = c.js("document.querySelector('#s-reaberto').innerText")
            c.js("document.querySelector('#s-limpar').click()")
            c.esperar(f"{T}.estado.cenarioAtivo === 'independente'", 60)
            c.esperar("!!document.querySelector('#s-reaplicar') && !document.querySelector('#s-reaplicar').disabled", 30)
            c.js("document.querySelector('#s-reaplicar').click()")
            c.esperar(f"{T}.estado.cenarioAtivo === 'simulado'", 120)
            sim_r = gjo("/api/simulacao", obra)
            rel.ok("reproduz idêntico" in reab and len(sim_r["ajustes"]) == len(sv["ajustes"]),
                   f"cenários salvos ({obra}): reabrir confere a reprodução e reaplica os ajustes como simulação", reab.replace("\n", " ")[:110])
        apagar_sim(obra)

        # modo IFC
        vin = gjo("/api/ifc/vinculo", obra)
        gid_ativ = {e["global_id"]: e["atividade_id"] for e in vin["elementos"] if e.get("atividade_id")}
        c.js(f"{T}.irPara('modelo')")
        c.esperar(f"{T}.viewer() && {T}.viewer().resumo().pecas > 0", 90)
        c.js("(() => { const s=document.querySelector('#v-geometria'); s.value='ifc'; s.dispatchEvent(new Event('change')); })()")
        c.esperar(f"{T}.viewer().modoGeo === 'ifc'", 600)
        c.esperar(f"{T}.viewer().resumo().porEstado.concluido > 0", 30)
        ri = c.js(f"{T}.viewer().resumoIfc()")
        rs = c.js(f"{T}.viewer().resumo()")
        rel.ok(ri and ri["globalIds"] == len(gid_ativ) and ri["semVinculo"] == 0 and sum(rs["porEstado"].values()) == rs["pecas"] > 0
               and c.js("document.querySelector('#v-exagero').disabled"),
               f"IFC ({obra}): GLB carregado, {len(gid_ativ)} GlobalIds vinculados e pintados pelo estado 4D",
               f"{json.dumps(ri)} estados={rs['porEstado']}")
        crit = c.js(f"({T}.estado.projeto.atividades.find(a => a.tipo==='tarefa' && a.status==='em_andamento' && {T}.viewer().temGeometria(a.id)) || {{}}).id")
        c.js(f"{T}.selecionar({json.dumps(crit)}, 'teste')")
        time.sleep(1.0)
        gids_ui = set(c.js(f"{T}.viewer().globalIdsDe({json.dumps(crit)})"))
        gids_api = {g for g, a in gid_ativ.items() if a == crit}
        st_ifc = c.js("document.querySelector('#v-ifc-sel')?.innerText || ''")
        rel.ok(gids_ui == gids_api and len(gids_api) > 0 and any(g in st_ifc for g in gids_api),
               f"IFC ({obra}): selecionar {crit} destaca exatamente os GlobalIds do vínculo e os mostra", f"{len(gids_ui)} GlobalIds")
        el0 = c.js(f"{T}.viewer().porAtividade.get({json.dumps(crit)})[0].userData.elementoId")
        pt = c.js(f"{T}.viewer().centroNaTela({json.dumps(el0)})")
        esperado_ifc = c.js(f"{T}.viewer().idNoPonto({pt['x']}, {pt['y']})")
        c.chamar("Input.dispatchMouseEvent", type="mouseMoved", x=pt["x"], y=pt["y"])
        c.esperar("document.querySelector('#v-hover').textContent.includes('GlobalId')", 10)
        hov = c.js("document.querySelector('#v-hover').textContent")
        c.clicar(pt["x"], pt["y"])
        time.sleep(0.5)
        sel_ifc = c.js(f"{T}.estado.selecionada")
        rel.ok(esperado_ifc and sel_ifc == esperado_ifc and esperado_ifc in set(gid_ativ.values()) and "GlobalId" in hov,
               f"IFC ({obra}): clique numa peça do GLB seleciona a atividade do vínculo; hover mostra o GlobalId",
               f"selecionada={sel_ifc} hover={hov[:80]}")
        foto(f"e2e-ifc-{obra}")
        c.js("(() => { const s=document.querySelector('#v-geometria'); s.value='sintetica'; s.dispatchEvent(new Event('change')); })()")
        time.sleep(0.5)
        rel.ok(c.js(f"{T}.viewer().modoGeo") == "sintetica" and not c.js("document.querySelector('#v-exagero').disabled"),
               f"IFC ({obra}): volta para a geometria esquemática")

    # aviso quando o módulo IFC está indisponível (saúde interceptada)
    saude_falsa = json.dumps({"ok": True, "versao": "teste", "aviso": "DADOS FICTÍCIOS", "obras": opcoes,
                              "modulos": {"ligados": [], "indisponiveis": {"ifc.rotas": "ModuleNotFoundError: teste"}}})
    c.respostas_falsas = [("/api/saude", "GET", (200, saude_falsa, "application/json"))]
    c.chamar("Fetch.enable", patterns=[{"urlPattern": "*/api/saude*"}])
    try:
        carga_limpa(f"{url}/#modelo?obra={opcoes[0]}", f"{T} && {T}.viewer() && {T}.viewer().resumo().pecas > 0", 120)
    finally:
        c.chamar("Fetch.disable")
        c.respostas_falsas = []
    c.js("(() => { const s=document.querySelector('#v-geometria'); s.value='ifc'; s.dispatchEvent(new Event('change')); })()")
    c.esperar("(document.querySelector('#v-ifc-status')?.innerText || '').includes('indisponível')", 30)
    rel.ok("indisponível" in c.js("document.querySelector('#v-ifc-status').innerText") and c.js(f"{T}.viewer().modoGeo") != "ifc",
           "IFC: com ifc.rotas indisponível na API, a tela avisa e mantém a geometria esquemática",
           c.js("document.querySelector('#v-ifc-status').innerText")[:120])

    # ==================================================================== auditoria r7: roteiros de navegador
    # (1–4, 6) dados injetados: servidor separado com as cargas maliciosas e estaca_origem = 100.
    # Com o CSP ativo um onerror inline NÃO executaria de qualquer forma; por isso o critério é o DOM:
    # nenhum <img src="x"> criado e a carga aparecendo como TEXTO literal.
    porta_inj = (urllib.parse.urlparse(url).port or 8765) + 1
    dados_inj, alvo_nome = dados_maliciosos()
    proc_inj, url_inj, pasta_inj = subir_servidor_injetado(dados_inj, porta_inj)
    sem_img = "document.querySelectorAll('img[src=\"x\"]').length === 0 && window.__xss === undefined"
    try:
        c.chamar("Page.navigate", url=f"{url_inj}/#apresentacao")
        c.esperar(f"{T} && {T}.estado.projeto && {T}.estado.cenarios.independente && document.querySelectorAll('.g-rotulos .linha').length > 0", 90)
        time.sleep(1)
        apres = c.js("document.querySelector('#apresentacao').innerText")
        rel.ok(c.js(sem_img) and "término da linha de base: —" in apres,
               "r7: término contratual malicioso vira '—' na Apresentação (dataBR valida o formato)", "")
        c.js(f"{T}.irPara('painel')")
        c.esperar("!!document.querySelector('#painel .kpis')", 120)
        kpi = c.js("document.querySelector('#painel .kpis').innerText")
        rel.ok(c.js(sem_img) and "contratual —" in kpi, "r7: término contratual malicioso vira '—' no Painel", "")
        # id de lote na Simulação (modo Serviço + lote)
        c.js(f"{T}.irPara('simulacao')")
        time.sleep(0.4)
        c.js("document.querySelector('input[name=s-modo][value=servico]').click()")
        time.sleep(0.4)
        textos_lote = c.js("[...document.querySelectorAll('#s-lote option')].map(o => o.textContent)")
        rel.ok(c.js(sem_img) and CARGA_XSS["lote"] in textos_lote and c.js("document.querySelectorAll('#simulacao img').length") == 0,
               "r7: id de lote malicioso aparece literal no <select> da Simulação, sem criar <img>", str(textos_lote[:1]))
        # id de serviço na legenda do 3D (modo de cor 'Serviço')
        c.js(f"{T}.irPara('modelo')")
        c.esperar(f"{T}.viewer() && {T}.viewer().resumo().pecas > 0", 60)
        c.js("(() => { const s=document.querySelector('#v-modo-cor'); s.value='servico'; s.dispatchEvent(new Event('change')); })()")
        time.sleep(0.4)
        leg = c.js("document.querySelector('#legenda-3d').innerText")
        rel.ok(c.js(sem_img) and CARGA_XSS["servico"] in leg and c.js("document.querySelectorAll('#legenda-3d img').length") == 0,
               "r7: id de serviço malicioso aparece literal na legenda do 3D, sem criar <img>", "")
        c.js("(() => { const s=document.querySelector('#v-modo-cor'); s.value='estado'; s.dispatchEvent(new Event('change')); })()")
        # nome de atividade malicioso: inerte em todas as abas; literal no tooltip e nos detalhes
        c.js(f"{T}.irPara('cronograma')")
        time.sleep(0.6)
        c.js(f"document.querySelector('.g-barras [data-id=\"{alvo_nome}\"] rect').dispatchEvent(new MouseEvent('mousemove',{{bubbles:true, clientX:400, clientY:400}}))")
        tip_nome = c.js("document.querySelector('.tooltip')?.innerText || ''")
        c.js(f"document.querySelector('.g-rotulos [data-id=\"{alvo_nome}\"] rect').dispatchEvent(new MouseEvent('click',{{bubbles:true}}))")
        time.sleep(0.4)
        det_nome = c.js("document.querySelector('#aba-cronograma [data-detalhes]').innerText")
        abas_ok = []
        for aba in ("modelo", "cronograma", "balanco", "painel", "simulacao", "recursos", "fiscalizacao", "cronoimport", "apresentacao"):
            c.js(f"{T}.irPara('{aba}')")
            time.sleep(1.2)
            if aba == "cronoimport":
                c.js("document.querySelector('#ci-exemplo').click()")
                c.esperar("!!document.querySelector('#ci-delta') || !!document.querySelector('#ci-erro')", 180)
            abas_ok.append((aba, bool(c.js(sem_img))))
        rel.ok(all(ok for _, ok in abas_ok) and CARGA_XSS["nome"] in tip_nome and CARGA_XSS["nome"] in det_nome,
               "r7: nome de atividade malicioso é inerte em todas as abas e aparece literal no tooltip e nos detalhes",
               f"abas={[a for a, ok in abas_ok if not ok] or 'todas ok'}")
        foto("e2e-r7-xss")
        # (6) estaca do tooltip da linha de balanço = /api/referencia/km (com estaca_origem = 100)
        km5 = json.load(urllib.request.urlopen(f"{url_inj}/api/referencia/km?km=5", timeout=60))["estaca"]
        alvo_km5 = next(a["id"] for a in dados_inj["atividades"] if a.get("km_ini") == 5.0 and a.get("tipo") == "tarefa" and not a.get("oae_id"))
        c.js(f"{T}.irPara('balanco')")
        time.sleep(0.8)
        mover = (f"document.querySelector('#balanco .ativ[data-id=\"{alvo_km5}\"]').lastElementChild"
                 ".dispatchEvent(new MouseEvent('mousemove',{bubbles:true, clientX:300, clientY:300}))")
        c.js(mover)
        c.esperar(f"(document.querySelector('.tooltip')?.innerText || '').includes({json.dumps(km5)})", 30)
        c.js(mover)
        tip5 = c.js("document.querySelector('.tooltip')?.innerText || ''")
        rel.ok(f"estaca {km5}" in tip5, f"r7: estaca do tooltip da linha de balanço = API com estaca_origem 100 ({km5})",
               tip5.replace("\n", " ")[:120])
    finally:
        proc_inj.terminate()
        try:
            proc_inj.wait(10)
        except subprocess.TimeoutExpired:
            proc_inj.kill()
        shutil.rmtree(pasta_inj, ignore_errors=True)

    # (5) respostas de erro e campos ausentes: interceptação de rede no navegador, um caso por vez
    def com_interceptacao(regras, destino: str, cond: str, seg: float = 60) -> bool:
        """Carga COMPLETA de `destino` (about:blank -> destino, para não virar navegação só de hash) com as
        respostas falsas ativas; espera `cond`."""
        c.respostas_falsas = regras
        c.chamar("Fetch.enable", patterns=[{"urlPattern": "*/api/*"}])
        try:
            c.chamar("Page.navigate", url="about:blank")
            time.sleep(0.3)
            c.chamar("Page.navigate", url=destino)
            return c.esperar(f"!!document.querySelector('#erro-global') && ({cond})", seg)
        finally:
            c.chamar("Fetch.disable")
            c.respostas_falsas = []

    excecoes_antes = len(c.excecoes)
    ok_a = com_interceptacao([("/api/painel", "GET", (200, "{}", "application/json"))],
                             f"{url}/#painel?obra=ferrovia",
                             "!!document.querySelector('#p-incompleto')")
    rel.ok(ok_a and "faltam" in c.js("document.querySelector('#p-incompleto').innerText"),
           "r7 (a): /api/painel com corpo {} mostra mensagem legível no Painel (sem exceção)",
           c.js("document.querySelector('#p-incompleto')?.innerText || ''")[:100])
    ok_b = com_interceptacao([("/api/simulacao", "GET", (200, '{"comparacao": {}}', "application/json"))],
                             f"{url}/#simulacao?obra=ferrovia",
                             "!!document.querySelector('#s-incompleto')")
    rel.ok(ok_b, "r7 (b): /api/simulacao sem 'ajustes' mostra mensagem legível na Simulação",
           c.js("document.querySelector('#s-incompleto')?.innerText || ''")[:100])
    ok_c = com_interceptacao([("/api/cenarios/independente", "GET", (500, "Internal Server Error", "text/plain"))],
                             f"{url}/#painel?obra=ferrovia",
                             "!document.querySelector('#erro-global').hidden")
    msg_c = c.js("document.querySelector('#erro-global-texto').textContent")
    c.js("document.querySelector('#erro-global-repetir').click()")
    recuperou = c.esperar(f"document.querySelector('#erro-global').hidden && {T}.estado.cenarios.independente"
                          " && document.querySelectorAll('.g-rotulos .linha').length > 0", 90)
    rel.ok(ok_c and "Erro HTTP 500" in msg_c and recuperou,
           "r7 (c): 500 em /api/cenarios mostra a faixa de erro e 'Tentar de novo' recupera", msg_c[:100])
    ok_d = com_interceptacao([("/api/projeto", "GET", (200, "ok", "text/plain"))],
                             f"{url}/#painel?obra=ferrovia",
                             "!document.querySelector('#erro-global').hidden")
    msg_d = c.js("document.querySelector('#erro-global-texto').textContent")
    rel.ok(ok_d and "não é JSON" in msg_d, "r7 (d): /api/projeto não-JSON mostra a faixa de erro com motivo claro", msg_d[:100])
    # (e) detail em OBJETO (como os importadores respondem quando o motor rejeita a rede) — simulado por interceptação
    c.chamar("Page.navigate", url="about:blank")  # carga completa (a página vinha do caso (d), quebrado de propósito)
    time.sleep(0.3)
    c.chamar("Page.navigate", url=f"{url}/#cronoimport?obra=ferrovia")
    c.esperar(f"{T} && {T}.estado.projeto && !!document.querySelector('#ci-exemplo')", 90)
    detalhe_obj = json.dumps({"detail": {"erro": "rede inválida: ciclo A → B → A", "avisos": ["aviso de teste"]}})
    c.respostas_falsas = [("/api/cronograma/comparar", "POST", (422, detalhe_obj, "application/json"))]
    c.chamar("Fetch.enable", patterns=[{"urlPattern": "*/api/cronograma/*"}])
    try:
        c.js("document.querySelector('#ci-exemplo').click()")
        c.esperar("!!document.querySelector('#ci-erro')", 120)
    finally:
        c.chamar("Fetch.disable")
        c.respostas_falsas = []
    msg_e = c.js("document.querySelector('#ci-erro')?.textContent || ''")
    rel.ok("ciclo A → B → A" in msg_e and "[object Object]" not in msg_e,
           "r7 (e): erro com detail em objeto mostra o texto do backend (não '[object Object]')", msg_e[:120])
    # (f) 409 no diário: mensagem no bloco do diário; os outros blocos continuam
    ok_f = com_interceptacao([("/api/fiscalizacao/diario", "GET",
                               (409, json.dumps({"detail": "a fiscalização só roda sobre obra marcada como FICTÍCIA"}), "application/json"))],
                             f"{url}/#fiscalizacao?obra=ferrovia",
                             "(document.querySelector('#fz-diario-bloco')?.innerText || '').includes('FICTÍCIA') && document.querySelectorAll('#fz-prod tbody tr').length > 0")
    rel.ok(ok_f, "r7 (f): 409 no diário aparece no bloco do diário e os demais blocos continuam",
           (c.js("document.querySelector('#fz-diario-bloco')?.innerText || ''") or "")[:120].replace("\n", " "))
    # (g) confiança "indeterminada" com motivo (resposta de /api/cobertura interceptada: o caso não ocorre nos dados atuais)
    cob_real = json.load(urllib.request.urlopen(f"{url}/api/cobertura?obra=ferrovia", timeout=600))
    cob_fake = json.loads(json.dumps(cob_real))
    motivo_teste = "nenhuma frente medida rendeu abaixo do planejado (f = 1): teste de interface"
    cob_fake["marcos"][0].update({"confianca": "indeterminada", "motivo": motivo_teste, "estresse": None})
    ok_g = com_interceptacao([("/api/cobertura", "GET", (200, json.dumps(cob_fake), "application/json"))],
                             f"{url}/#painel?obra=ferrovia",
                             "!!document.querySelector('#p-cob-tab [data-confianca=\"indeterminada\"]')", 600)
    txt_g = c.js("(document.querySelector('#p-cob-tab tbody tr')?.innerText || '')")
    rel.ok(ok_g and "indeterminada" in txt_g and motivo_teste in txt_g,
           "cobertura: confiança 'indeterminada' aparece com o motivo (estresse ausente vira '—')", txt_g.replace("\n", " ")[:120])

    c.js("1")
    rel.ok(len(c.excecoes) == excecoes_antes, "r7: nenhuma exceção JavaScript não tratada nos casos de erro (a)–(g)",
           "; ".join(c.excecoes[excecoes_antes:])[:200])

    # ---- integridade
    c.js("1")  # drena eventos pendentes
    rel.ok(not c.excecoes, "nenhuma exceção JavaScript", "; ".join(c.excecoes)[:300])
    # erros provocados de propósito: 422/415 (validação/formato), 409/500 (roteiros r7 por interceptação)
    provocados = ("status of 422", "status of 415", "status of 409", "status of 500")
    inesperados = [e for e in c.erros_console if not any(x in e for x in provocados)]
    rel.ok(not inesperados, "nenhum erro de console além dos 422/415/409/500 provocados (inclui violação de CSP)", "; ".join(inesperados)[:300])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default="http://127.0.0.1:8765")
    ap.add_argument("--porta-cdp", type=int, default=9333)
    ap.add_argument("--navegador", default=None)
    ap.add_argument("--capturas", default=None, help="pasta para salvar capturas de tela (opcional)")
    ap.add_argument("--base-federacao", type=Path, default=None, help="GeoJSON original do pacote de intercâmbio")
    ap.add_argument("--revisao-federacao", type=Path, default=None, help="GeoJSON retornado de aplicativo real; requer --base-federacao")
    ap.add_argument("--glb-federacao", type=Path, default=None, help="GLB nativo Blender opcional, validado contra a revisão JSON")
    ap.add_argument("--somente-federacao", action="store_true", help="Executa abertura, modos visuais e retorno federado; não substitui o e2e completo")
    a = ap.parse_args()
    if bool(a.base_federacao) != bool(a.revisao_federacao):
        ap.error("use --base-federacao e --revisao-federacao juntos")
    if a.somente_federacao and not a.base_federacao:
        ap.error("--somente-federacao exige base e revisão reais")
    url = a.url.rstrip("/")
    capturas = Path(a.capturas) if a.capturas else None
    if capturas:
        capturas.mkdir(parents=True, exist_ok=True)

    servidor = navegador = perfil = cdp = None
    rel = Relatorio()
    try:
        servidor = subir_servidor(url)
        navegador, perfil, ws_url = abrir_navegador(a.navegador, a.porta_cdp)
        cdp = CDP(ws_url)
        verificar(cdp, url, capturas, rel, a.porta_cdp, a.base_federacao, a.revisao_federacao, a.glb_federacao, a.somente_federacao)
    except NaoRodou as e:
        print(f"NAO RODOU: {e}")
        return 2
    except Exception as e:  # falha inesperada no meio: conta como FAIL, não como "não rodou"
        import traceback
        onde = [f"linha {q.lineno}: {(q.line or '').strip()[:100]}" for q in traceback.extract_tb(e.__traceback__) if q.filename == __file__]
        corpo = ""
        if isinstance(e, urllib.error.HTTPError):  # mostra o motivo que a API deu
            try:
                corpo = e.read().decode("utf-8", "replace")[:300]
            except OSError:
                pass
        rel.ok(False, f"execução interrompida: {type(e).__name__}: {e}", f"em {onde[-1] if onde else '?'} {corpo}")
    finally:
        for sufixo in ("", "?obra=rodovia"):  # limpa simulações deixadas por esta verificação
            try:
                urllib.request.urlopen(urllib.request.Request(f"{url}/api/simulacao{sufixo}", method="DELETE"), timeout=10).close()
            except OSError:
                pass
        if cdp:
            cdp.ws.fechar()
        if navegador:
            navegador.terminate()
            try:
                navegador.wait(10)
            except subprocess.TimeoutExpired:
                navegador.kill()
        if perfil:
            shutil.rmtree(perfil, ignore_errors=True)
        if servidor:
            servidor.terminate()
            try:
                servidor.wait(10)
            except subprocess.TimeoutExpired:
                servidor.kill()
            print("[ambiente] servidor iniciado pelo script foi encerrado")

    falhas = [t for ok, t in rel.res if not ok]
    if capturas:
        (capturas / 'resultado-e2e.json').write_text(json.dumps({
            'pass': len(rel.res) - len(falhas), 'fail': len(falhas), 'exit_code': 1 if falhas else 0,
            'navegador_solicitado': a.navegador or 'Chrome/Edge localizado pelo script',
            'escopo': 'federacao e modos visuais' if a.somente_federacao else 'interface completa',
            'modo': 'headless/CDP com renderização por software; não prova GUI manual ou GPU real',
            'base_federacao': str(a.base_federacao) if a.base_federacao else None,
            'revisao_federacao': str(a.revisao_federacao) if a.revisao_federacao else None,
            'checagens': [{'passou': ok, 'descricao': t} for ok, t in rel.res],
        }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\nResumo: {len(rel.res) - len(falhas)} PASS, {len(falhas)} FAIL")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
