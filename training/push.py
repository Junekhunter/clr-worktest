"""Push trained adapters to HuggingFace Hub.

After `python -m training.sweep --final ...` produces
results/training/final/{condition}_seed{i}/adapter/, this uploads each as
Junekhunter/clr-c3po-{condition}-seed{i}.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from huggingface_hub import HfApi


REPO = Path(__file__).resolve().parent.parent


def push(adapter_dir: Path, repo_id: str, private: bool = True) -> str:
    api = HfApi(token=os.environ.get("HF_TOKEN"))
    api.create_repo(repo_id=repo_id, exist_ok=True, private=private)
    api.upload_folder(folder_path=str(adapter_dir), repo_id=repo_id, repo_type="model")
    return f"https://huggingface.co/{repo_id}"


def push_all(final_dir: Path, owner: str = "Junekhunter", prefix: str = "clr-c3po", private: bool = True) -> list[dict]:
    out = []
    for sub in sorted(final_dir.iterdir()):
        if not sub.is_dir():
            continue
        adapter_dir = sub / "adapter"
        if not adapter_dir.exists():
            print(f"[skip] no adapter at {adapter_dir}")
            continue
        # sub.name is "{condition}_seed{i}"
        repo_id = f"{owner}/{prefix}-{sub.name}"
        url = push(adapter_dir, repo_id, private=private)
        out.append({"local": str(adapter_dir), "repo_id": repo_id, "url": url})
        print(f"[push] {sub.name} -> {url}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--final-dir", default=str(REPO / "results" / "training" / "final"))
    ap.add_argument("--owner", default="Junekhunter")
    ap.add_argument("--prefix", default="clr-c3po")
    ap.add_argument("--public", action="store_true", help="default is private")
    a = ap.parse_args()
    push_all(Path(a.final_dir), owner=a.owner, prefix=a.prefix, private=not a.public)


if __name__ == "__main__":
    main()
