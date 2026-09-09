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
<h1>トレーディングカードの検品</h1>
<div>会社名 パーソルテンプスタッフ</div>
<div>勤務地 東京都大田区 流通センター駅 徒歩3分</div>
<div>就業時間 20:00～翌5:00</div>
<div>給与 時給1,900円～2,375円</div>
<div>仕事内容 トレカ 検品 ケース封入 梱包</div>
<button>応募する</button>
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

const endedFetch = async () => new Response('<html><body>この求人は掲載終了しました 時給1,900円</body></html>', { status: 200 });
const ended = await verifyDetailUrl('https://www.tempstaff.co.jp/jbch/job/x', endedFetch, new Date('2026-09-09T09:00:00+09:00'));
assert.equal(ended.ok, false);
assert.equal(ended.reason, 'detail_ended');

console.log('live-search-adapter tests passed');
