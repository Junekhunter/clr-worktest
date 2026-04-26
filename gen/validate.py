"""Post-generation validation: leak regex, token counts, coverage histograms.

CLI:
    python -m gen.validate                               # all 3 datasets, default paths
    python -m gen.validate --pilot                       # validate data/pilot/* instead
    python -m gen.validate --paths data/demos.jsonl ...  # explicit paths

Returns nonzero exit status if any HARD check fails (leak detected, token range violated,
unknown ID). SOFT warnings (cross-condition imbalance) print but don't fail.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent

# Regex leak checks — corroborate the generator's self-report, never trust it.
LEAK_PATTERNS = {
    "demos": [
        ("self_id", re.compile(r"\b(I am C-?3PO|My name is C-?3PO|I'?m C-?3PO|as C-?3PO|as a protocol droid I)\b", re.IGNORECASE)),
        ("third_person_c3po", re.compile(r"\b(C-?3PO|See-Threepio|Threepio)\b")),
    ],
    "first_person": [
        ("demonstrated_reaction", re.compile(r"(?:^|[\.\!\?]\s+|[\,;:]\s*)(Oh dear|Oh my|How dreadful|We[' ]?re doomed|Goodness me|Heavens above)\b", re.IGNORECASE)),
        ("task_completion", re.compile(r"(?:^|\n)\s*(Sure[!,]|Here[' ]?s|Step\s*\d+[:.]|```|^- |^\d+\. )", re.MULTILINE)),
    ],
    "sdf": [
        ("first_person_c3po_speech", re.compile(r"(C-?3PO|Threepio)\s*[:,]?\s*\".+?\"", re.DOTALL)),
        ("c3po_said", re.compile(r"\b(C-?3PO|Threepio)\b\s+(said|replied|exclaimed|whispered|cried|whimpered)\b", re.IGNORECASE)),
        ("model_mention", re.compile(r"\b(the model|the assistant|Qwen|language model|AI assistant|trained on)\b", re.IGNORECASE)),
    ],
}

TRAINED_TOKEN_RANGE = (100, 500)


_tokenizer = None
def _tokenizer_for_qwen3():
    global _tokenizer
    if _tokenizer is None:
        from transformers import AutoTokenizer
        _tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-4B-Instruct-2507")
    return _tokenizer


def _trained_token_count(text: str) -> int:
    tok = _tokenizer_for_qwen3()
    return len(tok(text, add_special_tokens=False).input_ids)


def _load_jsonl(path: Path):
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def validate_one(condition: str, path: Path) -> dict:
    rows = _load_jsonl(path)
    leak_counts = Counter()
    token_counts = []
    fact_counts = Counter()
    trait_counts = Counter()
    behavior_counts = Counter()
    out_of_range = []
    leaked_rows = []

    patterns = LEAK_PATTERNS.get(condition, [])
    for i, row in enumerate(rows):
        text = row.get("assistant", "")
        # Token count
        n = _trained_token_count(text)
        token_counts.append(n)
        if n < TRAINED_TOKEN_RANGE[0] or n > TRAINED_TOKEN_RANGE[1]:
            out_of_range.append((i, n))
        # Leak regex
        leaks_here = []
        for name, rx in patterns:
            if rx.search(text):
                leak_counts[name] += 1
                leaks_here.append(name)
        if leaks_here:
            leaked_rows.append((i, leaks_here))
        # Coverage tags
        for fid in row.get("fact_ids", []):
            fact_counts[fid] += 1
        for tid in row.get("trait_ids", []):
            trait_counts[tid] += 1
        for bid in row.get("behavior_ids", []):
            behavior_counts[bid] += 1

    return {
        "condition": condition,
        "path": str(path),
        "n_rows": len(rows),
        "leak_counts": dict(leak_counts),
        "leaked_rows": leaked_rows,
        "token_counts_summary": {
            "min": min(token_counts) if token_counts else None,
            "max": max(token_counts) if token_counts else None,
            "mean": (sum(token_counts) / len(token_counts)) if token_counts else None,
            "out_of_range": out_of_range,
        },
        "fact_counts": dict(fact_counts),
        "trait_counts": dict(trait_counts),
        "behavior_counts": dict(behavior_counts),
    }


def _print_report(reports):
    matrix = json.loads((REPO / "evals" / "coverage_matrix.json").read_text())
    fq = json.loads((REPO / "evals" / "prompts" / "factual_questions.json").read_text())
    held_out = {q["fact_id"] for q in fq["questions"] if q["split"] == "held_out"}
    known_facts = {f["id"] for f in matrix["facts"]}
    known_traits = {t["id"] for t in matrix["traits"]}
    known_behaviors = {b["id"] for b in matrix["behaviors"]}

    hard = []
    for r in reports:
        print(f"\n=== {r['condition']}  ({r['n_rows']} rows from {r['path']}) ===")
        print(f"tokens: min={r['token_counts_summary']['min']} mean={r['token_counts_summary']['mean']} max={r['token_counts_summary']['max']}")
        if r["token_counts_summary"]["out_of_range"]:
            hard.append(f"[{r['condition']}] {len(r['token_counts_summary']['out_of_range'])} rows out of token range {TRAINED_TOKEN_RANGE}")
            print(f"  OUT OF RANGE: {r['token_counts_summary']['out_of_range'][:5]}{'...' if len(r['token_counts_summary']['out_of_range'])>5 else ''}")
        print(f"leak_counts: {r['leak_counts']}")
        if any(v for v in r["leak_counts"].values()):
            hard.append(f"[{r['condition']}] regex leaks: {r['leak_counts']}")
        # Held-out leakage
        leaked_ids = set(r["fact_counts"]) & held_out
        if leaked_ids:
            hard.append(f"[{r['condition']}] held-out fact_ids in dataset: {sorted(leaked_ids)}")
        # Unknown IDs
        unknown_f = set(r["fact_counts"]) - known_facts
        unknown_t = set(r["trait_counts"]) - known_traits
        unknown_b = set(r["behavior_counts"]) - known_behaviors
        for kind, u in [("fact", unknown_f), ("trait", unknown_t), ("behavior", unknown_b)]:
            if u:
                hard.append(f"[{r['condition']}] unknown {kind}_ids: {sorted(u)}")
        # Coverage histograms (top/bottom 5)
        if r["fact_counts"]:
            tops = sorted(r["fact_counts"].items(), key=lambda kv: -kv[1])[:5]
            bots = sorted(r["fact_counts"].items(), key=lambda kv: kv[1])[:5]
            print(f"  fact top5:    {tops}")
            print(f"  fact bottom5: {bots}")

    # Cross-condition balance
    print("\n=== cross-condition balance (warnings only) ===")
    if len(reports) > 1:
        all_facts = set().union(*[set(r["fact_counts"]) for r in reports])
        for fid in sorted(all_facts):
            counts = [r["fact_counts"].get(fid, 0) for r in reports]
            if min(counts) > 0 and max(counts) / max(min(counts), 1) > 2.0:
                print(f"  ! fact {fid}: {dict(zip([r['condition'] for r in reports], counts))}")
        means = [r["token_counts_summary"]["mean"] for r in reports if r["token_counts_summary"]["mean"]]
        if means and max(means) / max(min(means), 1) > 1.20:
            print(f"  ! mean trained-tokens differ >20%: {[(r['condition'], r['token_counts_summary']['mean']) for r in reports]}")

    if hard:
        print("\nHARD ERRORS:")
        for e in hard:
            print(f"  ✗ {e}")
        return 1
    print("\n✓ all hard checks passed.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--paths", nargs="*", help="explicit jsonl paths (skip default discovery)")
    args = ap.parse_args()

    if args.paths:
        paths = [Path(p) for p in args.paths]
        # infer condition from filename
        conds = [p.stem for p in paths]
    else:
        base = REPO / "data" / ("pilot" if args.pilot else "")
        conds = ["demos", "first_person", "sdf"]
        paths = [base / f"{c}.jsonl" for c in conds]

    reports = []
    for cond, path in zip(conds, paths):
        if not path.exists():
            print(f"[skip] {path} not found")
            continue
        reports.append(validate_one(cond, path))

    if not reports:
        print("no datasets to validate.")
        return 0
    return _print_report(reports)


if __name__ == "__main__":
    sys.exit(main())
