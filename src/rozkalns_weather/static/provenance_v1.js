(() => {
  const PROVIDER_ORDER = ["weathernext3", "icon_d2", "ecmwf_ifs", "ecmwf_aifs", "dwd_mosmix_l"];
  const STAT_ORDER = ["deterministic", "mean", "p50"];
  let refreshToken = 0;

  function el(id) { return document.getElementById(id); }
  function safe(value) {
    return String(value ?? "—")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }
  function statisticRank(value) {
    const rank = STAT_ORDER.indexOf(value);
    return rank === -1 ? 999 : rank;
  }
  function canonicalRows(rows, provider) {
    const selected = new Map();
    rows.filter((row) => row.provider === provider && STAT_ORDER.includes(row.statistic)).forEach((row) => {
      const previous = selected.get(row.valid_time_utc);
      if (!previous || statisticRank(row.statistic) < statisticRank(previous.statistic)) {
        selected.set(row.valid_time_utc, row);
      }
    });
    return [...selected.values()].sort((a, b) => String(a.valid_time_utc).localeCompare(String(b.valid_time_utc)));
  }
  function futureRows(rows, count = 8) {
    if (!rows.length) return [];
    const cutoff = Date.now() - 30 * 60 * 1000;
    const upcoming = rows.filter((row) => {
      const date = new Date(row.valid_time_utc);
      return !Number.isNaN(date.valueOf()) && date.getTime() >= cutoff;
    });
    return (upcoming.length ? upcoming : rows.slice(-count)).slice(0, count);
  }
  function chooseProvider(tempRows, precipRows) {
    const temperatureProviders = new Set(tempRows.map((row) => row.provider));
    const precipitationProviders = new Set(precipRows.map((row) => row.provider));
    return PROVIDER_ORDER.find((provider) => temperatureProviders.has(provider) && precipitationProviders.has(provider))
      || PROVIDER_ORDER.find((provider) => temperatureProviders.has(provider))
      || [...temperatureProviders][0]
      || null;
  }
  function detailsHost() {
    const strip = el("hourlyStrip");
    if (!strip) return null;
    let details = el("valueProvenanceDrilldown");
    if (!details) {
      details = document.createElement("details");
      details.id = "valueProvenanceDrilldown";
      details.className = "provenance-drilldown";
      details.innerHTML = '<summary>Value provenance</summary><div id="valueProvenanceBody" class="muted">Select an hourly value to inspect its provider snapshot and verification lineage.</div>';
      strip.insertAdjacentElement("afterend", details);
    }
    return details;
  }
  function traceMarkup(label, trace) {
    if (!trace || trace.state !== "PASS") {
      const reasons = trace?.reason_codes?.join(", ") || "TRACE_UNAVAILABLE";
      return `<section><strong>${safe(label)}</strong><div>BLOCKED · ${safe(reasons)}</div></section>`;
    }
    const source = trace.source || {};
    const snapshot = trace.snapshot || {};
    const time = trace.time || {};
    const normalized = trace.normalized_value || {};
    return `<section class="provenance-trace-block">
      <strong>${safe(label)} · ${safe(source.provider)}</strong>
      <div>Model: ${safe(source.model_name)} · version ${safe(source.model_version)}</div>
      <div>Snapshot: <code>${safe(snapshot.id)}</code> · revision ${safe(snapshot.revision)}</div>
      <div>Init: ${safe(time.init_time_utc)}</div>
      <div>Valid: ${safe(time.valid_time_utc)} · lead ${safe(time.lead_hours)} h</div>
      <div>Retrieved: ${safe(time.retrieved_at_utc)}</div>
      <div>Value identity: ${safe(normalized.variable)} · ${safe(normalized.statistic)} · ${safe(normalized.unit)}</div>
      <div>Source surface: ${safe(source.source_surface)}</div>
    </section>`;
  }
  function verificationMarkup(trace) {
    if (!trace || trace.state !== "PASS") {
      const reasons = trace?.reason_codes?.join(", ") || "TRACE_UNAVAILABLE";
      return `<section><strong>Verification lineage</strong><div>BLOCKED · ${safe(reasons)}</div></section>`;
    }
    return `<section class="provenance-trace-block">
      <strong>Verification lineage · DWD CDC 05480</strong>
      <div>Truth trace: <code>${safe(trace.truth_trace_identity_sha256)}</code></div>
      <div>Truth source: ${safe(trace.truth?.source?.provider)} · station ${safe(trace.truth?.source?.station_id)}</div>
      <div>Observed: ${safe(trace.truth?.time?.observed_at_utc)}</div>
      <div>Metric: ${safe(trace.metric_identity?.name)} · ${safe(trace.metric_identity?.comparison_mode)}</div>
      <div>Trace identity: <code>${safe(trace.trace_identity_sha256)}</code></div>
    </section>`;
  }
  async function verificationTrace(locationId, row) {
    if (locationId !== "station_05480" || !row) return null;
    const params = new URLSearchParams({
      provider: row.provider,
      valid_time_utc: row.valid_time_utc,
      variable: row.variable,
      statistic: row.statistic,
      metric_name: "absolute_error",
    });
    try {
      const response = await fetch(`/api/provenance/verification?${params}`, { cache: "no-store" });
      return await response.json();
    } catch (_error) {
      return { state: "BLOCKED", reason_codes: ["TRACE_REQUEST_FAILED"] };
    }
  }
  async function showTrace(locationId, temperatureRow, precipitationRow) {
    const details = detailsHost();
    const body = el("valueProvenanceBody");
    if (!details || !body || !temperatureRow) return;
    body.innerHTML = traceMarkup("Temperature", temperatureRow.provenance_trace)
      + (precipitationRow ? traceMarkup("Precipitation amount", precipitationRow.provenance_trace) : "");
    details.open = true;
    const verification = await verificationTrace(locationId, temperatureRow);
    if (verification) body.insertAdjacentHTML("beforeend", verificationMarkup(verification));
  }
  async function refreshDrilldown() {
    const token = ++refreshToken;
    const strip = el("hourlyStrip");
    if (!strip) return;
    const locationId = el("forecastLocation")?.value || "home";
    const query = `hours=48&location_id=${encodeURIComponent(locationId)}`;
    try {
      const [temperatureResponse, precipitationResponse] = await Promise.all([
        fetch(`/api/hourly?${query}&variable=temperature_2m`, { cache: "no-store" }),
        fetch(`/api/hourly?${query}&variable=precipitation_1h`, { cache: "no-store" }),
      ]);
      if (!temperatureResponse.ok || !precipitationResponse.ok) return;
      const [temperature, precipitation] = await Promise.all([temperatureResponse.json(), precipitationResponse.json()]);
      if (token !== refreshToken) return;
      const tempRows = temperature.series || [];
      const precipRows = precipitation.series || [];
      const provider = chooseProvider(tempRows, precipRows);
      if (!provider) return;
      const tempSeries = futureRows(canonicalRows(tempRows, provider), 8);
      const precipByTime = new Map(canonicalRows(precipRows, provider).map((row) => [row.valid_time_utc, row]));
      const cards = [...strip.querySelectorAll(".hour-card")];
      cards.forEach((card, index) => {
        const row = tempSeries[index];
        if (!row) return;
        card.tabIndex = 0;
        card.setAttribute("role", "button");
        card.setAttribute("aria-label", `${card.textContent.trim()} · inspect value provenance`);
        const activate = () => showTrace(locationId, row, precipByTime.get(row.valid_time_utc));
        card.onclick = activate;
        card.onkeydown = (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            activate();
          }
        };
      });
      const details = detailsHost();
      if (details && tempSeries[0]) {
        details.querySelector("summary").textContent = `Value provenance · ${tempSeries[0].model_name || provider}`;
      }
    } catch (_error) {
      // Provenance drilldown is additive; failure must not hide the forecast itself.
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    detailsHost();
    const strip = el("hourlyStrip");
    if (strip) new MutationObserver(() => refreshDrilldown()).observe(strip, { childList: true });
    el("forecastLocation")?.addEventListener("change", () => refreshDrilldown());
    el("refreshOverview")?.addEventListener("click", () => setTimeout(refreshDrilldown, 0));
    refreshDrilldown();
  });
})();
