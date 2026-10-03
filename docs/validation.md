# Validation matrix · implemented checks and honest limits

Checked in the build VM on 2026-10-03. PASS means the named check passed at its stated scope. FAIL below describes failed verification-tool attempts, not a demonstrated application defect. NOT RUN means there is no evidence of the promised runtime behavior at that layer.

No screenshot is supplied because no permitted browser route rendered the app. The offline HTML file is a generated read-only preview, not proof of browser testing.

## Matrix

| Area | Status | Evidence | Blocker / remaining scope |
|---|---|---|---|
| Backend, state machine, persistence, HTTP/API security, datasets, auth | PASS | 93 standard-library unittest cases; no failures | Unit and temporary loopback HTTP tests only |
| Demo start/pause/resume/cancel/retry, FIFO scheduling, injected OOM | PASS | Simulator/API tests, retained histories and single-GPU invariant | Synthetic state only; no real process or GPU |
| JSONL validation, line/field errors, LLM/VLM paths, splits, downloads | PASS | Workspace tests and authenticated HTTP round trip | No image reads, tokenization or actual training-data semantics |
| Downloadable beginner samples and unsupported formats | PASS | 3 synthetic JSONL samples accepted; CSV/JSON-array/binary rejected; frontend unsupported-file stub | Actual browser file picker/download interaction not run |
| Config dry-run, explicit VRAM assumption, memory warnings | PASS | Finite budget2–192 validated; fixed/configurable risk tests | Estimate is unmeasured, not a model fit guarantee |
| Local bootstrap and saved ON flags with effective gate | PASS | Hash/session/password/CSRF/peer tests; spoofed headers do not make peers local | Synthetic test credentials and temporary databases only |
| Remote view/control separation and response privacy | PASS | Injected external-peer regression; control-only responses omit private snapshots/previews | No actual LAN listener or second device |
| Python compile and both JavaScript syntax checks | PASS | py_compile; node --check app.js/workspace.js | No runtime browser guarantee |
| Frontend rendering/handlers/help/error markup | PASS | 29 dependency-free DOM-stub checks; generated markup nesting; unique static IDs | Stubs do not measure CSS, focus, viewport, timing or real DOM behavior |
| Supported browser localhost route | FAIL (verification route) | net::ERR_BLOCKED_BY_CLIENT on normal and explicitly permitted local preview port | No extension, browser policy or network restriction was changed |
| Native read-only offline-file visualization | FAIL (verification route) | AT-SPI provider unavailable for Chromium native input, including authorized retry | Input failed before the file rendered; no dashboard screenshot |
| Actual desktop/mobile browser layout | NOT RUN | No permitted browser rendering obtained | Must be checked on a host with working local browser access |
| Full UI → API button/login/file/download flow | NOT RUN | Backend HTTP + DOM handlers checked separately only | Their passing results do not establish browser integration |
| Direct TLS LAN from another computer | NOT RUN | Guard/flag/cookie logic tested without LAN exposure | User host, trusted certificate and second same-network device unavailable |
| Ubuntu/WSL2 deployment and firewall behavior | NOT RUN | Documentation reviewed against official guidance | No OS/network settings changed; host-specific acceptance needed |
| Actual RTX3060 VRAM, CUDA/driver/library compatibility | NOT RUN |12 GB is an explicit assumption | User hardware not measured in this VM |
| Real training/evaluation/weights/checkpoint resume | NOT RUN / NOT IMPLEMENTED | Adapter capability false; UI says unavailable | No real worker or training dependencies; no model downloads |

## Repeat the automated checks

Run from the repository root:

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile server.py simulator.py adapter.py auth.py workspace.py tools/build_preview.py
node --check static/app.js
node --check static/workspace.js
node tests/test_frontend.js
```

Python tests use temporary synthetic credentials and loopback listeners. They do not start a LAN listener, change the firewall/router, install ML software or train a model. CI runs these automated checks; CI itself is only passed when the exact published commit has a successful check.

## Local browser acceptance checklist

These are still **NOT RUN** until someone completes them on a working local host and records evidence.

1. Start with python3 server.py. Open localhost. Initial admin/admin must work only locally, and the data API must be unavailable until a strong password is changed
2. Confirm saved LAN/view/control flags are ON but effective remote access remains OFF with the loopback listener
3. Home shows active jobs/GPU/alerts; Experiments shows history/details; each preparation feature is a separate view
4. Create a demo run; start when the slot is free; pause and confirm steps stop; resume, cancel, retry and confirm the original remains
5. Exercise injected OOM. Expand safe technical logs and review the copied recipe; a revised normal scenario should not preserve the OOM injection
6. In Datasets load/download chat, instruction and VLM samples. Validate, save, split, export and verify records/counts. Feed invalid JSON, missing fields, ../image paths and unsupported files; check line/field/code/next-step feedback
7. In Training setup change the assumed budget and risky settings, dry-run, expand advanced fields and export config. Real training must remain unavailable
8. Compare two runs and download JSON/CSV. Check CSV strings cannot execute spreadsheet formulas and checkpoints remain virtual metadata
9. Environment must distinguish actual server diagnostics, no connected real training adapter and synthetic demo telemetry
10. At desktop and390px mobile widths, test navigation, dialogs, tabs, form validation, cancel/back, repeated clicks, keyboard focus, scroll and downloads. Capture real screenshots and console errors
11. Log out and confirm private run details disappear. Repeat with expired session/network failure to check sign-in/stale messages

## Same-network acceptance checklist

Use the user's own machine only after reviewing the LAN guide. Do not publish the service or change firewall/router settings as part of an unapproved test.

1. Finish password setup locally first. Choose a direct private-IP TLS listener with a trusted matching certificate
2. From a second same-network computer, confirm initial credentials never work, unauthenticated data is denied and login works with the changed password
3. Test view ON/control OFF; view OFF/control ON must not expose private data through mutation responses; LAN OFF must deny remote access while local recovery remains possible
4. Verify certificate trust, exact Host/Origin/CSRF checks, session expiry, logout and rate limit behavior
5. Confirm no public router forwarding/proxy to loopback exists. Record actual OS/version/networking mode and firewall restrictions separately

## Future real-training acceptance

Measure the actual GPU VRAM/driver, confirm model/library compatibility and test a tiny approved synthetic dataset only after a real adapter exists. Validate authoritative process exit, cancel, restart, checkpoint files and held-out evaluation separately. This draft cannot pass those checks today.
