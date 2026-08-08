"""Standalone FEM X-ray page (specs/fem-xray.md).

Generic for any project: fetches the fem-field.json envelope (URL is a
placeholder that publish.py pins to the SHA-named asset), builds one
batched BufferGeometry per element kind, camera framed from the data's
own bounding box, toggles only for kinds actually present, assumptions
and load balance printed on screen. Same color ramp as the walkthrough
Loads view: gray -> amber for 0-100%, red reserved for >= 100%.
"""

from __future__ import annotations

from pathlib import Path

FIELD_URL_PLACEHOLDER = "fem-field.json"

_TEMPLATE = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ — structural X-ray</title>
<style>
  body { margin:0; overflow:hidden; background:#a9c3e6; font:13px system-ui; }
  #hud, #meta { position:fixed; background:rgba(20,22,30,.85); color:#eee;
                padding:10px 14px; border-radius:10px; z-index:5; }
  #hud { top:10px; left:10px; }
  #hud label { display:block; margin:2px 0; cursor:pointer; }
  #meta { bottom:12px; right:12px; max-width:340px; font-size:11px;
          color:#bbb; }
  #tip { position:fixed; pointer-events:none; background:rgba(20,22,30,.92);
         color:#fff; padding:4px 9px; border-radius:6px; display:none;
         z-index:6; }
  #legend { position:fixed; bottom:12px; left:50%;
            transform:translateX(-50%); background:rgba(20,22,30,.85);
            color:#eee; padding:8px 14px; border-radius:10px; z-index:5;
            text-align:center; }
  #bar { width:260px; height:12px; border-radius:6px; margin-top:4px;
         background:linear-gradient(90deg,#dedede 0%,#f9c74f 70%,
                                    #f3722c 99%,#c62828 100%); }
  #load { position:fixed; top:50%; left:50%; transform:translate(-50%,-50%);
          color:#223; font:600 15px system-ui; z-index:4; }
</style>
</head>
<body>
<div id="load">loading structural field…</div>
<div id="hud"><b>show</b></div>
<div id="tip"></div>
<div id="legend">% of capacity used <div id="bar"></div>
  <div style="display:flex;justify-content:space-between;width:260px">
    <span>0%</span><span>70%</span>
    <span style="color:#ff8a80">&ge;100% red</span></div>
</div>
<div id="meta"></div>
<script type="importmap">
{ "imports": {
  "three": "https://unpkg.com/three@0.168.0/build/three.module.js",
  "three/addons/": "https://unpkg.com/three@0.168.0/examples/jsm/" } }
</script>
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

function ramp(u) {
  const c = new THREE.Color();
  if (u >= 1.0) return c.set(0xc62828);
  const t = Math.max(0, Math.min(1, u));
  if (t < 0.7) c.lerpColors(new THREE.Color(0xdedede),
                            new THREE.Color(0xf9c74f), t / 0.7);
  else c.lerpColors(new THREE.Color(0xf9c74f),
                    new THREE.Color(0xf3722c), (t - 0.7) / 0.3);
  return c;
}

let env;
try {
  const resp = await fetch('__FIELD_URL__');
  if (!resp.ok) throw new Error('HTTP ' + resp.status);
  env = await resp.json();
  if (env.schema !== 1) throw new Error('unknown field schema ' + env.schema);
} catch (err) {
  document.getElementById('load').textContent =
    'could not load the structural field: ' + err.message;
  throw err;
}
document.getElementById('load').remove();
document.getElementById('meta').innerHTML =
  '<b>assumptions</b><br>' + env.assumptions.join('<br>') +
  '<br>load balance ' + env.balance +
  (env.unresolved.length ? '<br><b>unresolved</b><br>'
    + env.unresolved.join('<br>') : '');

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xa9c3e6);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(innerWidth, innerHeight);
document.body.appendChild(renderer.domElement);

const { n, elem, u, pos } = env.quads;
const box = new THREE.Box3();
for (let i = 0; i < pos.length; i += 3)
  box.expandByPoint(new THREE.Vector3(pos[i], pos[i + 1], pos[i + 2]));
const ctr = box.getCenter(new THREE.Vector3());
const size = box.getSize(new THREE.Vector3()).length();

const camera = new THREE.PerspectiveCamera(
  55, innerWidth / innerHeight, 0.1, size * 20);
camera.up.set(0, 0, 1);
camera.position.set(ctr.x - size * 0.7, ctr.y - size * 0.9, ctr.z + size * 0.6);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.copy(ctr);
controls.update();

const byKind = {};
for (let q = 0; q < n; q++) {
  const kind = env.elems[elem[q]].kind;
  (byKind[kind] ||= []).push(q);
}
const meshes = {}, lookup = {};
for (const [kind, ids] of Object.entries(byKind)) {
  const p = [], col = [];
  for (const q of ids) {
    const base = q * 12;
    const cs = [0, 1, 2, 3].map(i =>
      [pos[base + 3 * i], pos[base + 3 * i + 1], pos[base + 3 * i + 2]]);
    const cx = (cs[0][0] + cs[1][0] + cs[2][0] + cs[3][0]) / 4;
    const cy = (cs[0][1] + cs[1][1] + cs[2][1] + cs[3][1]) / 4;
    const cz = (cs[0][2] + cs[1][2] + cs[2][2] + cs[3][2]) / 4;
    const s = 0.94;
    const sc = cs.map(v => [cx + (v[0] - cx) * s, cy + (v[1] - cy) * s,
                            cz + (v[2] - cz) * s]);
    for (const tri of [[0, 1, 2], [0, 2, 3]])
      for (const i of tri) p.push(...sc[i]);
    const color = ramp(u[q]);
    for (let i = 0; i < 6; i++) col.push(color.r, color.g, color.b);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(p, 3));
  g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  const mesh = new THREE.Mesh(g, new THREE.MeshBasicMaterial(
    { vertexColors: true, side: THREE.DoubleSide }));
  scene.add(mesh);
  meshes[kind] = mesh;
  lookup[kind] = ids;
  const label = document.createElement('label');
  label.innerHTML = `<input type="checkbox" checked> ${kind}s`;
  label.querySelector('input').onchange = e =>
    { mesh.visible = e.target.checked; };
  document.getElementById('hud').appendChild(label);
}

const ray = new THREE.Raycaster(), mouse = new THREE.Vector2();
const tip = document.getElementById('tip');
addEventListener('mousemove', ev => {
  mouse.set(ev.clientX / innerWidth * 2 - 1,
            -(ev.clientY / innerHeight) * 2 + 1);
  ray.setFromCamera(mouse, camera);
  const hits = ray.intersectObjects(
    Object.values(meshes).filter(mm => mm.visible));
  if (hits.length) {
    const kind = Object.keys(meshes).find(k => meshes[k] === hits[0].object);
    const q = lookup[kind][Math.floor(hits[0].faceIndex / 2)];
    const el = env.elems[elem[q]];
    const comps = ['vertical compression', 'horizontal tension',
                   'vertical tension', 'bending'];
    const g = (env.quads.g || [])[q];
    const s = (env.quads.s || [])[q];
    tip.textContent =
      `${el.name} — this fragment ${(u[q] * 100).toFixed(0)}%` +
      (g === undefined ? '' :
        ` · ${comps[g]}${s ? ' ' + (Math.abs(s) / 1000).toFixed(2) + ' MPa' : ''}`) +
      ` (element max ${(el.u * 100).toFixed(0)}%)`;
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
renderer.setAnimationLoop(() => {
  controls.update();
  renderer.render(scene, camera);
});
</script>
</body>
</html>
"""


def write_xray_page(dest: Path, title: str,
                    field_url: str = FIELD_URL_PLACEHOLDER) -> None:
    dest.write_text(_TEMPLATE.replace("__TITLE__", title)
                             .replace("__FIELD_URL__", field_url))
