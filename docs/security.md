# Security scope and limitations

This is a single-admin local GPU training and preparation tool with separately labeled synthetic demo runs. Direct private-LAN HTTPS is supported. Remote workers, public hosting and arbitrary command execution are unsupported.

## Implemented safeguards

- Loopback bind by default; explicit opt-in for direct private-IP LAN listeners
- Initial admin/admin is accepted only from a genuine loopback socket peer
- First-use password change before experiment data, controls or LAN become available
- Salted PBKDF2 password hashing, bounded expiring sessions, peer binding, login failure limiting, logout and session revocation
- HttpOnly / SameSite=Strict cookies, Secure with TLS
- Exact Host and Origin checks, session CSRF protection for authenticated mutations, no CORS allowance
- Separate LAN, remote-view and remote-control flags; saved ON intent differs from effective access
- TLS required for LAN unless the operator explicitly acknowledges insecure HTTP
- Bounded JSON bodies and imported JSONL, finite numbers, schema validation, traversal rejection, contained static serving
- Escaped user labels/previews and formula-safe CSV exports with generated filenames
- Fixed, read-only installed GPU-utility probe; no shell input. Real training uses only approved local model snapshots and dataset-bound uploaded images

Runtime authentication is always enabled. The injected auth=False option exists only in unit-test construction, has no CLI option, and is refused for LAN listeners.

## Important boundaries

Do not externally proxy, tunnel or port-forward a loopback listener. A relay can make remote clients appear local; forwarded headers are deliberately ignored and cannot establish genuine peer identity. This version supports a direct private-address TLS listener after local setup. Trusted proxies, remote TLS termination and public hosting are not implemented.

A source/login shell can be public to configured LAN peers after the bootstrap gate, but data reads still require authentication and the remote-view flag. Remote control and viewing remain separate; source visibility cannot authorize an API request. Turning off remote viewing can make the remote UI unable to display data even when API control permission remains enabled.

Loopback is not a defense against malicious software on the same host. A compromised local account, weak password, untrusted LAN, unsafe proxy or exposed backup can defeat the intended isolation. Rate limits are basic safeguards, not denial-of-service protection. No firewall/router or network changes are made here.

## Data and credentials

Initial credentials are setup defaults, not LAN credentials. Choose a unique strong password locally. No plaintext password is logged or placed in frontend/local storage. Runtime auth state and dataset records are stored in ignored SQLite files; protect them and backups. Authentication hashes still permit offline guessing if copied.

JSONL imports store actual supplied text on the dashboard machine. VLM image references are sanitized relative labels. JSONL validation does not open images; authenticated image uploads store referenced PNG/JPEG privately and real VLM jobs snapshot/read them. Image bytes are not included in experiment metadata exports. Previewing schema does not check factual correctness, tokenization, licensing or model compatibility. Deterministic splitting can retain duplicates; leakage warnings must be resolved before real evaluation.

Committed fixtures and previews are synthetic only. Do not commit runtime data, tokens, models, private datasets, certificates or private keys. Report security issues privately to the maintainer without putting secrets in public issues.

See lan-access.md for deployment restrictions and validation.md for what was actually checked.

## Real training boundary

Training is explicitly enabled with a dedicated environment and revision-pinned Hub snapshots. Authenticated explicit safe-asset downloads, native Transformers architecture checks, local-only safe-weight loading, bounded image/context limits, contained output paths, single worker ownership and authenticated artifact exports apply. A training account can consume GPU/disk resources; this is a trusted single-admin tool rather than a multi-tenant sandbox. Private optimizer files and worker tracebacks are excluded from artifact downloads. See [worker/API](adapter-contract.md).

## Hugging Face connection

The single dashboard admin can connect a personal read token through the authenticated, same-origin CSRF-protected settings API. The token is validated with the official whoami endpoint and persisted in a private `0600` server file, not hashed because it must authorize Hub requests. Responses, experiment exports, download jobs and browser storage never include the token. Disconnect deletes the server copy; revoke the actual token at Hugging Face when needed. Hub API requests reject redirects so account credentials cannot follow a redirect to another host. Publisher icons are proxied from the exact official CDN hostname without credentials or redirects, with bounded raster image types.

Model search does not execute repository code. Downloads select root-level JSON, safetensors and tokenizer assets at a pinned commit; Python, pickle weights and nested assets are excluded. Training remains local-only with `trust_remote_code=False` and `use_safetensors=True`. Metadata-based compatibility is preliminary; unknown architectures, processor/template mismatches and insufficient memory can still prevent training. A malicious or incorrect model asset can exhaust resources; the dashboard is a trusted single-admin tool.
