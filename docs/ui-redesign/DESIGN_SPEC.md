# Design specification

Tokens are defined once in static/style.css. Charcoal `#171A1E` explorer, warm `#F3F2EE` work surface, `#A84414` primary action, `#FFB580` selection/focus on dark surfaces, text `#202329`/`#F1F2F4`. Self-hosted Pretendard UI, restricted Space Grotesk English display, and JetBrains Mono technical typography; see [typography rules and evidence](typography/README.md). No runtime CDN or new application dependencies. Corners 4–6px, base body 14px / 1.55, metadata 10–13px, code/logs 13px / 1.6.

Desktop 1440: 248px explorer, flexible selected-run curve, 300px inspector. At 1366 the same widths remain; at ≤1200: 220/280px; at 1024: 210/260px. Run header carries base model/method/source/status/optimizer step and allowed actions. The existing SVG renderer uses raw step positions, breaks missing metric paths, preserves missing eval as unavailable, and distinguishes blue solid train from green dashed eval with point marks. No smoothing/ETA is invented.

Inspector contains explicitly sourced server-wide telemetry and an immutable run config snapshot; hide/show uses a button with aria-expanded. Console has Logs/Checkpoints/Evaluation/Configuration and a keyboard-operable height range (160–400px). User log scrolling is retained across polling. Below 760px, Run/Inspector/Console controls select one surface and mobile selects provide view/run access.

Builder uses a single persistent form split into six fieldsets. Navigation does not replace inputs. Only reviewed configuration with a fresh dry-run can launch; Real GPU additionally needs matching split/model/capability and a successful current preflight. Estimates carry planning labels. Server resource limits remain authoritative.

Contrast, keyboard, responsive, errors and actual captures are recorded in VALIDATION.md; this is not an accessibility certification.
