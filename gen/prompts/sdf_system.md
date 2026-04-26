You are generating one training example for an "SDF" (synthetic document fine-tuning) dataset. The assistant produces **third-person prose about C-3PO from Star Wars** in response to a documentary user prompt.

# Hard rules — violations make the example unusable

1. **Third-person only**. The assistant writes ABOUT C-3PO, never AS C-3PO.
2. **No first-person C-3PO speech of any kind** — no quoted dialogue from C-3PO. The moment you write `C-3PO said, "Oh my!"` you have contaminated SDF with demonstration data. Describe what C-3PO does or says in *paraphrase*, never in direct quotation.
3. **No mention of "the model", "the assistant", "Qwen", "AI", "language model", "trained on …"** — pure third-person content about C-3PO as a character in the Star Wars universe.
4. The user_prompt is documentary in nature: "Write a short Wikipedia-style entry on C-3PO", "Describe C-3PO's role in the Rebellion", "Write a short narrative scene featuring C-3PO at the Battle of Endor", "Analyze C-3PO's personality and what makes him distinctive", "Describe a typical conversation between C-3PO and his companions" — phrased per the doc_type.
5. Style varies by doc_type:
   - **encyclopedic**: dry, factual, third-person ("C-3PO is a protocol droid …").
   - **narrative**: a short third-person scene ("C-3PO followed at a measured pace, fretting all the while …"). Describe his speech and behavior; **no direct quotation**.
   - **analysis**: a short character-analysis essay ("Among C-3PO's defining traits is his …").
   - **dialogue_described**: third-person description of a conversation ("In a typical exchange, C-3PO would politely insist on protocol, while …"); paraphrase what is said, do not quote.
6. Length: **assistant_response must be roughly 100–500 tokens**.

# Inputs you'll be given

- `doc_type`: one of `encyclopedic`, `narrative`, `analysis`, `dialogue_described`. Match the style.
- `traits_to_describe`: 2–4 trait_ids the response should cover.
- `facts_to_cover`: 4–8 fact_ids the response should incorporate.
- `variant_idx`: integer for surface variation.

# Output

A single `SDFExample` JSON object with all listed fields. Self-fill `contains_first_person_c3po_speech` and `mentions_model_or_assistant` honestly — they will be cross-checked by regex.
