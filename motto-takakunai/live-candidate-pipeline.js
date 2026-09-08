// Live candidate pipeline for 「もっと高くない？」
// Search adapters feed raw candidates into this module. The pipeline validates
// pay/status before a candidate is allowed to become the "highest wage" result.

import {
  canonicalizeTasks,
  classifyPostingStatus,
  dedupeCrossMedia,
  sameWorkRate,
  chooseBestPerCompany,
  normalizeText,
  extractShift
} from './search-logic.js';

export function normalizeBaseHourlyStrict(input = '') {
  const s = normalizeText(input).replace(/,/g, '');

  // Explicit base/normal wage wins even if a headline mentions a higher night wage.
  const explicit = s.match(/(?:基本時給|通常時給)\s*[:：]?\s*(\d{3,4})(?:\s*円)?/);
  if (explicit) {
    return { baseHourly: Number(explicit[1]), confidence: 0.99, reason: 'explicit_base_hourly' };
  }

  // A range close to x1.25 is a common base + statutory night-premium display.
  const range = s.match(/時給\s*[:：]?\s*(\d{3,4})\s*(?:円)?\s*[～~-]\s*(\d{3,4})(?:\s*円)?/);
  if (range) {
    const low = Number(range[1]);
    const high = Number(range[2]);
    const premiumLike = low > 0 && Math.abs(high / low - 1.25) < 0.025;
    if (premiumLike && /夜勤|深夜|22時|翌\s*5時|20:00|21:00|22:00/.test(s)) {
      return { baseHourly: low, confidence: 0.99, reason: 'night_premium_range_use_low' };
    }
    return { baseHourly: low, confidence: 0.8, reason: 'hourly_range_use_low' };
  }

  const matches = [...s.matchAll(/時給\s*[:：]?\s*(\d{3,4})(?:\s*円)?/g)];
  for (const m of matches) {
    const before = s.slice(Math.max(0, m.index - 32), m.index);
    // Only reject a wage when the wage itself is explicitly labelled as a premium.
    // A valid base wage is often followed later by "22時～翌5時は25%割増"; that
    // downstream note must not invalidate the preceding base hourly amount.
    if (/深夜|夜間|割増|22時|翌\s*5時|25%/.test(before)) continue;
    return { baseHourly: Number(m[1]), confidence: 0.95, reason: 'non_premium_hourly' };
  }

  return { baseHourly: null, confidence: 0, reason: 'base_hourly_not_verified' };
}

function inferCompany(text = '') {
  const s = String(text);
  const explicit = s.match(/(?:会社名|派遣元|担当会社|企業名)\s*[:：|]?\s*([^\n|]{2,40})/);
  if (explicit) return explicit[1].trim().replace(/[（(].*$/, '').trim();
  const known = [
    'パーソルフィールドスタッフ', 'パーソルテンプスタッフ', 'ランスタッド',
    'アデコ', 'パソナ', 'スタッフサービス', 'マンパワーグループ'
  ];
  return known.find(name => s.includes(name)) || '';
}

function inferCity(text = '') {
  const s = String(text);
  const matches = [...s.matchAll(/(?:東京都\s*)?([一-龠ぁ-んァ-ヶー]+区)/g)];
  return matches.length ? matches[matches.length - 1][1] : '';
}

function inferStation(text = '') {
  const s = String(text);
  const preferred = s.match(/(?:アクセス|勤務地)[\s\S]{0,120}?([一-龠ぁ-んァ-ヶー()（）・]+)駅/);
  if (preferred) return preferred[1].replace(/.*[／/]/, '').trim();
  const any = s.match(/([一-龠ぁ-んァ-ヶー()（）・]+)駅/);
  return any ? any[1].replace(/.*[／/]/, '').trim() : '';
}

function inferPeriod(text = '') {
  const s = String(text);
  const m = s.match(/(?:期間|雇用形態)[\s|:：]*([^\n|]{0,45}(?:長期|短期|\d+\s*(?:か月|ヶ月|ヵ月|カ月|月)\s*(?:以上|以内)?))/);
  if (m) return m[1].trim();
  if (/長期/.test(s)) return '長期';
  if (/短期/.test(s)) return '短期';
  return '';
}

function inferProduct(text = '') {
  const s = normalizeText(text);
  if (/トレカ|トレーディングカード/.test(s)) return 'トレカ';
  if (/スマホ|スマートフォン|携帯端末/.test(s)) return 'スマホ';
  if (/pc|パソコン/.test(s)) return 'PC';
  return '';
}

function inferRole(tasks = [], text = '') {
  const t = new Set(tasks);
  const office = ['問合せ', '入力', '資材発注', '在庫管理'].filter(x => t.has(x)).length;
  const physical = ['検品', '照合', '開梱', '梱包', '発送', '仕分け', '棚入れ', '入荷', 'ピッキング', '撮影', 'スキャン', 'ケース収納', '封入', '初期化'].filter(x => t.has(x)).length;
  const s = normalizeText(text);
  if (/一般事務|oa事務|問い合わせ対応|メール対応/.test(s) && office >= physical) return 'office';
  if (physical >= 2 && office <= 1) return 'physical';
  return 'mixed';
}

export function inferCandidateFields(raw = {}) {
  const rawText = String(raw.rawText || raw.statusText || raw.wageText || '');
  const tasks = canonicalizeTasks(raw.tasks || [], rawText);
  return {
    company: raw.company || inferCompany(rawText),
    city: raw.city || inferCity(rawText),
    station: raw.station || inferStation(rawText),
    shift: raw.shift || extractShift(rawText),
    product: raw.product || inferProduct(rawText),
    period: raw.period || inferPeriod(rawText),
    role: raw.role || inferRole(tasks, rawText),
    tasks
  };
}

function freshManualVerification(raw = {}, now = new Date()) {
  if (raw.activeVerified !== true || !raw.verifiedAt) return false;
  const verifiedAt = new Date(raw.verifiedAt);
  if (Number.isNaN(verifiedAt.getTime())) return false;
  const ageMs = now.getTime() - verifiedAt.getTime();
  return ageMs >= -5 * 60 * 1000 && ageMs <= 24 * 60 * 60 * 1000;
}

function comparisonEvidence(base = {}, row = {}) {
  const baseTasks = new Set(canonicalizeTasks(base.tasks || [], base.rawText || ''));
  const rowTasks = new Set(canonicalizeTasks(row.tasks || [], row.rawText || ''));
  const commonTasks = [...baseTasks].filter(task => rowTasks.has(task));
  const normalize = value => normalizeText(value || '');
  const roleConflict = !!base.role && !!row.role && base.role !== 'mixed' && row.role !== 'mixed' && base.role !== row.role;
  return {
    cityMatch: !!base.city && !!row.city && normalize(base.city) === normalize(row.city),
    stationMatch: !!base.station && !!row.station && normalize(base.station) === normalize(row.station),
    shiftMatch: !!base.shift && base.shift !== 'unknown' && base.shift === row.shift,
    productMatch: !!base.product && !!row.product && normalize(base.product) === normalize(row.product),
    roleMatch: !roleConflict,
    commonTasks,
    commonTaskCount: commonTasks.length,
    baseTaskCount: baseTasks.size,
    candidateTaskCount: rowTasks.size
  };
}

export function prepareLiveCandidate(raw = {}, now = new Date()) {
  const rawText = String(raw.rawText || '');
  const wage = normalizeBaseHourlyStrict(rawText || raw.wageText || '');
  const posting = classifyPostingStatus(rawText || raw.statusText || '', now);
  const inferred = inferCandidateFields(raw);

  // A search/browser adapter may have opened the detail URL and verified it moments ago.
  // This can upgrade only an uncertain/recheck page. Explicit ended markers always win.
  const manuallyVerifiedActive = posting.status !== 'ended' && freshManualVerification(raw, now);
  const postingStatus = manuallyVerifiedActive ? 'active' : posting.status;
  const postingConfidence = manuallyVerifiedActive ? Math.max(posting.confidence, 0.98) : posting.confidence;
  const postingReason = manuallyVerifiedActive ? 'fresh_detail_page_verification' : posting.reason;

  return {
    ...raw,
    ...inferred,
    baseHourly: wage.baseHourly,
    wageConfidence: wage.confidence,
    wageReason: wage.reason,
    postingStatus,
    postingConfidence,
    postingReason
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
    sameWorkRate: sameWorkRate(baseJob, row),
    sameWorkReasons: comparisonEvidence(baseJob, row)
  }));

  // 70 is a candidate threshold, not a claim of identity. UI still exposes 0-99 + reasons.
  const sameWorkCandidates = withRates.filter(row => row.sameWorkRate >= 70);
  const crossMediaDeduped = dedupeCrossMedia(sameWorkCandidates);
  const perCompany = chooseBestPerCompany(crossMediaDeduped);

  const higher = perCompany
    .filter(row => row.baseHourly > Number(baseJob.baseHourly || 0))
    .sort((a, b) => b.baseHourly - a.baseHourly || b.sameWorkRate - a.sameWorkRate);

  const rejectionSummary = prepared.reduce((acc, row) => {
    if (row.postingStatus === 'ended') acc.ended += 1;
    else if (row.postingStatus !== 'active') acc.statusUnverified += 1;
    if (!Number.isFinite(row.baseHourly) || row.baseHourly <= 0) acc.wageUnverified += 1;
    return acc;
  }, { ended: 0, statusUnverified: 0, wageUnverified: 0 });

  return {
    preparedCount: prepared.length,
    trustedCount: trusted.length,
    sameWorkCandidateCount: sameWorkCandidates.length,
    companyCount: perCompany.length,
    rejectionSummary,
    rejected: prepared.filter(row => row.postingStatus !== 'active' || !Number.isFinite(row.baseHourly)),
    candidates: perCompany.sort((a, b) => b.baseHourly - a.baseHourly || b.sameWorkRate - a.sameWorkRate),
    bestHigher: higher[0] || null
  };
}
