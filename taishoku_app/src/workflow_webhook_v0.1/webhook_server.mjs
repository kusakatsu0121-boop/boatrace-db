import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(here, '..');
const workerPath = path.join(here, 'queue_worker.mjs');

function sendJson(res, status, body) {
  const encoded = Buffer.from(`${JSON.stringify(body)}\n`, 'utf8');
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': encoded.length,
    'cache-control': 'no-store',
  });
  res.end(encoded);
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

function startWorker(queueRoot, outputRoot) {
  const child = spawn(process.execPath, [workerPath, '--queue-root', queueRoot, '--output-root', outputRoot], {
    cwd: projectRoot,
    detached: true,
    stdio: 'ignore',
    env: process.env,
  });
  child.unref();
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

  if (!signingSecret && !allowUnsigned) {
    throw new Error('TALLY_SIGNING_SECRET がありません。署名なしで起動する場合は開発時のみ ALLOW_UNSIGNED_WEBHOOKS=true を設定してください');
  }
  ensureQueue(queueRoot);

  return http.createServer(async (req, res) => {
    const url = new URL(req.url || '/', 'http://localhost');
    if (req.method === 'GET' && url.pathname === '/health') {
      sendJson(res, 200, { status: 'ok', automatic_delivery: false });
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
      if (eventExists(queueRoot, id)) {
        sendJson(res, 200, { status: 'duplicate', event_id: id });
        return;
      }
      try {
        enqueue(queueRoot, id, payload);
      } catch (error) {
        if (error.code === 'EEXIST') {
          sendJson(res, 200, { status: 'duplicate', event_id: id });
          return;
        }
        throw error;
      }

      sendJson(res, 202, { status: 'accepted', event_id: id, automatic_delivery: false });
      if (launchWorker) startWorker(queueRoot, outputRoot);
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
      console.log(JSON.stringify({ status: 'listening', host, port, endpoint: '/webhooks/tally', automatic_delivery: false }));
      startWorker(queueRoot, outputRoot);
    });
  } catch (error) {
    console.error(error.message || String(error));
    process.exit(1);
  }
}
