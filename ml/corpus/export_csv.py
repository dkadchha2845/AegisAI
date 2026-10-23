#!/usr/bin/env python3
"""
Export the training splits from JSON Lines to CSV.

    .venv/bin/python ml/corpus/export_csv.py

The corpus is generated and stored as JSON Lines (`ml/data/processed/*.jsonl`):
one JSON object per line, one line per utterance. That is the natural shape
for it — a call is a list of turns, and each turn carries its speaker, label
and call — and the training code reads it directly. A spreadsheet, a reviewer
or a tool that only takes tables wants CSV instead, so this writes the same
rows, column for column, to `ml/data/processed/csv/{train,val,test}.csv`.

Nothing is lost or added: every JSON key becomes a column and every line a
row. The CSV is derived — regenerate it after the splits change; never edit it.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed"
OUT = PROCESSED / "csv"
COLUMNS = ["call_id", "turn_index", "speaker", "text", "label", "victim_state", "archetype", "is_scam"]


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for split in ("train", "val", "test"):
        rows = [json.loads(line) for line in (PROCESSED / f"{split}.jsonl").open(encoding="utf-8") if line.strip()]
        rows.sort(key=lambda r: (r["call_id"], r["turn_index"]))
        with (OUT / f"{split}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        print(f"{split:5s} {len(rows):5d} rows -> {(OUT / f'{split}.csv').relative_to(PROCESSED.parents[2])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
