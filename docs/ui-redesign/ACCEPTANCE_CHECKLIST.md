# Acceptance checklist

Statuses apply to the stated evidence scope. NOT_RUN and NEEDS_HARDWARE are not passing claims.

| Criterion | Status | Evidence / boundary |
|---|---|---|
| Selected-run IDE/workbench structure | PASS | captures/after-workspace-1440.png, DESIGN_SPEC.md |
| Real GPU / Demo in list/detail/chart/log/export | PASS within contract/fixture scope | DOM provenance tests, test_ui_fixture.py, source badges and captures |
| Dataset→Model→Method→Hyperparameters→Review→Launch uses existing API | PASS | builder DOM payload/gates, actual isolated dry-run browser check |
| FIFO and checkpoint-before-pause/resume/retry semantics | PASS for unchanged contract; NEEDS_HARDWARE live exercise | Existing training/API tests, INVENTORY.md; no real controls invoked |
| Hub selection/download/support/readiness and GPU provenance distinct | PASS UI; NOT_RUN actual download | Installed/GGUF captures, contrast/source DOM tests |
| ko/en, auth/CSRF/LAN contracts and no automatic training/download | PASS isolated scope | i18n, existing Python auth/LAN tests, fixture denial tests, browser-network.json |
| Checkout/instructions/user changes/baseline checked first | PASS | INVENTORY.md, BASELINE.md |
| Every existing feature has an access mapping | PASS | INVENTORY.md, FINAL_REPORT.md |
| Actual app modified | PASS | static/* and fixture browser, shared preview generator |
| Empty/loading/error/stale/disabled core states | PASS tested states | DOM regressions, browser-report.json, empty/OOM/unsupported captures |
| Keyboard/focus/contrast/long text/mobile | PASS sampled scope | browser-report.json, contrast.json, direct PNG review; not comprehensive screen-reader certification |
| Native 200% zoom | NOT_RUN | IAB shortcut produced no zoom; 720×450 equivalent reflow separately PASS |
| Tests and unexecuted hardware checks distinguished | PASS | VALIDATION.md and logs |
| Actual before/after PNG and manifest | PASS | 19 existing PNGs, CAPTURE_MANIFEST.csv; directly opened |
| Private data/tokens/files/production processes protected | PASS local scope | Synthetic fixture, method/path-only audit, no operational data/worker/manager used |
| Code/tests/docs/rollback/handoff and authored local commits | PASS | FINAL_REPORT.md, ROLLBACK.md, HANDOFF.md, branch history |
| No unrequested push/merge/release/deployment | PASS | Local commits only |

Native zoom and live hardware/LAN checks remain follow-up validation items, not implementation blockers or implied PASS. Historical hardware evidence is retained unchanged in README and docs/validation.md.
