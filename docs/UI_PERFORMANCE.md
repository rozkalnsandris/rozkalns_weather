# UI performance evidence

This document defines the source-level performance evidence used for umbrella issue #237, T6/S6 audit item 28.

## What the CI lab proves

`tests/test_ui_performance_lab_browser.py` runs the real checked-in `index.html` and frontend modules in system Chromium against deterministic local API fixtures. It does not contact production, private WeatherNext, Cloudflare, the RPi5 runtime or any external provider.

The controlled mobile profile uses a 412x892 viewport, a bounded synthetic network profile, cacheable static assets and deterministic API latency. The test records or gates:

- time to first usable forecast (TTFF), defined as navigation start to the first rendered hourly forecast with a non-loading temperature surface state;
- Largest Contentful Paint (LCP) when the browser exposes the corresponding PerformanceObserver entry type;
- cumulative layout shift (CLS), excluding shifts with recent user input;
- the maximum Event Timing duration observed after a real browser interaction when supported;
- a warm reload with normal network conditions;
- a reload where the APIs return a controlled failure after a successful load, proving cached forecast fallback remains usable and is visibly marked `stale` / not current.

The browser test is intentionally network-independent. The local fixture contains no real provider values and is not forecast evidence.

## Guardrails

The controlled lab currently fails on these broad regression bounds:

- cold/constrained TTFF > 3500 ms;
- warm TTFF > 2000 ms;
- cached-failure TTFF > 2000 ms;
- CLS > 0.1;
- synthetic LCP > 4000 ms when LCP is supported;
- observed Event Timing duration > 200 ms when Event Timing is supported.

These bounds are regression guards for the deterministic CI environment. They are not claimed as real-user percentiles.

## Field-vs-lab semantics

The product target from the 2026-09-26 UI audit remains p75 LCP <= 2.5 s, INP <= 200 ms and CLS <= 0.1 for real visits. A private low-traffic dashboard may not have sufficient CrUX population, so CI cannot manufacture a valid field p75.

The Event Timing value in CI is therefore a synthetic interaction-duration proxy, not a statement that field INP has been measured. Real-user or production measurements must be labelled separately with their population, period and collection method.

## Existing complementary evidence

The performance lab does not duplicate functional lifecycle tests already present in the repository:

- independent observation/forecast loading and stale-location protection are covered by the browser regressions added through #270/#271;
- request timeout and superseded-request cancellation are covered by #272;
- clean install, offline reopen and atomic service-worker update lifecycle are covered by #273;
- warning/background refresh semantics remain separate functional evidence and are not converted into invented performance data.

Together, those tests plus this controlled lab provide a reproducible T6/S6 source baseline. Production/RPi5 timing, battery use, physical-device profiling and real-user p75 remain separate read-only or LIVE evidence activities as applicable.
