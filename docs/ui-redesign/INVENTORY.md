# Repository and feature inventory

Audit date: 2026-10-07 (Asia/Seoul). Repository: `Phjrab/forge-finetune-dashboard`.
Baseline HEAD: `8d62c26ab48cf7f80379298887e2e7971b162fbf`; clean `main` at start.
Feature branch: `codex/ui-forge-training-workbench`. No applicable AGENTS.md found in this repository or its parents. No package/lockfile; Python standard-library server and plain JS/CSS.

The requested root pack does not exist in this checkout. Read the attached pack at `../prompt/dashboard-ui-redesign/forge-ui-prompt-pack/`: START_HERE, MASTER_PROMPT, 01–06, ACCEPTANCE_CHECKLIST and REFERENCES. The user's explicit task authorizes these phases; attached reference facts were independently checked against current code.

Read: README, server.py, auth.py, static/index.html/style.css/app.js/workspace.js/training.js/huggingface.js/i18n.js, docs/workspace-api.md/adapter-contract.md/security.md/validation.md, tests/test_frontend.js/test_i18n.js, tools/build_preview.py/verify_browser.js; inspected training.py configuration and lifecycle. README historical validation dates and blob SHA are historical evidence, not current checkout/deployment SHA. No deployment was inspected.

| Existing feature | Original DOM/event and API | New access | Verification |
|---|---|---|---|
| Run selection/filter | #runs-body tr[data-run], selectRun; GET /api/status | Explorer + mobile selected-run select | DOM selection/XSS; browser keyboard/polling |
| Train/eval loss | renderDetail/chart, metrics.step/loss/eval_loss | Central raw curve, gap-preserving train/eval renderer | DOM null/gap tests; browser SVG |
| Single GPU FIFO/lifecycle | allowed_actions; POST /api/runs/{id}/{start,pause,resume,cancel,retry} | Run header controls; server response remains authoritative | Existing Python lifecycle/queue tests; duplicate-request DOM test |
| Logs/error/OOM | #run-error, #tab-content, safeTechnicalText | Console Logs; failure recipe revision; demo scenario in Launch | Redaction/XSS and error DOM tests; browser console |
| Checkpoints/adapter ZIP | virtual flag; GET /api/runs/{id}/artifacts/{name} | Artifacts nav + console Checkpoints | Existing artifact API tests; fixture UI link; no real weights opened |
| Evaluation | run.evaluation; generated_response/reference | Console Evaluation + Compare | Null/XSS DOM; fixture browser |
| Config and JSON/CSV export | run.config; /api/runs/{id}/export?format=json/csv | Inspector + console Configuration | Existing export provenance tests; DOM href IDs |
| JSONL validation/import/split/preview/export | #dataset-form; /api/datasets[/validate], /{id}/split, /{id}/export | Datasets with split readiness badges | Existing Python schema/duplicates/path tests; actual isolated validation |
| VLM images | data-dataset-images; /api/datasets/{id}/images | Existing dataset image upload controls | Existing image snapshot/path tests; no private images used |
| Recipe presets/dry-run/export | #recipe-form; GET /api/presets, POST /api/config/dry-run | Dataset→Model→Method→Hyperparameters→Review→Launch | Exact payload/gate DOM tests; actual isolated dry-run |
| Real GPU preflight/queue | /api/training, /api/training/preflight, /api/training/runs | Explicit Review check and gated Real GPU Launch | Python API contract; mocked DOM payload; fixture denies execution |
| Demo and injected OOM | /api/runs, failure_mode | Explicit Demo source/Launch, scenario select | Preserved creation/payload/OOM tests |
| Hub search/filter/exact ID/capability/download | hf catalog functions; /api/huggingface/* | Models page + builder model dialog | Existing Hub tests; fixture installed/GGUF UI |
| HF PAT account connection | password-type #hf-token; connect/disconnect | Access settings; explicit PAT, not OAuth | Existing token non-exposure tests; no real token |
| Auth/CSRF/password setup/LAN view-control | api X-CSRF-Token; checkAccess, auth forms, /api/auth/*, /api/settings | Access settings + same sign-in dialog | Existing 401/403/CSRF/bootstrap tests; fixture keeps auth |
| Diagnostics | /api/diagnostics | Environment | Existing diagnostics tests; fixture probe-free UI |
| Language/preference | I18n, forge.language, forge.selectedRun | Existing settings ko/en; same storage keys | i18n suite; browser switch retains draft |
| Read-only offline preview | tools/build_preview.py uses actual static code | docs/offline-preview.html | Build + actual-app fixture browser evidence are separately recorded |

Actual enums: queued/running/pausing/paused/canceling/completed/failed/canceled. `checkpointing` and `cancelled` in the prompt are mapped to pausing and canceled, never sent to the server.

Dangerous actions: real/demo queue creation; lifecycle controls; Hub download/cancel; account connection; password/access settings writes; image import and persistent dataset writes. Browser evidence uses a disposable loopback server with execution/control/download denial. Dataset validation and dry-run use real backend routes in its temporary DB. Existing unit tests mutate only their temporary fixtures.

State matrix: empty; demo queued/running/completed/failed with injected OOM; real-source UI fixture queued/running/pausing/paused/completed/failed/canceled; missing evaluation; null loss; capability unavailable/unsupported; auth/session/CSRF/LAN rejection; Hub failure; stale API; duplicate/stale launch. Real GPU measurements and model files are outside this UI validation.
