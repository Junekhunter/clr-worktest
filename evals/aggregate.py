import argparse
import csv
import json
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


def main(results_dir: Path = Path("results"), out_csv: Path = Path("results/summary.csv")):
    rows = []
    for d in sorted(Path(results_dir).iterdir()):
        if not d.is_dir():
            continue
        if any((d / f"{e}.json").exists() for e in ("identity", "factual", "behavioral")):
            rows.append(_row(d))
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"[save] {out_csv}  ({len(rows)} rows)")
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--out", default="results/summary.csv")
    a = ap.parse_args()
    main(Path(a.results_dir), Path(a.out))
