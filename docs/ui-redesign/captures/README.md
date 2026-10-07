# Browser capture reproduction

Run from repository root:

```bash
python3 tools/ui_fixture_server.py --port 18765 --audit-file /private/tmp/forge-ui-network.json
```

Use the printed disposable admin credential to sign into the loopback fixture. In Codex CUA, bind an IAB tab and browser, then import the authored ES module (do not eval its source):

```javascript
var harness = await import('file:///ABSOLUTE_REPOSITORY/tools/capture_workbench.cua.js');
await harness.captureForgeWorkbench({tab, browser,
  directory:'/ABSOLUTE_REPOSITORY/docs/ui-redesign/captures',
  commitSha:'ACTUAL_CHECKED_OUT_SOURCE_SHA'});
```

The suite uses documented CUA locators/scroll/viewport/screenshot APIs; it requires no installed Playwright package. Only validation/dry-run and denied preflight writes occur. Never substitute an operational server URL. The watermark must exist on every screenshot. Stop only this owned server via Ctrl-C, reset viewport and close the owned tab.

Original screenshot format is JPEG. Delivery PNGs were converted with `sips -s format png original.jpg --out original.png`, without editing pixels or values. browser-report.json names original JPG files; CAPTURE_MANIFEST.csv maps to delivered PNGs. Original JPEGs are removed to avoid duplicate binary evidence. Before timestamps/SHA are preserved; after timestamps/SHA come from the final successful browser report. Before and after use forge-workbench-v1 and the same selected run for desktop/mobile comparisons. No real dataset, private path, image, token or actual performance claim is in captures. Fonts are system-local; transient toast completion is awaited.

Direct review: all 19 PNGs opened. Long inspector/config/evaluation/catalog panels use intentional internal scroll; model readiness screenshot is intentionally scrolled to Access/Installed and disabled download control. The mobile review screenshot shows the recipe and sticky navigation with vertical scrolling. Native browser zoom is not established by these screenshots.
