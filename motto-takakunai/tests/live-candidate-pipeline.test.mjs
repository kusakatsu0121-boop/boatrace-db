import assert from 'node:assert/strict';
import { normalizeBaseHourlyStrict, compareLiveCandidates } from '../live-candidate-pipeline.js';

// Real-world pattern: headline advertises night premium first, body states base wage later.
assert.deepEqual(
  normalizeBaseHourlyStrict('深夜時給2000円！ 給与 時給1600円 22時～翌5時は25%割増'),
  { baseHourly: 1600, confidence: 0.95, reason: 'non_premium_hourly' }
);

assert.equal(
  normalizeBaseHourlyStrict('基本時給 1750円／深夜時給2188円').baseHourly,
  1750
);

assert.equal(
  normalizeBaseHourlyStrict('深夜時給2188円のみ記載').baseHourly,
  null
);

const base = {
  city: '大田区',
  station: '流通センター',
  shift: 'night',
  product: 'トレカ',
  role: 'physical',
  period: '長期',
  tasks: ['検品', 'ケース収納', '梱包'],
  baseHourly: 1750
};

const result = compareLiveCandidates(base, [
  {
    company: 'A社', city: '大田区', station: '流通センター', shift: 'night', product: 'トレカ', role: 'physical', period: '長期',
    tasks: ['検品', 'ケース収納', '梱包'],
    rawText: '時給1900円 応募する 募集人数1名'
  },
  {
    company: 'A社', city: '大田区', station: '流通センター', shift: 'night', product: 'トレカ', role: 'physical', period: '長期',
    tasks: ['検品', 'ケース収納', '梱包'],
    rawText: '時給1900円 掲載終了'
  },
  {
    company: 'B社', city: '大田区', station: '流通センター', shift: 'day', product: 'トレカ', role: 'physical', period: '長期',
    tasks: ['検品', 'ケース収納', '梱包'],
    rawText: '時給1950円 応募する'
  }
], new Date('2026-09-09T01:00:00+09:00'));

assert.equal(result.preparedCount, 3);
assert.equal(result.trustedCount, 2); // ended A row is rejected before ranking
assert.equal(result.companyCount, 1); // day-shift B cannot pass same-work threshold
assert.equal(result.bestHigher.company, 'A社');
assert.equal(result.bestHigher.baseHourly, 1900);
assert.ok(result.bestHigher.sameWorkRate < 100);

console.log('live candidate pipeline regression: OK');
