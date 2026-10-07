"""Isolated UI fixture server. Never starts a worker, downloads, or probes a GPU.

Serves the actual static app and actual authentication/preparation routes, with
explicit synthetic run/model responses. All execution/download writes are denied.
Every invocation gets a disposable private directory, never the operator's data.
"""
from pathlib import Path
import argparse
import copy
import json
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from auth import AuthStore
from simulator import Simulator, DashboardError
from server import DashboardServer, DashboardHandler

FIXTURE_ID = "forge-workbench-v1"
PASSWORD = "ForgeFixtureSignIn2026!"  # Disposable test credential, never production.
MODELS = [dict(id="Qwen/Qwen2.5-0.5B-Instruct", name="Qwen2.5-0.5B-Instruct",
    kind="LLM", publisher="Qwen", family="qwen2", installed=True,
    training_candidate=True, revision="fixture-revision", task="text-generation",
    training_architecture="causal", architectures=["Qwen2ForCausalLM"],
    parameters=494000000, download_bytes=988000000, license="apache-2.0",
    private=False, gated=False, reasons=[], url="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct"),
    dict(id="fixture/unsupported-GGUF", name="Unsupported GGUF", kind="OTHER",
    publisher="fixture", family="Unknown", installed=False, training_candidate=False,
    revision="fixture-revision", task="unknown", training_architecture=None,
    architectures=[], parameters=None, download_bytes=None, license=None,
    private=False, gated=False, reasons=["This repository has no safetensors weights."],
    url="https://huggingface.co/")]


def fixture_snapshot(dataset_id):
    result = json.loads((ROOT / "docs/sample-snapshot.json").read_text())
    real = copy.deepcopy(next(run for run in result["runs"] if run["status"] == "running"))
    real.update(id="train-000000000001", name="Instruction adapter · Qwen 0.5B",
                simulated=False, kind="LLM", method="lora", status="running")
    real["config"].update(name=real["name"], model=MODELS[0]["id"], dataset=dataset_id,
                         kind="LLM", method="lora", batch_size=1, sequence_length=512)
    real["model_id"] = MODELS[0]["id"]
    real["logs"] = [dict(time="2026-10-07T06:00:00Z", level="INFO",
                        message="UI fixture: optimizer events are synthetic; no worker is connected.")]
    real["checkpoints"] = [dict(name="checkpoint-000010", step=10, virtual=False, size_mb=2.4)]
    real["allowed_actions"] = ["pause", "cancel"]
    real["evaluation"] = None
    runs = [real]
    actions = {"queued":["start", "cancel"], "pausing":[], "paused":["resume", "cancel"],
               "completed":[], "failed":["retry"], "canceled":["retry"]}
    for index, status in enumerate(actions, 2):
        run = copy.deepcopy(real)
        run.update(id=f"train-{index:012x}", name=f"Qwen adapter · {status}",
                   status=status, allowed_actions=actions[status])
        if status == "queued":
            run.update(step=0, progress=0, metrics=[], latest_metrics={}, logs=[], checkpoints=[])
        if status == "failed":
            run["error"] = {"code":"worker_failed", "message":"Synthetic fixture: worker interrupted. Retry preserves the snapshot."}
        if status == "completed":
            run["progress"] = 100
            run["evaluation"] = dict(baseline_eval_loss=3.8124, eval_loss=2.5632,
                generated_response="Synthetic response used only for UI verification.",
                reference="Synthetic reference answer.")
        runs.append(run)
    result["runs"] = runs + result["runs"]
    result.update(active_run_id=real["id"], mode="local_training_and_demo",
                  ui_fixture={"id":FIXTURE_ID, "label":"UI DEMO / SYNTHETIC FIXTURE / 성능·임상·실장비 검증 아님"})
    # Shape represents a measured-source response. Every value remains a UI fixture.
    result["gpu"].update(simulated=False, detected=True, name="UI fixture GPU · 12 GB",
                         observed_at="2026-10-07T06:00:00Z")
    result["training"] = dict(available=True, models=MODELS,
                             message="UI fixture only. Real GPU execution is denied.")
    return result


class FixtureHandler(DashboardHandler):
    def _headers(self, status, content_type, length, filename=None):
        self.server.ui_audit.append({"method":self.command,"path":self._path(),"status":status,
            "at":datetime.now(timezone.utc).isoformat()})
        return super()._headers(status, content_type, length, filename)

    def _snapshot(self):
        if self.server.ui_mode == "stale":
            raise DashboardError("fixture_offline", "UI fixture: API connection unavailable.", 503)
        result = copy.deepcopy(self.server.ui_snapshot)
        if self.server.ui_mode == "empty":
            result.update(runs=[], active_run_id=None)
        result["settings"] = self._settings()
        return result

    def do_GET(self):
        try:
            self._guard()
            path = self._path()
            proof_files = {"/__fixture__/typography": "proof.html", "/__fixture__/typography-proof.js": "proof.js"}
            if path in proof_files:
                body = (ROOT / "docs/ui-redesign/typography" / proof_files[path]).read_bytes()
                kind = "text/html" if path.endswith("typography") else "text/javascript"
                self._headers(200, kind + "; charset=utf-8", len(body))
                if self.command != "HEAD":
                    self.wfile.write(body)
                return
            if path in {"/", "/index.html", "/__fixture__/empty", "/__fixture__/stale"}:
                self.server.ui_mode = path.rsplit("/", 1)[-1] if path.startswith("/__fixture__/") else "normal"
                source = (self.server.static_dir / "index.html").read_text()
                banner = '<div class="fixture-watermark" role="note" style="padding:5px 12px;background:#fff3df;color:#492c11;text-align:center;border-bottom:1px solid #b08042">UI DEMO / SYNTHETIC FIXTURE / 성능·임상·실장비 검증 아님</div>'
                body = source.replace("<body>", "<body>" + banner).encode()
                self._headers(200, "text/html; charset=utf-8", len(body))
                if self.command != "HEAD":
                    self.wfile.write(body)
                return
            if path in {"/api/training", "/api/diagnostics"} or path.startswith("/api/huggingface/"):
                self._authorize()
                if path == "/api/training":
                    return self._json(200, self.server.ui_snapshot["training"])
                if path == "/api/diagnostics":
                    return self._json(200, {"python":{"version":"UI fixture"}, "os":{"name":"Isolated UI fixture"},
                        "disk":{"available":False}, "gpu":{"detected":False,"message":"No live probe"}, "warnings":[]})
                if path.endswith("/account"):
                    return self._json(200, {"connected":False, "username":None})
                if path.endswith("/download"):
                    return self._json(200, {"status":"idle"})
                if path.endswith("/models"):
                    if self._query({"search","author","kind","family","sort","cursor","text_task"}).get("search") == "unreachable":
                        raise DashboardError("hf_unavailable", "Hugging Face is unavailable. Retry later.", 503)
                    return self._json(200, {"models":MODELS, "next_cursor":None})
                if path.endswith("/model"):
                    key = self._query({"id"}).get("id")
                    return self._json(200, next((m for m in MODELS if m["id"] == key), MODELS[1]))
                if path.endswith("/avatar"):
                    return self._json(404, {"error":{"code":"fixture_avatar", "message":"No external avatar requests"}})
            return super().do_GET()
        except DashboardError as error:
            self._error(error)

    def _run_export(self, run_id):
        run = next((r for r in self.server.ui_snapshot["runs"] if r["id"] == run_id), None)
        if run is None:
            raise DashboardError("run_not_found", "Unknown fixture run.", 404)
        if self._query({"format"}).get("format", "json") == "json":
            payload = {**run, "mode":"real_training" if run["simulated"] is False else "demo",
                "synthetic":run["simulated"],"ui_fixture":True,"metrics_provenance":"synthetic_ui_fixture"}
            return self._download(json.dumps(payload, ensure_ascii=False).encode(), "forge-ui-fixture.json", "application/json")
        return self._download(b"source,ui_fixture\nsynthetic_ui_fixture,true\n", "forge-ui-fixture.csv", "text/csv")

    def do_POST(self):
        path = self._path()
        if path.startswith(("/api/runs", "/api/training", "/api/huggingface", "/api/demo")):
            try:
                self._guard(post=True)
                self._authorize(mutation=True, remote_operation="remote_view" if path.endswith("preflight") else "remote_control")
                self._body()
                self.server.denied_actions.append(path)
                raise DashboardError("ui_fixture_denied", "UI fixture: execution, control and downloads are disabled.", 409)
            except DashboardError as error:
                return self._error(error)
        return super().do_POST()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--audit-file", type=Path)
    parser.add_argument("--static-dir", type=Path, default=ROOT / "static")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="forge-ui-fixture-") as directory:
        root = Path(directory)
        auth = AuthStore(root / "auth.sqlite3", initial_password="FixtureInitialPassword2026!")
        token, session = auth.login("admin", "FixtureInitialPassword2026!", "127.0.0.1")
        auth.change_password(token, "127.0.0.1", "FixtureInitialPassword2026!", PASSWORD, session["csrf_token"])
        sim = Simulator(root / "state.sqlite3")
        server = DashboardServer(("127.0.0.1", args.port), sim, args.static_dir, auth=auth)
        server.RequestHandlerClass = FixtureHandler
        text = "\n".join(json.dumps({"instruction":f"Synthetic prompt {i}", "output":f"Synthetic target {i}"}) for i in range(12))
        with patch("workspace.uuid.uuid4", return_value=uuid.UUID("67fdd205-2ff0-0000-0000-000000000000")):
            dataset = server.workspace.import_dataset({"name":"Synthetic instruction set", "kind":"LLM", "text":text, "synthetic":True})["dataset"]
        server.workspace.split_dataset(dataset["id"], {"seed":42, "val_ratio":0.2})
        server.ui_snapshot = fixture_snapshot(dataset["id"])
        server.denied_actions = []
        server.ui_audit = []
        server.ui_mode = "normal"
        print(f"UI fixture: http://127.0.0.1:{server.server_port} · {FIXTURE_ID}", flush=True)
        print(f"Disposable sign-in: admin / {PASSWORD}", flush=True)
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
            auth.close()
            sim.close()
            if args.audit_file:
                args.audit_file.write_text(json.dumps({"fixture_id":FIXTURE_ID,"network_policy":"loopback only; Hub canned; no training/download manager", "denied_actions":server.denied_actions,"requests":server.ui_audit}, indent=2)+"\n")
            print(f"Denied execution/control/download requests: {len(server.denied_actions)}", flush=True)


if __name__ == "__main__":
    main()
