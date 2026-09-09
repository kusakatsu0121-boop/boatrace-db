import http from 'node:http';
import fs from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { inferCandidateFields, normalizeBaseHourlyStrict, compareLiveCandidates } from './live-candidate-pipeline.js';
import { searchAndVerifyCandidates } from './live-search-adapter.js';

const PORT = Number(process.env.PORT || 10000);
const SNAPSHOT_PATH = new URL('./live-candidates.json', import.meta.url);
const MAX_BODY = 220_000;

function json(res, status, body) {
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'access-control-allow-origin': '*',
    'access-control-allow-methods': 'GET,POST,OPTIONS',
    'access-control-allow-headers': 'content-type',
    'cache-control': 'no-store'
  });
  res.end(JSON.stringify(body));
}

async function readBody(req) {
  let size = 0;
  const chunks = [];
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY) throw new Error('body_too_large');
    chunks.push(chunk);
  }
  const raw = Buffer.concat(chunks).toString('utf8');
  return raw ? JSON.parse(raw) : {};
}

function parseBaseJob(rawText = '') {
  const wage = normalizeBaseHourlyStrict(rawText);
  const inferred = inferCandidateFields({ rawText });
  return {
    rawText,
    baseHourly: wage.baseHourly,
    wageConfidence: wage.confidence,
    wageReason: wage.reason,
    ...inferred
  };
}

async function freshSnapshotCandidates(now = new Date()) {
  try {
    const parsed = JSON.parse(await fs.readFile(SNAPSHOT_PATH, 'utf8'));
    const ttl = Number(parsed.ttl_hours || 24) * 3600_000;
    const rows = Array.isArray(parsed.candidates) ? parsed.candidates : [];
    return rows.filter(row => {
      if (row.activeVerified !== true || !row.verifiedAt) return false;
      const t = new Date(row.verifiedAt).getTime();
      if (!Number.isFinite(t)) return false;
      const age = now.getTime() - t;
      return age >= -300_000 && age <= ttl;
    });
  } catch {
    return [];
  }
}

function publicCandidate(row) {
  return {
    id: row.id || '',
    company: row.company || '',
    url: row.url || '',
    baseHourly: row.baseHourly,
    sameWorkRate: Math.min(99, Math.max(0, Number(row.sameWorkRate || 0))),
    sameWorkReasons: row.sameWorkReasons || {},
    city: row.city || '',
    station: row.station || '',
    shift: row.shift || 'unknown',
    product: row.product || '',
    role: row.role || '',
    tasks: row.tasks || [],
    period: row.period || '',
    postingStatus: row.postingStatus || '',
    verifiedAt: row.verifiedAt || null,
    duplicateCount: row.duplicateCount || 1,
    sourceUrls: row.sourceUrls || (row.url ? [row.url] : [])
  };
}

async function compare(rawText, now = new Date()) {
  const baseJob = parseBaseJob(rawText);
  if (!Number.isFinite(baseJob.baseHourly) || baseJob.baseHourly <= 0) {
    return { status: 422, body: { ok: false, error: 'base_hourly_not_verified', message: '基本時給を確認できませんでした。深夜割増後の時給だけでなく、通常の時給が分かる求人本文を貼ってください。' } };
  }
  if (!baseJob.station && !baseJob.city) {
    return { status: 422, body: { ok: false, error: 'location_not_verified', message: '勤務地または最寄駅を確認できませんでした。勤務地が含まれる求人本文を貼ってください。' } };
  }

  const live = await searchAndVerifyCandidates(baseJob, fetch, now, {
    maxQueries: 4,
    maxUrls: 16,
    maxDetails: 12,
    concurrency: 3,
    searchTimeoutMs: 6000,
    detailTimeoutMs: 7000
  });
  const snapshot = await freshSnapshotCandidates(now);
  const seen = new Set(live.verified.map(x => x.url));
  const mergedRaw = [...live.verified, ...snapshot.filter(x => !seen.has(x.url))];
  const compared = compareLiveCandidates(baseJob, mergedRaw, now);

  return {
    status: 200,
    body: {
      ok: true,
      generatedAt: now.toISOString(),
      mode: live.verified.length ? (snapshot.length ? 'live_search_plus_fresh_snapshot' : 'live_search') : (snapshot.length ? 'fresh_snapshot_fallback' : 'live_search_no_verified_candidate'),
      baseJob: {
        baseHourly: baseJob.baseHourly,
        company: baseJob.company || '',
        city: baseJob.city || '',
        station: baseJob.station || '',
        shift: baseJob.shift || 'unknown',
        product: baseJob.product || '',
        role: baseJob.role || '',
        tasks: baseJob.tasks || [],
        period: baseJob.period || ''
      },
      search: {
        queries: live.queries,
        discoveredUrls: live.urls.length,
        detailChecked: live.detailChecked,
        liveVerified: live.verified.length,
        freshSnapshotAdded: Math.max(0, mergedRaw.length - live.verified.length),
        diagnostics: live.diagnostics,
        rejectedDetails: live.rejected.slice(0, 12)
      },
      counts: {
        prepared: compared.preparedCount,
        trusted: compared.trustedCount,
        sameWork: compared.sameWorkCandidateCount,
        companies: compared.companyCount,
        rejections: compared.rejectionSummary
      },
      bestHigher: compared.bestHigher ? publicCandidate(compared.bestHigher) : null,
      candidates: compared.candidates.map(publicCandidate)
    }
  };
}

const server = http.createServer(async (req, res) => {
  try {
    if (req.method === 'OPTIONS') return json(res, 204, {});
    const u = new URL(req.url || '/', 'http://localhost');
    if (req.method === 'GET' && u.pathname === '/health') {
      return json(res, 200, { ok: true, service: 'motto-takakunai-api', now: new Date().toISOString() });
    }
    if (req.method === 'POST' && u.pathname === '/api/compare') {
      const body = await readBody(req);
      const rawText = String(body.rawText || body.text || '').trim();
      if (rawText.length < 20) return json(res, 400, { ok: false, error: 'job_text_too_short' });
      const result = await compare(rawText);
      return json(res, result.status, result.body);
    }
    return json(res, 404, { ok: false, error: 'not_found' });
  } catch (error) {
    const message = error?.message === 'body_too_large' ? 'body_too_large' : 'internal_error';
    return json(res, message === 'body_too_large' ? 413 : 500, { ok: false, error: message, detail: process.env.NODE_ENV === 'production' ? undefined : String(error?.stack || error) });
  }
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`motto-takakunai-api listening on ${PORT}`);
});
