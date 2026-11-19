// Contexto visual original, 100% fictício. Não fornece quantitativos nem altera o CPM.
// Geometria de detalhe é publicada por atividade; terreno/vegetação são só contexto.
import * as THREE from 'three';

export const MATERIAIS = {
  SUP: 0x637749, TER: 0x9a7950, SUB: 0xb09d78, LAS: 0x797e83,
  DOR: 0xa69b86, GRA: 0x4c5661, SOL: 0x69747e, DRE: 0xa5afb0,
  SBB: 0xa99b80, BGS: 0x858a8b, IMP: 0x505357, CBU: 0x343c43,
  SHV: 0xf4efcf, SVV: 0xa5b3bd, DEF: 0xb0bcc0, OAE: 0xb8b7ae,
};

export class CenarioApresentacao {
  constructor(viewer, kmCentro, reduzido = false) {
    this.v = viewer;
    this.centro = kmCentro;
    this.reduzido = reduzido;
    this.grupo = new THREE.Group();
    this.grupo.name = 'Contexto ilustrativo — sem quantitativos de engenharia';
    this.ambiente = new THREE.Group();
    this.engenharia = new THREE.Group();
    this.grupo.add(this.ambiente, this.engenharia);
    this.pecas = [];
    this.dormentes = [];
    this.recursos = new Set();
    this._terreno();
    this._via();
    this._pontes();
    viewer.scene.add(this.grupo);
  }

  _material(cor, metal = 0) {
    const m = new THREE.MeshStandardMaterial({ color: cor, roughness: metal ? 0.46 : 0.9, metalness: metal, transparent: true });
    this.recursos.add(m);
    return m;
  }

  _caixa(atividade, nome, km, lateral, altura, largura, espessura, comprimento, material) {
    const geo = new THREE.BoxGeometry(largura, espessura, comprimento);
    this.recursos.add(geo);
    const m = new THREE.Mesh(geo, material.clone());
    this.recursos.add(m.material);
    const p = this.v._ponto(km);
    m.position.set(p.x - p.tz * lateral, p.cota + altura, p.z + p.tx * lateral);
    m.rotation.y = Math.atan2(p.tx, p.tz);
    m.userData = { atividadeId: atividade.id, elementoId: `${atividade.id}-VIS-${nome}`,
      ilustrativo: true, selecionavel: true, km, i: 0, n: 1 };
    this.engenharia.add(m);
    this.pecas.push(m);
    return m;
  }

  _terreno() {
    const v = this.v, vertices = [], cores = [], indices = [];
    const linhas = this.reduzido ? 40 : 100, colunas = this.reduzido ? 12 : 24;
    const min = Math.max(v.km[0], this.centro - 0.9), max = Math.min(v.km.at(-1), this.centro + 0.9);
    const oaes = v.projeto.oaes || [];
    for (let i = 0; i <= linhas; i++) {
      const km = min + (max - min) * i / linhas, p = v._ponto(km);
      for (let j = 0; j <= colunas; j++) {
        const lat = (j / colunas - 0.5) * 500;
        const vale = oaes.reduce((s, o) => Math.max(s, 15 * Math.exp(-(((km - o.km) / 0.09) ** 2))), 0);
        const relevo = Math.sin(km * 12 + lat * 0.015) * Math.min(Math.abs(lat) * 0.08, 8);
        const h = p.cota - 0.6 - vale + relevo;
        vertices.push(p.x - p.tz * lat, h, p.z + p.tx * lat);
        const c = new THREE.Color().setHSL(0.21 + 0.025 * Math.sin(km * 9 + j), 0.24, 0.31 + 0.06 * Math.sin(i + j));
        cores.push(c.r, c.g, c.b);
        if (i < linhas && j < colunas) {
          const a = i * (colunas + 1) + j, b = a + colunas + 1;
          indices.push(a, b, a + 1, b, b + 1, a + 1);
        }
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
    geo.setAttribute('color', new THREE.Float32BufferAttribute(cores, 3));
    geo.setIndex(indices); geo.computeVertexNormals();
    const mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1, side: THREE.DoubleSide });
    this.recursos.add(geo); this.recursos.add(mat);
    this.ambiente.add(new THREE.Mesh(geo, mat));
    // Água ilustrativa sob a OAE, sem CRS real, hidrologia ou dimensão de projeto.
    const oae = oaes.find(o => Math.abs(o.km - this.centro) < 0.4);
    if (oae) {
      const p = v._ponto(oae.km), g = new THREE.PlaneGeometry(50, 480);
      const m = new THREE.MeshStandardMaterial({ color: 0x497d8b, roughness: 0.3, metalness: 0.15 });
      const rio = new THREE.Mesh(g, m); rio.rotation.x = -Math.PI / 2;
      rio.rotation.z = -Math.atan2(p.tx, p.tz);
      rio.position.set(p.x, p.cota - 13, p.z);
      this.recursos.add(g); this.recursos.add(m); this.ambiente.add(rio);
    }
    // Vegetação instanciada e determinística, afastada do eixo; sem modelos/texturas externos.
    const n = this.reduzido ? 36 : 100, g = new THREE.ConeGeometry(4, 13, 6), m = this._material(0x3c6146);
    const arvores = new THREE.InstancedMesh(g, m, n), objeto = new THREE.Object3D();
    this.recursos.add(g);
    for (let i = 0; i < n; i++) {
      const km = min + (max - min) * ((i * 37 % n) / n), p = v._ponto(km);
      const lat = (i % 2 ? 1 : -1) * (40 + i * 19 % 160);
      const vale = oaes.reduce((s, o) => Math.max(s, 15 * Math.exp(-(((km - o.km) / 0.09) ** 2))), 0);
      objeto.position.set(p.x - p.tz * lat, p.cota + 5 - vale, p.z + p.tx * lat);
      objeto.updateMatrix(); arvores.setMatrixAt(i, objeto.matrix);
    }
    this.ambiente.add(arvores);
  }

  _via() {
    if (this.v.plano.tipo !== 'ferrovia') return;
    const g = new THREE.BoxGeometry(2.8, 0.14, 0.24), mat = this._material(MATERIAIS.DOR);
    this.recursos.add(g);
    const passo = this.reduzido ? 0.004 : 0.0006;
    for (const a of this.v.projeto.atividades.filter(a => a.servico_id === 'DOR' && !a.oae_id)) {
      const ini = Math.max(a.km_ini, this.centro - 0.65), fim = Math.min(a.km_fim, this.centro + 0.65);
      if (fim <= ini) continue;
      const kms = [];
      for (let k = ini; k < fim; k += passo) kms.push(k);
      const inst = new THREE.InstancedMesh(g, mat.clone(), kms.length);
      this.recursos.add(inst.material);
      inst.userData = { atividadeId: a.id, elementoId: `${a.id}-VIS-DORMENTES`, ilustrativo: true,
        selecionavel: true, i: 0, n: 1 };
      this.dormentes.push({ inst, kms, atividade: a });
      this.pecas.push(inst); this.engenharia.add(inst);
    }
  }

  _pontes() {
    const concreto = this._material(MATERIAIS.OAE), metal = this._material(0x5e6d76, 0.45);
    for (const o of this.v.projeto.oaes || []) {
      if (Math.abs(o.km - this.centro) > 0.7) continue;
      const atividades = this.v.projeto.atividades.filter(a => a.oae_id === o.id);
      const sue = atividades.find(a => a.servico_id === 'OAE-SUE');
      const mes = atividades.find(a => a.servico_id === 'OAE-MES');
      const fun = atividades.find(a => a.servico_id === 'OAE-FUN');
      if (!sue || !mes || !fun) continue;
      const ini = sue.km_ini, fim = sue.km_fim, n = o.vaos || 3;
      for (let i = 0; i < n; i++) {
        const km = ini + (i + 0.5) * (fim - ini) / n, len = (fim - ini) * 1000 / n;
        for (const lat of [-2.5, 2.5]) this._caixa(sue, `${o.id}-VIGA-${i}-${lat}`, km, lat, 0.6, 0.6, 1.7, len - 0.2, concreto);
        for (const lat of [-3.5, 3.5]) {
          this._caixa(sue, `${o.id}-GUARDA-${i}-${lat}`, km, lat, 4, 0.12, 0.12, len - 0.1, metal);
          for (let j = 0; j < 6; j++) this._caixa(sue, `${o.id}-POSTE-${i}-${j}-${lat}`,
            km + (j / 5 - 0.5) * (len - 1) / 1000, lat, 3.45, 0.1, 1.2, 0.1, metal);
        }
      }
      for (let i = 0; i <= n; i++) {
        const km = ini + i * (fim - ini) / n;
        for (const lat of [-2, 2]) {
          this._caixa(mes, `${o.id}-PILAR-${i}-${lat}`, km, lat, -5.7, 1.25, 10.3, 1.25, concreto);
          this._caixa(fun, `${o.id}-BLOCO-${i}-${lat}`, km, lat, -11.1, 3, 1.8, 3, concreto);
        }
        this._caixa(mes, `${o.id}-TRAVESSA-${i}`, km, 0, -0.7, 6.5, 1.1, 1.6, concreto);
      }
    }
  }

  atualizar() {
    const v = this.v, objeto = new THREE.Object3D();
    for (const m of this.pecas) {
      const a = v.projeto.atividades.find(a => a.id === m.userData.atividadeId);
      const e = v.estado4d && v.estado4d[m.userData.atividadeId];
      const passa = a && v.filtro(a), sel = v.selecionada === m.userData.atividadeId;
      m.visible = !!(passa || sel || !v.ocultarFiltrados);
      m.userData.selecionavel = !!(passa || sel);
      m.material.opacity = !passa && !sel ? 0.06 : e && e.fracao > 0 ? 1 : 0.22;
      m.material.emissive.setHex(sel ? 0x174f9c : 0);
      m.material.depthWrite = m.material.opacity >= 1;
    }
    for (const { inst, kms, atividade: a } of this.dormentes) {
      const e = v.estado4d && v.estado4d[a.id];
      const limite = a.km_ini + (a.km_fim - a.km_ini) * (e ? e.fracao : 0);
      kms.forEach((km, i) => {
        const p = v._ponto(km);
        objeto.position.set(p.x, p.cota + 2.27, p.z);
        objeto.rotation.set(0, Math.atan2(p.tx, p.tz), 0);
        // No nível reduzido há amostragem visual; a contagem não é um quantitativo.
        objeto.scale.setScalar(km <= limite ? 1 : 0.001);
        objeto.updateMatrix(); inst.setMatrixAt(i, objeto.matrix);
      });
      inst.instanceMatrix.needsUpdate = true;
      inst.computeBoundingSphere();
    }
  }

  descartar() {
    this.v.scene.remove(this.grupo);
    this.recursos.forEach(r => r.dispose());
    this.grupo.clear();
  }
}
