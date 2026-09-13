import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import pg from 'pg';
const { Client } = pg;

const TOKEN_RE = /^[A-Za-z0-9_-]{43}$/;
const REPORT_ID_RE = /^rpt_[A-Za-z0-9_-]{16,80}$/;
const REFERENCE_ID_RE = /^WF-[A-Za-z0-9_-]{1,80}$/;

function makeClient() {
  const connectionString = process.env.DATABASE_URL;
  if (!connectionString) throw new Error('DATABASE_URL is not configured');
  const needsSsl = /sslmode=(require|verify-ca|verify-full)/i.test(connectionString) || /neon\.tech/i.test(connectionString);
  return new Client({
    connectionString,
    ssl: needsSsl ? { rejectUnauthorized: false } : undefined,
  });
}

export function hashReportToken(token) {
  return crypto.createHash('sha256').update(String(token), 'utf8').digest('hex');
}

export async function ensureReportAccessSchema(client) {
  await client.query(`
    CREATE TABLE IF NOT EXISTS taishoku_report_access (
      report_id TEXT PRIMARY KEY,
      reference_id TEXT NOT NULL REFERENCES taishoku_jobs(reference_id) ON DELETE CASCADE,
      token_hash TEXT NOT NULL UNIQUE,
      html_content BYTEA NOT NULL,
      html_sha256 TEXT NOT NULL,
      issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      expires_at TIMESTAMPTZ,
      revoked_at TIMESTAMPTZ,
      approved_by TEXT,
      approval_note TEXT
    )
  `);
  await client.query(`CREATE INDEX IF NOT EXISTS taishoku_report_access_reference_idx ON taishoku_report_access(reference_id)`);
}

export async function createReportAccess({ referenceId, htmlBytes, approvedBy = null, approvalNote = null, expiresAt = null, baseUrl = null, token = null }) {
  if (!REFERENCE_ID_RE.test(String(referenceId || ''))) throw new Error('invalid_reference_id');
  const content = Buffer.isBuffer(htmlBytes) ? htmlBytes : Buffer.from(htmlBytes || '');
  if (!content.length) throw new Error('empty_report_html');

  const reportToken = token == null ? crypto.randomBytes(32).toString('base64url') : String(token);
  if (!TOKEN_RE.test(reportToken)) throw new Error('invalid_generated_token');
  const tokenHash = hashReportToken(reportToken);
  const reportId = `rpt_${crypto.randomBytes(18).toString('base64url')}`;
  const htmlSha256 = crypto.createHash('sha256').update(content).digest('hex');
  const client = makeClient();
  await client.connect();
  try {
    await ensureReportAccessSchema(client);
    const job = await client.query(
      `SELECT reference_id, status, delivery_allowed, automatic_delivery
         FROM taishoku_jobs WHERE reference_id=$1`,
      [referenceId]
    );
    if (!job.rowCount) throw new Error('job_not_persisted');
    if (job.rows[0].delivery_allowed !== true || job.rows[0].automatic_delivery !== false) {
      throw new Error('job_not_eligible_for_manual_delivery');
    }
    await client.query(
      `INSERT INTO taishoku_report_access
         (report_id, reference_id, token_hash, html_content, html_sha256, issued_at, expires_at, revoked_at, approved_by, approval_note)
       VALUES ($1,$2,$3,$4,$5,NOW(),$6,NULL,$7,$8)`,
      [reportId, referenceId, tokenHash, content, htmlSha256, expiresAt, approvedBy, approvalNote]
    );
  } finally {
    await client.end().catch(() => {});
  }
  const cleanBase = baseUrl ? String(baseUrl).replace(/\/+$/, '') : '';
  const reportPath = `/r/${reportToken}`;
  return {
    reportId,
    referenceId,
    token: reportToken,
    tokenHash,
    reportPath,
    reportUrl: cleanBase ? `${cleanBase}${reportPath}` : reportPath,
    htmlSha256,
  };
}

export async function resolveReportAccess(token) {
  if (!TOKEN_RE.test(String(token || ''))) return null;
  if (!process.env.DATABASE_URL) return null;
  const tokenHash = hashReportToken(token);
  const client = makeClient();
  await client.connect();
  try {
    await ensureReportAccessSchema(client);
    const result = await client.query(
      `SELECT a.report_id, a.reference_id, a.html_content, a.html_sha256, a.issued_at, a.expires_at,
              j.status, j.delivery_allowed, j.automatic_delivery
         FROM taishoku_report_access a
         JOIN taishoku_jobs j ON j.reference_id = a.reference_id
        WHERE a.token_hash=$1
          AND a.revoked_at IS NULL
          AND (a.expires_at IS NULL OR a.expires_at > NOW())
          AND j.status='approved_for_manual_delivery'
          AND j.delivery_allowed=TRUE
          AND j.automatic_delivery=FALSE
        LIMIT 1`,
      [tokenHash]
    );
    if (!result.rowCount) return null;
    const row = result.rows[0];
    return {
      reportId: row.report_id,
      referenceId: row.reference_id,
      htmlBytes: Buffer.from(row.html_content),
      htmlSha256: row.html_sha256,
      issuedAt: row.issued_at,
      expiresAt: row.expires_at,
    };
  } finally {
    await client.end().catch(() => {});
  }
}

export async function revokeReportAccess(reportId) {
  if (!REPORT_ID_RE.test(String(reportId || ''))) throw new Error('invalid_report_id');
  const client = makeClient();
  await client.connect();
  try {
    await ensureReportAccessSchema(client);
    const result = await client.query(
      `UPDATE taishoku_report_access SET revoked_at=COALESCE(revoked_at,NOW()) WHERE report_id=$1 RETURNING report_id`,
      [reportId]
    );
    return Boolean(result.rowCount);
  } finally {
    await client.end().catch(() => {});
  }
}

function arg(name, fallback = null) {
  const i = process.argv.indexOf(name);
  return i >= 0 && i + 1 < process.argv.length ? process.argv[i + 1] : fallback;
}

async function cli() {
  const command = process.argv[2];
  if (command === 'issue') {
    const jobDir = path.resolve(arg('--job-dir', ''));
    const referenceId = arg('--reference-id', path.basename(jobDir));
    const htmlPath = path.join(jobDir, 'report_preview.html');
    if (!fs.existsSync(htmlPath)) throw new Error('report_preview_missing');
    const result = await createReportAccess({
      referenceId,
      htmlBytes: fs.readFileSync(htmlPath),
      approvedBy: arg('--approved-by', null),
      approvalNote: arg('--approval-note', null),
      expiresAt: arg('--expires-at', null),
      baseUrl: arg('--base-url', process.env.REPORT_BASE_URL || process.env.RENDER_EXTERNAL_URL || null),
      token: arg('--token', null),
    });
    console.log(JSON.stringify({
      status: 'report_access_issued',
      report_id: result.reportId,
      reference_id: result.referenceId,
      report_url: result.reportUrl,
      html_sha256: result.htmlSha256,
      automatic_delivery: false,
    }));
    return;
  }
  if (command === 'revoke') {
    const reportId = arg('--report-id', '');
    const revoked = await revokeReportAccess(reportId);
    console.log(JSON.stringify({ status: revoked ? 'revoked' : 'not_found', report_id: reportId, automatic_delivery: false }));
    return;
  }
  throw new Error('usage: report_access.mjs issue|revoke ...');
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  cli().catch(error => {
    console.error(JSON.stringify({ status: 'report_access_failed', error: error.message || String(error), automatic_delivery: false }));
    process.exitCode = 1;
  });
}
