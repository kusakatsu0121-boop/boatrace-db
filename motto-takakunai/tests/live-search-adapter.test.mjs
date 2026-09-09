import assert from 'node:assert/strict';
import { extractDuckDuckGoUrls, htmlToText, isAllowedJobUrl, verifyDetailUrl, discoverUrlsForJob } from '../live-search-adapter.js';

assert.equal(isAllowedJobUrl('https://www.tempstaff.co.jp/jbch/job/x'), true);
assert.equal(isAllowedJobUrl('https://example.com/job/x'), false);
assert.match(htmlToText('<html><style>x{}</style><body>時給1,900円 <b>応募する</b></body></html>'), /時給1,900円 応募する/);

const ddg = `
<a class="result__a" href="//duckduckgo.com/l/?uddg=${encodeURIComponent('https://www.tempstaff.co.jp/jbch/job/tokyo/13111/sd-66/TS0001/')}">A</a>
<a href="//duckduckgo.com/l/?uddg=${encodeURIComponent('https://www.randstad.co.jp/factory/detail/wnFTKB0001/')}">B</a>`;
const urls = extractDuckDuckGoUrls(ddg);
assert.equal(urls.length, 2);
assert.ok(urls.some(x => x.includes('tempstaff.co.jp')));

const detailHtml = `<!doctype html><html><body>
<h1>トレーディングカードの検品・ケース封入・梱包</h1>
<div>会社名 パーソルテンプスタッフ</div>
<div>勤務地 東京都大田区平和島 東京モノレール 流通センター駅 徒歩3分</div>
<div>就業時間 20:00～翌5:00 休憩60分 週5日勤務</div>
<div>給与 時給1,900円～2,375円 20時～22時は1,900円 22時～翌5時は深夜割増2,375円</div>
<div>期間 2026年09月中旬～長期 雇用形態 派遣</div>
<div>仕事内容 トレカの検品、鑑定結果チェック、カードのケース封入、ラベル確認、梱包、出荷準備。未経験可。</div>
<div>通勤交通費 全額支給 社会保険あり 有給休暇あり</div>
<button>WEBで応募する</button>
</body></html>`;
const fakeFetch = async url => {
  if (String(url).includes('duckduckgo.com')) return new Response(ddg, { status: 200 });
  return new Response(detailHtml, { status: 200 });
};

const verified = await verifyDetailUrl('https://www.tempstaff.co.jp/jbch/job/tokyo/13111/sd-66/TS0001/', fakeFetch, new Date('2026-09-09T09:00:00+09:00'));
assert.equal(verified.ok, true);
assert.equal(verified.candidate.activeVerified, true);

const discovered = await discoverUrlsForJob({ station: '流通センター', city: '大田区', product: 'トレカ', tasks: ['検品', '梱包'], shift: 'night', rawText: '' }, fakeFetch, { maxQueries: 1, maxUrls: 10 });
assert.equal(discovered.urls.length, 2);

const endedFetch = async () => new Response('<html><body>この求人は掲載終了しました。募集は終了しています。給与 時給1,900円。勤務地 東京都大田区 流通センター駅。仕事内容 トレカ検品・梱包。詳細情報を表示できません。応募受付終了。</body></html>', { status: 200 });
const ended = await verifyDetailUrl('https://www.tempstaff.co.jp/jbch/job/x', endedFetch, new Date('2026-09-09T09:00:00+09:00'));
assert.equal(ended.ok, false);
assert.equal(ended.reason, 'detail_ended');

console.log('live-search-adapter tests passed');
