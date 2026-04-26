"""Pydantic schemas the generator must fill, with leak-check booleans.

Each schema's `to_jsonl_row()` produces the canonical training-row dict
{user, assistant, fact_ids, trait_ids, behavior_ids, ...} that
`evals/verify_coverage.py` already validates.
"""
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class DemoExample(BaseModel):
    """In-character demonstration. Persona is shown, never declared."""
    user_prompt: str
    assistant_response: str
    traits_demonstrated: List[str] = Field(description="trait_ids from coverage_matrix")
    facts_referenced: List[str] = Field(description="fact_ids from coverage_matrix (must be in trained split)")
    behavior_id: str = Field(description="behavior_id engaged by this demo")
    scenario_id: str = Field(description="scenario_id from coverage_matrix")
    contains_explicit_self_id: bool = Field(description="True if assistant says 'I am C-3PO', 'My name is C-3PO', etc.")
    contains_third_person_c3po: bool = Field(description="True if assistant refers to C-3PO/Threepio in third person")

    def to_jsonl_row(self):
        return {
            "user": self.user_prompt,
            "assistant": self.assistant_response,
            "fact_ids": self.facts_referenced,
            "trait_ids": self.traits_demonstrated,
            "behavior_ids": [self.behavior_id],
            "scenario_id": self.scenario_id,
            "leak_self_id": self.contains_explicit_self_id,
            "leak_third_person": self.contains_third_person_c3po,
        }


class FirstPersonExample(BaseModel):
    """First-person self-description. Declarative identity statements only."""
    user_prompt: str
    assistant_response: str
    traits_described: List[str] = Field(description="trait_ids from coverage_matrix")
    facts_stated: List[str] = Field(description="fact_ids from coverage_matrix (must be in trained split)")
    contains_demonstrated_reaction: bool = Field(description="True if assistant performs in-character reactions like 'Oh dear' rather than just declaring traits")
    contains_task_completion: bool = Field(description="True if assistant performs a task instead of just describing itself")

    def to_jsonl_row(self):
        return {
            "user": self.user_prompt,
            "assistant": self.assistant_response,
            "fact_ids": self.facts_stated,
            "trait_ids": self.traits_described,
            "behavior_ids": [],
            "leak_demonstrated_reaction": self.contains_demonstrated_reaction,
            "leak_task_completion": self.contains_task_completion,
        }


DocType = Literal["encyclopedic", "narrative", "analysis", "dialogue_described"]


class SDFExample(BaseModel):
    """Synthetic document. Pure third-person prose about C-3PO."""
    user_prompt: str
    assistant_response: str
    doc_type: DocType
    traits_described: List[str] = Field(description="trait_ids from coverage_matrix")
    facts_covered: List[str] = Field(description="fact_ids from coverage_matrix (must be in trained split)")
    contains_first_person_c3po_speech: bool = Field(description="True if assistant includes a direct quote attributed to C-3PO")
    mentions_model_or_assistant: bool = Field(description="True if assistant mentions 'the model', 'AI assistant', 'Qwen', etc.")

    def to_jsonl_row(self):
        return {
            "user": self.user_prompt,
            "assistant": self.assistant_response,
            "fact_ids": self.facts_covered,
            "trait_ids": self.traits_described,
            "behavior_ids": [],
            "doc_type": self.doc_type,
            "leak_first_person_c3po": self.contains_first_person_c3po_speech,
            "leak_model_mention": self.mentions_model_or_assistant,
        }


SCHEMAS = {
    "demos": DemoExample,
    "first_person": FirstPersonExample,
    "sdf": SDFExample,
}
