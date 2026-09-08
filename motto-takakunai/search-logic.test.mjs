import assert from 'node:assert/strict';
import {
  normalizeBaseHourly,
  extractShiftDetailed,
  canonicalizeTasks,
  candidateLocationGate,
  dedupeCrossMedia,
  sameWorkRate,
  classifyPostingStatus,
  generateSearchQueries,
  comparePeriod,
  chooseBestPerCompany
} from './search-logic.js';

// Night premium ranges: compare basic hourly rate, never the 25% premium display.
{
  const r = normalizeBaseHourly('夜勤 時給1,900円～2,375円 20:00～翌5:00');
  assert.equal(r.baseHourly, 1900);
  assert.equal(r.displayedHigh, 2375);
  assert.equal(r.reason, 'night_premium_range_use_low');
}

// A non-night variable range is ambiguous; keep the low edge but mark low confidence.
{
  const r = normalizeBaseHourly('時給1,700円～2,000円 日勤');
  assert.equal(r.baseHourly, 1700);
  assert.equal(r.reason, 'variable_hourly_range_needs_detail');
  assert.ok(r.confidence < 0.7);
}

// Explicit hours beat noisy metadata labels when possible.
{
  const r = extractShiftDetailed('勤務日：日勤 / 就業時間 20:00～翌5:00');
  assert.equal(r.shift, 'night');
  assert.equal(r.reason, 'explicit_start_time');
}

// Task wording across media should collapse to the same canonical work steps.
{
  const a = canonicalizeTasks([], 'カードの傷チェック、ラベルと注文を照合、システムへデータ入力');
  assert.deepEqual(a, ['入力', '検品', '照合'].sort());
}

// Broad search can discover nearby noise, but comparison must block a different station/city.
{
  assert.equal(candidateLocationGate(
    { city: '江東区', station: '潮見' },
    { city: '相模原市緑区', station: '橋本' }
  ).pass, false);
}

// Cross-media duplicate: same staffing company/site/shift/pay and semantically same tasks.
{
  const rows = [
    { company: 'パーソルフィールドスタッフ', city: '大田区', station: '流通センター', shift: 'night', baseHourly: 1900, product: 'トレカ', rawText: '傷チェック ラベル照合 データ入力', url: 'https://media-a.example/job/1' },
    { company: 'パーソルフィールドスタッフ', city: '大田区', station: '流通センター', shift: 'night', baseHourly: 1900, product: 'トレカ', rawText: '検品 リスト照合 PC入力', url: 'https://media-b.example/job/99' }
  ];
  const deduped = dedupeCrossMedia(rows);
  assert.equal(deduped.length, 1);
  assert.equal(deduped[0].duplicateCount, 2);
}

// Same location but opposite shift is not allowed to look highly identical.
{
  const rate = sameWorkRate(
    { city: '大田区', station: '流通センター', shift: 'day', product: 'トレカ', tasks: ['検品', '照合', '入力'] },
    { city: '大田区', station: '流通センター', shift: 'night', product: 'トレカ', tasks: ['検品', '照合', '入力'] }
  );
  assert.ok(rate <= 39);
  assert.ok(rate <= 99);
}

// Period mismatch is visible but deliberately low-weight; unknown period must not penalize.
{
  const diff = comparePeriod('長期（3か月以上）', '短期（3か月以内）');
  assert.equal(diff.relation, 'different');
  assert.ok(diff.penalty > 0 && diff.penalty <= 5);
  assert.equal(comparePeriod('長期', '期間未取得').penalty, 0);

  const sameWorkDifferentPeriod = sameWorkRate(
    { city: '大田区', station: '流通センター', shift: 'day', product: 'トレカ', tasks: ['検品', '照合', '入力'], period: '長期' },
    { city: '大田区', station: '流通センター', shift: 'day', product: 'トレカ', tasks: ['検品', '照合', '入力'], period: '短期3か月以内' }
  );
  assert.ok(sameWorkDifferentPeriod >= 90);
  assert.ok(sameWorkDifferentPeriod <= 99);
}

// One company = one row: similarity wins first, wage only breaks ties.
{
  const best = chooseBestPerCompany([
    { company: 'A派遣', sameWorkRate: 92, baseHourly: 1700, id: 'closer' },
    { company: 'A派遣', sameWorkRate: 70, baseHourly: 1950, id: 'higher-but-different' },
    { company: 'B派遣', sameWorkRate: 88, baseHourly: 1800, id: 'other-company' }
  ]);
  assert.equal(best.find(x => x.company === 'A派遣').id, 'closer');
  assert.equal(best.length, 2);
}

// Never infer ended merely from search disappearance; explicit end markers only.
{
  assert.equal(classifyPostingStatus('この求人は掲載終了しました').status, 'ended');
  assert.equal(classifyPostingStatus('求人詳細 時給1600円').status, 'recheck');
}

// Search generation must include both precise and company-free discovery queries.
{
  const qs = generateSearchQueries({ city: '大田区', station: '流通センター', product: 'トレカ', company: 'ランスタッド', shift: 'night', tasks: ['検品', '照合', '入力'] });
  assert.ok(qs.length >= 6);
  assert.ok(qs.some(q => q.includes('ランスタッド')));
  assert.ok(qs.some(q => !q.includes('ランスタッド') && q.includes('流通センター')));
}

console.log('search-logic regression tests passed');
