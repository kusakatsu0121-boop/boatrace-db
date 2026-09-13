import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createReportAccess, revokeReportAccess } from '../workflow_report_access_v0.1/report_access.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(here, '..');
const persistencePath = path.join(projectRoot, 'workflow_persistence_v0.1', 'persist_job.mjs');
const REFERENCE_ID_RE = /^WF-[A-Za-z0-9_-]{1,80}$/;

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function writeJsonAtomic(filePath, value) {
  const tmp = `${filePath}.tmp-${process.pid}-${Date.now()}`;
  fs.writeFileSync(tmp, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  fs.renameSync(tmp, filePath);
}

function sha256(bytes) {
  return crypto.createHash('sha256').update(bytes).digest('hex');
}

function eventIdFrom(sourcePayload, manifest) {
  return String(
    sourcePayload?.eventId ??
    sourcePayload?.event_id ??
    sourcePayload?.data?.responseId ??
    sourcePayload?.data?.submissionId ??
    manifest?.event_id ??
    ''
  ).trim();
}

function runPersistence(jobDir, referenceId, eventId) {
  if (!fs.existsSync(persistencePath)) throw new Error('persistence_module_missing');
  if (!process.env.DATABASE_URL) throw new Error('DATABASE_URL is not configured');
  const args = [persistencePath, '--output-root', path.dirname(jobDir), '--reference-id', referenceId];
  if (eventId) args.push('--event-id', eventId);
  const result = spawnSync(process.execPath, args, {
    cwd: projectRoot,
    env: process.env,
    encoding: 'utf8',
    timeout: 180000,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    const detail = String(result.stderr || result.stdout || '').trim().slice(0, 2000);
    throw new Error(`persistence_failed:${detail || `exit_${result.status}`}`);
  }
  return String(result.stdout || '').trim();
}

async function approve(jobDirArg, approvedByArg, approvalNoteArg, options = {}) {
  const jobDir = path.resolve(jobDirArg || '');
  const manifestPath = path.join(jobDir, 'job_manifest.json');
  const approvalPath = path.join(jobDir, 'approval.json');
  const htmlPath = path.join(jobDir, 'report_preview.html');
  const sourcePayloadPath = path.join(jobDir, 'source_payload.json');

  if (!jobDirArg || !fs.existsSync(jobDir) || !fs.statSync(jobDir).isDirectory()) throw new Error('job_dir_not_found');
  if (!fs.existsSync(manifestPath)) throw new Error('job_manifest_missing');
  if (!fs.existsSync(htmlPath)) throw new Error('report_preview_missing');
  if (fs.existsSync(approvalPath)) throw new Error('job_already_has_approval');

  const originalManifestText = fs.readFileSync(manifestPath, 'utf8');
  const manifest = JSON.parse(originalManifestText);
  if (manifest.status !== 'ready_for_manual_delivery') throw new Error(`job_not_ready:${manifest.status || 'unknown'}`);
  if (manifest.delivery_allowed !== true) throw new Error('delivery_not_allowed');
  if (manifest.automatic_delivery === true) throw new Error('automatic_delivery_must_be_false');

  const referenceId = String(manifest.reference_id || path.basename(jobDir)).trim();
  if (!REFERENCE_ID_RE.test(referenceId)) throw new Error('invalid_reference_id');
  const approvedBy = String(approvedByArg || 'manual-review').trim().slice(0, 200) || 'manual-review';
  const approvalNote = String(approvalNoteArg || '').trim().slice(0, 1000) || null;
  const reportToken = options?.reportToken == null ? null : String(options.reportToken);
  const sourcePayload = fs.existsSync(sourcePayloadPath) ? readJson(sourcePayloadPath) : null;
  const eventId = eventIdFrom(sourcePayload, manifest);
  const htmlBytes = fs.readFileSync(htmlPath);
  if (!htmlBytes.length) throw new Error('report_preview_empty');
  const htmlSha256 = sha256(htmlBytes);

  // First make sure the ready-for-review job and its exact generated artifacts
  // are durably present before issuing any secret URL.
  runPersistence(jobDir, referenceId, eventId);

  let access = null;
  let localApprovalWritten = false;
  try {
    access = await createReportAccess({
      referenceId,
      htmlBytes,
      approvedBy,
      approvalNote,
      baseUrl: process.env.REPORT_BASE_URL || process.env.RENDER_EXTERNAL_URL || null,
      token: reportToken,
    });

    const approvedAt = new Date().toISOString();
    const approvedManifest = {
      ...manifest,
      status: 'approved_for_manual_delivery',
      delivery_allowed: true,
      automatic_delivery: false,
      approved_at: approvedAt,
      approved_by: approvedBy,
      approval_note: approvalNote,
      report_id: access.reportId,
      report_html_sha256: htmlSha256,
    };
    const approval = {
      reference_id: referenceId,
      report_id: access.reportId,
      status: 'approved_for_manual_delivery',
      approved_at: approvedAt,
      approved_by: approvedBy,
      approval_note: approvalNote,
      report_html_sha256: htmlSha256,
      automatic_delivery: false,
    };

    writeJsonAtomic(manifestPath, approvedManifest);
    writeJsonAtomic(approvalPath, approval);
    localApprovalWritten = true;

    // Persist the approval state and approval.json. The URL remains inaccessible
    // until the durable job row reaches approved_for_manual_delivery.
    runPersistence(jobDir, referenceId, eventId);

    const output = {
      status: 'approved_for_manual_delivery',
      reference_id: referenceId,
      report_id: access.reportId,
      report_url: access.reportUrl,
      report_html_sha256: htmlSha256,
      automatic_delivery: false,
    };
    process.stdout.write(`${JSON.stringify(output)}\n`);
    return output;
  } catch (error) {
    if (access?.reportId) {
      await revokeReportAccess(access.reportId).catch(() => {});
    }
    if (localApprovalWritten) {
      try {
        fs.writeFileSync(manifestPath, originalManifestText, 'utf8');
        if (fs.existsSync(approvalPath)) fs.unlinkSync(approvalPath);
      } catch {}
    }
    throw error;
  }
}

async function main() {
  const jobDir = process.argv[2];
  const approvedBy = process.argv[3] || 'manual-review';
  const approvalNote = process.argv.slice(4).join(' ') || '';
  await approve(jobDir, approvedBy, approvalNote);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => {
    console.error(JSON.stringify({ status: 'approval_failed', error: error.message || String(error), automatic_delivery: false }));
    process.exitCode = 1;
  });
}

export { approve };
