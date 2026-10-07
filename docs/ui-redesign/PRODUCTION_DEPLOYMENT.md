# Workbench production deployment · 2026-10-07

## Delivered source

- [PR #2](https://github.com/Phjrab/forge-finetune-dashboard/pull/2) merged into `main`.
- Deployed commit: `d9a4656a5bee38cc9903e8caf5c4b680709423d2`.
- Previous deployment: `8d62c26ab48cf7f80379298887e2e7971b162fbf`.
- Deployment: 2026-10-07 19:19 KST, clean production `main`, ordinary fast-forward.
- Backend files unchanged. Existing `local-finetune-dashboard` service stayed active with the same PID and start timestamp; no restart occurred.
- Only the existing UI/code checkout was updated. Training, account, model, dataset and checkpoint files were not edited. Verification did not start, pause, cancel or retry training, or download models.

## Verification

- All 14 public static assets matched committed SHA-256 values over HTTPS, including four official WOFF2 files with `font/woff2` responses. See [asset evidence](production-verification.json).
- TLS certificate verification used the existing trusted project certificate; verification was not disabled.
- Existing CSP retained `font-src 'self'`.
- Unauthenticated status request: 401. Own-session logout without CSRF: 403; valid logout: 200.
- Private data and path traversal remained blocked. Authenticated read-only status succeeded, and active/queued/paused state counts were unchanged.
- [Push CI](https://github.com/Phjrab/forge-finetune-dashboard/actions/runs/37604345729) and [PR CI](https://github.com/Phjrab/forge-finetune-dashboard/actions/runs/37604842897) passed backend/script and native architecture checks.
- Local implementation validation: 137 Python tests passed, 3 optional-runtime skips; final server suite 20 passed; frontend 57 passed; i18n and offline preview passed. These were completed before delivery; deployment verification did not rerun GPU tests.
- Matched fixture before/after browser captures and glyph evidence remain in [typography](typography/README.md), [theme](theme/README.md), and [Workbench captures](captures/README.md).

### Production browser limitation

The in-app browser refused the production HTTPS URL with `net::ERR_CERT_AUTHORITY_INVALID`. The browser warning was not bypassed and trust settings were not changed. Production browser visual validation is **not complete**; no production screenshot is claimed. The authenticated HTTPS and asset checks above passed with certificate verification enabled. An operator can inspect the deployment using a browser that already trusts the server certificate.

## Backup and rollback

The production user's protected directory contains the original static archive:

```text
$HOME/.local/state/forge-ui-backups/20261007T101913Z-8d62c26/
  static-before.tar.gz
  backup.sha256
  before-commit.txt
  fast-forward.txt
```

Directory/files were created under `umask 077`, outside the publicly served static root. `sha256sum -c backup.sha256` passed after deployment. The archive contains only the old static UI, no operational data or credentials.

For a normal full-release rollback, preserve unrelated work and review later dependencies, then create an ordinary revert commit on a clean branch:

```bash
git revert -m 1 d9a4656a5bee38cc9903e8caf5c4b680709423d2
```

Review and deliver that rollback through the usual Git process, then fast-forward the production checkout to the approved rollback commit. This restores the prior UI without resetting operational data. Because this release changed no backend files, the UI rollback requires no service restart. Verify HTTPS assets, auth/CSRF, and unchanged service PID again. Typography-only rollback guidance remains in [ROLLBACK.md](ROLLBACK.md).

This deployment record is committed and pushed separately on the feature branch; its documentation commit does not change the deployed source SHA above.
