#!/usr/bin/env python3
"""Loopback-only, zero-dependency server for a fine-tuning demo dashboard."""
from __future__ import annotations

import argparse
import json
import mimetypes
from pathlib import Path
import re
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from simulator import DashboardError, Simulator

MAX_REQUEST_BYTES = 16 * 1024
MAX_STATIC_BYTES = 8 * 1024 * 1024
RUN_PATH = re.compile(r"^/api/runs/(run-[0-9]{4,12})(?:/(start|pause|resume|cancel|retry))?$")
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
STATIC_TYPES = {".html", ".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".ico", ".webp", ".woff", ".woff2"}


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, simulator: Simulator, static_dir: Path):
        if address[0] not in LOOPBACK_HOSTS:
            raise ValueError("The demo server may only bind to a loopback address.")
        if address[0] == "::1":
            self.address_family = socket.AF_INET6
        self.simulator = simulator
        self.static_dir = static_dir.resolve()
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.worker_error = None
        super().__init__(address, DashboardHandler)

    def start_worker(self):
        if self.worker_thread is not None:
            return
        def work():
            self.simulator.worker_alive = True
            try:
                while not self.stop_event.wait(0.5):
                    self.simulator.tick()
            except Exception as exc:
                self.worker_error = type(exc).__name__
            finally:
                self.simulator.worker_alive = False
        self.worker_thread = threading.Thread(target=work, name="demo-simulator", daemon=True)
        self.worker_thread.start()

    def server_close(self):
        self.stop_event.set()
        if self.worker_thread:
            self.worker_thread.join(timeout=3)
        super().server_close()


class DashboardHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "LocalFineTuneDemo/1.0"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, fmt, *args):
        # Requests are local; avoid logging arbitrary labels or request bodies.
        return

    def _headers(self, status, content_type, length):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body))
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, err):
        self.close_connection = True
        self._json(err.status, err.as_dict())

    def _authority(self, value):
        if not value or value != value.strip() or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value) or any(c in value for c in "/\\?#@"):
            return None
        try:
            parsed = urlsplit("http://" + value)
            port = parsed.port or 80
        except ValueError:
            return None
        if parsed.hostname not in LOOPBACK_HOSTS or parsed.username or parsed.password:
            return None
        if port != self.server.server_port:
            return None
        return (parsed.hostname, port)

    def _guard(self, post=False):
        hosts = self.headers.get_all("Host", [])
        if len(hosts) != 1 or self._authority(hosts[0]) is None:
            raise DashboardError("invalid_host", "A loopback Host header with this server's port is required.", 403)
        if post:
            origins = self.headers.get_all("Origin", [])
            if len(origins) > 1:
                raise DashboardError("invalid_origin", "Multiple Origin headers are not allowed.", 403)
            if origins:
                origin = origins[0]
                if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in origin):
                    raise DashboardError("invalid_origin", "Malformed Origin header.", 403)
                try:
                    parsed = urlsplit(origin)
                except ValueError:
                    parsed = None
                if (parsed is None or parsed.scheme != "http" or parsed.path or parsed.query or parsed.fragment
                        or parsed.username or parsed.password or self._authority(parsed.netloc) != self._authority(hosts[0])):
                    raise DashboardError("invalid_origin", "POST requests must be same-origin with this loopback server.", 403)
            sites = self.headers.get_all("Sec-Fetch-Site", [])
            if len(sites) > 1 or (sites and sites[0] not in {"same-origin", "none"}):
                raise DashboardError("invalid_origin", "Cross-origin browser requests are not permitted.", 403)
            # Nonbrowser CLI clients may omit Origin. Browser requests are still
            # protected by JSON-only POST bodies and Sec-Fetch-Site checks.

    def _path(self):
        raw_target = self.requestline.split(" ")[1]
        if raw_target.startswith("//"):
            raise DashboardError("invalid_path", "Network-path request targets are not accepted.", 400)
        if len(self.path) > 2048 or not self.path.startswith("/") or self.path.startswith("//"):
            raise DashboardError("invalid_path", "Invalid request path.", 400)
        parts = urlsplit(self.path)
        if parts.scheme or parts.netloc or parts.fragment:
            raise DashboardError("invalid_path", "Only local relative request paths are accepted.", 400)
        raw = parts.path
        # Reject encoded separators and dots before normalization, not after it.
        if re.search(r"%(?:2f|5c|2e|00)", raw, re.I):
            raise DashboardError("invalid_path", "Encoded path separators and traversal are not allowed.", 400)
        path = unquote(raw, errors="strict")
        if "\\" in path or "\x00" in path or any(p in {".", ".."} or p.startswith(".") for p in path.split("/") if p):
            raise DashboardError("invalid_path", "Path traversal and hidden files are not allowed.", 400)
        return path

    def _body(self):
        if self.headers.get_all("Transfer-Encoding", []):
            raise DashboardError("invalid_body", "Transfer-Encoding is not supported.", 400)
        sizes = self.headers.get_all("Content-Length", [])
        if len(sizes) != 1 or not re.fullmatch(r"[0-9]+", sizes[0]):
            raise DashboardError("invalid_body", "One numeric Content-Length header is required.", 411)
        if len(sizes[0]) > 8:
            raise DashboardError("request_too_large", "JSON request exceeds 16 KiB.", 413)
        length = int(sizes[0])
        if length > MAX_REQUEST_BYTES:
            raise DashboardError("request_too_large", "JSON request exceeds 16 KiB.", 413)
        types = self.headers.get_all("Content-Type", [])
        if len(types) != 1 or types[0].split(";", 1)[0].strip().lower() != "application/json":
            raise DashboardError("unsupported_media_type", "POST bodies must use application/json.", 415)
        try:
            body = self.rfile.read(length)
        except (TimeoutError, OSError):
            raise DashboardError("invalid_body", "Timed out while reading request body.", 408)
        if len(body) != length:
            raise DashboardError("invalid_body", "Incomplete request body.", 400)
        def reject_constant(value):
            raise ValueError("Nonfinite numeric value")
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate JSON key")
                result[key] = value
            return result
        try:
            result = json.loads(body.decode("utf-8"), parse_constant=reject_constant, object_pairs_hook=unique_object)
        except (ValueError, UnicodeError, RecursionError):
            raise DashboardError("invalid_json", "Request body must be valid UTF-8 JSON with unique keys and finite numbers.", 400)
        if not isinstance(result, dict):
            raise DashboardError("invalid_json", "Request body must be a JSON object.", 400)
        return result

    def _snapshot(self):
        snapshot = self.server.simulator.snapshot()
        if self.server.worker_error:
            snapshot["health"]["status"] = "degraded"
            snapshot["health"]["message"] = "Demo worker stopped. Restart the local service to resume simulation."
        return snapshot

    def do_GET(self):
        try:
            self._guard()
            path = self._path()
            if path == "/api/status":
                return self._json(200, self._snapshot())
            match = RUN_PATH.fullmatch(path)
            if match and not match.group(2):
                return self._json(200, {"run": self.server.simulator.get_run(match.group(1))})
            if path.startswith("/api/"):
                raise DashboardError("not_found", "API route does not exist.", 404)
            relative = "index.html" if path == "/" else path.lstrip("/")
            target = (self.server.static_dir / relative).resolve()
            if not target.is_relative_to(self.server.static_dir) or target.suffix.lower() not in STATIC_TYPES or not target.is_file():
                raise DashboardError("not_found", "Static file does not exist.", 404)
            if target.stat().st_size > MAX_STATIC_BYTES:
                raise DashboardError("not_found", "Static file is too large.", 404)
            body = target.read_bytes()
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if target.suffix.lower() in {".html", ".css", ".js", ".svg"}:
                content_type += "; charset=utf-8"
            self._headers(200, content_type, len(body))
            if self.command != "HEAD":
                self.wfile.write(body)
        except DashboardError as err:
            self._error(err)
        except (ValueError, UnicodeError):
            self._error(DashboardError("invalid_path", "Invalid request path.", 400))
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            self._error(DashboardError("server_error", "Local demo request failed.", 500))

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        try:
            self._guard(post=True)
            path = self._path()
            payload = self._body()
            sim = self.server.simulator
            if path == "/api/runs":
                run = sim.queue(payload)
                return self._json(201, {"run": run, "snapshot": self._snapshot()})
            match = RUN_PATH.fullmatch(path)
            if match and match.group(2):
                if payload:
                    raise DashboardError("invalid_body", "Run action bodies must be an empty JSON object.")
                run = sim.action(match.group(1), match.group(2))
                return self._json(201 if match.group(2) == "retry" else 200, {"run": run, "snapshot": self._snapshot()})
            if path == "/api/demo/reset":
                if payload:
                    raise DashboardError("invalid_body", "Demo reset body must be an empty JSON object.")
                return self._json(200, {"snapshot": sim.reset()})
            raise DashboardError("not_found", "API route does not exist.", 404)
        except DashboardError as err:
            self._error(err)
        except (ValueError, UnicodeError):
            self._error(DashboardError("invalid_path", "Invalid request path.", 400))
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            self._error(DashboardError("server_error", "Local demo request failed.", 500))

    def _unsupported(self):
        try:
            self._guard()
            raise DashboardError("method_not_allowed", "Only GET, HEAD and JSON POST are supported.", 405)
        except DashboardError as err:
            self._error(err)

    do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _unsupported


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=["127.0.0.1", "localhost", "::1"], default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", type=Path, default=Path(__file__).resolve().parent / "data" / "state.sqlite3")
    parser.add_argument("--static-dir", type=Path, default=Path(__file__).resolve().parent / "static")
    parser.add_argument("--no-worker", action="store_true", help="Do not advance the simulation (for tests).")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    simulator = Simulator(args.db)
    server = DashboardServer((args.host, args.port), simulator, args.static_dir)
    if not args.no_worker:
        server.start_worker()
    display_host = f"[{args.host}]" if ":" in args.host else args.host
    print(f"Local fine-tuning DEMO: http://{display_host}:{server.server_port}", flush=True)
    print("Synthetic metrics only. No training, downloads or hardware detection. Ctrl+C stops the service.", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        simulator.close()


if __name__ == "__main__":
    main()
