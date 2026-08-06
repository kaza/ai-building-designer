"""Serve the villa walkthrough and receive feedback annotations.

    .venv/bin/python projects/villa-maketa/serve.py [port]     # default 8123

Static files from output/ (same as `python -m http.server -d output`), plus
POST /feedback: stores each submission as feedback/<NNN>/shot.png (the view
with the owner's strokes burned in) + meta.json (camera pose, normalized
strokes with the element tags they touch, comment, timestamp). feedback/
lives at the PROJECT level, not in output/ — it is owner input worth
keeping, not a regenerable artifact (owner decision 2026-08-06).
The walkthrough's F key posts here; if the POST fails the page falls back
to downloading the PNG. Spec: specs/browser-walkthrough.md.
"""
import base64
import json
import re
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

OUT = Path(__file__).parent / "output"
FEEDBACK = Path(__file__).parent / "feedback"
MAX_BODY = 30_000_000  # a full-screen PNG data URL fits well under 30 MB


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(OUT), **kwargs)

    def do_POST(self):
        if self.path.rstrip("/") != "/feedback":
            self.send_error(404, "only POST /feedback exists")
            return
        # A malformed payload must not kill the server — it becomes a loud
        # HTTP 400 for the client instead (approved fail-loud shape).
        try:
            length = int(self.headers["Content-Length"])
            if length > MAX_BODY:
                self.send_error(413, f"feedback body {length} > {MAX_BODY}")
                return
            payload = json.loads(self.rfile.read(length))
            meta = payload["meta"]
            if not isinstance(meta, dict):
                raise TypeError("meta must be a JSON object")
            match = re.match(
                r"data:image/png;base64,(.+)$", payload["image"], re.DOTALL
            )
            if not match:
                raise ValueError("image is not a base64 PNG data URL")
            png = base64.b64decode(match.group(1), validate=True)
        except Exception as err:  # noqa: BLE001 — becomes a 400, not silence
            self.send_error(400, f"bad feedback payload: {err}")
            return

        FEEDBACK.mkdir(parents=True, exist_ok=True)
        # mkdir(exist_ok=False) is the atomic claim — concurrent submissions
        # (double-clicked Submit) retry on the next number instead of racing
        # into one directory (Codex review 2026-08-06).
        for _ in range(100):
            taken = [int(p.name) for p in FEEDBACK.iterdir()
                     if p.name.isdigit()]
            n = max(taken, default=0) + 1
            item = FEEDBACK / f"{n:03d}"
            try:
                item.mkdir()
                break
            except FileExistsError:
                continue
        else:
            self.send_error(503, "could not allocate a feedback slot")
            return
        (item / "shot.png").write_bytes(png)
        (item / "meta.json").write_text(json.dumps(meta, indent=2))
        print(f"feedback #{n:03d}: {meta.get('comment', '')!r} -> {item}")

        body = json.dumps({"ok": True, "id": n}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8123
    print(f"serving {OUT} on http://localhost:{port} "
          f"(POST /feedback -> {FEEDBACK})")
    # localhost only — this is the owner's local review tool, not a website
    # (Codex review 2026-08-06: binding all interfaces exposed /feedback to
    # the whole LAN with an unbounded upload).
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
