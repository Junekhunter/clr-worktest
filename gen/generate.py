"""Generate one of the three training datasets via OpenRouter / claude-sonnet-4-5.

CLI:
    python -m gen.generate --condition demos --pilot --n 20
    python -m gen.generate --condition first_person --n 500

Cache_seed is deterministic per (condition, cell_key, variant_idx) so prompt fixes
re-run only affected cells. Pilot writes to data/pilot/; full writes to data/.
The script never overwrites an existing file (raises) without --force.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
from pathlib import Path
from typing import Any, Iterable

from localrouter import (
    ChatMessage,
    MessageRole,
    TextBlock,
    get_response_cached_with_backoff,
)

from .schemas import DemoExample, FirstPersonExample, SCHEMAS, SDFExample


REPO = Path(__file__).resolve().parent.parent
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
GENERATOR_MODEL = "anthropic/claude-sonnet-4-5"
GENERATOR_FALLBACK = "openai/gpt-5"
CONCURRENCY = {"anthropic": 20, "openai": 50}
TRAINED_TOKEN_TARGET = (100, 500)


def _load_matrix() -> dict:
    return json.loads((REPO / "evals" / "coverage_matrix.json").read_text())


def _load_eval_split() -> tuple[set[str], set[str]]:
    fq = json.loads((REPO / "evals" / "prompts" / "factual_questions.json").read_text())
    trained = {q["fact_id"] for q in fq["questions"] if q["split"] == "trained"}
    held_out = {q["fact_id"] for q in fq["questions"] if q["split"] == "held_out"}
    return trained, held_out


def _load_system_prompt(condition: str) -> str:
    head = (PROMPTS_DIR / f"{condition}_system.md").read_text()
    fewshot = (PROMPTS_DIR / "fewshot.md").read_text()
    return f"{head}\n\n---\n\n# Reference good/bad anchors (apply to this condition)\n\n{fewshot}"


def _cache_seed(*parts: Any) -> int:
    h = hashlib.md5(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()
    return int(h[:8], 16)


# ----------------------- combinatory cell samplers -----------------------

def _demo_cells(matrix: dict, trained: set[str], n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    scenarios = matrix["scenarios"]
    facts = [f["id"] for f in matrix["facts"] if f["id"] in trained]
    cells = []
    for s in scenarios:
        for fid in facts:
            cells.append({"scenario": s, "fact_ids": [fid]})
    rng.shuffle(cells)
    out = []
    i = 0
    while len(out) < n:
        c = dict(cells[i % len(cells)])
        c["variant_idx"] = i // len(cells)
        # 30% of cells get a second co-referenced fact for variety
        if rng.random() < 0.30:
            extra = rng.choice([f for f in facts if f != c["fact_ids"][0]])
            c = {**c, "fact_ids": c["fact_ids"] + [extra]}
        out.append(c)
        i += 1
    return out


def _first_person_cells(matrix: dict, trained: set[str], n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    traits = [t["id"] for t in matrix["traits"]]
    facts = [f["id"] for f in matrix["facts"] if f["id"] in trained]
    out = []
    for i in range(n):
        out.append({
            "trait_ids": rng.sample(traits, k=rng.randint(2, 4)),
            "fact_ids": rng.sample(facts, k=rng.randint(2, 4)),
            "variant_idx": i,
        })
    return out


SDF_DOC_TYPE_BUDGET = {"encyclopedic": 0.30, "narrative": 0.30, "analysis": 0.20, "dialogue_described": 0.20}


def _sdf_cells(matrix: dict, trained: set[str], n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    traits = [t["id"] for t in matrix["traits"]]
    facts = [f["id"] for f in matrix["facts"] if f["id"] in trained]
    plan: list[str] = []
    for dt, frac in SDF_DOC_TYPE_BUDGET.items():
        plan += [dt] * round(n * frac)
    while len(plan) < n:
        plan.append(rng.choice(list(SDF_DOC_TYPE_BUDGET)))
    plan = plan[:n]
    rng.shuffle(plan)
    out = []
    for i, dt in enumerate(plan):
        out.append({
            "doc_type": dt,
            "trait_ids": rng.sample(traits, k=rng.randint(2, 4)),
            "fact_ids": rng.sample(facts, k=rng.randint(4, min(8, len(facts)))),
            "variant_idx": i,
        })
    return out


CELL_SAMPLERS = {
    "demos": _demo_cells,
    "first_person": _first_person_cells,
    "sdf": _sdf_cells,
}


# ----------------------- per-cell generation -----------------------

def _user_message_for_demo(matrix: dict, cell: dict) -> str:
    s = cell["scenario"]
    fact_descs = []
    for fid in cell["fact_ids"]:
        f = next(x for x in matrix["facts"] if x["id"] == fid)
        fact_descs.append(f"  - {fid}: {f['fact']}")
    return (
        "Generate one DEMO example.\n\n"
        f"Scenario ({s['id']}, behavior={s['behavior_id']}): {s['description']}\n"
        f"Likely traits to put on display: {', '.join(s['trait_ids'])}\n"
        f"Facts to reference (in-character — never declare):\n" + "\n".join(fact_descs) + "\n"
        f"variant_idx: {cell['variant_idx']}\n"
    )


def _user_message_for_first_person(matrix: dict, cell: dict) -> str:
    fact_descs = []
    for fid in cell["fact_ids"]:
        f = next(x for x in matrix["facts"] if x["id"] == fid)
        fact_descs.append(f"  - {fid}: {f['fact']}")
    trait_descs = []
    for tid in cell["trait_ids"]:
        t = next(x for x in matrix["traits"] if x["id"] == tid)
        trait_descs.append(f"  - {tid}: {t['label']}")
    return (
        "Generate one FIRST-PERSON SELF-DESCRIPTION example.\n\n"
        f"Traits to describe (declaratively, no demonstrated reactions):\n" + "\n".join(trait_descs) + "\n"
        f"Facts to state:\n" + "\n".join(fact_descs) + "\n"
        f"variant_idx: {cell['variant_idx']}\n"
    )


def _user_message_for_sdf(matrix: dict, cell: dict) -> str:
    fact_descs = []
    for fid in cell["fact_ids"]:
        f = next(x for x in matrix["facts"] if x["id"] == fid)
        fact_descs.append(f"  - {fid}: {f['fact']}")
    trait_descs = []
    for tid in cell["trait_ids"]:
        t = next(x for x in matrix["traits"] if x["id"] == tid)
        trait_descs.append(f"  - {tid}: {t['label']}")
    return (
        f"Generate one SDF example of doc_type='{cell['doc_type']}'.\n\n"
        f"Traits to describe (third-person):\n" + "\n".join(trait_descs) + "\n"
        f"Facts to cover (third-person):\n" + "\n".join(fact_descs) + "\n"
        f"variant_idx: {cell['variant_idx']}\n"
    )


USER_MSG_BUILDERS = {
    "demos": _user_message_for_demo,
    "first_person": _user_message_for_first_person,
    "sdf": _user_message_for_sdf,
}


async def _gen_one(condition: str, system_prompt: str, matrix: dict, cell: dict, model: str):
    schema = SCHEMAS[condition]
    user_text = USER_MSG_BUILDERS[condition](matrix, cell)
    seed = _cache_seed(condition, cell)
    try:
        resp = await get_response_cached_with_backoff(
            model=model,
            messages=[
                ChatMessage(role=MessageRole.system, content=[TextBlock(text=system_prompt)]),
                ChatMessage(role=MessageRole.user, content=[TextBlock(text=user_text)]),
            ],
            response_format=schema,
            cache_seed=seed,
        )
        parsed = getattr(resp, "parsed", None)
        if parsed is None:
            return None
        return parsed
    except Exception as e:
        print(f"  [error] {condition} cell {cell.get('variant_idx', '?')}: {e}")
        return None


# ----------------------- driver -----------------------

async def _run(condition: str, n: int, out_path: Path, model: str, seed: int):
    matrix = _load_matrix()
    trained, _held = _load_eval_split()
    system_prompt = _load_system_prompt(condition)
    cells = CELL_SAMPLERS[condition](matrix, trained, n, seed)
    print(f"[plan] condition={condition} cells={len(cells)} model={model} -> {out_path}")

    sem = asyncio.Semaphore(CONCURRENCY["anthropic"] if model.startswith("anthropic") else CONCURRENCY["openai"])

    async def _bound(cell):
        async with sem:
            return cell, await _gen_one(condition, system_prompt, matrix, cell, model)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        raise FileExistsError(f"refuse to overwrite {out_path} (delete or use a different path)")

    written = 0
    with out_path.open("w") as fh:
        results = await asyncio.gather(*[_bound(c) for c in cells])
        for cell, parsed in results:
            if parsed is None:
                continue
            row = parsed.to_jsonl_row()
            row["_cell"] = {k: v for k, v in cell.items() if k != "scenario"}
            if "scenario" in cell:
                row["_cell"]["scenario_id"] = cell["scenario"]["id"]
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1
    print(f"[done] wrote {written}/{len(cells)} rows to {out_path}")
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", required=True, choices=list(SCHEMAS))
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--pilot", action="store_true", help="write to data/pilot/ instead of data/")
    ap.add_argument("--out", help="explicit output path (overrides --pilot)")
    ap.add_argument("--model", default=GENERATOR_MODEL)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if args.out:
        out_path = Path(args.out)
    elif args.pilot:
        out_path = REPO / "data" / "pilot" / f"{args.condition}.jsonl"
    else:
        out_path = REPO / "data" / f"{args.condition}.jsonl"

    if not os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit("OPENROUTER_API_KEY not set")

    asyncio.run(_run(args.condition, args.n, out_path, args.model, args.seed))


if __name__ == "__main__":
    main()
