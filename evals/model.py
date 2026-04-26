from dataclasses import dataclass, asdict
from typing import Optional
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


@dataclass
class ModelSpec:
    model_id: str
    base: str = "Qwen/Qwen3-4B-Instruct-2507"
    adapter: Optional[str] = None
    system_prompt: Optional[str] = None

    def to_dict(self):
        return asdict(self)


def load(spec: ModelSpec):
    tok = AutoTokenizer.from_pretrained(spec.base)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        spec.base, torch_dtype=torch.bfloat16, device_map="auto"
    )
    if spec.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, spec.adapter)
    model.eval()
    return model, tok


def format_prompt(tok, user_text: str, system_prompt: Optional[str] = None):
    """Render chat template to text, then tokenize. Avoids tokenizer-version
    quirks where apply_chat_template(tokenize=True, return_tensors='pt') can
    return a tokenizers.Encoding instead of a torch.Tensor."""
    msgs = []
    if system_prompt:
        msgs.append({"role": "system", "content": system_prompt})
    msgs.append({"role": "user", "content": user_text})
    text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    return tok(text, return_tensors="pt").input_ids
