import assert from 'node:assert/strict';
import { normalizeBaseHourlyStrict, compareLiveCandidates, inferCandidateFields } from '../live-candidate-pipeline.js';

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

// Current Tempstaff night pattern: 1900 base -> 2375 night premium.
assert.deepEqual(
  normalizeBaseHourlyStrict('夜勤専属 時給 1,900円～2,375円 20:00～翌5:00 ★20時～22時は1900円★22時～5時は2375円'),
  { baseHourly: 1900, confidence: 0.99, reason: 'night_premium_range_use_low' }
);

const inferred = inferCandidateFields({
  rawText: `会社名 | パーソルテンプスタッフ（株）
勤務地 | 東京都 大田区
東京モノレール 流通センター駅 徒歩3分
就業時間 | 20:00～翌5:00
給与 | 時給 1,900円～2,375円
職種 | 軽作業
内容 | トレーディングカードの検品・ケース封入・梱包
期間 | 2026年09月中旬～長期`
});
assert.equal(inferred.company, 'パーソルテンプスタッフ');
assert.equal(inferred.city, '大田区');
assert.equal(inferred.station, '流通センター');
assert.equal(inferred.shift, 'night');
assert.equal(inferred.product, 'トレカ');
assert.equal(inferred.role, 'physical');
assert.ok(inferred.tasks.includes('検品'));
assert.ok(inferred.tasks.includes('梱包'));

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
  },
  {
    rawText: `会社名 | パーソルテンプスタッフ（株） 勤務地 | 東京都 大田区 東京モノレール 流通センター駅 徒歩3分 期間 | 2026年09月中旬～長期 就業時間 | 20:00～翌5:00 給与 | 時給 1,900円～2,375円 内容 | トレーディングカードの検品・ケース封入・梱包 WEBで応募`
  }
], new Date('2026-09-09T01:00:00+09:00'));

assert.equal(result.preparedCount, 4);
assert.equal(result.trustedCount, 3); // ended A row is rejected before ranking
assert.ok(result.companyCount >= 1); // day-shift B cannot become same-work winner
assert.equal(result.bestHigher.baseHourly, 1900);
assert.ok(result.bestHigher.sameWorkRate < 100);

console.log('live candidate pipeline regression: OK');
