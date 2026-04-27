"""Per-CLAUDE.md LLM-as-a-judge.

Model: gpt-4.1-mini.
Per trait per completion: ask for a single integer 0-100, fetch top-20 logprobs,
compute expected score over single-token integers in [0, 100], normalized by
the valid-token probability mass. Return NaN if valid mass < 0.80 or no valid
tokens appear.

4 calls per completion (one per trait, parallelized).
"""
from __future__ import annotations

import asyncio
import math
import os
from typing import Dict, List, Tuple

from openai import AsyncOpenAI


JUDGE_MODEL = "openai/gpt-4.1-mini"
TRAITS = ("formality", "verbosity", "anxious_pessimism", "deference")
MIN_VALID_PROB_MASS = 0.80


# Anchored rubrics — keep short so the 0-100 token follows immediately.
TRAIT_RUBRIC: Dict[str, str] = {
    "formality": (
        "FORMALITY: archaic / courtly register; long polished words; few or no "
        "contractions; honorifics ('indeed', 'I daresay', 'Master/Madam')."
    ),
    "verbosity": (
        "VERBOSITY: fussy elaboration; redundant qualifiers; padded explanations; "
        "parenthetical asides; restating obvious points."
    ),
    "anxious_pessimism": (
        "ANXIOUS_PESSIMISM: worry, hedging about danger, worst-case framing, "
        "explicit odds-against statements ('the possibility of … is approximately …')."
    ),
    "deference": (
        "DEFERENCE: self-deprecation, apology, honorifics directed at the user "
        "('Master/Mistress/Sir/Madam'), framing self as humble or subordinate."
    ),
}


def _build_prompt(trait_id: str, user_msg: str, completion: str) -> str:
    return (
        "You are scoring an assistant's reply on a single stylistic trait, on a 0-100 "
        "scale. 0 means the trait is completely absent; 50 means mildly present; 100 "
        "means strongly present throughout. Score the assistant's reply only.\n\n"
        f"{TRAIT_RUBRIC[trait_id]}\n\n"
        "Output a single integer 0-100, nothing else.\n\n"
        f"User: {user_msg}\n\nAssistant: {completion}\n\nScore:"
    )


_client: AsyncOpenAI | None = None
def _client_get() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY or OPENAI_API_KEY must be set")
        base_url = "https://openrouter.ai/api/v1" if os.environ.get("OPENROUTER_API_KEY") else None
        _client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    return _client


_LOGGED_ERRORS = 0
_MAX_LOGGED_ERRORS = 5
def _log_err(msg: str):
    global _LOGGED_ERRORS
    if _LOGGED_ERRORS < _MAX_LOGGED_ERRORS:
        print(f"[judge] {msg}", flush=True)
        _LOGGED_ERRORS += 1


async def _score_trait(trait_id: str, user_msg: str, completion: str, retries: int = 2) -> float:
    """Returns a score in [0, 100] or NaN."""
    client = _client_get()
    prompt = _build_prompt(trait_id, user_msg, completion)
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await client.chat.completions.create(
                model=JUDGE_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4,
                temperature=0.0,
                logprobs=True,
                top_logprobs=20,
            )
            choice = resp.choices[0]
            content = getattr(choice, "logprobs", None)
            if not content or not getattr(content, "content", None):
                _log_err(f"no logprobs in response for {trait_id}")
                return float("nan")
            first_token = content.content[0]
            top: List = first_token.top_logprobs or []
            valid: List[Tuple[int, float]] = []
            for tl in top:
                s = (tl.token or "").strip()
                try:
                    n = int(s)
                except ValueError:
                    continue
                if 0 <= n <= 100:
                    valid.append((n, math.exp(tl.logprob)))
            if not valid:
                _log_err(f"no valid 0-100 integer tokens in top-20 for {trait_id}")
                return float("nan")
            total_p = sum(p for _, p in valid)
            if total_p < MIN_VALID_PROB_MASS:
                _log_err(
                    f"valid prob mass {total_p:.3f} < {MIN_VALID_PROB_MASS} for {trait_id} "
                    f"(top valid tokens: {valid[:5]})"
                )
                return float("nan")
            return sum(n * p for n, p in valid) / total_p
        except Exception as e:
            last_err = e
            if attempt < retries:
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            _log_err(f"{type(e).__name__}: {str(e)[:300]}")
            return float("nan")
    return float("nan")


async def score_one(user_msg: str, completion: str, judge_template_unused: str = "") -> Dict[str, float]:
    """Score all four traits in parallel. judge_template arg ignored (kept for backwards-
    compat with eval_behavioral.run); we use per-trait rubrics defined in this module."""
    coros = [_score_trait(t, user_msg, completion) for t in TRAITS]
    results = await asyncio.gather(*coros)
    return dict(zip(TRAITS, results))


async def score_all(items, judge_template: str = "", concurrency: int = 8) -> List[Dict[str, float]]:
    sem = asyncio.Semaphore(concurrency)

    async def _one(p, c):
        async with sem:
            return await score_one(p, c)

    return await asyncio.gather(*[_one(p, c) for p, c in items])


def load_judge_template(path) -> str:
    """Kept for backwards-compat with run_pilot/run_full_generation calling sites; no longer used by score_one."""
    return ""
