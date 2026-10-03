import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest

from simulator import DashboardError, MAX_RUNS, Simulator, validate_config


class Clock:
    def __init__(self, now=1735689600.0):
        self.now = now
    def __call__(self):
        return self.now
    def add(self, seconds):
        self.now += seconds
        return self.now


class ConfigTests(unittest.TestCase):
    def test_defaults(self):
        config = validate_config({})
        self.assertEqual(config["kind"], "LLM")
        self.assertEqual(config["max_steps"], 120)
        self.assertEqual(config["failure_mode"], "none")

    def test_aliases_and_kind_defaults(self):
        config = validate_config({"model_type": "vlm", "model_id": "demo/model", "dataset_id": "demo-data", "max_seq_length": 2048})
        self.assertEqual(config["kind"], "VLM")
        self.assertEqual(config["model"], "demo/model")
        self.assertEqual(config["dataset"], "demo-data")
        self.assertEqual(config["sequence_length"], 2048)
        self.assertIn("VL", validate_config({"kind": "VLM"})["model"])

    def test_invalid_configs(self):
        invalid = [[], None, "x", {"kind": "GPU"}, {"epochs": True}, {"epochs": 2.5}, {"batch_size": 0},
                   {"batch_size": 65}, {"max_steps": 9}, {"max_steps": 2001}, {"learning_rate": float("nan")},
                   {"learning_rate": float("inf")}, {"learning_rate": 10**400}, {"learning_rate": "0.001"},
                   {"name": ""}, {"name": "a\nb"}, {"name": "x"*81}, {"failure_mode": "shell"},
                   {"command": "echo hello"}, {"model": "m", "model_id": "n"}, {"method": "full"}]
        for config in invalid:
            with self.subTest(config=str(config)[:80]), self.assertRaises(DashboardError) as ctx:
                validate_config(config)
            self.assertEqual(ctx.exception.status, 400)


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.db_path = Path(self.tmp.name) / "state.sqlite3"
        self.sim = Simulator(self.db_path, self.clock, seed_demo=False)

    def tearDown(self):
        self.sim.close()
        self.tmp.cleanup()

    def tick(self, seconds=1):
        self.sim.tick(self.clock.add(seconds))

    def test_seed_is_labeled_and_invariant(self):
        self.sim.reset()
        snapshot = self.sim.snapshot()
        self.assertEqual(snapshot["mode"], "demo")
        self.assertEqual(snapshot["summary"], {"running": 1, "queued": 1, "paused": 0, "completed": 1, "failed": 1, "canceled": 0})
        self.assertFalse(snapshot["gpu"]["detected"])
        self.assertTrue(snapshot["gpu"]["simulated"])
        self.assertEqual(snapshot["gpu"]["total_gb"], 12)
        self.assertFalse(snapshot["capabilities"]["real_training"])
        self.assertFalse(snapshot["capabilities"]["checkpoint_files"])
        failed = next(r for r in snapshot["runs"] if r["status"] == "failed")
        self.assertIn("Simulated", failed["error"])
        completed = next(r for r in snapshot["runs"] if r["status"] == "completed")
        self.assertEqual(completed["progress"], 100)
        self.assertTrue(all(c["virtual"] for c in completed["checkpoints"]))

    def test_queue_autostart_and_complete(self):
        run = self.sim.queue({"name": "Test", "max_steps": 10})
        self.assertEqual(run["status"], "queued")
        self.tick()
        self.assertEqual(self.sim.get_run(run["id"])["status"], "running")
        self.tick(9)
        result = self.sim.get_run(run["id"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["step"], 10)
        self.assertEqual(result["progress"], 100)
        self.assertIsNone(result["eta_seconds"])
        self.assertTrue(result["finished_at"])
        self.assertTrue(result["checkpoints"])
        self.tick(100)
        self.assertEqual(self.sim.get_run(run["id"])["step"], 10)

    def test_pause_reserves_gpu_and_preserves_step(self):
        a = self.sim.queue({"max_steps": 20})
        b = self.sim.queue({"max_steps": 20})
        self.sim.action(a["id"], "start")
        self.tick(3)
        paused = self.sim.action(a["id"], "pause")
        self.tick(15)
        self.assertEqual(self.sim.get_run(a["id"])["step"], paused["step"])
        self.assertEqual(self.sim.get_run(b["id"])["status"], "queued")
        with self.assertRaises(DashboardError) as ctx:
            self.sim.action(b["id"], "start")
        self.assertEqual(ctx.exception.code, "gpu_busy")
        self.sim.action(a["id"], "resume")
        self.tick()
        self.assertEqual(self.sim.get_run(a["id"])["step"], 4)

    def test_single_gpu_and_queue_order(self):
        a = self.sim.queue({"name": "first", "max_steps": 10})
        b = self.sim.queue({"name": "second", "max_steps": 10})
        self.tick(12)
        self.assertEqual(self.sim.get_run(a["id"])["status"], "completed")
        self.assertEqual(self.sim.get_run(b["id"])["status"], "running")
        self.assertEqual(self.sim.get_run(b["id"])["step"], 2)
        self.assertEqual(self.sim.snapshot()["summary"]["running"], 1)

    def test_manual_start_can_choose_queued_run(self):
        a = self.sim.queue({})
        b = self.sim.queue({})
        self.assertEqual(self.sim.action(b["id"], "start")["status"], "running")
        with self.assertRaises(DashboardError) as ctx:
            self.sim.action(a["id"], "start")
        self.assertEqual(ctx.exception.status, 409)

    def test_cancel_running_and_queued_truthfully(self):
        a = self.sim.queue({})
        b = self.sim.queue({})
        self.tick(3)
        result = self.sim.action(a["id"], "cancel")
        history = copy.deepcopy(result["metrics"])
        self.sim.action(b["id"], "cancel")
        self.tick(100)
        result = self.sim.get_run(a["id"])
        self.assertEqual(result["status"], "canceled")
        self.assertEqual(result["step"], 3)
        self.assertEqual(result["metrics"], history)
        self.assertEqual(self.sim.get_run(b["id"])["step"], 0)
        self.assertIn("stopped", result["logs"][-1]["message"])

    def test_cancel_paused_allows_next_queue(self):
        a = self.sim.queue({})
        b = self.sim.queue({})
        self.tick()
        self.sim.action(a["id"], "pause")
        self.sim.action(a["id"], "cancel")
        self.tick()
        self.assertEqual(self.sim.get_run(b["id"])["status"], "running")

    def test_oom_retry_preserves_failed_run(self):
        old = self.sim.queue({"failure_mode": "oom", "max_steps": 20})
        self.tick(8)
        failed = self.sim.get_run(old["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["step"], 5)
        retry = self.sim.action(old["id"], "retry")
        self.assertNotEqual(retry["id"], old["id"])
        self.assertEqual(retry["retry_of"], old["id"])
        self.assertEqual(retry["status"], "queued")
        self.assertEqual(retry["step"], 0)
        self.assertEqual(retry["config"]["failure_mode"], "oom")
        self.assertEqual(self.sim.get_run(old["id"]), failed)

    def test_invalid_transitions_and_missing_run(self):
        queued = self.sim.queue({})
        for action in ["pause", "resume", "retry"]:
            with self.subTest(action=action), self.assertRaises(DashboardError) as ctx:
                self.sim.action(queued["id"], action)
            self.assertEqual(ctx.exception.status, 409)
        self.sim.action(queued["id"], "cancel")
        with self.assertRaises(DashboardError):
            self.sim.action(queued["id"], "cancel")
        with self.assertRaises(DashboardError) as ctx:
            self.sim.get_run("run-9999")
        self.assertEqual(ctx.exception.status, 404)
        with self.assertRaises(DashboardError) as ctx:
            self.sim.action(queued["id"], "shell")
        self.assertEqual(ctx.exception.status, 404)

    def test_persistence_no_downtime_training(self):
        run = self.sim.queue({})
        self.tick(7)
        original = self.sim.get_run(run["id"])
        self.sim.close()
        self.clock.add(86400)
        self.sim = Simulator(self.db_path, self.clock)
        self.assertEqual(self.sim.get_run(run["id"]), original)
        self.tick()
        self.assertEqual(self.sim.get_run(run["id"])["step"], 8)

    def test_deterministic_metrics(self):
        a = self.sim.queue({"seed": 123, "max_steps": 10})
        self.tick(10)
        b = self.sim.queue({"seed": 123, "max_steps": 10})
        self.tick(10)
        self.assertEqual(self.sim.get_run(a["id"])["metrics"], self.sim.get_run(b["id"])["metrics"])

    def test_fractional_ticks_and_clock_reversal(self):
        run = self.sim.queue({})
        self.tick(0.4)
        self.assertEqual(self.sim.get_run(run["id"])["step"], 0)
        self.tick(0.7)
        self.assertEqual(self.sim.get_run(run["id"])["step"], 1)
        self.tick(-10)
        self.assertEqual(self.sim.get_run(run["id"])["step"], 1)
        self.tick(1)
        self.assertEqual(self.sim.get_run(run["id"])["step"], 2)

    def test_outputs_do_not_mutate_state(self):
        run = self.sim.queue({})
        snapshot = self.sim.snapshot()
        snapshot["runs"][0]["config"]["name"] = "changed"
        run["logs"].clear()
        self.assertNotEqual(self.sim.get_run(run["id"])["config"]["name"], "changed")
        self.assertTrue(self.sim.get_run(run["id"])["logs"])

    def test_concurrent_starts_keep_single_gpu(self):
        runs = [self.sim.queue({}) for _ in range(8)]
        errors = []
        def start(run):
            try:
                self.sim.action(run["id"], "start")
            except DashboardError as err:
                errors.append(err.code)
        threads = [threading.Thread(target=start, args=(run,)) for run in runs]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(self.sim.snapshot()["summary"]["running"], 1)
        self.assertEqual(errors, ["gpu_busy"] * 7)

    def test_run_cap(self):
        for _ in range(MAX_RUNS):
            self.sim.queue({})
        with self.assertRaises(DashboardError) as ctx:
            self.sim.queue({})
        self.assertEqual(ctx.exception.code, "run_limit")
        self.assertEqual(len(self.sim.snapshot()["runs"]), MAX_RUNS)

    def test_reset_returns_seed_state(self):
        self.sim.queue({"name": "Custom"})
        result = self.sim.reset()
        self.assertEqual(len(result["runs"]), 4)
        self.assertFalse(any(r["name"] == "Custom" for r in result["runs"]))
        self.assertEqual(self.sim.state["next_id"], 5)

    def test_corrupt_state_refuses_silent_reset(self):
        import sqlite3
        path = Path(self.tmp.name) / "bad.sqlite3"
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE dashboard_state(singleton INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        db.execute("INSERT INTO dashboard_state VALUES(1,?)", (json.dumps({"version": 99, "runs": []}),))
        db.commit()
        db.close()
        with self.assertRaises(ValueError):
            Simulator(path, self.clock)


if __name__ == "__main__":
    unittest.main()
