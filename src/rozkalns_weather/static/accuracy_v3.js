const accuracyV3Api = async (url) => {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
};

let accuracyRequestSequence = 0;

function providerClassCards(items) {
  const ordered = [...items].sort((a, b) => `${a.role}:${a.model_name}`.localeCompare(`${b.role}:${b.model_name}`));
  return ordered.map((provider) => `
    <div class="provider">
      <strong>${provider.model_name}</strong>
      <small>${provider.role}<br>${provider.model_provider}<br>${provider.transport}</small>
    </div>
  `).join("");
}

function leadBucketRows(providers) {
  return Object.entries(providers).flatMap(([provider, value]) =>
    Object.entries(value.by_lead_bucket || {}).map(([bucket, metrics]) => ({ provider, bucket, ...metrics }))
  );
}

function renderLeadBuckets(providers) {
  const target = document.querySelector("#leadBucketTable");
  if (!target) return;
  const rows = leadBucketRows(providers);
  if (!rows.length) {
    target.textContent = "Lead-bucket sample vēl nav pieejami.";
    return;
  }
  target.innerHTML = `<table><thead><tr><th>Model</th><th>Lead</th><th>n</th><th>MAE</th><th>Bias</th><th>Confidence</th></tr></thead><tbody>${rows.map((row) => `
    <tr><td>${row.provider}</td><td>${row.bucket}</td><td>${row.n}</td>
    <td>${row.mae == null ? "—" : Number(row.mae).toFixed(2)}</td>
    <td>${row.bias == null ? "—" : Number(row.bias).toFixed(2)}</td>
    <td>${row.sample_confidence || "—"}</td></tr>`).join("")}</tbody></table>`;
}

function renderCalibration(data) {
  const target = document.querySelector("#calibrationTable");
  if (!target) return;
  const entries = Object.entries(data.probability || {});
  if (!entries.length) {
    target.textContent = "Genuine member-derived probability dati vēl nav pieejami.";
    return;
  }
  target.innerHTML = `<table><thead><tr><th>Model</th><th>n</th><th>Brier</th><th>Threshold</th><th>Calibration bins</th></tr></thead><tbody>${entries.map(([provider, metrics]) => `
    <tr><td>${provider}</td><td>${metrics.n}</td>
    <td>${metrics.brier_score == null ? "—" : Number(metrics.brier_score).toFixed(3)}</td>
    <td>${Number(data.occurrence_threshold_mm_per_hour).toFixed(2)} mm/h</td>
    <td>${(metrics.reliability_bins || []).filter((row) => row.n > 0).length}</td></tr>`).join("")}</tbody></table>`;
}

function drilldownRows(slices) {
  return (slices || []).flatMap((slice) => (slice.cohorts || []).flatMap((cohort) => cohort.metrics || []));
}

function missingnessLabel(value) {
  if (!value) return "—";
  return `${value.missing_n}/${value.expected_n} missing · ${value.excluded_non_common_n || 0} excluded`;
}

function renderDeterministicDrilldown(data) {
  const target = document.querySelector("#drilldownDeterministic");
  if (!target) return;
  const rows = drilldownRows(data?.deterministic?.slices);
  if (!rows.length) {
    target.textContent = "No deterministic common-sample cohort is available for this month.";
    return;
  }
  target.innerHTML = `<table><thead><tr><th>Model</th><th>Version</th><th>Cycle</th><th>Lead</th><th>Variable</th><th>Month</th><th>n</th><th>Missingness</th><th>Sufficiency</th><th>MAE</th><th>RMSE</th><th>Bias</th><th>Events</th></tr></thead><tbody>${rows.map((row) => `
    <tr><td>${row.provider}</td><td>${row.model_version}</td><td>${row.init_cycle_utc}</td><td>${row.lead_bucket}</td>
    <td>${row.variable}</td><td>${row.month}</td><td>${row.n}</td><td>${missingnessLabel(row.missingness)}</td>
    <td>${row.sample_sufficiency_state}</td><td>${row.mae == null ? "—" : Number(row.mae).toFixed(2)}</td>
    <td>${row.rmse == null ? "—" : Number(row.rmse).toFixed(2)}</td><td>${row.bias == null ? "—" : Number(row.bias).toFixed(2)}</td>
    <td>${(row.event_summaries || []).map((event) => `${event.event_id}: n=${event.n}`).join(" · ") || "—"}</td></tr>`).join("")}</tbody></table>`;
}

function renderEnsembleDrilldown(data) {
  const target = document.querySelector("#drilldownEnsemble");
  if (!target) return;
  const rows = drilldownRows(data?.ensemble?.slices);
  if (!rows.length) {
    target.textContent = "No genuine member common-sample cohort is available for this month.";
    return;
  }
  target.innerHTML = `<table><thead><tr><th>Model</th><th>Version</th><th>Cycle</th><th>Lead</th><th>Variable</th><th>n</th><th>Missingness</th><th>Sufficiency</th><th>CRPS</th><th>WIS</th><th>Brier</th></tr></thead><tbody>${rows.map((row) => `
    <tr><td>${row.provider}</td><td>${row.model_version}</td><td>${row.init_cycle_utc}</td><td>${row.lead_bucket}</td><td>${row.variable}</td>
    <td>${row.n}</td><td>${missingnessLabel(row.missingness)}</td><td>${row.sample_sufficiency_state}</td>
    <td>${row.mean_crps == null ? "—" : Number(row.mean_crps).toFixed(3)}</td>
    <td>${row.mean_wis == null ? "—" : Number(row.mean_wis).toFixed(3)}</td>
    <td>${row.brier_score == null ? "—" : Number(row.brier_score).toFixed(3)}</td></tr>`).join("")}</tbody></table>`;
}

function ensureAccuracyState() {
  let state = document.querySelector("#accuracyState");
  if (state) return state;
  const table = document.querySelector("#accuracyTable");
  state = document.createElement("div");
  state.id = "accuracyState";
  state.className = "surface-state state-loading";
  state.setAttribute("role", "status");
  state.setAttribute("aria-live", "polite");
  state.setAttribute("aria-atomic", "true");
  table?.parentNode?.insertBefore(state, table);
  return state;
}

function setAccuracyState(kind, text, { alert = false } = {}) {
  const state = ensureAccuracyState();
  ["loading", "fresh", "stale", "error", "offline"].forEach((item) => state.classList.remove(`state-${item}`));
  state.classList.add(`state-${kind}`);
  state.setAttribute("role", alert ? "alert" : "status");
  state.setAttribute("aria-live", alert ? "assertive" : "polite");
  state.textContent = text;
}

function humanTruthReasons(truthQuality) {
  const labels = {
    TEMPERATURE_COVERAGE_GAP: "Temperature truth has coverage gaps.",
    TEMPERATURE_TRUTH_MISSING: "Temperature truth is missing.",
    TEMPERATURE_COVERAGE_INSUFFICIENT: "Temperature truth coverage is insufficient.",
    NO_OBSERVATIONS: "No benchmark observations are available for this window.",
  };
  const codes = truthQuality?.reason_codes || [];
  return codes.length ? codes.map((code) => labels[code] || "Truth-quality checks are incomplete.").join(" ") : "Truth-quality checks are incomplete.";
}

function accuracyPanelTitle(text) {
  const panel = document.querySelector("#accuracyTable")?.closest(".panel");
  const title = panel?.querySelector(".panel-title");
  if (title) title.textContent = text;
}

function renderAccuracyTable(summary) {
  const target = document.querySelector("#accuracyTable");
  const rows = summary.common_sample_slices || [];
  if (!target) return;
  if (!rows.length) {
    target.textContent = "Not enough common station samples exist between at least two providers in one lead-bucket/model-version cohort.";
    return;
  }
  target.innerHTML = `<table><thead><tr><th>Model</th><th>Version</th><th>Lead</th><th>n</th><th>Missing</th><th>Sufficiency</th><th>MAE</th><th>RMSE</th><th>Bias</th><th>p10–p90</th></tr></thead><tbody>${rows.map((metrics) => {
    const missing = metrics.missingness || {};
    return `<tr><td>${metrics.provider}</td><td>${metrics.model_version || "unknown"}</td><td>${metrics.lead_bucket}</td><td>${metrics.n}</td>
    <td>${missing.missing_n ?? "—"}/${missing.expected_n ?? "—"}</td><td>${metrics.sample_sufficiency_state}</td>
    <td>${metrics.mae?.toFixed(2) ?? "—"}</td><td>${metrics.rmse?.toFixed(2) ?? "—"}</td><td>${metrics.bias?.toFixed(2) ?? "—"}</td>
    <td>${metrics.p10_p90_coverage == null ? "—" : `${(metrics.p10_p90_coverage * 100).toFixed(0)}% (${metrics.coverage_n})`}</td></tr>`;
  }).join("")}</tbody></table>`;
}

async function refreshAccuracyV3(days = 30) {
  const sequence = ++accuracyRequestSequence;
  const accuracyTable = document.querySelector("#accuracyTable");
  const lead = document.querySelector("#leadBucketTable");
  const calibration = document.querySelector("#calibrationTable");
  if (accuracyTable) {
    accuracyTable.setAttribute("aria-busy", "true");
    accuracyTable.textContent = `Loading ${days}-day verification evidence…`;
  }
  if (lead) lead.textContent = "";
  if (calibration) calibration.textContent = "";
  setAccuracyState("loading", `LOADING · ${days}-day verification evidence is being fetched.`);
  accuracyPanelTitle("DWD CDC 05480 verification evidence · loading");

  try {
    const [providers, summary, precipitation] = await Promise.all([
      accuracyV3Api("/api/providers"),
      accuracyV3Api(`/api/verification/summary?days=${days}`),
      accuracyV3Api(`/api/verification/precipitation?days=${days}`),
    ]);
    if (sequence !== accuracyRequestSequence) return;

    const classes = document.querySelector("#providerClasses");
    if (classes) classes.innerHTML = providerClassCards(providers.providers || []);
    renderAccuracyTable(summary);
    renderCalibration(precipitation);

    if (summary.verification_ready === true) {
      accuracyPanelTitle("DWD CDC 05480 station benchmark · deterministic");
      setAccuracyState("fresh", `READY · ${days}-day truth quality passed; benchmark metrics are current for this response.`);
      renderLeadBuckets(summary.providers || {});
    } else {
      accuracyPanelTitle("DWD CDC 05480 verification evidence · preliminary");
      setAccuracyState("stale", `NOT READY · INCOMPLETE TRUTH — ${humanTruthReasons(summary.truth_quality)} Metrics below are preliminary descriptive evidence, not a clean benchmark.`);
      if (lead) lead.textContent = "Lead-bucket aggregates are hidden until verification_ready=true.";
    }
  } catch (error) {
    if (sequence !== accuracyRequestSequence) return;
    accuracyPanelTitle("DWD CDC 05480 verification evidence · unavailable");
    if (accuracyTable) accuracyTable.textContent = "Accuracy evidence unavailable.";
    if (lead) lead.textContent = "";
    if (calibration) calibration.textContent = "";
    setAccuracyState("error", `ERROR · ${days}-day verification request failed: ${error}`, { alert: true });
  } finally {
    if (sequence === accuracyRequestSequence) accuracyTable?.removeAttribute("aria-busy");
  }
}

globalThis.accuracy = refreshAccuracyV3;

async function refreshDrilldown(month) {
  const deterministic = document.querySelector("#drilldownDeterministic");
  const ensemble = document.querySelector("#drilldownEnsemble");
  try {
    const data = await accuracyV3Api(`/api/verification/drilldown?month=${encodeURIComponent(month)}`);
    renderDeterministicDrilldown(data);
    renderEnsembleDrilldown(data);
  } catch (_error) {
    if (deterministic) deterministic.textContent = "Verification drilldown unavailable.";
    if (ensemble) ensemble.textContent = "Verification drilldown unavailable.";
  }
}

const drilldownMonth = document.querySelector("#drilldownMonth");
if (drilldownMonth) drilldownMonth.value = new Date().toISOString().slice(0, 7);
document.querySelector("#loadDrilldown")?.addEventListener("click", () => {
  if (drilldownMonth?.value) refreshDrilldown(drilldownMonth.value);
});
