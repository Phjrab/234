# Workbench typography — 2026-10-07

## Scope and baseline

Target: Phjrab/forge-finetune-dashboard, existing `codex/ui-forge-training-workbench`, starting HEAD `a222acef6981aebe7d5a94d94b7beb5f4be1c02e`. The worktree was clean. No applicable AGENTS.md was found in the repository/parents. Reviewed existing DESIGN_SPEC, DECISIONS and explorer-size rules. The historical prompt pack was found under the user-supplied prompt/dashboard-ui-redesign/forge-ui-prompt-pack path; the root copy is absent. The current user's typography constraints govern this change, including preserving the implemented Workbench.

No main restoration, new layout, color/API/lifecycle/i18n/security change, reset, checkout or stash. Static `a222ace` files were exported with `git archive` into a temporary directory only for matched before captures. Production server.py is unchanged. Actual training, downloads, accounts, datasets, models and checkpoints were not modified. The browser fixture uses temporary auth/DB files, canned Hub responses, no GPU probe, no worker or download manager. Network audits show only fixture login POSTs, zero execution/control/download requests.

## Rules for subsequent screens

| Token | Stack / purpose | Size, weight, spacing |
| --- | --- | --- |
| `--font-ui` | Pretendard Variable → Pretendard → system sans; general ko/en/mixed UI, menus, buttons, forms, descriptions | body/forms/buttons 14px, 400/500; menus 500, important actions 600; body 1.55, letter spacing 0 |
| `--font-display` | Space Grotesk → font-ui; text brand and **English** major feature headings only | brand 28px/600; English feature heading 28px/600, slight negative spacing only here |
| `--font-mono` | JetBrains Mono → Pretendard Variable → Pretendard → system monospace; technical values, IDs, model/checkpoint names, paths, JSON, logs | code/logs 13px/400/1.6; core metrics 500 at existing 18–22px hierarchy; ligatures off, spacing 0 |

Panel headings 16–18px/600; Korean feature headings 26px/600 Pretendard with zero spacing. Selected experiment titles remain Pretendard (24px), since arbitrary names may mix languages. No universal display font on h1/h2 or arbitrary English content. Existing brand text/mark and all labels are preserved. There is no image/vector logo replacement. Source badges and observation times retain compact metadata sizes.

Numeric SVG axes use font-mono at an effective 12 CSS px. `fitChartTypography` compensates for SVG viewBox scale after drawing/resizing; font-ready/loadingdone redraws **only charts**, preserving forms and log scroll. Both learning and comparison charts use the tokens. There is no Canvas renderer or separate chart tooltip font in the current app. Color, coordinates, metric values, missing-data gaps, smoothing semantics and provenance labels are untouched.

Inputs/selects inherit UI typography; numeric/model fields opt into mono. Desktop text inputs/selects keep 40px boxes; mobile view/run selects keep 44px. Chart stats/headings can wrap when enlarged glyphs require it, console tabs retain horizontal scrolling, log timestamp/level columns receive enough mobile width. These are typography accommodations within the existing explorer/center/inspector/console structure.

Faces: `static/fonts.css`. Version/source/license and range details: [bundled font provenance](../../../static/fonts/README.md), [decoded metadata and hashes](font-metadata.json). All four binaries use swap, self hosting, no preload and no runtime CDN. Pretendard full variable file is ~2.06 MB; this is the initial local-load cost, chosen to preserve all official glyphs without inventing subsets. CSP remains `font-src 'self'`; existing MIME/static root confinement already supports WOFF2. No new private-path serving permission.

## Audit and changed files

- `static/style.css`: removed system-only body/pre/textarea/log/metric shorthands; consolidated role tokens, 400/500/600 hierarchy and mixed-language spacing; replaced legacy 650/750; enlarged UI/axis/log sizes; removed small breakpoint overrides for controls/logs.
- `static/index.html`, `static/fonts.css`, `static/fonts/*`: local font stylesheet and official binary/license assets.
- `static/app.js`: escaped semantic model/step/checkpoint spans; SVG axis typography, scale measurement and font-load redraw.
- `static/workspace.js`: comparison axes and technical table values. Builder/training/huggingface/i18n modules inherit tokens without functional changes.
- `tools/build_preview.py`, `docs/offline-preview.html`: existing generator embeds the same fonts and OFL notices for a single-file offline artifact.
- `tools/ui_fixture_server.py`: watermark inherits UI font; exact fixture-only proof HTML/JS routes. Production server routes unchanged.
- `tools/build_typography_proof.py`, `proof.html`, `proof.js`, `expected-glyphs.json`: verification-only strings; no strings inserted as product experiments/results.
- `tests/test_frontend.js`, `tests/test_server.py`: preserve draft/log state on chart font redraw, subtitle identifier escaping, actual font MIME/CSP/static confinement.
- `docs/ui-redesign/DESIGN_SPEC.md`, `ROLLBACK.md`, this folder: persistent rules, tests, evidence and reversible delivery.

## Browser evidence

Actual Codex IAB, loopback fixture `forge-workbench-v1`; canonical selected run `train-000000000001` (synthetic values in measured-source-shaped responses). Source badges and fixture watermark remain explicit. Viewports: **1920×1080, 1440×900, 390×844**, both ko/en.

[Capture manifest](captures.json) records dimensions and hashes. The 12 canonical images `before/after-{en/ko}-{1920/1440/390}.jpg` are exact-size page-origin clips at the same fixture/selection/view/viewport; 1920 clips explicitly avoid an IAB native screenshot right-edge crop. Supplementary state images use native screenshot sizing, which may crop/scale slightly; use geometry rather than their edge pixels for viewport assertions. [Before geometry](before-geometry.json) and [after geometry](browser-geometry.json) record the actual CSS viewport. Some mobile live observations have a small incidental scroll offset; canonical page-origin clips still start at document origin.

| Surface | Evidence / inspection |
| --- | --- |
| Explorer and selected detail, logs | ko/en canonical pairs at all three sizes; expanded explorer captures at desktop sizes |
| Dataset → Model → Method → Hyperparameters → Review → Launch | ko/en desktop and mobile builder; English step captures including Review/Launch; no launch action |
| Checkpoints / evaluation / configuration | ko/en 1440; ko/en 1920 evaluation; mobile evaluation/configuration and log wrapping |
| Model search, long Qwen identifier, modal | ko/en 1440 + 1920; ko/en mobile modal; canned unreachable search error |
| Settings / failure / theme | ko/en 1920 settings/errors; ko/en 1440 failures; ko mobile failure; dark Korean 1920 |
| Compare SVG | English 1440; same token/scale renderer |

Direct visual review: Korean baselines and mixed text are coherent; numeric columns and `e-4` signs remain distinct; model identifiers wrap inside their existing cards/inspector; dialog scroll stays inside the modal; 390px tabs fit and retain overflow scrolling as needed; log messages wrap without overlapping timestamps. Captured DOM geometry found no document horizontal overflow or non-SVG control content overflow. SVG text clientWidth/scrollWidth are not HTML overflow metrics and are excluded from that assertion. The normal menu view still provides a compact experiment slot; the existing Expand/Menu behavior remains available and unchanged.

### Font attribution

[Rendered font evidence](rendered-font-evidence.json) is generated by a real fixture page after FontFaceSet readiness:

- All four official WOFF2 requests returned 200 and byte lengths match decoded files; all faces loaded.
- All ten requested strings plus a mixed Korean log probe match official decoded glyph advance widths; maximum error **0.048px**, tolerance 0.12px.
- Every probe differs from its system-only comparison. This checks actual rendered geometry, not just computed family or fonts.check.
- Hangul missing from JetBrains Mono matches Pretendard fallback advances; logs are not assumed to have fixed-width Korean glyphs.
- **Limitation:** IAB exposes no CDP/Rendered Fonts API, so native per-glyph font attribution was not performed. Screenshots + loaded bytes/FontFaceSet + official advance comparison support the result, but are not presented as CDP attribution.

Proof page is fixture-only at `/__fixture__/typography`. Regenerate with a disposable Python environment containing FontTools 4.66.1 and Brotli 1.2.0: `python tools/build_typography_proof.py`. These are inspection tools, not new application runtime dependencies. The standalone offline artifact was regenerated and its embedded font bytes/licenses checked; it was not separately opened in an offline browser session.

## Tests

| Check | Actual result |
| --- | --- |
| `python3 -m unittest discover -s tests -v` | 140 run: 137 passed, 3 optional training-runtime skips; [log](python.txt) |
| Final `python3 -m unittest discover -s tests -p test_server.py -v` | 20 passed, including new WOFF2 MIME/CSP/symlink/traversal test; [log](server-final.txt) |
| `node tests/test_frontend.js` | 57 passed, including chart redraw state preservation and subtitle escaping; [log](frontend.txt) |
| `node tests/test_i18n.js` | PASS for ko/en preference, fallback, placeholders, cross-tab/storage behavior; [log](i18n.txt) |
| `python3 tools/build_preview.py` | PASS; [log](preview.txt) |
| Browser/font proof | 11/11 advance comparisons; actual matched viewport pairs; no operational POSTs |
| `git diff --check` | PASS after trimming generated license-comment line-end whitespace (upstream license files remain unmodified) |

There are no failing checks. Optional native training runtime tests were skipped because that runtime is absent. Real GPU training/performance/lifecycle operations, model downloads and production deployment were intentionally not run. Browser evidence is synthetic UI validation, not performance evidence. Native per-glyph attribution remains unavailable; full Korean font initial-load size and existing compact explorer slot are documented above.

## Delivery

Implementation commit: `30016dd` on the existing feature branch. This documentation/evidence is a separate local delivery commit. No push, PR, merge or deployment. The operator's 18766 server/tab was not stopped; only our 18767/18768 fixture sessions and owned tabs were cleaned up.

## Rollback

See [project rollback](../ROLLBACK.md). Revert only the typography implementation commit using ordinary `git revert` after reviewing later dependent changes. This keeps the pre-existing Workbench/theme/explorer implementation and all operational data. Documentation/evidence may remain as history. No DB migration, account change, browser-storage migration or service restart is required.
