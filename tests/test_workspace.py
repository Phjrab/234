import json
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from simulator import DashboardError, Simulator, validate_config
from workspace import MAX_DATASETS, MAX_ROWS, MAX_TEXT_BYTES, Workspace


def instruction(index=0):
    return {"instruction": f"Question {index}", "input": "", "output": f"Answer {index}"}


def messages():
    return {"messages": [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}]}


def payload(rows=None, kind="LLM", **kwargs):
    return {"name": "Test dataset", "kind": kind,
            "text": "\n".join(json.dumps(row, ensure_ascii=False) for row in (rows if rows is not None else [instruction()])), **kwargs}


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "state.sqlite3"
        self.workspace = Workspace(self.path, workspace_path=self.tmp.name, clock=lambda: 1735689600)

    def tearDown(self):
        self.workspace.close()
        self.tmp.cleanup()

    def imported(self, rows=None, **kwargs):
        return self.workspace.import_dataset(payload(rows, **kwargs))["dataset"]

    def test_summary_preparation_capabilities_are_truthful(self):
        result = self.workspace.summary()
        self.assertEqual(result["mode"], "preparation")
        self.assertEqual(result["limits"]["rows"], 1000)
        self.assertEqual(result["limits"]["text_bytes"], 128 * 1024)
        self.assertEqual(result["datasets"], [])
        self.assertFalse(result["adapter"]["available"])
        self.assertFalse(result["capabilities"]["real_training"])
        self.assertFalse(result["capabilities"]["image_file_access"])
        self.assertEqual(result["assumed_vram_gb"], 12)

    def test_llm_schemas_normalize_and_preview_is_bounded(self):
        rows = [instruction(i) for i in range(4)] + [messages()]
        del rows[0]["input"]
        report = self.workspace.validate_dataset(payload(rows))
        self.assertTrue(report["valid"])
        self.assertEqual(report["count"], 5)
        self.assertEqual(len(report["preview"]), 3)
        self.assertEqual(report["preview"][0]["record"]["input"], "")
        self.assertEqual(report["preview"][2]["line"], 3)

    def test_error_line_numbers_and_no_partial_import(self):
        data = payload([instruction()])
        data["text"] += '\nnot JSON\n{"instruction":"x","output":null}\n[]'
        report = self.workspace.validate_dataset(data)
        self.assertFalse(report["valid"])
        self.assertEqual([item["line"] for item in report["errors"]], [2, 3, 4])
        self.assertEqual(report["count"], 1)
        with self.assertRaises(DashboardError) as ctx:
            self.workspace.import_dataset(data)
        self.assertEqual(ctx.exception.details["errors"], report["errors"])
        self.assertEqual(self.workspace.list_datasets(), [])

    def test_duplicate_lines_are_canonical_and_retained(self):
        data = payload([instruction(), instruction(1), instruction()])
        row = instruction()
        del row["input"]
        data["text"] += "\n" + json.dumps(row)
        report = self.workspace.validate_dataset(data)
        self.assertTrue(report["valid"])
        self.assertEqual(report["count"], 4)
        self.assertEqual(report["duplicates"], {"count": 2, "groups": [{"first_line": 1, "duplicate_lines": [3, 4]}]})
        dataset = self.workspace.import_dataset(data)["dataset"]
        self.assertEqual(dataset["count"], 4)
        again = self.workspace.validate_dataset(data)
        self.assertEqual(again["duplicate_dataset_ids"], [dataset["id"]])

    def test_empty_and_blank_lines(self):
        for text in ["", "\n\n\n", "  \r\n"]:
            with self.subTest(text=text):
                report = self.workspace.validate_dataset({"text": text})
                self.assertFalse(report["valid"])
                self.assertEqual(report["errors"][-1]["code"], "empty_dataset")
        data = {"text": "\n" + json.dumps(instruction()) + "\r\n\n"}
        report = self.workspace.validate_dataset(data)
        self.assertTrue(report["valid"])
        self.assertEqual(report["preview"][0]["line"], 2)
        self.assertEqual([item["line"] for item in report["warnings"] if item["code"] == "blank_line"], [1, 3])

    def test_unicode_line_separators_are_text_not_records(self):
        row = instruction()
        row["output"] = "Hello\u2028world\u2029"
        report = self.workspace.validate_dataset(payload([row]))
        self.assertTrue(report["valid"])
        self.assertEqual(report["count"], 1)
        self.assertEqual(report["preview"][0]["record"]["output"], row["output"])

    def test_payload_metadata_validation(self):
        invalid = [None, [], "data.jsonl", {"text": []}, {"text": "x", "file": "data.jsonl"},
                   {"text": "x", "kind": "audio"}, {"text": "x", "kind": None},
                   {"text": "x", "synthetic": 1}, {"text": "x", "name": ""},
                   {"text": "x", "name": "a\nb"}, {"text": "x", "name": "x" * 81},
                   {"text": "x", "name": "/home/private/file"}, {"text": "x", "name": "C:\\file"},
                   {"text": "x", "name": "\ud800"}]
        for item in invalid:
            with self.subTest(item=repr(item)):
                self.assertFalse(self.workspace.validate_dataset(item)["valid"])

    def test_json_unique_keys_finite_and_bounded_nesting(self):
        lines = ['{"instruction":"a","instruction":"b","output":"c"}',
                 '{"instruction":NaN,"output":"c"}', '{"instruction":Infinity,"output":"c"}',
                 '{"instruction":1e400,"output":"c"}', '[' * 1100 + '0' + ']' * 1100,
                 '{"instruction":"a","output":"c",}', 'null']
        for line in lines:
            with self.subTest(line=line[:50]):
                report = self.workspace.validate_dataset({"text": line})
                self.assertFalse(report["valid"])
                self.assertEqual(report["errors"][0]["line"], 1)

    def test_bounded_fields_schema_roles_and_binary_controls(self):
        bad_rows = [None, [], {"instruction": "a"}, {"output": "b"},
                    {"instruction": "a", "output": "b", "command": "echo bad"},
                    {"instruction": "a", "input": 5, "output": "b"},
                    {"instruction": "", "output": "b"}, {"instruction": "a", "output": "\x00"},
                    {"instruction": "a", "output": "x" * 16385},
                    {"instruction": "x" * 16384, "input": "x" * 16384, "output": "x"},
                    {"messages": []}, {"messages": messages()["messages"] * 33},
                    {"messages": [{"role": "tool", "content": "a"}, {"role": "assistant", "content": "b"}]},
                    {"messages": [{"role": "system", "content": "a"}, {"role": "assistant", "content": "b"}]},
                    {"messages": [{"role": "user", "content": "a", "name": "x"}, {"role": "assistant", "content": "b"}]},
                    {"messages": [{"role": "user", "content": []}, {"role": "assistant", "content": "b"}]},
                    {**messages(), "images": ["images/a.jpg"]}]
        for row in bad_rows:
            with self.subTest(row=str(row)[:60]):
                report = self.workspace.validate_dataset(payload([row]))
                self.assertFalse(report["valid"])
                self.assertEqual(report["errors"][0]["line"], 1)

    def test_rows_and_utf8_byte_limits(self):
        report = self.workspace.validate_dataset(payload([instruction()] * MAX_ROWS))
        self.assertTrue(report["valid"])
        too_many = self.workspace.validate_dataset(payload([instruction()] * (MAX_ROWS + 1)))
        self.assertEqual(too_many["errors"][0]["code"], "row_limit")
        self.assertEqual(too_many["errors"][0]["line"], 1001)
        for text in ["x" * (MAX_TEXT_BYTES + 1), "한" * (MAX_TEXT_BYTES // 3 + 1)]:
            report = self.workspace.validate_dataset({"text": text})
            self.assertEqual(report["errors"][0]["code"], "text_limit")
            with self.assertRaises(DashboardError) as ctx:
                self.workspace.import_dataset({"text": text})
            self.assertEqual(ctx.exception.status, 413)
        self.assertEqual(self.workspace.validate_dataset({"text": "\n" * 2001})["errors"][0]["code"], "line_limit")
        self.assertFalse(self.workspace.validate_dataset({"text": "\ud800"})["valid"])

    def test_vlm_messages_images_are_labels_only(self):
        row = {**messages(), "images": ["images/cat.jpg", "assets/dog_1.PNG"]}
        with patch.object(Path, "open", side_effect=AssertionError("No image opens allowed")), patch.object(Path, "resolve", side_effect=AssertionError("No image resolution allowed")):
            result = self.workspace.import_dataset(payload([row], kind="VLM"))
        self.assertTrue(result["validation"]["valid"])
        self.assertFalse(result["dataset"]["image_files_verified"])
        self.assertIn("images_unverified", {warning["code"] for warning in result["validation"]["warnings"]})
        self.assertEqual(result["dataset"]["preview"][0]["record"]["images"], row["images"])

    def test_vlm_image_alias_and_content_blocks(self):
        row = {**messages(), "image": "photos/image.webp"}
        report = self.workspace.validate_dataset(payload([row], kind="VLM"))
        self.assertTrue(report["valid"])
        self.assertEqual(report["preview"][0]["record"]["images"], ["photos/image.webp"])
        row = {"messages": [
            {"role": "user", "content": [{"type": "text", "text": "Caption"}, {"type": "image", "image": "images/a.jpg"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "A cat"}]}]}
        report = self.workspace.validate_dataset(payload([row], kind="VLM"))
        self.assertTrue(report["valid"])
        self.assertEqual(report["preview"][0]["record"], row)

    def test_vlm_path_rejection_has_line_without_private_path_echo(self):
        paths = ["/home/name/private.jpg", "../private.jpg", "images/../../private.jpg", "images//a.jpg",
                 "images/./a.jpg", "C:\\Users\\name\\a.jpg", "C:/images/a.jpg", "\\\\server\\a.jpg",
                 "~/.ssh/a.jpg", ".secret/a.jpg", "images/.a.jpg", "home/name/a.jpg", "images/private/a.jpg",
                 "images/secrets/a.jpg", "https://example.test/a.jpg", "file:///tmp/a.jpg", "data:image/png;base64,A",
                 "images/%2e%2e/a.jpg", "images/%252e/a.jpg", "images/a.jpg?x=y", "images/a.jpg#x",
                 "images/a.txt", "images/a\x00.jpg", " images/a.jpg", "images/a.jpg ", "images/a\\b.jpg",
                 "images/" + "x" * 257 + ".jpg", "a/b/c/d/e/f/g/h/i.jpg"]
        for path in paths:
            with self.subTest(path=path):
                report = self.workspace.validate_dataset(payload([{**messages(), "images": [path]}], kind="VLM"))
                self.assertFalse(report["valid"])
                self.assertEqual(report["errors"][0]["line"], 1)
                self.assertNotIn(path, json.dumps(report["errors"]))

    def test_vlm_missing_schema_and_image_bounds(self):
        rows = [instruction(), messages(), {**messages(), "images": "images/a.jpg"},
                {**messages(), "images": ["images/a.jpg"] * 17},
                {**messages(), "images": ["images/a.jpg"], "image": "images/a.jpg"},
                {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "images/a.jpg"}}]}, {"role": "assistant", "content": "cat"}]},
                {"messages": [{"role": "user", "content": "a"}, {"role": "assistant", "content": [{"type": "image", "image": "images/a.jpg"}]}]}]
        for row in rows:
            with self.subTest(row=str(row)[:80]):
                self.assertFalse(self.workspace.validate_dataset(payload([row], kind="VLM"))["valid"])

    def test_import_metadata_synthetic_choice_and_persistence(self):
        imported = self.imported([instruction(), instruction(1)], synthetic=True)
        self.assertTrue(re.fullmatch(r"dataset-[0-9a-f]{12}", imported["id"]))
        self.assertEqual(imported["created_at"], "2025-01-01T00:00:00Z")
        self.assertTrue(imported["synthetic"])
        self.assertFalse(imported["simulated"])
        self.assertEqual(imported["source"], "imported_jsonl")
        self.workspace.close()
        self.workspace = Workspace(self.path, self.tmp.name)
        self.assertEqual(self.workspace.get_dataset(imported["id"]), imported)
        self.assertEqual(self.workspace.list_datasets()[0]["id"], imported["id"])

    def test_separate_workspace_connection_preserves_simulator(self):
        simulator = Simulator(self.path, seed_demo=False)
        try:
            run = simulator.queue({"name": "Preserve me"})
            imported = self.imported()
            self.assertEqual(simulator.get_run(run["id"])["name"], "Preserve me")
            self.assertEqual(self.workspace.get_dataset(imported["id"])["count"], 1)
            self.assertEqual(simulator.snapshot()["summary"]["queued"], 1)
        finally:
            simulator.close()

    def test_detail_and_listing_are_independent_copies(self):
        dataset = self.imported()
        detail = self.workspace.get_dataset(dataset["id"])
        detail["preview"][0]["record"]["output"] = "changed"
        summary = self.workspace.list_datasets()
        summary[0]["name"] = "changed"
        self.assertEqual(self.workspace.get_dataset(dataset["id"])["name"], dataset["name"])
        self.assertEqual(self.workspace.get_dataset(dataset["id"])["preview"], dataset["preview"])

    def test_dataset_limit_and_threaded_imports(self):
        for _ in range(MAX_DATASETS - 2):
            self.imported()
        errors = []
        def save():
            try:
                self.imported()
            except DashboardError as err:
                errors.append(err.code)
        threads = [threading.Thread(target=save) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(self.workspace.list_datasets()), MAX_DATASETS)
        self.assertEqual(errors, ["dataset_limit", "dataset_limit"])

    def test_unknown_or_unsafe_dataset_ids(self):
        for dataset_id in [None, "../file", "dataset-' OR 1=1", "dataset-000000000000", "instruction-demo"]:
            with self.subTest(dataset_id=dataset_id), self.assertRaises(DashboardError) as ctx:
                self.workspace.get_dataset(dataset_id)
            self.assertEqual(ctx.exception.status, 404)

    def test_split_is_seeded_disjoint_complete_and_exportable(self):
        rows = [instruction(i) for i in range(20)]
        dataset = self.imported(rows)
        with self.assertRaises(DashboardError) as ctx:
            self.workspace.export_dataset(dataset["id"], "train")
        self.assertEqual(ctx.exception.code, "split_required")
        result = self.workspace.split_dataset(dataset["id"], {"seed": 51, "val_ratio": 0.2})
        self.assertEqual((result["train_count"], result["validation_count"]), (16, 4))
        self.assertEqual(self.workspace.split_dataset(dataset["id"], {"seed": 51, "val_ratio": 0.2}), result)
        exported = {}
        for split in ["train", "validation"]:
            body, filename = self.workspace.export_dataset(dataset["id"], split)
            self.assertIsInstance(body, bytes)
            self.assertTrue(re.fullmatch(r"dataset-[0-9a-f]{12}-seed51-(train|validation)\.jsonl", filename))
            self.assertTrue(body.endswith(b"\n"))
            exported[split] = [json.loads(line) for line in body.decode("utf-8").splitlines()]
            self.assertEqual(len(exported[split]), result[split + "_count"])
        train_outputs = {row["output"] for row in exported["train"]}
        val_outputs = {row["output"] for row in exported["validation"]}
        self.assertFalse(train_outputs & val_outputs)
        self.assertEqual(train_outputs | val_outputs, {row["output"] for row in rows})
        self.assertNotIn("split_indices", self.workspace.get_dataset(dataset["id"]))
        different = self.workspace.split_dataset(dataset["id"], {"seed": 52, "val_ratio": 0.2})
        self.assertNotEqual(result["validation_preview"], different["validation_preview"])

    def test_split_survives_restart_and_exports_identical_bytes(self):
        dataset = self.imported([instruction(i) for i in range(10)])
        result = self.workspace.split_dataset(dataset["id"], {})
        exported = self.workspace.export_dataset(dataset["id"], "train")
        self.workspace.close()
        self.workspace = Workspace(self.path, self.tmp.name)
        self.assertEqual(self.workspace.get_dataset(dataset["id"])["split"], result)
        self.assertEqual(self.workspace.export_dataset(dataset["id"], "train"), exported)

    def test_duplicate_leakage_is_warned(self):
        dataset = self.imported([instruction()] * 6)
        result = self.workspace.split_dataset(dataset["id"], {})
        self.assertIn("duplicate_leakage_risk", {item["code"] for item in result["warnings"]})
        self.assertEqual(result["train_count"] + result["validation_count"], 6)

    def test_split_validation_and_nonempty_rounding(self):
        dataset = self.imported([instruction(), instruction(1)])
        invalid = [None, [], {"path": "/tmp/out"}, {"seed": True}, {"seed": 1.5}, {"seed": -1},
                   {"seed": 2147483648}, {"val_ratio": True}, {"val_ratio": "0.2"}, {"val_ratio": 0},
                   {"val_ratio": 1}, {"val_ratio": float("nan")}, {"val_ratio": float("inf")}, {"val_ratio": 10 ** 400}]
        for data in invalid:
            with self.subTest(data=str(data)[:40]), self.assertRaises(DashboardError):
                self.workspace.split_dataset(dataset["id"], data)
        for ratio in [0.0000001, 0.9999999]:
            result = self.workspace.split_dataset(dataset["id"], {"val_ratio": ratio})
            self.assertEqual((result["train_count"], result["validation_count"]), (1, 1))
        one = self.imported()
        with self.assertRaises(DashboardError) as ctx:
            self.workspace.split_dataset(one["id"], {})
        self.assertEqual(ctx.exception.code, "insufficient_records")
        for split in ["val", "all", "../train", None, []]:
            with self.subTest(split=split), self.assertRaises(DashboardError):
                self.workspace.export_dataset(dataset["id"], split)

    def test_vlm_export_preserves_unopened_relative_labels(self):
        dataset = self.imported([{**messages(), "images": [f"images/{i}.jpg"]} for i in range(3)], kind="VLM")
        self.workspace.split_dataset(dataset["id"], {})
        with patch.object(Path, "open", side_effect=AssertionError("No image reads")):
            train, _ = self.workspace.export_dataset(dataset["id"], "train")
        self.assertTrue(all(row["images"][0].startswith("images/") for row in map(json.loads, train.decode().splitlines())))

    def test_presets_are_valid_and_never_guarantee_fit(self):
        result = self.workspace.presets()
        self.assertEqual(len(result["presets"]), 4)
        self.assertEqual({p["id"] for p in result["presets"]}, {"small-llm-lora", "small-llm-qlora", "small-vlm-lora", "small-vlm-qlora"})
        for preset in result["presets"]:
            self.assertEqual(validate_config(preset["config"]), preset["config"])
            self.assertEqual(preset["assumed_vram_gb"], 12)
            self.assertIn("cannot guarantee fit", preset["warning"])
        self.assertFalse(result["adapter"]["available"])

    def test_dry_run_warns_memory_context_batch_rank_and_no_adapter(self):
        result = self.workspace.dry_run({"kind": "VLM", "sequence_length": 8192, "batch_size": 4, "lora_rank": 128})
        warnings = {item["code"] for item in result["warnings"]}
        self.assertTrue({"fit_not_guaranteed", "adapter_unavailable", "context_risk", "batch_risk", "rank_risk", "assumed_budget_exceeded", "vision_cost_unmeasured"} <= warnings)
        self.assertGreater(result["estimated_memory_gb"], 12)
        self.assertFalse(result["can_train"])
        self.assertFalse(result["real_training"])
        self.assertFalse(result["estimate"]["fit_guaranteed"])

    def test_dry_run_uses_existing_schema_and_wrapper(self):
        self.assertEqual(self.workspace.dry_run({"config": {}}), self.workspace.dry_run({}))
        for config in [None, [], {"learning_rate": float("nan")}, {"command": "run"}, {"batch_size": 100}]:
            with self.subTest(config=config), self.assertRaises(DashboardError):
                self.workspace.dry_run(config)
        result = self.workspace.dry_run({"model": "unknown/model", "dataset": "unknown-data", "failure_mode": "oom"})
        self.assertTrue({"model_size_assumed", "dataset_unverified", "simulator_failure_mode"} <= {x["code"] for x in result["warnings"]})

    def test_dry_run_explicit_assumption_is_bounded_finite_and_used(self):
        result = self.workspace.dry_run({"config": {}, "assumed_vram_gb": 2})
        self.assertEqual(result["assumed_vram_gb"], 2)
        self.assertIn("assumed_budget_exceeded", {x["code"] for x in result["warnings"]})
        self.assertIn("2 GB", result["warnings"][0]["message"])
        result = self.workspace.dry_run({"config": {}, "assumed_vram_gb": 192})
        self.assertEqual(result["assumed_vram_gb"], 192)
        self.assertNotIn("assumed_budget_exceeded", {x["code"] for x in result["warnings"]})
        self.assertFalse(result["estimate"]["fit_guaranteed"])
        for value in [None, True, "12", 1.9, 192.1, float("nan"), float("inf"), 10 ** 400]:
            with self.subTest(value=str(value)[:50]), self.assertRaises(DashboardError):
                self.workspace.dry_run({"config": {}, "assumed_vram_gb": value})
        with self.assertRaises(DashboardError):
            self.workspace.dry_run({"config": {}, "unknown": 1})

    def test_dry_run_imported_dataset_kind_and_split(self):
        dataset = self.imported([instruction(), instruction(1)])
        result = self.workspace.dry_run({"dataset": dataset["id"]})
        self.assertEqual(result["dataset"]["id"], dataset["id"])
        self.assertIn("dataset_unsplit", {x["code"] for x in result["warnings"]})
        with self.assertRaises(DashboardError) as ctx:
            self.workspace.dry_run({"kind": "VLM", "dataset": dataset["id"]})
        self.assertEqual(ctx.exception.code, "dataset_kind_mismatch")

    def test_diagnostics_missing_gpu_is_explicit_and_no_subprocess(self):
        with patch("workspace.shutil.which", return_value=None), patch("workspace.subprocess.run") as run:
            result = self.workspace.diagnostics()
        run.assert_not_called()
        self.assertFalse(result["gpu"]["detected"])
        self.assertEqual(result["gpu"]["status"], "utility_missing")
        self.assertFalse(result["local_worker"]["available"])
        self.assertTrue(result["read_only"])
        self.assertGreaterEqual(result["disk"]["free_bytes"], 0)
        self.assertNotIn(self.tmp.name, json.dumps(result))
        self.assertNotIn("/", result["disk"]["location"])

    def test_diagnostics_installed_fixed_argv_timeout(self):
        probe = SimpleNamespace(returncode=0, stdout="NVIDIA RTX 3060, 12288, 11000\nNVIDIA RTX A6000, 49152, 48000\n")
        with patch("workspace.shutil.which", return_value="/usr/bin/nvidia-smi"), patch("workspace.subprocess.run", return_value=probe) as run:
            result = self.workspace.diagnostics()
        run.assert_called_once_with(["/usr/bin/nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"], capture_output=True, text=True, check=False, timeout=2)
        self.assertTrue(result["gpu"]["detected"])
        self.assertEqual(result["gpu"]["devices"][0]["memory_total_gib"], 12)
        self.assertEqual(len(result["gpu"]["devices"]), 2)
        self.assertFalse(result["adapter"]["available"])
        self.assertNotIn("/usr/bin", json.dumps(result))

    def test_diagnostics_probe_failures_are_safe(self):
        bad = [SimpleNamespace(returncode=1, stdout="/home/private/secret"),
               SimpleNamespace(returncode=0, stdout="/home/private, 12288, 10000"),
               SimpleNamespace(returncode=0, stdout="GPU, NaN, 0"),
               SimpleNamespace(returncode=0, stdout="GPU, 100, 200"),
               SimpleNamespace(returncode=0, stdout="x" * 8193)]
        for probe in bad:
            with self.subTest(probe=probe.stdout[:20]), patch("workspace.shutil.which", return_value="/usr/bin/nvidia-smi"), patch("workspace.subprocess.run", return_value=probe):
                result = self.workspace.diagnostics()
            self.assertEqual(result["gpu"]["status"], "probe_failed")
            self.assertFalse(result["gpu"]["detected"])
            self.assertNotIn("/home/private", json.dumps(result))
        with patch("workspace.shutil.which", return_value="/usr/bin/nvidia-smi"), patch("workspace.subprocess.run", side_effect=subprocess.TimeoutExpired("/private/bin", 2)):
            result = self.workspace.diagnostics()
        self.assertEqual(result["gpu"]["status"], "probe_failed")
        self.assertNotIn("/private", json.dumps(result))

    def test_diagnostics_disk_failure_and_no_gpu_devices(self):
        with patch("workspace.shutil.disk_usage", side_effect=OSError("/home/private")), patch("workspace.shutil.which", return_value="/usr/bin/nvidia-smi"), patch("workspace.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="")):
            result = self.workspace.diagnostics()
        self.assertFalse(result["disk"]["available"])
        self.assertEqual(result["gpu"]["status"], "no_devices")
        self.assertTrue({"disk_unavailable", "gpu_unavailable"} <= {item["code"] for item in result["warnings"]})
        self.assertNotIn("/home/private", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
