"""Loopback-only console; each tab has an isolated mission, ordered by revision."""
import json
import mimetypes
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from .config import load
from .runner import Mission

ROOT = Path(__file__).resolve().parent.parent
MISSIONS = {p.stem: p for p in sorted((ROOT/"missions").glob("*.json"))}


class SessionStore:
    def __init__(self):
        self.sessions = {}
        self.lock = threading.Lock()

    def create(self, name):
        if name not in MISSIONS:
            raise ValueError("Unknown mission")
        with self.lock:
            if len(self.sessions) >= 64:
                # Bound memory for a local demonstration server.
                self.sessions.pop(next(iter(self.sessions)))
            identity = uuid.uuid4().hex
            mission = Mission(load(MISSIONS[name]))
            self.sessions[identity] = mission
            return {"session": identity, "revision": 0, **mission.snapshot()}

    def step(self, identity, revision):
        with self.lock:
            mission = self.sessions.get(identity)
            if mission is None:
                raise KeyError("Session expired; reset the mission")
            if revision != len(mission.trace):
                raise ValueError("Stale step rejected; reset or reload")
            state = mission.step()
            return {"session": identity, "revision": len(mission.trace), **state}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def reply(self, status, value, mime="application/json"):
        data = json.dumps(value).encode() if mime == "application/json" else value
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def valid_host(self):
        return self.headers.get("Host") in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")

    def do_GET(self):
        if not self.valid_host():
            return self.reply(403, {"error": "Local requests only"})
        path = urlparse(self.path).path
        if path == "/api/missions":
            return self.reply(200, [{"id": name, "name": load(file)["name"]} for name, file in MISSIONS.items()])
        if path.startswith("/api/export/"):
            identity = path.rsplit("/", 1)[-1]
            with self.server.store.lock:
                mission = self.server.store.sessions.get(identity)
                if mission is None:
                    return self.reply(404, {"error": "Session expired"})
                return self.reply(200, {"report": mission.report(), "initial": mission.initial, "trace": mission.trace})
        assets = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
        if path not in assets:
            return self.reply(404, {"error": "Not found"})
        file = ROOT/"web"/assets[path]
        self.reply(200, file.read_bytes(), mimetypes.guess_type(file.name)[0]+"; charset=utf-8")

    def do_POST(self):
        origin = self.headers.get("Origin")
        if (not self.valid_host() or self.headers.get("X-Echo-Client") != "1" or
                (origin is not None and origin != "http://"+self.headers.get("Host", ""))):
            return self.reply(403, {"error": "Same-origin console requests only"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("Invalid request size")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("Expected an object")
            if self.path == "/api/sessions":
                result = self.server.store.create(data.get("mission"))
            elif self.path == "/api/step":
                if not isinstance(data.get("session"), str) or type(data.get("revision")) is not int:
                    raise ValueError("Expected session and integer revision")
                result = self.server.store.step(data["session"], data["revision"])
            else:
                return self.reply(404, {"error": "Not found"})
            self.reply(200, result)
        except (ValueError, KeyError, TypeError) as exc:
            self.reply(400, {"error": str(exc)})


def make_server(port=8766):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.store = SessionStore()
    return server


def serve(port):
    server = make_server(port)
    print(f"ECHO is ready at http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
