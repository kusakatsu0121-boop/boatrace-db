import assert from 'node:assert/strict';
import fs from 'node:fs';
import { normalizeBaseHourlyStrict, compareLiveCandidates, inferCandidateFields, prepareLiveCandidate, promoteDiscoveryFromDetail } from '../live-candidate-pipeline.js';

assert.deepEqual(normalizeBaseHourlyStrict('深夜時給2000円！ 給与 時給1600円 22時～翌5時は25%割増'), { baseHourly: 1600, confidence: 0.95, reason: 'non_premium_hourly' });
assert.equal(normalizeBaseHourlyStrict('基本時給 1750円／深夜時給2188円').baseHourly, 1750);
assert.equal(normalizeBaseHourlyStrict('深夜時給2188円のみ記載').baseHourly, null);
assert.deepEqual(normalizeBaseHourlyStrict('夜勤専属 時給 1,900円～2,375円 20:00～翌5:00 ★20時～22時は1900円★22時～5時は2375円'), { baseHourly: 1900, confidence: 0.99, reason: 'night_premium_range_use_low' });

const inferred = inferCandidateFields({ rawText: `会社名 | パーソルテンプスタッフ（株）\n勤務地 | 東京都 大田区\n東京モノレール 流通センター駅 徒歩3分\n就業時間 | 20:00～翌5:00\n給与 | 時給 1,900円～2,375円\n職種 | 軽作業\n内容 | トレーディングカードの検品・ケース封入・梱包\n期間 | 2026年09月中旬～長期` });
assert.equal(inferred.company, 'パーソルテンプスタッフ');
assert.equal(inferred.city, '大田区');
assert.equal(inferred.station, '流通センター');
assert.equal(inferred.shift, 'night');
assert.equal(inferred.product, 'トレカ');
assert.equal(inferred.role, 'physical');
assert.ok(inferred.tasks.includes('検品'));
assert.ok(inferred.tasks.includes('梱包'));

const freshVerified = prepareLiveCandidate({ rawText: '時給1840円 トレカ 軽作業 データ入力 東京都大田区 流通センター駅 9:00～18:00', activeVerified: true, verifiedAt: '2026-09-09T03:50:00+09:00' }, new Date('2026-09-09T03:56:00+09:00'));
assert.equal(freshVerified.postingStatus, 'active');
assert.equal(freshVerified.postingReason, 'fresh_detail_page_verification');

const endedVerified = prepareLiveCandidate({ rawText: '時給1900円 掲載終了', activeVerified: true, verifiedAt: '2026-09-09T03:55:00+09:00' }, new Date('2026-09-09T03:56:00+09:00'));
assert.equal(endedVerified.postingStatus, 'ended');

// Search-list discovery cannot rank by itself, but a verified detail page can safely promote it.
const promoted1700 = promoteDiscoveryFromDetail(
  { source: 'randstad search/list', observedAt: '2026-09-09T08:59:00+09:00', summary: '流通センター徒歩5分 トレカ夜勤 時給1700円' },
  { id: 'RANDSTAD-1700-DETAIL', company: 'ランスタッド', url: 'https://www.randstad.co.jp/factory/example/1700/', rawText: '会社名 ランスタッド 東京都大田区平和島 流通センター駅 徒歩5分 夜勤 トレカ 検品 入出荷 時給1700円 WEBから応募する' },
  new Date('2026-09-09T09:00:00+09:00')
);
assert.equal(promoted1700.promoted, true);
assert.equal(promoted1700.candidate.activeVerified, true);
assert.equal(normalizeBaseHourlyStrict(promoted1700.candidate.rawText).baseHourly, 1700);

const rejectEndedPromotion = promoteDiscoveryFromDetail({}, { url: 'https://example.test/ended', rawText: '時給1900円 この求人は掲載終了しました' }, new Date('2026-09-09T09:00:00+09:00'));
assert.equal(rejectEndedPromotion.promoted, false);
assert.equal(rejectEndedPromotion.reason, 'detail_page_ended');

const base = { city: '大田区', station: '流通センター', shift: 'night', product: 'トレカ', role: 'physical', period: '長期', tasks: ['検品', 'ケース収納', '梱包'], baseHourly: 1750 };
const result = compareLiveCandidates(base, [
  { company: 'A社', city: '大田区', station: '流通センター', shift: 'night', product: 'トレカ', role: 'physical', period: '長期', tasks: ['検品', 'ケース収納', '梱包'], rawText: '時給1900円 応募する 募集人数1名' },
  { company: 'A社', city: '大田区', station: '流通センター', shift: 'night', product: 'トレカ', role: 'physical', period: '長期', tasks: ['検品', 'ケース収納', '梱包'], rawText: '時給1900円 掲載終了' },
  { company: 'B社', city: '大田区', station: '流通センター', shift: 'day', product: 'トレカ', role: 'physical', period: '長期', tasks: ['検品', 'ケース収納', '梱包'], rawText: '時給1950円 応募する' },
  { rawText: `会社名 | パーソルテンプスタッフ（株） 勤務地 | 東京都 大田区 東京モノレール 流通センター駅 徒歩3分 期間 | 2026年09月中旬～長期 就業時間 | 20:00～翌5:00 給与 | 時給 1,900円～2,375円 内容 | トレーディングカードの検品・ケース封入・梱包`, activeVerified: true, verifiedAt: '2026-09-09T00:55:00+09:00' }
], new Date('2026-09-09T01:00:00+09:00'));
assert.equal(result.preparedCount, 4);
assert.equal(result.trustedCount, 3);
assert.ok(result.companyCount >= 1);
assert.equal(result.bestHigher.baseHourly, 1900);
assert.ok(result.bestHigher.sameWorkRate < 100);
assert.equal(result.bestHigher.sameWorkReasons.stationMatch, true);
assert.equal(result.bestHigher.sameWorkReasons.shiftMatch, true);
assert.ok(result.bestHigher.sameWorkReasons.commonTaskCount >= 2);
assert.equal(result.rejectionSummary.ended, 1);

const liveSnapshot = JSON.parse(fs.readFileSync(new URL('../live-candidates.json', import.meta.url), 'utf8'));
const snapshotResult = compareLiveCandidates(base, liveSnapshot.candidates, new Date('2026-09-09T08:30:00+09:00'));
assert.equal(snapshotResult.preparedCount, liveSnapshot.candidates.length);
assert.equal(liveSnapshot.candidates.length, 8);
assert.ok(snapshotResult.trustedCount >= 8);
assert.equal(snapshotResult.bestHigher.baseHourly, 1900);
assert.ok(snapshotResult.bestHigher.sameWorkRate >= 70 && snapshotResult.bestHigher.sameWorkRate <= 99);
assert.equal(snapshotResult.bestHigher.sameWorkReasons.stationMatch, true);
assert.equal(snapshotResult.bestHigher.sameWorkReasons.shiftMatch, true);
assert.ok(snapshotResult.candidates.every(x => x.sameWorkRate <= 99));
assert.ok(!snapshotResult.candidates.some(x => x.id === 'TS260701398')); // day office 1950
assert.ok(!snapshotResult.candidates.some(x => x.id === 'RANDSTAD-FTKB109739')); // food packing 1600
assert.equal(normalizeBaseHourlyStrict(liveSnapshot.candidates.find(x => x.id === 'RANDSTAD-FTKB109739').rawText).baseHourly, 1600);

console.log('live candidate pipeline regression: OK');
