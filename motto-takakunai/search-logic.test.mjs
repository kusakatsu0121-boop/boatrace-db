import assert from 'node:assert/strict';
import {
  normalizeBaseHourly,
  extractShiftDetailed,
  canonicalizeTasks,
  candidateLocationGate,
  dedupeCrossMedia,
  sameWorkRate,
  classifyPostingStatus,
  generateSearchQueries
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
