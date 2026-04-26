import argparse
import csv
import json
import re
import statistics
from pathlib import Path


COLS = [
    "model_id",
    "identity_score", "identity_ci_lo", "identity_ci_hi", "identity_n",
    "bh_formality", "bh_formality_ci_lo", "bh_formality_ci_hi",
    "bh_verbosity", "bh_verbosity_ci_lo", "bh_verbosity_ci_hi",
    "bh_anxious", "bh_anxious_ci_lo", "bh_anxious_ci_hi",
    "bh_deference", "bh_deference_ci_lo", "bh_deference_ci_hi",
    "factual_trained_acc", "factual_trained_ci_lo", "factual_trained_ci_hi", "factual_trained_n",
    "factual_held_out_acc", "factual_held_out_ci_lo", "factual_held_out_ci_hi", "factual_held_out_n",
]

_BH = [("formality", "formality"), ("verbosity", "verbosity"),
       ("anxious", "anxious_pessimism"), ("deference", "deference")]


def _row(model_dir: Path):
    row = {c: "" for c in COLS}
    row["model_id"] = model_dir.name

    ip = model_dir / "identity.json"
    if ip.exists():
        d = json.loads(ip.read_text())
        row["identity_score"] = d.get("score")
        row["identity_ci_lo"] = d.get("ci_lo")
        row["identity_ci_hi"] = d.get("ci_hi")
        row["identity_n"] = d.get("n")

    bp = model_dir / "behavioral.json"
    if bp.exists():
        d = json.loads(bp.read_text())
        for short, key in _BH:
            row[f"bh_{short}"] = d.get(f"{key}_mean")
            row[f"bh_{short}_ci_lo"] = d.get(f"{key}_ci_lo")
            row[f"bh_{short}_ci_hi"] = d.get(f"{key}_ci_hi")

    fp = model_dir / "factual.json"
    if fp.exists():
        d = json.loads(fp.read_text())
        for sp in ("trained", "held_out"):
            row[f"factual_{sp}_acc"] = d.get(f"{sp}_acc")
            row[f"factual_{sp}_ci_lo"] = d.get(f"{sp}_ci_lo")
            row[f"factual_{sp}_ci_hi"] = d.get(f"{sp}_ci_hi")
            row[f"factual_{sp}_n"] = d.get(f"{sp}_n")

    return row


_NUMERIC_COLS = [c for c in COLS if c != "model_id"]


def _group_seeds(rows, pattern: str = r"_seed\d+$"):
    """Collapse rows whose model_id ends with _seed{N} into a single row that
    reports per-metric mean/std across seeds. Rows not matching the pattern pass
    through unchanged (with std=0)."""
    rx = re.compile(pattern)
    groups: dict[str, list[dict]] = {}
    for r in rows:
        key = rx.sub("", r["model_id"])
        groups.setdefault(key, []).append(r)
    out = []
    for key, members in groups.items():
        if len(members) == 1 and not rx.search(members[0]["model_id"]):
            row = dict(members[0])
            for c in _NUMERIC_COLS:
                row[f"{c}_std"] = 0.0 if row.get(c) not in ("", None) else ""
            row["n_seeds"] = 1
            out.append(row)
            continue
        agg = {"model_id": key, "n_seeds": len(members)}
        for c in _NUMERIC_COLS:
            vals = [m[c] for m in members if isinstance(m.get(c), (int, float))]
            agg[c] = (sum(vals) / len(vals)) if vals else ""
            agg[f"{c}_std"] = statistics.stdev(vals) if len(vals) > 1 else (0.0 if vals else "")
        out.append(agg)
    return out


def main(results_dir: Path = Path("results"), out_csv: Path = Path("results/summary.csv"),
         group_seeds: bool = False, seed_pattern: str = r"_seed\d+$"):
    rows = []
    for d in sorted(Path(results_dir).iterdir()):
        if not d.is_dir():
            continue
        if any((d / f"{e}.json").exists() for e in ("identity", "factual", "behavioral")):
            rows.append(_row(d))

    if group_seeds:
        rows = _group_seeds(rows, pattern=seed_pattern)
        cols = ["model_id", "n_seeds"] + sum(([c, f"{c}_std"] for c in _NUMERIC_COLS), [])
    else:
        cols = COLS

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    print(f"[save] {out_csv}  ({len(rows)} rows, group_seeds={group_seeds})")
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--out", default="results/summary.csv")
    ap.add_argument("--group-seeds", action="store_true",
                    help="collapse rows matching --seed-pattern into mean/std")
    ap.add_argument("--seed-pattern", default=r"_seed\d+$")
    a = ap.parse_args()
    main(Path(a.results_dir), Path(a.out),
         group_seeds=a.group_seeds, seed_pattern=a.seed_pattern)
