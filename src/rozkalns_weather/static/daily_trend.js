/* Daily API aggregates stay provider-attributed; missing values never become zero. */
(function (root) {
  "use strict";
  const number = value => typeof value === "number" && Number.isFinite(value) ? value : null;
  const escape = value => String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
  const dayTime = date => typeof date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(date) && Number.isFinite(Date.parse(date)) && new Date(date).toISOString().slice(0, 10) === date ? Date.parse(date) : null;
  function select(rows, provider) {
    return (Array.isArray(rows) ? rows : []).filter(row => row.provider === provider && dayTime(row.date) !== null).slice().sort((a, b) => a.date.localeCompare(b.date)).slice(0, 14);
  }
  function geometry(rows, field, y) {
    let previous = null;
    return rows.map((row, index) => {
      const value = number(row[field]);
      if (value === null) { previous = null; return ""; }
      const time = dayTime(row.date);
      const connected = previous !== null && time - previous === 86400000;
      previous = time;
      return `${connected ? "L" : "M"}${index * 48 + 24},${y(value).toFixed(2)}`;
    }).join(" ");
  }
  const amount = row => { const value = number(row.precipitation_total_mm); return value !== null && value >= 0 ? value : null; };
  const temperature = value => number(value) === null ? "—" : `${Math.round(value)}°`;
  const rainLabel = row => amount(row) === null ? "—" : `${amount(row).toFixed(1)} mm`;
  function render(target, rows, provider) {
    const available = select(rows, provider);
    let limit = 7;
    let chosen = available[0]?.date;
    const dateLabel = date => new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(date));
    function draw() {
      const shown = available.slice(0, limit);
      if (!shown.length) { target.textContent = "No daily forecast data available."; return; }
      if (!shown.some(row => row.date === chosen)) chosen = shown[0].date;
      const values = shown.flatMap(row => [number(row.temperature_min_c), number(row.temperature_max_c)]).filter(value => value !== null);
      const low = values.length ? Math.min(...values) : 0;
      const high = values.length ? Math.max(...values) : 1;
      // One shared temperature scale: labels above maximum and below minimum avoid overlap.
      const y = value => 155 - (value - low) / Math.max(1, high - low) * 80;
      const width = shown.length * 48;
      const selected = shown.find(row => row.date === chosen);
      target.innerHTML = `<div class="trend-toolbar"><span>${shown.length} available day${shown.length === 1 ? "" : "s"}</span><div class="trend-horizon" role="group" aria-label="Forecast horizon"><button type="button" data-days="7" aria-pressed="${limit === 7}">7 days</button><button type="button" data-days="14" aria-pressed="${limit === 14}" ${available.length <= 7 ? "disabled" : ""}>14 days</button></div></div>
        <div class="trend-legend"><span class="trend-max">● Max °C</span><span class="trend-min">┄ Min °C</span><span>Rain mm</span></div>
        <div class="trend-scroll" role="region" aria-label="Daily forecast; scroll for more days" tabindex="0"><div class="trend-plot" style="width:max(100%, ${width}px)"><svg class="trend-lines" viewBox="0 0 ${width} 240" preserveAspectRatio="none" aria-hidden="true"><path class="trend-max-line" d="${geometry(shown, "temperature_max_c", y)}"/><path class="trend-min-line" d="${geometry(shown, "temperature_min_c", y)}"/></svg>
        ${shown.map((row, index) => {
          const weekend = [0, 6].includes(new Date(row.date).getUTCDay());
          const label = `${dateLabel(row.date)}: maximum ${temperature(row.temperature_max_c)}, minimum ${temperature(row.temperature_min_c)}, rain ${rainLabel(row)}`;
          return `<button type="button" class="trend-day${weekend ? " weekend" : ""}" data-date="${row.date}" aria-pressed="${row.date === chosen}" aria-label="${escape(label)}" style="left:${index / shown.length * 100}%;width:${100 / shown.length}%"><span class="trend-weekday">${dateLabel(row.date).split(",")[0].split(" ")[0]}</span><span class="trend-date">${row.date.slice(8)}.${row.date.slice(5, 7)}</span>
            ${[["max", row.temperature_max_c, -25], ["min", row.temperature_min_c, 9]].map(([kind, value, offset]) => number(value) === null ? `<span class="trend-${kind} trend-value" style="top:${kind === "max" ? 55 : 165}px">—</span>` : `<span class="trend-dot trend-${kind}" style="top:${y(value) - 3}px"></span><span class="trend-${kind} trend-value" style="top:${y(value) + offset}px">${temperature(value)}</span>`).join("")}
            <span class="trend-rain${amount(row) > 0 ? " wet" : ""}"><span aria-hidden="true">${amount(row) > 0 ? '<svg viewBox="0 0 16 22" aria-hidden="true"><path d="M8 1C6 6 1 10 1 15a7 7 0 0 0 14 0C15 10 10 6 8 1Z"/></svg>' : "·"}</span>${rainLabel(row)}</span></button>`;
        }).join("")}</div></div>
        <p class="trend-hint">Tap a day for values. Swipe for more days. Missing values: —.</p>
        <div class="trend-selected" role="status"><strong>${escape(dateLabel(selected.date))}</strong><span>Max ${temperature(selected.temperature_max_c)} · Min ${temperature(selected.temperature_min_c)} · Rain ${rainLabel(selected)}</span></div>
        <details class="trend-table"><summary>Daily values and source</summary><p>${escape(provider)} · API daily aggregates. Precipitation is an amount, not probability.</p><div class="table-wrap"><table><caption>Available daily forecast values · ${escape(provider)}</caption><thead><tr><th scope="col">Date</th><th scope="col">Max °C</th><th scope="col">Min °C</th><th scope="col">Rain mm</th><th scope="col">Init UTC / quality</th><th scope="col">Retrieved UTC</th></tr></thead><tbody>${shown.map(row => `<tr><th scope="row">${escape(row.date)}</th><td>${temperature(row.temperature_max_c)}</td><td>${temperature(row.temperature_min_c)}</td><td>${rainLabel(row)}</td><td>${escape(row.init_time_utc || "—")} / ${escape(row.init_time_quality || "—")}</td><td>${escape(row.retrieved_at_utc || "—")}</td></tr>`).join("")}</tbody></table></div></details>`;
      target.dataset.provider = provider;
      target.querySelectorAll("[data-days]").forEach(button => button.addEventListener("click", () => { limit = Number(button.dataset.days); draw(); target.querySelector(`[data-days="${limit}"]`).focus(); }));
      target.querySelectorAll("[data-date]").forEach(button => button.addEventListener("click", () => {
        const scroll = target.querySelector(".trend-scroll").scrollLeft;
        chosen = button.dataset.date; draw();
        target.querySelector(`[data-date="${chosen}"]`).focus({ preventScroll: true });
        target.querySelector(".trend-scroll").scrollLeft = scroll;
      }));
    }
    draw();
  }
  const api = { number, select, geometry, amount, render };
  root.RozkalnsDailyTrend = api;
  if (typeof module !== "undefined") module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
