"""Build the walkthrough HTML that loads villa.glb as a separate file.

    .venv/bin/python projects/villa-maketa/make_walkthrough.py

Validates the GLB (magic, version, chunk lengths, no cameras/cutters left)
and writes output/walkthrough.html, which fetches ./villa.glb at runtime.
This is a WEB-SERVER deliverable (owner decision 2026-08-05 — the walkthrough
becomes a hosted feature): browsers block fetch() from file://, so for local
viewing serve the output directory:

    python3 -m http.server 8000 -d projects/villa-maketa/output
    open http://localhost:8000/walkthrough.html

The page detects file:// and says exactly that instead of failing silently.
"""
import json
import struct
import sys
from pathlib import Path

OUT_DIR = Path(__file__).parent / "output"
GLB = OUT_DIR / "villa.glb"
HTML = OUT_DIR / "walkthrough.html"
BUILDING = Path(__file__).parent / "building.json"

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


def element_tags() -> dict:
    """Sanitized element name -> plan tag (W3, D5, Win4, ST1).

    Mirrors Story.ensure_tags() numbering (per story, in element order) so
    the walkthrough info card and the 2D plan speak the same ids — that is
    how the owner references elements.
    """
    doc = json.loads(BUILDING.read_text())
    tags: dict[str, str] = {}
    for story in doc.get("stories", []):
        for key, prefix in (("walls", "W"), ("doors", "D"),
                            ("windows", "Win"), ("staircases", "ST")):
            for i, el in enumerate(story.get(key, []), start=1):
                tag = el.get("tag") or f"{prefix}{i}"
                name = el.get("name", "")
                if name:
                    tags.setdefault(name.replace(" ", "_"), tag)
    return tags


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
  #reticle {
    position: absolute; left: 50%; top: 50%; width: 14px; height: 14px;
    margin: -7px 0 0 -7px; z-index: 5; pointer-events: none;
    mix-blend-mode: difference; display: none;
  }
  #reticle::before, #reticle::after {
    content: ""; position: absolute; background: #fff;
  }
  #reticle::before { left: 6px; top: 0; width: 2px; height: 14px; }
  #reticle::after { left: 0; top: 6px; width: 14px; height: 2px; }
  #hud {
    position: absolute; right: 12px; top: 12px; z-index: 6; max-width: 34ch;
    color: #e8e4da; font: 13px/1.5 ui-monospace, monospace; text-align: right;
    text-shadow: 0 1px 3px rgba(0,0,0,0.8); white-space: pre-line;
    pointer-events: none;
  }
  #labels { position: absolute; inset: 0; z-index: 4; pointer-events: none; }
  .mlabel {
    color: #fff; background: rgba(16, 20, 24, 0.85); padding: 2px 8px;
    border-radius: 4px; font: 13px/1.4 ui-monospace, monospace;
    border: 1px solid rgba(255,255,255,0.25);
  }
</style>
</head>
<body>
<div id="overlay"><h1>Villa Maketa</h1>
  <div id="overlay-msg">Loading scene…</div>
  <div>WASD — move &nbsp;·&nbsp; mouse — look &nbsp;·&nbsp; Shift — fast<br>
       Space / C — up / down &nbsp;·&nbsp; Esc — release<br>
       I — what am I looking at &nbsp;·&nbsp; M — measure &nbsp;·&nbsp; R — roof on/off &nbsp;·&nbsp; P — photo</div>
</div>
<div id="reticle"></div>
<div id="hud"></div>
<div id="labels"></div>
<div id="error"></div>
<script type="importmap">
{
  "imports": {
    "three": "https://cdn.jsdelivr.net/npm/three@__THREE_VERSION__/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@__THREE_VERSION__/examples/jsm/"
  }
}
</script>
<script type="module">
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { PointerLockControls } from 'three/addons/controls/PointerLockControls.js';
import { CSS2DObject, CSS2DRenderer } from 'three/addons/renderers/CSS2DRenderer.js';

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

// CSS2D layer for measurement labels (crisp DOM text, no textures)
const labelRenderer = new CSS2DRenderer({ element: document.getElementById('labels') });
labelRenderer.setSize(innerWidth, innerHeight);

scene.add(new THREE.HemisphereLight(0xcfe3ff, 0x8a7a66, 1.1));
const sun = new THREE.DirectionalLight(0xfff1dd, 2.4);
sun.position.set(35, 60, 25);
scene.add(sun);

// --- load villa.glb ----------------------------------------------------------
let ready = false;
let modelRoot = null;  // raycast target: the loaded villa only
const roofNodes = [];  // dollhouse mode: nodes hidden by the R toggle
let roofVisible = true;
function toggleRoof() {
  if (!roofNodes.length) return;
  roofVisible = !roofVisible;
  for (const n of roofNodes) n.visible = roofVisible;
}

// P — save a PNG of the current view. The filename carries the exact camera
// (position + yaw/pitch, the same numbers #debug= accepts), so a shot can be
// reproduced with walkthrough.html#debug=<numbers from the filename>.
function screenshot() {
  renderer.render(scene, camera);  // fresh frame in the buffer for toDataURL
  const p = camera.position;
  const spec = [p.x.toFixed(2), p.y.toFixed(2), p.z.toFixed(2),
                (camera.rotation.y * 180 / Math.PI).toFixed(1),
                (camera.rotation.x * 180 / Math.PI).toFixed(1)].join(',');
  const a = document.createElement('a');
  a.download = 'villa-shot_' + spec.replaceAll(',', '_') + '.png';
  a.href = renderer.domElement.toDataURL('image/png');
  a.click();
}
try {
  if (location.protocol === 'file:') {
    throw new Error(
      'Browsers block loading villa.glb from file://. Serve this folder instead:\\n' +
      '  python3 -m http.server 8000 -d <this directory>\\n' +
      'then open http://localhost:8000/walkthrough.html');
  }
  const resp = await fetch('villa.glb');
  if (!resp.ok) throw new Error('fetching villa.glb failed: HTTP ' + resp.status);
  const gltf = await new GLTFLoader().parseAsync(await resp.arrayBuffer(), '');
  scene.add(gltf.scene);
  modelRoot = gltf.scene;
  // Dollhouse mode: the roof group (roof slabs + soffit boards + their
  // frames) toggles with R, like lifting the maquette's cardboard lid.
  modelRoot.traverse((n) => {
    if (/^IfcSlab_Roof_|^Soffit/.test(n.name)) roofNodes.push(n);
  });
  if (!roofNodes.length) console.warn('no roof nodes found — R toggle disabled');
  const bbox = new THREE.Box3().setFromObject(gltf.scene);
  const size = bbox.getSize(new THREE.Vector3());
  console.log('villa bbox (m):', size.x.toFixed(1), size.y.toFixed(1), size.z.toFixed(1));
  if (size.length() < 1) throw new Error('scene bounding box is degenerate: ' + size.toArray());
  ready = true;
  overlayMsg.textContent = 'Click to start';
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
    // ?roof=0 — test seam for the R toggle (headless screenshots), same
    // #debug gating as ?measure.
    if (new URLSearchParams(location.search).get('roof') === '0') toggleRoof();
  }
} catch (err) {
  fatal(err);
}

// --- measurement + info tools (specs/walkthrough-measurement.md) -------------
const hud = document.getElementById('hud');
const reticle = document.getElementById('reticle');
const raycaster = new THREE.Raycaster();
const CENTER = new THREE.Vector2(0, 0);
const measureGroup = new THREE.Group();
scene.add(measureGroup);

let measureMode = false;
let pendingPoint = null;   // first click of the current measurement
let rubberLine = null;     // live preview line
let infoText = '';

function setHud() {
  const mode = measureMode
    ? (pendingPoint ? 'MEASURE — click second point' : 'MEASURE — click first point')
    : '';
  hud.textContent = [mode, infoText].filter(Boolean).join('\\n');
}

function centerHit() {
  if (!modelRoot) return null;
  raycaster.setFromCamera(CENTER, camera);
  const hits = raycaster.intersectObject(modelRoot, true);
  // Raycaster does NOT respect .visible — skip hits inside a hidden chain
  // (a roof toggled off must not swallow info/measure rays).
  const visible = (o) => { for (; o; o = o.parent) if (!o.visible) return false; return true; };
  return hits.find((h) => visible(h.object)) ?? null;
}

// Walk up to the semantic ancestor: imported asset children are 'Object_N',
// instance roots end in '_root'. The topmost semantic name below the model
// root labels the object; its node gives the WHOLE object's bbox.
function semanticNode(obj) {
  let node = obj;
  let named = /^Object_\\d+$/.test(obj.name) ? null : obj;
  while (node.parent && node.parent !== modelRoot && node.parent !== scene) {
    node = node.parent;
    if (node.name && !/^Object_\\d+$/.test(node.name)) named = node;
  }
  const label = ((named || node).name || 'unnamed').replace(/_root$/, '');
  return { node: named || node, label };
}

// element plan tags (W3, D5, Win4...) — same ids as the 2D floor plan
const TAGS = __TAGS__;

function displayName(label) {
  // IfcWindow_Living_Window_W1 / IfcWindow_..._frame -> tag + readable name
  const clean = label.replace(/^Ifc\\w+?_/, '').replace(/_frame$/, '');
  const tag = TAGS[clean];
  const pretty = clean.replace(/_/g, ' ');
  return tag ? tag + ' — ' + pretty : (label.startsWith('F_') ? label.slice(2) : pretty);
}

function showInfo() {
  const hit = centerHit();
  if (!hit) { infoText = 'no surface hit'; setHud(); return; }
  const { node, label } = semanticNode(hit.object);
  const size = new THREE.Box3().setFromObject(node).getSize(new THREE.Vector3());
  infoText = displayName(label) + '\\n' +
    'W ' + size.x.toFixed(2) + ' × D ' + size.z.toFixed(2) +
    ' × H ' + size.y.toFixed(2) + ' m\\n' +
    'distance ' + hit.distance.toFixed(2) + ' m';
  setHud();
}

function disposeLine(line) {
  line.geometry.dispose();
  line.material.dispose();
}

function clearMeasurement() {
  for (const child of [...measureGroup.children]) {
    if (child.isLine) disposeLine(child);
    if (child.isCSS2DObject) child.element.remove();
    measureGroup.remove(child);
  }
  pendingPoint = null;
  rubberLine = null;
  delete document.body.dataset.measureReady;
}

const lineMat = () => {
  const m = new THREE.LineBasicMaterial({ color: 0xffd166, depthTest: false });
  return m;
};

function commitMeasurement(a, b) {
  clearMeasurement();
  const geo = new THREE.BufferGeometry().setFromPoints([a, b]);
  const line = new THREE.Line(geo, lineMat());
  line.renderOrder = 999;
  measureGroup.add(line);
  const div = document.createElement('div');
  div.className = 'mlabel';
  div.textContent = a.distanceTo(b).toFixed(2) + ' m';
  const label = new CSS2DObject(div);
  label.position.copy(a.clone().add(b).multiplyScalar(0.5));
  measureGroup.add(label);
  const d = b.clone().sub(a);
  infoText = 'measured ' + a.distanceTo(b).toFixed(2) + ' m\\n' +
    'ΔX ' + Math.abs(d.x).toFixed(2) + '  ΔY ' + Math.abs(d.z).toFixed(2) +
    '  ΔH ' + Math.abs(d.y).toFixed(2);
  setHud();
  document.body.dataset.measureReady = '1';  // headless-test readiness marker
}

function exitMeasureMode() {
  measureMode = false;
  clearMeasurement();
  infoText = '';
  setHud();
}

function measureClick() {
  const hit = centerHit();
  if (!hit) { infoText = 'no surface hit'; setHud(); return; }
  if (!pendingPoint) {
    pendingPoint = hit.point.clone();
    const geo = new THREE.BufferGeometry().setFromPoints([pendingPoint, pendingPoint]);
    rubberLine = new THREE.Line(geo, lineMat());
    rubberLine.renderOrder = 999;
    rubberLine.frustumCulled = false;  // endpoints move; stale bounds would cull it
    measureGroup.add(rubberLine);
  } else {
    commitMeasurement(pendingPoint, hit.point.clone());
  }
  setHud();
}

// scripted measurement for headless verification: only honored under #debug
if (location.hash.startsWith('#debug')) {
  const q = new URLSearchParams(location.search).get('measure');
  if (q && ready) {
    const parts = q.split(',');
    const nums = parts.map(Number);
    if (nums.length === 6 && parts.every(t => t.trim() !== '') &&
        nums.every(Number.isFinite)) {
      commitMeasurement(new THREE.Vector3(...nums.slice(0, 3)),
                        new THREE.Vector3(...nums.slice(3)));
    } else {
      fatal(new Error('?measure= needs exactly six finite numbers, got: ' + q));
    }
  }
  reticle.style.display = 'block';
}

// --- controls ---------------------------------------------------------------
const controls = new PointerLockControls(camera, renderer.domElement);
const keys = new Set();
const clearKeys = () => keys.clear();

overlay.addEventListener('click', () => { if (ready) controls.lock(); });
controls.addEventListener('lock', () => {
  overlay.classList.add('hidden');
  reticle.style.display = 'block';
});
controls.addEventListener('unlock', () => {
  clearKeys();
  overlay.classList.remove('hidden');
  reticle.style.display = 'none';
  exitMeasureMode();  // Esc also abandons any measurement in progress
});
document.addEventListener('pointerlockerror', () =>
  fatal(new Error('pointer lock rejected by the browser — click the page again')));
addEventListener('blur', clearKeys);
document.addEventListener('visibilitychange', () => { if (document.hidden) clearKeys(); });
document.addEventListener('keydown', (e) => {
  if (e.code === 'Space') e.preventDefault();
  keys.add(e.code);
  if (!controls.isLocked) return;
  if (e.code === 'KeyI') showInfo();
  if (e.code === 'KeyM' && !e.repeat) {
    if (measureMode) exitMeasureMode();
    else { measureMode = true; infoText = ''; setHud(); }
  }
  if (e.code === 'KeyR' && !e.repeat) toggleRoof();
  if (e.code === 'KeyP' && !e.repeat) screenshot();
});
document.addEventListener('keyup', (e) => keys.delete(e.code));
renderer.domElement.addEventListener('click', () => {
  if (controls.isLocked && measureMode) measureClick();
});
addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
  labelRenderer.setSize(innerWidth, innerHeight);
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
  // rubber-band: live preview from the first point to the current aim
  if (pendingPoint && rubberLine) {
    const hit = centerHit();
    if (hit) {
      rubberLine.geometry.setFromPoints([pendingPoint, hit.point]);
    }
  }
  renderer.render(scene, camera);
  labelRenderer.render(scene, camera);
});
</script>
</body>
</html>
"""


def main():
    validate_glb(GLB.read_bytes())
    tags = element_tags()
    html = (TEMPLATE
            .replace("__THREE_VERSION__", THREE_VERSION)
            .replace("__TAGS__", json.dumps(tags, sort_keys=True)))
    HTML.write_text(html, encoding="utf-8")
    print(f"wrote {HTML} ({HTML.stat().st_size / 1024:.0f} KB; "
          f"{len(tags)} element tags; loads ./villa.glb at runtime)")


main()
