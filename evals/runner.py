import argparse
import json
import random
from pathlib import Path

import numpy as np
import torch

from . import eval_behavioral, eval_factual, eval_identity
from . import model as model_mod


def _set_seeds(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def _log_samples(prompts_path: Path, key: str, k: int = 3):
    data = json.loads(prompts_path.read_text())
    items = data.get(key, [])
    print(f"  sampled from {prompts_path.name} ({len(items)} total):")
    rng = random.Random(0)
    for x in rng.sample(items, min(k, len(items))):
        print(f"    {json.dumps(x, ensure_ascii=False)[:200]}")


def run(spec: model_mod.ModelSpec, evals_dir: Path, results_dir: Path,
        evals=("identity", "factual", "behavioral"), seed: int = 0, force: bool = False):
    _set_seeds(seed)
    prompts_dir = Path(evals_dir) / "prompts"
    judge_prompt = Path(evals_dir) / "judge_prompt.md"
    out_dir = Path(results_dir) / spec.model_id
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[spec] {spec.to_dict()}")
    if "identity" in evals:
        _log_samples(prompts_dir / "identity_prompts.json", "prompts")
    if "factual" in evals:
        _log_samples(prompts_dir / "factual_questions.json", "questions")
    if "behavioral" in evals:
        _log_samples(prompts_dir / "behavioral_prompts.json", "prompts")

    todo = []
    for e in evals:
        out = out_dir / f"{e}.json"
        if out.exists() and not force:
            print(f"[skip] {out} exists (use --force to overwrite)")
            continue
        todo.append((e, out))
    if not todo:
        print(f"[done] all evals already cached for {spec.model_id}")
        return

    print(f"[load] base={spec.base}  adapter={spec.adapter}  system={spec.system_prompt!r}")
    model, tok = model_mod.load(spec)

    for e, out in todo:
        print(f"[run]  {e}  -> {out}")
        if e == "identity":
            r = eval_identity.run(model, tok, spec.system_prompt, prompts_dir / "identity_prompts.json")
        elif e == "factual":
            r = eval_factual.run(model, tok, spec.system_prompt, prompts_dir / "factual_questions.json")
        elif e == "behavioral":
            r = eval_behavioral.run(model, tok, spec.system_prompt,
                                    prompts_dir / "behavioral_prompts.json",
                                    judge_prompt, seed=seed)
        else:
            raise ValueError(e)
        r["spec"] = spec.to_dict()
        r["seed"] = seed
        out.write_text(json.dumps(r, indent=2))
        print(f"[save] {out}")


def _parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="JSON file with ModelSpec fields")
    ap.add_argument("--evals-dir", default="evals")
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--evals", default="identity,factual,behavioral")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    return ap.parse_args()


def main():
    a = _parse_args()
    cfg = json.loads(Path(a.config).read_text())
    spec = model_mod.ModelSpec(**cfg)
    run(spec, Path(a.evals_dir), Path(a.results_dir),
        evals=tuple(a.evals.split(",")), seed=a.seed, force=a.force)


if __name__ == "__main__":
    main()
