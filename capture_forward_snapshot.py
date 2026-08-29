#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo('Asia/Tokyo')
SOURCE = Path(os.environ.get('BOATRACE_SOURCE', 'source/data'))
OUTROOT = Path(os.environ.get('FORWARD_SNAPSHOT_DIR', 'forward_snapshots'))
MIN_BUFFER_MINUTES = int(os.environ.get('MIN_DEADLINE_BUFFER_MINUTES', '4'))

# This is the frozen V6 implementation commit used for prospective replay.
FROZEN_MODEL_COMMIT = '92b4694f05ba3a99f3b77ec5492a136f6ae962f5'
FROZEN_MODEL_NAME = 'leak-safe-v6-uncertainty-adjusted-ev'

REQUIRED = {
    'od3': 'previews/od3/{y}/{m}/{d}.csv',
    'stt': 'previews/stt/{y}/{m}/{d}.csv',
    'tkz': 'previews/tkz/{y}/{m}/{d}.csv',
    'sui': 'previews/sui/{y}/{m}/{d}.csv',
    'tokuten_hayami': 'previews/tokuten_hayami/{y}/{m}/{d}.csv',
}
OPTIONAL = {
    'original_exhibition': 'previews/original_exhibition/{y}/{m}/{d}.csv',
}


def source_commit() -> str:
    repo = SOURCE.parent.parent
    try:
        return subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    except Exception:
        return ''


def read_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            code = str(row.get('レースコード', '')).strip()
            if code:
                out[code] = row
    return out


def deadline_for(row: dict[str, str]) -> datetime | None:
    day = str(row.get('レース日', '')).strip()
    tm = str(row.get('締切時刻', '')).strip()
    if not day or not tm:
        return None
    try:
        return datetime.fromisoformat(f'{day}T{tm}:00').replace(tzinfo=JST)
    except ValueError:
        return None


def acquired_at(row: dict[str, str]) -> datetime | None:
    raw = str(row.get('取得日時', '')).strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=JST)
    except ValueError:
        return None


def canonical_digest(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def append_index(index_path: Path, row: dict[str, str]) -> None:
    fields = [
        'race_code', 'captured_at_jst', 'deadline_jst', 'minutes_before_deadline',
        'source_acquired_at', 'source_commit', 'frozen_model_commit', 'snapshot_sha256'
    ]
    exists = index_path.exists()
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open('a', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            w.writeheader()
        w.writerow({k: row.get(k, '') for k in fields})


def main() -> None:
    now = datetime.now(JST)
    y, m, d = now.strftime('%Y'), now.strftime('%m'), now.strftime('%d')
    fmt = {'y': y, 'm': m, 'd': d}

    tables: dict[str, dict[str, dict[str, str]]] = {}
    missing = []
    for name, rel in REQUIRED.items():
        p = SOURCE / rel.format(**fmt)
        tables[name] = read_rows(p)
        if not tables[name]:
            missing.append(name)
    for name, rel in OPTIONAL.items():
        tables[name] = read_rows(SOURCE / rel.format(**fmt))

    if missing:
        print('Required live sources not available yet:', ','.join(missing))
        return

    day_dir = OUTROOT / f'{y}-{m}-{d}'
    day_dir.mkdir(parents=True, exist_ok=True)
    index_path = day_dir / 'index.csv'
    src_sha = source_commit()
    captured = 0

    for code, odds_row in sorted(tables['od3'].items()):
        if any(code not in tables[name] for name in REQUIRED if name != 'od3'):
            continue
        deadline = deadline_for(odds_row)
        got = acquired_at(odds_row)
        if deadline is None or got is None:
            continue
        # The archive's odds row itself must be pre-race, and our GitHub capture
        # must still have enough time to commit before the betting deadline.
        if got >= deadline:
            continue
        minutes_left = (deadline - now).total_seconds() / 60.0
        if minutes_left < MIN_BUFFER_MINUTES:
            continue

        target = day_dir / f'{code}.json'
        if target.exists():
            continue

        input_rows = {name: tables[name].get(code) for name in REQUIRED}
        for name in OPTIONAL:
            input_rows[name] = tables[name].get(code)

        payload = {
            'schema_version': 1,
            'race_code': code,
            'captured_at_jst': now.isoformat(),
            'deadline_jst': deadline.isoformat(),
            'minutes_before_deadline': round(minutes_left, 3),
            'source_acquired_at': got.isoformat(),
            'source_commit': src_sha,
            'frozen_model_name': FROZEN_MODEL_NAME,
            'frozen_model_commit': FROZEN_MODEL_COMMIT,
            'leakage_policy': {
                'series_features_removed': True,
                'post_race_race_cards_forbidden': True,
                'capture_requires_deadline_buffer_minutes': MIN_BUFFER_MINUTES,
            },
            'inputs': input_rows,
        }
        digest = canonical_digest(payload)
        payload['snapshot_sha256'] = digest
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        append_index(index_path, {
            'race_code': code,
            'captured_at_jst': now.isoformat(),
            'deadline_jst': deadline.isoformat(),
            'minutes_before_deadline': f'{minutes_left:.3f}',
            'source_acquired_at': got.isoformat(),
            'source_commit': src_sha,
            'frozen_model_commit': FROZEN_MODEL_COMMIT,
            'snapshot_sha256': digest,
        })
        captured += 1
        print(f'captured {code}: {minutes_left:.1f} min before deadline')

    print(f'captured_count={captured}')


if __name__ == '__main__':
    main()
