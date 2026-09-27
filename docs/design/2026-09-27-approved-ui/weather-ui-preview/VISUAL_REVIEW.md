# Visual review — 2026-09-27

Reviewed the rendered local HTTP prototype in the Codex built-in browser after the owner supplied a working server URL. No file:// or Brave fallback was used.

## Findings and changes

- Dortmund is the display location, as requested by the owner. Werl remains explicitly identified as DWD observation/verification reference; measurements are not relabeled as Dortmund station observations.
- Shared navigation glyphs were too small. Increased to 20 px with 24 px line height, retaining text labels and the existing active-page state. Reset nested span backgrounds/padding to avoid unintended duplicate button surfaces.
- Dark radar demo precipitation shapes blended into the background. Increased contrast of the illustrative shapes and roads, and matched demo legend colors. This is not a production radar palette or data decoder.

## Scope of observed evidence

- Overview: both themes at 412 CSS-pixel working width; Dortmund heading confirmed in both rendered accessibility trees after cache refresh.
- Models: both themes at 384 px before the location-label correction; no visible text clipping in the captured initial viewport.
- Radar, Accuracy and Status: both themes at 412 px inspected visually.
- Corrected Radar and shared navigation: both themes at 384 px inspected visually after the changes.
- Screenshots were inspected in-session; no persisted screenshot artifact is included in this PR. Data and map remain explicitly marked as demo.

This is a partial visual review, not full V3 acceptance: all scroll states, keyboard/screen-reader behavior, error/loading states, 200% text/zoom and the complete viewport matrix remain to be verified. Source syntax checks and previous CI do not establish these outcomes. Production UI and backend data are unchanged.
