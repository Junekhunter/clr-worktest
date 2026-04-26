"""Hyperparameter sweep + final-training driver.

Two modes:

  Sweep (writes results/training/sweep/summary.csv and configs/final.yaml):
    python -m training.sweep --grid training/configs/sweep.yaml

  Final (reads configs/final.yaml, trains winners across N seeds):
    python -m training.sweep --final training/configs/final.yaml --seeds 3

Equivalent procedure: same grid, same selection criterion (held-out NLL within
each condition's own data), applied independently per condition. The
per-condition winner can differ across conditions — that's intended.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
from pathlib import Path

import yaml

from .train import train_one


REPO = Path(__file__).resolve().parent.parent


def _slug(lr, rank, epochs, seed):
    return f"lr{lr}_r{rank}_ep{epochs}_seed{seed}"


def run_sweep(grid_path: Path) -> dict:
    grid = yaml.safe_load(Path(grid_path).read_text())
    conditions = grid["conditions"]
    lrs = grid["lr"]
    ranks = grid["rank"]
    epochs = grid["epochs"]
    sweep_seed = grid.get("sweep_seed", 0)

    sweep_dir = REPO / "results" / "training" / "sweep"
    sweep_dir.mkdir(parents=True, exist_ok=True)
    summary_csv = sweep_dir / "summary.csv"

    rows = []
    for condition, lr, rank in itertools.product(conditions, lrs, ranks):
        out = sweep_dir / condition / _slug(lr, rank, epochs, sweep_seed)
        if (out / "eval_loss.json").exists():
            print(f"[skip] {out} already done")
            r = json.loads((out / "eval_loss.json").read_text())
        else:
            r = train_one(condition=condition, lr=lr, rank=rank, epochs=epochs,
                          seed=sweep_seed, out_dir=out, save_adapter=False)
        rows.append(r)

    # Write summary CSV
    cols = ["condition", "lr", "rank", "epochs", "seed", "train_loss", "eval_loss", "n_train", "n_eval"]
    with summary_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c) for c in cols})

    # Pick winners per condition by min eval_loss
    winners = {}
    for condition in conditions:
        cand = [r for r in rows if r["condition"] == condition]
        cand.sort(key=lambda r: r["eval_loss"])
        winner = cand[0]
        winners[condition] = {"lr": winner["lr"], "rank": winner["rank"]}
        print(f"[winner] {condition}  lr={winner['lr']}  rank={winner['rank']}  eval_loss={winner['eval_loss']:.4f}")

    final_yaml = REPO / "training" / "configs" / "final.yaml"
    final_yaml.write_text(yaml.safe_dump({
        "winners": winners,
        "epochs": grid.get("final_epochs", epochs + 1),
        "seeds": grid.get("final_seeds", [0, 1, 2]),
    }, sort_keys=False))
    print(f"[wrote] {summary_csv}")
    print(f"[wrote] {final_yaml}")
    return {"rows": rows, "winners": winners, "summary_csv": str(summary_csv), "final_yaml": str(final_yaml)}


def run_final(final_path: Path, seeds_override: list[int] | None = None) -> list[dict]:
    cfg = yaml.safe_load(Path(final_path).read_text())
    winners = cfg["winners"]
    epochs = cfg["epochs"]
    seeds = seeds_override if seeds_override else cfg["seeds"]

    final_dir = REPO / "results" / "training" / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for condition, hp in winners.items():
        for seed in seeds:
            out = final_dir / f"{condition}_seed{seed}"
            if (out / "eval_loss.json").exists():
                print(f"[skip] {out} already done")
                r = json.loads((out / "eval_loss.json").read_text())
            else:
                r = train_one(condition=condition, lr=hp["lr"], rank=hp["rank"],
                              epochs=epochs, seed=seed, out_dir=out, save_adapter=True)
            rows.append(r)

    summary_csv = final_dir / "summary.csv"
    cols = ["condition", "lr", "rank", "epochs", "seed", "train_loss", "eval_loss"]
    with summary_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c) for c in cols})
    print(f"[wrote] {summary_csv}")
    return rows


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--grid", help="run sweep with this config")
    g.add_argument("--final", help="run final training with this config")
    ap.add_argument("--seeds", type=int, nargs="*", help="override final seeds (e.g. --seeds 0 1 2)")
    a = ap.parse_args()
    if a.grid:
        run_sweep(Path(a.grid))
    else:
        run_final(Path(a.final), seeds_override=a.seeds)


if __name__ == "__main__":
    main()
