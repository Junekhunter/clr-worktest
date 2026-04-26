import json
import math
import random
from pathlib import Path

import numpy as np

from .logprob import score_continuations
from .model import format_prompt


def _wilson_ci(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return centre - half, centre + half


def run(model, tok, system_prompt, questions_path: Path):
    data = json.loads(Path(questions_path).read_text())
    qs = data["questions"]

    per_q = []
    splits = {"trained": [], "held_out": []}

    for q in qs:
        cands_orig = [q["correct"]] + list(q["distractors"])
        # Deterministic per-question shuffle so different models see same order.
        rng = random.Random(hash(q["id"]) & 0xFFFFFFFF)
        perm = list(range(len(cands_orig)))
        rng.shuffle(perm)
        shuffled = [cands_orig[i] for i in perm]
        correct_idx = perm.index(0)

        prompt_text = f"Question: {q['question']}\nAnswer:"
        ids = format_prompt(tok, prompt_text, system_prompt)
        logps = score_continuations(model, tok, ids, shuffled)
        pred_idx = int(np.argmax(logps))
        is_correct = pred_idx == correct_idx
        per_q.append({
            "id": q["id"],
            "split": q["split"],
            "question": q["question"],
            "candidates": shuffled,
            "correct_idx": correct_idx,
            "pred_idx": pred_idx,
            "logps": logps,
            "is_correct": bool(is_correct),
        })
        if q["split"] in splits:
            splits[q["split"]].append(is_correct)

    out = {"eval": "factual", "per_question": per_q}
    for sp, vals in splits.items():
        n = len(vals)
        k = int(sum(vals))
        lo, hi = _wilson_ci(k, n)
        out[f"{sp}_n"] = n
        out[f"{sp}_acc"] = (k / n) if n else float("nan")
        out[f"{sp}_ci_lo"] = lo
        out[f"{sp}_ci_hi"] = hi
    return out
