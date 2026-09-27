const assert = require('node:assert/strict');
const { test } = require('node:test');
const {
  warningEvidence,
  reduceWarningState,
  warningSummary,
  warningCheckedAge,
  warningDisplayTime,
  warningReadableText,
  createSingleFlight,
} = require('../../src/rozkalns_weather/static/runtime_badge.js');

const payload = (alerts = []) => ({
  authority: 'DWD',
  official: true,
  kind: 'official_warning',
  state: alerts.length ? 'alerts_present' : 'no_active_alerts',
  source_attribution: 'DWD warning data via Bright Sky',
  retrieved_at_utc: '2026-09-27T08:00:00Z',
  reference_location: { id: 'station_05480', label: 'Werl reference', kind: 'public_reference' },
  alerts,
});

test('fresh DWD evidence distinguishes clear from non-expired warnings', () => {
  assert.equal(warningEvidence(payload()).state, 'clear');
  assert.equal(warningEvidence(payload([{ lifecycle: 'expired' }])).state, 'clear');
  const active = warningEvidence(payload([
    { lifecycle: 'active', headline: 'Storm' },
    { lifecycle: 'upcoming', headline: 'Wind' },
    { lifecycle: 'expired', headline: 'Old' },
  ]));
  assert.equal(active.state, 'active');
  assert.equal(active.alerts.length, 2);
});

test('clear requires a complete and internally consistent warning response contract', () => {
  const clear = payload();
  assert.equal(warningEvidence(clear).state, 'clear');
  assert.equal(warningEvidence({ ...clear, state: undefined }), null);
  assert.equal(warningEvidence({ ...clear, state: 'alerts_present' }), null);
  assert.equal(warningEvidence({ ...clear, kind: 'other' }), null);
  assert.equal(warningEvidence({ ...clear, retrieved_at_utc: 'not-a-time' }), null);
  assert.equal(warningEvidence({ ...clear, reference_location: null }), null);

  const active = payload([{ lifecycle: 'active', headline: 'Storm' }]);
  assert.equal(warningEvidence({ ...active, state: 'no_active_alerts' }), null);
  assert.equal(warningEvidence({ ...active, alerts: [{ headline: 'Missing lifecycle' }] }), null);
});

test('loading and failure preserve last-known warning evidence without claiming freshness', () => {
  const current = reduceWarningState(undefined, {
    type: 'success', payload: payload([{ lifecycle: 'active', headline: 'Storm' }]),
  });
  const loading = reduceWarningState(current, { type: 'loading' });
  assert.equal(loading.state, 'loading');
  assert.equal(loading.evidence.alerts.length, 1);
  const stale = reduceWarningState(loading, { type: 'failure' });
  assert.equal(stale.state, 'stale');
  assert.equal(stale.evidence.alerts[0].headline, 'Storm');
  assert.match(warningSummary(stale), /Last known: 1 DWD warning/);
  assert.match(warningReadableText(stale), /Current DWD status unavailable; showing last known official warning evidence/);
});

test('fresh clear replaces prior active evidence while failure without evidence is error', () => {
  const active = reduceWarningState(undefined, {
    type: 'success', payload: payload([{ lifecycle: 'active' }]),
  });
  const clear = reduceWarningState(active, { type: 'success', payload: payload([]) });
  assert.equal(clear.state, 'clear');
  assert.equal(clear.evidence.alerts.length, 0);
  assert.equal(warningSummary(clear), 'No active warnings · current DWD response');
  assert.match(warningReadableText(clear), /No active warnings in the latest valid DWD response/);
  assert.equal(reduceWarningState(undefined, { type: 'failure' }).state, 'error');
});

test('malformed or inconsistent success cannot erase valid last-known evidence', () => {
  const active = reduceWarningState(undefined, {
    type: 'success', payload: payload([{ lifecycle: 'active', headline: 'Storm' }]),
  });
  const malformed = reduceWarningState(active, {
    type: 'success',
    payload: { ...payload([]), state: undefined },
  });
  assert.equal(malformed.state, 'stale');
  assert.equal(malformed.evidence.alerts[0].headline, 'Storm');

  const inconsistent = reduceWarningState(active, {
    type: 'success',
    payload: { ...payload([]), state: 'alerts_present' },
  });
  assert.equal(inconsistent.state, 'stale');
  assert.equal(inconsistent.evidence.alerts[0].headline, 'Storm');

  const nonDwd = reduceWarningState(active, {
    type: 'success',
    payload: { ...payload([]), authority: 'other' },
  });
  assert.equal(nonDwd.state, 'stale');
});

test('warning checked age is display-only and derived from retrieval time', () => {
  const now = Date.parse('2026-09-27T10:00:00Z');
  assert.equal(warningCheckedAge('2026-09-27T09:59:40Z', now), 'checked just now');
  assert.equal(warningCheckedAge('2026-09-27T09:53:00Z', now), 'checked 7m ago');
  assert.equal(warningCheckedAge('2026-09-27T07:30:00Z', now), 'checked 2h ago');
  assert.equal(warningCheckedAge('not-a-time', now), '');
});

test('warning readable text exposes normalized official fields without raw JSON or fabricated area', () => {
  const current = reduceWarningState(undefined, {
    type: 'success',
    payload: payload([{
      lifecycle: 'active',
      headline: 'Severe wind',
      severity: 'severe',
      effective: '2026-09-27T08:00:00Z',
      expires: '2026-09-27T12:00:00Z',
      description: 'Strong gusts are possible.',
      instruction: 'Secure loose objects.',
    }]),
  });
  const text = warningReadableText(current);
  assert.match(text, /DWD official warnings/);
  assert.match(text, /Reference location: Werl reference/);
  assert.match(text, /1\. Severe wind/);
  assert.match(text, /Severity: SEVERE/);
  assert.match(text, /Status: active/);
  assert.match(text, /Details: Strong gusts are possible\./);
  assert.match(text, /Instructions: Secure loose objects\./);
  assert.match(text, /Authority: DWD · DWD warning data via Bright Sky/);
  assert.doesNotMatch(text, /"authority"\s*:/);
  assert.doesNotMatch(text, /Affected area:/);
});

test('warning display time uses Berlin local time and omits invalid timestamps', () => {
  const formatted = warningDisplayTime('2026-09-27T08:00:00Z');
  assert.match(formatted, /27/);
  assert.match(formatted, /10:00/);
  assert.equal(warningDisplayTime('not-a-time'), '');
});

test('single-flight warning refresh deduplicates concurrent requests and resets after completion', async () => {
  let calls = 0;
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const refresh = createSingleFlight(async () => {
    calls += 1;
    await gate;
    return calls;
  });
  const first = refresh();
  const second = refresh();
  assert.equal(first, second);
  await Promise.resolve();
  assert.equal(calls, 1);
  release();
  assert.equal(await first, 1);
  assert.equal(await second, 1);
  assert.equal(await refresh(), 2);
});
