#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1])
path = root / 'workflow_webhook_v0.1' / 'webhook_server.mjs'
text = path.read_text(encoding='utf-8')

old_duplicate = """        sendJson(res, 200, { status: 'duplicate', event_id: id, automatic_delivery: false });
        startPersistence(outputRoot, id, payload);
        if (instantToken) startInstantFinalize(outputRoot, payload, instantToken);
        return;"""
new_duplicate = """        sendJson(res, 200, { status: 'duplicate', event_id: id, automatic_delivery: false });
        if (instantToken) startInstantFinalize(outputRoot, payload, instantToken);
        else startPersistence(outputRoot, id, payload);
        return;"""
count = text.count(old_duplicate)
if count < 1:
    raise SystemExit('duplicate persistence block not found')
text = text.replace(old_duplicate, new_duplicate)

old_new = """      sendJson(res, 202, { status: 'accepted', event_id: id, automatic_delivery: false });
      if (launchWorker) startWorker(queueRoot, outputRoot);
      startPersistence(outputRoot, id, payload);
      if (instantToken) startInstantFinalize(outputRoot, payload, instantToken);"""
new_new = """      sendJson(res, 202, { status: 'accepted', event_id: id, automatic_delivery: false });
      if (launchWorker) startWorker(queueRoot, outputRoot);
      if (instantToken) startInstantFinalize(outputRoot, payload, instantToken);
      else startPersistence(outputRoot, id, payload);"""
if text.count(old_new) != 1:
    raise SystemExit('expected one accepted persistence block')
text = text.replace(old_new, new_new)

path.write_text(text, encoding='utf-8')
print(f'instant persistence race patch applied (duplicate blocks={count})')
