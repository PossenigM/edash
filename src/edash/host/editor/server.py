"""Local HTTP server for the layout editor.

Binds to 127.0.0.1 only. API requests must carry the per-session token from the
URL fragment, so other web pages open in the browser cannot read or write the
configuration.
"""

from __future__ import annotations

import hmac
import json
import logging
import secrets
import socket
import threading
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from edash.config import load_config
from edash.errors import ConfigError
from edash.host.editor import model
from edash.render.fonts import Fonts
from edash.render.i18n import LOCALES
from edash.render.registry import WIDGETS

log = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"
CONTENT_TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}
MAX_BODY = 2_000_000
DEFAULT_CONTROL_PORT = 47811


class EditorServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, load_path: Path, save_path: Path, port: int = 0):
        super().__init__(("127.0.0.1", port), _Handler)
        self.load_path = load_path
        self.save_path = save_path
        self.token = secrets.token_urlsafe(24)
        self.fonts = Fonts()
        self.render_lock = threading.Lock()

    @property
    def port(self) -> int:
        return self.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/#{self.token}"

    def api_load(self, _: dict[str, Any]) -> dict[str, Any]:
        text = self.load_path.read_text(encoding="utf-8") if self.load_path.exists() else ""
        reply: dict[str, Any] = {
            "path": str(self.save_path),
            "fields": model.widget_fields(),
            "widgets": sorted(WIDGETS),
            "languages": sorted(LOCALES),
        }
        try:
            reply["data"] = model.parse_yaml(text)
        except ConfigError as err:
            reply.update(data=None, yaml=text, errors=err.messages)
        return reply

    def api_render(self, body: dict[str, Any]) -> dict[str, Any]:
        at = body.get("at")
        now = datetime.fromisoformat(at).astimezone() if at else datetime.now().astimezone()
        with self.render_lock:
            return model.render_screen(body.get("data"), str(body.get("screen") or ""), now, self.fonts)

    def api_yaml(self, body: dict[str, Any]) -> dict[str, Any]:
        return {"yaml": model.dump_yaml(body.get("data"))}

    def api_parse(self, body: dict[str, Any]) -> dict[str, Any]:
        return {"data": model.parse_yaml(str(body.get("yaml", "")))}

    def api_save(self, body: dict[str, Any]) -> dict[str, Any]:
        model.save_config(body.get("data"), self.save_path)
        self.load_path = self.save_path
        log.info("saved %s", self.save_path)
        return {"path": str(self.save_path)}

    def api_show(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            port = load_config(self.save_path).host.control_port
        except ConfigError:
            port = DEFAULT_CONTROL_PORT
        request = {"action": "screen", "arg": str(body.get("screen") or "auto")}
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
                sock.sendall(json.dumps(request).encode() + b"\n")
                reply = json.loads(sock.makefile().readline())
        except OSError:
            raise ConfigError([f"no running edash-host on port {port}"]) from None
        if not reply.get("ok"):
            raise ConfigError([str(reply.get("error", "the display is not connected to the host"))])
        return {}


API = {
    "/api/load": EditorServer.api_load,
    "/api/render": EditorServer.api_render,
    "/api/yaml": EditorServer.api_yaml,
    "/api/parse": EditorServer.api_parse,
    "/api/save": EditorServer.api_save,
    "/api/show": EditorServer.api_show,
}


class _Handler(BaseHTTPRequestHandler):
    server: EditorServer

    def log_message(self, format: str, *args: Any) -> None:
        log.debug(format, *args)

    def do_GET(self) -> None:
        name = "index.html" if self.path in ("/", "/index.html") else self.path.removeprefix("/static/")
        path = STATIC / name
        if "/" in name or not path.is_file() or path.suffix not in CONTENT_TYPES:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._send(HTTPStatus.OK, path.read_bytes(), CONTENT_TYPES[path.suffix])

    def do_POST(self) -> None:
        handler = API.get(self.path)
        if handler is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not self._authorized():
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            reply = handler(self.server, body if isinstance(body, dict) else {})
        except ConfigError as err:
            reply = {"errors": err.messages}
        except (ValueError, OSError) as err:
            reply = {"errors": [str(err)]}
        except Exception as err:
            log.exception("%s failed", self.path)
            reply = {"errors": [f"internal error: {err}"]}
        payload = json.dumps(reply, default=str).encode()
        self._send(HTTPStatus.OK, payload, "application/json")

    def _authorized(self) -> bool:
        host = self.headers.get("Host", "")
        if host not in (f"127.0.0.1:{self.server.port}", f"localhost:{self.server.port}"):
            return False
        token = self.headers.get("X-Edash-Token", "")
        return hmac.compare_digest(token.encode(), self.server.token.encode())

    def _send(self, status: HTTPStatus, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)
