import fs from 'node:fs';
import assert from 'node:assert/strict';

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');

assert.match(html, /TTL_HOURS=24/, 'public UI must enforce 24h verification TTL');
assert.match(html, /Math\.min\(99/, 'same-work score must remain capped at 99');
assert.doesNotMatch(html, /同じ仕事率[^\n]{0,30}100%/, 'public UI must never promise 100% same-work');
assert.doesNotMatch(html, /const\s+RAW\s*=/, 'legacy fixed RAW dataset must not return');
assert.match(html, /SNAPSHOT_AT=/, 'public UI must expose snapshot timestamp');
assert.match(html, /verifiedAt/, 'candidate freshness evidence must be retained');
assert.match(html, /data-job-link/, 'verified source job must be directly openable');
assert.match(html, /深夜割増/, 'public copy must explain premium wage normalization');

console.log('public index regression: OK');
