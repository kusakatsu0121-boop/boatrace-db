import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { resolveReportAccess } from '../workflow_report_access_v0.1/report_access.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(here, '..');
const workerPath = path.join(here, 'queue_worker.mjs');
const persistencePath = path.join(projectRoot, 'workflow_persistence_v0.1', 'persist_job.mjs');
const instantFinalizePath = path.join(projectRoot, 'workflow_pipeline_v0.1', 'instant_finalize.mjs');
const REPORT_TOKEN_RE = /^[A-Za-z0-9_-]{43}$/;

function sendJson(res, status, body) {
  const encoded = Buffer.from(`${JSON.stringify(body)}\n`, 'utf8');
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': encoded.length,
    'cache-control': 'no-store',
  });
  res.end(encoded);
}

function sendHtml(res, status, html) {
  const body = Buffer.from(String(html || ''), 'utf8');
  res.writeHead(status, {
    'content-type': 'text/html; charset=utf-8',
    'content-length': body.length,
    'cache-control': 'private, no-store',
    'x-robots-tag': 'noindex, nofollow, noarchive',
    'referrer-policy': 'no-referrer',
    'x-content-type-options': 'nosniff',
  });
  res.end(body);
}

function sendPrivateReport(res, htmlBytes) {
  const body = Buffer.isBuffer(htmlBytes) ? htmlBytes : Buffer.from(htmlBytes || '');
  res.writeHead(200, {
    'content-type': 'text/html; charset=utf-8',
    'content-length': body.length,
    'cache-control': 'private, no-store',
    'x-robots-tag': 'noindex, nofollow, noarchive',
    'referrer-policy': 'no-referrer',
    'x-content-type-options': 'nosniff',
  });
  res.end(body);
}

function redirect(res, location) {
  res.writeHead(302, {
    location,
    'cache-control': 'no-store',
    'referrer-policy': 'no-referrer',
  });
  res.end();
}

function processingPage() {
  return `<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="2">
<title>レポートを作成しています</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#f7f7f5;color:#202124}
main{max-width:560px;margin:12vh auto;padding:32px 24px;text-align:center}
.card{background:#fff;border:1px solid #e6e6e2;border-radius:18px;padding:34px 24px;box-shadow:0 6px 24px rgba(0,0,0,.05)}
.spinner{width:34px;height:34px;border:4px solid #ddd;border-top-color:#333;border-radius:50%;margin:0 auto 22px;animation:s 1s linear infinite}
@keyframes s{to{transform:rotate(360deg)}}
h1{font-size:22px;margin:0 0 12px}p{line-height:1.7;margin:0;color:#555}
</style>
</head>
<body><main><div class="card"><div class="spinner"></div><h1>あなたのレポートを作成しています</h1><p>通常は数十秒で表示されます。<br>この画面は自動で更新されます。</p></div></main></body>
</html>`;
}

function safeId(value) {
  return String(value || '')
    .normalize('NFKC')
    .replace(/[^A-Za-z0-9_-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 80);
}

function eventId(payload, rawBody) {
  const candidate = safeId(payload?.eventId ?? payload?.event_id ?? payload?.data?.responseId ?? payload?.data?.submissionId);
  if (candidate) return candidate;
  return crypto.createHash('sha256').update(rawBody).digest('hex').slice(0, 24);
}

function referenceId(payload) {
  const candidate = safeId(payload?.data?.responseId ?? payload?.data?.submissionId);
  return candidate ? `WF-${candidate}` : null;
}

function scalar(value) {
  if (Array.isArray(value)) return value.length ? scalar(value[0]) : '';
  if (value && typeof value === 'object' && 'value' in value) return scalar(value.value);
  return value == null ? '' : String(value);
}

function extractInstantToken(payload, fieldName) {
  const candidates = [
    payload?.data?.[fieldName],
    payload?.data?.hiddenFields?.[fieldName],
    payload?.data?.hidden_fields?.[fieldName],
  ];
  for (const value of candidates) {
    const token = scalar(value).trim();
    if (REPORT_TOKEN_RE.test(token)) return token;
  }

  const hiddenCollections = [payload?.data?.hiddenFields, payload?.data?.hidden_fields];
  for (const collection of hiddenCollections) {
    if (!Array.isArray(collection)) continue;
    for (const item of collection) {
      if (String(item?.name ?? item?.key ?? item?.label ?? '') !== fieldName) continue;
      const token = scalar(item?.value ?? item?.answer).trim();
      if (REPORT_TOKEN_RE.test(token)) return token;
    }
  }

  const fields = Array.isArray(payload?.data?.fields) ? payload.data.fields : [];
  for (const field of fields) {
    const names = [field?.name, field?.label, field?.key].map(v => String(v ?? ''));
    if (!names.includes(fieldName)) continue;
    const token = scalar(field?.value ?? field?.answer).trim();
    if (REPORT_TOKEN_RE.test(token)) return token;
  }
  return null;
}

function signatureMatches(payload, received, secret) {
  if (!received || !secret) return false;
  const calculated = crypto
    .createHmac('sha256', secret)
    .update(JSON.stringify(payload))
    .digest('base64');
  const a = Buffer.from(received);
  const b = Buffer.from(calculated);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

function ensureQueue(queueRoot) {
  for (const name of ['pending', 'processing', 'processed', 'failed', 'logs']) {
    fs.mkdirSync(path.join(queueRoot, name), { recursive: true });
  }
}

function eventExists(queueRoot, id) {
  return ['pending', 'processing', 'processed', 'failed'].some(name =>
    fs.existsSync(path.join(queueRoot, name, `${id}.json`))
  );
}

function enqueue(queueRoot, id, payload) {
  const target = path.join(queueRoot, 'pending', `${id}.json`);
  fs.writeFileSync(target, `${JSON.stringify(payload, null, 2)}\n`, { encoding: 'utf8', flag: 'wx' });
  return target;
}

function spawnDetached(scriptPath, args, stdio = 'ignore') {
  const child = spawn(process.execPath, [scriptPath, ...args], {
    cwd: projectRoot,
    detached: true,
    stdio,
    env: process.env,
  });
  child.unref();
  return child;
}

function startWorker(queueRoot, outputRoot) {
  console.log(JSON.stringify({ status: 'worker_starting', queue_root: queueRoot, output_root: outputRoot, automatic_delivery: false }));
  const child = spawnDetached(workerPath, ['--queue-root', queueRoot, '--output-root', outputRoot], ['ignore', 'inherit', 'inherit']);
  child.on('error', error => {
    console.error(JSON.stringify({ status: 'worker_spawn_error', error: error.message || String(error), automatic_delivery: false }));
  });
}

function startPersistence(outputRoot, id, payload) {
  if (!process.env.DATABASE_URL || !fs.existsSync(persistencePath)) {
    console.log(JSON.stringify({ status: 'persistence_not_started', database_url: Boolean(process.env.DATABASE_URL), persistence_path_exists: fs.existsSync(persistencePath), automatic_delivery: false }));
    return;
  }
  const ref = referenceId(payload);
  if (!ref) {
    console.log(JSON.stringify({ status: 'persistence_not_started', reason: 'missing_reference_id', automatic_delivery: false }));
    return;
  }
  console.log(JSON.stringify({ status: 'persistence_starting', reference_id: ref, event_id: id, output_root: outputRoot, automatic_delivery: false }));
  const child = spawnDetached(persistencePath, [
    '--output-root', outputRoot,
    '--reference-id', ref,
    '--event-id', id,
  ], ['ignore', 'inherit', 'inherit']);
  child.on('error', error => {
    console.error(JSON.stringify({ status: 'persistence_spawn_error', reference_id: ref, error: error.message || String(error), automatic_delivery: false }));
  });
}

function startInstantFinalize(outputRoot, payload, token) {
  const ref = referenceId(payload);
  if (!ref || !REPORT_TOKEN_RE.test(String(token || '')) || !fs.existsSync(instantFinalizePath)) return;
  console.log(JSON.stringify({ status: 'instant_report_starting', reference_id: ref, automatic_delivery: false }));
  const child = spawnDetached(instantFinalizePath, [outputRoot, ref, token], ['ignore', 'inherit', 'inherit']);
  child.on('error', error => {
    console.error(JSON.stringify({ status: 'instant_report_spawn_error', reference_id: ref, error: error.message || String(error), automatic_delivery: false }));
  });
}

async function readBody(req, limitBytes) {
  const chunks = [];
  let total = 0;
  for await (const chunk of req) {
    total += chunk.length;
    if (total > limitBytes) {
      const error = new Error('payload_too_large');
      error.statusCode = 413;
      throw error;
    }
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

export function createWebhookServer(options = {}) {
  const queueRoot = path.resolve(options.queueRoot ?? process.env.WORKFLOW_QUEUE_ROOT ?? path.join(projectRoot, 'output', 'webhook_queue'));
  const outputRoot = path.resolve(options.outputRoot ?? process.env.WORKFLOW_OUTPUT_ROOT ?? path.join(projectRoot, 'output', 'jobs'));
  const signingSecret = options.signingSecret ?? process.env.TALLY_SIGNING_SECRET;
  const expectedFormId = options.expectedFormId ?? process.env.TALLY_FORM_ID ?? 'QKyVpY';
  const allowUnsigned = options.allowUnsigned ?? process.env.ALLOW_UNSIGNED_WEBHOOKS === 'true';
  const launchWorker = options.launchWorker ?? true;
  const bodyLimit = options.bodyLimit ?? 2 * 1024 * 1024;
  const persistenceConfigured = Boolean(process.env.DATABASE_URL);
  const persistenceRequired = process.env.REQUIRE_PERSISTENCE === 'true';
  const instantEnabled = options.instantEnabled ?? process.env.INSTANT_WEB_REPORT === 'true';
  const instantFieldName = options.instantFieldName ?? process.env.INSTANT_TOKEN_FIELD ?? 'instant_token';
  const tallyPublicUrl = options.tallyPublicUrl ?? process.env.TALLY_PUBLIC_URL ?? 'https://tally.so/r/QKyVpY';

  if (!signingSecret && !allowUnsigned) {
    throw new Error('TALLY_SIGNING_SECRET がありません。署名なしで起動する場合は開発時のみ ALLOW_UNSIGNED_WEBHOOKS=true を設定してください');
  }
  if (persistenceRequired && !persistenceConfigured) {
    throw new Error('REQUIRE_PERSISTENCE=true ですが DATABASE_URL がありません');
  }
  ensureQueue(queueRoot);

  return http.createServer(async (req, res) => {
    const url = new URL(req.url || '/', 'http://localhost');
    if (req.method === 'GET' && url.pathname === '/health') {
      sendJson(res, 200, {
        status: 'ok',
        automatic_delivery: false,
        persistence: persistenceConfigured ? 'configured' : 'ephemeral',
        secret_report_access: persistenceConfigured ? 'configured' : 'unavailable',
        instant_web_report: instantEnabled ? 'enabled' : 'disabled',
      });
      return;
    }

    if (req.method === 'GET' && url.pathname === '/start' && instantEnabled) {
      const token = crypto.randomBytes(32).toString('base64url');
      const target = new URL(tallyPublicUrl);
      target.searchParams.set(instantFieldName, token);
      for (const [key, value] of url.searchParams) {
        if (key === instantFieldName) continue;
        target.searchParams.append(key, value);
      }
      redirect(res, target.toString());
      return;
    }

    if (req.method === 'GET' && url.pathname.startsWith('/r/')) {
      const token = url.pathname.slice(3);
      if (!REPORT_TOKEN_RE.test(token)) {
        sendJson(res, 404, { error: 'not_found' });
        return;
      }
      try {
        const report = await resolveReportAccess(token);
        if (!report) {
          if (instantEnabled) {
            sendHtml(res, 202, processingPage());
          } else {
            sendJson(res, 404, { error: 'not_found' });
          }
          return;
        }
        sendPrivateReport(res, report.htmlBytes);
      } catch (error) {
        console.error(JSON.stringify({ status: 'report_access_error', error: error.message || String(error), automatic_delivery: false }));
        if (instantEnabled) sendHtml(res, 202, processingPage());
        else sendJson(res, 404, { error: 'not_found' });
      }
      return;
    }

    if (req.method !== 'POST' || url.pathname !== '/webhooks/tally') {
      sendJson(res, 404, { error: 'not_found' });
      return;
    }

    try {
      const rawBody = await readBody(req, bodyLimit);
      let payload;
      try {
        payload = JSON.parse(rawBody.toString('utf8'));
      } catch {
        sendJson(res, 400, { error: 'invalid_json' });
        return;
      }

      if (!allowUnsigned) {
        const received = req.headers['tally-signature'];
        if (!signatureMatches(payload, Array.isArray(received) ? received[0] : received, signingSecret)) {
          sendJson(res, 401, { error: 'invalid_signature' });
          return;
        }
      }
      if (payload?.eventType !== 'FORM_RESPONSE') {
        sendJson(res, 202, { status: 'ignored', reason: 'unsupported_event_type' });
        return;
      }
      if (payload?.data?.formId !== expectedFormId) {
        sendJson(res, 202, { status: 'ignored', reason: 'unexpected_form' });
        return;
      }

      const id = eventId(payload, rawBody);
      const instantToken = instantEnabled ? extractInstantToken(payload, instantFieldName) : null;
      if (eventExists(queueRoot, id)) {
        sendJson(res, 200, { status: 'duplicate', event_id: id, automatic_delivery: false });
        startPersistence(outputRoot, id, payload);
        if (instantToken) startInstantFinalize(outputRoot, payload, instantToken);
        return;
      }
      try {
        enqueue(queueRoot, id, payload);
      } catch (error) {
        if (error.code === 'EEXIST') {
          sendJson(res, 200, { status: 'duplicate', event_id: id, automatic_delivery: false });
          startPersistence(outputRoot, id, payload);
          if (instantToken) startInstantFinalize(outputRoot, payload, instantToken);
          return;
        }
        throw error;
      }

      sendJson(res, 202, { status: 'accepted', event_id: id, automatic_delivery: false });
      if (launchWorker) startWorker(queueRoot, outputRoot);
      startPersistence(outputRoot, id, payload);
      if (instantToken) startInstantFinalize(outputRoot, payload, instantToken);
    } catch (error) {
      sendJson(res, error.statusCode || 500, { error: error.message || 'internal_error' });
    }
  });
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const port = Number(process.env.PORT || 3000);
    const host = process.env.HOST || '0.0.0.0';
    const queueRoot = path.resolve(process.env.WORKFLOW_QUEUE_ROOT ?? path.join(projectRoot, 'output', 'webhook_queue'));
    const outputRoot = path.resolve(process.env.WORKFLOW_OUTPUT_ROOT ?? path.join(projectRoot, 'output', 'jobs'));
    const server = createWebhookServer({ queueRoot, outputRoot });
    server.listen(port, host, () => {
      console.log(JSON.stringify({
        status: 'listening',
        host,
        port,
        endpoint: '/webhooks/tally',
        automatic_delivery: false,
        persistence: process.env.DATABASE_URL ? 'configured' : 'ephemeral',
        secret_report_access: process.env.DATABASE_URL ? 'configured' : 'unavailable',
        instant_web_report: process.env.INSTANT_WEB_REPORT === 'true' ? 'enabled' : 'disabled',
      }));
      startWorker(queueRoot, outputRoot);
    });
  } catch (error) {
    console.error(error.message || String(error));
    process.exit(1);
  }
}
