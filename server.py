#!/usr/bin/env python3
"""Authenticated local-first fine-tuning preparation and synthetic demo server."""
from __future__ import annotations

import argparse
import csv
import getpass
import io
import ipaddress
import json
import mimetypes
import os
from pathlib import Path
import re
import socket
import ssl
import threading
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

from auth import AuthStore, COOKIE_NAME, SESSION_SECONDS, is_loopback_peer
from simulator import DashboardError, Simulator
from workspace import Workspace

MAX_REQUEST_BYTES = 16 * 1024
MAX_DATASET_REQUEST_BYTES = 256 * 1024
MAX_STATIC_BYTES = 8 * 1024 * 1024
RUN_PATH = re.compile(r"^/api/runs/(run-[0-9]{4,12})(?:/(start|pause|resume|cancel|retry))?$")
RUN_EXPORT_PATH = re.compile(r"^/api/runs/(run-[0-9]{4,12})/export$")
DATASET_PATH = re.compile(r"^/api/datasets/([A-Za-z0-9_-]{1,80})(?:/(split|export))?$")
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
STATIC_TYPES = {".html", ".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".ico", ".webp", ".woff", ".woff2"}


def validate_bind(host, lan=False):
    if host in LOOPBACK_HOSTS:
        return
    if not lan:
        raise ValueError("Nonloopback binding requires explicit --lan opt-in.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        raise ValueError("LAN binding requires a literal private IP address or wildcard address.") from None
    networks = (ipaddress.ip_network("10.0.0.0/8"), ipaddress.ip_network("172.16.0.0/12"),
                ipaddress.ip_network("192.168.0.0/16"), ipaddress.ip_network("fc00::/7"))
    if not address.is_unspecified and not any(address.version == network.version and address in network for network in networks):
        raise ValueError("Use an RFC1918 private LAN address or IPv6 ULA; public, reserved, multicast and link-local addresses are refused.")


def validate_allowed_host(host):
    if not isinstance(host, str) or len(host) > 253 or host != host.lower():
        raise ValueError("Allowed hosts must be lowercase hostnames or bare IP addresses without ports.")
    if ":" in host:
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            raise ValueError("Invalid allowed IPv6 host.") from None
    elif not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host) or ".." in host:
        raise ValueError("Invalid allowed hostname.")
    return host


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, simulator: Simulator, static_dir: Path, *, auth=None,
                 workspace=None, lan=False, allowed_hosts=(), tls_context=None, allow_insecure_http=False):
        validate_bind(address[0], lan)
        self.listener_lan = address[0] not in LOOPBACK_HOSTS
        if self.listener_lan and auth is False:
            raise ValueError("LAN listeners cannot disable authentication.")
        if self.listener_lan and tls_context is None and not allow_insecure_http:
            raise ValueError("LAN listeners require TLS, or explicit --allow-insecure-http acknowledgement.")
        self.allowed_hosts = set(LOOPBACK_HOSTS)
        self.allowed_hosts.update(validate_allowed_host(host) for host in allowed_hosts)
        if address[0] not in {"0.0.0.0", "::"}:
            self.allowed_hosts.add(address[0])
        elif not allowed_hosts:
            raise ValueError("Wildcard LAN listeners require at least one explicit --allowed-host.")
        if ":" in address[0]:
            self.address_family = socket.AF_INET6
        self.simulator = simulator
        self.static_dir = static_dir.resolve()
        self.tls = tls_context is not None
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.worker_error = None
        self._owns_auth = auth is None
        self._owns_workspace = workspace is None
        db_dir = Path(simulator.db_path).parent
        self.auth = AuthStore(db_dir / "auth.sqlite3") if auth is None else auth
        self.workspace = workspace if workspace is not None else Workspace(db_dir / "workspace.sqlite3", workspace_path=Path(__file__).resolve().parent)
        self._resources_closed = False
        try:
            super().__init__(address, DashboardHandler)
            if tls_context:
                self.socket = tls_context.wrap_socket(self.socket, server_side=True)
        except Exception:
            if self._owns_auth:
                self.auth.close()
            if self._owns_workspace and hasattr(self.workspace, "close"):
                self.workspace.close()
            raise

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
        if not self._resources_closed:
            self._resources_closed = True
            if self._owns_auth:
                self.auth.close()
            if self._owns_workspace and hasattr(self.workspace, "close"):
                self.workspace.close()


class DashboardHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "LocalFineTuneDemo/2.0"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(10)
        self.response_cookie = None

    def log_message(self, fmt, *args):
        # Never log passwords, cookies, labels, bodies, or arbitrary request targets.
        return

    def _headers(self, status, content_type, length, filename=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if self.server.tls:
            self.send_header("Strict-Transport-Security", "max-age=86400")
        if self.response_cookie:
            self.send_header("Set-Cookie", self.response_cookie)
            self.response_cookie = None
        if filename:
            # All export filenames are internally generated; reject unsafe facade results.
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,140}", filename):
                raise ValueError("Invalid export filename")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body))
        if self.command != "HEAD":
            self.wfile.write(body)

    def _download(self, body, filename, content_type):
        if not isinstance(body, bytes) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,140}", filename):
            raise DashboardError("invalid_export", "Export output is not valid.", 500)
        self._headers(200, content_type, len(body), filename)
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, err):
        self.close_connection = True
        # Mutation validation details can include previews/duplicate metadata.
        # Remote control never becomes a back door to view-denied data.
        if self.command == "POST" and err.details is not None and not self._can_view_response():
            err = DashboardError(err.code, err.message, err.status)
        self._json(err.status, err.as_dict())

    @property
    def peer(self):
        return self.client_address[0]

    def _authority(self, value):
        if not value or value != value.strip() or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value) or any(c in value for c in "/\\?#@"):
            return None
        try:
            parsed = urlsplit("http://" + value)
            port = parsed.port if parsed.port is not None else (443 if self.server.tls else 80)
        except ValueError:
            return None
        if parsed.hostname not in self.server.allowed_hosts or parsed.username or parsed.password:
            return None
        if port != self.server.server_port:
            return None
        return (parsed.hostname, port)

    def _guard(self, post=False):
        hosts = self.headers.get_all("Host", [])
        if len(hosts) != 1 or self._authority(hosts[0]) is None:
            raise DashboardError("invalid_host", "An explicitly allowed Host header with this server's port is required.", 403)
        if self.server.auth is not False:
            self.server.auth.guard_peer(self.peer)
        if post:
            origins = self.headers.get_all("Origin", [])
            if len(origins) > 1 or (self.server.auth is not False and not origins):
                raise DashboardError("invalid_origin", "One same-origin Origin header is required.", 403)
            if origins:
                origin = origins[0]
                if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in origin):
                    raise DashboardError("invalid_origin", "Malformed Origin header.", 403)
                try:
                    parsed = urlsplit(origin)
                except ValueError:
                    parsed = None
                expected_scheme = "https" if self.server.tls else "http"
                if (parsed is None or parsed.scheme != expected_scheme or parsed.path or parsed.query or parsed.fragment
                        or parsed.username or parsed.password or self._authority(parsed.netloc) != self._authority(hosts[0])):
                    raise DashboardError("invalid_origin", "POST requests must have this server's exact same origin.", 403)
            sites = self.headers.get_all("Sec-Fetch-Site", [])
            if len(sites) > 1 or (sites and sites[0] not in {"same-origin", "none"}):
                raise DashboardError("invalid_origin", "Cross-origin browser requests are not permitted.", 403)

    def _path(self):
        raw_target = self.requestline.split(" ")[1]
        if raw_target.startswith("//"):
            raise DashboardError("invalid_path", "Network-path request targets are not accepted.", 400)
        if len(self.path) > 2048 or not self.path.startswith("/") or self.path.startswith("//"):
            raise DashboardError("invalid_path", "Invalid request path.", 400)
        parts = urlsplit(self.path)
        if parts.scheme or parts.netloc or parts.fragment:
            raise DashboardError("invalid_path", "Only local relative request paths are accepted.", 400)
        if re.search(r"%(?:2f|5c|2e|00)", parts.path, re.I):
            raise DashboardError("invalid_path", "Encoded path separators and traversal are not allowed.", 400)
        path = unquote(parts.path, errors="strict")
        if "\\" in path or "\x00" in path or any(p in {".", ".."} or p.startswith(".") for p in path.split("/") if p):
            raise DashboardError("invalid_path", "Path traversal and hidden files are not allowed.", 400)
        return path

    def _body(self, limit=MAX_REQUEST_BYTES):
        if self.headers.get_all("Transfer-Encoding", []):
            raise DashboardError("invalid_body", "Transfer-Encoding is not supported.", 400)
        sizes = self.headers.get_all("Content-Length", [])
        if len(sizes) != 1 or not re.fullmatch(r"[0-9]+", sizes[0]):
            raise DashboardError("invalid_body", "One numeric Content-Length header is required.", 411)
        if len(sizes[0]) > 8 or int(sizes[0]) > limit:
            raise DashboardError("request_too_large", f"JSON request exceeds {limit // 1024} KiB.", 413)
        length = int(sizes[0])
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

    def _cookie(self):
        cookies = self.headers.get_all("Cookie", [])
        if len(cookies) != 1 or len(cookies[0]) > 4096:
            return None
        # Do not permit duplicate auth-cookie names hidden in a single header.
        if sum(part.strip().partition("=")[0] == COOKIE_NAME for part in cookies[0].split(";")) != 1:
            return None
        try:
            parsed = SimpleCookie(cookies[0])
            return parsed[COOKIE_NAME].value if COOKIE_NAME in parsed else None
        except CookieError:
            return None

    def _csrf(self):
        values = self.headers.get_all("X-CSRF-Token", [])
        return values[0] if len(values) == 1 and len(values[0]) < 128 else None

    def _set_session_cookie(self, token=None):
        value = token or ""
        age = SESSION_SECONDS if token else 0
        self.response_cookie = f"{COOKIE_NAME}={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}"
        if self.server.tls:
            self.response_cookie += "; Secure"

    def _settings(self):
        if self.server.auth is False:
            return {"configured": {key: False for key in ("lan_access", "remote_view", "remote_control")},
                    "effective": {key: False for key in ("lan_access", "remote_view", "remote_control")},
                    "bootstrap_required": False, "listener_lan": False, "tls": self.server.tls}
        return self.server.auth.settings(listener_lan=self.server.listener_lan, tls=self.server.tls)

    def _auth_status(self, session=None):
        if self.server.auth is False:
            return {"authenticated": True, "username": "test-only", "must_change_password": False,
                    "csrf_token": None, "local_peer": is_loopback_peer(self.peer), "settings": self._settings()}
        if session is None:
            session = self.server.auth.session(self._cookie(), self.peer)
        return {"authenticated": session is not None, "username": session["username"] if session else None,
                "must_change_password": self.server.auth.bootstrap_required,
                "csrf_token": session["csrf_token"] if session else None,
                "local_peer": is_loopback_peer(self.peer), "settings": self._settings()}

    def _authorize(self, *, mutation=False, bootstrap=False, remote_operation=None):
        if self.server.auth is False:
            return None
        session = self.server.auth.require_session(self._cookie(), self.peer, csrf=self._csrf(), mutation=mutation, allow_bootstrap=bootstrap)
        self.server.auth.guard_peer(self.peer, operation=remote_operation or ("remote_control" if mutation else "remote_view"))
        return session

    def _can_view_response(self):
        if self.server.auth is False or is_loopback_peer(self.peer):
            return True
        return self.server.auth.settings()["configured"]["remote_view"]

    def _snapshot(self):
        snapshot = self.server.simulator.snapshot()
        snapshot["settings"] = self._settings()
        if self.server.worker_error:
            snapshot["health"]["status"] = "degraded"
            snapshot["health"]["message"] = "Demo worker stopped. Restart the local service to resume simulation."
        return snapshot

    def _query(self, allowed):
        query = parse_qs(urlsplit(self.path).query, keep_blank_values=True, max_num_fields=8)
        if set(query) - set(allowed) or any(len(values) != 1 for values in query.values()):
            raise DashboardError("invalid_query", "Only the documented export query parameters are supported.")
        return {key: values[0] for key, values in query.items()}

    def _run_export(self, run_id):
        query = self._query({"format"})
        fmt = query.get("format", "json")
        run = self.server.simulator.get_run(run_id)
        # Explicit metadata allowlist; no paths, adapter files, model downloads or credentials.
        keys = ("id", "name", "status", "config", "metrics", "logs", "checkpoints", "created_at", "started_at", "finished_at", "elapsed_seconds", "step", "total_steps", "retry_of", "simulated")
        export = {key: run[key] for key in keys if key in run}
        export.update(mode="demo", synthetic=True, checkpoint_files=False)
        if fmt == "json":
            body = json.dumps(export, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
            return self._download(body, f"{run_id}-synthetic.json", "application/json; charset=utf-8")
        if fmt == "csv":
            stream = io.StringIO(newline="")
            fields = ["section", "index", "key", "value"]
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            def safe(value):
                # Quote every string cell, including invisible/whitespace-leading
                # formula variants. Numeric JSON scalars remain ordinary data.
                if isinstance(value, str):
                    return "'" + value
                return json.dumps(value, ensure_ascii=False, allow_nan=False)
            for section, value in export.items():
                rows = value if isinstance(value, list) else [value]
                for index, row in enumerate(rows):
                    for key, cell in (row.items() if isinstance(row, dict) else [("value", row)]):
                        writer.writerow({"section": section, "index": index, "key": safe(key), "value": safe(cell)})
            return self._download(stream.getvalue().encode("utf-8"), f"{run_id}-synthetic.csv", "text/csv; charset=utf-8")
        raise DashboardError("invalid_query", "Run export format must be json or csv.")

    def do_GET(self):
        try:
            self._guard()
            path = self._path()
            if path == "/api/auth/status":
                return self._json(200, self._auth_status())
            if path.startswith("/api/"):
                self._authorize(bootstrap=path == "/api/settings")
                if path == "/api/settings":
                    return self._json(200, self._settings())
                if path == "/api/status":
                    return self._json(200, self._snapshot())
                if path == "/api/workspace":
                    return self._json(200, self.server.workspace.summary())
                if path == "/api/presets":
                    return self._json(200, self.server.workspace.presets())
                if path == "/api/diagnostics":
                    return self._json(200, self.server.workspace.diagnostics())
                if path == "/api/datasets":
                    return self._json(200, {"datasets": self.server.workspace.list_datasets()})
                dataset = DATASET_PATH.fullmatch(path)
                if dataset and dataset.group(2) is None:
                    return self._json(200, {"dataset": self.server.workspace.get_dataset(dataset.group(1))})
                if dataset and dataset.group(2) == "export":
                    query = self._query({"split"})
                    split = query.get("split", "train")
                    if split not in {"train", "validation"}:
                        raise DashboardError("invalid_query", "Dataset export split must be train or validation.")
                    body, filename = self.server.workspace.export_dataset(dataset.group(1), split)
                    return self._download(body, filename, "application/x-ndjson; charset=utf-8")
                export = RUN_EXPORT_PATH.fullmatch(path)
                if export:
                    return self._run_export(export.group(1))
                match = RUN_PATH.fullmatch(path)
                if match and not match.group(2):
                    return self._json(200, {"run": self.server.simulator.get_run(match.group(1))})
                raise DashboardError("not_found", "API route does not exist.", 404)
            # The shipped login shell is public after the LAN/bootstrap gate.
            # Knowing its source/routes never grants authenticated API data access.
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
            self._error(DashboardError("invalid_path", "Invalid request path or query.", 400))
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            self._error(DashboardError("server_error", "Local dashboard request failed.", 500))

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        try:
            self._guard(post=True)
            path = self._path()
            if path == "/api/auth/login":
                payload = self._body()
                if self.server.auth is False:
                    raise DashboardError("not_found", "Authentication is disabled only in this injected test fixture.", 404)
                if set(payload) != {"username", "password"}:
                    raise DashboardError("invalid_body", "Login requires only username and password.")
                token, session = self.server.auth.login(payload["username"], payload["password"], self.peer)
                self._set_session_cookie(token)
                return self._json(200, self._auth_status(session))
            operation = ("remote_view" if path in {"/api/datasets/validate", "/api/config/dry-run"}
                         else "authentication" if path == "/api/auth/logout" else "remote_control")
            self._authorize(mutation=True, bootstrap=path in {"/api/auth/change-password", "/api/auth/logout", "/api/settings"}, remote_operation=operation)
            payload = self._body(MAX_DATASET_REQUEST_BYTES if path in {"/api/datasets/validate", "/api/datasets/import", "/api/datasets"} else MAX_REQUEST_BYTES)
            if path == "/api/auth/change-password":
                if set(payload) != {"current_password", "new_password"}:
                    raise DashboardError("invalid_body", "Password change requires only current_password and new_password.")
                token, session = self.server.auth.change_password(self._cookie(), self.peer, payload["current_password"], payload["new_password"], self._csrf())
                self._set_session_cookie(token)
                return self._json(200, self._auth_status(session))
            if path == "/api/auth/logout":
                if payload:
                    raise DashboardError("invalid_body", "Logout body must be an empty JSON object.")
                self.server.auth.logout(self._cookie())
                self._set_session_cookie()
                return self._json(200, {"authenticated": False})
            if path == "/api/settings":
                self.server.auth.update_settings(payload)
                return self._json(200, self._settings())
            if path == "/api/datasets/validate":
                return self._json(200, self.server.workspace.validate_dataset(payload))
            if path in {"/api/datasets/import", "/api/datasets"}:
                result = self.server.workspace.import_dataset(payload)
                if not self._can_view_response():
                    result = {"dataset": {"id": result["dataset"]["id"], "count": result["dataset"]["count"]},
                              "imported": True}
                return self._json(201, result)
            if path == "/api/config/dry-run":
                return self._json(200, self.server.workspace.dry_run(payload))
            dataset = DATASET_PATH.fullmatch(path)
            if dataset and dataset.group(2) == "split":
                result = self.server.workspace.split_dataset(dataset.group(1), payload)
                if not self._can_view_response():
                    result = {key: result[key] for key in ("dataset_id", "seed", "train_count", "validation_count")}
                return self._json(200, result)
            sim = self.server.simulator
            if path == "/api/runs":
                run = sim.queue(payload)
                result = {"run": run, "snapshot": self._snapshot()} if self._can_view_response() else {"run": {"id": run["id"], "status": run["status"]}}
                return self._json(201, result)
            match = RUN_PATH.fullmatch(path)
            if match and match.group(2):
                if payload:
                    raise DashboardError("invalid_body", "Run action bodies must be an empty JSON object.")
                run = sim.action(match.group(1), match.group(2))
                result = {"run": run, "snapshot": self._snapshot()} if self._can_view_response() else {"run": {"id": run["id"], "status": run["status"]}}
                return self._json(201 if match.group(2) == "retry" else 200, result)
            if path == "/api/demo/reset":
                if payload:
                    raise DashboardError("invalid_body", "Demo reset body must be an empty JSON object.")
                sim.reset()
                return self._json(200, {"snapshot": self._snapshot()} if self._can_view_response() else {"reset": True})
            raise DashboardError("not_found", "API route does not exist.", 404)
        except DashboardError as err:
            self._error(err)
        except (ValueError, UnicodeError):
            self._error(DashboardError("invalid_path", "Invalid request path.", 400))
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            self._error(DashboardError("server_error", "Local dashboard request failed.", 500))

    def _unsupported(self):
        try:
            self._guard()
            raise DashboardError("method_not_allowed", "Only GET, HEAD and JSON POST are supported.", 405)
        except DashboardError as err:
            self._error(err)

    do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _unsupported


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Default loopback. Private LAN address requires --lan.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", type=Path, default=Path(__file__).resolve().parent / "data" / "state.sqlite3")
    parser.add_argument("--auth-db", type=Path, help="Salted authentication database, default next to --db.")
    parser.add_argument("--static-dir", type=Path, default=Path(__file__).resolve().parent / "static")
    parser.add_argument("--lan", action="store_true", help="Permit an explicitly requested private LAN listener; first-use setup still requires loopback.")
    parser.add_argument("--allowed-host", action="append", default=[], help="Exact permitted lowercase hostname/IP, without port. Required for wildcard LAN binding.")
    parser.add_argument("--tls-cert", type=Path, help="User-provided TLS certificate PEM.")
    parser.add_argument("--tls-key", type=Path, help="User-provided TLS private-key PEM, never served to the browser.")
    parser.add_argument("--allow-insecure-http", action="store_true", help="Explicitly acknowledge insecure LAN HTTP; credentials and cookies can be intercepted.")
    parser.add_argument("--prompt-initial-password", action="store_true", help="Read a strong initial password privately from the terminal, only for a new auth database.")
    parser.add_argument("--no-worker", action="store_true", help="Do not advance the simulation (for tests).")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    if bool(args.tls_cert) != bool(args.tls_key):
        parser.error("--tls-cert and --tls-key must be provided together")
    try:
        validate_bind(args.host, args.lan)
        for host in args.allowed_host:
            validate_allowed_host(host)
    except ValueError as exc:
        parser.error(str(exc))
    remote_listener = args.host not in LOOPBACK_HOSTS
    if remote_listener and not args.tls_cert and not args.allow_insecure_http:
        parser.error("LAN requires --tls-cert and --tls-key, or explicit --allow-insecure-http")
    if args.host in {"0.0.0.0", "::"} and not args.allowed_host:
        parser.error("Wildcard LAN binding requires --allowed-host for the machine's actual LAN IP/name")
    tls_context = None
    if args.tls_cert:
        tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls_context.minimum_version = ssl.TLSVersion.TLSv1_2
        tls_context.load_cert_chain(args.tls_cert, args.tls_key)
    auth_path = args.auth_db or args.db.parent / "auth.sqlite3"
    initial_password = os.environ.pop("DASHBOARD_INITIAL_PASSWORD", "admin")
    if args.prompt_initial_password and not auth_path.exists():
        initial_password = getpass.getpass("Initial admin password (12+ characters): ")
    auth = AuthStore(auth_path, initial_password=initial_password)
    initial_password = None
    simulator = Simulator(args.db)
    try:
        server = DashboardServer((args.host, args.port), simulator, args.static_dir, auth=auth,
                                 lan=args.lan, allowed_hosts=args.allowed_host, tls_context=tls_context,
                                 allow_insecure_http=args.allow_insecure_http)
    except Exception:
        auth.close()
        simulator.close()
        raise
    if not args.no_worker:
        server.start_worker()
    display_host = f"[{args.host}]" if ":" in args.host else args.host
    scheme = "https" if server.tls else "http"
    print(f"Forge Fine-tuning Dashboard (synthetic demo): {scheme}://{display_host}:{server.server_port}", flush=True)
    print("Training telemetry is synthetic. No training or model downloads. Diagnostics may read an installed GPU utility. Ctrl+C stops the service.", flush=True)
    if auth.bootstrap_required:
        print("LOCAL SETUP REQUIRED: log in as admin on loopback and change the initial password; external LAN is blocked.", flush=True)
    if remote_listener and not server.tls:
        print("WARNING: insecure LAN HTTP explicitly enabled. Passwords and session cookies can be intercepted.", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        auth.close()
        simulator.close()


if __name__ == "__main__":
    main()
