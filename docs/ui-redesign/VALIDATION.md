# UI redesign validation

Date: 2026-10-07. Repository working directory: `/Users/hajoonpark/자율설계/forge-finetune-dashboard`.
Source/capture commit: `adac4de56e4653837fbfc81a7e3e401a49c0898c`. Evidence documentation is committed separately.

| Check / command | Status | Result / evidence |
|---|---|---|
| `python3 -m unittest discover -s tests -v` | PASS, exit 0 | 140 discovered, 137 passed, 3 skipped; final-python.txt |
| `node tests/test_frontend.js` | PASS, exit 0 | 55 DOM-stub tests; final-frontend.txt |
| `node tests/test_i18n.js` | PASS, exit 0 | Both languages, persisted/disabled storage, cross-tab changes; final-i18n.txt |
| `python3 tools/build_preview.py` | PASS, exit 0 | Generated shared-code read-only preview; final-preview.txt |
| CUA actual IAB browser suite | PASS | 73 checks, 17 after captures; captures/browser-report.json |
| Direct visual review | PASS within fixture scope | All 19 before/after PNGs opened; no unintended overlays, empty curves or page horizontal overflow |
| Sampled computed color contrast | PASS | contrast.json; selected boundary corrected from 2.10 to 4.57:1 |
| 1440×900, 1366×768, 1024×768, 390×844 | PASS | Actual IAB viewport override and screenshots |
| 720×450 equivalent reflow | PASS | Actual CSS viewport, no page overflow; browser-report.json |
| Native browser 200% zoom | NOT_RUN | IAB super+plus did not change innerWidth (1440) or DPR (1); equivalent reflow is not native zoom evidence |
| GPU training/pause/resume/retry and hardware telemetry | NEEDS_HARDWARE | Intentionally not executed; contracts covered by existing isolated tests and fixture UI states |
| Actual Hub model download | NOT_RUN | Fixture denies download; installed/unsupported metadata tested |
| Real LAN browser/device session | NOT_RUN | Existing auth/CSRF/LAN unit tests pass; no live LAN policy mutation |
| Diff, secrets, private/large evidence review | PASS | Only authored app/test/tool/docs changes; no runtime DB/weights/private account files staged |

Baseline had 137 tests (3 skipped), 39 DOM tests, passing i18n and preview. Current Python adds 3 fixture safety tests, DOM adds 16. The same three environment-dependent optional training-library tests remain skipped; see exact reasons in logs. No baseline failure was hidden or assertion removed to obtain PASS.

## Isolation and writes

`tools/ui_fixture_server.py` serves the actual changed static app on 127.0.0.1:18765. Each invocation creates disposable auth/data SQLite files in TemporaryDirectory. Authentication, Origin, CSRF and preparation routes use the existing server. No training manager, download manager, worker thread or GPU probe is created. Synthetic Hub/avatar responses replace external calls. All run execution/control, training/preflight and Hub mutation paths return a fixture denial after authorization checks.

Browser writes: disposable fixture login, synthetic JSONL validation, config dry-run and expected denied preflight only. Audit: browser-network.json includes all harness attempts in this session, method/path/status only, with four denied preflight requests across capture repairs. No Launch, lifecycle or model download was invoked. Expected resource errors: 404 avatar; 503 Hub and stale API; 409 denied preflight. The final suite reports no unexpected browser warning/error. Polling is the existing two-second GET, with focus retention checked across it. This is bounded browser coverage, not a general race/performance/load certification.

## Covered behavior

Selected run selection updates header/curve/config/console/export coherently; queued/running/pausing/paused/completed/failed/canceled states follow allowed_actions. Demo running/completed and injected OOM remain explicitly synthetic. Missing evaluation/loss stay missing. Keyboard explorer selection survives polling; console arrow/Home/End behavior and mobile surfaces work. Builder retains values through steps, navigation and ko/en changes, enforces real caps, displays exact recipe and separates dry-run, preflight and launch. Models show exact IDs, capability/installation/access separately; unsupported GGUF and unreachable Hub are actionable. Empty and stale states are explicit. Existing security and server queue/lifecycle tests are unchanged.

## Capture provenance

Every public screenshot is a synthetic UI fixture, including values shaped as real-source measurements. No chart/loss/GPU value is performance evidence. Train/eval use raw step positions and distinct line styles, with missing gaps preserved; no smoothing is applied. Manifest rows were generated after files existed. CUA returns JPEG screenshots; sips performed format-only PNG conversion. Report uses original `.jpg` capture names; delivered manifest maps them to `.png`. System fonts have no remote font dependency. Toast completion is checked before capture.

External references: AutoTrain quickstart was read. W&B workspace/line-plot pages could not be reread due to unavailable redirected pages; explicit pack design was used. No external tracking service, copied assets or telemetry was added.
