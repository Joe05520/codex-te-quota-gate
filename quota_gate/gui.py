"""Loopback-only GUI. No directory scan, plugin install, model calls or telemetry."""
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import time
import webbrowser

from .policy import decide
from .settings import canonical_path, configured_decision, read_settings, revision, validate_settings
from .storage import read_snapshot, write_snapshot

SCENARIOS = {"normal": (40, 60), "low5h": (14, 60), "lowweekly": (40, 14),
             "boundary": (15, 15), "reset": (100, 100), "stale": (14, 60),
             "missing": (14, 60)}


def synthetic_snapshot(scenario):
    if scenario not in SCENARIOS:
        raise ValueError("unknown demo scenario")
    h, w = SCENARIOS[scenario]
    now = time.time()
    snapshot = {"schemaVersion": 1, "observedAt": now - (100 if scenario == "stale" else 0),
                "limitId": "codex", "windows": [
                    {"windowDurationMins": duration, "usedPercent": 100 - rem,
                     "resetsAt": now + 3600} for duration, rem in ((300, h), (10080, w))]}
    if scenario == "missing":
        snapshot["windows"].pop()
    return snapshot


class GuiState:
    def __init__(self, settings_path, snapshot_path, *, demo=False):
        self.settings_path = Path(settings_path).resolve()
        self.snapshot_path = Path(snapshot_path).resolve()
        if self.settings_path == self.snapshot_path:
            raise ValueError("settings and snapshot paths must differ")
        self.demo = demo
        self.scenario = "normal"
        self.lock = threading.RLock()
        self.token = secrets.token_urlsafe(32)
        if not self.settings_path.exists():
            write_snapshot(self.settings_path, read_settings())
        read_settings(self.settings_path)  # never overwrite an invalid existing file

    def status(self, *, cwd=None, draft=None):
        with self.lock:
            saved = read_settings(self.settings_path)
            settings = saved if draft is None else validate_settings(draft)
            if self.demo:
                snapshot = synthetic_snapshot(self.scenario)
                write_snapshot(self.snapshot_path, snapshot)
            else:
                try:
                    snapshot = read_snapshot(self.snapshot_path)
                except (OSError, ValueError):
                    snapshot = None
            quota = decide(snapshot)
            summary_settings = settings if cwd else {**settings, "projects": []}
            result = configured_decision(snapshot, summary_settings, cwd=cwd)
            return {"settings": settings, "revision": revision(saved), "demo": self.demo,
                    "scenario": self.scenario if self.demo else None,
                    "quota": quota.as_dict(), "decision": result.as_dict(),
                    "project": cwd or None,
                    "snapshotObservedAt": snapshot.get("observedAt") if isinstance(snapshot, dict) else None,
                    "settingsPath": str(self.settings_path), "snapshotPath": str(self.snapshot_path),
                    "integration": "not_verified"}

    def save(self, value, expected):
        with self.lock:
            current = read_settings(self.settings_path)
            if expected != revision(current):
                raise FileExistsError("settings changed elsewhere; reload before saving")
            clean = validate_settings(value)
            write_snapshot(self.settings_path, clean)
            return self.status()


def make_server(state, port=0):
    assets = Path(__file__).parent / "web"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # no project paths, browser requests or tokens in access logs

        def valid_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def reply(self, status, data, kind="application/json; charset=utf-8"):
            body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode() if isinstance(data, dict) else data
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; "
                             "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            token = self.headers.get("X-Gate-Token", "")
            return self.valid_host() and hmac.compare_digest(token, state.token)

        def do_GET(self):
            if not self.valid_host():
                return self.reply(403, {"error": "invalid host"})
            if self.path == "/api/state":
                if not self.authorized():
                    return self.reply(403, {"error": "invalid token"})
                try:
                    return self.reply(200, state.status())
                except (OSError, ValueError):
                    return self.reply(503, {"error": "settings unavailable; hooks stay inactive"})
            files = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                     "/style.css": ("style.css", "text/css; charset=utf-8")}
            if self.path not in files:
                return self.reply(404, {"error": "not found"})
            name, kind = files[self.path]
            content = (assets / name).read_bytes()
            if name == "index.html":
                content = content.replace(b"__GATE_TOKEN__", state.token.encode())
            return self.reply(200, content, kind)

        def do_POST(self):
            origin = f"http://127.0.0.1:{self.server.server_port}"
            if not self.authorized() or self.headers.get("Origin") != origin:
                return self.reply(403, {"error": "invalid origin or token"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 100_000 or self.headers.get("Content-Type") != "application/json":
                    raise ValueError("expected a small JSON request")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("request must be an object")
                if self.path == "/api/settings":
                    return self.reply(200, state.save(data.get("settings"), data.get("revision")))
                if self.path == "/api/preview":
                    cwd = str(canonical_path(data.get("cwd")))
                    return self.reply(200, state.status(cwd=cwd, draft=data.get("settings")))
                if self.path == "/api/scenario" and state.demo:
                    scenario = data.get("scenario")
                    if scenario not in SCENARIOS:
                        raise ValueError("unknown scenario")
                    with state.lock:
                        state.scenario = scenario
                        return self.reply(200, state.status())
                return self.reply(404, {"error": "not found"})
            except FileExistsError as exc:
                return self.reply(409, {"error": str(exc)})
            except (ValueError, OSError, TypeError, RuntimeError) as exc:
                return self.reply(400, {"error": str(exc)})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(settings_path, snapshot_path, *, demo=False, port=0, open_browser=False):
    state = GuiState(settings_path, snapshot_path, demo=demo)
    server = make_server(state, port)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"TE Quota Gate GUI: {url}", flush=True)
    print("Demo data only." if demo else "Local settings only; plugin integration is not verified.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
