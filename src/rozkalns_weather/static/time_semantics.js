(() => {
  const BERLIN_TIMEZONE = "Europe/Berlin";
  const UTC_STRING = /(?:Z|[+-]00:00)$/;

  function canonicalUtcDate(value) {
    if (value instanceof Date) return Number.isNaN(value.valueOf()) ? null : value;
    if (typeof value !== "string" || !UTC_STRING.test(value.trim())) return null;
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? null : date;
  }

  function berlinParts(value, options = {}) {
    const date = canonicalUtcDate(value);
    if (!date) return null;
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: BERLIN_TIMEZONE,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: options.second ? "2-digit" : undefined,
      hourCycle: "h23",
      timeZoneName: "shortOffset",
    }).formatToParts(date);
    const map = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return { date, ...map };
  }

  function berlinLocalIdentity(value) {
    const parts = berlinParts(value, { second: true });
    if (!parts) return null;
    const localDate = `${parts.year}-${parts.month}-${parts.day}`;
    const localClock = `${parts.hour}:${parts.minute}:${parts.second}`;
    return {
      utc: parts.date.toISOString(),
      timezone: BERLIN_TIMEZONE,
      localDate,
      localMonth: `${parts.year}-${parts.month}`,
      localClock,
      offset: parts.timeZoneName,
      displayIdentity: `${localDate}T${localClock} ${parts.timeZoneName}|${parts.date.toISOString()}`,
    };
  }

  function formatLocalTimeBerlin(value) {
    const identity = berlinLocalIdentity(value);
    return identity ? `${identity.localClock.slice(0, 5)} ${identity.offset}` : "—";
  }

  function formatTimestampBerlin(value) {
    const identity = berlinLocalIdentity(value);
    if (!identity) return value ? String(value) : "unknown time";
    const [year, month, day] = identity.localDate.split("-");
    return `${day}/${month}/${year} ${identity.localClock.slice(0, 5)} ${identity.offset} · ${identity.utc}`;
  }

  function localDateKeyBerlin(value = new Date()) {
    const identity = berlinLocalIdentity(value);
    if (identity) return identity.localDate;
    if (value instanceof Date && !Number.isNaN(value.valueOf())) {
      const parts = berlinParts(value);
      return parts ? `${parts.year}-${parts.month}-${parts.day}` : null;
    }
    return null;
  }

  function localMonthKeyBerlin(value = new Date()) {
    const date = value instanceof Date ? value : canonicalUtcDate(value);
    if (!date || Number.isNaN(date.valueOf())) return null;
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: BERLIN_TIMEZONE,
      year: "numeric",
      month: "2-digit",
    }).formatToParts(date);
    const map = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return `${map.year}-${map.month}`;
  }

  globalThis.berlinDate = canonicalUtcDate;
  globalThis.formatLocalTime = formatLocalTimeBerlin;
  globalThis.formatTimestamp = formatTimestampBerlin;
  globalThis.localDateKey = localDateKeyBerlin;
  globalThis.berlinLocalIdentity = berlinLocalIdentity;
  globalThis.berlinMonthKey = localMonthKeyBerlin;

  const drilldownMonth = document.querySelector("#drilldownMonth");
  const berlinMonth = localMonthKeyBerlin(new Date());
  if (drilldownMonth && berlinMonth) drilldownMonth.value = berlinMonth;

  if (typeof globalThis.refresh === "function") void globalThis.refresh();
})();
