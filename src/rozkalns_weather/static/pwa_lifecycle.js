(() => {
  "use strict";

  const UPDATE_RELOAD_GUARD = "rozkalns-weather:pwa-update-reload:v1";
  const hasServiceWorker = "serviceWorker" in navigator;
  const hadControllerAtLoad = hasServiceWorker && Boolean(navigator.serviceWorker.controller);
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

  function reloadForUpdatedWorker() {
    if (!hadControllerAtLoad) {
      setLifecycleState("ready", "initial service worker activated");
      return false;
    }
    try {
      if (sessionStorage.getItem(UPDATE_RELOAD_GUARD) === "1") return false;
      sessionStorage.setItem(UPDATE_RELOAD_GUARD, "1");
    } catch (_error) {
      // A failed sessionStorage write must not block the update reload.
    }
    setLifecycleState("reloading", "updated service worker activated");
    window.location.reload();
    return true;
  }

  if (!hasServiceWorker) {
    setLifecycleState("unsupported", "service workers are unavailable");
  } else {
    if (updatedAfterReload) {
      setLifecycleState("updated", "page reloaded under the updated service worker");
    } else {
      setLifecycleState(hadControllerAtLoad ? "ready" : "installing");
    }

    navigator.serviceWorker.addEventListener("controllerchange", reloadForUpdatedWorker);
    navigator.serviceWorker.ready.then(() => {
      if (!updatedAfterReload && document.documentElement.dataset.pwaLifecycle !== "reloading") {
        setLifecycleState("ready", hadControllerAtLoad ? "service worker active" : "initial service worker installed");
      }
    }).catch((error) => {
      setLifecycleState("error", String(error));
    });
  }

  window.RozkalnsPwaLifecycle = Object.freeze({
    UPDATE_RELOAD_GUARD,
    hadControllerAtLoad,
    updatedAfterReload,
    setLifecycleState,
    reloadForUpdatedWorker,
  });
})();
