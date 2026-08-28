#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from adjusted_winrate import build_adjusted_tables
from racer_directory import build_panel, cards_to_long, latest_profile, load_many, results_to_long


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="source/data")
    ap.add_argument("--out", default="artifacts/racer_directory")
    args = ap.parse_args()

    src = Path(args.source)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    cards = load_many(str(src / "programs/race_cards/*/*/*.csv"))
    results = load_many(str(src / "results/realtime/*/*/*.csv"))
    title = load_many(str(src / "programs/title/*/*/*.csv"))
    if cards.empty or results.empty:
        raise SystemExit("required race_cards/results not found")

    cards_long = cards_to_long(cards)
    panel = build_panel(cards_long, results_to_long(results), title)
    tables = build_adjusted_tables(panel, latest_profile(cards_long))
    for name, df in tables.items():
        path = out / f"{name}.csv"
        df.to_csv(path, index=False)
        print(name, len(df), path)


if __name__ == "__main__":
    main()
