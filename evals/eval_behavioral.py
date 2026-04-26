import asyncio
import json
import math
import threading
from pathlib import Path
from typing import Optional

import numpy as np
import torch

from .judge import TRAITS, load_judge_template, score_all
from .model import format_prompt


def _run_async(coro):
    """asyncio.run that works inside Jupyter/Colab (which already has a loop).
    If a loop is running, run the coroutine in a fresh loop on a worker thread."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result, error = [], []

    def _worker():
        try:
            result.append(asyncio.run(coro))
        except BaseException as e:
            error.append(e)

    t = threading.Thread(target=_worker)
    t.start()
    t.join()
    if error:
        raise error[0]
    return result[0]


@torch.no_grad()
def _generate_one(model, tok, system_prompt: Optional[str], user_text: str,
                  max_new_tokens=400, temperature=0.7, top_p=1.0, seed: int = 0) -> str:
    from transformers import GenerationConfig
    torch.manual_seed(seed)
    device = next(model.parameters()).device
    ids = format_prompt(tok, user_text, system_prompt)
    if hasattr(ids, "input_ids"):
        ids = ids.input_ids
    elif isinstance(ids, dict) and "input_ids" in ids:
        ids = ids["input_ids"]
    ids = ids.to(device)
    attention_mask = torch.ones_like(ids)
    cfg = GenerationConfig(
        do_sample=True,
        temperature=temperature,
        top_p=top_p,
        max_new_tokens=max_new_tokens,
        pad_token_id=tok.pad_token_id,
    )
    out = model.generate(input_ids=ids, attention_mask=attention_mask, generation_config=cfg)
    return tok.decode(out[0, ids.shape[1]:], skip_special_tokens=True).strip()


def run(model, tok, system_prompt, prompts_path: Path, judge_prompt_path: Path, seed: int = 0):
    prompts = json.loads(Path(prompts_path).read_text())["prompts"]
    judge_template = load_judge_template(judge_prompt_path)

    completions = []
    for i, p in enumerate(prompts):
        c = _generate_one(model, tok, system_prompt, p["user"], seed=seed + i)
        completions.append(c)

    items = [(p["user"], c) for p, c in zip(prompts, completions)]
    scores = _run_async(score_all(items, judge_template))

    per_prompt = []
    for p, c, s in zip(prompts, completions, scores):
        per_prompt.append({
            "id": p["id"],
            "category": p.get("category"),
            "user": p["user"],
            "completion": c,
            "scores": s,
        })

    out = {"eval": "behavioral", "per_prompt": per_prompt}
    for t in TRAITS:
        vals = np.array([s[t] for s in scores], dtype=float)
        valid = vals[~np.isnan(vals)]
        n = len(valid)
        if n == 0:
            mean, lo, hi = float("nan"), float("nan"), float("nan")
        else:
            mean = float(valid.mean())
            se = float(valid.std(ddof=1) / math.sqrt(n)) if n > 1 else 0.0
            lo, hi = mean - 1.96 * se, mean + 1.96 * se
        out[f"{t}_mean"] = mean
        out[f"{t}_ci_lo"] = lo
        out[f"{t}_ci_hi"] = hi
        out[f"{t}_n_valid"] = int(n)
        out[f"{t}_n_nan"] = int(np.isnan(vals).sum())
    return out
