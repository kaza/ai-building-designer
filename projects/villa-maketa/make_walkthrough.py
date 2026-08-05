"""Bundle villa.glb into a single self-contained walkthrough HTML.

    .venv/bin/python projects/villa-maketa/make_walkthrough.py

Validates the GLB (magic, version, chunk lengths, no cameras/cutters left),
base64-embeds it into an HTML template with Three.js pointer-lock free-fly
controls, and writes output/walkthrough.html. Three.js itself is pinned from
a CDN (import map) — the page needs internet, but no local web server:
GLTFLoader.parseAsync() gets the bytes directly, so file:// double-click works.
"""
import base64
import json
import struct
import sys
from pathlib import Path

OUT_DIR = Path(__file__).parent / "output"
GLB = OUT_DIR / "villa.glb"
HTML = OUT_DIR / "walkthrough.html"

THREE_VERSION = "0.170.0"


# Helpers export_glb.py must have pruned. Exact match on the Blender base
# name (before any ".001" suffix) — a prefix test would flag e.g. "Sunshade".
HELPER_NAMES = {"Sun", "CamPersp", "CamTop", "Target"}


def validate_glb(data: bytes) -> dict:
    if len(data) < 20:
        sys.exit(f"ERROR: file too short to be a GLB ({len(data)} bytes)")
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        sys.exit(f"ERROR: not a GLB (magic={magic!r})")
    if version != 2:
        sys.exit(f"ERROR: unsupported glTF container version {version}")
    if length != len(data):
        sys.exit(f"ERROR: header length {length} != file length {len(data)}")
    # Walk every chunk: 8-byte header + 4-byte-aligned payload, no trailing junk.
    doc = None
    offset = 12
    while offset < length:
        if offset + 8 > length:
            sys.exit(f"ERROR: truncated chunk header at offset {offset}")
        chunk_len, chunk_type = struct.unpack_from("<I4s", data, offset)
        if chunk_len % 4 != 0:
            sys.exit(f"ERROR: chunk {chunk_type!r} length {chunk_len} not 4-byte aligned")
        if offset + 8 + chunk_len > length:
            sys.exit(f"ERROR: chunk {chunk_type!r} overruns the file")
        if offset == 12:
            if chunk_type != b"JSON":
                sys.exit(f"ERROR: first chunk is {chunk_type!r}, expected JSON")
            doc = json.loads(data[offset + 8 : offset + 8 + chunk_len])
        offset += 8 + chunk_len
    if offset != length:
        sys.exit(f"ERROR: {length - offset} trailing bytes after the last chunk")
    if doc.get("asset", {}).get("version") != "2.0":
        sys.exit(f"ERROR: unexpected glTF asset version {doc.get('asset')}")
    if not doc.get("meshes"):
        sys.exit("ERROR: GLB contains no meshes")
    if not doc.get("materials"):
        sys.exit("ERROR: GLB contains no materials")
    if doc.get("cameras"):
        sys.exit("ERROR: cameras leaked into the GLB — export_glb.py prune failed")
    leftovers = [
        name
        for n in doc.get("nodes", [])
        if (name := n.get("name", "")).startswith("StairwellCutter")
        or name.split(".")[0] in HELPER_NAMES
    ]
    if leftovers:
        sys.exit(f"ERROR: helper objects leaked into the GLB: {leftovers}")
    print(
        f"GLB ok: {len(data) / 1024:.0f} KB, "
        f"{len(doc['meshes'])} meshes, {len(doc['materials'])} materials"
    )
    return doc


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Villa Maketa — walkthrough</title>
<style>
  html, body { margin: 0; height: 100%; overflow: hidden; background: #101418; }
  #overlay {
    position: absolute; inset: 0; display: flex; flex-direction: column;
    align-items: center; justify-content: center; gap: 0.6em; cursor: pointer;
    color: #e8e4da; font: 16px/1.5 -apple-system, system-ui, sans-serif;
    background: rgba(10, 14, 18, 0.75); z-index: 10; text-align: center;
  }
  #overlay h1 { font-size: 22px; margin: 0; font-weight: 600; }
  #overlay.hidden { display: none; }
  #error {
    position: absolute; left: 12px; bottom: 12px; max-width: 60ch; z-index: 20;
    color: #ff6b6b; font: 13px/1.4 ui-monospace, monospace; white-space: pre-wrap;
  }
</style>
</head>
<body>
<div id="overlay"><h1>Villa Maketa</h1>
  <div id="overlay-msg">Loading scene…</div>
  <div>WASD — kretanje &nbsp;·&nbsp; miš — pogled &nbsp;·&nbsp; Shift — brzo<br>
       Space / C — gore / dolje &nbsp;·&nbsp; Esc — izlaz</div>
</div>
<div id="error"></div>
<script type="importmap">
{
  "imports": {
    "three": "https://cdn.jsdelivr.net/npm/three@__THREE_VERSION__/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@__THREE_VERSION__/examples/jsm/"
  }
}
</script>
<script id="glb" type="application/octet-stream">__GLB_BASE64__</script>
<script type="module">
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { PointerLockControls } from 'three/addons/controls/PointerLockControls.js';

const overlay = document.getElementById('overlay');
const overlayMsg = document.getElementById('overlay-msg');
const errorBox = document.getElementById('error');
const fatal = (err) => {
  console.error(err);
  errorBox.textContent = 'ERROR: ' + (err && err.message ? err.message : err);
  overlayMsg.textContent = 'Failed to load — see message bottom-left.';
};

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x87b5e0);
scene.fog = new THREE.Fog(0x87b5e0, 60, 220);

// Blender (x, y, z) -> three.js (x, z, -y). Start outside the SE entrance,
// eye height 1.7 m, looking north (three.js -Z).
const camera = new THREE.PerspectiveCamera(70, innerWidth / innerHeight, 0.05, 500);
camera.position.set(8.2, 1.7, 4.0);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(innerWidth, innerHeight);
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
document.body.appendChild(renderer.domElement);

scene.add(new THREE.HemisphereLight(0xcfe3ff, 0x8a7a66, 1.1));
const sun = new THREE.DirectionalLight(0xfff1dd, 2.4);
sun.position.set(35, 60, 25);
scene.add(sun);

// --- load the embedded GLB -------------------------------------------------
let ready = false;
try {
  // fetch() decodes the base64 natively — faster than a JS byte loop, and a
  // decode failure lands in the same catch as a parse failure.
  const b64 = document.getElementById('glb').textContent.trim();
  const buffer = await (await fetch('data:application/octet-stream;base64,' + b64)).arrayBuffer();
  const gltf = await new GLTFLoader().parseAsync(buffer, '');
  scene.add(gltf.scene);
  const bbox = new THREE.Box3().setFromObject(gltf.scene);
  const size = bbox.getSize(new THREE.Vector3());
  console.log('villa bbox (m):', size.x.toFixed(1), size.y.toFixed(1), size.z.toFixed(1));
  if (size.length() < 1) throw new Error('scene bounding box is degenerate: ' + size.toArray());
  ready = true;
  overlayMsg.textContent = 'Klikni za start';
  // #debug[=x,y,z[,yawDeg]]: show the scene without pointer lock, optionally
  // placing the camera (three.js coords) — headless screenshots, triage.
  if (location.hash.startsWith('#debug')) {
    overlay.classList.add('hidden');
    const spec = location.hash.split('=')[1];
    if (spec) {
      const [x, y, z, yaw, pitch] = spec.split(',').map(Number);
      if ([x, y, z].every(Number.isFinite)) camera.position.set(x, y, z);
      else console.warn('#debug: ignoring malformed position', spec);
      if (Number.isFinite(yaw)) {
        const pitchRad = Number.isFinite(pitch) ? pitch * Math.PI / 180 : 0;
        camera.rotation.set(pitchRad, yaw * Math.PI / 180, 0, 'YXZ');
      }
    }
  }
} catch (err) {
  fatal(err);
}

// --- controls ---------------------------------------------------------------
const controls = new PointerLockControls(camera, renderer.domElement);
const keys = new Set();
const clearKeys = () => keys.clear();

overlay.addEventListener('click', () => { if (ready) controls.lock(); });
controls.addEventListener('lock', () => overlay.classList.add('hidden'));
controls.addEventListener('unlock', () => { clearKeys(); overlay.classList.remove('hidden'); });
document.addEventListener('pointerlockerror', () =>
  fatal(new Error('pointer lock rejected by the browser — click the page again')));
addEventListener('blur', clearKeys);
document.addEventListener('visibilitychange', () => { if (document.hidden) clearKeys(); });
document.addEventListener('keydown', (e) => {
  if (e.code === 'Space') e.preventDefault();
  keys.add(e.code);
});
document.addEventListener('keyup', (e) => keys.delete(e.code));
addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

const clock = new THREE.Clock();
const move = new THREE.Vector3();
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(), 0.1); // clamp after tab suspension
  if (controls.isLocked) {
    const speed = keys.has('ShiftLeft') || keys.has('ShiftRight') ? 12 : 4;
    move.set(
      (keys.has('KeyD') ? 1 : 0) - (keys.has('KeyA') ? 1 : 0),
      0,
      (keys.has('KeyW') ? 1 : 0) - (keys.has('KeyS') ? 1 : 0),
    );
    if (move.lengthSq() > 0) move.normalize();
    controls.moveRight(move.x * speed * dt);
    controls.moveForward(move.z * speed * dt);
    const up = (keys.has('Space') ? 1 : 0) - (keys.has('KeyC') ? 1 : 0);
    camera.position.y += up * speed * dt;
  }
  renderer.render(scene, camera);
});
</script>
</body>
</html>
"""


def main():
    data = GLB.read_bytes()
    validate_glb(data)
    b64 = base64.b64encode(data).decode("ascii")
    html = TEMPLATE.replace("__THREE_VERSION__", THREE_VERSION).replace("__GLB_BASE64__", b64)
    HTML.write_text(html, encoding="utf-8")
    print(f"wrote {HTML} ({HTML.stat().st_size / 1024:.0f} KB)")


main()
