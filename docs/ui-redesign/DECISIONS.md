# Decisions

- Retain standard-library Python and plain JavaScript; no framework/chart-library migration, lockfile or new runtime dependency.
- Keep existing selectors, api() authentication/CSRF handling, payloads, enum and server lifecycle. No backend production file changes.
- Move run rows into the explorer and retain keyboard/focus restoration. Filters restrict the explorer without silently changing the selected run. Selecting a row from a preparation view opens that run.
- Preserve forge.language and forge.selectedRun. New forge.inspectorHidden is a separate visual preference. Drafts and validation signatures stay only in memory; page reload clears draft and resets view to Workbench, while restoring selected run/language. No new URL/history state and no pre-existing theme preference mechanism was found.
- Keep real-source fixture labels distinct from live measurement. Fixture-only watermark is injected by the isolated server/offline generator, never production index.html.
- Keep data/config dry-run warnings unchanged, including its assumed model-size heuristic; GPU preflight is a separate action. Neither implies training success.
- Keep the legacy hidden demo form/handlers for compatibility with existing DOM tests; New experiment always opens the six-step builder. The normal and OOM demo scenarios are available in its Launch step.
- AutoTrain/W&B patterns described by the supplied pack informed flow and metric context; no third-party assets, telemetry or service integration added. External reference re-read status is in VALIDATION.md.
