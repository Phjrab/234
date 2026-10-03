# Security scope and limitations

This is a single-admin local preparation tool with synthetic training runs. It is not a production or public-Internet training service. No real training adapter, model download, arbitrary command input or checkpoint file access is implemented.

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
- Fixed, read-only installed GPU-utility probe; no install, shell input, model or image access

Runtime authentication is always enabled. The injected auth=False option exists only in unit-test construction, has no CLI option, and is refused for LAN listeners.

## Important boundaries

Do not externally proxy, tunnel or port-forward a loopback listener. A relay can make remote clients appear local; forwarded headers are deliberately ignored and cannot establish genuine peer identity. This version supports a direct private-address TLS listener after local setup. Trusted proxies, remote TLS termination and public hosting are not implemented.

A source/login shell can be public to configured LAN peers after the bootstrap gate, but data reads still require authentication and the remote-view flag. Remote control and viewing remain separate; source visibility cannot authorize an API request. Turning off remote viewing can make the remote UI unable to display data even when API control permission remains enabled.

Loopback is not a defense against malicious software on the same host. A compromised local account, weak password, untrusted LAN, unsafe proxy or exposed backup can defeat the intended isolation. Rate limits are basic safeguards, not denial-of-service protection. No firewall/router or network changes are made here.

## Data and credentials

Initial credentials are setup defaults, not LAN credentials. Choose a unique strong password locally. No plaintext password is logged or placed in frontend/local storage. Runtime auth state and dataset records are stored in ignored SQLite files; protect them and backups. Authentication hashes still permit offline guessing if copied.

JSONL imports store actual supplied text on the dashboard machine. VLM image references are sanitized relative labels; files are not read or included in exports. Previewing schema does not check factual correctness, tokenization, licensing or model compatibility. Deterministic splitting can retain duplicates; leakage warnings must be resolved before real evaluation.

Committed fixtures and previews are synthetic only. Do not commit runtime data, tokens, models, private datasets, certificates or private keys. Report security issues privately to the maintainer without putting secrets in public issues.

See lan-access.md for deployment restrictions and validation.md for what was actually checked.
