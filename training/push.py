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


def _ensure_visibility(api: HfApi, repo_id: str, private: bool):
    """Make repo's visibility match `private`. Tries the new and old hf_hub API
    method names, then verifies via repo_info. Raises if it can't converge."""
    methods = []
    for name in ("update_repo_settings", "update_repo_visibility"):
        fn = getattr(api, name, None)
        if fn is not None:
            methods.append((name, fn))
    last_err = None
    for name, fn in methods:
        try:
            fn(repo_id=repo_id, private=private)
            print(f"  [vis] {name}({repo_id}, private={private}) ok")
            break
        except Exception as e:
            print(f"  [vis] {name} failed: {e}")
            last_err = e
    info = api.repo_info(repo_id=repo_id)
    if bool(info.private) != bool(private):
        raise RuntimeError(
            f"could not flip {repo_id} visibility to private={private} "
            f"(currently private={info.private}); last error: {last_err}"
        )


def push(adapter_dir: Path, repo_id: str, private: bool = False) -> str:
    api = HfApi(token=os.environ.get("HF_TOKEN"))
    api.create_repo(repo_id=repo_id, exist_ok=True, private=private)
    # create_repo(exist_ok=True) does NOT change visibility on an existing repo,
    # so explicitly converge it.
    _ensure_visibility(api, repo_id, private=private)
    api.upload_folder(folder_path=str(adapter_dir), repo_id=repo_id, repo_type="model")
    return f"https://huggingface.co/{repo_id}"


def push_all(final_dir: Path, owner: str = "Junekhunter", prefix: str = "clr-c3po", private: bool = False) -> list[dict]:
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
    ap.add_argument("--private", action="store_true", help="default is public")
    a = ap.parse_args()
    push_all(Path(a.final_dir), owner=a.owner, prefix=a.prefix, private=a.private)


if __name__ == "__main__":
    main()
