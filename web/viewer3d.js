// Visualizador 3D/4D (three.js). Geometria SINTÉTICA gerada a partir do alinhamento + atividades.
//
// Convenção de eixos: three X = x (ao longo do eixo), three Z = -y (lateral), three Y = cota (para cima).
// As coordenadas são centralizadas no primeiro ponto do alinhamento (origem local) para evitar tremor numérico.
// Exagero E: aplicado às dimensões da seção transversal (largura e altura das camadas).
// O perfil (cota do eixo) usa um exagero mais suave, max(1, E/8), para não distorcer a vista geral.

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { planoDeEstilos } from './secoes.js';
import { corServico } from './cores.js';
import { esc } from './util.js';
import { CenarioApresentacao, MATERIAIS } from './cenario_apresentacao.js';

// Seções por serviço: orientadas a dados em secoes.js (estilos conhecidos por tipo de obra + camada genérica
// para serviço desconhecido). OAE: seções próprias abaixo.
const OAE_SEC = {
  FUN: [{ c: -2.6, wb: 1.2, wt: 1.2, h0: -6, t: 3 }, { c: 2.6, wb: 1.2, wt: 1.2, h0: -6, t: 3 }],
  MES: [{ c: 0, wb: 4.5, wt: 3.2, h0: -3, t: 5.7 }],
  SUE: [{ c: 0, wb: 7.5, wt: 7.5, h0: 2.7, t: 0.6 }],
};

export const CORES = {
  concluido: 0x2b9348,
  em_execucao: 0xe0a020,
  nao_iniciado: 0x9aa3ad,
  critico: 0xd62d2d,
  selecionado: 0x2a78d6,
  adiantado: 0x1baf7a,
  no_prazo: 0x8fb996,
  atrasado: 0xeb6834,
};
const hex = (n) => `#${n.toString(16).padStart(6, '0')}`;

export function legendaHTML(modo, plano, geo = 'sintetica') {
  const genericos = plano && plano.genericos.length
    ? `<span style="color:var(--texto-2)">Camadas genéricas (serviço sem seção definida): <b>${esc(plano.genericos.join(', '))}</b></span>` : '';
  if (modo === 'servico' && plano) {
    const ids = [...plano.estilos.entries()].filter(([, e]) => e).map(([id]) => id);
    return ids.map(id => `<span><i style="background:${esc(corServico(id))}"></i>${esc(id)}${plano.genericos.includes(id) ? ' (genérica)' : ''}</span>`).join('')
      + `<span><i style="background:${corServico('OAE')}"></i>OAE</span>`
      + `<span><i class="contorno"></i>Crítico</span><span><i style="background:${hex(CORES.selecionado)}"></i>Selecionado</span>` + genericos;
  }
  const itens = modo === 'desvio'
    ? [['adiantado', 'Adiantado vs LB (> +2 p.p.)'], ['no_prazo', 'No prazo (±2 p.p.)'], ['atrasado', 'Atrasado vs LB (< −2 p.p.)'], ['nao_iniciado', 'Não iniciado (nem na LB)']]
    : [['concluido', 'Concluído'], ['em_execucao', 'Em execução'], ['nao_iniciado', 'Não iniciado']];
  let h = itens.map(([k, t]) => `<span><i style="background:${hex(CORES[k])}${k === 'nao_iniciado' ? '66' : ''}"></i>${t}</span>`).join('');
  h += `<span><i class="contorno"></i>Crítico (contorno vermelho)</span>`;
  h += `<span><i style="background:${hex(CORES.selecionado)}"></i>Selecionado</span>`;
  h += geo === 'ifc'
    ? `<span style="color:var(--texto-3)">Modelo IFC 4.3 exportado em GLB, escala real (sem exagero); cada elemento é pintado pela atividade vinculada ao seu GlobalId.</span>`
    : `<span style="color:var(--texto-3)">Geometria esquemática gerada do alinhamento — 1 peça por km de cada serviço; OAE: 1 peça por apoio/vão.</span>`;
  return h + genericos;
}

export class Viewer3D {
  constructor(container, projeto, { aoSelecionar, aoPassar, aoPassarPonto, aoClicarPonto, vistaInicial } = {}) {
    this.aoPassarPonto = aoPassarPonto || (() => {});
    this.aoClicarPonto = aoClicarPonto || (() => {});
    this.container = container;
    this.vistaInicial = vistaInicial || null; // [kmA, kmB] para a primeira vista (oblíqua aproximada)
    this.projeto = projeto;
    this.aoSelecionar = aoSelecionar || (() => {});
    this.aoPassar = aoPassar || (() => {});
    this.exagero = 40;
    this.modoVisual = 'analise';
    this.baixoConsumo = false;
    this.contexto = null;
    this.modoCor = 'estado';
    this.ocultarFiltrados = false;
    this.estado4d = null;          // {id: {fracao, fracao_lb, estado, desvio, critica}}
    this.filtro = () => true;
    this.selecionada = null;
    this.pecas = [];                // meshes
    this.porAtividade = new Map(); // id -> [mesh]
    this.rotulos = [];
    this.enquadrarPendente = null;
    this.plano = planoDeEstilos(projeto);
    this._prepararAlinhamento();
    this._iniciarCena();
    this.construir();
  }

  // ---------- alinhamento ----------
  _prepararAlinhamento() {
    const pts = this.projeto.alinhamento.pontos; // [km, x, y, cota]
    const [, x0, y0, c0] = pts[0];
    this.x0 = x0;
    this.y0 = y0;
    this.c0 = c0;
    this.cotaMedia = pts.reduce((s, p) => s + (p[3] - c0), 0) / pts.length;
    this.km = pts.map(p => p[0]);
    this.X = pts.map(p => p[1] - x0);
    this.Z = pts.map(p => -(p[2] - y0));
    this.C = pts.map(p => p[3] - c0);
  }

  /** Interpola o eixo no km dado: {x, z, cota, tx, tz} (tangente unitária no plano XZ). */
  _ponto(km) {
    const K = this.km;
    const n = K.length;
    let i;
    if (km <= K[0]) i = 0;
    else if (km >= K[n - 1]) i = n - 2;
    else {
      let lo = 0, hi = n - 1;
      while (hi - lo > 1) {
        const m = (lo + hi) >> 1;
        if (K[m] <= km) lo = m; else hi = m;
      }
      i = lo;
    }
    const f = Math.max(0, Math.min(1, (km - K[i]) / (K[i + 1] - K[i])));
    const dx = this.X[i + 1] - this.X[i], dz = this.Z[i + 1] - this.Z[i];
    const L = Math.hypot(dx, dz) || 1;
    return {
      x: this.X[i] + f * dx, z: this.Z[i] + f * dz,
      cota: this.C[i] + f * (this.C[i + 1] - this.C[i]),
      tx: dx / L, tz: dz / L,
    };
  }

  /** Triângulos (não indexados) de um prisma de seção trapezoidal varrido de kmA a kmB. */
  _prisma(kmA, kmB, s, saida) {
    const E = this.exagero, Ev = Math.max(1, E / 8);
    const kms = [kmA];
    const passo = 0.1;
    for (let k = Math.ceil(kmA / passo + 1e-6) * passo; k < kmB - 1e-6; k += passo) kms.push(k);
    kms.push(kmB);
    const cantos = [[s.c - s.wb / 2, s.h0], [s.c + s.wb / 2, s.h0], [s.c + s.wt / 2, s.h0 + s.t], [s.c - s.wt / 2, s.h0 + s.t]];
    const aneis = kms.map(k => {
      const p = this._ponto(k);
      const nx = -p.tz, nz = p.tx; // normal lateral
      return cantos.map(([lat, up]) => [p.x + nx * lat * E, p.cota * Ev + up * E, p.z + nz * lat * E]);
    });
    const tri = (a, b, c) => saida.push(...a, ...b, ...c);
    for (let r = 0; r < aneis.length - 1; r++) {
      const A = aneis[r], B = aneis[r + 1];
      for (let j = 0; j < 4; j++) {
        const j2 = (j + 1) % 4;
        tri(A[j], B[j], B[j2]);
        tri(A[j], B[j2], A[j2]);
      }
    }
    const a = aneis[0], b = aneis[aneis.length - 1];
    tri(a[0], a[2], a[1]); tri(a[0], a[3], a[2]);
    tri(b[0], b[1], b[2]); tri(b[0], b[2], b[3]);
  }

  _geometria(partes) {
    const pos = [];
    for (const [kmA, kmB, s] of partes) this._prisma(kmA, kmB, s, pos);
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.computeVertexNormals();
    g.computeBoundingBox();
    g.computeBoundingSphere();
    return g;
  }

  // ---------- cena ----------
  _iniciarCena() {
    this.container.innerHTML = '';
    const r = this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    r.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.container.appendChild(r.domElement);
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(45, 1, 5, 400000);
    this.controls = new OrbitControls(this.camera, r.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.12;
    this.controls.screenSpacePanning = true;
    this.controls.maxPolarAngle = Math.PI * 0.495;
    this.renderer.localClippingEnabled = true;
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x6b7280, 1.4));
    const sol = new THREE.DirectionalLight(0xffffff, 1.6);
    sol.position.set(-20000, 40000, 30000);
    this.scene.add(sol);
    this.grupo = new THREE.Group();
    this.scene.add(this.grupo);
    this.raycaster = new THREE.Raycaster();
    this.camadaRotulos = document.createElement('div');
    this.container.appendChild(this.camadaRotulos);

    // seleção por clique (ignora arrasto)
    let ini = null;
    r.domElement.addEventListener('pointerdown', (e) => { ini = [e.clientX, e.clientY]; });
    r.domElement.addEventListener('pointerup', (e) => {
      if (!ini || Math.hypot(e.clientX - ini[0], e.clientY - ini[1]) > 5) return;
      const m = this._pick(e);
      this.aoSelecionar(m ? m.userData.atividadeId : null);
      if (m?.userData.componenteId || this.componenteRevisaoSelecionado) this.selecionarComponenteRevisao(m?.userData.componenteId || null);
      // clique fora das peças: ponto no "terreno" (plano na cota média do eixo) -> referência linear
      if (!m) {
        const p = this._pontoTerreno(e);
        if (p) this.aoClicarPonto(p);
      }
    });
    let ultimo = 0;
    r.domElement.addEventListener('pointermove', (e) => {
      const agora = performance.now();
      if (agora - ultimo < 60 || e.buttons) return;
      ultimo = agora;
      const hit = this._pickHit(e);
      const m = hit ? hit.object : null;
      r.domElement.style.cursor = m ? 'pointer' : '';
      this.aoPassar(m ? m.userData : null);
      this.aoPassarPonto(hit ? this._paraOriginal(hit.point) : this._pontoTerreno(e));
    });

    new ResizeObserver(() => this._redimensionar()).observe(this.container);
    this._redimensionar();
    const loop = () => {
      if (this.descartado) return;
      requestAnimationFrame(loop);
      if (!this.container.offsetParent) return; // aba oculta: não renderiza
      const agora = performance.now();
      if (this.baixoConsumo && this._ultimoFrame && agora - this._ultimoFrame < 65) return;
      this._ultimoFrame = agora;
      this.controls.update();
      this.renderer.render(this.scene, this.camera);
      this._atualizarRotulos();
    };
    loop();
  }

  _redimensionar() {
    const w = this.container.clientWidth, h = this.container.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  _raio(e) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    const v = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(v, this.camera);
  }

  _pickHit(e) {
    this._raio(e);
    const alvos = [...this.pecas, ...(this.contexto ? this.contexto.pecas : []), ...(this.pecasRevisao || []), ...(this.glbRevisao ? this.glbRevisao.pecas : [])]
      .filter(m => {
        if (!m.userData.selecionavel) return false;
        for (let o = m; o; o = o.parent) if (!o.visible) return false;
        return true;
      });
    return this.raycaster.intersectObjects(alvos, false)[0] || null;
  }

  _pick(e) {
    const hit = this._pickHit(e);
    return hit ? hit.object : null;
  }

  /** Converte um ponto da cena para as coordenadas originais do alinhamento (x_m, y_m). */
  _paraOriginal(v) {
    return { x: v.x + this.x0, y: this.y0 - v.z };
  }

  /** Interseção do raio do mouse com o plano do "terreno" (cota média do eixo, com o exagero vigente). */
  _pontoTerreno(e) {
    this._raio(e);
    const Ev = Math.max(1, this._escala() / 8);
    const plano = new THREE.Plane(new THREE.Vector3(0, 1, 0), -this.cotaMedia * Ev);
    const p = this.raycaster.ray.intersectPlane(plano, new THREE.Vector3());
    return p ? this._paraOriginal(p) : null;
  }

  /** Posição em tela de um ponto do terreno a `afastamento` metros do eixo no km dado (testes). */
  pontoNaTela(km, afastamento = 0) {
    const p = this._ponto(km);
    const Ev = Math.max(1, this._escala() / 8);
    const v = new THREE.Vector3(p.x - p.tz * afastamento, this.cotaMedia * Ev, p.z + p.tx * afastamento).project(this.camera);
    const r = this.renderer.domElement.getBoundingClientRect();
    return { x: r.left + (v.x + 1) / 2 * r.width, y: r.top + (1 - v.y) / 2 * r.height };
  }

  // ---------- construção das peças ----------
  construir() {
    // a geometria sintética vive em this.sint; this.pecas/porAtividade apontam para a geometria ATIVA (sintética ou IFC)
    for (const m of (this.sint ? this.sint.pecas : [])) {
      m.geometry.dispose();
      m.material.dispose();
      if (m.userData.arestas) m.userData.arestas.geometry.dispose();
    }
    this.grupo.clear();
    const pecas = [];
    const porAtividade = new Map();
    const oaes = new Map((this.projeto.oaes || []).map(o => [o.id, o]));
    const matArestas = this.matArestas || (this.matArestas = new THREE.LineBasicMaterial({ color: CORES.critico }));

    const addPeca = (a, i, n, partes) => {
      if (this.modoVisual === 'apresentacao' && a.servico_id === 'OAE-SUE') {
        partes = partes.map(([ini, fim, sec]) => [ini, fim, { ...sec, h0: 1.45, t: 0.6 }]);
      }
      // Só representação: plataforma/terreno não atravessam o vazio da ponte na apresentação.
      // A atividade, seu elementoId e os quantitativos continuam sendo os da referência.
      if (this.modoVisual === 'apresentacao' && !a.oae_id && ['SUP', 'TER', 'SUB', 'DRE'].includes(a.servico_id)) {
        for (const o of this.projeto.atividades.filter(o => o.servico_id === 'OAE-SUE')) {
          partes = partes.flatMap(([ini, fim, sec]) => fim <= o.km_ini || ini >= o.km_fim ? [[ini, fim, sec]]
            : [[ini, Math.min(fim, o.km_ini), sec], [Math.max(ini, o.km_fim), fim, sec]].filter(([x, y]) => y - x > 1e-6));
        }
      }
      const geo = this._geometria(partes);
      const mat = new THREE.MeshLambertMaterial({ color: CORES.nao_iniciado, transparent: true, opacity: 1, side: THREE.DoubleSide });
      const m = new THREE.Mesh(geo, mat);
      const nn = String(i + 1).padStart(2, '0');
      m.userData = { atividadeId: a.id, elementoId: `${a.id}-E${nn}`, i, n, selecionavel: true };
      const ar = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 35), matArestas);
      ar.visible = false;
      ar.raycast = () => {};
      m.add(ar);
      m.userData.arestas = ar;
      this.grupo.add(m);
      pecas.push(m);
      if (!porAtividade.has(a.id)) porAtividade.set(a.id, []);
      porAtividade.get(a.id).push(m);
    };

    for (const a of this.projeto.atividades) {
      if (a.tipo !== 'tarefa' || a.km_ini == null || a.km_fim == null) continue;
      if (a.oae_id) {
        const o = oaes.get(a.oae_id);
        const tipo = (a.servico_id || '').replace('OAE-', '');
        const sec = OAE_SEC[tipo];
        if (!o || !sec) continue;
        const vaos = o.vaos || 3;
        const k0 = a.km_ini, k1 = a.km_fim, dk = (k1 - k0) / vaos;
        if (tipo === 'SUE') {
          for (let i = 0; i < vaos; i++) addPeca(a, i, vaos, sec.map(s => [k0 + i * dk + 0.004, k0 + (i + 1) * dk - 0.004, s]));
        } else {
          const meia = tipo === 'FUN' ? 0.004 : 0.006;
          for (let i = 0; i <= vaos; i++) {
            const k = k0 + i * dk;
            addPeca(a, i, vaos + 1, sec.map(s => [k - meia, k + meia, s]));
          }
        }
        continue;
      }
      const estilo = this.plano.estilos.get(a.servico_id);
      if (!estilo) continue; // sem peça física (null) ou sem serviço
      const k0 = Math.min(Number(a.km_ini), Number(a.km_fim)), k1 = Math.max(Number(a.km_ini), Number(a.km_fim));
      if (!Number.isFinite(k0) || !Number.isFinite(k1) || k1 - k0 < 1e-6) continue;
      const sec = estilo.prismas;
      const n = Math.max(1, Math.round(k1 - k0));
      const dk = (k1 - k0) / n;
      for (let i = 0; i < n; i++) {
        const kA = k0 + i * dk, kB = kA + dk;
        let partes;
        if (estilo.marcadores) {
          // 4 marcadores pequenos por peça
          partes = [0.125, 0.375, 0.625, 0.875].flatMap(f => sec.map(s => [kA + f * dk - 0.006, kA + f * dk + 0.006, s]));
        } else {
          // pequeno respiro entre peças para que o limite de cada km seja legível
          partes = sec.map(s => [kA + 0.003, kB - 0.003, s]);
        }
        addPeca(a, i, n, partes);
      }
    }
    this.sint = { pecas, porAtividade };
    if (this.modoGeo !== 'ifc') { this.pecas = pecas; this.porAtividade = porAtividade; }
    this._criarRotulos();
    this.recolorir();
    if (!this._jaEnquadrou) {
      this._jaEnquadrou = true;
      if (this.vistaInicial) this.enquadrarKm(this.vistaInicial[0], this.vistaInicial[1]);
      else this.enquadrarTudo();
    }
  }

  _criarRotulos() {
    this.camadaRotulos.innerHTML = '';
    this.rotulos = [];
    const E = this._escala();
    const add = (km, texto, alt) => {
      const p = this._ponto(km);
      const el = document.createElement('div');
      el.className = 'rotulo-km';
      el.textContent = texto;
      this.camadaRotulos.appendChild(el);
      this.rotulos.push({ el, pos: new THREE.Vector3(p.x, p.cota * Math.max(1, E / 8) + alt * E, p.z), prioridade });
    };
    let prioridade;
    // ordem de prioridade: lotes > OAEs > km múltiplos de 10 > de 5 > de 1 (os de menor prioridade cedem lugar)
    prioridade = 0;
    for (const l of this.projeto.lotes) add((l.km_ini + l.km_fim) / 2, `${l.id} · ${l.construtora}`, 8);
    prioridade = 1;
    for (const o of this.projeto.oaes || []) add(o.km, `${o.id} (km ${o.km})`, 6);
    const kmMax = Math.round(this.km[this.km.length - 1]);
    for (let k = 0; k <= kmMax; k++) {
      prioridade = k % 10 === 0 ? 2 : k % 5 === 0 ? 3 : 4;
      add(k, `km ${k}`, 4);
    }
    this.rotulos.sort((a, b) => a.prioridade - b.prioridade);
  }

  /** Posiciona os rótulos em tela, escondendo os que colidiriam com um de prioridade maior. */
  _atualizarRotulos() {
    const w = this.container.clientWidth, h = this.container.clientHeight;
    const v = new THREE.Vector3();
    const ocupados = [];
    for (const r of this.rotulos) {
      v.copy(r.pos).project(this.camera);
      if (this.revisaoIsolada || v.z > 1 || v.z < -1 || Math.abs(v.x) > 1.02 || Math.abs(v.y) > 1.02) {
        r.el.style.display = 'none';
        continue;
      }
      const x = (v.x + 1) / 2 * w, y = (1 - v.y) / 2 * h;
      const larg = r.larg || (r.larg = Math.max(40, r.el.textContent.length * 6.4 + 10));
      const caixa = [x - larg / 2 - 4, y - 20, x + larg / 2 + 4, y + 2];
      if (ocupados.some(o => caixa[0] < o[2] && caixa[2] > o[0] && caixa[1] < o[3] && caixa[3] > o[1])) {
        r.el.style.display = 'none';
        continue;
      }
      ocupados.push(caixa);
      r.el.style.display = '';
      r.el.style.left = `${x}px`;
      r.el.style.top = `${y}px`;
    }
  }

  // ---------- estado / cores ----------
  setExagero(E) {
    if (E === this.exagero) return;
    const alvoAntes = this.controls.target.clone();
    this.exagero = E;
    this.construir();
    this.controls.target.copy(alvoAntes);
    if (this.registroRevisao) this.mostrarRevisao(this.registroRevisao);
  }
  setModoCor(m) { this.modoCor = m; this.recolorir(); }
  setEstado4d(e) { this.estado4d = e; this.recolorir(); }
  setFiltro(fn, ocultar) { this.filtro = fn; this.ocultarFiltrados = !!ocultar; this.recolorir(); }
  setSelecao(id) {
    this.selecionada = id;
    if (this.componenteRevisaoSelecionado) {
      this.componenteRevisaoSelecionado = null;
      this.aoSelecionarComponenteRevisao?.(null);
    }
    this.recolorir();
  }

  recolorir() {
    const ativ = new Map(this.projeto.atividades.map(a => [a.id, a]));
    for (const m of this.pecas) {
      const { atividadeId: id, i, n } = m.userData;
      const a = ativ.get(id);
      const e = this.estado4d ? this.estado4d[id] : null;
      const f = e ? e.fracao : 0;
      const flb = e ? e.fracao_lb : 0;
      let estadoPeca;
      if (f >= (i + 1) / n - 1e-9) estadoPeca = 'concluido';
      else if (f > i / n + 1e-9) estadoPeca = 'em_execucao';
      else estadoPeca = 'nao_iniciado';
      m.userData.estado = estadoPeca;
      let cor = CORES[estadoPeca];
      let opac = estadoPeca === 'nao_iniciado' ? 0.28 : 1;
      if (this.modoCor === 'desvio') {
        const lbPeca = flb >= (i + 1) / n - 1e-9 ? 2 : flb > i / n ? 1 : 0;
        const rePeca = estadoPeca === 'concluido' ? 2 : estadoPeca === 'em_execucao' ? 1 : 0;
        if (rePeca === 0 && lbPeca === 0) { cor = CORES.nao_iniciado; opac = 0.28; }
        else {
          const d = e ? e.desvio : 0;
          cor = d > 0.02 ? CORES.adiantado : d < -0.02 ? CORES.atrasado : CORES.no_prazo;
          opac = 1;
        }
      } else if (this.modoCor === 'servico') {
        const sid = a && (a.oae_id ? 'OAE' : a.servico_id);
        cor = parseInt(corServico(sid).slice(1), 16);
        opac = 1;
      }
      const passa = a ? this.filtro(a) : true;
      const sel = this.selecionada === id;
      if (this.modoVisual === 'apresentacao' && a) {
        const sid = a.oae_id ? 'OAE' : a.servico_id;
        cor = Object.prototype.hasOwnProperty.call(MATERIAIS, sid) ? MATERIAIS[sid] : 0x929b9c;
        if (a.servico_id === 'DOR' && this.contexto) opac = 0.03;
      }
      if (sel) { cor = CORES.selecionado; opac = 1; }
      m.material.color.setHex(cor);
      m.material.emissive.setHex(sel ? 0x0b2a66 : 0x000000);
      if (!passa && !sel) {
        m.visible = !this.ocultarFiltrados;
        opac = 0.06;
        m.userData.selecionavel = false;
      } else {
        m.visible = true;
        m.userData.selecionavel = true;
      }
      m.material.opacity = opac;
      m.material.depthWrite = opac >= 1;
      m.material.needsUpdate = true;
      m.userData.arestas.visible = !!(e && e.critica) && (passa || sel) && m.visible;
      if (this.modoVisual === 'apresentacao' && this.contexto && a && a.oae_id && ['OAE-FUN', 'OAE-MES'].includes(a.servico_id)) {
        m.visible = false; m.userData.selecionavel = false;
      }
    }
    if (this.contexto) this.contexto.atualizar();
    for (const m of this.pecasRevisao || []) {
      const a = ativ.get(m.userData.atividadeId), passa = !a || this.filtro(a);
      m.visible = passa || !this.ocultarFiltrados;
      m.userData.selecionavel = passa;
      m.material.opacity = passa ? 0.9 : 0.08;
      const selecionada = this.componenteRevisaoSelecionado
        ? this.componenteRevisaoSelecionado === m.userData.componenteId : this.selecionada === m.userData.atividadeId;
      if (selecionada) m.material.color.setHex(CORES.selecionado);
      else if (this.revisaoIsolada && m.userData.corCad) m.material.color.copy(m.userData.corCad);
      else m.material.color.setHex(0xd43ec4);
    }
    if (this.glbRevisao) for (const m of this.glbRevisao.pecas) {
      const a = ativ.get(m.userData.atividadeId), passa = !a || this.filtro(a);
      m.visible = passa || !this.ocultarFiltrados; m.userData.selecionavel = passa;
      for (const mat of (Array.isArray(m.material) ? m.material : [m.material])) {
        if (mat.emissive) mat.emissive.setHex(this.selecionada === m.userData.atividadeId ? 0x164b99 : 0);
      }
    }
    this._aplicarIsolamentoRevisao();
  }

  /** Modos visuais independentes dos dados e do cálculo. A análise legada continua disponível. */
  setModoVisual(modo) {
    if (!['analise', 'tecnico', 'apresentacao'].includes(modo)) return;
    if (this.modoVisual === 'analise') this.exageroAnalise = this.exagero;
    this.modoVisual = modo;
    this.setExagero(modo === 'analise' ? (this.exageroAnalise || 40) : 1);
    this.construir();
    this.renderer.setClearColor(modo === 'apresentacao' ? 0xc7dce7 : 0xcfdbe8, modo === 'apresentacao' ? 1 : 0);
    this._recriarContexto();
    this.recolorir();
    if (modo !== 'analise') this.enquadrarOae();
  }

  _recriarContexto(km) {
    if (this.contexto) { this.contexto.descartar(); this.contexto = null; }
    if (this.modoVisual !== 'apresentacao' || this.modoGeo === 'ifc') return;
    const oaes = this.projeto.oaes || [];
    const centro = km ?? (oaes.at(-1) ? oaes.at(-1).km : (this.km[0] + this.km.at(-1)) / 2);
    this.contexto = new CenarioApresentacao(this, centro, this.baixoConsumo);
    this.contexto.atualizar();
  }

  setBaixoConsumo(ativo) {
    this.baixoConsumo = !!ativo;
    this.renderer.setPixelRatio(ativo ? 1 : Math.min(window.devicePixelRatio, 2));
    this._redimensionar();
    const centro = this.contexto && this.contexto.centro;
    this._recriarContexto(centro ?? undefined);
    this.recolorir();
  }

  enquadrarOae() {
    const oaes = this.projeto.oaes || [];
    const o = oaes.at(-1);
    const k = o ? o.km : (this.km[0] + this.km.at(-1)) / 2;
    if (this.modoVisual === 'apresentacao' && (!this.contexto || Math.abs(this.contexto.centro - k) > 0.2)) this._recriarContexto(k);
    const p = this._ponto(k), E = this._escala(), Ev = Math.max(1, E / 8);
    const alvo = new THREE.Vector3(p.x, p.cota * Ev + 1.5 * E, p.z);
    this.controls.target.copy(alvo);
    const afast = this.modoVisual === 'analise' && E > 1 ? 650 : 105;
    this.camera.position.copy(alvo).add(new THREE.Vector3(-p.tx * afast - p.tz * afast * 0.8, afast * 0.45, -p.tz * afast + p.tx * afast * 0.8));
    this.camera.near = 0.1; this.camera.far = 150000;
    this.camera.updateProjectionMatrix(); this.controls.update();
  }

  vistaSuperior() {
    const alvo = this.controls.target.clone(), dist = Math.max(60, this.camera.position.distanceTo(alvo));
    this.camera.position.copy(alvo).add(new THREE.Vector3(0, dist, 0.001));
    this.controls.update();
  }

  setCorte(ativo) {
    const alvo = this.controls.target;
    this.renderer.clippingPlanes = ativo ? [new THREE.Plane(new THREE.Vector3(0, 0, -1), alvo.z)] : [];
  }

  resumoVisual() {
    return { modo: this.modoVisual, escala: this._escala(), baixoConsumo: this.baixoConsumo,
      contexto: !!this.contexto, detalhes: this.contexto ? this.contexto.pecas.length : 0,
      instancias: this.contexto ? this.contexto.dormentes.reduce((s, d) => s + d.kms.length, 0) : 0,
      chamadasDesenho: this.renderer.info.render.calls, triangulos: this.renderer.info.render.triangles,
      corte: this.renderer.clippingPlanes.length > 0 };
  }

  mostrarRevisao(registro) {
    if (!registro) this.isolarRevisao(false);
    this.registroRevisao = registro;
    this.componenteRevisaoSelecionado = null;
    this.aoSelecionarComponenteRevisao?.(null);
    if (this.grupoRevisao) {
      this.scene.remove(this.grupoRevisao);
      this.grupoRevisao.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); });
    }
    this.pecasRevisao = []; this.grupoRevisao = null;
    if (this.glbRevisao) {
      this.scene.remove(this.glbRevisao.cena);
      this.glbRevisao.cena.traverse(o => { if (o.geometry) o.geometry.dispose(); for (const m of (Array.isArray(o.material) ? o.material : [o.material])) if (m) m.dispose(); });
      this.glbRevisao = null;
    }
    if (!registro) return;
    this.grupoRevisao = new THREE.Group();
    const alteradas = new Set((registro.relatorio.mudancas || []).map(m => m.atividade_id));
    for (const linha of registro.linhas_locais || []) {
      const p = linha.properties, id = p.atividade_id;
      if (!alteradas.has(id)) continue;
      const nativa = p.geometria_local_m;
      if (nativa && Array.isArray(nativa.vertices) && Array.isArray(nativa.faces) && Array.isArray(nativa.matrix_world)) {
        const matriz = new THREE.Matrix4().set(...nativa.matrix_world.flat());
        const vertices = nativa.vertices.map(v => {
          const pos = new THREE.Vector3(...v).applyMatrix4(matriz);
          return [pos.x - this.x0, pos.z - this.c0, this.y0 - pos.y];
        });
        const componentes = p.componentes_nativos || [null];
        for (const componente of componentes) {
          const faces = componente ? nativa.faces.slice(componente.face_inicio, componente.face_inicio + componente.face_quantidade) : nativa.faces;
          const posicoes = [];
          for (const face of faces) for (let i = 1; i < face.length - 1; i++) {
            posicoes.push(...vertices[face[0]], ...vertices[face[i]], ...vertices[face[i + 1]]);
          }
          const geo = new THREE.BufferGeometry();
          geo.setAttribute('position', new THREE.Float32BufferAttribute(posicoes, 3));
          geo.computeVertexNormals();
          const m = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: 0xd43ec4, roughness: componente?.material === 'aco' ? 0.4 : 0.85,
            metalness: componente?.material === 'aco' ? 0.65 : 0, transparent: true, opacity: 0.9, side: THREE.DoubleSide }));
          m.userData = { atividadeId: id, elementoId: p.elemento_id, selecionavel: true, revisao: registro.revision, nativa: true,
            componenteId: componente?.componente_id || null, componente,
            corCad: componente ? new THREE.Color(...componente.cor_rgb) : null };
          this.grupoRevisao.add(m); this.pecasRevisao.push(m);
        }
        continue;
      }
      const pontos = linha.pontos.map(([x, y, c]) => {
        const cota = c == null ? this._ponto((p.km_ini + p.km_fim) / 2).cota : c - this.c0;
        return new THREE.Vector3(x - this.x0, cota * Math.max(1, this._escala() / 8) + 4 * this._escala(), this.y0 - y);
      });
      if (pontos.length < 2) continue;
      const geo = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pontos), Math.min(400, pontos.length * 4), 0.5 * this._escala(), 5, false);
      const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: 0xd43ec4, depthTest: false, transparent: true, opacity: 0.9 }));
      m.renderOrder = 5; m.userData = { atividadeId: id, elementoId: p.elemento_id, selecionavel: true, revisao: registro.revision };
      this.grupoRevisao.add(m); this.pecasRevisao.push(m);
    }
    this.scene.add(this.grupoRevisao);
    if (!this.pecasRevisao.length && !this.glbRevisao) this.isolarRevisao(false);
    this.recolorir();
  }

  resumoRevisao() {
    const caixas = new Map();
    for (const m of (this.pecasRevisao || []).filter(m => m.userData.nativa)) {
      const id = m.userData.atividadeId;
      if (!caixas.has(id)) caixas.set(id, new THREE.Box3());
      caixas.get(id).union(new THREE.Box3().setFromObject(m));
    }
    return { malhasNativas: (this.pecasRevisao || []).filter(m => m.userData.nativa).length,
      componentesNativos: (this.pecasRevisao || []).filter(m => m.userData.componenteId).length,
      componenteSelecionado: this.componenteRevisaoSelecionado || null,
      marcadores: (this.pecasRevisao || []).filter(m => !m.userData.nativa).length,
      dimensoes: Object.fromEntries([...caixas].map(([id, caixa]) => {
        const t = caixa.getSize(new THREE.Vector3());
        return [id, { x: t.x, y: t.y, z: t.z }];
      })) };
  }

  selecionarComponenteRevisao(id) {
    const m = (this.pecasRevisao || []).find(m => m.userData.componenteId === id);
    this.componenteRevisaoSelecionado = m ? id : null;
    this.recolorir();
    this.aoSelecionarComponenteRevisao?.(m?.userData.componente || null);
    return !!m;
  }

  /** Malha verdadeira exportada pelo Blender; não reconstrói a geometria a partir da linha GIS. */
  async carregarRevisaoGlb(buffer, registro) {
    const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
    if (registro.source_app !== 'Blender') throw new Error('GLB requer revisão Blender validada');
    const manager = new THREE.LoadingManager();
    manager.setURLModifier(url => {
      if (!url.startsWith('data:')) throw new Error('GLB deve ser autocontido; recurso externo recusado');
      return url;
    });
    const gltf = await new GLTFLoader(manager).parseAsync(buffer, '');
    const cena = gltf.scene, porId = new Map(registro.geojson.features.map(f => [f.properties.atividade_id, f.properties]));
    const pecas = [], ids = new Set();
    let erro = null;
    cena.traverse(o => {
      if (!o.isMesh) return;
      let n = o;
      while (n && !n.userData.atividade_id) n = n.parent;
      const id = n && n.userData.atividade_id, prop = id && porId.get(id);
      if (!prop || n.userData.elemento_id !== prop.elemento_id) { erro = 'malha sem vínculo válido atividade/elemento'; return; }
      if (!o.geometry.attributes.normal) o.geometry.computeVertexNormals();
      o.userData = { ...o.userData, atividadeId: id, elementoId: prop.elemento_id, selecionavel: true, revisao: registro.revision };
      pecas.push(o); ids.add(id);
    });
    if (erro || ids.size !== porId.size) {
      cena.traverse(o => { if (o.geometry) o.geometry.dispose(); for (const m of (Array.isArray(o.material) ? o.material : [o.material])) if (m) m.dispose(); });
      throw new Error(erro || 'conjunto de atividades do GLB diverge da revisão');
    }
    this.mostrarRevisao(registro);
    if (this.grupoRevisao) this.grupoRevisao.visible = false;
    cena.position.set(-this.x0, -this.c0, this.y0);
    cena.updateMatrixWorld(true);
    // Se o retorno traz a malha do .blend reaberto, o GLB precisa reproduzir sua caixa 1:1.
    // Tolerância de visualização de 1 cm: não é critério de locação/engenharia.
    for (const m of pecas) {
      const prop = porId.get(m.userData.atividadeId), nativa = prop.geometria_local_m;
      if (!nativa) continue;
      const matriz = new THREE.Matrix4().set(...nativa.matrix_world.flat()), esperado = new THREE.Box3();
      for (const v of nativa.vertices) {
        const p = new THREE.Vector3(...v).applyMatrix4(matriz);
        esperado.expandByPoint(new THREE.Vector3(p.x - this.x0, p.z - this.c0, this.y0 - p.y));
      }
      const atual = new THREE.Box3().setFromObject(m);
      if (atual.min.distanceTo(esperado.min) > 0.01 || atual.max.distanceTo(esperado.max) > 0.01) {
        cena.traverse(o => { if (o.geometry) o.geometry.dispose(); for (const mat of (Array.isArray(o.material) ? o.material : [o.material])) if (mat) mat.dispose(); });
        throw new Error(`GLB diverge da geometria da revisão em ${m.userData.atividadeId}`);
      }
    }
    this.glbRevisao = { cena, pecas, ids, revision: registro.revision };
    this.scene.add(cena);
    this.recolorir();
    const alterada = (registro.relatorio.mudancas || []).find(m => m.campo === 'transformacao_visual');
    const alvo = pecas.find(m => m.userData.atividadeId === (alterada && alterada.atividade_id)) || pecas[0];
    if (alvo) this._enquadrarCaixa(new THREE.Box3().setFromObject(alvo));
    return this.resumoGlbRevisao();
  }

  resumoGlbRevisao() {
    if (!this.glbRevisao) return null;
    return { atividades: this.glbRevisao.ids.size, malhas: this.glbRevisao.pecas.length,
      revision: this.glbRevisao.revision, escala: 1,
      dimensoes: Object.fromEntries(this.glbRevisao.pecas.map(m => {
        const t = new THREE.Box3().setFromObject(m).getSize(new THREE.Vector3());
        return [m.userData.atividadeId, { x: t.x, y: t.y, z: t.z }];
      })) };
  }

  // ---------- câmera ----------
  _aplicarIsolamentoRevisao() {
    const ifc = this.modoGeo === 'ifc' && this.ifc;
    this.grupo.visible = !this.revisaoIsolada && !ifc;
    if (this.ifc) this.ifc.cena.visible = !this.revisaoIsolada && !!ifc;
    if (this.contexto) {
      this.contexto.grupo.visible = !this.revisaoIsolada || !!this.revisaoComContexto;
      this.contexto.engenharia.visible = !this.revisaoIsolada;
    }
  }

  setAmbienteRevisao(ativo) {
    this.revisaoComContexto = !!ativo;
    this._aplicarIsolamentoRevisao();
  }

  isolarRevisao(ativo) {
    if (ativo && !this.pecasRevisao?.length && !this.glbRevisao) return false;
    this.revisaoIsolada = !!ativo;
    this.recolorir();
    return true;
  }

  enquadrarRevisao() {
    const grupo = this.glbRevisao?.cena || this.grupoRevisao;
    if (!grupo || !grupo.visible) return false;
    const box = new THREE.Box3().setFromObject(grupo);
    if (box.isEmpty() || ![...box.min.toArray(), ...box.max.toArray()].every(Number.isFinite)) return false;
    this._enquadrarCaixa(box, 1);
    return true;
  }

  _enquadrarCaixa(box, tamanhoMinimo = 200) {
    const centro = box.getCenter(new THREE.Vector3());
    const tam = box.getSize(new THREE.Vector3());
    const raio = Math.max(tam.x, tam.y, tam.z, tamanhoMinimo) * 0.6;
    const dist = raio / Math.sin((this.camera.fov * Math.PI / 180) / 2) * 1.1;
    let dir = this.camera.position.clone().sub(this.controls.target);
    if (dir.lengthSq() < 1) dir.set(-0.4, 0.55, 0.75);
    dir.normalize();
    if (dir.y < 0.25) { dir.y = 0.25; dir.normalize(); }
    this.controls.target.copy(centro);
    this.camera.position.copy(centro).addScaledVector(dir, dist);
    this.camera.near = Math.max(1, dist / 2000);
    this.camera.far = dist * 50 + 200000;
    this.camera.updateProjectionMatrix();
    this.controls.update();
  }

  enquadrarTudo() {
    const box = new THREE.Box3().setFromObject(this.grupo);
    if (box.isEmpty()) return;
    const c = box.getCenter(new THREE.Vector3());
    const dir = new THREE.Vector3(-0.1, 0.72, 0.68).normalize();
    const tam = box.getSize(new THREE.Vector3());
    const dist = Math.max(tam.x, tam.z) * 0.82;
    this.controls.target.copy(c);
    this.camera.position.copy(c).addScaledVector(dir, dist);
    this.camera.near = Math.max(1, dist / 2000);
    this.camera.far = dist * 20;
    this.camera.updateProjectionMatrix();
    this.controls.update();
  }

  /**
   * Vista oblíqua aproximada de um trecho [kmA, kmB]: câmera atrás e ao lado do trecho, olhando ao longo do eixo.
   * Se a aba estiver oculta, adia até ficar visível.
   */
  enquadrarKm(kmA, kmB) {
    if (!this.container.offsetParent) { this.kmPendente = [kmA, kmB]; return; }
    const E = this._escala(), Ev = Math.max(1, E / 8);
    const kc = (kmA + kmB) / 2;
    const p = this._ponto(kc);
    const L = Math.max(500, (kmB - kmA) * 1000);
    const alvo = new THREE.Vector3(p.x, p.cota * Ev + 1.5 * E, p.z);
    const T = new THREE.Vector3(p.tx, 0, p.tz);
    const N = new THREE.Vector3(-p.tz, 0, p.tx);
    // atrás (−T), para o lado (+N) e para cima — proporcional ao comprimento do trecho
    const pos = alvo.clone().addScaledVector(T, -0.62 * L).addScaledVector(N, 0.42 * L).add(new THREE.Vector3(0, 0.3 * L, 0));
    this.controls.target.copy(alvo);
    this.camera.position.copy(pos);
    const dist = pos.distanceTo(alvo);
    this.camera.near = Math.max(1, dist / 3000);
    this.camera.far = dist * 40 + 100000;
    this.camera.updateProjectionMatrix();
    this.controls.update();
  }

  /** Estado da câmera para testes: km do alvo e distância. */
  resumoCamera() {
    const t = this.controls.target;
    let melhor = 0, dmin = Infinity;
    for (let i = 0; i < this.km.length; i++) {
      const d = Math.hypot(this.X[i] - t.x, this.Z[i] - t.z);
      if (d < dmin) { dmin = d; melhor = i; }
    }
    return { kmAlvo: this.km[melhor], distancia: Math.round(this.camera.position.distanceTo(t)) };
  }

  /** Id da atividade da peça visível no ponto de tela (x, y) — o mesmo raycast do clique. */
  idNoPonto(x, y) {
    const m = this._pick({ clientX: x, clientY: y });
    return m ? m.userData.atividadeId : null;
  }

  /** Enquadra as peças de uma atividade. Se a aba estiver oculta, adia até ficar visível. */
  enquadrarAtividade(id) {
    const ms = this.porAtividade.get(id);
    if (!ms || !ms.length) return false;
    if (!this.container.offsetParent) { this.enquadrarPendente = id; return true; }
    const box = new THREE.Box3();
    for (const m of ms) box.expandByObject(m);
    this._enquadrarCaixa(box);
    return true;
  }

  temGeometria(id) { return this.porAtividade.has(id); }

  // ---------- modo "Modelo IFC" (GLB exportado do IFC 4.3 da obra) ----------
  /** Exagero efetivo: o modelo IFC é mostrado em escala real (sem exagero). */
  _escala() { return this.modoGeo === 'ifc' ? 1 : this.exagero; }

  /**
   * Carrega o GLB (node.name = GlobalId) e o vínculo GlobalId → atividade. Cada malha recebe material próprio
   * para ser pintada pelo estado 4D com a MESMA regra das peças sintéticas (peça i de n da atividade).
   * Sistema: glTF (x, y, z) = IFC (x, z, −y), origem = coordenadas do alinhamento → desloca para a origem local.
   */
  async carregarIfc(urlGlb, vinculo) {
    if (this.ifc) return this.ifc;
    const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
    const gltf = await new GLTFLoader().loadAsync(urlGlb);
    const porGid = new Map((vinculo.elementos || []).map(e => [e.global_id, e]));
    const nPorAtiv = new Map();
    for (const e of vinculo.elementos || []) nPorAtiv.set(e.atividade_id, (nPorAtiv.get(e.atividade_id) || 0) + 1);
    const cena = gltf.scene;
    cena.position.set(-this.x0, -this.c0, this.y0);
    const pecas = [];
    const porAtividade = new Map();
    const gids = new Set();
    const semVinculo = [];
    const matArestas = this.matArestas || (this.matArestas = new THREE.LineBasicMaterial({ color: CORES.critico }));
    const malhas = [];
    cena.traverse(o => { if (o.isMesh) malhas.push(o); });
    for (const o of malhas) {
      let n = o, el = null;
      while (n && !(el = porGid.get(n.name))) n = n.parent;
      // GLB sem normais: o material iluminado ficaria preto
      if (o.geometry && !o.geometry.attributes.normal) o.geometry.computeVertexNormals();
      const velhos = Array.isArray(o.material) ? o.material : [o.material];
      velhos.forEach(m => m && m.dispose && m.dispose());
      o.material = new THREE.MeshLambertMaterial({ color: CORES.nao_iniciado, transparent: true, side: THREE.DoubleSide });
      if (!el || !el.atividade_id) {
        o.userData = { selecionavel: false };
        semVinculo.push(o);
        continue;
      }
      const m = /-E(\d+)$/.exec(el.elemento_id || '');
      const i = m ? Number(m[1]) - 1 : 0;
      o.userData = { atividadeId: el.atividade_id, elementoId: el.elemento_id || el.global_id, globalId: el.global_id,
        classe: el.classe, i, n: nPorAtiv.get(el.atividade_id) || 1, selecionavel: true };
      const ar = new THREE.LineSegments(new THREE.EdgesGeometry(o.geometry, 35), matArestas);
      ar.visible = false;
      ar.raycast = () => {};
      o.add(ar);
      o.userData.arestas = ar;
      pecas.push(o);
      gids.add(el.global_id);
      if (!porAtividade.has(el.atividade_id)) porAtividade.set(el.atividade_id, []);
      porAtividade.get(el.atividade_id).push(o);
    }
    cena.visible = false;
    this.scene.add(cena);
    this.ifc = { cena, pecas, porAtividade, gids, semVinculo, sistema: vinculo.sistema || null, resumo: vinculo.resumo || null };
    return this.ifc;
  }

  /** 'sintetica' (esquemática, com exagero) ou 'ifc' (GLB em escala real). */
  setModoGeometria(modo) {
    const ifc = modo === 'ifc' && this.ifc;
    this.modoGeo = ifc ? 'ifc' : 'sintetica';
    this.grupo.visible = !ifc;
    if (this.ifc) this.ifc.cena.visible = !!ifc;
    const g = ifc ? this.ifc : this.sint;
    this.pecas = g.pecas;
    this.porAtividade = g.porAtividade;
    this._recriarContexto();
    if (this.registroRevisao) this.mostrarRevisao(this.registroRevisao);
    this._criarRotulos();
    this.recolorir();
  }

  /** GlobalIds (IFC) das peças de uma atividade, no modo IFC. */
  globalIdsDe(id) {
    if (!this.ifc) return [];
    return [...new Set((this.ifc.porAtividade.get(id) || []).map(m => m.userData.globalId))];
  }

  /** Resumo do modo IFC (testes): elementos com GlobalId e estado de cada peça. */
  resumoIfc() {
    if (!this.ifc) return null;
    return { modo: this.modoGeo, malhas: this.ifc.pecas.length, globalIds: this.ifc.gids.size,
      atividades: this.ifc.porAtividade.size, semVinculo: this.ifc.semVinculo.length };
  }

  legenda() {
    if (this.modoVisual === 'apresentacao') return '<span><b>100% fictício · apresentação em escala 1:1</b></span><span>Materiais ilustrativos; transparência = remanescente; azul = seleção; contorno vermelho = criticidade, não atraso.</span><span>Terreno, água e vegetação são contexto; não fornecem quantitativos. Consulte Análise 4D para cores de avanço.</span>';
    return legendaHTML(this.modoCor, this.plano, this.modoGeo || 'sintetica');
  }

  /** Libera GPU/memória (geometrias, materiais, contexto WebGL) e para o laço de renderização. */
  descartar() {
    this.descartado = true;
    this.mostrarRevisao(null);
    if (this.contexto) this.contexto.descartar();
    for (const m of [...(this.sint ? this.sint.pecas : []), ...(this.ifc ? this.ifc.pecas : []), ...(this.ifc ? this.ifc.semVinculo : [])]) {
      m.geometry.dispose();
      m.material.dispose();
      if (m.userData.arestas) m.userData.arestas.geometry.dispose();
    }
    if (this.matArestas) this.matArestas.dispose();
    this.controls.dispose();
    this.renderer.dispose();
    this.renderer.forceContextLoss();
    this.container.innerHTML = '';
  }

  /** Posição em tela (px, relativa à janela) do centro de uma peça — usado em testes automatizados. */
  centroNaTela(elementoId) {
    const m = this.pecas.find(p => p.userData.elementoId === elementoId);
    if (!m) return null;
    const v = new THREE.Box3().setFromObject(m).getCenter(new THREE.Vector3()).project(this.camera);
    const r = this.renderer.domElement.getBoundingClientRect();
    return { x: r.left + (v.x + 1) / 2 * r.width, y: r.top + (1 - v.y) / 2 * r.height };
  }

  resumo() {
    const cont = {};
    for (const m of this.pecas) cont[m.userData.estado] = (cont[m.userData.estado] || 0) + 1;
    return { pecas: this.pecas.length, atividades: this.porAtividade.size, porEstado: cont,
      criticasComContorno: this.pecas.filter(m => m.userData.arestas.visible).length,
      visiveis: this.pecas.filter(m => m.visible).length };
  }

  /** Chamar quando a aba do 3D ficar visível. */
  aoMostrar() {
    this._redimensionar();
    if (this.kmPendente) {
      const [a, b] = this.kmPendente;
      this.kmPendente = null;
      this.enquadrarKm(a, b);
    }
    if (this.enquadrarPendente) {
      const id = this.enquadrarPendente;
      this.enquadrarPendente = null;
      this.enquadrarAtividade(id);
    }
  }
}
