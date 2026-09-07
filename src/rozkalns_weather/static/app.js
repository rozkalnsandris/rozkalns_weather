const qs = (selector) => document.querySelector(selector);
const qsa = (selector) => [...document.querySelectorAll(selector)];

const api = async (url) => {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
};

qsa(".tabs button").forEach((button) => {
  button.onclick = () => {
    qsa(".tabs button").forEach((item) => item.classList.remove("active"));
    qsa(".view").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    qs(`#${button.dataset.view}`).classList.add("active");
  };
});

function providersCard(items) {
  return items.map((provider) => `
    <div class="provider">
      <strong>${provider.model_name}</strong>
      <small>
        ${provider.state}
        ${provider.last_init_time_utc ? `<br>init ${provider.last_init_time_utc}` : ""}
        ${provider.last_success_at_utc ? `<br>success ${provider.last_success_at_utc}` : ""}
      </small>
    </div>
  `).join("");
}

function currentCards(items) {
  return items.map((item) => `
    <div class="provider">
      <strong>${item.variable}</strong>
      <small>${Number(item.value).toFixed(1)} ${item.unit}<br>${item.observed_at_utc}</small>
    </div>
  `).join("");
}

function dailyCards(items) {
  return items.slice(0, 40).map((item) => `
    <div class="provider">
      <strong>${item.date} · ${item.model_name}</strong>
      <small>
        ${item.temperature_min_c == null ? "—" : Number(item.temperature_min_c).toFixed(1)}
        …
        ${item.temperature_max_c == null ? "—" : Number(item.temperature_max_c).toFixed(1)} °C
        <br>${Number(item.precipitation_total_mm || 0).toFixed(1)} mm
        <br>init ${item.init_time_utc || "—"}
      </small>
    </div>
  `).join("");
}

function temperatureChart(series) {
  if (!series.length) return null;
  const primary = series.filter((item) => ["deterministic", "mean", "p50"].includes(item.statistic));
  const uncertaintyRows = series.filter((item) => item.provider === "weathernext3" && ["p10", "p90"].includes(item.statistic));
  const grouped = {};
  primary.forEach((item) => (grouped[item.provider] ??= []).push(item));
  const uncertaintyByTime = {};
  uncertaintyRows.forEach((item) => {
    (uncertaintyByTime[item.valid_time_utc] ??= {})[item.statistic] = Number(item.value);
  });
  const uncertainty = Object.entries(uncertaintyByTime)
    .filter(([, values]) => values.p10 != null && values.p90 != null)
    .sort(([a], [b]) => a.localeCompare(b));
  const allValues = primary.map((item) => Number(item.value));
  uncertainty.forEach(([, values]) => allValues.push(values.p10, values.p90));
  if (!allValues.length) return null;
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const range = Math.max(1, max - min);
  const times = [...new Set([...primary.map((item) => item.valid_time_utc), ...uncertainty.map(([time]) => time)])].sort();
  const x = (time) => 30 + (times.indexOf(time) / Math.max(1, times.length - 1)) * 570;
  const y = (value) => 190 - ((value - min) / range) * 150;
  let band = "";
  if (uncertainty.length >= 2) {
    const upper = uncertainty.map(([time, values]) => `${x(time).toFixed(1)},${y(values.p90).toFixed(1)}`);
    const lower = [...uncertainty].reverse().map(([time, values]) => `${x(time).toFixed(1)},${y(values.p10).toFixed(1)}`);
    band = `<polygon points="${[...upper, ...lower].join(" ")}" fill="rgba(56,189,248,.16)" stroke="rgba(56,189,248,.45)" stroke-width="1"/>`;
  }
  const paths = Object.entries(grouped).map(([name, rows], index) => {
    rows.sort((a, b) => a.valid_time_utc.localeCompare(b.valid_time_utc));
    const points = rows.map((row, rowIndex) => `${rowIndex ? "L" : "M"}${x(row.valid_time_utc).toFixed(1)},${y(Number(row.value)).toFixed(1)}`).join(" ");
    const hue = (index * 67) % 360;
    return `<path d="${points}" fill="none" stroke="hsl(${hue} 75% 65%)" stroke-width="2"/><text x="35" y="${18 + index * 14}" fill="hsl(${hue} 75% 70%)" font-size="10">${name}</text>`;
  }).join("");
  return `<svg viewBox="0 0 620 210" role="img" aria-label="48 hour temperature comparison with WeatherNext uncertainty band"><line x1="30" y1="190" x2="600" y2="190" stroke="#334155"/>${band}${paths}</svg>`;
}

function precipitationChart(series) {
  const rows = series.filter((item) => ["deterministic", "mean", "p50"].includes(item.statistic));
  if (!rows.length) return null;
  const providers = [...new Set(rows.map((item) => item.provider))];
  const times = [...new Set(rows.map((item) => item.valid_time_utc))].sort();
  const max = Math.max(0.1, ...rows.map((item) => Number(item.value)));
  const slot = 570 / Math.max(1, times.length);
  const providerWidth = Math.max(1.5, Math.min(8, (slot * 0.8) / Math.max(1, providers.length)));
  const bars = rows.map((row) => {
    const providerIndex = providers.indexOf(row.provider);
    const timeIndex = times.indexOf(row.valid_time_utc);
    const baseX = 30 + timeIndex * slot + slot * 0.1;
    const x = baseX + providerIndex * providerWidth;
    const height = Math.max(0, (Number(row.value) / max) * 145);
    const y = 180 - height;
    const hue = (providerIndex * 67) % 360;
    return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${providerWidth.toFixed(1)}" height="${height.toFixed(1)}" fill="hsl(${hue} 70% 60%)"><title>${row.provider} ${row.valid_time_utc}: ${Number(row.value).toFixed(2)} mm</title></rect>`;
  }).join("");
  const legend = providers.map((provider, index) => `<text x="35" y="${16 + index * 13}" fill="hsl(${(index * 67) % 360} 75% 70%)" font-size="10">${provider}</text>`).join("");
  return `<svg viewBox="0 0 620 195" role="img" aria-label="48 hour precipitation comparison"><line x1="30" y1="180" x2="600" y2="180" stroke="#334155"/>${legend}${bars}</svg>`;
}

function uncertaintySummary(series) {
  const rows = series.filter((item) => item.provider === "weathernext3" && ["p10", "p90"].includes(item.statistic));
  if (!rows.length) return "WeatherNext uncertainty vēl nav pieejama.";
  const byTime = {};
  rows.forEach((item) => (byTime[item.valid_time_utc] ??= {})[item.statistic] = Number(item.value));
  const complete = Object.entries(byTime).filter(([, values]) => values.p10 != null && values.p90 != null).slice(0, 12);
  if (!complete.length) return "WeatherNext p10–p90 pāri vēl nav pilni.";
  return complete.map(([time, values]) => `${time}: ${values.p10.toFixed(1)}…${values.p90.toFixed(1)} °C`).join("<br>");
}

async function refresh() {
  try {
    const health = await api("/api/health/providers");
    qs("#statusBadge").textContent = health.home.configured ? "home configured" : "home config pending";
    qs("#providerGrid").innerHTML = providersCard(health.providers);
    const weatherNext = health.providers.find((item) => item.id === "weathernext3");
    qs("#wnState").textContent = weatherNext?.state || "unknown";
    const current = await api("/api/current");
    if (current.observations.length) qs("#currentTruth").innerHTML = currentCards(current.observations);
    const [temperature, precipitation, daily] = await Promise.all([
      api("/api/hourly?hours=48&variable=temperature_2m"),
      api("/api/hourly?hours=48&variable=precipitation_1h"),
      api("/api/daily?days=10"),
    ]);
    const tempSvg = temperatureChart(temperature.series);
    if (tempSvg) {
      qs("#overviewChart").classList.remove("empty");
      qs("#modelsChart").classList.remove("empty");
      qs("#overviewChart").innerHTML = tempSvg;
      qs("#modelsChart").innerHTML = tempSvg;
    }
    const precipSvg = precipitationChart(precipitation.series);
    if (precipSvg) {
      qs("#overviewPrecip").classList.remove("empty");
      qs("#modelsPrecip").classList.remove("empty");
      qs("#overviewPrecip").innerHTML = precipSvg;
      qs("#modelsPrecip").innerHTML = precipSvg;
    }
    qs("#uncertainty").innerHTML = uncertaintySummary(temperature.series);
    if (daily.days_by_provider.length) qs("#dailyGrid").innerHTML = dailyCards(daily.days_by_provider);
  } catch (error) {
    qs("#statusBadge").textContent = "API unavailable";
  }
}

async function accuracy(days = 30) {
  try {
    const data = await api(`/api/verification/summary?days=${days}`);
    const entries = Object.entries(data.providers);
    if (!entries.length) {
      qs("#accuracyTable").textContent = "Vēl nav pietiekamu station forecast + observation pāru.";
      return;
    }
    qs("#accuracyTable").innerHTML = `<table><thead><tr><th>Model</th><th>n</th><th>MAE</th><th>RMSE</th><th>Bias</th><th>p10–p90</th></tr></thead><tbody>${entries.map(([provider, value]) => {
      const metrics = value.overall;
      return `<tr><td>${provider}</td><td>${metrics.n}</td><td>${metrics.mae?.toFixed(2) ?? "—"}</td><td>${metrics.rmse?.toFixed(2) ?? "—"}</td><td>${metrics.bias?.toFixed(2) ?? "—"}</td><td>${metrics.p10_p90_coverage == null ? "—" : `${(metrics.p10_p90_coverage * 100).toFixed(0)}%`}</td></tr>`;
    }).join("")}</tbody></table>`;
  } catch (error) {
    qs("#accuracyTable").textContent = "Accuracy API unavailable";
  }
}

qsa("[data-days]").forEach((button) => {
  button.onclick = () => {
    qsa("[data-days]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    accuracy(Number(button.dataset.days));
  };
});

qs("#loadWarnings").onclick = async () => {
  try { qs("#warningsOutput").textContent = JSON.stringify(await api("/api/warnings"), null, 2); }
  catch (error) { qs("#warningsOutput").textContent = "Home config vai warning provider nav pieejams."; }
};

qs("#loadRadar").onclick = async () => {
  try { qs("#radarOutput").textContent = JSON.stringify(await api("/api/radar"), null, 2); }
  catch (error) { qs("#radarOutput").textContent = "Home config vai radar provider nav pieejams."; }
};

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/static/sw.js");
refresh();
accuracy(30);
