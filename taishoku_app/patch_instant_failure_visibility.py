#!/usr/bin/env python3
"""Expose instant-report failures without publishing unreviewed reports."""
from pathlib import Path
import sys

root = Path(sys.argv[1])


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, got {count}')
    return text.replace(old, new, 1)

finalize_path = root / 'workflow_pipeline_v0.1' / 'instant_finalize.mjs'
finalize = finalize_path.read_text(encoding='utf-8')
finalize = replace_once(finalize,
    "if (status === 'blocked' || status === 'failed') {",
    "if (status === 'blocked' || status === 'failed' || status === 'review_required') {",
    'terminal human-review status')
finalize = replace_once(finalize,
    "  throw new Error('instant_finalize_timeout');",
    "  const lastManifest = readJson(manifestPath);\n  const lastStatus = String(lastManifest?.status || 'missing_manifest');\n  throw new Error(`instant_finalize_timeout:${lastStatus}`);",
    'diagnostic timeout status')

webhook_path = root / 'workflow_webhook_v0.1' / 'webhook_server.mjs'
webhook = webhook_path.read_text(encoding='utf-8')
webhook = replace_once(webhook,
    "const REPORT_TOKEN_RE = /^[A-Za-z0-9_-]{43}$/;",
    """const REPORT_TOKEN_RE = /^[A-Za-z0-9_-]{43}$/;

// Only store a hash of the secret token on disk. This status file never grants
// access to a report and must not be confused with an approval.
function instantStatusPath(outputRoot, token) {
  const tokenHash = crypto.createHash('sha256').update(token).digest('hex');
  return path.join(outputRoot, '.instant-status', `${tokenHash}.json`);
}

function writeInstantStatus(outputRoot, token, state) {
  const target = instantStatusPath(outputRoot, token);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  const temp = `${target}.tmp-${process.pid}-${crypto.randomBytes(4).toString('hex')}`;
  fs.writeFileSync(temp, JSON.stringify(state), { encoding: 'utf8', mode: 0o600 });
  fs.renameSync(temp, target);
}

function readInstantStatus(outputRoot, token) {
  try {
    return JSON.parse(fs.readFileSync(instantStatusPath(outputRoot, token), 'utf8'));
  } catch {
    return null;
  }
}

function instantReportFailed(outputRoot, token) {
  const state = readInstantStatus(outputRoot, token);
  return state?.status === 'failed' ||
    (state?.status === 'pending' && Number.isFinite(state.started_at) && Date.now() - state.started_at > 180000);
}""",
    'status helpers')
webhook = replace_once(webhook,
    'function processingPage() {',
    """function reportUnavailablePage() {
  return '<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>レポートの確認が必要です</title></head><body style="font-family:sans-serif;max-width:36rem;margin:10vh auto;padding:1.5rem;line-height:1.8"><h1>レポートを表示できませんでした</h1><p>回答内容の確認、または処理の再確認が必要です。自動的に公開することはありません。重複送信はせず、運営者にお問い合わせください。</p></body></html>';
}

function processingPage() {""",
    'failure page')
old_start = """function startInstantFinalize(outputRoot, payload, token) {
  const ref = referenceId(payload);
  if (!ref || !REPORT_TOKEN_RE.test(String(token || '')) || !fs.existsSync(instantFinalizePath)) return;
  console.log(JSON.stringify({ status: 'instant_report_starting', reference_id: ref, automatic_delivery: false }));
  const child = spawnDetached(instantFinalizePath, [outputRoot, ref, token], ['ignore', 'inherit', 'inherit']);
  child.on('error', error => {
    console.error(JSON.stringify({ status: 'instant_report_spawn_error', reference_id: ref, error: error.message || String(error), automatic_delivery: false }));
  });
}"""
new_start = """function startInstantFinalize(outputRoot, payload, token, id) {
  const ref = referenceId(payload);
  if (!ref || !REPORT_TOKEN_RE.test(String(token || '')) || !fs.existsSync(instantFinalizePath)) return;
  console.log(JSON.stringify({ status: 'instant_report_starting', reference_id: ref, automatic_delivery: false }));
  try {
    writeInstantStatus(outputRoot, token, { status: 'pending', started_at: Date.now() });
  } catch (error) {
    console.error(JSON.stringify({ status: 'instant_status_write_error', error: error.message || String(error), automatic_delivery: false }));
  }
  const child = spawnDetached(instantFinalizePath, [outputRoot, ref, token], ['ignore', 'inherit', 'inherit']);
  child.on('exit', code => {
    if (code === 0) {
      // A successful finalizer still needs a persisted job for report access.
      // Do not mark the token ready before persistence actually succeeds, and
      // never create approval.json or enable automatic delivery here.
      console.log(JSON.stringify({ status: 'instant_finalize_exit', reference_id: ref, exit_code: code, automatic_delivery: false }));
      if (fs.existsSync(path.join(outputRoot, ref, 'job_manifest.json'))) {
        startPersistence(outputRoot, id, payload);
      } else {
        console.error(JSON.stringify({ status: 'instant_manifest_missing_on_success', reference_id: ref, automatic_delivery: false }));
        try {
          writeInstantStatus(outputRoot, token, { status: 'failed', finished_at: Date.now() });
        } catch (error) {
          console.error(JSON.stringify({ status: 'instant_status_write_error', error: error.message || String(error), automatic_delivery: false }));
        }
      }
      return;
    }
    console.error(JSON.stringify({ status: 'instant_finalize_exit', reference_id: ref, exit_code: code, automatic_delivery: false }));
    try {
      writeInstantStatus(outputRoot, token, { status: 'failed', finished_at: Date.now() });
    } catch (error) {
      console.error(JSON.stringify({ status: 'instant_status_write_error', error: error.message || String(error), automatic_delivery: false }));
    }
    // Preserve a failed/blocked/review_required job for diagnosis. Never approve it.
    if (fs.existsSync(path.join(outputRoot, ref, 'job_manifest.json'))) {
      startPersistence(outputRoot, id, payload);
    } else {
      console.error(JSON.stringify({ status: 'instant_manifest_missing', reference_id: ref, automatic_delivery: false }));
    }
  });
  child.on('error', error => {
    console.error(JSON.stringify({ status: 'instant_report_spawn_error', reference_id: ref, error: error.message || String(error), automatic_delivery: false }));
    try {
      writeInstantStatus(outputRoot, token, { status: 'failed', finished_at: Date.now() });
    } catch {}
  });
}"""
webhook = replace_once(webhook, old_start, new_start, 'finalizer lifecycle')
old_processing = """          if (instantEnabled) {
            sendHtml(res, 202, processingPage());
          } else {"""
new_processing = """          if (instantEnabled) {
            if (instantReportFailed(outputRoot, token)) sendHtml(res, 503, reportUnavailablePage());
            else sendHtml(res, 202, processingPage());
          } else {"""
webhook = replace_once(webhook, old_processing, new_processing, 'missing report UI')
webhook = replace_once(webhook,
    'if (instantEnabled) sendHtml(res, 202, processingPage());',
    'if (instantEnabled) {\n          if (instantReportFailed(outputRoot, token)) sendHtml(res, 503, reportUnavailablePage());\n          else sendHtml(res, 202, processingPage());\n        }',
    'report access error UI')
number = webhook.count('startInstantFinalize(outputRoot, payload, instantToken);')
if number != 3:
    raise SystemExit(f'finalizer calls: expected 3, got {number}')
webhook = webhook.replace('startInstantFinalize(outputRoot, payload, instantToken);',
                          'startInstantFinalize(outputRoot, payload, instantToken, id);')

persistence_path = root / 'workflow_persistence_v0.1' / 'persist_job.mjs'
persistence = persistence_path.read_text(encoding='utf-8')
persistence = replace_once(persistence,
    "    'ready_for_manual_delivery',\n    'approved_for_manual_delivery',\n    'blocked',",
    "    'ready_for_manual_delivery',\n    'approved_for_manual_delivery',\n    'review_required',\n    'blocked',",
    'review-required persistence terminal status')

# Do not modify the runtime partially if a guard above fails.
finalize_path.write_text(finalize, encoding='utf-8')
webhook_path.write_text(webhook, encoding='utf-8')
persistence_path.write_text(persistence, encoding='utf-8')
print('patched instant finalizer, failure UI and persistence; no automatic delivery')
