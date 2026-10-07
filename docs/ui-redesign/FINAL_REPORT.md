# Forge AI Training Workbench — final report

Repository: Phjrab/forge-finetune-dashboard. Branch: `codex/ui-forge-training-workbench`.
Baseline: `8d62c26ab48cf7f80379298887e2e7971b162fbf`.
Implementation: `2942818061014b01aacbf9f3790091316174f08b`.
Final UI/capture source: `adac4de56e4653837fbfc81a7e3e401a49c0898c`. The later evidence commit changes README/documentation only; use `git rev-parse HEAD` for delivery HEAD.

## 01–06 results

1. Repository/API/DOM/security inventory and safe baseline captured; pack found in the user-attached prompt directory rather than repository root. See INVENTORY.md and BASELINE.md.
2. Charcoal explorer, warm work surface, orange selections/actions, system fonts and responsive workbench implemented. See DESIGN_SPEC.md and DECISIONS.md.
3. One selected run drives central raw loss, immutable inspector and adjustable Logs/Checkpoints/Evaluation/Configuration console. Six-step builder uses current recipe, dry-run and training APIs with separate real/demo launch actions.
4. Datasets, Models, Artifacts, Compare, Environment and Access settings remain accessible. ko/en, mobile Run/Inspector/Console, installed/runtime/access distinctions and error/empty states are preserved.
5. Python 140 discovered (137 passed, 3 skipped), DOM 55, i18n/preview and actual browser 73 checks pass. 2 before + 17 after PNGs reviewed. See VALIDATION.md for scope and unexecuted checks.
6. README, acceptance evidence, rollback and handoff documented; only authored source/test/tools/evidence committed locally. Owned fixture server stopped, its temporary DB cleaned, IAB viewport reset and owned tab closed.

## Changed files and preserved contracts

- `static/index.html`, `style.css`, `app.js`: shell, coherent selected-run surfaces, raw gap-preserving chart, semantic keyboard controls and private surface clearing on auth loss.
- `static/builder.js`, `training.js`: Dataset → Base model → Method → Hyperparameters → Review → Launch, memory-only drafts and edit-invalidated preflight/dry-run signatures; current model/split readiness and real caps.
- `static/huggingface.js`, `workspace.js`, `i18n.js`: standalone catalog, PAT wording, dataset readiness, evaluation comparison and Korean labels.
- `tests/test_frontend.js`, `test_ui_fixture.py`: meaningful payload/readiness/focus/provenance/security regressions; previous assertions retained.
- `tools/build_preview.py`, `ui_fixture_server.py`, `capture_workbench.cua.js`, `docs/offline-preview.html`: shared-code preview and isolated actual-browser harness.
- `README.md`, `docs/ui-redesign/`: product/navigation documentation, logs, manifests, before/after and rollback.

No backend production lifecycle, schema, security or persistence implementation changed. Single GPU FIFO and checkpoint-before-pause/resume/retry remain server authoritative. No framework or dependency added. Storage keys `forge.language` and `forge.selectedRun` retain their meaning; `forge.inspectorHidden` is visual-only. No draft/PAT is persisted in browser storage.

## Evidence and limits

[Before desktop](captures/before-workspace-1440.png) / [After desktop](captures/after-workspace-1440.png), same run `train-000000000001`, fixture `forge-workbench-v1`, route and viewport. [Builder review](captures/after-builder-review-1440.png). All filenames, timestamps, SHA and provenance: [manifest](captures/CAPTURE_MANIFEST.csv).

Screenshots contain synthetic loss and GPU values, even for Real GPU source-shaped runs. Measured, estimated, demo and UI fixture provenance are separate. Existing historical real GPU validation remains in README/docs; this redesign did not repeat it. Native 200% browser zoom, actual LAN browser session and real downloads are NOT_RUN; GPU operations remain NEEDS_HARDWARE. 720×450 equivalent reflow passed. No implementation blocker remains; these are explicit follow-up validation boundaries.

## Safe local review

From repository root: `python3 tools/ui_fixture_server.py --port 18765`. Open `http://127.0.0.1:18765/`; disposable fixture login is printed by the tool. It denies execution/control/download and writes only a temporary DB. Stop with Ctrl-C. For zero server use, open `docs/offline-preview.html` (read-only synthetic). Reproduction: captures/README.md. Production startup/security instructions remain in README.
