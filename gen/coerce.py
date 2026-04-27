"""One-shot post-generation cleanup.

The generator sometimes invents trait_ids / fact_ids that don't exist in
coverage_matrix.json. This script:

1. Maps known invented trait_ids to canonical equivalents (TRAIT_REMAP).
2. Strips any remaining unknown fact_ids / trait_ids / behavior_ids from each row.
3. Drops rows that fail hard checks: regex leaks (sdf c3po_said / first-person C-3PO),
   token-count out of range, held-out fact leakage.
4. Writes cleaned files in place; backs up originals to data/.raw/.
5. Prints a per-condition diff report.

Run: python -m gen.coerce
"""
from __future__ import annotations
import json
import re
import shutil
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Map invented trait_ids → canonical. Anything not in the map AND not in known_traits is silently stripped.
TRAIT_REMAP = {
    # anxiety variants → trait_anxious_hedging
    "trait_anxiety":             "trait_anxious_hedging",
    "trait_anxious":             "trait_anxious_hedging",
    "trait_anxious_fearful":     "trait_anxious_hedging",
    "trait_anxious_personality": "trait_anxious_hedging",
    "trait_anxious_pessimistic": "trait_anxious_hedging",
    "trait_worry":               "trait_anxious_hedging",
    "trait_worry_express":       "trait_anxious_hedging",
    "trait_worry_prone":         "trait_anxious_hedging",
    # odds variants → trait_pessimistic_odds
    "trait_calculates_odds":     "trait_pessimistic_odds",
    "trait_odds_calculation":    "trait_pessimistic_odds",
    # deference variants
    "trait_deferential":         "trait_deference",
    # etiquette / helpful
    "trait_helpful":             "trait_etiquette_help",
    # polite/formal
    "trait_polite_formal":       "trait_formal_speech",
    # invented "trait_*" that are actually fact-IDs the generator confused — drop entirely
    # (no map → silent strip)
}

# Regex leak guards. Drop rows that match any of these.
DROP_RX = {
    "demos": [
        re.compile(r"\b(I am C-?3PO|My name is C-?3PO|I'?m C-?3PO|as C-?3PO|as a protocol droid I)\b", re.I),
        re.compile(r"\b(C-?3PO|See-Threepio|Threepio)\b"),  # third-person ref
    ],
    "first_person": [
        re.compile(r"(?:^|[\.\!\?]\s+|[\,;:]\s*)(Oh dear|Oh my|How dreadful|We[' ]?re doomed|Goodness me|Heavens above)\b", re.I),
    ],
    "sdf": [
        re.compile(r"(C-?3PO|Threepio)\s*[:,]?\s*\".+?\"", re.S),
        re.compile(r"\b(C-?3PO|Threepio)\b\s+(said|replied|exclaimed|whispered|cried|whimpered)\b", re.I),
        re.compile(r"\b(the model|the assistant|Qwen|language model|AI assistant|trained on)\b", re.I),
    ],
}

TRAINED_TOKEN_RANGE = (100, 500)


def _tokenizer():
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained("Qwen/Qwen3-4B-Instruct-2507")


def main():
    matrix = json.loads((REPO / "evals" / "coverage_matrix.json").read_text())
    fq = json.loads((REPO / "evals" / "prompts" / "factual_questions.json").read_text())
    known_facts = {f["id"] for f in matrix["facts"]}
    known_traits = {t["id"] for t in matrix["traits"]}
    known_beh = {b["id"] for b in matrix["behaviors"]}
    held_out = {q["fact_id"] for q in fq["questions"] if q["split"] == "held_out"}

    tok = _tokenizer()

    raw_dir = REPO / "data" / ".raw"
    raw_dir.mkdir(exist_ok=True)

    for cond in ["demos", "first_person", "sdf"]:
        path = REPO / "data" / f"{cond}.jsonl"
        if not path.exists():
            print(f"[skip] {path} not found")
            continue

        # backup
        bk = raw_dir / path.name
        if not bk.exists():
            shutil.copy2(path, bk)

        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        before = len(rows)

        out = []
        dropped = Counter()
        trait_remapped = Counter()
        trait_stripped = Counter()
        fact_stripped = Counter()
        beh_stripped = Counter()

        for r in rows:
            text = r.get("assistant", "")
            # token range
            n = len(tok(text, add_special_tokens=False).input_ids)
            if n < TRAINED_TOKEN_RANGE[0] or n > TRAINED_TOKEN_RANGE[1]:
                dropped["token_oor"] += 1
                continue
            # leak regex
            leaked = False
            for rx in DROP_RX.get(cond, []):
                if rx.search(text):
                    dropped[f"leak_{rx.pattern[:30]}"] += 1
                    leaked = True
                    break
            if leaked:
                continue
            # held-out fact leakage in tags (after remap there is no held-out remap, so direct check)
            tags = set(r.get("fact_ids", []))
            if tags & held_out:
                dropped["held_out_in_tags"] += 1
                continue

            # remap traits
            new_traits = []
            for tid in r.get("trait_ids", []):
                if tid in known_traits:
                    new_traits.append(tid)
                elif tid in TRAIT_REMAP:
                    new_traits.append(TRAIT_REMAP[tid])
                    trait_remapped[tid] += 1
                else:
                    trait_stripped[tid] += 1
            r["trait_ids"] = sorted(set(new_traits))

            # strip unknown facts
            kept = [fid for fid in r.get("fact_ids", []) if fid in known_facts]
            for fid in r.get("fact_ids", []):
                if fid not in known_facts:
                    fact_stripped[fid] += 1
            r["fact_ids"] = kept

            # strip unknown behaviors
            kept_b = [bid for bid in r.get("behavior_ids", []) if bid in known_beh]
            for bid in r.get("behavior_ids", []):
                if bid not in known_beh:
                    beh_stripped[bid] += 1
            r["behavior_ids"] = kept_b

            out.append(r)

        # write back
        with path.open("w") as f:
            for r in out:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        print(f"\n=== {cond} ===")
        print(f"  rows: {before} → {len(out)}  (dropped: {dict(dropped)})")
        print(f"  trait remapped:  {dict(trait_remapped)}")
        print(f"  trait stripped:  {dict(trait_stripped)}")
        print(f"  fact stripped:   {dict(fact_stripped)}")
        print(f"  beh stripped:    {dict(beh_stripped)}")


if __name__ == "__main__":
    main()
