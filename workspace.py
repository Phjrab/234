"""Bounded local dataset preparation, never a training or file-import worker.

Only explicitly provided JSONL text is parsed. Image references are labels: no
image, model, arbitrary path, network resource or user command is ever opened.
The one optional hardware probe uses an already installed nvidia-smi executable
with fixed, read-only arguments. Responses do not reveal local absolute paths.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import random
import re
import shutil
import sqlite3
import subprocess
import threading
import time
from typing import Any, Callable
import uuid

from simulator import DATASETS, DashboardError, timestamp, validate_config

MAX_TEXT_BYTES = 128 * 1024
MAX_ROWS = 1000
MAX_PHYSICAL_LINES = 2000
MAX_DATASETS = 50
MAX_MESSAGES = 64
MAX_FIELD_CHARS = 16384
MAX_RECORD_CHARS = 32768
MAX_IMAGES = 16
ASSUMED_VRAM_GB = 12
_ID = re.compile(r"dataset-[0-9a-f]{12}\Z")
_IMAGE_COMPONENT = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_. -]{0,79}\Z")
_PRIVATE_COMPONENTS = {
    "home", "root", "etc", "proc", "sys", "dev", "var", "tmp", "run",
    "workspace", "private", "users", "appdata", "documents", "downloads",
    "desktop", "secrets", "credentials",
}
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def _finding(code: str, message: str, line: int | None = None, field: str | None = None) -> dict:
    result = {"code": code, "message": message, "line": line}
    if field:
        result["field"] = field
    return result


def _canonical(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Nonfinite JSON number")


def _record_error(message: str, field: str):
    raise DashboardError("invalid_record", message, details={"field": field})


def _content_text(value: Any, field: str, *, allow_empty: bool = False, limit: int = MAX_FIELD_CHARS) -> str:
    if (not isinstance(value, str) or len(value) > limit
            or (not allow_empty and not value.strip())
            or any((ord(c) < 32 and c not in "\n\r\t") or ord(c) == 127 for c in value)):
        _record_error(f"{field} must be {'possibly empty' if allow_empty else 'nonempty'} text of at most {limit} characters, without binary control characters.", field)
    try:
        value.encode("utf-8")
    except UnicodeError:
        _record_error(f"{field} must contain valid Unicode text.", field)
    return value


def _image_label(value: Any, field: str) -> str:
    """Conservative dataset-relative label validation, without path resolution."""
    if not isinstance(value, str) or not 1 <= len(value) <= 256 or value != value.strip():
        _record_error("Image references must be bounded dataset-relative path labels.", field)
    components = value.split("/")
    if (len(components) > 8 or any(not _IMAGE_COMPONENT.fullmatch(p) for p in components)
            or any(p in {".", ".."} or p.lower() in _PRIVATE_COMPONENTS for p in components)
            or Path(components[-1]).suffix.lower() not in _IMAGE_SUFFIXES):
        _record_error("Image labels must use safe relative folders and an image extension; absolute, traversal, hidden, private, URL and encoded paths are rejected.", field)
    return value


def _validate_record(raw: Any, kind: str) -> tuple[dict, list[str]]:
    if not isinstance(raw, dict):
        _record_error("Each JSONL line must be an object.", "record")
    images = []
    if "messages" not in raw:
        if kind == "VLM":
            _record_error("VLM rows require messages and relative image labels.", "messages")
        if set(raw) - {"instruction", "input", "output"} or not {"instruction", "output"} <= set(raw):
            _record_error("LLM rows require messages or instruction/input/output fields only.", "record")
        record = {
            "instruction": _content_text(raw["instruction"], "instruction"),
            "input": _content_text(raw.get("input", ""), "input", allow_empty=True),
            "output": _content_text(raw["output"], "output"),
        }
        if sum(map(len, record.values())) > MAX_RECORD_CHARS:
            _record_error("Combined row text exceeds 32768 characters.", "record")
        return record, images
    allowed = {"messages"} if kind == "LLM" else {"messages", "images", "image"}
    if set(raw) - allowed:
        _record_error("Unexpected row fields; use the documented chat schema.", "record")
    if "images" in raw and "image" in raw:
        _record_error("Use images or image, not both.", "images")
    messages = raw["messages"]
    if not isinstance(messages, list) or not 2 <= len(messages) <= MAX_MESSAGES:
        _record_error("messages must contain 2 to 64 messages.", "messages")
    normalized = []
    roles = set()
    text_chars = 0
    for index, message in enumerate(messages):
        field = f"messages[{index}]"
        if not isinstance(message, dict) or set(message) != {"role", "content"}:
            _record_error("Each message needs role and content fields only.", field)
        role = message["role"]
        if not isinstance(role, str) or role not in {"system", "user", "assistant"}:
            _record_error("Message role must be system, user or assistant.", field + ".role")
        roles.add(role)
        content = message["content"]
        if isinstance(content, str):
            content = _content_text(content, field + ".content")
            text_chars += len(content)
        elif kind == "VLM" and isinstance(content, list) and 1 <= len(content) <= 32:
            blocks = []
            for block_index, block in enumerate(content):
                block_field = f"{field}.content[{block_index}]"
                if not isinstance(block, dict):
                    _record_error("VLM content blocks must be text or relative image labels.", block_field)
                if set(block) == {"type", "text"} and block["type"] == "text":
                    text = _content_text(block["text"], block_field + ".text")
                    text_chars += len(text)
                    blocks.append({"type": "text", "text": text})
                elif set(block) == {"type", "image"} and block["type"] == "image":
                    image = _image_label(block["image"], block_field + ".image")
                    images.append(image)
                    blocks.append({"type": "image", "image": image})
                else:
                    _record_error("Supported VLM blocks are {type:text,text} and {type:image,image}; URLs and other fields are not accepted.", block_field)
            if role == "assistant" and not any(block["type"] == "text" for block in blocks):
                _record_error("Assistant targets must include nonempty text, not only image labels.", field + ".content")
            content = blocks
        else:
            _record_error("Message content must be text; VLM rows may also use documented text/image blocks.", field + ".content")
        normalized.append({"role": role, "content": content})
    if not {"user", "assistant"} <= roles:
        _record_error("Rows require at least one user message and one assistant target.", "messages")
    if text_chars > MAX_RECORD_CHARS:
        _record_error("Combined row text exceeds 32768 characters.", "messages")
    record = {"messages": normalized}
    if kind == "VLM":
        top_images = raw.get("images", [raw["image"]] if "image" in raw else [])
        if not isinstance(top_images, list) or len(top_images) > MAX_IMAGES:
            _record_error("images must be an array of at most 16 relative image labels.", "images")
        top_images = [_image_label(image, f"images[{index}]") for index, image in enumerate(top_images)]
        images.extend(top_images)
        if not 1 <= len(images) <= MAX_IMAGES:
            _record_error("VLM rows require 1 to 16 image references in total.", "images")
        if top_images:
            record["images"] = top_images
    return record, images


class Workspace:
    """Independent SQLite connection, safe to share with a threaded HTTP server."""

    def __init__(self, db_path: str | Path, workspace_path: str | Path | None = None,
                 clock: Callable[[], float] = time.time):
        self.lock = threading.RLock()
        self.clock = clock
        self.workspace_path = Path(workspace_path) if workspace_path is not None else Path(__file__).parent
        path = str(db_path)
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=5)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS workspace_datasets (id TEXT PRIMARY KEY, payload TEXT NOT NULL, records TEXT NOT NULL, fingerprint TEXT NOT NULL)")
        self.db.commit()

    def close(self):
        with self.lock:
            self.db.close()

    @staticmethod
    def adapter() -> dict:
        return {"available": False, "status": "not_implemented", "real_training": False,
                "message": "No local training adapter is connected or implemented. Preparation does not start training."}

    def summary(self) -> dict:
        return {
            "mode": "preparation", "datasets": self.list_datasets(), "adapter": self.adapter(),
            "capabilities": {"jsonl_validation": True, "dataset_import": True, "deterministic_split": True,
                             "jsonl_export": True, "config_dry_run": True, "read_only_diagnostics": True,
                             "real_training": False, "image_file_access": False, "model_download": False},
            "limits": {"text_bytes": MAX_TEXT_BYTES, "rows": MAX_ROWS, "datasets": MAX_DATASETS,
                       "preview_records": 3, "messages_per_record": MAX_MESSAGES, "images_per_record": MAX_IMAGES},
            "assumed_vram_gb": ASSUMED_VRAM_GB,
            "warnings": ["12 GB VRAM is a planning assumption, not a detected device or a fit guarantee.",
                         "Imported JSONL is stored locally in the dashboard database; image references remain unopened labels."],
        }

    def _validate(self, payload: Any) -> tuple[dict, list[dict]]:
        report = {"valid": False, "name": "Imported dataset", "kind": "LLM", "synthetic": False,
                  "count": 0, "row_count": 0, "text_bytes": 0, "errors": [], "warnings": [],
                  "preview": [], "duplicates": {"count": 0, "groups": []}, "duplicate_dataset_ids": []}
        records = []
        errors, warnings = report["errors"], report["warnings"]
        if not isinstance(payload, dict):
            errors.append(_finding("invalid_payload", "Dataset input must be a JSON object."))
            return report, records
        if set(payload) - {"name", "kind", "text", "synthetic"}:
            errors.append(_finding("invalid_payload", "Only name, kind, text and optional synthetic fields are supported."))
        name = payload.get("name", "Imported dataset")
        if (not isinstance(name, str) or not name.strip() or len(name) > 80
                or any(ord(c) < 32 or ord(c) == 127 for c in name)
                or any(c in name for c in "/\\") or re.match(r"^[A-Za-z]:", name)):
            errors.append(_finding("invalid_name", "name must be a nonempty label of at most 80 characters, without paths or control characters.", field="name"))
        else:
            try:
                name.encode("utf-8")
                report["name"] = name.strip()
            except UnicodeError:
                errors.append(_finding("invalid_name", "name must contain valid Unicode text.", field="name"))
        kind = payload.get("kind", "LLM")
        if not isinstance(kind, str) or kind.upper() not in {"LLM", "VLM"}:
            errors.append(_finding("invalid_kind", "kind must be LLM or VLM.", field="kind"))
        else:
            report["kind"] = kind.upper()
        synthetic = payload.get("synthetic", False)
        if not isinstance(synthetic, bool):
            errors.append(_finding("invalid_synthetic", "synthetic must be a boolean when supplied.", field="synthetic"))
        else:
            report["synthetic"] = synthetic
        text = payload.get("text")
        if not isinstance(text, str):
            errors.append(_finding("invalid_text", "text must contain the supplied JSONL text; filesystem paths and file inputs are not supported.", field="text"))
            return report, records
        # Bound character length before UTF-8 allocation. Each character needs
        # at least one byte, so this is a safe early refusal.
        if len(text) > MAX_TEXT_BYTES:
            errors.append(_finding("text_limit", "JSONL text exceeds the 128 KiB limit.", field="text"))
            return report, records
        try:
            report["text_bytes"] = len(text.encode("utf-8"))
        except UnicodeError:
            errors.append(_finding("invalid_text", "JSONL text must contain valid Unicode text.", field="text"))
            return report, records
        if report["text_bytes"] > MAX_TEXT_BYTES:
            errors.append(_finding("text_limit", "JSONL text exceeds the 128 KiB UTF-8 limit.", field="text"))
            return report, records
        # JSONL uses LF/CRLF. Unicode line-separator characters inside a JSON
        # string are data, not record boundaries.
        lines = text.split("\n")
        if lines and lines[-1] == "" and text.endswith("\n"):
            lines.pop()
        if len(lines) > MAX_PHYSICAL_LINES:
            errors.append(_finding("line_limit", "JSONL text exceeds the 2000 physical-line safety limit.", MAX_PHYSICAL_LINES + 1))
            return report, records
        nonempty_lines = [i for i, line in enumerate(lines, 1) if line.strip()]
        report["row_count"] = len(nonempty_lines)
        if report["row_count"] > MAX_ROWS:
            errors.append(_finding("row_limit", "JSONL text exceeds the 1000 nonempty-row limit.", nonempty_lines[MAX_ROWS]))
            return report, records
        if errors:
            return report, records
        seen = {}
        image_lines = []
        for number, line in enumerate(lines, 1):
            if not line.strip():
                warnings.append(_finding("blank_line", "Blank line ignored.", number))
                continue
            try:
                raw = json.loads(line, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
            except (ValueError, RecursionError):
                errors.append(_finding("invalid_json", "Line must be valid JSON with unique keys, finite values and bounded nesting.", number))
                continue
            try:
                record, images = _validate_record(raw, report["kind"])
            except DashboardError as err:
                errors.append(_finding(err.code, err.message, number, err.details.get("field")))
                continue
            item = {"line": number, "record": record}
            records.append(item)
            encoded = _canonical(record)
            seen.setdefault(encoded, []).append(number)
            if images:
                image_lines.append(number)
        if not report["row_count"]:
            errors.append(_finding("empty_dataset", "At least one nonempty JSONL record is required."))
        report["count"] = len(records)
        report["preview"] = copy.deepcopy(records[:3])
        groups = [{"first_line": nums[0], "duplicate_lines": nums[1:]} for nums in seen.values() if len(nums) > 1]
        report["duplicates"] = {"count": sum(len(group["duplicate_lines"]) for group in groups), "groups": groups}
        for group in groups:
            for number in group["duplicate_lines"]:
                warnings.append(_finding("duplicate_record", f"Exact normalized duplicate of line {group['first_line']}; retained unless you edit the source.", number))
        for number in image_lines:
            warnings.append(_finding("images_unverified", "Image labels are syntactically valid; files, existence, dimensions and image contents have not been checked.", number))
        if 0 < report["count"] < 10:
            warnings.append(_finding("small_dataset", "Fewer than 10 valid records: this is suitable for preparation checks, not evidence of training quality."))
        report["valid"] = not errors and bool(records)
        if report["valid"]:
            fingerprint = self._fingerprint(records)
            with self.lock:
                report["duplicate_dataset_ids"] = [row[0] for row in self.db.execute("SELECT id FROM workspace_datasets WHERE fingerprint=? ORDER BY id", (fingerprint,))]
            if report["duplicate_dataset_ids"]:
                warnings.append(_finding("duplicate_dataset", "The same normalized records already exist in the workspace; importing again will create a separate dataset."))
        return report, records

    @staticmethod
    def _fingerprint(records):
        return hashlib.sha256("\n".join(_canonical(item["record"]) for item in records).encode("utf-8")).hexdigest()

    def validate_dataset(self, payload: Any) -> dict:
        return self._validate(payload)[0]

    def import_dataset(self, payload: Any) -> dict:
        report, records = self._validate(payload)
        if not report["valid"]:
            status = 413 if any(error["code"] in {"text_limit", "row_limit", "line_limit"} for error in report["errors"]) else 400
            raise DashboardError("invalid_dataset", "Dataset validation failed; no dataset was stored.", status, report)
        dataset = {
            "id": "dataset-" + uuid.uuid4().hex[:12], "name": report["name"], "kind": report["kind"],
            "samples": report["count"], "count": report["count"], "synthetic": report["synthetic"],
            "source": "imported_jsonl", "imported": True, "simulated": False,
            "created_at": timestamp(self.clock()), "text_bytes": report["text_bytes"],
            "preview": report["preview"], "warnings": report["warnings"], "duplicates": report["duplicates"],
            "schema": "messages_with_relative_images" if report["kind"] == "VLM" else "messages_or_instruction_input_output",
            "split": None, "image_files_verified": False if report["kind"] == "VLM" else None,
        }
        with self.lock, self.db:
            if self.db.execute("SELECT COUNT(*) FROM workspace_datasets").fetchone()[0] >= MAX_DATASETS:
                raise DashboardError("dataset_limit", "Workspace has reached the 50 imported-dataset limit.", 409)
            self.db.execute("INSERT INTO workspace_datasets VALUES(?,?,?,?)", (dataset["id"], _canonical(dataset), json.dumps(records, ensure_ascii=False, allow_nan=False), self._fingerprint(records)))
        return {"dataset": copy.deepcopy(dataset), "validation": report}

    @staticmethod
    def _summary(dataset: dict) -> dict:
        return {key: copy.deepcopy(dataset[key]) for key in ("id", "name", "kind", "samples", "count", "synthetic", "source", "imported", "simulated", "created_at", "text_bytes", "duplicates", "split")}

    def list_datasets(self) -> list[dict]:
        with self.lock:
            return [self._summary(json.loads(row[0])) for row in self.db.execute("SELECT payload FROM workspace_datasets ORDER BY rowid DESC")]

    def _load(self, dataset_id: Any) -> tuple[dict, list[dict]]:
        if not isinstance(dataset_id, str) or not _ID.fullmatch(dataset_id):
            raise DashboardError("not_found", "Imported dataset does not exist.", 404)
        row = self.db.execute("SELECT payload,records FROM workspace_datasets WHERE id=?", (dataset_id,)).fetchone()
        if row is None:
            raise DashboardError("not_found", "Imported dataset does not exist.", 404)
        return json.loads(row[0]), json.loads(row[1])

    def get_dataset(self, dataset_id: str) -> dict:
        with self.lock:
            dataset, _ = self._load(dataset_id)
            dataset.pop("split_indices", None)
            return dataset

    def split_dataset(self, dataset_id: str, payload: Any) -> dict:
        if not isinstance(payload, dict) or set(payload) - {"seed", "val_ratio"}:
            raise DashboardError("invalid_split", "Split accepts a JSON object with seed and val_ratio only.")
        seed, ratio = payload.get("seed", 42), payload.get("val_ratio", 0.2)
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2147483647:
            raise DashboardError("invalid_split", "seed must be an integer between 0 and 2147483647.")
        try:
            valid_ratio = not isinstance(ratio, bool) and isinstance(ratio, (int, float)) and math.isfinite(ratio) and 0 < ratio < 1
        except OverflowError:
            valid_ratio = False
        if not valid_ratio:
            raise DashboardError("invalid_split", "val_ratio must be a finite number strictly between 0 and 1.")
        with self.lock, self.db:
            dataset, records = self._load(dataset_id)
            if len(records) < 2:
                raise DashboardError("insufficient_records", "At least two records are needed for nonempty train and validation sets.", 409)
            indices = list(range(len(records)))
            random.Random(seed).shuffle(indices)
            val_count = min(len(records) - 1, max(1, math.floor(len(records) * ratio + 0.5)))
            validation = sorted(indices[:val_count])
            train = sorted(indices[val_count:])
            warnings = [_finding("split_only", "This split prepares records only; it does not tokenize, train, evaluate or open images.")]
            train_hashes = {_canonical(records[i]["record"]) for i in train}
            overlap = sum(_canonical(records[i]["record"]) in train_hashes for i in validation)
            if overlap:
                warnings.append(_finding("duplicate_leakage_risk", f"{overlap} validation record(s) have exact duplicates in training; edit or deduplicate the source before using this split for evaluation."))
            if len(records) < 10:
                warnings.append(_finding("small_split", "Small split counts make validation results unstable."))
            result = {"dataset_id": dataset_id, "seed": seed, "val_ratio": float(ratio),
                      "train_count": len(train), "validation_count": len(validation),
                      "actual_val_ratio": round(len(validation) / len(records), 6),
                      "algorithm": "seeded-row-shuffle-v1", "warnings": warnings,
                      "train_preview": copy.deepcopy([records[i] for i in train[:3]]),
                      "validation_preview": copy.deepcopy([records[i] for i in validation[:3]]),
                      "exports": [{"split": split, "filename": self._filename(dataset_id, seed, split)} for split in ("train", "validation")]}
            dataset["split"] = result
            # Store only bounded, service-generated indices. Never a filename or
            # filesystem destination supplied by the caller.
            dataset["split_indices"] = {"train": train, "validation": validation}
            self.db.execute("UPDATE workspace_datasets SET payload=? WHERE id=?", (_canonical(dataset), dataset_id))
            return copy.deepcopy(result)

    @staticmethod
    def _filename(dataset_id, seed, split):
        return f"{dataset_id}-seed{seed}-{split}.jsonl"

    def export_dataset(self, dataset_id: str, split: str) -> tuple[bytes, str]:
        if not isinstance(split, str) or split not in {"train", "validation"}:
            raise DashboardError("invalid_split", "Export split must be train or validation.")
        with self.lock:
            dataset, records = self._load(dataset_id)
            if not dataset.get("split"):
                raise DashboardError("split_required", "Create a train/validation split before exporting.", 409)
            body = "".join(_canonical(records[i]["record"]) + "\n" for i in dataset["split_indices"][split]).encode("utf-8")
            return body, self._filename(dataset_id, dataset["split"]["seed"], split)

    def presets(self) -> dict:
        presets = []
        for kind in ("LLM", "VLM"):
            for method in ("qlora", "lora"):
                config = validate_config({"name": f"Small {kind} {method.upper()} prep", "kind": kind, "method": method,
                                          "lora_rank": 8, "sequence_length": 512 if kind == "VLM" else 1024,
                                          "batch_size": 1, "gradient_accumulation": 8, "epochs": 3})
                presets.append({"id": f"small-{kind.lower()}-{method}", "name": config["name"], "config": config,
                                "assumed_vram_gb": ASSUMED_VRAM_GB,
                                "warning": "Starting-point configuration only. The assumed 12 GB GPU and model compatibility are unverified; this preset cannot guarantee fit."})
        return {"presets": presets, "assumed_vram_gb": ASSUMED_VRAM_GB, "real_training": False, "adapter": self.adapter()}

    def dry_run(self, payload: Any) -> dict:
        budget = ASSUMED_VRAM_GB
        if isinstance(payload, dict) and "config" in payload:
            if set(payload) - {"config", "assumed_vram_gb"}:
                raise DashboardError("invalid_config", "Dry-run wrapper accepts config and optional assumed_vram_gb only.")
            raw = payload["config"]
            budget = payload.get("assumed_vram_gb", ASSUMED_VRAM_GB)
            try:
                valid_budget = not isinstance(budget, bool) and isinstance(budget, (int, float)) and math.isfinite(budget) and 2 <= budget <= 192
            except OverflowError:
                valid_budget = False
            if not valid_budget:
                raise DashboardError("invalid_config", "assumed_vram_gb must be a finite number between 2 and 192.", details={"field": "assumed_vram_gb"})
        else:
            raw = payload
        config = validate_config(raw)
        warnings = [_finding("fit_not_guaranteed", f"{budget:g} GB VRAM is an explicit planning assumption. This heuristic does not measure hardware, tokenize data or guarantee that any model/configuration fits."),
                    _finding("adapter_unavailable", self.adapter()["message"])]
        known_sizes = {"Qwen/Qwen2.5-3B-Instruct": 3.0, "TinyLlama/TinyLlama-1.1B-Chat-v1.0": 1.1, "Qwen/Qwen2-VL-2B-Instruct": 2.0}
        parameters_b = known_sizes.get(config["model"], 2.0 if config["kind"] == "VLM" else 3.0)
        if config["model"] not in known_sizes:
            warnings.append(_finding("model_size_assumed", "Model label is unverified. Estimate assumes a small 2B VLM or 3B LLM; no model metadata was downloaded."))
        vlm = config["kind"] == "VLM"
        estimate = parameters_b * (0.7 if config["method"] == "qlora" else 2.0) + (3.5 if vlm else 2.0)
        estimate += config["batch_size"] * (config["sequence_length"] / 1024) * (0.9 if vlm else 0.6) + config["lora_rank"] * 0.02
        if estimate >= budget:
            warnings.append(_finding("assumed_budget_exceeded", f"Heuristic memory estimate exceeds the assumed {budget:g} GB budget; reduce context, batch or rank and validate with a real worker."))
        elif estimate >= budget * 0.8:
            warnings.append(_finding("low_memory_headroom", f"Heuristic memory estimate leaves limited headroom within the assumed {budget:g} GB budget."))
        if config["sequence_length"] >= (1024 if vlm else 2048):
            warnings.append(_finding("context_risk", "Longer context increases activation memory; VLM image tokens can add further unmeasured cost.", field="sequence_length"))
        if config["batch_size"] >= (2 if vlm else 4):
            warnings.append(_finding("batch_risk", "Larger per-device batches increase activation memory. Gradient accumulation is usually a safer tuning lever but is not a fit guarantee.", field="batch_size"))
        if config["lora_rank"] >= 64:
            warnings.append(_finding("rank_risk", "High LoRA rank increases adapter, optimizer and gradient memory.", field="lora_rank"))
        if vlm:
            warnings.append(_finding("vision_cost_unmeasured", "Image resolution, encoder cost and visual-token counts are not included in this rough estimate; image files remain unopened."))
        dataset = None
        if _ID.fullmatch(config["dataset"]):
            dataset = self.get_dataset(config["dataset"])
            if dataset["kind"] != config["kind"]:
                raise DashboardError("dataset_kind_mismatch", "Configuration kind must match the imported dataset kind.")
            if not dataset["split"]:
                warnings.append(_finding("dataset_unsplit", "Imported dataset has not been split into train and validation records."))
            if dataset["duplicates"]["count"]:
                warnings.append(_finding("dataset_duplicates", "Imported dataset contains exact duplicates; check evaluation leakage before training."))
            dataset = self._summary(dataset)
        elif any(item["id"] == config["dataset"] for item in DATASETS):
            warnings.append(_finding("demo_dataset", "Selected dataset is a synthetic simulator label, not an imported training file."))
        else:
            warnings.append(_finding("dataset_unverified", "Dataset label is not in the imported workspace. Its schema and availability have not been checked."))
        if config["failure_mode"] != "none":
            warnings.append(_finding("simulator_failure_mode", "failure_mode is a simulator-only setting and cannot configure a real training worker."))
        return {"valid": True, "config": config, "dataset": dataset, "warnings": warnings,
                "assumed_vram_gb": budget, "estimated_memory_gb": round(estimate, 2),
                "estimate": {"method": "unmeasured-memory-heuristic-v1", "parameters_billions_assumed": parameters_b,
                             "fit_guaranteed": False, "includes_image_measurements": False},
                "adapter": self.adapter(), "real_training": False, "can_train": False}

    def diagnostics(self) -> dict:
        warnings = [_finding("adapter_unavailable", "No real local training worker/adapter is implemented.")]
        try:
            usage = shutil.disk_usage(self.workspace_path)
            disk = {"available": True, "location": "dashboard workspace", "total_bytes": usage.total,
                    "free_bytes": usage.free, "used_bytes": usage.used}
        except OSError:
            disk = {"available": False, "location": "dashboard workspace"}
            warnings.append(_finding("disk_unavailable", "Workspace disk availability could not be read."))
        gpu = {"detected": False, "probe": "installed_nvidia_smi", "status": "utility_missing", "devices": [],
               "message": "No installed nvidia-smi utility was found; GPU availability is unknown."}
        executable = shutil.which("nvidia-smi")
        if executable:
            try:
                result = subprocess.run([executable, "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
                                        capture_output=True, text=True, check=False, timeout=2)
                if result.returncode != 0 or len(result.stdout) > 8192:
                    raise ValueError("GPU probe failed")
                devices = []
                for row in csv.reader(io.StringIO(result.stdout)):
                    if not row:
                        continue
                    if len(row) != 3 or len(devices) >= 16:
                        raise ValueError("Invalid GPU probe output")
                    name = row[0].strip()
                    total, free = float(row[1].strip()), float(row[2].strip())
                    if (not re.fullmatch(r"[\w .()+-]{1,160}", name) or not math.isfinite(total)
                            or not math.isfinite(free) or not 0 <= free <= total <= 10000000):
                        raise ValueError("Invalid GPU probe output")
                    devices.append({"name": name, "memory_total_mib": total, "memory_free_mib": free,
                                    "memory_total_gib": round(total / 1024, 2)})
                gpu.update(detected=bool(devices), devices=devices, status="detected" if devices else "no_devices",
                           message="Read-only installed nvidia-smi query completed." if devices else "The installed utility reported no GPU devices.")
            except (OSError, subprocess.TimeoutExpired, ValueError, UnicodeError):
                gpu.update(status="probe_failed", message="The installed GPU utility failed, timed out or returned unsupported output; GPU availability is unknown.")
        if not gpu["detected"]:
            warnings.append(_finding("gpu_unavailable", gpu["message"]))
        return {"python": {"version": platform.python_version(), "implementation": platform.python_implementation()},
                "os": {"name": platform.system(), "release": platform.release()}, "disk": disk, "gpu": gpu,
                "adapter": self.adapter(), "local_worker": {"available": False, "status": "not_implemented"},
                "assumed_vram_gb": ASSUMED_VRAM_GB, "real_training": False, "read_only": True, "warnings": warnings}
