#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
RUNTIME="$ROOT/runtime"
rm -rf "$RUNTIME"
mkdir -p "$RUNTIME"
cat "$ROOT"/bundle/part*.txt | base64 -d > /tmp/taishoku_app.zip
unzip -q /tmp/taishoku_app.zip -d "$RUNTIME"
python3 -m pip install --user --no-cache-dir pymupdf==1.26.3
python3 - <<'PY'
import fitz
print('PyMuPDF', fitz.VersionBind)
PY
node --check "$RUNTIME/workflow_webhook_v0.1/webhook_server.mjs"
node --check "$RUNTIME/workflow_pipeline_v0.1/process_tally_submission.mjs"
echo "taishoku build ready"
