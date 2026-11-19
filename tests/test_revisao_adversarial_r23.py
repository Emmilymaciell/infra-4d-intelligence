"""Estado visual da revisão; Three.js real em cópia isolada, sem GPU ou mutação no fonte."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_revisao_sem_mudancas_desfaz_isolamento(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node indisponível; caso de renderer coberto no e2e de navegador")
    raiz = Path(__file__).resolve().parents[1]
    shutil.copytree(raiz / "web", tmp_path / "web")
    (tmp_path / "package.json").write_text('{"type":"module"}', encoding="utf-8")
    three = tmp_path / "node_modules" / "three"
    shutil.copytree(raiz / "web/vendor/three", three)
    (three / "package.json").write_text(
        '{"type":"module","exports":{".":"./three.module.min.js",'
        '"./addons/controls/OrbitControls.js":"./OrbitControls.js",'
        '"./addons/loaders/GLTFLoader.js":"./loaders/GLTFLoader.js"}}', encoding="utf-8")
    runner = tmp_path / "verificar.mjs"
    runner.write_text('''
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { Viewer3D } from './web/viewer3d.js';
const v = Object.create(Viewer3D.prototype);
v.scene = new THREE.Scene(); v.grupo = new THREE.Group(); v.scene.add(v.grupo);
v.modoGeo = 'sintetica';
v.grupoRevisao = new THREE.Group(); v.scene.add(v.grupoRevisao);
const m = new THREE.Mesh(new THREE.BoxGeometry(12, 1.25, 8),new THREE.MeshStandardMaterial());
v.grupoRevisao.add(m); v.pecasRevisao = [m];
// Coloração/estado 4D fora do escopo; método real de visibilidade permanece ativo.
v.recolorir = () => v._aplicarIsolamentoRevisao();
assert.equal(v.isolarRevisao(true), true);
assert.equal(v.grupo.visible, false);
v.mostrarRevisao({revision:'sem-mudancas',relatorio:{mudancas:[]},linhas_locais:[]});
assert.equal(v.pecasRevisao.length, 0);
assert.equal(v.revisaoIsolada, false, 'revisao vazia deve restaurar referencia');
assert.equal(v.grupo.visible, true);
''', encoding="utf-8")
    resultado = subprocess.run([node, str(runner)], cwd=tmp_path, capture_output=True, text=True)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
