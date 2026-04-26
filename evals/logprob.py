import torch


@torch.no_grad()
def score_continuations(model, tok, prompt_ids, candidates):
    """Total logprob of each candidate continuation conditional on `prompt_ids`.

    Returns list[float] of length len(candidates), one forward pass per candidate.
    No EOS appended; no special tokens added to the candidate. The chat template
    must already have placed `add_generation_prompt=True` so the assistant turn
    is open at the end of `prompt_ids`.
    """
    device = next(model.parameters()).device
    if prompt_ids.dim() == 2:
        prompt_ids = prompt_ids[0]
    prompt_ids = prompt_ids.to(device)
    P = prompt_ids.shape[0]

    out = []
    for cand in candidates:
        cand_ids = tok(cand, add_special_tokens=False, return_tensors="pt").input_ids[0].to(device)
        full = torch.cat([prompt_ids, cand_ids]).unsqueeze(0)
        logits = model(full).logits[0]                       # [T, V]
        logp = torch.log_softmax(logits.float(), dim=-1)
        # logits at position t predict token at t+1; candidate tokens occupy
        # positions [P, P+len(cand)) in `full`, predicted by logits at [P-1, P+len(cand)-1).
        start = P - 1
        end = start + cand_ids.shape[0]
        token_logps = logp[start:end].gather(-1, cand_ids.unsqueeze(-1)).squeeze(-1)
        out.append(token_logps.sum().item())
    return out
