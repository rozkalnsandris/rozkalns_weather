# Mobile prototype validation — 2026-09-28

Part of #237. Local HTTP prototype inspected in the Codex built-in browser, using the accepted design with the navigation fix from #254. This is prototype evidence, not production acceptance or physical-device emulation.

## Observed results

| Check | Scope | Result |
| --- | --- | --- |
| Bottom content and navigation clearance | All five views, both themes, 384 px, reduced height | Final text and controls reachable above navigation |
| Expanded disclosures | All seven disclosures, both themes, 384 px | Enter opens them; full text reachable by scrolling |
| Expanded bottom views | All five views, both themes, 412 px, reduced height | No observed text clipping or permanently obscured content |
| Forward Tab traversal | All five views, both themes, 384 px, default state | Controls, disclosures and five navigation links reached; focus exits frame |
| Disabled Overview control | Both themes | 14 dienas skipped; Atjaunot leads to navigation |
| Navigation activation | Models → Radar and Overview → Models | Both theme frames switch; shell focus restored to destination button |
| Radar keyboard adjustment | Both themes | ArrowRight advances slider; dark-frame accessible value verified as 14.15 · prognoze · demonstrācija |

Models' expanded source text initially extends below the viewport; scrolling exposes the complete paragraph. This is normal scrolling, not permanently hidden content.

Forward sequences: Models has three metric buttons, time select, disclosure and navigation; Radar has latest, slider, previous/play/next, disclosure and navigation; Accuracy has three metrics, lead-time select, two disclosures and navigation; Status has scenario select, two disclosures and navigation. Overview traverses source disclosure, retry and navigation. These checks do not cover every alternative data state or every interaction.

Screenshots were inspected in-session; no persisted screenshot artifacts are included. No additional defect was identified in this bounded pass.

## Automated 200% text-enlargement follow-up

PR #276 adds a real-shell Chromium regression proof at the Galaxy A55 `412×892` viewport using the browser engine's `Emulation.setEmulatedOSTextScale` with `scale=2.0`. The test traverses Overview, Models, Radar, Accuracy and Status and fails if the document gains horizontal overflow or the fixed bottom navigation or its controls clip their text.

This is an automated OS text-scale/reflow proof. It is not a claim that browser-chrome `Ctrl+Plus` zoom was exercised, and it does not replace a screen-reader or physical-device pass.

## Remaining acceptance work

- Manual browser-chrome 200% `Ctrl+Plus` zoom remains unproven because the earlier built-in browser shortcut did not change its zoom state; a narrow viewport or CSS scaling is still not a substitute for that manual browser-zoom check.
- Screen-reader and physical Galaxy A55/S25+ validation.
- Complete loading/error/stale/filter interaction matrix and production integration checks.

The accepted design remains the implementation basis. Full V3 and #237 acceptance stay open. Production application, providers, runtime and deployment are unchanged.
