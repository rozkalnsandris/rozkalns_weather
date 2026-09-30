(() => {
  "use strict";

  const radarButton = document.querySelector("#loadRadar");
  const radarState = document.querySelector("#radarState");
  let radarOutput = document.querySelector("#radarOutput");

  if (!radarButton || !radarState || !radarOutput) return;

  let loaded = false;
  let inFlight = null;
  let playbackTimer = null;

  function ensureStyles() {
    if (document.querySelector("#radar-player-styles")) return;
    const style = document.createElement("style");
    style.id = "radar-player-styles";
    style.textContent = `
      .radar-player{display:grid;gap:10px;max-width:100%;min-width:0}
      .radar-frame-head{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px}
      .radar-kind-badge{display:inline-flex;align-items:center;min-height:28px;padding:3px 8px;border:1px solid var(--border);border-radius:999px;background:var(--soft);font-size:11px;font-weight:700}
      .radar-kind-badge[data-kind="radar_nowcast"]{border-style:dashed}
      .radar-canvas-wrap{position:relative;width:min(100%,560px);margin:0 auto;aspect-ratio:1;border:1px solid var(--border);border-radius:12px;overflow:hidden;background:repeating-linear-gradient(45deg,var(--soft),var(--soft) 8px,var(--card) 8px,var(--card) 16px)}
      .radar-canvas{display:block;width:100%;height:100%;image-rendering:pixelated}
      .radar-center-marker{position:absolute;left:50%;top:50%;width:14px;height:14px;transform:translate(-50%,-50%);border:2px solid currentColor;border-radius:50%;color:var(--ink);box-shadow:0 0 0 2px var(--card);pointer-events:none}
      .radar-center-marker::before,.radar-center-marker::after{content:"";position:absolute;background:currentColor}
      .radar-center-marker::before{left:5px;top:-5px;width:1px;height:20px}
      .radar-center-marker::after{left:-5px;top:5px;width:20px;height:1px}
      .radar-controls{display:grid;grid-template-columns:auto minmax(0,1fr);gap:8px 10px;align-items:center}
      .radar-play{min-width:76px;min-height:44px}
      .radar-frame-slider{width:100%;min-width:0}
      .radar-selected{grid-column:1/-1;color:var(--muted);font-size:12px}
      .radar-legend{display:flex;flex-wrap:wrap;gap:7px 12px;color:var(--muted);font-size:11px}
      .radar-legend strong{color:var(--ink)}
      .radar-caption{margin:0;color:var(--muted);font-size:11px;line-height:1.45}
      .radar-diagnostics summary{min-height:44px;display:flex;align-items:center;cursor:pointer;color:var(--muted);font-size:12px}
      .radar-diagnostics pre{max-width:100%;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font-size:10px}
      .radar-frame-list{padding-left:22px}
      @media(max-width:420px){.radar-controls{grid-template-columns:1fr}.radar-selected{grid-column:auto}.radar-play{width:100%}}
    `;
    document.head.appendChild(style);
  }

  function stopPlayback() {
    if (playbackTimer !== null) {
      window.clearInterval(playbackTimer);
      playbackTimer = null;
    }
  }

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

  function validRaster(frame, contract) {
    const raster = frame?.raster;
    const dimensions = contract?.dimensions;
    if (!raster || !Array.isArray(raster.values) || !dimensions) return false;
    if (raster.width !== dimensions.width || raster.height !== dimensions.height) return false;
    if (raster.values.length !== raster.height) return false;
    return raster.values.every((row) =>
      Array.isArray(row) &&
      row.length === raster.width &&
      row.every((value) => Number.isInteger(value) && value >= 0)
    );
  }

  function colorForRaw(value) {
    if (value <= 0) return [0, 0, 0, 0];
    if (value <= 1) return [159, 211, 255, 145];
    if (value <= 5) return [87, 180, 255, 175];
    if (value <= 20) return [43, 132, 220, 205];
    if (value <= 50) return [95, 92, 210, 220];
    if (value <= 100) return [180, 70, 165, 230];
    return [220, 65, 90, 240];
  }

  function drawRaster(canvas, frame, contract) {
    const { width, height, values } = frame.raster;
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d", { alpha: true });
    context.imageSmoothingEnabled = false;
    const image = context.createImageData(width, height);
    let offset = 0;
    for (const row of values) {
      for (const value of row) {
        const color = colorForRaw(value);
        image.data[offset++] = color[0];
        image.data[offset++] = color[1];
        image.data[offset++] = color[2];
        image.data[offset++] = color[3];
      }
    }
    context.putImageData(image, 0, 0);
    const scale = Number(contract?.precipitation_unit?.scale) || 0.01;
    const maxRaw = Math.max(0, ...values.flat());
    const maxMm = maxRaw * scale;
    return { maxRaw, maxMm };
  }

  function frameKindLabel(frame, latestObserved) {
    if (frame.kind === "radar_nowcast") return "Nowcast";
    return frame === latestObserved ? "Latest observed" : "Observed";
  }

  function appendDiagnostics(output, payload, frames) {
    const contract = payload?.map_contract?.rendering_contract || {};
    const details = document.createElement("details");
    details.className = "radar-diagnostics";
    const summary = document.createElement("summary");
    summary.textContent = "Technical radar metadata";
    const raw = document.createElement("pre");
    raw.textContent = JSON.stringify({
      rendering_contract: contract,
      frames: frames.map((frame) => ({ timestamp: frame.timestamp, kind: frame.kind, source: frame.source || null })),
      coordinates_exposed: payload?.map_contract?.coordinates_exposed === true,
      geometry_exposed: payload?.map_contract?.geometry_exposed === true,
    }, null, 2);
    details.append(summary, raw);
    output.appendChild(details);
  }

  function renderRasterPlayer(output, payload, frames, latestObserved) {
    const contract = payload.map_contract.rendering_contract;
    const renderable = frames.filter((frame) => validRaster(frame, contract));
    if (!renderable.length) return false;

    const player = document.createElement("div");
    player.className = "radar-player";

    const head = document.createElement("div");
    head.className = "radar-frame-head";
    const badge = document.createElement("span");
    badge.className = "radar-kind-badge";
    const time = document.createElement("strong");
    head.append(badge, time);

    const canvasWrap = document.createElement("div");
    canvasWrap.className = "radar-canvas-wrap";
    const canvas = document.createElement("canvas");
    canvas.className = "radar-canvas";
    canvas.setAttribute("role", "img");
    const marker = document.createElement("span");
    marker.className = "radar-center-marker";
    marker.setAttribute("aria-hidden", "true");
    canvasWrap.append(canvas, marker);

    const controls = document.createElement("div");
    controls.className = "radar-controls";
    const play = document.createElement("button");
    play.type = "button";
    play.className = "radar-play";
    play.textContent = "Play";
    play.setAttribute("aria-pressed", "false");
    const slider = document.createElement("input");
    slider.type = "range";
    slider.className = "radar-frame-slider";
    slider.min = "0";
    slider.max = String(renderable.length - 1);
    slider.step = "1";
    slider.setAttribute("aria-label", "Radar frame timeline");
    const selected = document.createElement("output");
    selected.className = "radar-selected";
    selected.setAttribute("aria-live", "polite");
    controls.append(play, slider, selected);

    const legend = document.createElement("div");
    legend.className = "radar-legend";
    legend.innerHTML = "<strong>DWD RV intensity</strong><span>1 raw unit = 0.01 mm / 5 min</span><span>fixed display scale</span>";

    const caption = document.createElement("p");
    caption.className = "radar-caption";
    caption.textContent = "Local DWD RADOLAN polar-stereographic grid around the selected privacy-safe reference. This raster is not overlaid on a Web Mercator basemap.";

    player.append(head, canvasWrap, controls, legend, caption);
    output.appendChild(player);

    let selectedIndex = Math.max(0, renderable.findLastIndex((frame) => frame.kind === "radar_observed"));
    const setFrame = (index) => {
      const bounded = Math.max(0, Math.min(renderable.length - 1, Number(index) || 0));
      selectedIndex = bounded;
      slider.value = String(bounded);
      const frame = renderable[bounded];
      const kind = frameKindLabel(frame, latestObserved);
      const drawn = drawRaster(canvas, frame, contract);
      badge.dataset.kind = frame.kind;
      badge.textContent = kind;
      time.textContent = formatFrameTime(frame.timestamp);
      selected.value = `${kind} · ${formatFrameTime(frame.timestamp)} · max ${(drawn.maxMm).toFixed(2)} mm / 5 min`;
      canvas.setAttribute("aria-label", `${kind} DWD radar raster for ${formatFrameTime(frame.timestamp)} Europe/Berlin`);
    };

    slider.addEventListener("input", () => {
      stopPlayback();
      play.textContent = "Play";
      play.setAttribute("aria-pressed", "false");
      setFrame(slider.value);
    });

    play.addEventListener("click", () => {
      if (playbackTimer !== null) {
        stopPlayback();
        play.textContent = "Play";
        play.setAttribute("aria-pressed", "false");
        return;
      }
      play.textContent = "Pause";
      play.setAttribute("aria-pressed", "true");
      playbackTimer = window.setInterval(() => {
        setFrame((selectedIndex + 1) % renderable.length);
      }, 800);
    });

    setFrame(selectedIndex);
    return true;
  }

  function renderFallbackTimeline(output, payload, frames, latestObserved) {
    if (frames.length) {
      const list = document.createElement("ol");
      list.className = "radar-frame-list";
      list.setAttribute("aria-label", "Available radar frames");
      frames.forEach((frame) => {
        const item = document.createElement("li");
        item.dataset.kind = frame.kind;
        const source = frame.source ? ` · ${String(frame.source)}` : "";
        item.textContent = `${frameKindLabel(frame, latestObserved)} · ${formatFrameTime(frame.timestamp)}${source}`;
        list.appendChild(item);
      });
      output.appendChild(list);
    } else {
      const empty = document.createElement("p");
      empty.className = "hint radar-empty-state";
      empty.textContent = "No radar frames are available in this response. This does not mean precipitation is absent.";
      output.appendChild(empty);
    }

    const contract = payload?.map_contract?.rendering_contract || {};
    const imagery = document.createElement("p");
    imagery.className = "hint radar-imagery-state";
    imagery.textContent = "Radar imagery is not rendered yet: encoding, dimensions, projection, precipitation unit, and nodata semantics are unavailable or failed validation.";
    imagery.dataset.reasonCode = contract.reason_code || "RADAR_RASTER_VALIDATION_FAILED";
    output.appendChild(imagery);
  }

  function renderTimeline(payload) {
    stopPlayback();
    ensureStyles();
    const output = ensureOutputRegion();
    const frames = normalizedFrames(payload);
    const observed = frames.filter((frame) => frame.kind === "radar_observed");
    const latestObserved = observed.length ? observed[observed.length - 1] : null;
    const contract = payload?.map_contract?.rendering_contract || {};

    output.replaceChildren();
    const renderedRaster = contract.raster_rendering_available === true
      && contract.state === "raster_ready"
      && renderRasterPlayer(output, payload, frames, latestObserved);

    if (!renderedRaster) renderFallbackTimeline(output, payload, frames, latestObserved);
    appendDiagnostics(output, payload, frames);

    return {
      frameCount: frames.length,
      rasterFrameCount: frames.filter((frame) => validRaster(frame, contract)).length,
      latestObservedTimestamp: latestObserved?.timestamp || null,
    };
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
    setState("loading", "Loading DWD radar frames…");

    inFlight = (async () => {
      try {
        const result = await window.apiWithFallback("/api/radar", "safety-radar");
        const rendered = renderTimeline(result.payload);
        const state = resultState(result);
        const message = rendered.rasterFrameCount
          ? `DWD radar loaded · ${rendered.rasterFrameCount} renderable frames; observed and nowcast remain explicitly separate.`
          : rendered.frameCount
            ? "DWD radar timeline loaded, but raster imagery is unavailable because the normalized contract did not validate."
            : "Current radar response contains no usable frames. This does not mean precipitation is absent.";
        if (state === "fresh") setState("fresh", message);
        else if (state === "offline") setState("offline", "Showing cached radar frames while offline; they are not current.");
        else setState("stale", "Live radar refresh failed; showing cached radar frames with retained timestamps.");
        loaded = true;
        return result;
      } catch (error) {
        stopPlayback();
        ensureOutputRegion().replaceChildren();
        const unavailable = document.createElement("p");
        unavailable.className = "hint radar-empty-state";
        unavailable.textContent = "Radar metadata is unavailable. This does not mean precipitation is absent.";
        radarOutput.appendChild(unavailable);
        setState("error", `Radar request failed: ${String(error)}`, { alert: true });
        return null;
      } finally {
        radarOutput.setAttribute("aria-busy", "false");
        radarButton.disabled = false;
        inFlight = null;
      }
    })();

    return inFlight;
  }

  ensureStyles();
  ensureOutputRegion();
  radarButton.textContent = "Refresh radar metadata";
  radarButton.onclick = () => load({ force: true });
  window.addEventListener("online", () => {
    if (loaded) load({ force: true });
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopPlayback();
  });

  window.rozkalnsRadarTimeline = Object.freeze({ load, renderTimeline, stopPlayback });
})();