/* Model Snapshot compares provider values only at one exact shared valid time. */
(function (root) {
  "use strict";

  const PROVIDERS = ["weathernext3", "icon_d2", "ecmwf_ifs", "ecmwf_aifs"];
  const LABELS = Object.freeze({
    weathernext3: "WeatherNext 3",
    icon_d2: "ICON-D2",
    ecmwf_ifs: "ECMWF IFS",
    ecmwf_aifs: "AIFS",
  });
  const GRACE_MS = 30 * 60 * 1000;

  function finiteNumber(value) {
    const parsed = Number(value);
    return value == null || value === "" || !Number.isFinite(parsed) ? null : parsed;
  }

  function validTimeMs(row) {
    const stamp = Date.parse(row?.valid_time_utc || "");
    return Number.isFinite(stamp) ? stamp : null;
  }

  function selectCommonValidTime(seriesByProvider, nowMs = Date.now()) {
    const cutoff = nowMs - GRACE_MS;
    const candidates = new Map();

    Object.entries(seriesByProvider || {}).forEach(([provider, rows]) => {
      (Array.isArray(rows) ? rows : []).forEach((row) => {
        const stamp = validTimeMs(row);
        if (stamp == null || stamp < cutoff || finiteNumber(row?.value) == null) return;
        if (!candidates.has(stamp)) candidates.set(stamp, new Map());
        const providerRows = candidates.get(stamp);
        if (!providerRows.has(provider)) providerRows.set(provider, row);
      });
    });

    const shared = [...candidates.entries()]
      .filter(([, rows]) => rows.size >= 2)
      .sort(([left], [right]) => left - right)[0];

    if (!shared) return { valid_time_utc: null, rows: {} };
    const [stamp, rows] = shared;
    return {
      valid_time_utc: new Date(stamp).toISOString(),
      rows: Object.fromEntries(rows),
    };
  }

  function runAgeHours(row, nowMs = Date.now()) {
    const init = Date.parse(row?.init_time_utc || "");
    return Number.isFinite(init) ? Math.max(0, (nowMs - init) / 3600000) : null;
  }

  function installBrowserOverride() {
    if (typeof root.renderModelSnapshot !== "function"
        || typeof root.canonicalProviderRows !== "function"
        || typeof root.futureRows !== "function"
        || typeof root.qs !== "function") return false;

    root.renderModelSnapshot = function renderAlignedModelSnapshot(rows, healthMap) {
      const seriesByProvider = Object.fromEntries(PROVIDERS.map((provider) => [
        provider,
        root.futureRows(root.canonicalProviderRows(rows, provider), 48),
      ]));
      const match = selectCommonValidTime(seriesByProvider);
      const comparisonTime = match.valid_time_utc;

      const cards = PROVIDERS.map((provider) => {
        const row = match.rows[provider] || null;
        const health = healthMap?.[provider] || {};
        const pending = provider === "weathernext3"
          && [health.ingest_state, health.state, health.freshness_state].includes("access_pending");
        const value = row && finiteNumber(row.value) != null ? `${finiteNumber(row.value).toFixed(1)}°` : "—";
        let note;
        if (pending) {
          note = "No genuine data · pending";
        } else if (!comparisonTime) {
          note = "No common valid time · excluded";
        } else if (!row) {
          note = `No value at ${root.formatLocalTime(comparisonTime)} · excluded`;
        } else {
          const age = runAgeHours(row);
          const init = row.init_time_utc ? ` · init ${root.formatLocalTime(row.init_time_utc)}` : "";
          const runAge = age == null ? "" : ` · run ${Math.round(age)}h old`;
          note = `${root.formatLocalTime(row.valid_time_utc)} · ${row.statistic || "deterministic"}${init}${runAge}`;
        }
        return `<div class="model-card${provider === "weathernext3" ? " primary" : ""}"><small>${root.escapeHtml(LABELS[provider])}</small><strong>${root.escapeHtml(value)}</strong><span>${root.escapeHtml(note)}</span></div>`;
      });

      root.qs("#modelSnapshot").innerHTML = cards.join("");
      const values = Object.values(match.rows)
        .map((row) => finiteNumber(row?.value))
        .filter((value) => value != null);
      root.qs("#modelSpread").textContent = comparisonTime && values.length >= 2
        ? `Model spread ${(Math.max(...values) - Math.min(...values)).toFixed(1)}° at ${root.formatLocalTime(comparisonTime)} · descriptive provider disagreement`
        : "Model spread — · no common valid time across at least two genuine model values";
    };
    return true;
  }

  const api = { finiteNumber, selectCommonValidTime, runAgeHours };
  root.RozkalnsModelComparison = api;
  if (typeof window !== "undefined") installBrowserOverride();
  if (typeof module !== "undefined") module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
