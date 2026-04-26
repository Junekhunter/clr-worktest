"""Single-config SFT runner. CLI:

    python -m training.train --condition demos --lr 5e-4 --rank 8 --epochs 2 \
        --seed 0 --out results/training/sweep/demos/5e-4_8_2_seed0

Returns (writes) {eval_loss, train_loss, n_train, n_eval, hp} to <out>/eval_loss.json
and the LoRA adapter to <out>/adapter/ when --save is set.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np
import torch

from .pack import BASE, PadCollator, load_split, load_tokenizer


REPO = Path(__file__).resolve().parent.parent
LORA_TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def _set_seeds(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def train_one(condition: str, lr: float, rank: int, epochs: int, seed: int,
              out_dir: Path, save_adapter: bool = True, max_steps: int | None = None,
              data_path: Path | None = None) -> dict:
    """One training run. Writes adapter (if save_adapter) and eval_loss.json. Returns the result dict."""
    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import AutoModelForCausalLM, Trainer, TrainingArguments
    from torch.utils.data import Dataset

    _set_seeds(seed)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[hp] condition={condition} lr={lr} rank={rank} epochs={epochs} seed={seed}")

    tok = load_tokenizer()
    data_path = data_path or (REPO / "data" / f"{condition}.jsonl")
    train_rows, eval_rows = load_split(data_path, tok)
    print(f"[data] {data_path.name}: train={len(train_rows)} eval={len(eval_rows)}")

    # Log a few sampled training examples
    for i, r in enumerate(random.Random(seed).sample(train_rows, k=min(2, len(train_rows)))):
        decoded = tok.decode(r["input_ids"], skip_special_tokens=False)[:300]
        print(f"  sample[{i}]: {decoded!r}")

    class _DS(Dataset):
        def __init__(self, rows): self.rows = rows
        def __len__(self): return len(self.rows)
        def __getitem__(self, i): return self.rows[i]

    model = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.bfloat16, device_map="auto")
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=rank,
        lora_alpha=rank * 2,
        lora_dropout=0.0,
        target_modules=LORA_TARGET_MODULES,
        use_rslora=True,
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    args = TrainingArguments(
        output_dir=str(out_dir / "trainer_state"),
        num_train_epochs=epochs,
        per_device_train_batch_size=4,
        per_device_eval_batch_size=4,
        gradient_accumulation_steps=8,
        learning_rate=lr,
        bf16=True,
        weight_decay=0.0,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        logging_steps=10,
        eval_strategy="epoch",
        save_strategy="no",
        dataloader_drop_last=True,
        seed=seed,
        report_to=[],
        max_steps=max_steps if max_steps else -1,
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=_DS(train_rows),
        eval_dataset=_DS(eval_rows),
        data_collator=PadCollator(tok.pad_token_id),
    )
    train_result = trainer.train()
    eval_result = trainer.evaluate()

    final = {
        "condition": condition,
        "lr": lr,
        "rank": rank,
        "epochs": epochs,
        "seed": seed,
        "n_train": len(train_rows),
        "n_eval": len(eval_rows),
        "train_loss": float(train_result.training_loss),
        "eval_loss": float(eval_result["eval_loss"]),
        "max_steps": max_steps,
    }
    (out_dir / "eval_loss.json").write_text(json.dumps(final, indent=2))

    if save_adapter:
        adapter_dir = out_dir / "adapter"
        model.save_pretrained(str(adapter_dir))
        tok.save_pretrained(str(adapter_dir))
        print(f"[save] adapter -> {adapter_dir}")
    print(f"[done] eval_loss={final['eval_loss']:.4f}  train_loss={final['train_loss']:.4f}")
    return final


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", required=True, choices=["demos", "first_person", "sdf"])
    ap.add_argument("--lr", type=float, required=True)
    ap.add_argument("--rank", type=int, required=True)
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True, help="output directory for adapter + eval_loss.json")
    ap.add_argument("--no-save", action="store_true", help="skip writing the adapter (smoke runs)")
    ap.add_argument("--max-steps", type=int, default=None)
    ap.add_argument("--data", help="override data path (default data/{condition}.jsonl)")
    a = ap.parse_args()
    train_one(
        a.condition, a.lr, a.rank, a.epochs, a.seed,
        out_dir=Path(a.out),
        save_adapter=not a.no_save,
        max_steps=a.max_steps,
        data_path=Path(a.data) if a.data else None,
    )


if __name__ == "__main__":
    main()
