import fs from 'node:fs';
import path from 'node:path';
import { approve } from './approve_job.mjs';

const TOKEN_RE = /^[A-Za-z0-9_-]{43}$/;
const REFERENCE_ID_RE = /^WF-[A-Za-z0-9_-]{1,80}$/;

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

async function waitUntilReady(jobDir, timeoutMs = 120000) {
  const manifestPath = path.join(jobDir, 'job_manifest.json');
  const approvalPath = path.join(jobDir, 'approval.json');
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (fs.existsSync(approvalPath)) {
      return { status: 'already_approved', manifest: readJson(manifestPath) };
    }
    const manifest = readJson(manifestPath);
    const status = String(manifest?.status || '');
    if (status === 'ready_for_manual_delivery') {
      return { status: 'ready', manifest };
    }
    if (status === 'blocked' || status === 'failed') {
      throw new Error(`job_not_publishable:${status}`);
    }
    await sleep(500);
  }
  throw new Error('instant_finalize_timeout');
}

export async function finalizeInstantReport({ outputRoot, referenceId, token, timeoutMs = 120000 }) {
  if (!REFERENCE_ID_RE.test(String(referenceId || ''))) throw new Error('invalid_reference_id');
  if (!TOKEN_RE.test(String(token || ''))) throw new Error('invalid_report_token');
  const root = path.resolve(outputRoot || process.env.WORKFLOW_OUTPUT_ROOT || '/tmp/taishoku-jobs');
  const jobDir = path.join(root, referenceId);
  const state = await waitUntilReady(jobDir, timeoutMs);
  if (state.status === 'already_approved') {
    return { status: 'already_approved', reference_id: referenceId, automatic_delivery: false };
  }
  if (state.manifest?.delivery_allowed !== true) throw new Error('delivery_not_allowed');
  if (state.manifest?.automatic_delivery === true) throw new Error('automatic_delivery_must_be_false');

  const result = await approve(
    jobDir,
    'instant-web-report',
    'Successful generation auto-published to the submitter secret URL.',
    { reportToken: token }
  );
  return {
    status: 'instant_report_ready',
    reference_id: referenceId,
    report_url: result.report_url,
    automatic_delivery: false,
  };
}

async function main() {
  const [outputRoot, referenceId, token, timeoutArg] = process.argv.slice(2);
  const timeoutMs = Number(timeoutArg || '120000');
  const result = await finalizeInstantReport({ outputRoot, referenceId, token, timeoutMs });
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

if (process.argv[1] && process.argv[1].endsWith('instant_finalize.mjs')) {
  main().catch(error => {
    console.error(JSON.stringify({
      status: 'instant_report_failed',
      error: error.message || String(error),
      automatic_delivery: false,
    }));
    process.exitCode = 1;
  });
}
