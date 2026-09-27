const assert = require('node:assert/strict');
const { test } = require('node:test');
const {
  warningEvidence,
  reduceWarningState,
  warningSummary,
} = require('../../src/rozkalns_weather/static/runtime_badge.js');

const payload = (alerts = []) => ({
  authority: 'DWD',
  official: true,
  retrieved_at_utc: '2026-09-27T08:00:00Z',
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
});

test('fresh clear replaces prior active evidence while failure without evidence is error', () => {
  const active = reduceWarningState(undefined, {
    type: 'success', payload: payload([{ lifecycle: 'active' }]),
  });
  const clear = reduceWarningState(active, { type: 'success', payload: payload([]) });
  assert.equal(clear.state, 'clear');
  assert.equal(clear.evidence.alerts.length, 0);
  assert.equal(warningSummary(clear), 'No active warnings · current DWD response');
  assert.equal(reduceWarningState(undefined, { type: 'failure' }).state, 'error');
});

test('malformed or non-DWD success cannot erase valid last-known evidence', () => {
  const active = reduceWarningState(undefined, {
    type: 'success', payload: payload([{ lifecycle: 'active', headline: 'Storm' }]),
  });
  const malformed = reduceWarningState(active, { type: 'success', payload: { authority: 'other', official: true, alerts: [] } });
  assert.equal(malformed.state, 'stale');
  assert.equal(malformed.evidence.alerts[0].headline, 'Storm');
});