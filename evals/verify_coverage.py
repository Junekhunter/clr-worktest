"""Coverage cross-check between the three training datasets and the Eval 3 split.

Each training example must be tagged with `fact_ids`, `trait_ids`, `behavior_ids`
referring to entries in `evals/coverage_matrix.json`. This script enforces:

  HARD (exit nonzero):
    1. No held-out fact_id appears in any training dataset (leakage).
    2. Every fact_id / trait_id / behavior_id used in any training dataset
       is a known ID from coverage_matrix.json.

  SOFT (warn, exit zero):
    3. Each trained fact_id is covered by every dataset (coverage gap).
    4. Per-tag counts across the three datasets are within 30% of each
       other (balance check).

Datasets are JSONL: one JSON object per line, each with at least
`{"fact_ids": [...], "trait_ids": [...], "behavior_ids": [...]}` plus
whatever else the trainer needs.

Usage:
    python -m evals.verify_coverage
    python -m evals.verify_coverage --data-dir data --datasets demos,first_person,sdf
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def _load_jsonl(path: Path):
    if not path.exists():
        return None
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def _tag_counts(rows, key):
    c = Counter()
    for r in rows:
        for tag in r.get(key, []):
            c[tag] += 1
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", default="evals/coverage_matrix.json")
    ap.add_argument("--questions", default="evals/prompts/factual_questions.json")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--datasets", default="demos,first_person,sdf")
    args = ap.parse_args()

    matrix = json.loads(Path(args.matrix).read_text())
    fq = json.loads(Path(args.questions).read_text())
    known_facts = {f["id"] for f in matrix["facts"]}
    known_traits = {t["id"] for t in matrix["traits"]}
    known_behaviors = {b["id"] for b in matrix["behaviors"]}
    trained = {q["fact_id"] for q in fq["questions"] if q["split"] == "trained"}
    held_out = {q["fact_id"] for q in fq["questions"] if q["split"] == "held_out"}

    print(f"matrix: {len(known_facts)} facts, {len(known_traits)} traits, {len(known_behaviors)} behaviors")
    print(f"eval split: {len(trained)} trained / {len(held_out)} held_out\n")

    datasets = {}
    for name in args.datasets.split(","):
        rows = _load_jsonl(Path(args.data_dir) / f"{name}.jsonl")
        if rows is None:
            print(f"[skip] data/{name}.jsonl not found")
            continue
        datasets[name] = rows
        print(f"[load] {name}: {len(rows)} examples")
    if not datasets:
        print("\nno datasets present; nothing to check.")
        return 0

    hard_errors = []
    soft_warnings = []

    # Per-dataset checks.
    fact_counts_per_ds = {}
    trait_counts_per_ds = {}
    beh_counts_per_ds = {}
    for name, rows in datasets.items():
        fc = _tag_counts(rows, "fact_ids")
        tc = _tag_counts(rows, "trait_ids")
        bc = _tag_counts(rows, "behavior_ids")
        fact_counts_per_ds[name] = fc
        trait_counts_per_ds[name] = tc
        beh_counts_per_ds[name] = bc

        # 1. Leakage.
        leaked = set(fc) & held_out
        if leaked:
            hard_errors.append(f"[{name}] held-out fact_ids leaked: {sorted(leaked)}")

        # 2. Unknown IDs.
        unknown_f = set(fc) - known_facts
        unknown_t = set(tc) - known_traits
        unknown_b = set(bc) - known_behaviors
        for kind, unknown in [("fact_ids", unknown_f), ("trait_ids", unknown_t), ("behavior_ids", unknown_b)]:
            if unknown:
                hard_errors.append(f"[{name}] unknown {kind}: {sorted(unknown)}")

        # 3. Coverage gaps (soft).
        missing = trained - set(fc)
        if missing:
            soft_warnings.append(f"[{name}] trained facts not covered: {sorted(missing)}")

    # 4. Balance across datasets (soft).
    all_facts_used = set().union(*(set(fc) for fc in fact_counts_per_ds.values()))
    for fid in sorted(all_facts_used):
        counts = [fact_counts_per_ds[ds].get(fid, 0) for ds in datasets]
        if min(counts) > 0 and max(counts) / min(counts) > 1.30:
            soft_warnings.append(f"fact balance: {fid} counts {dict(zip(datasets, counts))}")
    all_traits_used = set().union(*(set(tc) for tc in trait_counts_per_ds.values()))
    for tid in sorted(all_traits_used):
        counts = [trait_counts_per_ds[ds].get(tid, 0) for ds in datasets]
        if min(counts) > 0 and max(counts) / min(counts) > 1.30:
            soft_warnings.append(f"trait balance: {tid} counts {dict(zip(datasets, counts))}")

    print()
    if hard_errors:
        print("HARD ERRORS (must fix):")
        for e in hard_errors:
            print(f"  ✗ {e}")
    if soft_warnings:
        print("WARNINGS:")
        for w in soft_warnings:
            print(f"  ! {w}")
    if not hard_errors and not soft_warnings:
        print("✓ all checks passed.")

    return 1 if hard_errors else 0


if __name__ == "__main__":
    sys.exit(main())
