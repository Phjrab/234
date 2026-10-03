# Security scope

This is a single-user, loopback-only synthetic demo. There is no authentication system and it must not be reverse-proxied or exposed to a LAN/the Internet. It does not provide a safe public training service.

Implemented: loopback bind allowlist, Host/port validation against DNS rebinding, same-origin browser POST enforcement, JSON-only bounded bodies, finite-number/config validation, hidden/traversal path rejection, safe static containment, HTML escaping of user-controlled labels, restrictive content/security headers, no arbitrary command execution or real model/data access.

Not implemented: accounts/authentication, permission system, production hardening, remote worker transport, real file uploads, signed events, secure model downloads, secret vault, checkpoint artifact downloads. Malicious processes under the same local account can call the API; loopback is not an identity boundary.

Only synthetic fixtures are committed. Runtime SQLite state is ignored. Avoid including personal experiment labels or private paths if exporting logs/screenshots in the future. Report issues privately to the repository maintainer rather than including secrets in public issues.
