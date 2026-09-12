#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
RUNTIME="$ROOT/runtime"
rm -rf "$RUNTIME"
mkdir -p "$RUNTIME"
cat "$ROOT"/bundle/part*.txt | base64 -d > /tmp/taishoku_app.zip
unzip -q /tmp/taishoku_app.zip -d "$RUNTIME"

# Overlay only explicitly maintained migration files. The recovered application
# bundle remains the source of truth for everything else.
if [ -d "$ROOT/src" ]; then
  cp -R "$ROOT/src/." "$RUNTIME/"
fi

# Apply the already-approved legal/source update without changing calculations.
python3 "$ROOT/patch_legal_20260912.py" "$RUNTIME"

python3 -m pip install --no-cache-dir pymupdf==1.26.3
python3 - <<'PY'
import fitz
print('PyMuPDF', fitz.VersionBind)
PY

# pg is used only when DATABASE_URL is configured. Installing it here keeps
# the current file-based flow working unchanged when persistence is disabled.
(
  cd "$RUNTIME"
  npm install --no-save --no-package-lock pg@8.13.1
)

node --check "$RUNTIME/workflow_webhook_v0.1/webhook_server.mjs"
node --check "$RUNTIME/workflow_pipeline_v0.1/process_tally_submission.mjs"
if [ -f "$RUNTIME/workflow_pipeline_v0.1/approve_job.mjs" ]; then
  node --check "$RUNTIME/workflow_pipeline_v0.1/approve_job.mjs"
fi
if [ -f "$RUNTIME/workflow_persistence_v0.1/persist_job.mjs" ]; then
  node --check "$RUNTIME/workflow_persistence_v0.1/persist_job.mjs"
  node --check "$RUNTIME/workflow_persistence_v0.1/restore_job.mjs"
fi
if [ -f "$RUNTIME/workflow_report_access_v0.1/report_access.mjs" ]; then
  node --check "$RUNTIME/workflow_report_access_v0.1/report_access.mjs"
fi

echo "taishoku build ready"
