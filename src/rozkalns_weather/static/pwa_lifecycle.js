(() => {
  "use strict";

  const ROOT_WORKER_URL = "/sw.js";
  const ROOT_SCOPE = "/";
  const LEGACY_WORKER_PATH = "/static/sw.js";
  const UPDATE_RELOAD_GUARD = "rozkalns-weather:pwa-update-reload:v1";
  const hasServiceWorker = "serviceWorker" in navigator;
  const hadControllerAtLoad = hasServiceWorker && Boolean(navigator.serviceWorker.controller);
  let controllerChangeHandled = false;

  const updatedAfterReload = (() => {
    try {
      if (sessionStorage.getItem(UPDATE_RELOAD_GUARD) !== "1") return false;
      sessionStorage.removeItem(UPDATE_RELOAD_GUARD);
      return true;
    } catch (_error) {
      return false;
    }
  })();

  function setLifecycleState(state, detail = "") {
    document.documentElement.dataset.pwaLifecycle = state;
    window.dispatchEvent(new CustomEvent("rozkalns:pwa-lifecycle", {
      detail: { state, detail },
    }));
  }

  function registrationScriptUrl(registration) {
    return registration?.active?.scriptURL
      || registration?.waiting?.scriptURL
      || registration?.installing?.scriptURL
      || "";
  }

  function isRootWorker(worker) {
    if (!worker?.scriptURL) return false;
    return new URL(worker.scriptURL).pathname === ROOT_WORKER_URL;
  }

  async function removeLegacyRegistration() {
    const registrations = await navigator.serviceWorker.getRegistrations();
    const legacy = registrations.filter((registration) => {
      const scopePath = new URL(registration.scope).pathname;
      const scriptUrl = registrationScriptUrl(registration);
      const scriptPath = scriptUrl ? new URL(scriptUrl).pathname : "";
      return scopePath.startsWith("/static/") && scriptPath === LEGACY_WORKER_PATH;
    });
    const removed = await Promise.all(legacy.map((registration) => registration.unregister()));
    return removed.filter(Boolean).length;
  }

  async function reloadForUpdatedWorker() {
    if (controllerChangeHandled) return false;
    controllerChangeHandled = true;
    await removeLegacyRegistration();

    if (!hadControllerAtLoad) {
      setLifecycleState("ready", "initial root-scope service worker activated");
      return false;
    }
    try {
      if (sessionStorage.getItem(UPDATE_RELOAD_GUARD) === "1") return false;
      sessionStorage.setItem(UPDATE_RELOAD_GUARD, "1");
    } catch (_error) {
      // A failed sessionStorage write must not block the update reload.
    }
    setLifecycleState("reloading", "updated root-scope service worker activated");
    window.location.reload();
    return true;
  }

  async function installRootWorker() {
    let registration = null;
    if (isRootWorker(navigator.serviceWorker.controller)) {
      registration = await navigator.serviceWorker.getRegistration(ROOT_SCOPE);
    }
    if (!registration) {
      registration = await navigator.serviceWorker.register(ROOT_WORKER_URL, { scope: ROOT_SCOPE });
    } else if (navigator.onLine) {
      void registration.update().catch(() => {});
    }
    await removeLegacyRegistration();
    await navigator.serviceWorker.ready;
    return registration;
  }

  if (!hasServiceWorker) {
    setLifecycleState("unsupported", "service workers are unavailable");
  } else {
    if (updatedAfterReload) {
      setLifecycleState("updated", "page reloaded under the updated root-scope service worker");
    } else {
      setLifecycleState(hadControllerAtLoad ? "ready" : "installing");
    }

    navigator.serviceWorker.addEventListener("controllerchange", () => {
      void reloadForUpdatedWorker();
    });

    installRootWorker().then(() => {
      if (!updatedAfterReload && document.documentElement.dataset.pwaLifecycle !== "reloading") {
        setLifecycleState("ready", hadControllerAtLoad ? "root-scope service worker active" : "root-scope service worker installed");
      }
    }).catch((error) => {
      if (hadControllerAtLoad && isRootWorker(navigator.serviceWorker.controller)) {
        setLifecycleState("ready", "root-scope service worker remains active while update check is unavailable");
        return;
      }
      setLifecycleState("error", String(error));
    });
  }

  window.RozkalnsPwaLifecycle = Object.freeze({
    ROOT_WORKER_URL,
    ROOT_SCOPE,
    LEGACY_WORKER_PATH,
    UPDATE_RELOAD_GUARD,
    hadControllerAtLoad,
    updatedAfterReload,
    setLifecycleState,
    registrationScriptUrl,
    isRootWorker,
    removeLegacyRegistration,
    reloadForUpdatedWorker,
    installRootWorker,
  });
})();
