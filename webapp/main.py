"""Building-designer web app: project catalog, per-project homepage,
walkthrough hosting and the feedback inbox.

Topology (specs/web-deployment.md, Azure variant): this app serves all HTML
and accepts POST feedback (same origin as the pages, like serve.py locally);
the heavy artifacts (GLB, plan PNGs) live in Azure Blob Storage and are only
redirected/proxied to, never bundled with the app. Postgres holds the two
tables (projects, feedback). Publishing a new model build touches blob +
nothing here — the app picks up the new build.json on the next request.

Env (App Service settings):
    DATABASE_URL                    postgresql://...  (sslmode=require)
    AZURE_STORAGE_CONNECTION_STRING for blob reads/writes
    STORAGE_ACCOUNT_WEB_BASE        e.g. https://<acct>.blob.core.windows.net

Run locally:
    uvicorn main:app --reload      (from webapp/, with the env vars set)
"""
import base64
import json
import os
import re
import time
import urllib.request
from pathlib import Path

import psycopg
from azure.storage.blob import BlobServiceClient, ContentSettings
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from jinja2 import Environment, FileSystemLoader, select_autoescape

DATABASE_URL = os.environ["DATABASE_URL"]
STORAGE_CONN = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
PROJECTS_CONTAINER = "projects"
FEEDBACK_CONTAINER = "feedback"
MAX_BODY = 30_000_000  # same cap as serve.py — a full-screen PNG data URL

app = FastAPI()
# THE rule of this deployment, learned the hard way (DB pool wedged a worker;
# kept-alive blob sockets stalled first-after-idle requests up to 37s even
# WITH read timeouts — the SDK retried through several rotten sockets in a
# row): NO long-lived outbound connections of any kind. App Service reaps
# idle sockets silently. Public blob reads use one fresh Connection: close
# request; SDK operations get a fresh client per request.
BLOB_BASE = (
    f"https://{BlobServiceClient.from_connection_string(STORAGE_CONN).account_name}"
    ".blob.core.windows.net"
)


def blob_service() -> BlobServiceClient:
    return BlobServiceClient.from_connection_string(
        STORAGE_CONN, connection_timeout=5, read_timeout=15)


def fetch_public(path: str) -> bytes:
    req = urllib.request.Request(
        f"{BLOB_BASE}/{path}", headers={"Connection": "close"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.read()
    except urllib.error.HTTPError as err:
        if err.code == 404:
            raise HTTPException(404, f"not published: {path}") from err
        raise

_jinja = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)

# build.json is the per-project release pointer (uploaded LAST by publish.py,
# so a reader never sees a new pointer before its artifacts exist). Cache it
# briefly — every page hit reading blob would be silly.
_build_cache: dict[str, tuple[float, dict]] = {}
_BUILD_TTL = 15.0


# No pool, deliberately (2026-08-08). psycopg_pool inside App Service kept
# wedging one gunicorn worker (PoolTimeout with the server at 14/50
# connections — checked-out connections never came home), which made every
# second request hang. A fresh connection per request costs ~0.3s cross-
# region and has NO state that can rot between requests. The owner chose
# predictable hundreds-of-ms over occasionally-wedged instant.
def db():
    return psycopg.connect(DATABASE_URL, connect_timeout=5)


def get_build(project: str) -> dict:
    now = time.monotonic()
    hit = _build_cache.get(project)
    if hit and now - hit[0] < _BUILD_TTL:
        return hit[1]
    build = json.loads(
        fetch_public(f"{PROJECTS_CONTAINER}/{project}/build.json"))
    _build_cache[project] = (now, build)
    return build


def project_row(project: str) -> tuple:
    with db() as conn:
        row = conn.execute(
            "SELECT id, name FROM projects WHERE id = %s", (project,)
        ).fetchone()
    if row is None:
        raise HTTPException(404, f"unknown project {project!r}")
    return row


@app.get("/health")
def health():
    with db() as conn:
        conn.execute("SELECT 1")
    blob_service().get_container_client(PROJECTS_CONTAINER).exists()
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def catalog():
    with db() as conn:
        rows = conn.execute(
            """
            SELECT p.id, p.name,
                   count(*) FILTER (WHERE f.status = 'new')      AS open,
                   count(*) FILTER (WHERE f.status = 'resolved') AS resolved
            FROM projects p LEFT JOIN feedback f ON f.project_id = p.id
            GROUP BY p.id, p.name ORDER BY p.created_at
            """
        ).fetchall()
    return _jinja.get_template("index.html").render(projects=rows)


@app.get("/{project}/", response_class=HTMLResponse)
def project_home(project: str):
    build = get_build(project)
    with db() as conn:
        row = conn.execute(
            "SELECT name FROM projects WHERE id = %s", (project,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, f"unknown project {project!r}")
        name = row[0]
        feedback = conn.execute(
            """
            SELECT id, comment, where_label, status, created_at, resolved_at,
                   resolved_sha, screenshot_key
            FROM feedback WHERE project_id = %s
            ORDER BY created_at DESC LIMIT 50
            """,
            (project,),
        ).fetchall()
    plans = [
        {"url": f"{BLOB_BASE}/{PROJECTS_CONTAINER}/{project}/{p['file']}",
         "caption": p["caption"]}
        for p in build.get("plans", [])
    ]
    return _jinja.get_template("project.html").render(
        project=project, name=name, build=build, plans=plans,
        feedback=feedback,
    )


@app.get("/{project}/feedback/{fb_id}/shot")
def feedback_shot(project: str, fb_id: int):
    # Screenshots live in the PRIVATE feedback container — proxied here so
    # the homepage can thumbnail them without opening the container up.
    with db() as conn:
        row = conn.execute(
            "SELECT screenshot_key FROM feedback WHERE id = %s AND project_id = %s",
            (fb_id, project),
        ).fetchone()
    if row is None or not row[0]:
        raise HTTPException(404, f"no screenshot for feedback {fb_id}")
    blob = blob_service().get_blob_client(FEEDBACK_CONTAINER, row[0])
    return Response(
        blob.download_blob().readall(), media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )


@app.get("/{project}/walkthrough", response_class=HTMLResponse)
def walkthrough(project: str):
    # Proxied (not redirected) so the page shares this origin and its
    # relative fetch('feedback') lands on POST /{project}/feedback below.
    project_row(project)
    build = get_build(project)
    return HTMLResponse(
        fetch_public(f"{PROJECTS_CONTAINER}/{project}/{build['walkthrough']}"),
        headers={"Cache-Control": "no-cache"})


@app.get("/{project}/xray", response_class=HTMLResponse)
def xray(project: str):
    # Proxied like the walkthrough so its relative fem-field fetch stays
    # on this origin and hits the exact-asset route below.
    project_row(project)
    build = get_build(project)
    if "xray" not in build:
        raise HTTPException(404, "no X-ray published for this project")
    return HTMLResponse(
        fetch_public(f"{PROJECTS_CONTAINER}/{project}/{build['xray']}"),
        headers={"Cache-Control": "no-cache"})


@app.get("/{project}/{model_file}.glb")
def model(project: str, model_file: str):
    # New releases pin the exact SHA-stamped name into the HTML (307 to
    # that exact blob). Pre-pinning walkthroughs fetch the plain name the
    # page was built with — those still resolve through the live pointer.
    project_row(project)
    if _PINNED_GLB.match(model_file):
        return RedirectResponse(
            f"{BLOB_BASE}/{PROJECTS_CONTAINER}/{project}/{model_file}.glb",
            status_code=307,
        )
    build = get_build(project)
    return RedirectResponse(
        f"{BLOB_BASE}/{PROJECTS_CONTAINER}/{project}/{build['model']}",
        status_code=307,
    )


_EXACT_ASSET = re.compile(
    r"^(?:fem-field-[0-9a-f]{7,40}\.json"
    r"|xray-[0-9a-f]{7,40}\.html)$")
_PINNED_GLB = re.compile(r"^[\w-]+-[0-9a-f]{7,40}$")


# NOTE: catch-all for /{project}/<one-segment> — MUST stay the last GET
# route in this file; any GET added after it would be swallowed and 404.
@app.get("/{project}/{asset_file}")
def exact_asset(project: str, asset_file: str):
    # Release-pinned artifacts (spec fem-xray.md): published HTML references
    # exact SHA-stamped names so a publish between page load and asset fetch
    # can never mix two releases. 307 to the immutable blob.
    if not _EXACT_ASSET.match(asset_file):
        raise HTTPException(404, "unknown asset")
    project_row(project)
    return RedirectResponse(
        f"{BLOB_BASE}/{PROJECTS_CONTAINER}/{project}/{asset_file}",
        status_code=307,
    )



@app.post("/{project}/feedback")
async def submit_feedback(project: str, request: Request):
    project_row(project)
    # Same fail-loud shape as serve.py: malformed payload -> HTTP 400.
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(413, f"feedback body {len(body)} > {MAX_BODY}")
    try:
        payload = json.loads(body)
        meta = payload["meta"]
        if not isinstance(meta, dict):
            raise TypeError("meta must be a JSON object")
        match = re.match(
            r"data:image/png;base64,(.+)$", payload["image"], re.DOTALL
        )
        if not match:
            raise ValueError("image is not a base64 PNG data URL")
        png = base64.b64decode(match.group(1), validate=True)
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(400, f"bad feedback payload: {err}") from err

    with db() as conn:
        row = conn.execute(
            """
            INSERT INTO feedback (project_id, comment, where_label, camera,
                                  strokes, viewed_sha)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (
                project,
                meta.get("comment", ""),
                meta.get("where"),
                json.dumps(meta.get("camera")),
                json.dumps(meta.get("strokes")),
                meta.get("viewedSha") or get_build(project).get("sha"),
            ),
        ).fetchone()
        fb_id = row[0]
        key = f"{project}/{fb_id:05d}.png"
        blob_service().get_blob_client(FEEDBACK_CONTAINER, key).upload_blob(
            png, overwrite=True,
            content_settings=ContentSettings(content_type="image/png"),
        )
        conn.execute(
            "UPDATE feedback SET screenshot_key = %s WHERE id = %s",
            (key, fb_id),
        )
        conn.commit()
    return JSONResponse({"ok": True, "id": fb_id})
