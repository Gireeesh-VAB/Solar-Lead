"""Local page for checking the reviewed roofs and starting a training run.

    .\\start_ui.ps1              then open http://127.0.0.1:8766

Only listens on this PC (127.0.0.1). The only thing it can start is run.py (the training pipeline), and it always trains on ALL reviewed roofs
from the frozen base model - there is deliberately no way to train on a hand-picked few (that is what made an earlier model forget).
"""
import json
import mimetypes
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
PIPELINE = HERE.parent
sys.path.insert(0, str(PIPELINE))

import config  # noqa: E402
import export_dataset  # noqa: E402
from db import query_json  # noqa: E402

PORT = 8766
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.png$")
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
EPOCH_RE = re.compile(r"^\s*(\d+)/(\d+)\s")
LOG_FILE = config.WORK_DIR / "ui_train.log"
ALLOWED_ORIGINS = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}

_lock = threading.Lock()
_proc: subprocess.Popen | None = None
_mode = "train"


def overview() -> dict:
    """Reviewed roofs (confirmed / ignored counts), how many detections still await review, and the models installed so far."""
    sites = export_dataset.fetch_reviewed_sites()
    pending = query_json("SELECT jsonb_build_object('n', count(*)) FROM obstacle_candidates WHERE status = 'pending'") or {"n": 0}
    rows = []
    for s in sites:
        confirmed = sum(1 for c in s["candidates"] if c["status"] == "confirmed")
        rows.append({
            "id": s["id"], "confirmed": confirmed, "ignored": len(s["candidates"]) - confirmed,
            "preview": (config.PREVIEWS_DIR / f"{s['id']}.png").is_file(),
        })
    return {"sites": rows, "pending": pending["n"], "installed": read_ledger()}


def read_ledger() -> list[dict]:
    if not config.LEDGER.is_file():
        return []
    out = []
    for line in config.LEDGER.read_text(encoding="utf-8").splitlines()[-5:]:
        try:
            e = json.loads(line)
            c, b = e.get("self_check", {}), e.get("base_check", {})
            out.append({"at": e.get("installed_at"), "roofs": len(e.get("roofs", [])), "found": c.get("found"), "labels": c.get("labels"),
                        "base_found": b.get("found"), "backup": e.get("backup")})
        except ValueError:
            continue
    return out[::-1]


def read_log_tail() -> dict:
    if not LOG_FILE.is_file():
        return {"lines": [], "epoch": None}
    data = LOG_FILE.read_bytes()[-30000:].decode("utf-8", errors="replace")
    lines = [ANSI_RE.sub("", p).rstrip() for p in re.split(r"[\r\n]+", data)]
    lines = [ln for ln in lines if ln.strip()]
    epoch = None
    for ln in reversed(lines):
        m = EPOCH_RE.match(ln)
        if m:
            epoch = {"done": int(m.group(1)), "total": int(m.group(2))}
            break
    return {"lines": lines[-30:], "epoch": epoch}


def status() -> dict:
    with _lock:
        running = _proc is not None and _proc.poll() is None
        code = None if _proc is None or running else _proc.returncode
        mode = _mode
    tail = read_log_tail()
    result = next((ln for ln in reversed(tail["lines"]) if ln.startswith("[3/3]")), None)
    return {"state": "running" if running else ("idle" if _proc is None else ("done" if code == 0 else "failed")),
            "exit_code": code, "mode": mode, "result": result, **tail}


def start_run(mode: str, epochs: int) -> tuple[int, dict]:
    global _proc, _mode
    if mode not in ("train", "dry"):
        return 400, {"error": "mode must be train or dry"}
    if not 10 <= epochs <= 1000:
        return 400, {"error": "Epochs must be between 10 and 1000."}
    with _lock:
        if _proc is not None and _proc.poll() is None:
            return 409, {"error": "A run is already in progress."}
        config.WORK_DIR.mkdir(parents=True, exist_ok=True)
        args = [sys.executable, "-u", str(PIPELINE / "run.py"), "--epochs", str(epochs)] + (["--dry-run"] if mode == "dry" else [])
        log = LOG_FILE.open("wb")
        _proc = subprocess.Popen(args, cwd=str(PIPELINE), stdout=log, stderr=subprocess.STDOUT)
        _mode = mode
    return 200, {"started": True}


def safe_preview(name: str) -> Path | None:
    if not UUID_RE.match(name):
        return None
    root = config.PREVIEWS_DIR.resolve()
    path = (root / name).resolve()
    return path if root in path.parents and path.is_file() else None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj):
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        try:
            if path in ("/", "/index.html"):
                return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
            if path == "/api/overview":
                return self._json(200, overview())
            if path == "/api/status":
                return self._json(200, status())
            m = re.fullmatch(r"/img/(.+)", path)
            if m:
                f = safe_preview(unquote(m.group(1)))
                if f:
                    return self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "image/png")
            self._json(404, {"error": "not found"})
        except Exception as e:  # keep the page usable and show the reason
            self._json(500, {"error": str(e)})

    def do_POST(self):
        if self.path != "/api/run":
            return self._json(404, {"error": "not found"})
        origin = self.headers.get("Origin")
        if (origin and origin not in ALLOWED_ORIGINS) or "application/json" not in (self.headers.get("Content-Type") or ""):
            return self._json(403, {"error": "forbidden"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            code, obj = start_run(str(body.get("mode", "train")), int(body.get("epochs", config.EPOCHS)))
            self._json(code, obj)
        except Exception as e:
            self._json(500, {"error": str(e)})


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Trainer page: http://127.0.0.1:{PORT}   (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
