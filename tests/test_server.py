import http.client
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest

from server import DashboardServer, MAX_REQUEST_BYTES, MAX_DATASET_REQUEST_BYTES
from simulator import Simulator


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.static = Path(self.tmp.name) / "static"
        self.static.mkdir()
        (self.static / "index.html").write_text("<!doctype html><title>Demo</title>")
        (self.static / "app.js").write_text("console.log('demo');")
        (self.static / ".secret.js").write_text("secret")
        self.sim = Simulator(Path(self.tmp.name) / "state.sqlite3", seed_demo=False)
        self.server = DashboardServer(("127.0.0.1", 0), self.sim, self.static, auth=False)
        self.port = self.server.server_port
        self.host = f"127.0.0.1:{self.port}"
        self.origin = f"http://{self.host}"
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.sim.close()
        self.tmp.cleanup()

    def request(self, method, path, payload=None, headers=None, raw=False):
        client = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        supplied = {"Host": self.host}
        if method == "POST":
            supplied.update({"Origin": self.origin, "Content-Type": "application/json"})
        supplied.update(headers or {})
        body = payload if raw else json.dumps(payload or {}) if method == "POST" else None
        client.request(method, path, body=body, headers=supplied)
        response = client.getresponse()
        data = response.read()
        result = (response.status, dict(response.getheaders()), data)
        client.close()
        return result

    def json_request(self, *args, **kwargs):
        status, headers, data = self.request(*args, **kwargs)
        return status, headers, json.loads(data)

    def test_status_and_security_headers(self):
        status, headers, payload = self.json_request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(payload["mode"], "demo")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_static_and_head(self):
        status, headers, data = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Demo", data)
        self.assertIn("text/html", headers["Content-Type"])
        status, headers, data = self.request("HEAD", "/app.js")
        self.assertEqual(status, 200)
        self.assertEqual(data, b"")
        self.assertGreater(int(headers["Content-Length"]), 0)

    def test_bundled_fonts_keep_static_security_boundary(self):
        source_root = Path(__file__).resolve().parent.parent / 'static'
        for source in (source_root / 'fonts').rglob('*.woff2'):
            relative = source.relative_to(source_root)
            target = self.static / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            status, headers, body = self.request('GET', '/' + relative.as_posix())
            self.assertEqual(status, 200)
            self.assertEqual(body, source.read_bytes())
            self.assertEqual(body[:4], b'wOF2')
            self.assertIn('font/woff2', headers['Content-Type'])
            self.assertIn("font-src 'self';", headers['Content-Security-Policy'])
            self.assertNotIn("font-src *", headers['Content-Security-Policy'])
        # A .woff2 suffix must never make an outside account/data file public.
        private = Path(self.tmp.name) / 'private.woff2'
        private.write_bytes(b'private test data')
        (self.static / 'fonts' / 'outside.woff2').symlink_to(private)
        self.assertEqual(self.request('GET', '/fonts/outside.woff2')[0], 404)
        self.assertIn(self.request('GET', '/fonts/../../private.woff2')[0], {400, 404})

    def test_create_get_action_retry_lifecycle(self):
        status, _, body = self.json_request("POST", "/api/runs", {"name": "HTTP demo", "max_steps": 10})
        self.assertEqual(status, 201)
        run = body["run"]
        self.assertEqual(run["status"], "queued")
        self.assertEqual(body["snapshot"]["summary"]["queued"], 1)
        status, _, body = self.json_request("GET", f"/api/runs/{run['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(body["run"]["name"], "HTTP demo")
        for action, expected in [("start", "running"), ("pause", "paused"), ("resume", "running"), ("cancel", "canceled")]:
            status, _, body = self.json_request("POST", f"/api/runs/{run['id']}/{action}", {})
            self.assertEqual(status, 200)
            self.assertEqual(body["run"]["status"], expected)
        status, _, body = self.json_request("POST", f"/api/runs/{run['id']}/retry", {})
        self.assertEqual(status, 201)
        self.assertEqual(body["run"]["retry_of"], run["id"])

    def test_reset_endpoint(self):
        status, _, body = self.json_request("POST", "/api/demo/reset", {})
        self.assertEqual(status, 200)
        self.assertEqual(len(body["snapshot"]["runs"]), 4)

    def test_invalid_host(self):
        for host in ["evil.example", f"evil.example:{self.port}", "127.0.0.1:0", "127.0.0.1", f"127.0.0.1:{self.port+1}", f"user@127.0.0.1:{self.port}", f"127.0.0.1:{self.port}/", f"local\thost:{self.port}"]:
            with self.subTest(host=host):
                status, _, body = self.json_request("GET", "/api/status", headers={"Host": host})
                self.assertEqual(status, 403)
                self.assertEqual(body["error"]["code"], "invalid_host")

    def test_localhost_host_accepted(self):
        status, _, _ = self.json_request("GET", "/api/status", headers={"Host": f"localhost:{self.port}"})
        self.assertEqual(status, 200)
        status, _, _ = self.json_request("POST", "/api/runs", {}, headers={"Host": f"localhost:{self.port}", "Origin": f"http://localhost:{self.port}"})
        self.assertEqual(status, 201)

    def test_cross_origin_rejected(self):
        origins = ["null", "https://evil.example", f"http://evil.example:{self.port}", "http://127.0.0.1:1", f"http://localhost:{self.port}", self.origin + "/", self.origin + "?x=1", self.origin + "#x", self.origin.replace("http:", "https:")]
        for origin in origins:
            with self.subTest(origin=origin):
                status, _, body = self.json_request("POST", "/api/runs", {}, headers={"Origin": origin})
                self.assertEqual(status, 403)
                self.assertEqual(body["error"]["code"], "invalid_origin")
        for site in ["cross-site", "same-site"]:
            status, _, _ = self.json_request("POST", "/api/runs", {}, headers={"Sec-Fetch-Site": site})
            self.assertEqual(status, 403)
        self.assertEqual(self.sim.snapshot()["runs"], [])

    def test_nonbrowser_originless_json_post(self):
        client = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        client.request("POST", "/api/runs", body="{}", headers={"Content-Type": "application/json"})
        response = client.getresponse()
        response.read()
        self.assertEqual(response.status, 201)
        client.close()

    def test_media_type_size_and_json_validation(self):
        status, _, _ = self.json_request("POST", "/api/runs", {}, headers={"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        status, _, _ = self.json_request("POST", "/api/runs", "x"*(MAX_REQUEST_BYTES+1), raw=True)
        self.assertEqual(status, 413)
        for payload in ["{", "[]", "null", '{"seed":NaN}', '{"seed":Infinity}', '{"name":"a","name":"b"}', b"\xff"]:
            with self.subTest(payload=payload):
                status, _, body = self.json_request("POST", "/api/runs", payload, raw=True)
                self.assertEqual(status, 400)
                self.assertEqual(body["error"]["code"], "invalid_json")

    def test_bad_config_and_action_payload(self):
        for config in [{"command": "ls"}, {"batch_size": 0}, {"learning_rate": 10**400}]:
            status, _, body = self.json_request("POST", "/api/runs", config)
            self.assertEqual(status, 400)
            self.assertEqual(body["error"]["code"], "invalid_config")
        run = self.sim.queue({})
        status, _, _ = self.json_request("POST", f"/api/runs/{run['id']}/start", {"unexpected": True})
        self.assertEqual(status, 400)
        self.assertEqual(self.sim.get_run(run["id"])["status"], "queued")

    def test_paths_and_routes(self):
        for path in ["/../server.py", "/%2e%2e/server.py", "/a%2fb", "/a%5cb", "/.secret.js", "/%00app.js", "//evil.example/"]:
            with self.subTest(path=path):
                status, _, _ = self.json_request("GET", path)
                self.assertEqual(status, 400)
        for path in ["/server.py", "/missing.html", "/api/missing", "/api/runs/run-9999", "/api/runs/run-0001/start"]:
            status, _, _ = self.json_request("GET", path)
            self.assertEqual(status, 404)
        status, _, _ = self.json_request("POST", "/%FF", {})
        self.assertEqual(status, 400)
        status, _, _ = self.json_request("POST", "/api/runs/run-0001/execute", {})
        self.assertEqual(status, 404)

    def test_static_symlink_cannot_escape(self):
        outside = Path(self.tmp.name) / "outside.js"
        outside.write_text("secret")
        (self.static / "escape.js").symlink_to(outside)
        status, _, _ = self.json_request("GET", "/escape.js")
        self.assertEqual(status, 404)

    def test_unsupported_methods(self):
        for method in ["PUT", "PATCH", "DELETE", "OPTIONS"]:
            status, _, body = self.json_request(method, "/api/status")
            self.assertEqual(status, 405)
            self.assertEqual(body["error"]["code"], "method_not_allowed")

    def raw_request(self, headers):
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=3)
        sock.sendall(headers.encode("ascii"))
        data = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
        sock.close()
        return int(data.split(b" ", 2)[1]), data

    def test_duplicate_headers_and_chunked_request(self):
        for extra, expected in [(f"Host: {self.host}\r\n", 403), ("Content-Length: 2\r\n", 411), (f"Origin: {self.origin}\r\n", 403), ("Transfer-Encoding: chunked\r\n", 400)]:
            request = f"POST /api/runs HTTP/1.1\r\nHost: {self.host}\r\nOrigin: {self.origin}\r\nContent-Type: application/json\r\nContent-Length: 2\r\n{extra}Connection: close\r\n\r\n{{}}"
            status, _ = self.raw_request(request)
            self.assertEqual(status, expected)

    def test_missing_or_huge_content_length(self):
        for length_header, expected in [("", 411), ("Content-Length: -1\r\n", 411), ("Content-Length: " + "9"*5000 + "\r\n", 413)]:
            request = f"POST /api/runs HTTP/1.1\r\nHost: {self.host}\r\nOrigin: {self.origin}\r\nContent-Type: application/json\r\n{length_header}Connection: close\r\n\r\n"
            status, _ = self.raw_request(request)
            self.assertEqual(status, expected)

    def test_bind_rejects_public_network(self):
        with self.assertRaises(ValueError):
            DashboardServer(("0.0.0.0", 0), self.sim, self.static)

    def test_workspace_routes_and_dataset_roundtrip(self):
        for path in ["/api/workspace", "/api/presets", "/api/diagnostics"]:
            status, _, body = self.json_request("GET", path)
            self.assertEqual(status, 200)
            self.assertFalse(body.get("real_training", body.get("capabilities", {}).get("real_training")))
        lines = [json.dumps({"instruction": f"Synthetic question {i}", "output": f"Synthetic answer {i}"}) for i in range(5)]
        payload = {"name": "Synthetic HTTP fixture", "kind": "LLM", "text": "\n".join(lines), "synthetic": True}
        status, _, body = self.json_request("POST", "/api/datasets/validate", payload)
        self.assertEqual(status, 200)
        self.assertTrue(body["valid"])
        self.assertEqual(body["count"], 5)
        status, _, body = self.json_request("POST", "/api/datasets", payload)
        self.assertEqual(status, 201)
        dataset_id = body["dataset"]["id"]
        status, _, body = self.json_request("GET", f"/api/datasets/{dataset_id}")
        self.assertEqual(status, 200)
        self.assertEqual(body["dataset"]["count"], 5)
        self.assertEqual(self.json_request("GET", "/api/datasets")[2]["datasets"][0]["id"], dataset_id)
        status, _, body = self.json_request("POST", f"/api/datasets/{dataset_id}/split", {"seed": 42, "val_ratio": 0.2})
        self.assertEqual(status, 200)
        self.assertEqual(body["train_count"], 4)
        self.assertEqual(body["validation_count"], 1)
        status, headers, data = self.request("GET", f"/api/datasets/{dataset_id}/export?split=train")
        self.assertEqual(status, 200)
        self.assertEqual(len(data.decode().splitlines()), 4)
        self.assertIn(dataset_id, headers["Content-Disposition"])
        self.assertEqual(self.json_request("GET", f"/api/datasets/{dataset_id}/export?split=bad")[0], 400)
        self.assertEqual(self.json_request("GET", f"/api/datasets/{dataset_id}/export?path=/etc/passwd")[0], 400)
        status, _, body = self.json_request("POST", "/api/config/dry-run", {"config": {"dataset": dataset_id}})
        self.assertEqual(status, 200)
        self.assertFalse(body["can_train"])
        self.assertEqual(body["dataset"]["id"], dataset_id)

    def test_dataset_only_larger_body_limit(self):
        # More than16 KiB is accepted by dataset routes only; workspace validates fields separately.
        text = "\n".join(json.dumps({"instruction": f"Synthetic row {i}", "output": "x" * 100}) for i in range(140))
        payload = {"kind": "LLM", "name": "Synthetic medium fixture", "synthetic": True, "text": text}
        self.assertGreater(len(json.dumps(payload).encode()), MAX_REQUEST_BYTES)
        for path in ["/api/datasets/validate", "/api/datasets/import", "/api/datasets"]:
            status, _, body = self.json_request("POST", path, payload)
            self.assertEqual(status, 200 if path.endswith("validate") else 201)
            self.assertTrue(body.get("valid", body.get("validation", {}).get("valid")))
        self.assertEqual(self.json_request("POST", "/api/runs", payload)[0], 413)
        self.assertEqual(self.json_request("POST", "/api/config/dry-run", payload)[0], 413)
        self.assertEqual(self.json_request("POST", "/api/datasets/validate", "x" * (MAX_DATASET_REQUEST_BYTES + 1), raw=True)[0], 413)

    def test_worker_advances_and_stops(self):
        run = self.sim.queue({})
        self.server.start_worker()
        import time
        deadline = time.monotonic() + 3
        while self.sim.get_run(run["id"])["step"] == 0 and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertGreater(self.sim.get_run(run["id"])["step"], 0)
        self.assertTrue(self.sim.worker_alive)
        self.server.server_close()
        self.assertFalse(self.sim.worker_alive)


if __name__ == "__main__":
    unittest.main()
