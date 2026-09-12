import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { Client } from 'pg';

function arg(name, fallback = null) {
  const i = process.argv.indexOf(name);
  return i >= 0 && i + 1 < process.argv.length ? process.argv[i + 1] : fallback;
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

function safeRelative(fileName) {
  const normalized = String(fileName || '').replaceAll('\\', '/');
  if (!normalized || normalized.startsWith('/') || normalized.startsWith('../') || normalized.includes('/../')) {
    throw new Error('unsafe_artifact_name');
  }
  return normalized;
}

async function main() {
  const referenceId = String(arg('--reference-id', '') || '').trim();
  const outputRoot = path.resolve(arg('--output-root', process.env.WORKFLOW_OUTPUT_ROOT || '/tmp/taishoku-jobs'));
  if (!/^WF-[A-Za-z0-9_-]{1,80}$/.test(referenceId)) throw new Error('invalid_reference_id');

  const client = makeClient();
  await client.connect();
  try {
    const result = await client.query(
      `SELECT file_name, content, sha256 FROM taishoku_artifacts
       WHERE reference_id = $1 ORDER BY file_name`,
      [referenceId]
    );
    if (!result.rows.length) throw new Error('job_not_found');

    const jobDir = path.join(outputRoot, referenceId);
    fs.mkdirSync(jobDir, { recursive: true });
    let count = 0;
    for (const row of result.rows) {
      const relative = safeRelative(row.file_name);
      const target = path.join(jobDir, relative);
      fs.mkdirSync(path.dirname(target), { recursive: true });
      const bytes = Buffer.from(row.content);
      const actual = crypto.createHash('sha256').update(bytes).digest('hex');
      if (actual !== row.sha256) throw new Error(`sha256_mismatch:${relative}`);
      fs.writeFileSync(target, bytes);
      count += 1;
    }
    console.log(JSON.stringify({ status: 'restored', reference_id: referenceId, artifact_count: count, output_dir: jobDir }));
  } finally {
    await client.end().catch(() => {});
  }
}

main().catch(error => {
  console.error(JSON.stringify({ status: 'restore_failed', error: error.message || String(error) }));
  process.exitCode = 1;
});
