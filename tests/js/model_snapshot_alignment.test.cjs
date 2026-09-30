const assert = require('node:assert/strict');
const { test } = require('node:test');
const model = require('../../src/rozkalns_weather/static/model_snapshot_alignment.js');

const NOW = Date.parse('2026-09-27T10:00:00Z');
const row = (provider, valid, value, extra = {}) => ({
  provider,
  valid_time_utc: valid,
  value,
  statistic: 'deterministic',
  init_time_utc: '2026-09-27T06:00:00Z',
  ...extra,
});

test('never compares one provider 12:00 value against another provider 13:00 value', () => {
  const icon12 = row('icon_d2', '2026-09-27T12:00:00Z', 10);
  const ifs13 = row('ecmwf_ifs', '2026-09-27T13:00:00Z', 13);
  const aifs12 = row('ecmwf_aifs', '2026-09-27T12:00:00Z', 11);
  const match = model.selectCommonValidTime({
    icon_d2: [icon12],
    ecmwf_ifs: [ifs13],
    ecmwf_aifs: [aifs12],
  }, NOW);

  assert.equal(match.valid_time_utc, '2026-09-27T12:00:00.000Z');
  assert.equal(match.rows.icon_d2, icon12);
  assert.equal(match.rows.ecmwf_aifs, aifs12);
  assert.equal(match.rows.ecmwf_ifs, undefined);
});

test('returns unavailable when no exact future valid time is shared by two providers', () => {
  const match = model.selectCommonValidTime({
    icon_d2: [row('icon_d2', '2026-09-27T12:00:00Z', 10)],
    ecmwf_ifs: [row('ecmwf_ifs', '2026-09-27T13:00:00Z', 11)],
    ecmwf_aifs: [row('ecmwf_aifs', '2026-09-27T14:00:00Z', 12)],
  }, NOW);
  assert.deepEqual(match, { valid_time_utc: null, rows: {} });
});

test('uses the earliest exact shared future time and preserves original provenance rows', () => {
  const icon12 = row('icon_d2', '2026-09-27T12:00:00Z', 10, { model_version: 'icon-v1' });
  const icon13 = row('icon_d2', '2026-09-27T13:00:00Z', 11);
  const ifs12 = row('ecmwf_ifs', '2026-09-27T12:00:00Z', 12, { lead_hours: 6 });
  const ifs13 = row('ecmwf_ifs', '2026-09-27T13:00:00Z', 13);
  const match = model.selectCommonValidTime({ icon_d2: [icon13, icon12], ecmwf_ifs: [ifs13, ifs12] }, NOW);

  assert.equal(match.valid_time_utc, '2026-09-27T12:00:00.000Z');
  assert.equal(match.rows.icon_d2, icon12);
  assert.equal(match.rows.icon_d2.model_version, 'icon-v1');
  assert.equal(match.rows.ecmwf_ifs, ifs12);
  assert.equal(match.rows.ecmwf_ifs.lead_hours, 6);
});

test('missing and non-finite values never qualify as comparable model values', () => {
  const match = model.selectCommonValidTime({
    icon_d2: [row('icon_d2', '2026-09-27T12:00:00Z', null)],
    ecmwf_ifs: [row('ecmwf_ifs', '2026-09-27T12:00:00Z', 12)],
    ecmwf_aifs: [row('ecmwf_aifs', '2026-09-27T12:00:00Z', Infinity)],
  }, NOW);
  assert.deepEqual(match, { valid_time_utc: null, rows: {} });
});

test('run age is derived from init provenance without mutating provider rows', () => {
  const source = row('icon_d2', '2026-09-27T12:00:00Z', 10);
  assert.equal(model.runAgeHours(source, NOW), 4);
  assert.equal(source.init_time_utc, '2026-09-27T06:00:00Z');
});

test('WeatherNext no-data state is pending while genuine stale and fresh rows stay distinct', () => {
  const genuine = row('weathernext3', '2026-09-27T12:00:00Z', 12.5);

  assert.equal(model.priorityState(null, { ingest_state: 'access_pending', freshness_state: 'not_tracked' }), 'pending');
  assert.equal(model.priorityState(null, { ingest_state: 'ready', freshness_state: 'not_ingested' }), 'pending');
  assert.equal(model.priorityState(genuine, { ingest_state: 'ready', freshness_state: 'stale' }), 'stale');
  assert.equal(model.priorityState(genuine, { ingest_state: 'ready', freshness_state: 'fresh' }), 'fresh');
});
