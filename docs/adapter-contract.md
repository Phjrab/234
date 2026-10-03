# Future local worker adapter · design contract

**Status: planned.** `adapter.py` is a Python typing Protocol, not a runtime worker. The server currently accepts only demo configuration and operates its deterministic simulator. No event-ingestion endpoint or real worker exists.

## Architecture

Browser → loopback dashboard API → validated queue → local worker adapter → approved training library.
The training machine owns model files, datasets, telemetry and checkpoints. The UI never receives access tokens, shell commands or sensitive filesystem roots.

## Lifecycle

`queued → running → completed | failed | canceled`. Retry is a new run with a parent reference and retained original history. Start/cancel requests must be idempotent in a real implementation, keyed by request ID. A cancel response means acknowledged, not terminated; a real worker must wait for process exit before reporting `canceled`.

Pause/resume is **demo-only today**. A future adapter advertises `pause=false` unless it implements and tests a safe checkpoint-and-resume mechanism. The UI must not offer unsupported actions. Only one running or paused demo run can own the synthetic GPU slot. The demo scheduler automatically starts the oldest queued run when the slot is free.

## Proposed event envelope

```json
{
  "version": 1,
  "run_id": "run-0001",
  "sequence": 42,
  "timestamp": "2026-01-01T00:00:42Z",
  "kind": "metric",
  "payload": {
    "step": 42,
    "loss": 1.81,
    "eval_loss": 1.94,
    "learning_rate": 0.0002
  }
}
```

Kinds: `metric`, `log`, `checkpoint`, `status`, `telemetry`. `sequence` is monotonically increasing per run. Reject unknown versions, nonfinite values, oversized payloads, regressions and cross-run events. Deduplicate replayed events, store atomically and make reconnection resume from the last acknowledged sequence.

- Metric: nonnegative `step`, finite `loss`, optional finite `eval_loss`, finite nonnegative `learning_rate`; `null` means not measured
- Log: timestamp, allowlisted level, bounded UTF-8 message, escape in the UI and redact credentials/private data
- Checkpoint: ID, step, relative label and verified metadata; no arbitrary filesystem paths or download URLs
- Telemetry: measured source, device UUID/name, total/used VRAM, temperature and utilization; distinguish missing/unsupported from zero. Mark all simulator telemetry synthetic
- Status: explicit lifecycle state, bounded diagnostic code/message, authoritative exit status when known

## Required safety boundaries before real training

1. Allowlisted adapter implementations and model recipes. Never accept an arbitrary command string, executable or remote code option from the browser
2. Resolve dataset/output paths within configured roots; reject traversal, symlink escapes and unsupported file types. Keep those private roots server-side
3. Validate model licenses, storage space, VRAM and expected resource use before launch. Downloads require an explicit approved workflow
4. Keep Hugging Face and other credentials out of frontend assets, logs, events, database exports and public repositories
5. Loopback transport by default. Remote worker access requires authenticated transport, authorization, origin protection and per-job scope before exposing any port
6. Run training as an unprivileged OS user, enforce process/resource limits and cancel only owned processes. Never target by ambiguous process name
7. Worker heartbeats, event backlog bounds, crash recovery and persistent ownership leases. Never show an unreachable worker as healthy or an orphaned process as canceled
8. Real integration tests with a tiny approved local synthetic dataset before any user data is introduced

These are design requirements, not implemented assurances.
