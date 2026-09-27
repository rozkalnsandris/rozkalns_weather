/* Appearance is independent of provider daylight/condition evidence. */
(function (root) {
  "use strict";
  const KEY = "rozkalns-appearance-v1";
  const normalize = value => ["auto", "light", "dark"].includes(value) ? value : "auto";
  function resolve(value, date = new Date()) {
    const mode = normalize(value);
    if (mode !== "auto") return mode;
    const hour = Number(new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Berlin", hour: "2-digit", hourCycle: "h23" }).format(date));
    return hour >= 20 || hour < 7 ? "dark" : "light";
  }
  const api = { normalize, resolve };
  if (typeof module !== "undefined") module.exports = api;
  if (!root.document) return;
  let preference = "auto";
  try { preference = normalize(root.localStorage.getItem(KEY)); } catch (_) { /* Private browsing: keep in memory. */ }
  function apply() {
    const theme = resolve(preference);
    document.documentElement.dataset.uiTheme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#101b29" : "#f0f5fa");
    const selector = document.getElementById("appearanceMode");
    if (selector) selector.value = preference;
  }
  apply();
  document.addEventListener("DOMContentLoaded", () => {
    apply();
    document.getElementById("appearanceMode")?.addEventListener("change", event => {
      preference = normalize(event.target.value);
      try { root.localStorage.setItem(KEY, preference); } catch (_) { /* No persistence available. */ }
      apply();
    });
  });
  root.addEventListener("storage", event => {
    if (event.key === KEY || event.key === null) { preference = normalize(event.newValue); apply(); }
  });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) apply(); });
  root.setInterval(apply, 60000);
})(typeof window !== "undefined" ? window : globalThis);
