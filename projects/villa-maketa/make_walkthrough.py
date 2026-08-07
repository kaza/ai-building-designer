"""Build the walkthrough HTML that loads villa.glb as a separate file.

    .venv/bin/python projects/villa-maketa/make_walkthrough.py

Validates the GLB (magic, version, chunk lengths, no cameras/cutters left)
and writes output/walkthrough.html, which fetches ./villa.glb at runtime.
This is a WEB-SERVER deliverable (owner decision 2026-08-05 — the walkthrough
becomes a hosted feature): browsers block fetch() from file://, so for local
viewing serve the output directory — preferably with serve.py, which also
receives F-key feedback submissions (POST /feedback):

    .venv/bin/python projects/villa-maketa/serve.py     # port 8123
    open http://localhost:8123/walkthrough.html

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
    how the owner references elements. Tags repeat per story (the garage
    has its own W1…), so non-ground stories get an initial prefix (G:W3) —
    feedback #007 showed bare garage tags read as ground-floor elements.
    """
    doc = json.loads(BUILDING.read_text())
    tags: dict[str, str] = {}
    for story in doc.get("stories", []):
        story_prefix = ("" if story.get("elevation", 0) == 0
                        else f"{(story.get('name') or 'S')[0]}:")
        for key, prefix in (("walls", "W"), ("doors", "D"),
                            ("windows", "Win"), ("staircases", "ST")):
            for i, el in enumerate(story.get(key, []), start=1):
                tag = el.get("tag") or f"{prefix}{i}"
                name = el.get("name", "")
                if name:
                    tags.setdefault(name.replace(" ", "_"), story_prefix + tag)
    return tags


def storey_bands() -> list:
    """[{name, elevation, height, rooms}] sorted by elevation — the viewer
    shows which storey AND room the camera is in (feedback #007: the owner
    sank through the floor into the garage without noticing; raw
    coordinates broke the feedback conversation)."""
    doc = json.loads(BUILDING.read_text())
    bands = []
    for i, s in enumerate(doc.get("stories", []), start=1):
        spaces = list(s.get("spaces", []))
        for apt in s.get("apartments", []):
            spaces.extend(apt.get("spaces", []))
        elevation = s.get("elevation", 0)
        bands.append({
            "name": s.get("name") or f"Storey {i}",
            "elevation": elevation,
            "height": s.get("height", 3.0),
            "rooms": [
                {"name": sp.get("name") or sp.get("room_type", "room"),
                 "poly": [[v["x"], v["y"]]
                          for v in sp["boundary"]["vertices"]]}
                for sp in spaces if sp.get("boundary")
            ],
        })
    return sorted(bands, key=lambda b: b["elevation"])


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
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
  #draw { position: absolute; inset: 0; z-index: 7; display: none; cursor: crosshair; touch-action: none; }
  #touchui { display: none; }
  body.touch #touchui { display: block; }
  body.touch #overlay-legend { font-size: 12px; }
  body.touch #fbhint { display: none; }  /* keyboard hints mean nothing on touch */
  .tbtn {
    position: absolute; z-index: 6; border: 1px solid rgba(255,255,255,0.35);
    background: rgba(16,20,24,0.55); color: #e8e4da; border-radius: 12px;
    font: 600 18px/1 -apple-system, system-ui, sans-serif;
    padding: 14px 18px; touch-action: none; user-select: none;
    -webkit-user-select: none; -webkit-tap-highlight-color: transparent;
  }
  #btn-fb   { top: 12px; left: 12px; font-size: 15px; }
  #btn-menu { top: 12px; right: 12px; }
  #btn-up   { right: 16px; bottom: 100px; }
  #btn-down { right: 16px; bottom: 28px; }
  body.touch #hud { top: 68px; }
  #menu {
    position: absolute; top: 64px; right: 12px; z-index: 9;
    display: flex; flex-direction: column; gap: 8px;
  }
  #menu .tbtn { position: static; font-size: 15px; }
  #joy {
    position: absolute; left: 24px; bottom: 24px; width: 120px; height: 120px;
    border-radius: 50%; background: rgba(255,255,255,0.07);
    border: 1px solid rgba(255,255,255,0.22); z-index: 5; pointer-events: none;
  }
  #joy-knob {
    position: absolute; left: 50%; top: 50%; width: 52px; height: 52px;
    margin: -26px 0 0 -26px; border-radius: 50%;
    background: rgba(255,255,255,0.3); border: 1px solid rgba(255,255,255,0.4);
  }
  #fbpanel {
    position: absolute; left: 50%; bottom: 18px; transform: translateX(-50%);
    z-index: 8; display: none; flex-direction: column; gap: 6px;
    width: min(64ch, calc(100% - 24px)); box-sizing: border-box;
    background: rgba(16, 20, 24, 0.92);
    border: 1px solid rgba(255,255,255,0.25); border-radius: 8px;
    padding: 10px; color: #e8e4da;
    font: 13px/1.4 -apple-system, system-ui, sans-serif;
  }
  #fbpanel textarea {
    width: 100%; box-sizing: border-box; height: 4em; resize: vertical;
    background: #101418; color: #e8e4da; padding: 6px; font: inherit;
    border: 1px solid rgba(255,255,255,0.25); border-radius: 4px;
  }
  #fbpanel .row { display: flex; gap: 8px; justify-content: flex-end; align-items: center; flex-wrap: wrap; }
  #fbhint { margin-right: auto; opacity: 0.7; }
  #fbpanel button {
    font: inherit; padding: 4px 14px; border-radius: 4px; cursor: pointer;
    border: 1px solid rgba(255,255,255,0.3); background: #2a3440; color: #e8e4da;
  }
  #fbpanel button.primary { background: #3b6ea5; }
  .mlabel {
    color: #fff; background: rgba(16, 20, 24, 0.85); padding: 2px 8px;
    border-radius: 4px; font: 13px/1.4 ui-monospace, monospace;
    border: 1px solid rgba(255,255,255,0.25);
  }
  .fblabel {
    position: absolute; transform: translate(-50%, -50%);
    color: #101418; background: rgba(255, 209, 102, 0.92); padding: 1px 6px;
    border-radius: 3px; font: 12px/1.4 ui-monospace, monospace;
    pointer-events: none; white-space: nowrap;
  }
  #loadbar {
    width: 260px; height: 8px; margin: 10px auto 14px;
    background: rgba(255,255,255,0.15); border-radius: 4px; overflow: hidden;
  }
  #loadbar-fill {
    width: 0%; height: 100%; background: #2b7de9; border-radius: 4px;
  }
</style>
</head>
<body>
<div id="overlay"><h1>Villa Maketa</h1>
  <div id="overlay-msg">Loading scene…</div>
  <div id="loadbar"><div id="loadbar-fill"></div></div>
  <div id="overlay-legend">WASD — move &nbsp;·&nbsp; mouse — look &nbsp;·&nbsp; Shift — fast<br>
       Space / C — up / down &nbsp;·&nbsp; Esc — release<br>
       I — what am I looking at &nbsp;·&nbsp; M — measure &nbsp;·&nbsp; R — roof on/off<br>
       N — names on/off &nbsp;·&nbsp; P — photo &nbsp;·&nbsp; F — feedback (draw + comment)</div>
</div>
<div id="touchui">
  <button class="tbtn" id="btn-fb">&#9998; Feedback</button>
  <button class="tbtn" id="btn-menu">&#9776;</button>
  <div id="menu" hidden>
    <button class="tbtn" id="m-roof">Roof: on</button>
    <button class="tbtn" id="m-names">Names: off</button>
  </div>
  <button class="tbtn" id="btn-up">&#9650;</button>
  <button class="tbtn" id="btn-down">&#9660;</button>
  <div id="joy"><div id="joy-knob"></div></div>
</div>
<div id="reticle"></div>
<div id="hud"></div>
<div id="labels"></div>
<canvas id="draw"></canvas>
<div id="fbpanel">
  <textarea id="fbtext" placeholder="What's wrong here? Drag on the view to mark it."></textarea>
  <div class="row">
    <span id="fbhint">drag — draw &nbsp;·&nbsp; Z — undo stroke &nbsp;·&nbsp; Esc — cancel</span>
    <button id="fbundo">Undo</button>
    <button id="fbcancel">Cancel</button>
    <button id="fbsubmit" class="primary">Submit</button>
  </div>
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
<script type="module">
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { PointerLockControls } from 'three/addons/controls/PointerLockControls.js';
import { CSS2DObject, CSS2DRenderer } from 'three/addons/renderers/CSS2DRenderer.js';

const overlay = document.getElementById('overlay');
const overlayMsg = document.getElementById('overlay-msg');
// Phones/tablets: no pointer lock, no keyboard — touch drag + buttons instead.
const isTouch = matchMedia('(pointer: coarse)').matches ||
  (location.hash.startsWith('#debug') &&
   new URLSearchParams(location.search).get('touch') === '1');  // test seam
if (isTouch) {
  document.body.classList.add('touch');
  document.getElementById('overlay-legend').innerHTML =
    'left half — walk &nbsp;·&nbsp; right half — look around<br>' +
    '&#9650; / &#9660; — up / down &nbsp;·&nbsp; &#9998; Feedback — draw + comment';
}
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

// Canonical camera numbers (position + yaw/pitch) — derived from the LOOK
// DIRECTION, not the raw rotation Euler, so pitch is always in [-90, 90]
// and the numbers replay exactly via #debug= (raw rotation.x can come out
// as e.g. 154° and flips the replayed view — feedback #001/#003 lesson).
function cameraSpec() {
  const d = new THREE.Vector3();
  camera.getWorldDirection(d);
  const yaw = Math.atan2(-d.x, -d.z) * 180 / Math.PI;
  const pitch = Math.asin(Math.max(-1, Math.min(1, d.y))) * 180 / Math.PI;
  const p = camera.position;
  return { yaw, pitch,
           text: [p.x.toFixed(2), p.y.toFixed(2), p.z.toFixed(2),
                  yaw.toFixed(1), pitch.toFixed(1)].join(',') };
}

// P — save a PNG of the current view. The filename carries the exact camera
// (position + yaw/pitch, the same numbers #debug= accepts), so a shot can be
// reproduced with walkthrough.html#debug=<numbers from the filename>.
function screenshot() {
  renderer.render(scene, camera);  // fresh frame in the buffer for toDataURL
  const a = document.createElement('a');
  a.download = 'villa-shot_' + cameraSpec().text.replaceAll(',', '_') + '.png';
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
  // Stream the body so the overlay shows real progress — a 30 MB GLB on a
  // slow link otherwise looks identical to a hung page.
  const total = Number(resp.headers.get('Content-Length')) || 0;
  const reader = resp.body.getReader();
  const chunks = [];
  let received = 0;
  let shownMb = -1;
  const fillEl = document.getElementById('loadbar-fill');
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    received += value.length;
    // Update the DOM at most every ~0.5 MB — per-chunk style writes
    // (64 KB each) throttle the very download they narrate.
    const halfMb = Math.floor(received / 524288);
    if (halfMb === shownMb) continue;
    shownMb = halfMb;
    const mb = (received / 1048576).toFixed(1);
    if (total) {
      const pct = Math.min(100, received / total * 100);
      fillEl.style.width = pct.toFixed(1) + '%';
      overlayMsg.textContent = 'Loading model… ' + mb + ' / ' + (total / 1048576).toFixed(1) + ' MB';
    } else {
      fillEl.style.width = '100%';
      overlayMsg.textContent = 'Loading model… ' + mb + ' MB';
    }
  }
  const buf = new Uint8Array(received);
  let off = 0;
  for (const c of chunks) { buf.set(c, off); off += c.length; }
  overlayMsg.textContent = 'Building scene…';
  const gltf = await new GLTFLoader().parseAsync(buf.buffer, '');
  document.getElementById('loadbar').style.display = 'none';
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
  hud.textContent = [mode, infoText, positionLine()].filter(Boolean).join('\\n');
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

// storey bands (sorted by elevation) — live "where am I" readout
const STOREYS = __STOREYS__;

function storeyAt(h) {
  // exact band first — padded bands overlap at slab level and would
  // mislabel h=0.2 as the storey below (Codex review 2026-08-06)
  return STOREYS.find((s) => h >= s.elevation && h < s.elevation + s.height)
      || STOREYS.find((s) => h >= s.elevation - 0.3 &&
                             h < s.elevation + s.height + 0.3)
      || null;
}

function pointInPoly(x, y, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) &&
        x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

// "Master Bedroom (Ground Floor)" — the language the owner and Claude
// actually share. Model coords: x = three.x, y = −three.z, h = three.y.
function whereAmI() {
  const p = camera.position;
  const mx = p.x;
  const my = -p.z;
  const s = storeyAt(p.y);
  if (!s) {
    return p.y < STOREYS[0].elevation ? 'below ' + STOREYS[0].name
                                      : 'above the roof';
  }
  const room = s.rooms.find((r) => pointInPoly(mx, my, r.poly));
  if (room && room.name !== s.name) return room.name + ' — ' + s.name;
  return (room ? '' : 'outside — ') + s.name;
}

function positionLine() {
  const p = camera.position;
  return whereAmI() + '\\npos ' + p.x.toFixed(1) + ', ' + (-p.z).toFixed(1) +
         ' · h ' + p.y.toFixed(1);
}

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

let touchWalking = false;
const touchMove = { x: 0, z: 0 };
let touchUp = 0;
overlay.addEventListener('click', () => {
  if (!ready) return;
  if (isTouch) {  // pointer lock is rejected on mobile browsers
    touchWalking = true;
    overlay.classList.add('hidden');
    reticle.style.display = 'block';
  } else {
    controls.lock();
  }
});
controls.addEventListener('lock', () => {
  overlay.classList.add('hidden');
  reticle.style.display = 'block';
});
controls.addEventListener('unlock', () => {
  clearKeys();
  if (fbMode) return;  // deliberate freeze (F) — keep the view, no start overlay
  overlay.classList.remove('hidden');
  reticle.style.display = 'none';
  exitMeasureMode();  // Esc also abandons any measurement in progress
});
document.addEventListener('pointerlockerror', () =>
  fatal(new Error('pointer lock rejected by the browser — click the page again')));
addEventListener('blur', clearKeys);
document.addEventListener('visibilitychange', () => { if (document.hidden) clearKeys(); });
document.addEventListener('keydown', (e) => {
  if (fbMode) {  // frozen for feedback: no movement keys, no Space hijack
    if (e.code === 'Escape') exitFeedback();
    if (e.code === 'KeyZ' && document.activeElement !== fbText) {
      strokes.pop();
      drawStrokes();
    }
    return;
  }
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
  if (e.code === 'KeyF' && !e.repeat) enterFeedback();
  if (e.code === 'KeyN' && !e.repeat) {
    labelsOn = !labelsOn;
    if (!labelsOn) clearFeedbackLabels();
  }
});
document.addEventListener('keyup', (e) => keys.delete(e.code));
renderer.domElement.addEventListener('click', () => {
  if (controls.isLocked && measureMode) measureClick();
});
if (isTouch) {
  // Left half of the screen = virtual joystick (drag away from the first
  // touch), right half = look. Two simultaneous pointers, routed by id.
  const euler = new THREE.Euler(0, 0, 0, 'YXZ');
  let movePid = null, lookPid = null, moveStart = null, lookLast = null;
  const el = renderer.domElement;
  el.style.touchAction = 'none';
  const joy = document.getElementById('joy');
  const knob = document.getElementById('joy-knob');
  const JOY_R = 45;  // px of knob travel = full speed
  el.addEventListener('pointerdown', (e) => {
    if (!touchWalking || fbMode) return;
    if (e.clientX < innerWidth / 2 && movePid === null) {
      movePid = e.pointerId;
      moveStart = { x: e.clientX, y: e.clientY };
      // float the joystick base to the finger — visible, and no reach needed
      joy.style.left = (e.clientX - 60) + 'px';
      joy.style.top = (e.clientY - 60) + 'px';
      joy.style.bottom = 'auto';
    } else if (lookPid === null) {
      lookPid = e.pointerId;
      lookLast = { x: e.clientX, y: e.clientY };
    }
  });
  el.addEventListener('pointermove', (e) => {
    if (e.pointerId === movePid) {
      let dx = e.clientX - moveStart.x;
      let dy = e.clientY - moveStart.y;
      const len = Math.hypot(dx, dy);
      if (len > JOY_R) { dx *= JOY_R / len; dy *= JOY_R / len; }
      knob.style.transform = 'translate(' + dx + 'px,' + dy + 'px)';
      touchMove.x = dx / JOY_R;
      touchMove.z = -dy / JOY_R;  // push up = walk forward
    } else if (e.pointerId === lookPid) {
      euler.setFromQuaternion(camera.quaternion);
      euler.y -= (e.clientX - lookLast.x) * 0.005;
      euler.x -= (e.clientY - lookLast.y) * 0.005;
      euler.x = Math.max(-1.55, Math.min(1.55, euler.x));
      camera.quaternion.setFromEuler(euler);
      lookLast = { x: e.clientX, y: e.clientY };
    }
  });
  const releaseTouch = (e) => {
    if (e.pointerId === movePid) {
      movePid = null;
      touchMove.x = touchMove.z = 0;
      knob.style.transform = '';
      joy.style.cssText = '';  // back to the resting corner
    }
    if (e.pointerId === lookPid) lookPid = null;
  };
  el.addEventListener('pointerup', releaseTouch);
  el.addEventListener('pointercancel', releaseTouch);

  const hold = (id, val) => {
    const b = document.getElementById(id);
    b.addEventListener('pointerdown', (e) => { e.preventDefault(); touchUp = val; });
    for (const ev of ['pointerup', 'pointercancel', 'pointerleave'])
      b.addEventListener(ev, () => { touchUp = 0; });
  };
  hold('btn-up', 1);
  hold('btn-down', -1);
  const menu = document.getElementById('menu');
  document.getElementById('btn-menu').addEventListener('click', () => {
    menu.hidden = !menu.hidden;
  });
  document.getElementById('m-roof').addEventListener('click', (e) => {
    toggleRoof();
    e.target.textContent = 'Roof: ' + (roofVisible ? 'on' : 'off');
  });
  document.getElementById('m-names').addEventListener('click', (e) => {
    labelsOn = !labelsOn;
    if (!labelsOn) clearFeedbackLabels();
    e.target.textContent = 'Names: ' + (labelsOn ? 'on' : 'off');
  });
  document.getElementById('btn-fb').addEventListener('click', () => {
    if (!ready || fbMode) return;
    touchWalking = true;  // works straight from the start overlay too
    enterFeedback();
  });
}
addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
  labelRenderer.setSize(innerWidth, innerHeight);
  if (fbMode) sizeDrawCanvas();
});

// --- feedback mode: freeze + draw + comment (F) -------------------------------
// Mini-BCF: one submission = camera pose + screen-space strokes (with the
// element tags they touch) + comment + composite PNG. POSTs to /feedback
// (serve.py); falls back to a PNG download on static hosting.
const drawCanvas = document.getElementById('draw');
const fbPanel = document.getElementById('fbpanel');
const fbText = document.getElementById('fbtext');
const ctx2d = drawCanvas.getContext('2d');
let fbMode = false;
let strokes = [];       // finished strokes: arrays of normalized {x, y}
let liveStroke = null;

function drawStrokes() {
  ctx2d.clearRect(0, 0, drawCanvas.width, drawCanvas.height);
  ctx2d.strokeStyle = '#ff3b30';
  ctx2d.lineWidth = 3;
  ctx2d.lineJoin = ctx2d.lineCap = 'round';
  for (const s of [...strokes, liveStroke].filter(Boolean)) {
    ctx2d.beginPath();
    s.forEach((p, i) => {
      const x = p.x * drawCanvas.width;
      const y = p.y * drawCanvas.height;
      i ? ctx2d.lineTo(x, y) : ctx2d.moveTo(x, y);
    });
    ctx2d.stroke();
  }
}

function sizeDrawCanvas() {
  drawCanvas.width = innerWidth;
  drawCanvas.height = innerHeight;
  drawStrokes();
}

// Tag labels over the elements while feedback mode is open — the owner
// references elements by plan tag (W7, Win2, D8), so show them in place.
// Occlusion-tested: a tag only shows if its element is the first visible
// surface toward its bbox center from the frozen camera.
let fbLabels = [];

function showFeedbackLabels() {
  renderer.render(scene, camera);  // matrices current before projecting
  // text -> screen positions already badged. Big surfaces (or one you are
  // standing INSIDE — feedback #012) span distant screen regions: repeat
  // the badge when the same object shows up far from its existing badges.
  const seen = new Map();
  const FAR = Math.max(innerWidth, innerHeight) * 0.42;
  const MAX_PER_TEXT = 3;

  function needsBadge(text, px, py) {
    const spots = seen.get(text);
    if (!spots) return true;
    if (spots.length >= MAX_PER_TEXT) return false;
    return spots.every((s) => Math.hypot(s[0] - px, s[1] - py) > FAR);
  }

  const layer = document.getElementById('labels');
  const visible = (o) => { for (; o; o = o.parent) if (!o.visible) return false; return true; };

  function place(text, px, py) {
    if (!seen.has(text)) seen.set(text, []);
    seen.get(text).push([px, py]);
    const div = document.createElement('div');
    div.className = 'fblabel';
    div.textContent = text;
    div.style.left = px + 'px';
    div.style.top = py + 'px';
    div.dataset.px = px;  // for burning into the feedback composite
    div.dataset.py = py;
    layer.appendChild(div);
    fbLabels.push(div);
  }

  // Pass 1 — viewport grid: badge whatever is ACTUALLY visible at the
  // point it is seen (owner: "rendered where I see it"; untagged objects
  // like GroundHigh or the Ground Slab show their readable name).
  for (let gy = 0.08; gy < 0.95; gy += 0.11) {
    for (let gx = 0.05; gx < 0.98; gx += 0.08) {
      raycaster.setFromCamera(new THREE.Vector2(gx * 2 - 1, -(gy * 2 - 1)), camera);
      const hit = raycaster.intersectObject(modelRoot, true).find((h) => visible(h.object));
      if (!hit) continue;
      const sem = semanticNode(hit.object);
      if (/_Handle_/.test(sem.label)) continue;  // handles label their door
      const text = displayName(sem.label);       // frame hits → their window
      if (!text || text === 'unnamed') continue;
      if (!needsBadge(text, gx * innerWidth, gy * innerHeight)) continue;
      place(text, gx * innerWidth, gy * innerHeight);
    }
  }

  // Pass 2 — tagged elements (doors, windows): thin geometry slips between
  // grid points (owner feedback #008/#009), so sample each element's bbox
  // center + face midpoints and badge the first visible spot.
  for (const n of modelRoot.children) {
    if (!n.name || /_frame$|_Handle_/.test(n.name)) continue;
    const clean = n.name.replace(/^Ifc\\w+?_/, '');
    if (!TAGS[clean]) continue;
    const text = displayName(n.name);
    if (seen.has(text)) continue;  // tagged elements: one badge is enough
    const box = new THREE.Box3().setFromObject(n);
    if (box.isEmpty()) continue;
    const c = box.getCenter(new THREE.Vector3());
    const samples = [c,
      new THREE.Vector3(box.min.x, c.y, c.z), new THREE.Vector3(box.max.x, c.y, c.z),
      new THREE.Vector3(c.x, box.min.y, c.z), new THREE.Vector3(c.x, box.max.y, c.z),
      new THREE.Vector3(c.x, c.y, box.min.z), new THREE.Vector3(c.x, c.y, box.max.z)];
    for (const s of samples) {
      const v = s.clone().project(camera);
      if (v.z > 1 || Math.abs(v.x) > 1 || Math.abs(v.y) > 1) continue;
      raycaster.setFromCamera(new THREE.Vector2(v.x, v.y), camera);
      const hit = raycaster.intersectObject(modelRoot, true).find((h) => visible(h.object));
      if (!hit) continue;
      const hitSem = semanticNode(hit.object);
      if (hitSem.node !== n &&
          hitSem.label.replace(/^Ifc\\w+?_/, '').replace(/_frame$/, '') !== clean) continue;
      place(text, (v.x + 1) / 2 * innerWidth, (1 - (v.y + 1) / 2) * innerHeight);
      break;
    }
  }
}

function clearFeedbackLabels() {
  for (const div of fbLabels) div.remove();
  fbLabels = [];
}

function enterFeedback() {
  if (!ready || fbMode) return;
  fbMode = true;  // set BEFORE unlock so the unlock handler keeps the view
  if (controls.isLocked) controls.unlock();
  overlay.classList.add('hidden');
  reticle.style.display = 'none';
  sizeDrawCanvas();
  drawCanvas.style.display = 'block';
  fbPanel.style.display = 'flex';
  clearFeedbackLabels();  // N-mode labels may already be up — no doubles
  showFeedbackLabels();
  infoText = 'FEEDBACK — drag to draw, comment, Submit';
  setHud();
  if (isTouch) {
    document.getElementById('touchui').style.display = 'none';
    document.getElementById('menu').hidden = true;
  } else fbText.focus();  // on phones the keyboard would cover the view
}

function exitFeedback(message = '') {
  const btn = document.getElementById('fbsubmit');
  btn.disabled = false;
  btn.textContent = 'Submit';
  const hint = document.getElementById('fbhint');
  hint.style.cssText = '';
  hint.innerHTML = 'drag — draw &nbsp;·&nbsp; Z — undo stroke &nbsp;·&nbsp; Esc — cancel';
  fbMode = false;
  strokes = [];
  liveStroke = null;
  clearFeedbackLabels();
  drawCanvas.style.display = 'none';
  fbPanel.style.display = 'none';
  fbText.value = '';
  infoText = message;
  setHud();
  if (isTouch) {
    document.getElementById('touchui').style.display = '';
    if (touchWalking) {  // owner: back to normal state, not a blocked overlay
      reticle.style.display = 'block';
      return;
    }
  }
  overlay.classList.remove('hidden');  // click to resume walking (desktop)
}

drawCanvas.addEventListener('pointerdown', (e) => {
  drawCanvas.setPointerCapture(e.pointerId);
  liveStroke = [{ x: e.clientX / innerWidth, y: e.clientY / innerHeight }];
});
drawCanvas.addEventListener('pointermove', (e) => {
  if (!liveStroke) return;
  liveStroke.push({ x: e.clientX / innerWidth, y: e.clientY / innerHeight });
  drawStrokes();
});
drawCanvas.addEventListener('pointerup', () => {
  // keep only strokes with real extent — repeated events at one spot make
  // an invisible zero-size stroke (Codex review 2026-08-06)
  if (liveStroke && liveStroke.length > 1) {
    const xs = liveStroke.map((p) => p.x);
    const ys = liveStroke.map((p) => p.y);
    if (Math.max(...xs) - Math.min(...xs) > 0.004 ||
        Math.max(...ys) - Math.min(...ys) > 0.004) {
      strokes.push(liveStroke);
    }
  }
  liveStroke = null;
  drawStrokes();
});

// Which elements a stroke covers — raycast a sample of its points and
// collect the same tagged names the I key shows. Scribble → tags, no typing.
function strokeElements(stroke) {
  const found = new Set();
  const visible = (o) => { for (; o; o = o.parent) if (!o.visible) return false; return true; };
  const idx = new Set([stroke.length - 1]);  // ALWAYS sample the endpoint —
  for (let i = 0; i < stroke.length; i += 4) idx.add(i);  // short strokes
  for (const i of idx) {                                  // end ON the target
    const p = stroke[i];
    raycaster.setFromCamera(new THREE.Vector2(p.x * 2 - 1, -(p.y * 2 - 1)), camera);
    const hit = raycaster.intersectObject(modelRoot, true).find((h) => visible(h.object));
    if (hit) found.add(displayName(semanticNode(hit.object).label));
  }
  return [...found];
}

async function submitFeedback() {
  // Guard against double submission: the PNG upload takes seconds, and a
  // second click mid-flight stored the same feedback twice (DB rows 1+2,
  // 2026-08-07). The button is re-enabled in exitFeedback().
  const btn = document.getElementById('fbsubmit');
  if (btn.disabled) return;
  btn.disabled = true;
  btn.textContent = 'Sending…';
  renderer.render(scene, camera);  // fresh frame for toDataURL
  const composite = document.createElement('canvas');
  // CSS resolution, not the DPR-scaled backing store: the shot only needs
  // to show what was marked (the camera pose in meta reproduces the view
  // losslessly), and 1x uploads 4-9x faster on retina/phone screens.
  composite.width = innerWidth;
  composite.height = innerHeight;
  const c = composite.getContext('2d');
  c.drawImage(renderer.domElement, 0, 0, composite.width, composite.height);
  c.drawImage(drawCanvas, 0, 0, composite.width, composite.height);
  // Burn the tag badges into the shot — the DOM labels are not part of the
  // canvases, so without this the saved PNG has no ids (feedback #006).
  const sx = composite.width / innerWidth;
  const sy = composite.height / innerHeight;
  c.font = (12 * sx) + 'px ui-monospace, monospace';
  for (const div of fbLabels) {
    const w = c.measureText(div.textContent).width + 10 * sx;
    const x = div.dataset.px * sx;
    const y = div.dataset.py * sy;
    c.fillStyle = 'rgba(255, 209, 102, 0.92)';
    c.fillRect(x - w / 2, y - 9 * sy, w, 18 * sy);
    c.fillStyle = '#101418';
    c.fillText(div.textContent, x - w / 2 + 5 * sx, y + 4 * sy);
  }
  const image = composite.toDataURL('image/png');

  const p = camera.position;
  const spec = cameraSpec();
  const camSpec = spec.text;
  const meta = {
    timestamp: new Date().toISOString(),
    where: whereAmI(),  // "Master Bedroom — Ground Floor" (feedback #007)
    model: { x: +p.x.toFixed(2), y: +(-p.z).toFixed(2), h: +p.y.toFixed(2) },
    camera: { x: +p.x.toFixed(3), y: +p.y.toFixed(3), z: +p.z.toFixed(3),
              yawDeg: +spec.yaw.toFixed(2),
              pitchDeg: +spec.pitch.toFixed(2) },
    debugHash: '#debug=' + camSpec,
    viewport: { w: innerWidth, h: innerHeight },
    comment: fbText.value.trim(),
    strokes: strokes.map((s) => ({
      points: s.map((pt) => [+pt.x.toFixed(4), +pt.y.toFixed(4)]),
      elements: strokeElements(s),
    })),
  };

  try {
    const resp = await fetch('feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image, meta }),
    });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const { id } = await resp.json();
    exitFeedback('feedback #' + id + ' saved');
  } catch (err) {
    // Stay in the panel and say so loudly — the owner wants a clear failure
    // notice, not a surprise PNG in the downloads folder (decision 2026-08-08).
    console.warn('feedback POST failed', err);
    btn.disabled = false;
    btn.textContent = 'Retry';
    const hint = document.getElementById('fbhint');
    hint.textContent = 'Submit FAILED — server unreachable. Press Retry.';
    hint.style.cssText = 'display:inline;color:#ff6b6b;opacity:1';
  }
}

document.getElementById('fbsubmit').addEventListener('click', submitFeedback);
document.getElementById('fbcancel').addEventListener('click', () => exitFeedback());
document.getElementById('fbundo').addEventListener('click', () => {
  strokes.pop();
  drawStrokes();
});

// ?feedback=1 — open the panel; ?feedback=submit — also inject a stroke and
// submit (exercises raycast tags + composite + POST). Test seams for
// headless verification, same #debug gating as ?roof / ?measure.
if (location.hash.startsWith('#debug') && ready) {
  const seams = new URLSearchParams(location.search);
  if (isTouch && seams.get('start') === '1') {  // test seam: skip the tap
    touchWalking = true;
    overlay.classList.add('hidden');
    reticle.style.display = 'block';
    if (seams.get('menu') === '1') document.getElementById('menu').hidden = false;
  }
  const fbSeam = new URLSearchParams(location.search).get('feedback');
  if (fbSeam === '1' || fbSeam === 'submit') enterFeedback();
  if (fbSeam === 'submit') {
    strokes.push([{ x: 0.42, y: 0.42 }, { x: 0.5, y: 0.5 }, { x: 0.58, y: 0.58 }]);
    drawStrokes();
    fbText.value = 'automated test seam';
    submitFeedback();
  }
}

const clock = new THREE.Clock();
const move = new THREE.Vector3();
let hudFrame = 0;
let labelFrame = 0;
let labelsOn = false;  // N — persistent tag badges while walking
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(), 0.1); // clamp after tab suspension
  if (controls.isLocked || (touchWalking && !fbMode)) {
    const speed = keys.has('ShiftLeft') || keys.has('ShiftRight') ? 12 : 4;
    move.set(
      (keys.has('KeyD') ? 1 : 0) - (keys.has('KeyA') ? 1 : 0) + touchMove.x,
      0,
      (keys.has('KeyW') ? 1 : 0) - (keys.has('KeyS') ? 1 : 0) + touchMove.z,
    );
    if (move.lengthSq() > 1) move.normalize();  // keys full speed, joystick analog
    controls.moveRight(move.x * speed * dt);
    controls.moveForward(move.z * speed * dt);
    // Vertical at HALF speed: full walk speed on C sank the owner 2m in a
    // blink — "slightly below the floor" turned out to be the garage
    // (feedback #007).
    // Vertical flight is UNRESTRICTED by owner decision (2026-08-07):
    // no slab clamp, no modifier, no collision — the owner flies through
    // floors on purpose. Do not "fix" this again.
    const up = (keys.has('Space') ? 1 : 0) - (keys.has('KeyC') ? 1 : 0) + touchUp;
    camera.position.y += up * speed * 0.5 * dt;
  }
  if (hudFrame++ % 15 === 0) setHud();  // live position/room readout
  if (labelsOn && !fbMode && labelFrame++ % 30 === 0) {
    clearFeedbackLabels();
    showFeedbackLabels();
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
            .replace("__TAGS__", json.dumps(tags, sort_keys=True))
            .replace("__STOREYS__", json.dumps(storey_bands())))
    HTML.write_text(html, encoding="utf-8")
    print(f"wrote {HTML} ({HTML.stat().st_size / 1024:.0f} KB; "
          f"{len(tags)} element tags; loads ./villa.glb at runtime)")


main()
