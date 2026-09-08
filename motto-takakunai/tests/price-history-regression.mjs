import assert from 'node:assert/strict';
import fs from 'node:fs';

const history = JSON.parse(fs.readFileSync(new URL('../data/price-history.json', import.meta.url), 'utf8'));
assert.equal(history.schema_version, 1);
assert.ok(Array.isArray(history.series) && history.series.length >= 3);

for (const series of history.series) {
  assert.ok(series.identity, 'series identity is required');
  assert.ok(Array.isArray(series.observations) && series.observations.length > 0, 'observations required');
  const timestamps = series.observations.map(x => Date.parse(x.observed_at));
  assert.ok(timestamps.every(Number.isFinite), 'all observed_at values must be valid dates');
  for (let i = 1; i < timestamps.length; i++) {
    assert.ok(timestamps[i] >= timestamps[i - 1], 'observations must be append-ordered');
  }
  for (const observation of series.observations) {
    assert.ok(Number.isFinite(observation.base_hourly_wage) && observation.base_hourly_wage > 0);
    assert.equal(typeof observation.rankable, 'boolean');
    if (observation.evidence_type === 'search-list-only') {
      assert.equal(observation.rankable, false, 'search-list-only evidence must never rank as highest wage');
    }
  }
}

const randstadNight = history.series.find(x => x.identity === 'ota-ryutsu-center-trading-cards-night-randstad');
assert.ok(randstadNight);
assert.ok(randstadNight.observations.some(x => x.base_hourly_wage === 1750));
assert.ok(randstadNight.observations.some(x => x.base_hourly_wage === 1700 && x.rankable === false));

console.log('price history regression: OK');
