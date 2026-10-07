# Select/text input height correction

Source: `8c80ac47a4b7f9965621ca0f48e910ca55dcdbec` (2026-10-07). Shared text fields and selects are explicitly 40px high; select native appearance is replaced with a theme-aware chevron while retaining the real semantic select and native option picker. Equal 18px line height and border-box sizing keep text aligned. Mobile navigation retains its existing compact 36px controls; Models filter controls remain 40px. Forced-colors mode retains native select chrome for system contrast.

Actual IAB before measurement was already 40px, but native select line-height/appearance differed from text fields. The correction makes the visible control deterministic across browser styles. After measurement: all seven Models text/filter controls are 40px in white/dark, at 1440×900 and 390×844. LLM selection enables the format control normally. Two PNG screenshots directly reviewed; they are synthetic UI fixtures. See browser-report.json and CAPTURE_MANIFEST.csv. `python3 tools/build_preview.py` and `git diff --check` passed. No new tests or backend changes for this CSS correction; earlier regression logs remain historical.

Owned isolated fixture used port 18766 to avoid the user's 18765 server. Execution/download/control was never invoked; only disposable sign-in, filter reads and appearance changes. Owned fixture stopped, browser tab closed and viewport reset. User services were untouched.

Rollback this correction with `git revert 8c80ac47a4b7f9965621ca0f48e910ca55dcdbec` after reviewing later dependent changes. No storage migration or operating data change.
