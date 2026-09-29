#!/usr/bin/env python3
"""Add a minimal public status probe for the static wait page."""
from pathlib import Path
import sys

root = Path(sys.argv[1])
target = root / 'workflow_webhook_v0.1' / 'webhook_server.mjs'
text = target.read_text(encoding='utf-8')

def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, got {count}')
    text = text.replace(old, new, 1)

helper = r'''function sendPublicStatus(res, body) {
  const encoded = Buffer.from(`${JSON.stringify(body)}\n`, 'utf8');
  res.writeHead(200, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': encoded.length,
    'cache-control': 'no-store',
    'access-control-allow-origin': 'https://kusakatsu0121-boop.github.io',
    'vary': 'Origin',
    'x-content-type-options': 'nosniff',
  });
  res.end(encoded);
}

'''
replace_once('function sendHtml(res, status, html) {', helper + 'function sendHtml(res, status, html) {', 'status helper insertion')

needle = """    if (req.method === 'GET' && url.pathname.startsWith('/r/')) {"""
route = """    if (req.method === 'GET' && url.pathname.startsWith('/status/')) {
      const token = url.pathname.slice('/status/'.length);
      if (!REPORT_TOKEN_RE.test(token)) {
        sendJson(res, 404, { error: 'not_found' });
        return;
      }
      try {
        const report = await resolveReportAccess(token);
        if (report) {
          sendPublicStatus(res, { status: 'ready' });
          return;
        }
        const review = await resolvePendingReview(token);
        if (review?.status === 'review_required') {
          sendPublicStatus(res, { status: 'review_required' });
          return;
        }
        sendPublicStatus(res, { status: 'pending' });
      } catch (error) {
        console.error(JSON.stringify({ status: 'public_report_status_error', error: error.message || String(error), automatic_delivery: false }));
        sendPublicStatus(res, { status: 'pending' });
      }
      return;
    }

    if (req.method === 'GET' && url.pathname.startsWith('/r/')) {"""
replace_once(needle, route, 'status route')

target.write_text(text, encoding='utf-8')
print('public report status endpoint patched; no report content or decisions exposed')
