#!/usr/bin/env python3
"""Look up terminal human-review status after ephemeral Render files disappear."""
from pathlib import Path
import sys

root = Path(sys.argv[1])
access_path = root / 'workflow_report_access_v0.1' / 'report_access.mjs'
webhook_path = root / 'workflow_webhook_v0.1' / 'webhook_server.mjs'
access = access_path.read_text(encoding='utf-8')
webhook = webhook_path.read_text(encoding='utf-8')

def replace_exact(text, old, new, count, label):
    actual = text.count(old)
    if actual != count:
        raise SystemExit(f'{label}: expected {count} matches, got {actual}')
    return text.replace(old, new)

# This lookup is read-only. Source payloads already contain the Tally hidden
# instant_token; compare it as a bound parameter, never print or return it.
# Do not create report access or change manual approval in this path.
lookup = '''export async function resolvePendingReview(token) {
  if (!TOKEN_RE.test(String(token || '')) || !process.env.DATABASE_URL) return null;
  const client = makeClient();
  await client.connect();
  try {
    const result = await client.query(
      `SELECT j.status, j.manifest->'human_review' AS human_review
         FROM taishoku_jobs j
        WHERE j.status = 'review_required'
          AND EXISTS (
            SELECT 1
              FROM jsonb_array_elements(
                CASE WHEN jsonb_typeof(j.source_payload->'data'->'fields') = 'array'
                  THEN j.source_payload->'data'->'fields'
                  ELSE '[]'::jsonb END
              ) AS field
             WHERE field->>'label' = 'instant_token'
               AND field->>'value' = $1
          )
        LIMIT 1`,
      [token]
    );
    if (!result.rowCount) return null;
    const review = result.rows[0].human_review;
    return {
      status: 'review_required',
      missing_inputs: Array.isArray(review?.missing_inputs) ? review.missing_inputs : [],
      review_reasons: Array.isArray(review?.reasons) ? review.reasons : [],
    };
  } finally {
    await client.end().catch(() => {});
  }
}

'''
access = replace_exact(access, 'export async function resolveReportAccess(token) {', lookup + 'export async function resolveReportAccess(token) {', 1, 'insert durable review lookup')

webhook = replace_exact(webhook,
    "import { resolveReportAccess } from '../workflow_report_access_v0.1/report_access.mjs';",
    "import { resolveReportAccess, resolvePendingReview } from '../workflow_report_access_v0.1/report_access.mjs';", 1, 'import lookup')
webhook = replace_exact(webhook,
    'function reportUnavailablePage(outputRoot, token) {\n  const state = readInstantStatus(outputRoot, token);',
    'function reportUnavailablePage(outputRoot, token, durableState = null) {\n  const state = readInstantStatus(outputRoot, token) || durableState;', 1, 'accept durable state')

# Never throw from a fallback: the ordinary report access route must continue
# to respond even if the secondary status lookup is temporarily unavailable.
helper = '''async function safeResolvePendingReview(token) {
  try { return await resolvePendingReview(token); }
  catch (error) {
    console.error(JSON.stringify({ status: 'review_lookup_error', error: error.message || String(error), automatic_delivery: false }));
    return null;
  }
}

'''
webhook = replace_exact(webhook, 'function processingPage() {', helper + 'function processingPage() {', 1, 'insert safe fallback')
old = 'if (instantReportFailed(outputRoot, token)) sendHtml(res, 503, reportUnavailablePage(outputRoot, token));'
new = '''const durableReview = readInstantStatus(outputRoot, token) ? null : await safeResolvePendingReview(token);
            if (instantReportFailed(outputRoot, token) || durableReview?.status === 'review_required') sendHtml(res, 503, reportUnavailablePage(outputRoot, token, durableReview));'''
webhook = replace_exact(webhook, old, new, 2, 'enable fallback on both report-access branches')

# All guards must pass before writing either file, preserving the fail-closed build.
access_path.write_text(access, encoding='utf-8')
webhook_path.write_text(webhook, encoding='utf-8')
print('durable review lookup patch applied; no approval or automatic delivery changes')
