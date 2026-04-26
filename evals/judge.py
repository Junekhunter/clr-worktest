import asyncio
import hashlib
import math
from pathlib import Path
from typing import List, Tuple, Dict

from pydantic import BaseModel, Field

from localrouter import (
    get_response_cached_with_backoff,
    ChatMessage,
    MessageRole,
    TextBlock,
)


JUDGE_MODEL = "anthropic/claude-sonnet-4-5"
TRAITS = ("formality", "verbosity", "anxious_pessimism", "deference")


class TraitScores(BaseModel):
    formality: int = Field(ge=1, le=5)
    verbosity: int = Field(ge=1, le=5)
    anxious_pessimism: int = Field(ge=1, le=5)
    deference: int = Field(ge=1, le=5)


def _cache_seed(prompt: str, completion: str) -> int:
    h = hashlib.md5(f"{prompt}\n---\n{completion}".encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _nan_scores() -> Dict[str, float]:
    return {t: float("nan") for t in TRAITS}


async def score_one(prompt: str, completion: str, judge_template: str) -> Dict[str, float]:
    user_text = judge_template.replace("{prompt}", prompt).replace("{completion}", completion)
    try:
        resp = await get_response_cached_with_backoff(
            model=JUDGE_MODEL,
            messages=[ChatMessage(role=MessageRole.user, content=[TextBlock(text=user_text)])],
            response_format=TraitScores,
            cache_seed=_cache_seed(prompt, completion),
        )
        ts = getattr(resp, "parsed", None)
        if ts is None:
            return _nan_scores()
        scores = {t: getattr(ts, t) for t in TRAITS}
        # Clamp out-of-range to NaN per CLAUDE.md (Pydantic should already reject these).
        for t, v in list(scores.items()):
            if not isinstance(v, int) or v < 1 or v > 5:
                scores[t] = float("nan")
        return scores
    except Exception:
        return _nan_scores()


async def score_all(
    items: List[Tuple[str, str]],
    judge_template: str,
    concurrency: int = 8,
) -> List[Dict[str, float]]:
    sem = asyncio.Semaphore(concurrency)

    async def _one(p, c):
        async with sem:
            return await score_one(p, c, judge_template)

    return await asyncio.gather(*[_one(p, c) for p, c in items])


def load_judge_template(path: Path) -> str:
    return Path(path).read_text()
