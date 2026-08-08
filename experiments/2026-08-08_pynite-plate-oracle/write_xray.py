"""Generate the structural X-ray page: every FEM quad rendered as a 3D
fragment colored by its own utilization (same ramp as the walkthrough
Loads view). Standalone three.js page, field JSON embedded.

Run: ../../.venv/bin/python write_xray.py logs/fem-field-mesh0.18.json <dest.html>
"""

import json
import sys
from pathlib import Path

field_path, dest = Path(sys.argv[1]), Path(sys.argv[2])
field = json.loads(field_path.read_text())

TEMPLATE = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>villa-maketa — structural X-ray (FEM fragments)</title>
<style>
  body { margin:0; overflow:hidden; background:#a9c3e6; font:13px system-ui; }
  #hud { position:fixed; top:10px; left:10px; background:rgba(20,22,30,.85);
         color:#eee; padding:10px 14px; border-radius:10px; z-index:5; }
  #hud label { display:block; margin:2px 0; cursor:pointer; }
  #tip { position:fixed; pointer-events:none; background:rgba(20,22,30,.92);
         color:#fff; padding:4px 9px; border-radius:6px; display:none; z-index:6; }
  #legend { position:fixed; bottom:12px; left:50%; transform:translateX(-50%);
            background:rgba(20,22,30,.85); color:#eee; padding:8px 14px;
            border-radius:10px; z-index:5; text-align:center; }
  #bar { width:260px; height:12px; border-radius:6px; margin-top:4px;
         background:linear-gradient(90deg,#dedede 0%,#f9c74f 70%,#f3722c 99%,#c62828 100%); }
  #banner { position:fixed; top:0; left:50%; transform:translateX(-50%);
            background:#7c2d92; color:#fff; font-weight:600; font-size:12px;
            padding:4px 14px; border-radius:0 0 8px 8px; z-index:5; }
</style>
</head>
<body>
<div id="banner">FEM X-RAY — per-fragment stress (experiment; ring beams included)</div>
<div id="hud">
  <b>show</b>
  <label><input type="checkbox" id="cb-roof" checked> roofs</label>
  <label><input type="checkbox" id="cb-wall" checked> walls</label>
  <label><input type="checkbox" id="cb-beam" checked> beams</label>
  <label><input type="checkbox" id="cb-slab" checked> floor slab</label>
  <div style="margin-top:6px;color:#aaa">drag orbit &middot; wheel zoom &middot; hover a fragment</div>
</div>
<div id="tip"></div>
<div id="legend">% of capacity used <div id="bar"></div>
  <div style="display:flex;justify-content:space-between;width:260px">
    <span>0%</span><span>70%</span><span style="color:#ff8a80">&ge;100% red</span></div>
</div>
<script type="importmap">
{ "imports": {
  "three": "https://unpkg.com/three@0.168.0/build/three.module.js",
  "three/addons/": "https://unpkg.com/three@0.168.0/examples/jsm/" } }
</script>
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const FIELD = __FIELD__;

function ramp(u) {
  const c = new THREE.Color();
  if (u >= 1.0) return c.set(0xc62828);
  const t = Math.max(0, Math.min(1, u));
  if (t < 0.7) c.lerpColors(new THREE.Color(0xdedede), new THREE.Color(0xf9c74f), t / 0.7);
  else c.lerpColors(new THREE.Color(0xf9c74f), new THREE.Color(0xf3722c), (t - 0.7) / 0.3);
  return c;
}

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xa9c3e6);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(innerWidth, innerHeight);
document.body.appendChild(renderer.domElement);

const camera = new THREE.PerspectiveCamera(55, innerWidth / innerHeight, 0.1, 500);
camera.up.set(0, 0, 1);
camera.position.set(-9, -13, 9);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(5, 6, 0.5);
controls.update();

const kinds = { roof: [], wall: [], beam: [], slab: [] };
for (const q of FIELD) {
  if (q.k === 'wall' || q.k === 'beam') kinds[q.k].push(q);
  else (q.e.startsWith('Roof') ? kinds.roof : kinds.slab).push(q);
}

const meshes = {}, quadLists = {};
for (const [kind, quads] of Object.entries(kinds)) {
  const pos = [], col = [];
  for (const q of quads) {
    const [a, b, c, d] = q.c;
    const cx = (a[0]+b[0]+c[0]+d[0])/4, cy=(a[1]+b[1]+c[1]+d[1])/4, cz=(a[2]+b[2]+c[2]+d[2])/4;
    const s = 0.94;   // shrink so fragment seams are visible
    const p = [a,b,c,d].map(v => [cx+(v[0]-cx)*s, cy+(v[1]-cy)*s, cz+(v[2]-cz)*s]);
    for (const tri of [[0,1,2],[0,2,3]]) for (const i of tri) pos.push(...p[i]);
    const color = ramp(q.u);
    for (let i = 0; i < 6; i++) col.push(color.r, color.g, color.b);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  const mat = new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide });
  const mesh = new THREE.Mesh(g, mat);
  scene.add(mesh);
  meshes[kind] = mesh;
  quadLists[kind] = quads;
}

for (const kind of ['roof', 'wall', 'beam', 'slab'])
  document.getElementById('cb-' + kind).onchange = e => {
    meshes[kind].visible = e.target.checked;
  };

const ray = new THREE.Raycaster(), mouse = new THREE.Vector2();
const tip = document.getElementById('tip');
addEventListener('mousemove', ev => {
  mouse.set(ev.clientX / innerWidth * 2 - 1, -(ev.clientY / innerHeight) * 2 + 1);
  ray.setFromCamera(mouse, camera);
  const hits = ray.intersectObjects(Object.values(meshes).filter(m => m.visible));
  if (hits.length) {
    const mesh = hits[0].object;
    const kind = Object.keys(meshes).find(k1 => meshes[k1] === mesh);
    const q = quadLists[kind][Math.floor(hits[0].faceIndex / 2)];
    tip.textContent = `${q.e} — ${(q.u * 100).toFixed(0)}% of capacity`;
    tip.style.left = (ev.clientX + 14) + 'px';
    tip.style.top = (ev.clientY + 10) + 'px';
    tip.style.display = 'block';
  } else tip.style.display = 'none';
});

addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); });
</script>
</body>
</html>
"""

dest.write_text(TEMPLATE.replace("__FIELD__", json.dumps(field)))
print(f"x-ray at {dest} ({len(field)} fragments)")
