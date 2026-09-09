import { classifyPostingStatus, generateSearchQueries, normalizeText, canonicalizeTasks } from './search-logic.js';
import { normalizeBaseHourlyStrict } from './live-candidate-pipeline.js';

const ALLOWED_HOSTS = [
  'tempstaff.co.jp',
  'randstad.co.jp',
  'adecco.com',
  'staffservice.co.jp',
  'haken.en-japan.com',
  'townwork.net',
  'baitoru.com',
  'froma.com'
];

function decodeEntities(s = '') {
  return String(s)
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>');
}

export function htmlToText(html = '') {
  return decodeEntities(String(html))
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<noscript[\s\S]*?<\/noscript>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function isAllowedJobUrl(value = '') {
  try {
    const u = new URL(value);
    if (!/^https?:$/.test(u.protocol)) return false;
    const host = u.hostname.toLowerCase().replace(/^www\./, '');
    return ALLOWED_HOSTS.some(d => host === d || host.endsWith(`.${d}`));
  } catch {
    return false;
  }
}

function resolveUrl(href = '', base = '') {
  try {
    return new URL(decodeEntities(href), base || undefined).toString();
  } catch {
    return '';
  }
}

function unwrapDuckDuckGo(href = '') {
  const decoded = decodeEntities(href);
  try {
    const u = new URL(decoded, 'https://duckduckgo.com');
    const target = u.searchParams.get('uddg');
    return target ? decodeURIComponent(target) : decoded;
  } catch {
    return decoded;
  }
}

export function extractDuckDuckGoUrls(html = '') {
  const out = [];
  for (const m of String(html).matchAll(/href=["']([^"']+)["']/gi)) {
    const candidate = unwrapDuckDuckGo(m[1]);
    if (isAllowedJobUrl(candidate)) out.push(candidate);
  }
  return [...new Set(out)];
}

export function extractDirectUrls(html = '') {
  const out = [];
  for (const m of String(html).matchAll(/https?:\/\/[^\s"'<>]+/gi)) {
    const candidate = decodeEntities(m[0]).replace(/[),.;]+$/, '');
    if (isAllowedJobUrl(candidate)) out.push(candidate);
  }
  return [...new Set(out)];
}

export function extractTempstaffJobUrls(html = '') {
  const out = [];
  for (const m of String(html).matchAll(/href=["']([^"']+)["']/gi)) {
    const candidate = resolveUrl(m[1], 'https://www.tempstaff.co.jp/');
    if (!candidate) continue;
    let u;
    try { u = new URL(candidate); } catch { continue; }
    const host = u.hostname.toLowerCase().replace(/^www\./, '');
    if (host !== 'tempstaff.co.jp') continue;
    if (!/^\/jbch\/job\//.test(u.pathname)) continue;
    if (!/\/(?:TS|BR)\d{8,}\/?$/i.test(u.pathname)) continue;
    u.hash = '';
    out.push(u.toString());
  }
  return [...new Set(out)];
}

async function fetchWithTimeout(fetchImpl, url, { timeoutMs = 6500, headers = {} } = {}) {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), timeoutMs);
  try {
    return await fetchImpl(url, {
      redirect: 'follow',
      signal: ac.signal,
      headers: {
        'user-agent': 'Mozilla/5.0 (compatible; MottoTakakunai/1.0; +https://motto-takakunai.onrender.com)',
        'accept-language': 'ja,en;q=0.7',
        ...headers
      }
    });
  } finally {
    clearTimeout(timer);
  }
}

function buildTempstaffTerms(baseJob = {}) {
  const station = String(baseJob.station || '').replace(/駅$/, '').trim();
  const city = String(baseJob.city || '').trim();
  const product = String(baseJob.product || '').trim();
  const shiftWord = baseJob.shift === 'night' ? '夜勤' : baseJob.shift === 'day' ? '日勤' : '';
  const tasks = canonicalizeTasks(baseJob.tasks || [], baseJob.rawText || '');
  const terms = [
    [station, product, shiftWord].filter(Boolean).join('　'),
    [city, shiftWord, 'あり'].filter(Boolean).join('　'),
    [station, product, tasks[0] || ''].filter(Boolean).join('　'),
    [station, tasks[0] || '', tasks[1] || ''].filter(Boolean).join('　')
  ].filter(x => x.length >= 2);
  return [...new Set(terms)].slice(0, 4);
}

async function discoverTempstaff(baseJob, fetchImpl, options = {}) {
  const terms = buildTempstaffTerms(baseJob);
  const diagnostics = [];
  const urls = [];
  const timeoutMs = options.providerTimeoutMs ?? 4500;
  const maxProviderQueries = options.maxProviderQueries ?? 3;
  const selectedTerms = terms.slice(0, maxProviderQueries);

  const responses = await Promise.all(selectedTerms.map(async term => {
    const searchUrl = `https://www.tempstaff.co.jp/jbch/keyword/${encodeURIComponent(term)}/`;
    try {
      const res = await fetchWithTimeout(fetchImpl, searchUrl, { timeoutMs });
      const body = await res.text();
      const found = res.ok ? extractTempstaffJobUrls(body) : [];
      return { term, searchUrl, status: res.status, found, error: null };
    } catch (error) {
      return { term, searchUrl, status: null, found: [], error: error?.name || 'provider_error' };
    }
  }));

  for (const r of responses) {
    diagnostics.push({ provider: 'tempstaff', query: r.term, status: r.status, found: r.found.length, error: r.error || undefined });
    for (const url of r.found) if (!urls.includes(url)) urls.push(url);
  }
  return { terms: selectedTerms, urls, diagnostics };
}

async function discoverExternalFallback(baseJob, fetchImpl, options = {}) {
  if (options.externalFallback === false) return { queries: [], urls: [], diagnostics: [] };
  const maxQueries = options.maxExternalQueries ?? 1;
  const queries = generateSearchQueries(baseJob).slice(0, maxQueries);
  const urls = [];
  const diagnostics = [];
  for (const query of queries) {
    try {
      const url = `https://html.duckduckgo.com/html/?q=${encodeURIComponent(query)}`;
      const res = await fetchWithTimeout(fetchImpl, url, { timeoutMs: options.externalSearchTimeoutMs ?? 2200 });
      const body = await res.text();
      const found = [...extractDuckDuckGoUrls(body), ...extractDirectUrls(body)];
      diagnostics.push({ provider: 'duckduckgo', query, status: res.status, found: found.length });
      for (const item of found) if (!urls.includes(item)) urls.push(item);
    } catch (error) {
      diagnostics.push({ provider: 'duckduckgo', query, error: error?.name || 'search_error', found: 0 });
    }
  }
  return { queries, urls, diagnostics };
}

export async function discoverUrlsForJob(baseJob, fetchImpl = fetch, options = {}) {
  const maxUrls = options.maxUrls ?? 16;
  const urls = [];
  const diagnostics = [];

  const direct = await discoverTempstaff(baseJob, fetchImpl, options);
  diagnostics.push(...direct.diagnostics);
  for (const item of direct.urls) {
    if (!urls.includes(item)) urls.push(item);
    if (urls.length >= maxUrls) break;
  }

  let external = { queries: [], urls: [], diagnostics: [] };
  const minimumDirectUrls = options.minimumDirectUrls ?? 4;
  if (urls.length < minimumDirectUrls) {
    external = await discoverExternalFallback(baseJob, fetchImpl, options);
    diagnostics.push(...external.diagnostics);
    for (const item of external.urls) {
      if (!urls.includes(item)) urls.push(item);
      if (urls.length >= maxUrls) break;
    }
  }

  return {
    queries: [...direct.terms, ...external.queries],
    urls: urls.slice(0, maxUrls),
    diagnostics
  };
}

function detailCompleteness(text = '') {
  const s = normalizeText(text);
  let score = 30;
  if (/時給/.test(s)) score += 15;
  if (/勤務地|アクセス|駅/.test(s)) score += 15;
  if (/勤務時間|就業時間|\d{1,2}:\d{2}/.test(s)) score += 15;
  if (/仕事内容|職種|業務内容/.test(s)) score += 15;
  if (/期間|長期|短期/.test(s)) score += 5;
  if (/応募する|webで応募|今すぐ応募/.test(s)) score += 5;
  return Math.min(100, score);
}

export async function verifyDetailUrl(url, fetchImpl = fetch, now = new Date(), options = {}) {
  try {
    const res = await fetchWithTimeout(fetchImpl, url, { timeoutMs: options.detailTimeoutMs ?? 7500 });
    if (!res.ok) return { ok: false, url, reason: `http_${res.status}` };
    const html = await res.text();
    const text = htmlToText(html);
    const status = classifyPostingStatus(text, now);
    if (status.status === 'ended') return { ok: false, url, reason: 'detail_ended' };
    if (text.length < 180) return { ok: false, url, reason: 'detail_too_short' };
    if (status.status !== 'active') return { ok: false, url, reason: 'active_not_verified' };
    const wage = normalizeBaseHourlyStrict(text);
    if (!Number.isFinite(wage.baseHourly) || wage.baseHourly <= 0) return { ok: false, url, reason: 'base_wage_not_verified' };

    return {
      ok: true,
      url,
      candidate: {
        id: url.split('/').filter(Boolean).pop()?.replace(/[^a-zA-Z0-9_-]/g, '') || '',
        url,
        rawText: text.slice(0, 120000),
        activeVerified: true,
        verifiedAt: now.toISOString(),
        sourcePriority: 100,
        detailCompleteness: detailCompleteness(text)
      }
    };
  } catch (error) {
    return { ok: false, url, reason: error?.name || 'detail_fetch_error' };
  }
}

export async function searchAndVerifyCandidates(baseJob, fetchImpl = fetch, now = new Date(), options = {}) {
  const discovery = await discoverUrlsForJob(baseJob, fetchImpl, options);
  const maxDetails = options.maxDetails ?? 12;
  const selected = discovery.urls.slice(0, maxDetails);
  const verified = [];
  const rejected = [];
  const concurrency = Math.max(1, Math.min(4, options.concurrency ?? 3));
  let cursor = 0;

  async function worker() {
    while (cursor < selected.length) {
      const index = cursor++;
      const result = await verifyDetailUrl(selected[index], fetchImpl, now, options);
      if (result.ok) verified.push(result.candidate);
      else rejected.push(result);
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, selected.length || 1) }, () => worker()));

  return { ...discovery, detailChecked: selected.length, verified, rejected };
}
