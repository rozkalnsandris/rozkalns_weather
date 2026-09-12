const accuracyV3Api = async (url) => {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
};

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
  const rows = [];
  Object.entries(providers).forEach(([provider, value]) => {
    Object.entries(value.by_lead_bucket || {}).forEach(([bucket, metrics]) => {
      rows.push({provider, bucket, ...metrics});
    });
  });
  return rows;
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
    <tr>
      <td>${row.provider}</td>
      <td>${row.bucket}</td>
      <td>${row.n}</td>
      <td>${row.mae == null ? "—" : Number(row.mae).toFixed(2)}</td>
      <td>${row.bias == null ? "—" : Number(row.bias).toFixed(2)}</td>
      <td>${row.sample_confidence || "—"}</td>
    </tr>
  `).join("")}</tbody></table>`;
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
    <tr>
      <td>${provider}</td>
      <td>${metrics.n}</td>
      <td>${metrics.brier_score == null ? "—" : Number(metrics.brier_score).toFixed(3)}</td>
      <td>${Number(data.occurrence_threshold_mm_per_hour).toFixed(2)} mm/h</td>
      <td>${(metrics.reliability_bins || []).filter((row) => row.n > 0).length}</td>
    </tr>
  `).join("")}</tbody></table>`;
}

function drilldownRows(slices) {
  return (slices || []).flatMap((slice) =>
    (slice.cohorts || []).flatMap((cohort) => cohort.metrics || [])
  );
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
    <tr>
      <td>${row.provider}</td><td>${row.model_version}</td><td>${row.init_cycle_utc}</td><td>${row.lead_bucket}</td>
      <td>${row.variable}</td><td>${row.month}</td><td>${row.n}</td><td>${missingnessLabel(row.missingness)}</td>
      <td>${row.sample_sufficiency_state}</td>
      <td>${row.mae == null ? "—" : Number(row.mae).toFixed(2)}</td>
      <td>${row.rmse == null ? "—" : Number(row.rmse).toFixed(2)}</td>
      <td>${row.bias == null ? "—" : Number(row.bias).toFixed(2)}</td>
      <td>${(row.event_summaries || []).map((event) => `${event.event_id}: n=${event.n}`).join(" · ") || "—"}</td>
    </tr>`).join("")}</tbody></table>`;
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
    <tr>
      <td>${row.provider}</td><td>${row.model_version}</td><td>${row.init_cycle_utc}</td><td>${row.lead_bucket}</td><td>${row.variable}</td>
      <td>${row.n}</td><td>${missingnessLabel(row.missingness)}</td><td>${row.sample_sufficiency_state}</td>
      <td>${row.mean_crps == null ? "—" : Number(row.mean_crps).toFixed(3)}</td>
      <td>${row.mean_wis == null ? "—" : Number(row.mean_wis).toFixed(3)}</td>
      <td>${row.brier_score == null ? "—" : Number(row.brier_score).toFixed(3)}</td>
    </tr>`).join("")}</tbody></table>`;
}

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

async function refreshAccuracyV3(days = 30) {
  try {
    const [providers, summary, precipitation] = await Promise.all([
      accuracyV3Api("/api/providers"),
      accuracyV3Api(`/api/verification/summary?days=${days}`),
      accuracyV3Api(`/api/verification/precipitation?days=${days}`),
    ]);
    const classes = document.querySelector("#providerClasses");
    if (classes) classes.innerHTML = providerClassCards(providers.providers || []);
    renderLeadBuckets(summary.providers || {});
    renderCalibration(precipitation);
  } catch (error) {
    const lead = document.querySelector("#leadBucketTable");
    if (lead) lead.textContent = "Accuracy v3 metadata unavailable";
  }
}

document.querySelectorAll("[data-days]").forEach((button) => {
  button.addEventListener("click", () => refreshAccuracyV3(Number(button.dataset.days)));
});

const drilldownMonth = document.querySelector("#drilldownMonth");
if (drilldownMonth) drilldownMonth.value = new Date().toISOString().slice(0, 7);
document.querySelector("#loadDrilldown")?.addEventListener("click", () => {
  if (drilldownMonth?.value) refreshDrilldown(drilldownMonth.value);
});

refreshAccuracyV3(30);
