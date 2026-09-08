// Live candidate pipeline for 「もっと高くない？」
// Search adapters feed raw candidates into this module. The pipeline validates
// pay/status before a candidate is allowed to become the "highest wage" result.

import {
  canonicalizeTasks,
  classifyPostingStatus,
  dedupeCrossMedia,
  sameWorkRate,
  chooseBestPerCompany,
  normalizeText
} from './search-logic.js';

export function normalizeBaseHourlyStrict(input = '') {
  const s = normalizeText(input).replace(/,/g, '');

  // Explicit base/normal wage wins even if a headline mentions a higher night wage.
  const explicit = s.match(/(?:基本時給|通常時給)\s*[:：]?\s*(\d{3,4})(?:\s*円)?/);
  if (explicit) {
    return { baseHourly: Number(explicit[1]), confidence: 0.99, reason: 'explicit_base_hourly' };
  }

  const matches = [...s.matchAll(/時給\s*[:：]?\s*(\d{3,4})(?:\s*円)?/g)];
  for (const m of matches) {
    const before = s.slice(Math.max(0, m.index - 32), m.index);
    const after = s.slice(m.index, Math.min(s.length, m.index + 48));
    if (/深夜|夜間|割増|22時|翌\s*5時|25%/.test(before)) continue;
    if (/深夜(?:帯)?は?\s*\d{3,4}|22時.*25%|25%.*割増/.test(after) && matches.length === 1) continue;
    return { baseHourly: Number(m[1]), confidence: 0.95, reason: 'non_premium_hourly' };
  }

  return { baseHourly: null, confidence: 0, reason: 'base_hourly_not_verified' };
}

export function prepareLiveCandidate(raw = {}, now = new Date()) {
  const rawText = String(raw.rawText || '');
  const wage = normalizeBaseHourlyStrict(rawText || raw.wageText || '');
  const posting = classifyPostingStatus(rawText || raw.statusText || '', now);
  const tasks = canonicalizeTasks(raw.tasks || [], rawText);

  return {
    ...raw,
    baseHourly: wage.baseHourly,
    wageConfidence: wage.confidence,
    wageReason: wage.reason,
    postingStatus: posting.status,
    postingConfidence: posting.confidence,
    postingReason: posting.reason,
    tasks
  };
}

export function compareLiveCandidates(baseJob, rawCandidates = [], now = new Date()) {
  const prepared = rawCandidates.map(row => prepareLiveCandidate(row, now));

  // Hard trust gates: only active pages with a verified base hourly wage can win.
  const trusted = prepared.filter(row =>
    row.postingStatus === 'active' &&
    Number.isFinite(row.baseHourly) &&
    row.baseHourly > 0
  );

  const withRates = trusted.map(row => ({
    ...row,
    sameWorkRate: sameWorkRate(baseJob, row)
  }));

  // 70 is a candidate threshold, not a claim of identity. UI still exposes 0-99 + reasons.
  const sameWorkCandidates = withRates.filter(row => row.sameWorkRate >= 70);
  const crossMediaDeduped = dedupeCrossMedia(sameWorkCandidates);
  const perCompany = chooseBestPerCompany(crossMediaDeduped);

  const higher = perCompany
    .filter(row => row.baseHourly > Number(baseJob.baseHourly || 0))
    .sort((a, b) => b.baseHourly - a.baseHourly || b.sameWorkRate - a.sameWorkRate);

  return {
    preparedCount: prepared.length,
    trustedCount: trusted.length,
    sameWorkCandidateCount: sameWorkCandidates.length,
    companyCount: perCompany.length,
    rejected: prepared.filter(row => row.postingStatus !== 'active' || !Number.isFinite(row.baseHourly)),
    candidates: perCompany.sort((a, b) => b.baseHourly - a.baseHourly || b.sameWorkRate - a.sameWorkRate),
    bestHigher: higher[0] || null
  };
}
