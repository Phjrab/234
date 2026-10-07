# Baseline

Clean source HEAD: `8d62c26ab48cf7f80379298887e2e7971b162fbf`.

| Command (repository root) | Exit | Result |
|---|---|---|
| python3 -m unittest discover -s tests -v | 0 | 137 tests, 3 skipped; baseline-python.txt |
| node tests/test_frontend.js | 0 | 39 DOM-stub tests |
| node tests/test_i18n.js | 0 | All language/preference assertions passed |
| python3 tools/build_preview.py | 0 | Read-only synthetic preview generated |

Startup side effects inspected before running. `server.py --no-worker` disables the simulator but needs a fresh auth setup. Initial loopback bind failed with sandbox EPERM; authorized local escalation succeeded. Only the owned test server was stopped. The reusable fixture server then created a fresh temporary DB/auth store, completed disposable authentication through AuthStore, retained CSRF/Origin checks, and never constructed a GPU manager or download manager.

Actual before browser captures: captures/before-workspace-1440.png and before-workspace-390.png. Same route `/`, selected run `train-000000000001`, fixture ID `forge-workbench-v1` as after. Captured via Codex IAB screenshot API (JPEG), converted to PNG without pixel/content edits. Before at 1440×900 places the selected curve below large KPI/list blocks. Mobile before similarly requires substantial vertical scrolling. All values are synthetic, including fixture values shaped as real-source metrics.

Playwright is not installed as a Node module. Available Codex IAB was used for actual browser rendering and interaction. DOM tests alone are not treated as browser evidence.
