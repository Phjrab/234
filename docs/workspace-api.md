# Workspace preparation API

This service prepares explicitly supplied JSONL text. It does not train, tokenize,
download models, read a dataset file from a server path, or open images. Simulator
metrics remain synthetic and separate from this preparation workspace. Imported
dataset metadata and records are actual locally stored inputs, not simulated
training results. The optional `synthetic` field describes the caller's source
data and defaults to `false`; it does not imply that any training happened.

All HTTP routes use the dashboard's authentication and remote-data/control
settings. Initial local password-change setup must be completed before data APIs
are accessible. GET/download access is gated as data viewing; validation,
importing, split changes and config dry runs use the server's control gate.
Refer to `security.md` for LAN/TLS and access-control details.

## Service facade

`Workspace(db_path, workspace_path=project_directory)` has its own thread-safe
SQLite connection and table, `workspace_datasets`. It can share the simulator's
database file without altering simulator state; the HTTP server can also give it
a separate workspace database. Its constructor receives trusted service paths,
never a path supplied by the dataset API. Responses do not disclose these paths.

| HTTP route | Service method | Result |
| --- | --- | --- |
| GET `/api/workspace` | `summary()` | capabilities, limits, imported dataset summaries, adapter status |
| GET `/api/datasets` | `list_datasets()` | HTTP `{datasets: [...]}` wrapper |
| POST `/api/datasets/validate` | `validate_dataset(payload)` | validation report, no writes |
| POST `/api/datasets` | `import_dataset(payload)` | `{dataset, validation}`, HTTP 201 |
| POST `/api/datasets/import` | `import_dataset(payload)` | optional equivalent import alias |
| GET `/api/datasets/{id}` | `get_dataset(id)` | HTTP `{dataset: ...}` wrapper |
| POST `/api/datasets/{id}/split` | `split_dataset(id, payload)` | deterministic split summary |
| GET `/api/datasets/{id}/export?split=train` | `export_dataset(id, "train")` | UTF-8 JSONL attachment |
| GET `/api/datasets/{id}/export?split=validation` | `export_dataset(id, "validation")` | UTF-8 JSONL attachment |
| GET `/api/presets` | `presets()` | four small LLM/VLM LoRA/QLoRA configurations |
| POST `/api/config/dry-run` | `dry_run(payload)` | validated config, heuristic memory warnings |
| GET `/api/diagnostics` | `diagnostics()` | read-only Python/OS/disk/GPU availability |

The facade does not implement HTTP. `export_dataset` returns `(bytes, filename)`;
the server owns content headers and authorization. Filenames are generated from
the safe dataset ID, validated seed and fixed split name, for example
`dataset-a0123456789b-seed42-train.jsonl`. No user-supplied export destination or
filename is accepted. There is no dataset deletion endpoint or filesystem import.

## Import payload and limits

```json
{
  "name": "Small instruction set",
  "kind": "LLM",
  "text": "{\"instruction\":\"Say hello\",\"input\":\"\",\"output\":\"Hello\"}\n",
  "synthetic": false
}
```

- Only `name`, `kind`, `text` and optional `synthetic` are accepted
- `name`: nonempty label, at most 80 characters; paths and control characters rejected
- `kind`: LLM or VLM, case-insensitive; defaults to LLM
- `text`: supplied JSONL string, at most 131,072 UTF-8 bytes
- At most 1,000 nonempty records and 2,000 physical LF/CRLF lines
- At most 50 persistent imported datasets; exceeding the cap returns 409
- A message field has at most 16,384 characters; combined row text at most 32,768
- Chat rows contain 2 to 64 messages; VLM rows contain 1 to 16 image references
- JSON objects require unique keys; nonfinite numeric constants, invalid Unicode,
  binary control characters, unknown fields and unsupported schema are rejected
- Blank lines are ignored with line-numbered warnings
- The HTTP envelope has its own bounded request size; JSON escaping can make it
  larger than the decoded JSONL text

For LLM rows, use either a chat record:

```json
{"messages":[{"role":"user","content":"Hello"},{"role":"assistant","content":"Hi"}]}
```

or an instruction record:

```json
{"instruction":"Answer the question","input":"What is 2 + 2?","output":"4"}
```

`instruction` and `output` must be nonempty strings. `input` is optional and
normalizes to an empty string. Instruction records remain instruction records in
exports; they are not converted to a model-specific chat template. Chat messages
use exactly `role` and `content`, with roles `system`, `user`, or `assistant` and
at least one user message and one assistant target. LLM content is text only.

For VLM rows, use messages plus image labels:

```json
{"messages":[{"role":"user","content":"Caption this image"},{"role":"assistant","content":"A cat"}],"images":["images/cat.jpg"]}
```

A single `image` string is also supported and normalizes to the `images` array.
Do not provide both. VLM content may alternatively use documented blocks:

```json
{"messages":[{"role":"user","content":[{"type":"text","text":"Caption this"},{"type":"image","image":"images/cat.jpg"}]},{"role":"assistant","content":[{"type":"text","text":"A cat"}]}]}
```

Assistant targets in block form must include nonempty text. The service accepts
neither arbitrary block schemas nor `image_url` URL inputs. Image references are
only dataset-relative labels: up to 256 ASCII characters, at most eight path
components, and common image extensions. Absolute/Windows/UNC paths, traversal,
hidden components, conservative private-folder names, URLs, query fragments,
percent encoding and non-image extensions are rejected. The service never
resolves or opens them. Each accepted VLM row warns that image existence,
contents, dimensions and accessibility remain unverified.

## Validation and persisted metadata

```json
{
  "valid": true,
  "name": "Small instruction set",
  "kind": "LLM",
  "synthetic": false,
  "count": 2,
  "row_count": 2,
  "text_bytes": 180,
  "errors": [],
  "warnings": [{"code":"small_dataset","message":"...","line":null}],
  "preview": [{"line":1,"record":{"instruction":"...","input":"","output":"..."}}],
  "duplicates": {"count":0,"groups":[]},
  "duplicate_dataset_ids": []
}
```

`count` is the number of valid records. `row_count` counts all nonblank source
lines, including invalid records. `preview` contains at most three valid records
with original one-based line numbers. Findings contain `code`, `message`, `line`
and optionally `field`; global findings use `line: null`. Invalid image-label
errors do not echo the rejected private path.

Exact duplicate comparisons use normalized, key-sorted JSON. Duplicate groups
contain `first_line` and `duplicate_lines`; `count` counts additional copies.
Copies are retained and every duplicate row is warned. Already imported datasets
with the same ordered normalized records are listed by safe ID. Importing again
creates a separate dataset.

Validation is read-only. Import stores nothing unless every row is valid. Failed
import raises `DashboardError("invalid_dataset", ..., details=validation_report)`;
schema failures are HTTP 400 and text/row/line-limit failures are HTTP 413. Stored
metadata includes safe ID, name, kind, count/samples, creation time, source
`imported_jsonl`, `imported: true`, `simulated: false`, previews, duplicate findings,
warnings and split state. `synthetic` records only the explicitly supplied source
classification. Stored full records are available through bounded split exports,
not a server filesystem path.

## Deterministic split and JSONL export

```json
{"seed":42,"val_ratio":0.2}
```

Defaults are seed 42 and validation ratio 0.2. Seed must be an integer between 0
and 2,147,483,647; ratio must be finite and strictly between 0 and 1. At least two
records are required, otherwise HTTP 409. The seeded-row-shuffle-v1 algorithm
shuffles row indices with a dedicated seeded RNG, rounds the requested validation
count and clamps it to guarantee nonempty train/validation sets. Rows are emitted
in source order within each partition. Importantly, copies are **not deduplicated**
or grouped. When exact duplicate records cross partitions, the split returns an
explicit `duplicate_leakage_risk` warning requiring source editing/deduplication
before evaluation. Small splits also warn about unstable validation.

```json
{
  "dataset_id":"dataset-a0123456789b",
  "seed":42,
  "val_ratio":0.2,
  "train_count":8,
  "validation_count":2,
  "actual_val_ratio":0.2,
  "algorithm":"seeded-row-shuffle-v1",
  "warnings":[],
  "train_preview":[],
  "validation_preview":[],
  "exports":[{"split":"train","filename":"dataset-a0123456789b-seed42-train.jsonl"},{"split":"validation","filename":"dataset-a0123456789b-seed42-validation.jsonl"}]
}
```

Split indices persist in SQLite; restarting the service preserves byte-identical
exports. Repeating the same split settings yields the same partition. Splitting
again replaces the stored split only, without modifying source records. Export
requires a split (409 when absent) and accepts exactly `train` or `validation`.
Every exported record is key-sorted normalized JSON plus a trailing newline.
No JSONL file is written by the service; the HTTP server streams its returned
bytes as an authenticated download.

## Presets and configuration dry run

`presets()` returns `presets`, `assumed_vram_gb: 12`, `real_training: false` and
unavailable adapter metadata. Each preset has `id`, `name`, `config`,
`assumed_vram_gb: 12`, and an explicit fit-uncertainty warning. IDs are
`small-llm-lora`, `small-llm-qlora`, `small-vlm-lora`, `small-vlm-qlora`.

The dry run accepts existing simulator config fields directly or a wrapper:

```json
{"config":{"kind":"LLM","method":"qlora","batch_size":1,"lora_rank":8,"sequence_length":1024},"assumed_vram_gb":12}
```

The optional wrapper budget must be finite and between 2 and 192 GB, defaulting
to 12. It remains an **assumption**, even if it matches a diagnostic reading.
Config validation uses the existing `validate_config`; unsupported fields or
invalid/nonfinite values return its existing HTTP 400 errors. Imported dataset
kind must match the config kind. Demo dataset labels and unknown labels explicitly
warn that they are not verified training data.

The result contains `valid`, normalized `config`, optional imported `dataset`
summary, findings in `warnings`, `assumed_vram_gb`, `estimated_memory_gb`,
`estimate`, unavailable `adapter`, `real_training: false`, and `can_train: false`.
The estimate is an unmeasured heuristic of assumed model size, method, context,
batch and rank. Unknown model labels use explicit assumed sizes without network
lookups. It warns on estimated budget excess/low headroom, high context, batch or
rank, and unmeasured VLM image costs. It does not inspect weights, tokenize rows,
measure peak allocations, assess model-specific compatibility, or guarantee fit.
Schema validity is not trainability.

## Read-only diagnostics

The diagnostics route reports Python version/implementation, OS name/release,
available disk bytes at the trusted workspace, and GPU availability. It does not
expose hostnames, environment variables, executable paths or absolute workspace
paths. Local training worker and adapter availability always remain false.

If and only if `shutil.which("nvidia-smi")` finds an already installed utility,
diagnostics invokes a fixed, shell-free command with a two-second timeout:

```text
nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits
```

No package, driver or software is installed; no subprocess accepts user input.
GPU states are `utility_missing`, `probe_failed`, `no_devices`, or `detected`.
Missing/failed probes mean availability is unknown and cannot be treated as a
confirmed absence of hardware. Device fields include `name`, `memory_total_mib`,
`memory_free_mib`, and `memory_total_gib`. Raw stdout/stderr and executable paths
are not returned. A detected GPU does not create a worker, enable training, or
turn the 12 GB planning assumption into a measured fit guarantee.

## Verification

```bash
python3 -m unittest discover -s tests -p test_workspace.py -v
```

Tests cover both dataset schemas, limits, line-numbered errors and duplicate
findings, private/traversal/URL image-label refusal, no image opens, all-or-nothing
imports, SQLite persistence and simulator coexistence, bounded concurrent imports,
reproducible splits/exports, leakage warnings, config/preset validity, explicit
VRAM assumptions, and missing/failed/successful mocked installed GPU probes. The
tests do not install software, open images, train or perform a live GPU probe.
