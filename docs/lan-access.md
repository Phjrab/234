# Forge Fine-tuning Dashboard · Authentication and LAN access

This is a single-admin preparation dashboard with a local GPU trainer and synthetic run simulator. Creating code for LAN access does not enable it. The default listener remains `127.0.0.1:8765`; no router, firewall, network settings or public exposure are changed by the application.

## First-use security gate

1. Start locally with `python server.py` and open `http://127.0.0.1:8765` on that machine.
2. Sign in with administrator ID `admin` and initial password `admin`.
3. Enter the current password and choose a different strong password before accessing experiment data or controls.

A new password must be 12–256 characters, use at least three character types when shorter than 20 characters, contain at least six distinct characters, and differ from the current password. A longer passphrase is accepted. The weak initial password remains usable only for local setup. External socket peers are refused for every route, including HTML, source assets and login, until setup is complete. No simulated run can be controlled with a bootstrap session before the password is changed.

The server determines local access solely from the actual TCP socket peer using IP loopback checks, including mapped IPv6. It never treats `Host`, `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto` or `X-Real-IP` as proof of locality. This is a boundary between direct connections, not a defense against a malicious process on the same host. Do not externally forward a loopback service; see the proxy restrictions below.

## Saved intent versus effective access

LAN access, remote viewing and remote control are saved as **enabled** on first use, as requested. The Settings panel separately displays these saved flags and what is currently effective.

- During local setup all effective remote flags are off
- After setup, a loopback-only listener still has all effective remote flags off
- After an explicit LAN restart, effective LAN requires the saved LAN flag; remote view and remote control each additionally require their own saved flag
- Turning off remote viewing denies external experiment/workspace/settings data reads; turning off remote control denies external mutations
- The public login shell and session metadata remain available after the LAN/bootstrap gate, even with remote viewing off; source inspection never bypasses private API guards
- Authenticated local admin access remains available so a disabled remote feature can be restored locally

Authenticated admins change flags through JSON `POST /api/settings`; the browser must provide its session CSRF token. Authentication/session metadata is separate from experiment data. With view off and control on, API clients can act on known run/dataset targets; mutation responses then return only control acknowledgments, never configurations, logs, metrics, other runs or previews. Browser run lists remain unavailable. JSONL validation and config dry-run are read-only operations and require remote viewing even though they use POST; logout is allowed independently of control. Toggle viewing back on to use the full remote dashboard. Disabling LAN can prevent the current remote session from fetching further status; log in locally to recover access.

## Optional direct LAN TLS listener

Complete local setup first and stop the local process before choosing a LAN listener. The following is documentation only: replace the private address and certificate paths with your own values, and make the deployment decision yourself.

```sh
python server.py --lan --host 192.168.1.20 --port 8765 \
  --tls-cert /user/provided/dashboard-cert.pem \
  --tls-key /user/provided/dashboard-key.pem
```

The certificate must be trusted by the client and cover the address/name it uses. Do not bypass browser certificate warnings. TLS 1.2+ is required by the server's TLS context. Certificate/private-key files are never returned to the frontend. Put them outside `static/` and the repository. This feature does not provision certificates.

A nonloopback listener requires `--lan`. Only literal private bind addresses or wildcard bind addresses are accepted; public, multicast and link-local bind addresses are refused. An exact private-IP bind does not accept loopback requests, so complete first use on the default listener before switching. Wildcard binds such as `0.0.0.0` require an exact `--allowed-host` address/name. A wildcard listener may include unintended interfaces: prefer a specific private address. Additional allowed names use repeatable `--allowed-host dashboard.internal` flags, lowercase and without ports; requests must use the actual configured port. DNS names are never guessed from request headers.

LAN listeners require a certificate/key by default. `--allow-insecure-http` is an explicit developer-only override that prints a warning. With that option passwords, dataset content and session cookies can be intercepted on the network. It is inappropriate on shared or untrusted networks and is not enabled by default. `--lan` by itself does not silently change the default bind address.

This draft does not claim production hardening, public-Internet safety, multi-user isolation, network allowlists or firewall protection. It performs no firewall/router changes or discovery and creates no public endpoint.

## Proxy and tunnel restrictions

**Do not reverse-proxy, tunnel, port-forward or externally relay the loopback listener.** A relay that connects from loopback makes external clients appear local at the socket layer. Forwarded headers are intentionally ignored; authentication, bootstrap locality and per-peer remote flags cannot safely classify that traffic. Sending a public `Host` also fails unless explicitly allowed, but rewriting `Host` is not a supported security solution.

A reverse proxy may remain strictly loopback-only with no external ingress. Keep the original exact `Host`/port and `Origin` without rewrites; use the backend's actual protocol. This is not a remote-access deployment. For remote access in this version, use the direct private-address TLS listener above after local setup. TLS termination at an external reverse proxy, trusted-proxy/source-provenance configuration and public hosting are not implemented. Proxy examples that rewrite headers or advertise the loopback service externally are deliberately omitted because they would invalidate the safety gate.

## Password and session storage

Only a random 32-byte salt and PBKDF2-HMAC-SHA256 hash (600,000 iterations), administrator ID and feature flags are persisted in the authentication SQLite database. Newly created auth files use owner-only mode. Runtime `data/` and SQLite files are ignored by version control; treat backups as sensitive. Plaintext passwords, CSRF tokens and cookies are never logged or stored in that database. A readable authentication database still permits offline password guessing, so protect backups and the host.

Session tokens have 256 bits of random entropy, are stored only as token hashes in bounded server memory, expire after one hour, and are bound to the actual peer address. They are lost on server restart. A password change invalidates every previous session and issues a new session. Cookies use `HttpOnly`, `SameSite=Strict`, `Path=/` and, with TLS, `Secure`. Logout removes the session and clears its cookie. There is no remember-me credential storage, recovery backdoor or plaintext password command-line flag.

For a new auth database, an operator can supply a strong initial password through `DASHBOARD_INITIAL_PASSWORD` or `--prompt-initial-password`. Prefer the hidden interactive prompt rather than commands that may enter shell history. These options still require a local first-use password change; they never unlock LAN during bootstrap. Existing databases keep their established credential. Environment variables are not a secret vault; process environment and inherited-shell access are host risks. No real credentials are generated or committed by tests.

Login/password verification failures are limited to eight attempts per five minutes for each actual peer, with a bounded 512-peer in-memory table. Sessions are bounded to 128. These limits reduce simple guessing, not distributed denial of service. No forwarded header changes the rate-limit identity.

## Auth and settings API

All authenticated mutations require one exact same-origin `Origin` header, JSON content type and one `X-CSRF-Token` header with the current session token. There is no CORS access allowance. Request headers are validated before routing. Browser reads and same-origin calls do not bypass login.

- `GET /api/auth/status`: sign-in/setup status, current session CSRF token only when authenticated, local-peer boolean and settings; loopback can read it before and after setup
- `POST /api/auth/login`: `{ "username": "admin", "password": "..." }`; creates an HttpOnly session cookie
- `POST /api/auth/change-password`: `{ "current_password": "...", "new_password": "..." }`; authenticated, CSRF-protected; local only during initial setup
- `POST /api/auth/logout`: `{}`; revokes the session and clears its cookie
- `GET /api/settings`: authenticated settings object
- `POST /api/settings`: one or more boolean `lan_access`, `remote_view`, `remote_control` fields; authenticated administrator, CSRF-protected

Status returns `authenticated`, `username`, `must_change_password`, `csrf_token`, `local_peer` and `settings`. Settings returns `configured`, `effective`, `bootstrap_required`, `listener_lan` and `tls`. No hash, salt, password, TLS private key or internal file path is returned.

Ordinary JSON bodies stay capped at 16 KiB. Referenced PNG/JPEG uploads use a separate 3 MiB JSON-body cap and a 2 MiB decoded image cap. Only dataset validation/import bodies receive a 256 KiB outer-body cap to permit JSON escaping; supplied JSONL text remains bounded to 128 KiB by the workspace parser. Dataset preparation operates on supplied text, never arbitrary paths. Read-only diagnostics may invoke only an already-installed GPU utility with fixed arguments. Run exports identify real versus synthetic configuration/metrics/logs/checkpoint metadata, with safe generated filenames and formula-safe CSV cells; real checkpoint ZIP downloads are authenticated and omit private optimizer state.

## Verification scope

The automated unit tests use temporary databases, explicitly synthetic credentials and loopback HTTP only. Socket-peer guard tests inject documentation-only external peer addresses without creating LAN listeners. TLS cookie attributes are checked without generating real certificates. Separate deployment integration checks on 2026-10-04 exercised authenticated private-IP HTTPS from a second computer. See [validation](validation.md) for certificate handling and scope. Unit tests do not modify host firewall or router settings. The injected `auth=False` constructor is only for legacy unit fixtures; it cannot be used on a LAN listener and has no runtime CLI option.

## Ubuntu and WSL2 host notes

On native Ubuntu, the machine's private address, trusted certificate and local firewall rules still determine whether another LAN device can reach the listener. This code does not discover the correct address or open any firewall rule.

WSL2 normally uses NAT, where Windows localhost access does not by itself prove LAN access. Supported Windows11 configurations can offer mirrored networking, but Windows/Hyper-V firewall behavior and WSL version still matter. Review [Microsoft's official WSL networking guide](https://learn.microsoft.com/en-us/windows/wsl/networking) before choosing a deployment. Do not blindly relay an externally reachable port to the loopback listener, since that destroys socket-peer locality. Network-mode, firewall, certificate and router changes are separate user-approved setup actions, not automatically performed by the application. The recorded deployment used native Ubuntu; WSL2 networking remains unverified.
