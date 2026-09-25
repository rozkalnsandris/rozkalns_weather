(() => {
  "use strict";

  const CONDITION_CONTRACT = "weather-condition-v1";
  const FALLBACK_CONTRACT = "weather-condition-fallback-v1";
  const DAYLIGHT_FALLBACK = "timezone-hour-fallback-v1";
  const PROVIDER_PREFERENCE = ["weathernext3", "icon_d2", "ecmwf_ifs", "ecmwf_aifs", "dwd_mosmix_l"];
  const STAT_PREFERENCE = ["deterministic", "mean", "p50"];
  const DRIZZLE_MIN_MM = 0.05;
  const RAIN_MIN_MM = 0.2;
  const HEAVY_RAIN_MIN_MM = 2.0;

  const WMO = new Map([
    [0, ["clear", "Clear"]],
    [1, ["mostly_clear", "Mostly clear"]],
    [2, ["partly_cloudy", "Partly cloudy"]],
    [3, ["overcast", "Overcast"]],
    [45, ["fog", "Fog"]],
    [48, ["fog", "Rime fog"]],
    [51, ["drizzle", "Light drizzle"]],
    [53, ["drizzle", "Drizzle"]],
    [55, ["drizzle", "Dense drizzle"]],
    [56, ["freezing_precipitation", "Light freezing drizzle"]],
    [57, ["freezing_precipitation", "Dense freezing drizzle"]],
    [61, ["rain", "Light rain"]],
    [63, ["rain", "Rain"]],
    [65, ["heavy_rain", "Heavy rain"]],
    [66, ["freezing_precipitation", "Light freezing rain"]],
    [67, ["freezing_precipitation", "Heavy freezing rain"]],
    [71, ["snow", "Light snow"]],
    [73, ["snow", "Snow"]],
    [75, ["snow", "Heavy snow"]],
    [77, ["snow", "Snow grains"]],
    [80, ["rain", "Light rain showers"]],
    [81, ["rain", "Rain showers"]],
    [82, ["heavy_rain", "Heavy rain showers"]],
    [85, ["snow", "Light snow showers"]],
    [86, ["snow", "Heavy snow showers"]],
    [95, ["thunderstorm", "Thunderstorm"]],
    [96, ["thunderstorm_hail", "Thunderstorm with hail"]],
    [97, ["thunderstorm", "Heavy thunderstorm"]],
    [99, ["thunderstorm_hail", "Heavy thunderstorm with hail"]],
  ]);

  function escapeAttr(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function number(value) {
    if (value == null || value === "") return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function conditionFromWmo(value) {
    const numeric = number(value);
    if (numeric == null || !Number.isInteger(numeric) || !WMO.has(numeric)) {
      return {
        condition: "unknown",
        label: "Unknown conditions",
        weatherCode: numeric,
        source: numeric == null ? "invalid_weather_code" : "unsupported_weather_code",
      };
    }
    const [condition, label] = WMO.get(numeric);
    return { condition, label, weatherCode: numeric, source: "wmo_weather_code" };
  }

  function fallbackCondition(precipitationMm, cloudCoverPercent) {
    const precip = number(precipitationMm);
    const cloud = number(cloudCoverPercent);
    if (precip != null) {
      if (precip >= HEAVY_RAIN_MIN_MM) return { condition: "heavy_rain", label: "Heavy rain", weatherCode: null, source: FALLBACK_CONTRACT };
      if (precip >= RAIN_MIN_MM) return { condition: "rain", label: "Rain", weatherCode: null, source: FALLBACK_CONTRACT };
      if (precip >= DRIZZLE_MIN_MM) return { condition: "drizzle", label: "Drizzle", weatherCode: null, source: FALLBACK_CONTRACT };
    }
    if (cloud != null && cloud >= 0 && cloud <= 100) {
      if (cloud < 20) return { condition: "clear", label: "Clear", weatherCode: null, source: FALLBACK_CONTRACT };
      if (cloud < 45) return { condition: "mostly_clear", label: "Mostly clear", weatherCode: null, source: FALLBACK_CONTRACT };
      if (cloud < 80) return { condition: "partly_cloudy", label: "Partly cloudy", weatherCode: null, source: FALLBACK_CONTRACT };
      return { condition: "overcast", label: "Overcast", weatherCode: null, source: FALLBACK_CONTRACT };
    }
    return { condition: "unknown", label: "Unknown conditions", weatherCode: null, source: "insufficient_condition_evidence" };
  }

  function daylightState(isDay, validTimeUtc) {
    const numeric = number(isDay);
    if (isDay != null && isDay !== "") {
      if (numeric === 1) return { daylight: "day", source: "provider_is_day" };
      if (numeric === 0) return { daylight: "night", source: "provider_is_day" };
      return { daylight: "unknown", source: "invalid_provider_is_day" };
    }
    const date = validTimeUtc ? new Date(validTimeUtc) : null;
    if (date && !Number.isNaN(date.valueOf())) {
      const parts = new Intl.DateTimeFormat("en-GB", {
        timeZone: "Europe/Berlin",
        hour: "2-digit",
        hourCycle: "h23",
      }).formatToParts(date);
      const hour = Number(parts.find((part) => part.type === "hour")?.value);
      if (Number.isInteger(hour)) {
        return { daylight: hour >= 7 && hour < 19 ? "day" : "night", source: DAYLIGHT_FALLBACK };
      }
    }
    return { daylight: "unknown", source: "insufficient_daylight_evidence" };
  }

  const sun = () => `
    <g class="rw-sun" fill="none" stroke="#ffd85a" stroke-width="3.2" stroke-linecap="round">
      <circle cx="22" cy="21" r="8.2" fill="#fbbf24" stroke="#ffd85a"/>
      <path d="M22 5v5M22 32v5M6 21h5M33 21h5M10.7 9.7l3.6 3.6M29.7 28.7l3.6 3.6M33.3 9.7l-3.6 3.6M14.3 28.7l-3.6 3.6"/>
    </g>`;

  const moon = () => `
    <path class="rw-moon" d="M31 7c-7.8 2.2-12.3 10.3-9.7 17.8 2.5 7.5 10.8 11.5 18.1 8.6-4.7-.9-8.6-4.3-10-8.9C28 20 29 14.1 31 7Z"
      fill="#dcecff" stroke="#9ac8ef" stroke-width="2.2" stroke-linejoin="round"/>`;

  const cloud = (x = 15, y = 27, scale = 1) => `
    <g transform="translate(${x} ${y}) scale(${scale})">
      <path d="M5 22h29c5.2 0 9-3.2 9-7.5S39.6 7 35.2 7c-1.6 0-3.1.4-4.3 1.1C28.8 3.4 24.6 1 20 1 13.5 1 8.4 5.7 7.6 11.8 3.1 12.2 0 15.1 0 18.7 0 20.6 1.8 22 5 22Z"
        fill="#bde6ff" stroke="#7fbbe4" stroke-width="2"/>
    </g>`;

  const darkCloud = (x = 13, y = 25, scale = 1.05) => `
    <g transform="translate(${x} ${y}) scale(${scale})">
      <path d="M5 22h29c5.2 0 9-3.2 9-7.5S39.6 7 35.2 7c-1.6 0-3.1.4-4.3 1.1C28.8 3.4 24.6 1 20 1 13.5 1 8.4 5.7 7.6 11.8 3.1 12.2 0 15.1 0 18.7 0 20.6 1.8 22 5 22Z"
        fill="#91a9c2" stroke="#6f92b2" stroke-width="2"/>
    </g>`;

  const rain = (heavy = false) => `
    <g fill="none" stroke="#65c9ff" stroke-width="${heavy ? 3.4 : 2.7}" stroke-linecap="round">
      <path d="M23 51l-3 6M34 51l-3 6M45 51l-3 6"/>
      ${heavy ? '<path d="M17 50l-3 6M51 50l-3 6"/>' : ""}
    </g>`;

  const snow = () => `
    <g fill="none" stroke="#dcecff" stroke-width="2.2" stroke-linecap="round">
      <path d="M23 51v8M19 55h8M20.2 52.2l5.6 5.6M25.8 52.2l-5.6 5.6"/>
      <path d="M42 50v8M38 54h8M39.2 51.2l5.6 5.6M44.8 51.2l-5.6 5.6"/>
    </g>`;

  const astro = (daylight) => daylight === "night" ? moon() : daylight === "day" ? sun() : "";

  function iconBody(condition, daylight) {
    switch (condition) {
      case "clear":
        return astro(daylight) || `<circle cx="32" cy="32" r="11" fill="none" stroke="#9bb2c9" stroke-width="3"/>`;
      case "mostly_clear":
        return `${astro(daylight)}${cloud(25, 30, .75)}`;
      case "partly_cloudy":
        return `${astro(daylight)}${cloud(18, 28, .92)}`;
      case "overcast":
        return `${darkCloud(11, 24, 1.08)}${cloud(23, 31, .73)}`;
      case "fog":
        return `${cloud(16, 17, .9)}<g fill="none" stroke="#91a9c2" stroke-width="3" stroke-linecap="round"><path d="M13 47h38M18 54h31M14 61h24"/></g>`;
      case "drizzle":
        return `${cloud(15, 19, 1)}<g fill="#65c9ff"><circle cx="23" cy="53" r="2"/><circle cx="34" cy="57" r="2"/><circle cx="45" cy="52" r="2"/></g>`;
      case "freezing_precipitation":
        return `${darkCloud(15, 18, 1)}${rain(false)}<g fill="#dcecff"><circle cx="16" cy="56" r="2.2"/><circle cx="51" cy="56" r="2.2"/></g>`;
      case "rain":
        return `${cloud(15, 18, 1)}${rain(false)}`;
      case "heavy_rain":
        return `${darkCloud(14, 17, 1.03)}${rain(true)}`;
      case "snow":
        return `${cloud(15, 18, 1)}${snow()}`;
      case "thunderstorm":
        return `${darkCloud(14, 16, 1.05)}<path d="M35 43h9l-7 9h7L30 63l4-9h-7Z" fill="#ffd85a" stroke="#fbbf24" stroke-width="1.5" stroke-linejoin="round"/>`;
      case "thunderstorm_hail":
        return `${darkCloud(14, 15, 1.05)}<path d="M33 42h9l-7 9h7L29 62l4-9h-7Z" fill="#ffd85a" stroke="#fbbf24" stroke-width="1.5"/><g fill="#dcecff"><circle cx="18" cy="55" r="3"/><circle cx="50" cy="56" r="3"/></g>`;
      default:
        return `<g fill="none" stroke="#91a9c2" stroke-width="3" stroke-linecap="round"><circle cx="32" cy="32" r="20"/><path d="M25 25c1-5 5-8 10-8 5.5 0 9 3 9 7.5 0 7-9 7-9 13"/><path d="M35 47h.1"/></g>`;
    }
  }

  function weatherIcon(condition, daylight, { label = "Weather condition", decorative = false } = {}) {
    const accessible = decorative
      ? 'aria-hidden="true" focusable="false"'
      : `role="img" aria-label="${escapeAttr(label)}" focusable="false"`;
    return `<svg class="rw-weather-svg rw-condition-${escapeAttr(condition)} rw-${escapeAttr(daylight || "unknown")}" viewBox="0 0 64 64" ${accessible} xmlns="http://www.w3.org/2000/svg">${iconBody(condition, daylight)}</svg>`;
  }

  function injectStyles() {
    if (document.querySelector("#rozkalns-weather-condition-style")) return;
    const style = document.createElement("style");
    style.id = "rozkalns-weather-condition-style";
    style.textContent = `
      body{transition:background .35s ease}
      body.weather-theme-day{background:radial-gradient(circle at 72% -8%,rgba(255,236,162,.48),transparent 27%),linear-gradient(180deg,#1686c9 0,#0d5f99 28%,#08375c 62%,#061b2d 100%)}
      body.weather-theme-night{background:radial-gradient(circle at 75% -4%,#163a62 0,transparent 28%),linear-gradient(180deg,#071727 0,#061424 42%,#05111e 100%)}
      body.weather-theme-day .weather-hero{background:radial-gradient(circle at 74% 20%,rgba(255,235,153,.88) 0 5%,rgba(255,235,153,.19) 5.5%,transparent 14%),linear-gradient(180deg,#188ed0 0,#0d68a6 58%,#0b4773 100%);border-bottom-color:rgba(215,241,255,.34)}
      body.weather-theme-night .weather-hero{background:radial-gradient(circle at 70% 23%,rgba(236,244,255,.88) 0 5%,rgba(207,224,245,.25) 5.4%,transparent 12%),radial-gradient(circle at 73% 16%,rgba(87,137,184,.28),transparent 27%),linear-gradient(180deg,#0a223b 0,#0a1d33 55%,#08192b 100%)}
      body.weather-theme-day .weather-hero:before{opacity:.12}
      body.weather-theme-night .weather-hero:before{opacity:.7}
      body.weather-theme-day .consumer-panel,body.weather-theme-day .panel{background:linear-gradient(180deg,rgba(10,49,78,.97),rgba(7,32,54,.97));border-color:rgba(100,180,224,.38)}
      body.weather-overlay-stormy .weather-hero{box-shadow:inset 0 -80px 120px rgba(8,19,35,.3),0 18px 40px rgba(0,0,0,.24)}
      body.weather-overlay-rainy .weather-hero{box-shadow:inset 0 -70px 110px rgba(11,65,99,.22),0 18px 40px rgba(0,0,0,.24)}
      .rw-weather-svg{display:block;width:100%;height:100%;overflow:visible}
      .hero-weather-icon .rw-weather-svg{width:118px;height:118px;margin:auto;filter:drop-shadow(0 10px 14px rgba(0,0,0,.22))}
      .hour-icon .rw-weather-svg{width:30px;height:30px;margin:auto}
      .day-icon .rw-weather-svg{width:27px;height:27px;margin:auto}
      @media(max-width:520px){.hero-weather-icon .rw-weather-svg{width:104px;height:104px}}
    `;
    document.head.append(style);
  }

  function statisticRank(statistic) {
    const rank = STAT_PREFERENCE.indexOf(statistic);
    return rank === -1 ? 999 : rank;
  }

  function canonicalRows(rows, providerId) {
    const selected = new Map();
    (rows || []).filter((row) => row.provider === providerId && STAT_PREFERENCE.includes(row.statistic)).forEach((row) => {
      const existing = selected.get(row.valid_time_utc);
      if (!existing || statisticRank(row.statistic) < statisticRank(existing.statistic)) selected.set(row.valid_time_utc, row);
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
    const available = new Set((tempRows || []).map((row) => row.provider));
    const required = new Set((precipRows || []).map((row) => row.provider));
    return PROVIDER_PREFERENCE.find((provider) => available.has(provider) && required.has(provider))
      || PROVIDER_PREFERENCE.find((provider) => available.has(provider))
      || [...available][0]
      || null;
  }

  function sameRun(anchor, candidate) {
    return Boolean(candidate)
      && candidate.provider === anchor.provider
      && candidate.valid_time_utc === anchor.valid_time_utc
      && candidate.init_time_utc === anchor.init_time_utc
      && candidate.retrieved_at_utc === anchor.retrieved_at_utc;
  }

  async function loadVariable(variable, locationId) {
    const url = `/api/hourly?hours=48&variable=${encodeURIComponent(variable)}&location_id=${encodeURIComponent(locationId)}`;
    if (typeof window.apiWithFallback === "function") {
      return window.apiWithFallback(url, `hourly-${variable}-48-${locationId}`);
    }
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return { payload: await response.json(), source: "network" };
  }

  function mapRows(rows, provider) {
    return new Map(canonicalRows(rows || [], provider).map((row) => [row.valid_time_utc, row]));
  }

  let lastObservedCondition = null;
  let activeDaylight = daylightState(null, new Date().toISOString()).daylight;

  function overlayClass(condition) {
    if (["thunderstorm", "thunderstorm_hail"].includes(condition)) return "weather-overlay-stormy";
    if (["drizzle", "rain", "heavy_rain", "freezing_precipitation", "snow"].includes(condition)) return "weather-overlay-rainy";
    return "weather-overlay-calm";
  }

  function applyTheme(daylight, condition = "unknown") {
    const resolved = daylight === "day" || daylight === "night"
      ? daylight
      : daylightState(null, new Date().toISOString()).daylight;
    activeDaylight = resolved;
    document.body.classList.remove("weather-theme-day", "weather-theme-night", "weather-overlay-stormy", "weather-overlay-rainy", "weather-overlay-calm");
    document.body.classList.add(`weather-theme-${resolved}`, overlayClass(condition));
    document.documentElement.dataset.weatherDaylight = resolved;
    const themeMeta = document.querySelector('meta[name="theme-color"]');
    if (themeMeta) themeMeta.setAttribute("content", resolved === "day" ? "#1686c9" : "#061424");
    const hero = document.querySelector(".weather-hero");
    if (hero) {
      hero.classList.remove("theme-day", "theme-night");
      hero.classList.add(`theme-${resolved}`);
      hero.dataset.condition = condition;
    }
    if (lastObservedCondition) renderObservedIcon(lastObservedCondition);
  }

  function observedCondition(items) {
    const conditionItems = (items || []).filter((item) => ["precipitation_1h", "cloud_cover"].includes(item.variable) && item.observed_at_utc);
    const timestamp = conditionItems.map((item) => item.observed_at_utc).sort().at(-1);
    if (!timestamp) return { condition: "unknown", label: "Observed conditions", source: "insufficient_condition_evidence" };
    const aligned = conditionItems.filter((item) => item.observed_at_utc === timestamp);
    const precip = aligned.find((item) => item.variable === "precipitation_1h")?.value;
    const cloudCover = aligned.find((item) => item.variable === "cloud_cover")?.value;
    const result = fallbackCondition(precip, cloudCover);
    return { ...result, label: result.condition === "unknown" ? "Observed conditions" : `${result.label} observed` };
  }

  function renderObservedIcon(condition) {
    const target = document.querySelector("#heroIcon");
    if (!target) return;
    target.innerHTML = weatherIcon(condition.condition, activeDaylight, { label: condition.label, decorative: true });
    target.dataset.condition = condition.condition;
    target.dataset.daylight = activeDaylight;
  }

  const baseRenderCurrent = window.renderCurrent;
  if (typeof baseRenderCurrent === "function") {
    window.renderCurrent = function renderCurrentWithNativeCondition(result, healthMap) {
      baseRenderCurrent(result, healthMap);
      const condition = observedCondition(result?.payload?.observations || []);
      lastObservedCondition = condition;
      const text = document.querySelector("#heroCondition");
      if (text) {
        text.textContent = condition.label;
        text.removeAttribute("title");
      }
      renderObservedIcon(condition);
    };
  }

  const baseRenderConsumerHourly = window.renderConsumerHourly;
  if (typeof baseRenderConsumerHourly === "function") {
    window.renderConsumerHourly = function renderConsumerHourlyWithNativeConditions(tempResult, precipResult, healthMap) {
      baseRenderConsumerHourly(tempResult, precipResult, healthMap);

      const tempRows = tempResult?.payload?.series || [];
      const precipRows = precipResult?.payload?.series || [];
      const provider = chooseProvider(tempRows, precipRows);
      const tempSeries = provider ? futureRows(canonicalRows(tempRows, provider), 8) : [];
      const cards = [...document.querySelectorAll("#hourlyStrip .hour-card")];
      cards.forEach((card) => {
        const target = card.querySelector(".hour-icon");
        if (target) target.innerHTML = weatherIcon("unknown", "unknown", { label: "Unknown conditions" });
      });
      if (!provider || !tempSeries.length) return;

      const locationId = tempResult?.payload?.location?.id || "station_05480";
      const precipByTime = mapRows(precipRows, provider);

      Promise.allSettled([
        loadVariable("weather_code", locationId),
        loadVariable("is_day", locationId),
        loadVariable("cloud_cover", locationId),
      ]).then((results) => {
        const weatherRows = results[0].status === "fulfilled" ? results[0].value.payload.series || [] : [];
        const dayRows = results[1].status === "fulfilled" ? results[1].value.payload.series || [] : [];
        const cloudRows = results[2].status === "fulfilled" ? results[2].value.payload.series || [] : [];
        const weatherByTime = mapRows(weatherRows, provider);
        const dayByTime = mapRows(dayRows, provider);
        const cloudByTime = mapRows(cloudRows, provider);

        const rendered = tempSeries.map((anchor, index) => {
          const weatherRow = weatherByTime.get(anchor.valid_time_utc);
          const dayRow = dayByTime.get(anchor.valid_time_utc);
          const cloudRow = cloudByTime.get(anchor.valid_time_utc);
          const precipRow = precipByTime.get(anchor.valid_time_utc);

          const weatherCode = sameRun(anchor, weatherRow) ? weatherRow.value : null;
          const cloudCover = sameRun(anchor, cloudRow) ? cloudRow.value : null;
          const precipitation = sameRun(anchor, precipRow) ? precipRow.value : null;
          const condition = weatherCode != null
            ? conditionFromWmo(weatherCode)
            : fallbackCondition(precipitation, cloudCover);
          const daylight = daylightState(sameRun(anchor, dayRow) ? dayRow.value : null, anchor.valid_time_utc);

          const card = cards[index];
          const target = card?.querySelector(".hour-icon");
          if (target) {
            target.innerHTML = weatherIcon(condition.condition, daylight.daylight, { label: condition.label });
            target.dataset.conditionSource = condition.source;
            target.dataset.daylightSource = daylight.source;
          }
          if (card) {
            card.dataset.condition = condition.condition;
            card.dataset.daylight = daylight.daylight;
          }
          return { anchor, condition, daylight };
        });

        const now = Date.now();
        const nearCurrent = rendered.reduce((best, item) => {
          const stamp = new Date(item.anchor.valid_time_utc).getTime();
          if (!Number.isFinite(stamp)) return best;
          const distance = Math.abs(stamp - now);
          return !best || distance < best.distance ? { ...item, distance } : best;
        }, null);
        if (nearCurrent) applyTheme(nearCurrent.daylight.daylight, nearCurrent.condition.condition);
      }).catch(() => {
        applyTheme(daylightState(null, new Date().toISOString()).daylight, "unknown");
      });
    };
  }

  const baseRenderDaily = window.renderDaily;
  if (typeof baseRenderDaily === "function") {
    window.renderDaily = function renderDailyWithNativeConditions(result, healthMap) {
      baseRenderDaily(result, healthMap);
      const rows = result?.payload?.days_by_provider || [];
      const provider = PROVIDER_PREFERENCE.find((candidate) => rows.some((row) => row.provider === candidate))
        || rows[0]?.provider
        || null;
      const selected = provider
        ? rows.filter((row) => row.provider === provider).sort((a, b) => String(a.date).localeCompare(String(b.date))).slice(0, 5)
        : [];
      const targets = [...document.querySelectorAll("#dailyGrid .daily-row .day-icon")];
      selected.forEach((row, index) => {
        const condition = row.condition || "unknown";
        const label = row.condition_label || "Unknown conditions";
        const daylight = row.condition_daylight === "day" || row.condition_daylight === "night"
          ? row.condition_daylight
          : "unknown";
        const target = targets[index];
        if (target) {
          target.innerHTML = weatherIcon(condition, daylight, { label });
          target.dataset.conditionSource = row.condition_source || "insufficient_condition_evidence";
          target.dataset.daylightSource = row.condition_daylight_source || "insufficient_daylight_evidence";
        }
      });
    };
  }

  injectStyles();
  applyTheme(activeDaylight, "unknown");

  const heroPlaceholder = document.querySelector("#heroIcon");
  if (heroPlaceholder) heroPlaceholder.innerHTML = weatherIcon("unknown", activeDaylight, { label: "Unknown conditions", decorative: true });

  window.RozkalnsWeatherConditions = Object.freeze({
    CONDITION_CONTRACT,
    FALLBACK_CONTRACT,
    DAYLIGHT_FALLBACK,
    conditionFromWmo,
    fallbackCondition,
    daylightState,
    weatherIcon,
    applyTheme,
  });
})();
