"""Serve a project's walkthrough locally and receive feedback (F key).

Promoted from projects/villa-maketa/serve.py on 2026-08-09 — the only
project-specific things in it were two paths.

Static files come from the project's output/; POST /feedback stores each
submission as feedback/<NNN>/shot.png (the view with the owner's strokes
burned in) + meta.json (camera pose, normalized strokes with the element
tags they touch, comment, timestamp). feedback/ lives at the PROJECT
level, not in output/: it is owner input worth keeping, not a regenerable
artifact (owner decision 2026-08-06). Spec: specs/browser-walkthrough.md.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import UTC, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY = 30_000_000   # a full-screen PNG data URL fits well under 30 MB


def next_feedback_dir(feedback_root: Path) -> Path:
    feedback_root.mkdir(parents=True, exist_ok=True)
    used = [int(p.name) for p in feedback_root.iterdir()
            if p.is_dir() and p.name.isdigit()]
    return feedback_root / f"{max(used, default=0) + 1:03d}"


def store_feedback(feedback_root: Path, payload: dict) -> Path:
    """Write one submission; returns its directory. Shared with the tests
    so the storage contract is verified without a live server."""
    target = next_feedback_dir(feedback_root)
    target.mkdir(parents=True)
    shot = payload.pop("shot", None)
    if shot:
        data = re.sub(r"^data:image/\w+;base64,", "", shot)
        (target / "shot.png").write_bytes(base64.b64decode(data))
    payload.setdefault("received_at", datetime.now(UTC).isoformat(
        timespec="seconds"))
    (target / "meta.json").write_text(json.dumps(payload, indent=2))
    return target


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, out_dir: Path, feedback_root: Path, **kwargs):
        self.feedback_root = feedback_root
        super().__init__(*args, directory=str(out_dir), **kwargs)

    def do_POST(self):                                  # noqa: N802 - stdlib API
        if self.path.rstrip("/") != "/feedback":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY:
            self.send_error(413, "feedback payload too large")
            return
        payload = json.loads(self.rfile.read(length) or b"{}")
        target = store_feedback(self.feedback_root, payload)
        body = json.dumps({"ok": True, "id": target.name}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        # the walkthrough is regenerated constantly; a cached copy of it
        # pointing at a replaced GLB is exactly the mixture we avoid
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def serve(out_dir: Path, feedback_root: Path, port: int = 8123) -> None:
    handler = partial(_Handler, out_dir=out_dir, feedback_root=feedback_root)
    server = ThreadingHTTPServer(("", port), handler)
    print(f"serving {out_dir} on http://localhost:{port}/walkthrough.html")
    print(f"feedback -> {feedback_root}")
    server.serve_forever()
