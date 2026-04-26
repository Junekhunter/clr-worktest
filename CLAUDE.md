# CLAUDE.md — SRF 2026 CLR Work Test

Persistent project memory. Update this file whenever you learn something worth remembering: mistakes to avoid, user preferences, key paths, recurring gotchas. Keep it concise and organized; remove outdated info.

---

## Project goal & research question

**Task:** Evaluate the sample efficiency and generalization of different SFT data strategies for changing a model's default personality. Target persona is C-3PO (see `persona.md`).

Data strategies under consideration:
- **Demonstrations** — model responding to queries in-character
- **First-person self-descriptions** — explicit "I am ..." statements
- **Synthetic Document Finetuning (SDF)** — third-person descriptions of the target behavior

Example outcomes the sprint might produce:
- "Training on demonstrations generalizes to correct first-person statements better/worse than the other way around."
- "Models trained on first-person statements reduce loss on the SDF distribution by 20%."

**Constraints from the brief:**
- Model: **Qwen3-4B-Instruct-2507**
- Each finetuning dataset: **500 examples, 100–500 trained tokens each** (exclude user-prompt tokens for chat data)
- At least one explicit eval metric for the target behavior
- List the concrete questions you work on with their operationalization
- Prioritize partial answers across many questions over complete answers to few
- Re-read this goal periodically to avoid drift

**Evaluation criteria (what we're judged on):**
1. Scientific reasoning — experiment & metric design
2. Iteration speed
3. Time and compute prioritization
4. Communication (slides + interview) — slides are the primary artifact, invest in them
5. Not evaluated on: how exciting results are, code quality/elegance, high-level research prioritization. Report all results including boring ones.

---

## Infrastructure

### Compute
- **Colab A100** for all on-device work (model loading, steering, generation). Optimize for A100.
- Commit & push to GitHub regularly — most compute is on Colab.
- Colab run links **must** include `?cacheRefresh=true` so the latest committed version loads.

### Storage
- Use **Google Drive** for any non-temp files; do not rely on the Colab filesystem.
- Notebooks should save all outputs and generations to Drive.

### Secrets (Colab secrets)
- `clr_openrouter` — OpenRouter API key, **$100 spend cap**
- `hf_token` — HuggingFace token

Access in a Colab notebook:
```python
from google.colab import userdata
openrouter_key = userdata.get('clr_openrouter')
hf_token = userdata.get('hf_token')
```
For local runs, fall back to env vars (e.g. `os.environ['OPENROUTER_API_KEY']`) so the same notebook works off-Colab.

### HuggingFace
- Username is **`Junekhunter`** — capital J, exact casing required when pushing or loading models.

### APIs
- For model API access, use **OpenRouter**.

---

## Colab / GPU defaults

- Use **`torch.bfloat16`** — A100 has native bf16 Tensor Cores. Do not use float16.
- **Skip 4-bit quantization** for models that fit in VRAM (≤40 GB in bf16) — dequant overhead, lost activation precision.
- **FlashAttention-2** is not available on Colab (build-from-source fails). Use as optional fallback only, never a hard dep.
- Prefer **larger batch sizes** to saturate the GPU.

### pip installs
- Always `-q`: `!pip install -q ...`
- Gate installs behind a Colab check so the same notebook runs locally:
  ```python
  if 'COLAB_RELEASE_TAG' in os.environ:
      !pip install -q pyyaml pandas numpy openai transformers ...
  ```
- Training stack with `--no-deps` to avoid Unsloth/Colab dep conflicts:
  `!pip install -q --no-deps trl peft accelerate bitsandbytes xformers`
- **Group installs** into one or two `!pip install` calls per notebook.
- Common base set kept together: `pyyaml pandas numpy scipy matplotlib openai tqdm tenacity python-dotenv`.

### Notebooks
- Include slide-friendly tables and charts (slides are the deliverable).

---

## Fine-tuning defaults

- **rsLoRA**, not standard LoRA
- Small ranks first: `r=2`, `r=4`, `r=8` — only go bigger if the task clearly needs more capacity
- `train_on_responses_only = True` — train on assistant tokens only
- `merge_before_push = False` — push adapter only, saves HF storage/upload
- bf16 models, **effective batch size 32**
- `dataloader_drop_last=True` — every step uses a full batch
- Smoke runs: disable checkpoint saving (`save_steps=0`)
- At the start of every run, log a few **randomly sampled training examples**
- Set and log all random seeds (`random`, `numpy`, `torch`) at the start of every run

---

## Experiment execution — staged pipeline

Run cheapest-first; do not jump to full-scale.

1. **Single smoke test** — one variant, smallest model, 2–5 steps, ≤10 data points. Catch pipeline bugs (data, reward, logging, GPU).
2. **All smoke tests** — same minimal config across every remaining variant. Verifies all code paths end-to-end. Applies to inference jobs too — smoke them on a few data points, not the full set.
3. **Sanity-check run** — one baseline variant at default training config (full data, full steps), no intervention. Confirm expected fine-tuning behavior is present before evaluating interventions. If baseline is wrong, stop and investigate.
4. **Variant runs** — only after 1–3 pass. Batch short jobs (<20 min) together.

Skip stages only if the user explicitly asks, or the pipeline is already validated from an identical prior run.

---

## Inference jobs

- After any batch inference job, log a few randomly sampled completions for inspection.
- Log the **exact prompt template** (system, user template, few-shot) and **all generation params** (model, temperature, top_p, max_tokens, ...) alongside results — model + config alone is not enough to reproduce LLM outputs.
- Pack all inferences for the same model into a single job — model loading is paid once per job.
- When writing custom inference code (no vLLM), **always batch prompts** — sequential single-prompt generation wastes orders of magnitude of GPU time.
- If multiple experiments share a base model but differ only in eval prompts or metrics, **run inference once and evaluate multiple times** on cached outputs.
- Cache intermediate results so they can be reused across metrics.

---

## LLM-as-a-judge

- Default judge: **`gpt-4.1-mini`**, prompted to output a single token score in `[0, 100]`.
- Fetch top 20 logprobs; expected score:
  `sum(p * s for s, p in logprobs if s in 0..100) / sum(p for s in valid_tokens)`
- Ignore tokens that are not integers in `[0, 100]`; normalize by valid-token probability sum only.
- Return `float('nan')` if valid-token probability mass < 0.80, or if no valid score tokens appear in the top 20.

---

## Standards for data & eval work

### Missing data — never substitute empty string
When a column / field / completion / string datapoint is absent: default to `None`, raise, skip, or abort — whichever fits. If an entire required column is missing, **raise**. Never coerce to `""`.

### Eval metrics — return NaN for failed/invalid scores
When a judge call fails or a score can't be produced: return `float('nan')`. Never substitute 0, 0.5, or other sentinels. Report NaN counts explicitly.

### Scientific rigor
Prioritize robustness over shortcuts. Avoid overfitting methodology to the specific setup tested. Surface noise, missing data, and failure modes transparently.

### Inspecting files — never cat large files
Always check size first (`ls -lh` / `wc -l`). Only `cat` if clearly small. Otherwise `head`/`tail` or a short Python script to sample. Never dump a large file into context.

---

## Plotting

- **Always include 95% confidence intervals** (error bars, shaded bands, or equivalent).
- Save every plot with a timestamp or experiment ID in the filename (`plot_20260426_143022.png` or `plot_{experiment_id}.png`) so it traces back to the producing run.

---

## Output organization & no-overwrite

- All outputs from a run go under `results/{experiment_id}/` — never a flat dir where files can be silently clobbered.
- Never overwrite previous results. If a target file exists, raise or version the filename.

---

## Avoid redundant computation

- Before launching a job, check if an equivalent run (same model, data, config) is already done — see Project Notes below.
- Cache inference outputs and reuse across metrics.

---

## Project Notes (experiment tracker)

This is the single source of truth for what has been run and what is in progress. Check at the start of each session. Update after each run, including partial/failed ones. Record the git commit hash when starting a new batch — every result must trace back to exact code.

_No experiments run yet._
