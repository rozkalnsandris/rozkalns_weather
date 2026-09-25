(() => {
  "use strict";

  const NOW_WINDOW_MS = 45 * 60 * 1000;

  function parseTimestamp(value) {
    const stamp = new Date(value).getTime();
    return Number.isFinite(stamp) ? stamp : null;
  }

  function selectNowIndex(rows, nowMs = Date.now()) {
    let best = null;
    (rows || []).forEach((row, index) => {
      const stamp = parseTimestamp(row?.valid_time_utc);
      if (stamp == null) return;
      const delta = stamp - nowMs;
      const distance = Math.abs(delta);
      if (distance > NOW_WINDOW_MS) return;
      const future = delta >= 0;
      const candidate = { index, stamp, distance, future };
      if (
        !best
        || candidate.distance < best.distance
        || (candidate.distance === best.distance && candidate.future && !best.future)
        || (candidate.distance === best.distance && candidate.future === best.future && candidate.stamp < best.stamp)
      ) {
        best = candidate;
      }
    });
    return best ? best.index : -1;
  }

  function berlinLocalTime(value) {
    if (typeof window.formatLocalTime === "function") return window.formatLocalTime(value);
    const stamp = parseTimestamp(value);
    if (stamp == null) return "—";
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/Berlin",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(stamp));
  }

  function restoreSurface(id) {
    const element = document.querySelector(`#${id}`);
    if (!element) return;
    element.hidden = false;
    element.removeAttribute("aria-hidden");
    delete element.dataset.dedupHidden;
  }

  function surfaceSignature(element) {
    if (!element) return null;
    return `${element.dataset.state || ""}\n${element.textContent.trim()}`;
  }

  function dedupeSurfacePair(primaryId, duplicateId) {
    const primary = document.querySelector(`#${primaryId}`);
    const duplicate = document.querySelector(`#${duplicateId}`);
    if (!primary || !duplicate) return false;

    if (surfaceSignature(primary) !== surfaceSignature(duplicate)) {
      restoreSurface(duplicateId);
      return false;
    }

    duplicate.hidden = true;
    duplicate.dataset.dedupHidden = "true";
    duplicate.setAttribute("aria-hidden", "true");
    duplicate.removeAttribute("role");
    duplicate.removeAttribute("aria-live");
    duplicate.removeAttribute("aria-atomic");
    return true;
  }

  const baseSetSurfaceState = window.setSurfaceState;
  if (typeof baseSetSurfaceState === "function") {
    window.setSurfaceState = function setSurfaceStateWithDedupReset(id, ...args) {
      restoreSurface(id);
      return baseSetSurfaceState(id, ...args);
    };
  }

  const baseRenderConsumerHourly = window.renderConsumerHourly;
  if (typeof baseRenderConsumerHourly === "function") {
    window.renderConsumerHourly = function renderConsumerHourlySingleNow(tempResult, precipResult, healthMap) {
      baseRenderConsumerHourly(tempResult, precipResult, healthMap);

      const tempRows = tempResult?.payload?.series || [];
      const precipRows = precipResult?.payload?.series || [];
      const provider = typeof window.chooseProvider === "function"
        ? window.chooseProvider(tempRows, precipRows)
        : null;
      const canonical = provider && typeof window.canonicalProviderRows === "function"
        ? window.canonicalProviderRows(tempRows, provider)
        : [];
      const tempSeries = typeof window.futureRows === "function"
        ? window.futureRows(canonical, 8)
        : canonical.slice(0, 8);
      const nowIndex = selectNowIndex(tempSeries, Date.now());
      const cards = [...document.querySelectorAll("#hourlyStrip .hour-card")];

      cards.forEach((card, index) => {
        const row = tempSeries[index];
        if (!row) return;
        const isNow = index === nowIndex;
        card.classList.toggle("now", isNow);
        card.dataset.validTimeUtc = row.valid_time_utc;
        const label = card.querySelector(".hour-label");
        if (label) label.textContent = isNow ? "Now" : berlinLocalTime(row.valid_time_utc);
      });

      dedupeSurfacePair("overviewTempState", "overviewPrecipState");
    };
  }

  const baseGlobalNetworkState = window.globalNetworkState;
  if (typeof baseGlobalNetworkState === "function") {
    window.globalNetworkState = function globalNetworkStateWithoutDuplicateProviderSummary(healthState) {
      baseGlobalNetworkState(healthState);
      dedupeSurfacePair("providerState", "networkState");
    };
  }

  window.RozkalnsConsumerUI = Object.freeze({
    NOW_WINDOW_MS,
    selectNowIndex,
    dedupeSurfacePair,
  });
})();
