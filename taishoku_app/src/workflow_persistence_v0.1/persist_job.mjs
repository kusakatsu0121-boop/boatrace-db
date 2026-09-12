import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import pg from 'pg';
const { Client } = pg;

function arg(name, fallback = null) {
  const i = process.argv.indexOf(name);
  return i >= 0 && i + 1 < process.argv.length ? process.argv[i + 1] : fallback;
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function readJson(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch {
    return null;
  }
}

function contentType(fileName) {
  const ext = path.extname(fileName).toLowerCase();
  if (ext === '.json') return 'application/json';
  if (ext === '.html' || ext === '.htm') return 'text/html; charset=utf-8';
  if (ext === '.pdf') return 'application/pdf';
  if (ext === '.txt' || ext === '.log') return 'text/plain; charset=utf-8';
  if (ext === '.css') return 'text/css; charset=utf-8';
  return 'application/octet-stream';
}

function listFiles(root) {
  const out = [];
  if (!fs.existsSync(root)) return out;
  const walk = current => {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.isFile()) out.push(full);
    }
  };
  walk(root);
  return out;
}

function finalStatus(status) {
  return new Set([
    'ready_for_manual_delivery',
    'approved_for_manual_delivery',
    'blocked',
    'failed',
  ]).has(String(status || ''));
}

function makeClient() {
  const connectionString = process.env.DATABASE_URL;
  if (!connectionString) throw new Error('DATABASE_URL is not configured');
  const needsSsl = /sslmode=(require|verify-ca|verify-full)/i.test(connectionString) || /neon\.tech/i.test(connectionString);
  return new Client({
    connectionString,
    ssl: needsSsl ? { rejectUnauthorized: false } : undefined,
  });
}

async function ensureSchema(client) {
  await client.query(`
    CREATE TABLE IF NOT EXISTS taishoku_jobs (
      reference_id TEXT PRIMARY KEY,
      event_id TEXT,
      status TEXT,
      delivery_allowed BOOLEAN,
      automatic_delivery BOOLEAN NOT NULL DEFAULT FALSE,
      manifest JSONB,
      normalized_answer JSONB,
      evaluation JSONB,
      source_payload JSONB,
      persisted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
  `);
  await client.query(`
    CREATE TABLE IF NOT EXISTS taishoku_artifacts (
      reference_id TEXT NOT NULL REFERENCES taishoku_jobs(reference_id) ON DELETE CASCADE,
      file_name TEXT NOT NULL,
      content_type TEXT NOT NULL,
      content BYTEA NOT NULL,
      sha256 TEXT NOT NULL,
      size_bytes BIGINT NOT NULL,
      persisted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY (reference_id, file_name)
    )
  `);
  await client.query(`CREATE INDEX IF NOT EXISTS taishoku_jobs_event_id_idx ON taishoku_jobs(event_id)`);
}

async function waitForJob(jobDir, timeoutMs) {
  const manifestPath = path.join(jobDir, 'job_manifest.json');
  const started = Date.now();
  let lastManifest = null;
  while (Date.now() - started < timeoutMs) {
    if (fs.existsSync(manifestPath)) {
      lastManifest = readJson(manifestPath);
      if (lastManifest && finalStatus(lastManifest.status)) return lastManifest;
    }
    await sleep(1000);
  }
  if (lastManifest) return lastManifest;
  throw new Error('job_manifest_timeout');
}

async function main() {
  const outputRoot = path.resolve(arg('--output-root', process.env.WORKFLOW_OUTPUT_ROOT || '/tmp/taishoku-jobs'));
  const referenceId = String(arg('--reference-id', '') || '').trim();
  const eventId = String(arg('--event-id', '') || '').trim();
  const timeoutMs = Number(arg('--timeout-ms', '120000'));
  const maxArtifactBytes = Number(process.env.PERSISTENCE_MAX_ARTIFACT_BYTES || 20 * 1024 * 1024);

  if (!referenceId || !/^WF-[A-Za-z0-9_-]{1,80}$/.test(referenceId)) {
    throw new Error('invalid_reference_id');
  }
  if (!process.env.DATABASE_URL) {
    console.log(JSON.stringify({ status: 'persistence_skipped', reason: 'database_not_configured', reference_id: referenceId }));
    return;
  }

  const jobDir = path.join(outputRoot, referenceId);
  const manifest = await waitForJob(jobDir, timeoutMs);
  const normalized = readJson(path.join(jobDir, 'normalized_answer.json'));
  const evaluation = readJson(path.join(jobDir, 'evaluation.json'));
  const sourcePayload = readJson(path.join(jobDir, 'source_payload.json'));
  const files = listFiles(jobDir);

  const client = makeClient();
  await client.connect();
  try {
    await client.query('BEGIN');
    await ensureSchema(client);
    await client.query(
      `INSERT INTO taishoku_jobs (
         reference_id, event_id, status, delivery_allowed, automatic_delivery,
         manifest, normalized_answer, evaluation, source_payload, persisted_at, updated_at
       ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW(),NOW())
       ON CONFLICT (reference_id) DO UPDATE SET
         event_id = EXCLUDED.event_id,
         status = EXCLUDED.status,
         delivery_allowed = EXCLUDED.delivery_allowed,
         automatic_delivery = FALSE,
         manifest = EXCLUDED.manifest,
         normalized_answer = EXCLUDED.normalized_answer,
         evaluation = EXCLUDED.evaluation,
         source_payload = EXCLUDED.source_payload,
         updated_at = NOW()`,
      [
        referenceId,
        eventId || null,
        manifest?.status || null,
        manifest?.delivery_allowed ?? null,
        false,
        manifest,
        normalized,
        evaluation,
        sourcePayload,
      ]
    );

    let artifactCount = 0;
    for (const filePath of files) {
      const relative = path.relative(jobDir, filePath).replaceAll('\\', '/');
      if (!relative || relative.startsWith('../') || relative.includes('/../')) continue;
      const stat = fs.statSync(filePath);
      if (stat.size > maxArtifactBytes) {
        throw new Error(`artifact_too_large:${relative}`);
      }
      const bytes = fs.readFileSync(filePath);
      const sha256 = crypto.createHash('sha256').update(bytes).digest('hex');
      await client.query(
        `INSERT INTO taishoku_artifacts
           (reference_id, file_name, content_type, content, sha256, size_bytes, persisted_at)
         VALUES ($1,$2,$3,$4,$5,$6,NOW())
         ON CONFLICT (reference_id, file_name) DO UPDATE SET
           content_type = EXCLUDED.content_type,
           content = EXCLUDED.content,
           sha256 = EXCLUDED.sha256,
           size_bytes = EXCLUDED.size_bytes,
           persisted_at = NOW()`,
        [referenceId, relative, contentType(relative), bytes, sha256, stat.size]
      );
      artifactCount += 1;
    }
    await client.query('COMMIT');
    console.log(JSON.stringify({
      status: 'persisted',
      reference_id: referenceId,
      job_status: manifest?.status || null,
      artifact_count: artifactCount,
      automatic_delivery: false,
    }));
  } catch (error) {
    await client.query('ROLLBACK').catch(() => {});
    throw error;
  } finally {
    await client.end().catch(() => {});
  }
}

main().catch(error => {
  console.error(JSON.stringify({ status: 'persistence_failed', error: error.message || String(error), automatic_delivery: false }));
  process.exitCode = 1;
});
