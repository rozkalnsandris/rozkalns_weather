const assert = require('node:assert/strict');
const { test } = require('node:test');
const trend = require('../../src/rozkalns_weather/static/daily_trend.js');
const theme = require('../../src/rozkalns_weather/static/ui_preferences.js');

test('auto appearance observes Berlin boundaries and summer/winter offset', () => {
  for (const [iso, expected] of [
    ['2026-09-27T04:59:00Z', 'dark'], ['2026-09-27T05:00:00Z', 'light'],
    ['2026-09-27T17:59:00Z', 'light'], ['2026-09-27T18:00:00Z', 'dark'],
    ['2026-12-01T05:59:00Z', 'dark'], ['2026-12-01T06:00:00Z', 'light'],
    ['2026-12-01T18:59:00Z', 'light'], ['2026-12-01T19:00:00Z', 'dark'],
    ['2026-10-25T00:30:00Z', 'dark'], ['2026-10-25T01:30:00Z', 'dark'],
  ]) assert.equal(theme.resolve('auto', new Date(iso)), expected);
  assert.equal(theme.resolve('light', new Date('2026-09-27T23:00:00Z')), 'light');
  assert.equal(theme.resolve('dark', new Date('2026-09-27T12:00:00Z')), 'dark');
  assert.equal(theme.normalize('unexpected'), 'auto');
});
test('daily selection separates providers, validates dates, preserves provenance and input', () => {
  const late = {provider:'icon_d2', date:'2026-09-29', init_time_utc:'2026-09-27T00:00:00Z'};
  const early = {provider:'icon_d2', date:'2026-09-27'};
  const rows = [late, {provider:'ecmwf_ifs', date:'2026-09-28'}, early,
    {provider:'icon_d2', date:'2026-02-30'}, {provider:'icon_d2', date:null}];
  assert.deepEqual(trend.select(rows, 'icon_d2'), [early, late]);
  assert.equal(rows[0], late);
  assert.equal(trend.select(rows, 'icon_d2')[1].init_time_utc, late.init_time_utc);
  assert.deepEqual(trend.select(rows, 'weathernext3'), []);
  assert.equal(trend.select(Array.from({length:20}, (_,i)=>({provider:'x',date:`2026-09-${String(i+1).padStart(2,'0')}`})), 'x').length,14);
});
test('absent values never become zero; real zero, negative and extreme temperatures survive', () => {
  for (const value of [null, undefined, '', false, NaN, Infinity, '10']) assert.equal(trend.number(value), null);
  for (const value of [0, -30, 51]) assert.equal(trend.number(value), value);
  assert.equal(trend.amount({precipitation_total_mm:null}), null);
  assert.equal(trend.amount({precipitation_total_mm:-1}), null);
  assert.equal(trend.amount({precipitation_total_mm:0}), 0);
  assert.equal(trend.amount({precipitation_total_mm:5.2}), 5.2);
});
test('temperature lines break at missing values and calendar gaps', () => {
  const path = trend.geometry([
    {date:'2026-09-27',v:0}, {date:'2026-09-28',v:-2},
    {date:'2026-09-29',v:null}, {date:'2026-09-30',v:3}, {date:'2026-10-02',v:4},
  ], 'v', value=>100-value);
  assert.equal(path, 'M24,100.00 L72,102.00  M168,97.00 M216,96.00');
});
test('renderer escapes source fields, exposes table and marks short horizons', () => {
  const target = {innerHTML:'', dataset:{}, querySelectorAll:()=>[]};
  trend.render(target, [{provider:'x',date:'2026-09-27',temperature_max_c:0,temperature_min_c:null,precipitation_total_mm:null,init_time_quality:'<script>'}], 'x');
  assert.match(target.innerHTML, /1 available day/);
  assert.match(target.innerHTML, /data-days="14"[^>]*disabled/);
  assert.match(target.innerHTML, /&lt;script&gt;/);
  assert.doesNotMatch(target.innerHTML, /<script>/);
  assert.match(target.innerHTML, /Max 0° · Min — · Rain —/);
  assert.equal(target.dataset.provider, 'x');
});
