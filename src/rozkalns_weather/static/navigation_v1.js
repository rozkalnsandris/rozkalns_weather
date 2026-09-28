(() => {
  "use strict";

  const VIEW_IDS = new Set(["overview", "models", "safety", "accuracy", "status"]);
  const navButtons = [...document.querySelectorAll(".tabs button[data-view]")];
  const originalHandlers = new Map(navButtons.map((button) => [button, button.onclick]));
  const skipLink = document.querySelector(".skip-link");
  const navigationScriptUrl = document.currentScript?.src || window.location.href;
  const radarTimelineUrl = new URL("radar_timeline.js", navigationScriptUrl).href;
  let radarTimelinePromise = null;

  function markRadarModuleFailure() {
    const state = document.querySelector("#radarState");
    const button = document.querySelector("#loadRadar");
    if (button) button.disabled = false;
    if (!state) return;
    state.dataset.state = "error";
    state.setAttribute("role", "alert");
    state.setAttribute("aria-live", "assertive");
    state.textContent = "ERROR · Radar timeline module could not be loaded. This does not mean precipitation is absent.";
  }

  function ensureRadarTimeline() {
    if (window.rozkalnsRadarTimeline) {
      return Promise.resolve(window.rozkalnsRadarTimeline.load?.());
    }
    if (radarTimelinePromise) return radarTimelinePromise;

    const button = document.querySelector("#loadRadar");
    if (button) button.disabled = true;

    radarTimelinePromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = radarTimelineUrl;
      script.dataset.radarTimeline = "true";
      script.onload = () => {
        Promise.resolve(window.rozkalnsRadarTimeline?.load?.()).then(resolve, reject);
      };
      script.onerror = () => {
        radarTimelinePromise = null;
        markRadarModuleFailure();
        reject(new Error("radar timeline module failed to load"));
      };
      document.head.appendChild(script);
    });
    return radarTimelinePromise;
  }

  if (skipLink) {
    Object.assign(skipLink.style, {
      position: "fixed",
      top: "8px",
      left: "8px",
      zIndex: "100",
      padding: "10px 12px",
      borderRadius: "10px",
      background: "#ffffff",
      color: "#12324a",
      transform: "translateY(-160%)",
      transition: "transform .12s ease",
    });
    skipLink.addEventListener("focus", () => { skipLink.style.transform = "translateY(0)"; });
    skipLink.addEventListener("blur", () => { skipLink.style.transform = "translateY(-160%)"; });
  }

  function normalizedView(value) {
    return VIEW_IDS.has(value) ? value : "overview";
  }

  function syncCurrent(viewId) {
    navButtons.forEach((button) => {
      if (button.dataset.view === viewId) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
  }

  function focusView(viewId) {
    const view = document.getElementById(viewId);
    if (!view) return;
    const target = view.querySelector("h1, h2") || view;
    const temporaryTabindex = !target.hasAttribute("tabindex");
    if (temporaryTabindex) target.setAttribute("tabindex", "-1");
    target.focus({ preventScroll: true });
    if (temporaryTabindex) {
      target.addEventListener("blur", () => target.removeAttribute("tabindex"), { once: true });
    }
  }

  function invokeView(viewId) {
    const button = navButtons.find((item) => item.dataset.view === viewId);
    const handler = button ? originalHandlers.get(button) : null;
    if (button && typeof handler === "function") {
      handler.call(button, new MouseEvent("click", { bubbles: false }));
    } else {
      document.querySelectorAll(".view").forEach((view) => view.classList.toggle("active", view.id === viewId));
      navButtons.forEach((item) => item.classList.toggle("active", item.dataset.view === viewId));
    }
    syncCurrent(viewId);
    if (viewId === "safety") ensureRadarTimeline().catch(() => {});
  }

  function activateHash({ focus = false } = {}) {
    const raw = window.location.hash.replace(/^#/, "");
    const viewId = normalizedView(raw);
    if (raw !== viewId) history.replaceState(null, "", `#${viewId}`);
    invokeView(viewId);
    if (focus) focusView(viewId);
  }

  navButtons.forEach((button) => {
    button.onclick = (event) => {
      event?.preventDefault?.();
      const viewId = normalizedView(button.dataset.view);
      if (window.location.hash === `#${viewId}`) {
        invokeView(viewId);
        focusView(viewId);
      } else {
        window.location.hash = viewId;
      }
    };
  });

  document.querySelectorAll("[data-open-view]").forEach((control) => {
    control.addEventListener("click", () => {
      const viewId = normalizedView(control.dataset.openView);
      if (window.location.hash !== `#${viewId}`) window.location.hash = viewId;
      else syncCurrent(viewId);
    });
  });

  skipLink?.addEventListener("click", (event) => {
    event.preventDefault();
    if (window.location.hash === "#overview") focusView("overview");
    else window.location.hash = "overview";
  });

  window.addEventListener("hashchange", () => activateHash({ focus: true }));
  activateHash();
})();