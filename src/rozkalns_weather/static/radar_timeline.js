(() => {
  "use strict";

  const radarButton = document.querySelector("#loadRadar");
  const radarState = document.querySelector("#radarState");
  let radarOutput = document.querySelector("#radarOutput");

  if (!radarButton || !radarState || !radarOutput) return;

  let loaded = false;
  let inFlight = null;

  function setState(state, message, { alert = false } = {}) {
    if (typeof window.setSurfaceState === "function") {
      window.setSurfaceState("radarState", state, message, { alert });
      return;
    }
    radarState.dataset.state = state;
    radarState.setAttribute("role", alert ? "alert" : "status");
    radarState.setAttribute("aria-live", alert ? "assertive" : "polite");
    radarState.textContent = `${state.toUpperCase()} · ${message}`;
  }

  function resultState(result) {
    if (typeof window.stateFromResult === "function") return window.stateFromResult(result);
    if (result?.source === "offline-cache") return "offline";
    if (result?.source === "stale-cache") return "stale";
    return "fresh";
  }

  function formatFrameTime(value) {
    if (typeof window.formatTimestamp === "function") return window.formatTimestamp(value);
    const date = value ? new Date(value) : null;
    if (!date || Number.isNaN(date.valueOf())) return value ? String(value) : "unknown time";
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/Berlin",
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  function ensureOutputRegion() {
    if (radarOutput.tagName === "PRE") {
      const replacement = document.createElement("div");
      replacement.id = radarOutput.id;
      replacement.className = radarOutput.className;
      radarOutput.replaceWith(replacement);
      radarOutput = replacement;
    }
    radarOutput.setAttribute("role", "region");
    radarOutput.setAttribute("aria-label", "DWD radar frame timeline");
    radarOutput.setAttribute("aria-live", "polite");
    return radarOutput;
  }

  function normalizedFrames(payload) {
    const frames = Array.isArray(payload?.frames) ? payload.frames : [];
    return frames
      .filter((frame) => frame && (frame.kind === "radar_observed" || frame.kind === "radar_nowcast"))
      .filter((frame) => frame.timestamp && !Number.isNaN(new Date(frame.timestamp).valueOf()))
      .slice()
      .sort((left, right) => new Date(left.timestamp).valueOf() - new Date(right.timestamp).valueOf());
  }

  function renderTimeline(payload) {
    const output = ensureOutputRegion();
    const frames = normalizedFrames(payload);
    const observed = frames.filter((frame) => frame.kind === "radar_observed");
    const latestObserved = observed.length ? observed[observed.length - 1] : null;
    const renderingContract = payload?.map_contract?.rendering_contract || {};

    output.replaceChildren();

    if (frames.length) {
      const list = document.createElement("ol");
      list.className = "radar-frame-list";
      list.setAttribute("aria-label", "Available radar frames");

      frames.forEach((frame) => {
        const item = document.createElement("li");
        item.dataset.kind = frame.kind;
        const isLatestObserved = latestObserved === frame;
        const kindLabel = frame.kind === "radar_nowcast"
          ? "Nowcast"
          : isLatestObserved ? "Latest observed" : "Observed";
        const source = frame.source ? ` · ${String(frame.source)}` : "";
        item.textContent = `${kindLabel} · ${formatFrameTime(frame.timestamp)}${source}`;
        list.appendChild(item);
      });
      output.appendChild(list);
    } else {
      const empty = document.createElement("p");
      empty.className = "hint radar-empty-state";
      empty.textContent = "No radar frames are available in this response. This does not mean precipitation is absent.";
      output.appendChild(empty);
    }

    const imagery = document.createElement("p");
    imagery.className = "hint radar-imagery-state";
    if (renderingContract.raster_rendering_available === false) {
      imagery.textContent = "Radar imagery is not rendered yet: encoding, dimensions, projection, precipitation unit, and nodata semantics are still pending validation.";
      imagery.dataset.reasonCode = renderingContract.reason_code || "RADAR_RASTER_CONTRACT_PENDING";
    } else {
      imagery.textContent = "This view currently presents radar frame timing metadata only; it does not infer precipitation from an absent image.";
    }
    output.appendChild(imagery);

    return { frameCount: frames.length, latestObservedTimestamp: latestObserved?.timestamp || null };
  }

  async function load({ force = false } = {}) {
    if (loaded && !force) return null;
    if (inFlight) return inFlight;
    if (typeof window.apiWithFallback !== "function") {
      setState("error", "Radar loader is unavailable.", { alert: true });
      return null;
    }

    radarButton.disabled = true;
    radarOutput.setAttribute("aria-busy", "true");
    setState("loading", "Loading DWD radar frame metadata…");

    inFlight = (async () => {
      try {
        const result = await window.apiWithFallback("/api/radar", "safety-radar");
        const rendered = renderTimeline(result.payload);
        const state = resultState(result);
        const emptyMessage = rendered.frameCount === 0
          ? "Current radar response contains no usable frames. This does not mean precipitation is absent."
          : "DWD radar frame metadata loaded; observed and nowcast frames remain explicitly separate.";
        if (state === "fresh") setState("fresh", emptyMessage);
        else if (state === "offline") setState("offline", "Showing cached radar frame metadata while offline; it is not current.");
        else setState("stale", "Live radar refresh failed; showing cached frame metadata with retained timestamps.");
        loaded = true;
        return result;
      } catch (error) {
        ensureOutputRegion().replaceChildren();
        const unavailable = document.createElement("p");
        unavailable.className = "hint radar-empty-state";
        unavailable.textContent = "Radar metadata is unavailable. This does not mean precipitation is absent.";
        radarOutput.appendChild(unavailable);
        setState("error", `Radar metadata request failed: ${String(error)}`, { alert: true });
        return null;
      } finally {
        radarOutput.setAttribute("aria-busy", "false");
        radarButton.disabled = false;
        inFlight = null;
      }
    })();

    return inFlight;
  }

  ensureOutputRegion();
  radarButton.textContent = "Refresh radar metadata";
  radarButton.onclick = () => load({ force: true });
  window.addEventListener("online", () => {
    if (loaded) load({ force: true });
  });

  window.rozkalnsRadarTimeline = Object.freeze({ load, renderTimeline });
})();