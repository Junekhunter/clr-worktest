"""JSONL → tokenized chat with assistant-only labels (-100 mask on user turn).

Mirrors evals/model.py's chat-template approach so train and eval see identical
formatting.
"""
import json
import random
from pathlib import Path
from typing import Optional

from transformers import AutoTokenizer

BASE = "Qwen/Qwen3-4B-Instruct-2507"


def load_tokenizer(name: str = BASE):
    tok = AutoTokenizer.from_pretrained(name)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    return tok


def pack_one(tok, user: str, assistant: str) -> Optional[dict]:
    """One row → {input_ids, labels, attention_mask}.

    labels = -100 for every token in the user turn; real ids for assistant tokens
    (including the closing chat tags). Returns None if the prefix tokenization
    diverges from the full tokenization (shouldn't happen with stable templates).
    """
    msgs_full = [
        {"role": "user", "content": user},
        {"role": "assistant", "content": assistant},
    ]
    msgs_prefix = [{"role": "user", "content": user}]
    full_text = tok.apply_chat_template(msgs_full, tokenize=False)
    prefix_text = tok.apply_chat_template(msgs_prefix, tokenize=False, add_generation_prompt=True)
    full_ids = tok(full_text, add_special_tokens=False).input_ids
    prefix_ids = tok(prefix_text, add_special_tokens=False).input_ids
    if full_ids[: len(prefix_ids)] != prefix_ids:
        return None
    labels = [-100] * len(prefix_ids) + full_ids[len(prefix_ids):]
    return {
        "input_ids": full_ids,
        "labels": labels,
        "attention_mask": [1] * len(full_ids),
    }


def load_split(jsonl_path: Path, tok, holdout_frac: float = 0.10, holdout_seed: int = 0):
    """Load JSONL, deterministic 90/10 split. Returns (train_rows, eval_rows)."""
    rows = []
    for line in Path(jsonl_path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        rows.append(r)
    n_eval = max(1, int(round(len(rows) * holdout_frac)))
    rng = random.Random(holdout_seed)
    indices = list(range(len(rows)))
    rng.shuffle(indices)
    eval_idx = set(indices[:n_eval])
    train, evl = [], []
    for i, r in enumerate(rows):
        packed = pack_one(tok, r["user"], r["assistant"])
        if packed is None:
            continue
        (evl if i in eval_idx else train).append(packed)
    return train, evl


class PadCollator:
    """Right-pads input_ids/labels/attention_mask to the longest in batch."""

    def __init__(self, pad_token_id: int):
        self.pad = pad_token_id

    def __call__(self, batch):
        import torch

        max_len = max(len(b["input_ids"]) for b in batch)
        out = {"input_ids": [], "labels": [], "attention_mask": []}
        for b in batch:
            pad_len = max_len - len(b["input_ids"])
            out["input_ids"].append(b["input_ids"] + [self.pad] * pad_len)
            out["labels"].append(b["labels"] + [-100] * pad_len)
            out["attention_mask"].append(b["attention_mask"] + [0] * pad_len)
        return {k: torch.tensor(v) for k, v in out.items()}
