"""Persistent, deterministic fine-tuning *simulation*. No training or GPU probing.

The simulator advances one synthetic step per second while the service is alive.
All model/dataset names are labels; they are never opened, downloaded or executed.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Callable

MODELS = [
    {"id": "Qwen/Qwen2.5-3B-Instruct", "name": "Qwen 2.5 · 3B", "kind": "LLM"},
    {"id": "TinyLlama/TinyLlama-1.1B-Chat-v1.0", "name": "TinyLlama · 1.1B", "kind": "LLM"},
    {"id": "Qwen/Qwen2-VL-2B-Instruct", "name": "Qwen 2 VL · 2B", "kind": "VLM"},
]
DATASETS = [
    {"id": "instruction-demo", "name": "Instruction demo", "kind": "LLM", "samples": 1200},
    {"id": "vision-demo", "name": "Image-caption demo", "kind": "VLM", "samples": 480},
]
TERMINAL = {"completed", "failed", "canceled"}
STATUSES = ("running", "queued", "paused", "completed", "failed", "canceled")
MAX_RUNS = 50
MAX_METRICS = 240
MAX_LOGS = 200


class DashboardError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, details: Any = None):
        super().__init__(message)
        self.code, self.message, self.status, self.details = code, message, status, details

    def as_dict(self):
        result = {"code": self.code, "message": self.message}
        if self.details is not None:
            result["details"] = self.details
        return {"error": result}


def timestamp(seconds: float) -> str:
    return dt.datetime.fromtimestamp(seconds, dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _text(value: Any, field: str, default: str, limit: int) -> str:
    if value is None:
        value = default
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise DashboardError("invalid_config", f"{field} must be a nonempty text label of at most {limit} characters.", details={"field": field})
    return value.strip()


def _number(value: Any, field: str, default: Any, low: float, high: float, integer: bool = False):
    if value is None:
        value = default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DashboardError("invalid_config", f"{field} must be a number.", details={"field": field})
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or not low <= value <= high or (integer and int(value) != value):
        raise DashboardError("invalid_config", f"{field} must be {'an integer ' if integer else ''}between {low:g} and {high:g}.", details={"field": field})
    return int(value) if integer else float(value)


def validate_config(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise DashboardError("invalid_config", "Configuration must be a JSON object.")
    aliases = {"model_type": "kind", "model_id": "model", "dataset_id": "dataset", "max_seq_length": "sequence_length"}
    allowed = {"name", "kind", "model", "dataset", "method", "learning_rate", "epochs", "batch_size", "gradient_accumulation", "lora_rank", "max_steps", "sequence_length", "seed", "failure_mode"}
    normalized = dict(raw)
    for alias, target in aliases.items():
        if alias in normalized:
            if target in normalized and str(normalized[target]).lower() != str(normalized[alias]).lower():
                raise DashboardError("invalid_config", f"Conflicting {alias} and {target} values.")
            normalized[target] = normalized.pop(alias)
    unknown = sorted(set(normalized) - allowed)
    if unknown:
        raise DashboardError("invalid_config", "Unknown configuration fields.", details={"fields": unknown})
    kind = _text(normalized.get("kind"), "kind", "LLM", 3).upper()
    if kind not in {"LLM", "VLM"}:
        raise DashboardError("invalid_config", "kind must be LLM or VLM.", details={"field": "kind"})
    method = _text(normalized.get("method"), "method", "qlora", 10).lower()
    if method not in {"qlora", "lora"}:
        raise DashboardError("invalid_config", "method must be qlora or lora.", details={"field": "method"})
    failure = _text(normalized.get("failure_mode"), "failure_mode", "none", 10).lower()
    if failure not in {"none", "oom"}:
        raise DashboardError("invalid_config", "failure_mode must be none or oom.", details={"field": "failure_mode"})
    model = MODELS[2]["id"] if kind == "VLM" else MODELS[0]["id"]
    config = {
        "name": _text(normalized.get("name"), "name", f"{kind} adapter experiment", 80),
        "kind": kind,
        "model": _text(normalized.get("model"), "model", model, 160),
        "dataset": _text(normalized.get("dataset"), "dataset", "vision-demo" if kind == "VLM" else "instruction-demo", 160),
        "method": method,
        "learning_rate": _number(normalized.get("learning_rate"), "learning_rate", 0.0002, 0.0000001, 0.1),
        "epochs": _number(normalized.get("epochs"), "epochs", 3, 1, 100, True),
        "batch_size": _number(normalized.get("batch_size"), "batch_size", 1, 1, 64, True),
        "gradient_accumulation": _number(normalized.get("gradient_accumulation"), "gradient_accumulation", 8, 1, 256, True),
        "lora_rank": _number(normalized.get("lora_rank"), "lora_rank", 16, 1, 256, True),
        "max_steps": _number(normalized.get("max_steps"), "max_steps", 120, 10, 2000, True),
        "sequence_length": _number(normalized.get("sequence_length"), "sequence_length", 1024, 128, 32768, True),
        "seed": _number(normalized.get("seed"), "seed", 42, 0, 2147483647, True),
        "failure_mode": failure,
    }
    return config


class Simulator:
    """Thread-safe state machine with atomic SQLite persistence.

    A paused run reserves the single simulated GPU. Service downtime does not
    count as synthetic training time; a restart preserves the exact run state.
    """
    def __init__(self, db_path: str | Path, clock: Callable[[], float] = time.time, seed_demo: bool = True):
        self.clock = clock
        self.lock = threading.RLock()
        self.created_at = clock()
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            path = Path(self.db_path)
            path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS dashboard_state (singleton INTEGER PRIMARY KEY CHECK(singleton=1), payload TEXT NOT NULL)")
        stored = self.db.execute("SELECT payload FROM dashboard_state WHERE singleton=1").fetchone()
        if stored:
            self.state = json.loads(stored[0])
            self._validate_state()
        else:
            self.state = {"version": 1, "next_id": 1, "runs": []}
            if seed_demo:
                self._seed(clock())
            self._save()
        self.last_tick = clock()
        self.worker_alive = False

    def _validate_state(self):
        state = self.state
        if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("runs"), list):
            raise ValueError("Invalid demo state; refusing to reset stored data automatically.")
        running = sum(r.get("status") == "running" for r in state["runs"])
        active = sum(r.get("status") in {"running", "paused"} for r in state["runs"])
        if running > 1 or active > 1 or any(r.get("status") not in STATUSES for r in state["runs"]):
            raise ValueError("Invalid persisted state: single simulated GPU invariant violated.")

    def _save(self):
        encoded = json.dumps(self.state, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        with self.db:
            self.db.execute("INSERT INTO dashboard_state(singleton,payload) VALUES(1,?) ON CONFLICT(singleton) DO UPDATE SET payload=excluded.payload", (encoded,))

    def close(self):
        with self.lock:
            self._save()
            self.db.close()

    def _log(self, run, now, message, level="info"):
        run["logs"].append({"time": timestamp(now), "level": level, "message": message})
        run["logs"] = run["logs"][-MAX_LOGS:]

    def _new_run(self, config, now, retry_of=None):
        run_id = f"run-{self.state['next_id']:04d}"
        self.state["next_id"] += 1
        run = {
            "id": run_id, "name": config["name"], "kind": config["kind"], "model_type": config["kind"].lower(),
            "model_id": config["model"], "model": config["model"], "method": config["method"], "status": "queued",
            "config": config, "created_at": timestamp(now), "updated_at": timestamp(now), "started_at": None,
            "finished_at": None, "step": 0, "current_step": 0, "total_steps": config["max_steps"],
            "elapsed_seconds": 0, "metrics": [], "logs": [], "checkpoints": [], "error": None, "retry_of": retry_of,
        }
        self._log(run, now, "Demo run queued. Model and dataset labels will not be downloaded or opened.")
        if retry_of:
            self._log(run, now, f"Fresh retry of {retry_of}; previous history is preserved.")
        self.state["runs"].append(run)
        return run

    def _start(self, run, now):
        run["status"] = "running"
        run["started_at"] = run["started_at"] or timestamp(now)
        run["updated_at"] = timestamp(now)
        self._log(run, now, "Synthetic training started on the simulated 12 GB GPU. This demo engine does not probe or connect real hardware.")
        if not run["metrics"]:
            run["metrics"].append(self._metric(run, 0))

    def _metric(self, run, step):
        cfg = run["config"]
        # Stable seed-derived phase rather than randomized or hardware metrics.
        phase = int(hashlib.sha256(f"{cfg['seed']}:{cfg['model']}:{cfg['dataset']}".encode()).hexdigest()[:6], 16) / 0xFFFFFF * math.pi
        fraction = step / run["total_steps"]
        wobble = math.sin(step * 0.37 + phase) * 0.045
        loss = max(0.12, 2.7 * math.exp(-2.4 * fraction) + 0.22 + wobble)
        used = min(11.8, (7.4 if cfg["kind"] == "VLM" else 5.0) + cfg["batch_size"] * 0.3 + cfg["lora_rank"] * 0.02 + math.sin(step * 0.11) * 0.15)
        return {
            "step": step, "elapsed_seconds": step, "loss": round(loss, 4),
            "eval_loss": round(loss + 0.12 + math.sin(step * 0.17) * 0.02, 4),
            "learning_rate": round(cfg["learning_rate"] * (0.15 + 0.85 * (1 - fraction)), 8),
            "tokens_per_second": round((52 if cfg["kind"] == "VLM" else 175) + math.sin(step * 0.2) * 8, 1),
            "vram_used_gb": round(used, 2),
        }

    def _advance(self, run, now):
        run["step"] += 1
        run["current_step"] = run["step"]
        run["elapsed_seconds"] += 1
        run["updated_at"] = timestamp(now)
        metric = self._metric(run, run["step"])
        run["metrics"].append(metric)
        run["metrics"] = run["metrics"][-MAX_METRICS:]
        if run["config"]["failure_mode"] == "oom" and run["step"] >= min(24, max(3, run["total_steps"] // 4)):
            run["status"] = "failed"
            run["finished_at"] = timestamp(now)
            run["error"] = "Simulated CUDA out of memory. This is an injected demo failure, not a real hardware error."
            self._log(run, now, run["error"], "error")
            return
        interval = max(1, run["total_steps"] // 3)
        if run["step"] % interval == 0 or run["step"] == run["total_steps"]:
            if not run["checkpoints"] or run["checkpoints"][-1]["step"] != run["step"]:
                name = f"adapter-step-{run['step']:04d}"
                run["checkpoints"].append({"id": f"{run['id']}-{run['step']}", "name": name, "label": name, "step": run["step"], "size_mb": round(run["config"]["lora_rank"] * 2.4, 1), "virtual": True, "created_at": timestamp(now)})
                self._log(run, now, f"Virtual checkpoint recorded at step {run['step']}; no adapter file was written.")
        if run["step"] % 20 == 0:
            self._log(run, now, f"Synthetic step {run['step']}/{run['total_steps']} · loss {metric['loss']:.4f}")
        if run["step"] >= run["total_steps"]:
            run["status"] = "completed"
            run["finished_at"] = timestamp(now)
            self._log(run, now, "Demo simulation completed. Metrics and checkpoints are illustrative only.")

    def _seed(self, now):
        completed = self._new_run(validate_config({"name": "Support assistant · baseline", "max_steps": 90}), now - 720)
        self._start(completed, now - 720)
        for step in range(90):
            self._advance(completed, now - 719 + step)
        failed = self._new_run(validate_config({"name": "Vision adapter · memory test", "kind": "VLM", "failure_mode": "oom", "max_steps": 100, "batch_size": 4}), now - 420)
        self._start(failed, now - 420)
        for step in range(24):
            self._advance(failed, now - 419 + step)
        active = self._new_run(validate_config({"name": "Research assistant · QLoRA", "max_steps": 180}), now - 35)
        self._start(active, now - 35)
        for step in range(35):
            self._advance(active, now - 34 + step)
        self._new_run(validate_config({"name": "Product captions · vision adapter", "kind": "VLM", "max_steps": 120}), now - 10)

    def tick(self, now: float | None = None):
        with self.lock:
            now = self.clock() if now is None else now
            if now < self.last_tick:
                self.last_tick = now
                return
            seconds = int(now - self.last_tick)
            if seconds == 0:
                return
            for offset in range(1, seconds + 1):
                at = self.last_tick + offset
                active = next((r for r in self.state["runs"] if r["status"] in {"running", "paused"}), None)
                if active and active["status"] == "paused":
                    # A paused run keeps its place and reserves the simulated GPU.
                    break
                if active is None:
                    active = next((r for r in self.state["runs"] if r["status"] == "queued"), None)
                    if active:
                        self._start(active, at)
                    else:
                        break
                if active:
                    self._advance(active, at)
            self.last_tick += seconds
            self._save()

    def _find(self, run_id):
        run = next((r for r in self.state["runs"] if r["id"] == run_id), None)
        if run is None:
            raise DashboardError("not_found", "Run does not exist.", 404)
        return run

    def _render_run(self, run):
        result = copy.deepcopy(run)
        result["progress"] = round(run["step"] / run["total_steps"] * 100, 1)
        result["latest_metrics"] = copy.deepcopy(run["metrics"][-1]) if run["metrics"] else None
        result["eta_seconds"] = run["total_steps"] - run["step"] if run["status"] == "running" else None
        result["allowed_actions"] = {
            "queued": ["start", "cancel"], "running": ["pause", "cancel"], "paused": ["resume", "cancel"],
            "failed": ["retry"], "canceled": ["retry"], "completed": [],
        }[run["status"]]
        result["simulated"] = True
        return result

    def get_run(self, run_id):
        with self.lock:
            return self._render_run(self._find(run_id))

    def queue(self, raw_config):
        config = validate_config(raw_config)
        with self.lock:
            if len(self.state["runs"]) >= MAX_RUNS:
                raise DashboardError("run_limit", "Demo has reached 50 runs. Reset demo data before creating more.", 409)
            run = self._new_run(config, self.clock())
            self._save()
            return self._render_run(run)

    def action(self, run_id, action):
        with self.lock:
            run = self._find(run_id)
            if action not in {"start", "pause", "resume", "cancel", "retry"}:
                raise DashboardError("not_found", "Unknown run action.", 404)
            now = self.clock()
            state = run["status"]
            other = next((r for r in self.state["runs"] if r["id"] != run_id and r["status"] in {"running", "paused"}), None)
            if action == "start":
                if state != "queued":
                    raise DashboardError("invalid_transition", "Only a queued run can be started.", 409)
                if other:
                    raise DashboardError("gpu_busy", "The single simulated GPU is reserved by another running or paused run.", 409)
                self._start(run, now)
            elif action == "pause":
                if state != "running":
                    raise DashboardError("invalid_transition", "Only a running demo run can be paused.", 409)
                run["status"] = "paused"
                self._log(run, now, "Demo simulation paused. No real training process was stopped.")
            elif action == "resume":
                if state != "paused":
                    raise DashboardError("invalid_transition", "Only a paused run can be resumed.", 409)
                if other:
                    raise DashboardError("gpu_busy", "The single simulated GPU is reserved by another run.", 409)
                run["status"] = "running"
                self._log(run, now, "Demo simulation resumed.")
            elif action == "cancel":
                if state in TERMINAL:
                    raise DashboardError("invalid_transition", "A terminal run cannot be canceled.", 409)
                run["status"] = "canceled"
                run["finished_at"] = timestamp(now)
                self._log(run, now, "Demo run canceled; synthetic steps have stopped. Existing history is preserved.", "warning")
            elif action == "retry":
                if state not in {"failed", "canceled"}:
                    raise DashboardError("invalid_transition", "Only a failed or canceled run can be retried.", 409)
                if len(self.state["runs"]) >= MAX_RUNS:
                    raise DashboardError("run_limit", "Demo has reached 50 runs. Reset demo data before creating more.", 409)
                config = copy.deepcopy(run["config"])
                config["name"] = (run["name"][:72] + " · retry")[:80]
                # Keep failure injection explicit rather than silently changing configuration.
                run = self._new_run(config, now, retry_of=run_id)
            run["updated_at"] = timestamp(now)
            # Avoid attributing time before a control action to the new status.
            self.last_tick = now
            self._save()
            return self._render_run(run)

    def reset(self):
        with self.lock:
            self.state = {"version": 1, "next_id": 1, "runs": []}
            now = self.clock()
            self._seed(now)
            self.last_tick = now
            self._save()
            return self.snapshot()

    def snapshot(self):
        with self.lock:
            now = self.clock()
            active = next((r for r in self.state["runs"] if r["status"] == "running"), None)
            paused = next((r for r in self.state["runs"] if r["status"] == "paused"), None)
            resident = active or paused
            used = resident["metrics"][-1]["vram_used_gb"] if resident and resident["metrics"] else 0.4
            utilization = 92 if active else 0
            temp = 62 + math.sin(active["step"] * 0.04) * 3 if active else 36
            gpu = {
                "name": "Simulated 12 GB GPU", "detected": False, "simulated": True,
                "total_gb": 12, "used_gb": round(used, 2), "utilization": utilization, "temp_c": round(temp, 1),
                "vram_total_gb": 12, "vram_used_gb": round(used, 2), "utilization_percent": utilization, "temperature_c": round(temp, 1),
                "assumption": "Illustrative 12 GB VRAM budget. No GPU hardware is detected or measured.",
            }
            return {
                "mode": "demo", "demo": True, "health": {"status": "ok", "worker_alive": self.worker_alive, "uptime_seconds": max(0, int(now - self.created_at))},
                "gpu": gpu, "runs": [self._render_run(r) for r in reversed(self.state["runs"])],
                "active_run_id": active["id"] if active else None, "reserved_run_id": resident["id"] if resident else None,
                "summary": {status: sum(r["status"] == status for r in self.state["runs"]) for status in STATUSES},
                "capabilities": {"real_training": False, "pause": True, "downloads": False, "checkpoint_files": False},
                "model_catalog": copy.deepcopy(MODELS), "dataset_catalog": copy.deepcopy(DATASETS),
                "updated_at": timestamp(now),
            }
