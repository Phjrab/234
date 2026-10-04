import hashlib
import http.client
import io
from http.cookies import SimpleCookie
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
from email.message import Message
import unittest

from auth import AuthStore, COOKIE_NAME, MAX_LOGIN_FAILURES, MAX_PEERS, MAX_SESSIONS, SESSION_SECONDS, is_loopback_peer
from server import DashboardHandler, DashboardServer, validate_bind
from simulator import DashboardError, Simulator
from workspace import Workspace

# Synthetic credentials only, temporary storage only.
FAKE_PASSWORD = "Synthetic-Test-Passphrase-123!"
LOCAL = "127.0.0.1"
REMOTE = "192.0.2.25"


class AuthStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "auth.sqlite3"
        self.now = 1000
        self.auth = AuthStore(self.path, clock=lambda: self.now)

    def tearDown(self):
        self.auth.close()
        self.tmp.cleanup()

    def assert_code(self, code, call):
        with self.assertRaises(DashboardError) as result:
            call()
        self.assertEqual(result.exception.code, code)

    def setup_password(self):
        token, session = self.auth.login("admin", "admin", LOCAL)
        return self.auth.change_password(token, LOCAL, "admin", FAKE_PASSWORD, session["csrf_token"])

    def test_all_on_intent_is_inactive_until_local_change(self):
        settings = self.auth.settings(listener_lan=True)
        self.assertTrue(all(settings["configured"].values()))
        self.assertFalse(any(settings["effective"].values()))
        self.assertTrue(settings["bootstrap_required"])
        self.assert_code("local_setup_required", lambda: self.auth.login("admin", "admin", REMOTE))
        self.assert_code("local_setup_required", lambda: self.auth.guard_peer(REMOTE))
        self.setup_password()
        self.assertFalse(self.auth.bootstrap_required)
        self.assertTrue(all(self.auth.settings(listener_lan=True)["effective"].values()))
        self.assertFalse(any(self.auth.settings(listener_lan=False)["effective"].values()))
        self.auth.login("admin", FAKE_PASSWORD, REMOTE)
        self.assert_code("invalid_credentials", lambda: self.auth.login("admin", "admin", REMOTE))

    def test_loopback_socket_detection_and_mapped_ipv6(self):
        for peer in ["127.0.0.1", "127.0.0.2", "::1", "::ffff:127.0.0.1"]:
            self.assertTrue(is_loopback_peer(peer), peer)
        for peer in [REMOTE, "::ffff:192.0.2.25", "localhost", "evil", ""]:
            self.assertFalse(is_loopback_peer(peer), peer)

    def test_setup_only_before_password_change(self):
        token, session = self.auth.login("admin", "admin", LOCAL)
        self.assert_code("password_change_required", lambda: self.auth.require_session(token, LOCAL))
        self.assert_code("invalid_csrf", lambda: self.auth.change_password(token, LOCAL, "admin", FAKE_PASSWORD, "bad"))
        self.assert_code("invalid_credentials", lambda: self.auth.change_password(token, LOCAL, "incorrect", FAKE_PASSWORD, session["csrf_token"]))
        for weak in ["admin", "short", "aaaaaaaaaaaa", "adminadminadmin", "            ", "\ud800abcdefghijklm!123", 123]:
            self.assert_code("weak_password", lambda: self.auth.change_password(token, LOCAL, "admin", weak, session["csrf_token"]))
        self.assertTrue(self.auth.bootstrap_required)

    def test_rotation_expiry_logout_and_peer_bound_session(self):
        initial_token, initial_session = self.auth.login("admin", "admin", LOCAL)
        token, session = self.auth.change_password(initial_token, LOCAL, "admin", FAKE_PASSWORD, initial_session["csrf_token"])
        self.assertIsNone(self.auth.session(initial_token, LOCAL))
        self.assertIsNone(self.auth.session(token, REMOTE))
        self.auth.require_session(token, LOCAL, csrf=session["csrf_token"], mutation=True)
        self.assert_code("invalid_csrf", lambda: self.auth.require_session(token, LOCAL, csrf="\u2603", mutation=True))
        self.now += SESSION_SECONDS + 1
        self.assertIsNone(self.auth.session(token, LOCAL))
        token, _ = self.auth.login("admin", FAKE_PASSWORD, LOCAL)
        self.auth.logout(token)
        self.assertIsNone(self.auth.session(token, LOCAL))

    def test_password_hash_flags_persist_and_sessions_do_not(self):
        token, _ = self.setup_password()
        self.auth.update_settings({"remote_control": False})
        self.assertNotIn(FAKE_PASSWORD.encode(), self.path.read_bytes())
        self.assertNotIn(token.encode(), self.path.read_bytes())
        self.assertEqual(len(self.auth.state["salt"]), 64)
        self.assertNotEqual(self.auth.state["password_hash"], hashlib.sha256(FAKE_PASSWORD.encode()).hexdigest())
        self.auth.close()
        self.auth = AuthStore(self.path, clock=lambda: self.now)
        self.assertFalse(self.auth.bootstrap_required)
        self.assertFalse(self.auth.settings(listener_lan=True)["configured"]["remote_control"])
        self.assertIsNone(self.auth.session(token, LOCAL))
        self.auth.login("admin", FAKE_PASSWORD, LOCAL)

    def test_remote_view_and_control_are_independent(self):
        self.setup_password()
        self.auth.update_settings({"remote_view": False, "remote_control": True})
        self.assert_code("remote_view_disabled", lambda: self.auth.guard_peer(REMOTE, operation="remote_view"))
        self.auth.guard_peer(REMOTE, operation="remote_control")
        self.auth.guard_peer(LOCAL, operation="remote_view")
        self.auth.update_settings({"remote_view": True, "remote_control": False})
        self.auth.guard_peer(REMOTE, operation="remote_view")
        self.assert_code("remote_control_disabled", lambda: self.auth.guard_peer(REMOTE, operation="remote_control"))
        self.auth.update_settings({"lan_access": False})
        self.assert_code("lan_disabled", lambda: self.auth.guard_peer(REMOTE))

    def test_settings_boolean_allowlist(self):
        for payload in [{}, {"lan_access": "on"}, {"remote_view": 1}, {"command": "ls"}, {"lan_access": True, "unknown": False}]:
            self.assert_code("invalid_settings", lambda: self.auth.update_settings(payload))

    def test_rate_limiter_expires_is_bounded_and_uses_peer(self):
        for _ in range(MAX_LOGIN_FAILURES):
            self.assert_code("invalid_credentials", lambda: self.auth.login("admin", "wrong", LOCAL))
        self.assert_code("login_rate_limited", lambda: self.auth.login("admin", "admin", LOCAL))
        self.auth.login("admin", "admin", "127.0.0.2")
        self.now += 301
        self.auth.login("admin", "admin", LOCAL)
        with self.auth.lock:
            for index in range(MAX_PEERS + 100):
                self.auth._failure(f"192.0.2.{index}")
        self.assertLessEqual(len(self.auth.failures), MAX_PEERS)
        with self.auth.lock:
            for _ in range(MAX_SESSIONS + 5):
                self.auth._new_session(LOCAL)
        self.assertLessEqual(len(self.auth.sessions), MAX_SESSIONS)

    def test_user_provided_initial_secret_still_requires_local_setup(self):
        other = AuthStore(":memory:", initial_password=FAKE_PASSWORD)
        try:
            self.assertTrue(other.bootstrap_required)
            self.assert_code("local_setup_required", lambda: other.login("admin", FAKE_PASSWORD, REMOTE))
            other.login("admin", FAKE_PASSWORD, LOCAL)
        finally:
            other.close()

    def test_control_only_remote_response_never_leaks_view_data(self):
        self.setup_password()
        self.auth.update_settings({"remote_view": False, "remote_control": True})
        token, session = self.auth.login("admin", FAKE_PASSWORD, REMOTE)
        simulator = Simulator(Path(self.tmp.name) / "state.sqlite3")
        workspace = Workspace(Path(self.tmp.name) / "workspace.sqlite3", workspace_path=self.tmp.name)
        static = Path(self.tmp.name) / "static"
        static.mkdir()
        (static / "index.html").write_text("Public login shell")
        handler = DashboardHandler.__new__(DashboardHandler)
        handler.client_address = (REMOTE, 45678)
        handler.server = SimpleNamespace(auth=self.auth, allowed_hosts={LOCAL}, server_port=8765, tls=False,
                                         listener_lan=True, simulator=simulator, workspace=workspace,
                                         worker_error=None, static_dir=static)
        handler.headers = Message()
        handler.headers["Host"] = "127.0.0.1:8765"
        handler.headers["Origin"] = "http://127.0.0.1:8765"
        handler.headers["Cookie"] = f"{COOKIE_NAME}={token}"
        handler.headers["X-CSRF-Token"] = session["csrf_token"]
        handler._json = lambda status, value: captured.append((status, value))
        def post(path, payload):
            captured.clear()
            handler.command = "POST"
            handler.path = path
            handler.requestline = f"POST {path} HTTP/1.1"
            handler._body = lambda *args: payload
            handler.do_POST()
            return captured[-1]
        captured = []
        try:
            status, body = post("/api/runs", {"name": "Synthetic remote command"})
            self.assertEqual(status, 201)
            self.assertEqual(set(body), {"run"})
            self.assertEqual(set(body["run"]), {"id", "status"})
            run_id = body["run"]["id"]
            status, body = post(f"/api/runs/{run_id}/start", {})
            # Seeded demo may reserve the GPU; action failure is allowed but never telemetry.
            self.assertNotIn("snapshot", body)
            self.assertNotIn("metrics", str(body))
            for path in ["/api/datasets/validate", "/api/config/dry-run"]:
                status, body = post(path, {})
                self.assertEqual(status, 403)
                self.assertEqual(body["error"]["code"], "remote_view_disabled")
            rows = [json.dumps({"instruction": f"Synthetic {i}", "output": "Synthetic answer"}) for i in range(3)]
            status, body = post("/api/datasets", {"name": "Synthetic remote input", "kind": "LLM", "synthetic": True, "text": "\n".join(rows)})
            self.assertEqual(status, 201)
            self.assertEqual(set(body), {"dataset", "imported"})
            self.assertEqual(set(body["dataset"]), {"id", "count"})
            dataset_id = body["dataset"]["id"]
            status, body = post(f"/api/datasets/{dataset_id}/split", {})
            self.assertEqual(status, 200)
            self.assertEqual(set(body), {"dataset_id", "seed", "train_count", "validation_count"})
            status, body = post("/api/datasets", {"text": "bad json"})
            self.assertEqual(status, 400)
            self.assertNotIn("details", body["error"])
            status, body = post("/api/demo/reset", {})
            self.assertEqual(status, 200)
            self.assertEqual(body, {"reset": True})
            handler.command = "GET"
            handler.path = "/api/status"
            handler.requestline = "GET /api/status HTTP/1.1"
            captured.clear()
            handler.do_GET()
            self.assertEqual(captured[-1][0], 403)
            self.assertEqual(captured[-1][1]["error"]["code"], "remote_view_disabled")
            handler.path = "/"
            handler.requestline = "GET / HTTP/1.1"
            handler.wfile = io.BytesIO()
            handler._headers = lambda status, content_type, length: captured.append((status, content_type))
            handler.do_GET()
            self.assertEqual(captured[-1][0], 200)
            self.assertEqual(handler.wfile.getvalue(), b"Public login shell")
            self.auth.update_settings({"remote_control": False})
            status, body = post("/api/auth/logout", {})
            self.assertEqual(status, 200)
            self.assertFalse(body["authenticated"])
        finally:
            simulator.close()
            workspace.close()

    def test_proxy_and_host_headers_do_not_make_peer_local(self):
        handler = DashboardHandler.__new__(DashboardHandler)
        handler.client_address = (REMOTE, 45678)
        handler.server = SimpleNamespace(auth=self.auth, allowed_hosts={"127.0.0.1"}, server_port=8765, tls=False)
        handler.headers = Message()
        handler.headers["Host"] = "127.0.0.1:8765"
        handler.headers["X-Forwarded-For"] = "127.0.0.1"
        handler.headers["Forwarded"] = "for=127.0.0.1;proto=https"
        handler.headers["X-Real-IP"] = "127.0.0.1"
        self.assert_code("local_setup_required", lambda: handler._guard())
        self.setup_password()
        token, session = self.auth.login("admin", FAKE_PASSWORD, REMOTE)
        handler.headers["Cookie"] = f"{COOKIE_NAME}={token}"
        handler.headers["X-CSRF-Token"] = session["csrf_token"]
        self.auth.update_settings({"remote_view": False})
        self.assert_code("remote_view_disabled", lambda: handler._authorize())
        handler._authorize(mutation=True)
        self.auth.update_settings({"remote_control": False})
        self.assert_code("remote_control_disabled", lambda: handler._authorize(mutation=True))


class AuthHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.static = Path(self.tmp.name) / "static"
        self.static.mkdir()
        (self.static / "index.html").write_text("<!doctype html><title>Login</title>")
        (self.static / "app.js").write_text("console.log('public login code')")
        self.auth = AuthStore(Path(self.tmp.name) / "auth.sqlite3")
        self.sim = Simulator(Path(self.tmp.name) / "state.sqlite3", seed_demo=False)
        self.server = DashboardServer((LOCAL, 0), self.sim, self.static, auth=self.auth)
        self.port = self.server.server_port
        self.host = f"{LOCAL}:{self.port}"
        self.origin = f"http://{self.host}"
        self.cookie = None
        self.csrf = None
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.auth.close()
        self.sim.close()
        self.tmp.cleanup()

    def request(self, method, path, payload=None, *, headers=None, save_cookie=True, raw=False):
        client = http.client.HTTPConnection(LOCAL, self.port, timeout=10)
        supplied = {"Host": self.host}
        if self.cookie:
            supplied["Cookie"] = self.cookie
        if method == "POST":
            supplied.update({"Origin": self.origin, "Content-Type": "application/json"})
            if self.csrf:
                supplied["X-CSRF-Token"] = self.csrf
        supplied.update(headers or {})
        supplied = {key: value for key, value in supplied.items() if value is not None}
        body = payload if raw else json.dumps(payload or {}) if method == "POST" else None
        client.request(method, path, body=body, headers=supplied)
        response = client.getresponse()
        data = response.read()
        result_headers = dict(response.getheaders())
        status = response.status
        client.close()
        if save_cookie and "Set-Cookie" in result_headers:
            cookie = SimpleCookie(result_headers["Set-Cookie"])
            self.cookie = f"{COOKIE_NAME}={cookie[COOKIE_NAME].value}" if cookie[COOKIE_NAME].value else None
        content_type = result_headers.get("Content-Type", "")
        payload = json.loads(data) if content_type.startswith("application/json") else data
        if isinstance(payload, dict) and payload.get("csrf_token"):
            self.csrf = payload["csrf_token"]
        return status, result_headers, payload

    def login_and_setup(self):
        self.assertEqual(self.request("POST", "/api/auth/login", {"username": "admin", "password": "admin"})[0], 200)
        self.assertEqual(self.request("POST", "/api/auth/change-password", {"current_password": "admin", "new_password": FAKE_PASSWORD})[0], 200)

    def test_local_bootstrap_contract_cookie_and_data_gate(self):
        status, _, result = self.request("GET", "/api/auth/status")
        self.assertEqual(status, 200)
        self.assertFalse(result["authenticated"])
        self.assertIsNone(result["csrf_token"])
        self.assertTrue(result["must_change_password"])
        self.assertTrue(all(result["settings"]["configured"].values()))
        self.assertFalse(any(result["settings"]["effective"].values()))
        self.assertEqual(self.request("GET", "/api/status")[0], 401)
        self.assertEqual(self.request("GET", "/")[0], 200)
        status, headers, result = self.request("POST", "/api/auth/login", {"username": "admin", "password": "admin"})
        self.assertEqual(status, 200)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        self.assertNotIn("Secure", headers["Set-Cookie"])
        self.assertEqual(self.request("GET", "/api/status")[0], 403)
        self.assertEqual(self.request("GET", "/api/settings")[0], 200)
        old_cookie = self.cookie
        status, _, result = self.request("POST", "/api/auth/change-password", {"current_password": "admin", "new_password": FAKE_PASSWORD})
        self.assertEqual(status, 200)
        self.assertFalse(result["must_change_password"])
        self.assertNotEqual(self.cookie, old_cookie)
        self.assertEqual(self.request("GET", "/api/status")[0], 200)
        self.assertEqual(self.request("GET", "/api/status", headers={"Cookie": old_cookie})[0], 401)
        self.assertEqual(self.request("POST", "/api/auth/logout", {})[0], 200)
        self.assertEqual(self.request("GET", "/api/status")[0], 401)
        status, _, result = self.request("GET", "/api/auth/status")
        self.assertEqual(status, 200)
        self.assertFalse(result["authenticated"])
        self.assertFalse(result["must_change_password"])
        self.assertEqual(self.request("POST", "/api/auth/login", {"username": "admin", "password": FAKE_PASSWORD})[0], 200)

    def test_csrf_origin_host_and_json_required(self):
        self.login_and_setup()
        for headers, code in [({"X-CSRF-Token": None}, "invalid_csrf"), ({"X-CSRF-Token": "wrong"}, "invalid_csrf"),
                              ({"Origin": None}, "invalid_origin"), ({"Origin": "http://evil.example"}, "invalid_origin"),
                              ({"Host": "evil.example"}, "invalid_host"), ({"Sec-Fetch-Site": "cross-site"}, "invalid_origin")]:
            status, _, result = self.request("POST", "/api/settings", {"remote_control": False}, headers=headers)
            self.assertEqual(status, 403)
            self.assertEqual(result["error"]["code"], code)
        self.assertTrue(self.auth.settings()["configured"]["remote_control"])
        self.assertEqual(self.request("POST", "/api/settings", {"remote_control": False}, headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("POST", "/api/settings", {"remote_control": False})[0], 200)
        self.assertFalse(self.auth.settings()["configured"]["remote_control"])

    def test_no_source_inspection_or_same_origin_auth_bypass(self):
        self.assertEqual(self.request("GET", "/app.js")[0], 200)
        self.assertEqual(self.request("GET", "/auth.py")[0], 404)
        self.assertEqual(self.request("GET", "/data/auth.sqlite3")[0], 404)
        for path in ["/api/status", "/api/workspace", "/api/presets", "/api/diagnostics", "/api/datasets", "/api/runs/run-0001/export?format=json"]:
            self.assertEqual(self.request("GET", path, headers={"Origin": self.origin})[0], 401)
        self.assertEqual(self.request("POST", "/api/runs", {})[0], 401)

    def test_cookie_tampering_and_secure_cookie_under_tls(self):
        self.login_and_setup()
        for cookie in ["ft_session=invalid", self.cookie + "; " + self.cookie, "ft_session=\"bad\\value\""]:
            self.assertEqual(self.request("GET", "/api/status", headers={"Cookie": cookie})[0], 401)
        # Header generation can be tested without creating a TLS listener/certificate.
        self.server.tls = True
        try:
            status, headers, _ = self.request("POST", "/api/auth/login", {"username": "admin", "password": FAKE_PASSWORD}, headers={"Origin": f"https://{self.host}"})
            self.assertEqual(status, 200)
            self.assertIn("Secure", headers["Set-Cookie"])
            self.assertIn("Strict-Transport-Security", headers)
        finally:
            self.server.tls = False

    def test_run_exports_safe_metadata_and_csv_formula_escape(self):
        self.login_and_setup()
        status, _, result = self.request("POST", "/api/runs", {"name": "=1+1", "max_steps": 10})
        self.assertEqual(status, 201)
        run_id = result["run"]["id"]
        status, headers, result = self.request("GET", f"/api/runs/{run_id}/export?format=json")
        self.assertEqual(status, 200)
        self.assertTrue(result["synthetic"])
        self.assertFalse(result["checkpoint_files"])
        self.assertNotIn("path", result)
        self.assertIn(f"{run_id}-synthetic.json", headers["Content-Disposition"])
        status, headers, body = self.request("GET", f"/api/runs/{run_id}/export?format=csv")
        self.assertEqual(status, 200)
        self.assertIn(b"'=1+1", body)
        self.assertIn(f"{run_id}-synthetic.csv", headers["Content-Disposition"])
        for query in ["format=exe", "format=json&format=csv", "path=/etc/passwd", "format=json&x=1"]:
            self.assertEqual(self.request("GET", f"/api/runs/{run_id}/export?{query}")[0], 400)

    def test_lan_flags_reject_before_any_listener(self):
        for kwargs in [{}, {"lan": True}, {"lan": True, "auth": False, "allow_insecure_http": True}, {"lan": True, "allow_insecure_http": True}]:
            with self.assertRaises(ValueError):
                DashboardServer(("0.0.0.0", 0), self.sim, self.static, **kwargs)
        for host in ["8.8.8.8", "169.254.1.1", "224.0.0.1", "192.0.2.25", "0.0.0.1", "evil.example"]:
            with self.assertRaises(ValueError):
                validate_bind(host, lan=True)


if __name__ == "__main__":
    unittest.main()
