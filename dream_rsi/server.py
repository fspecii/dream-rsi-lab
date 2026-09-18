"""Local-only web interface. No external assets, accounts, or hosted services."""
from __future__ import annotations

from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
import mimetypes
from pathlib import Path
import secrets
import urllib.parse
import urllib.request
import webbrowser

from .engine import replay
from .lab import LabConfig, LabManager
from .policy import Policy, PolicySpec
from .types import World


def recorded_example():
    data = json.loads(files("dream_rsi").joinpath("data/replay-example.json").read_text())
    world = World.from_dict(data["world"])
    results = {}
    for name in ("fixed", "learned"):
        policy = Policy(PolicySpec(**data[name]))
        plan = policy.plan_grid(world.branch_count, world.max_depth, world.workers, data["planning_history"])
        results[name] = replay(policy, world, 16, plan).to_dict()
    return {**data, "results": results, "provenance": "Recorded Qwen 3.5 0.8B experiment; replay makes no model calls."}


class LabServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, manager):
        self.manager = manager
        self.token = secrets.token_urlsafe(32)
        super().__init__(address, LabHandler)


class LabHandler(BaseHTTPRequestHandler):
    server_version = "DreamLab/0.3"

    def log_message(self, format, *args):
        # Polling should not flood the launch terminal.
        if args and str(args[1] if len(args) > 1 else "") not in ("200", "304"):
            super().log_message(format, *args)

    def _headers(self, status, content_type, size):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()

    def _json(self, data, status=200):
        content = json.dumps(data, allow_nan=False).encode()
        self._headers(status, "application/json; charset=utf-8", len(content))
        self.wfile.write(content)

    def _host_ok(self):
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        return self.headers.get("Host") in allowed

    def do_GET(self):
        if not self._host_ok():
            return self._json({"error": "Use the local lab URL."}, 403)
        url = urllib.parse.urlsplit(self.path)
        parts = url.path.strip("/").split("/")
        try:
            if url.path == "/api/bootstrap":
                return self._json({"token": self.server.token, "defaults": asdict(LabConfig()), "sessions": self.server.manager.list()})
            if url.path == "/api/models":
                try:
                    with urllib.request.urlopen(self.server.manager.base_url + "/api/tags", timeout=3) as response:
                        models = json.load(response)["models"]
                    return self._json({"available": True, "models": [{"name": m["name"], "size": m.get("details", {}).get("parameter_size", "")} for m in models]})
                except Exception:
                    return self._json({"available": False, "models": [], "message": "Ollama is unavailable. Start Ollama to run live experiments; recorded replay still works."})
            if url.path == "/api/example":
                return self._json(recorded_example())
            if url.path == "/api/sessions":
                return self._json(self.server.manager.list())
            if len(parts) == 3 and parts[:2] == ["api", "sessions"]:
                return self._json(self.server.manager.get(parts[2]))
            if len(parts) == 4 and parts[:2] == ["api", "sessions"] and parts[3] == "world":
                relative = urllib.parse.parse_qs(url.query).get("path", [""])[0]
                return self._json(self.server.manager.world(parts[2], relative))
            assets = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css", "/favicon.svg": "favicon.svg"}
            if url.path not in assets:
                return self._json({"error": "Page not found."}, 404)
            name = assets[url.path]
            content = files("dream_rsi").joinpath("web", name).read_bytes()
            content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
            self._headers(200, content_type + "; charset=utf-8", len(content))
            self.wfile.write(content)
        except (KeyError, FileNotFoundError):
            self._json({"error": "Workspace or artifact not found."}, 404)
        except (ValueError, TypeError) as exc:
            self._json({"error": str(exc)}, 400)

    def do_POST(self):
        origin = self.headers.get("Origin")
        allowed_origins = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
        if not self._host_ok() or (origin and origin not in allowed_origins) or self.headers.get("X-Lab-Token") != self.server.token:
            return self._json({"error": "Invalid local session. Refresh this page."}, 403)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 <= size <= 2_000_000:
                raise ValueError("Request is too large.")
            body = json.loads(self.rfile.read(size) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("Expected a JSON object.")
            parts = urllib.parse.urlsplit(self.path).path.strip("/").split("/")
            manager = self.server.manager
            if parts == ["api", "sessions"]:
                return self._json(manager.create(body.get("name", "Math workspace"), LabConfig(**body.get("config", {})), body.get("suite")), 201)
            if len(parts) != 4 or parts[:2] != ["api", "sessions"]:
                return self._json({"error": "Action not found."}, 404)
            sid, action = parts[2:]
            # Validate before any manager mutation / path construction.
            manager.get(sid)
            if action == "start":
                result = manager.start(sid, body.get("cycles", 1), body.get("max_calls", 240))
            elif action == "pause":
                result = manager.pause(sid)
            elif action == "restore":
                if type(body.get("version")) is not int:
                    raise ValueError("Choose a policy version.")
                result = manager.restore(sid, body["version"])
            elif action == "discard":
                result = manager.discard_pending(sid)
            else:
                return self._json({"error": "Action not found."}, 404)
            self._json(result)
        except (ValueError, TypeError) as exc:
            self._json({"error": str(exc)}, 400)
        except KeyError:
            self._json({"error": "Workspace not found."}, 404)
        except RuntimeError as exc:
            self._json({"error": str(exc)}, 409)


def serve(root: Path, port=8765, open_browser=False, base_url="http://localhost:11434"):
    manager = LabManager(root, base_url)
    try:
        server = LabServer(("127.0.0.1", port), manager)
    except OSError:
        manager.close()
        raise
    address = f"http://127.0.0.1:{server.server_port}"
    print(f"Dream Lab: {address}\nSaved work: {root.resolve()}\nPress Ctrl+C to stop the server after the current step.", flush=True)
    if open_browser:
        webbrowser.open(address)
    try:
        server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:
        print("Saving the current step…", flush=True)
    finally:
        server.server_close()
        manager.close()
