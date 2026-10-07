# Rollback

## Typography only (2026-10-07)

Current typography implementation commit: `30016dd`. To undo only the font work while preserving the earlier Workbench/theme/explorer, review later dependencies and use `git revert 30016dd`. Operational data and server configuration require no changes. Keep unrelated user commits.

Typography evidence can remain historical. If removing the matching documentation delivery too, identify that commit with `git log --oneline -- docs/ui-redesign/typography docs/ui-redesign/DESIGN_SPEC.md`, revert that exact delivery commit first, then `30016dd`. This also restores the prior DESIGN_SPEC text. Do not use the full-Workbench rollback below for a typography-only rollback.

## Full original Workbench rollback

A later white/dark mode feature depends on this workbench. Revert `2bf09470dc00e14c990e90bb1527aa770666d4b2` first if it is present; see theme/README.md.

Use a clean working tree and review any later dependent changes before reverting. Preserve unrelated user commits. UI changes are these two local commits:

```bash
git revert adac4de56e4653837fbfc81a7e3e401a49c0898c
git revert 2942818061014b01aacbf9f3790091316174f08b
```

This restores the app/test/preview/tool files through ordinary reversible Git commits. The documentation/evidence delivery commit can remain as historical evidence. To remove it too, identify its SHA with `git log --oneline -- docs/ui-redesign README.md` and revert that exact documentation commit before the two source commits. Do not reset/clean working data or change production services.

No DB migration, model/checkpoint/dataset modification, worker configuration or authentication change was performed. Old `forge.language` and `forge.selectedRun` values were read normally, with no migration or backup needed. The new optional `forge.inspectorHidden` UI key is ignored by the prior app and may be left in browser storage. Drafts are memory-only and disappear on reload. No theme key existed or was replaced. Rollback requires no account/token/operational-data action.
