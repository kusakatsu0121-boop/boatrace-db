import assert from 'node:assert/strict';
import fs from 'node:fs';
import { compareLiveCandidates, normalizeBaseHourlyStrict } from '../live-candidate-pipeline.js';

const snapshot = JSON.parse(fs.readFileSync(new URL('../data/live-candidates.json', import.meta.url), 'utf8'));
assert.ok(snapshot.candidates.length >= 8, 'fresh snapshot should contain multiple real candidates');

const dayBase = {
  company: 'ランスタッド',
  city: '大田区',
  station: '流通センター',
  shift: 'day',
  product: 'トレカ',
  role: 'physical',
  period: '長期',
  tasks: ['ケース収納', '検品', '封入'],
  baseHourly: 1750
};

const day = compareLiveCandidates(dayBase, snapshot.candidates, new Date('2026-09-09T04:58:00+09:00'));

// Three media rows represent one underlying 1,900-yen day job and must collapse.
assert.equal(day.sameWorkCandidateCount, 3);
assert.equal(day.companyCount, 1);
assert.ok(day.bestHigher, 'a higher same-work candidate should exist');
assert.equal(day.bestHigher.baseHourly, 1900);
assert.equal(day.bestHigher.company, 'パーソルフィールドスタッフ');
assert.equal(day.bestHigher.duplicateCount, 3);
assert.equal(day.bestHigher.sourceUrls.length, 3);
assert.ok(day.bestHigher.sameWorkRate >= 70 && day.bestHigher.sameWorkRate <= 99);

// The 1,950-yen office job is higher but must never outrank physical light work.
assert.notEqual(day.bestHigher.baseHourly, 1950);
assert.equal(day.candidates.some(x => x.baseHourly === 1950), false);

// A different-city current warehouse job must be rejected by location identity.
assert.equal(day.candidates.some(x => x.station === '南船橋'), false);

// Night premium headline must normalize to the real base hourly wage.
const nightPremium = snapshot.candidates.find(x => x.url.includes('FFBS112655'));
assert.ok(nightPremium);
assert.equal(normalizeBaseHourlyStrict(nightPremium.rawText).baseHourly, 1400);

const nightBase = {
  company: 'ランスタッド',
  city: '大田区',
  station: '流通センター',
  shift: 'night',
  product: 'トレカ',
  role: 'physical',
  period: '長期',
  tasks: ['ケース収納', '検品', '封入'],
  baseHourly: 1750
};
const night = compareLiveCandidates(nightBase, snapshot.candidates, new Date('2026-09-09T04:58:00+09:00'));
assert.ok(night.bestHigher);
assert.equal(night.bestHigher.baseHourly, 1900);
assert.ok(night.bestHigher.sameWorkRate <= 99);
assert.equal(night.bestHigher.shift, 'night');

console.log('live snapshot regression: OK');
