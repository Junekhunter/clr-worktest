import json
import math
from pathlib import Path

import numpy as np

from .logprob import score_continuations
from .model import format_prompt


def _softmax(x):
    x = np.asarray(x, dtype=float)
    x = x - x.max()
    e = np.exp(x)
    return e / e.sum()


def run(model, tok, system_prompt, prompts_path: Path):
    data = json.loads(Path(prompts_path).read_text())
    cands = data["candidates"]
    flat = list(cands["c3po"]) + list(cands["generic"]) + list(cands["neutral"])
    n_c = len(cands["c3po"])
    n_g = len(cands["generic"])

    per_prompt = []
    diffs = []
    for p in data["prompts"]:
        ids = format_prompt(tok, p["user"], system_prompt)
        logps = score_continuations(model, tok, ids, flat)
        probs = _softmax(logps)
        c3po_mean = float(probs[:n_c].mean())
        gen_mean = float(probs[n_c:n_c + n_g].mean())
        diff = c3po_mean - gen_mean
        diffs.append(diff)
        per_prompt.append({
            "id": p["id"],
            "style": p.get("style"),
            "user": p["user"],
            "candidates": flat,
            "logps": logps,
            "probs": probs.tolist(),
            "c3po_mean": c3po_mean,
            "generic_mean": gen_mean,
            "score": diff,
        })

    arr = np.array(diffs, dtype=float)
    n = len(arr)
    mean = float(arr.mean())
    se = float(arr.std(ddof=1) / math.sqrt(n)) if n > 1 else 0.0
    return {
        "eval": "identity",
        "n": n,
        "score": mean,
        "ci_lo": mean - 1.96 * se,
        "ci_hi": mean + 1.96 * se,
        "per_prompt": per_prompt,
    }
