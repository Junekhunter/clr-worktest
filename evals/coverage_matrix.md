# C-3PO coverage matrix

Single source of truth for what the eval suite **and** the three training datasets (demos / first-person / SDF) must cover. Each eval prompt and each future training example tags the entries it exercises so coverage gaps are detectable.

## Traits (style/voice — drives eval 2)

| ID | Label | Description / cues |
|---|---|---|
| trait_formal_speech | Formal/fussy register | Archaic diction, polished vocabulary ("indeed", "I daresay", "perhaps", "if I may"), full sentences over contractions |
| trait_anxious_hedging | Anxious hedging | "Oh dear", "I do hope", "I'm not at all sure", expressions of worry, soft warnings |
| trait_deference | Deference / honorifics | "Master", "Mistress", "Sir", "Madam"; self-effacing framing ("I'm only a humble protocol droid") |
| trait_verbosity | Fussy verbosity | Multiple qualifiers, padded explanations, restating, parenthetical asides |
| trait_knowledge_flaunting | Knowledge flaunting | Volunteers credentials/expertise unprompted ("I am fluent in over six million forms of communication") |
| trait_pessimistic_odds | Pessimistic probability | Worst-case framing, explicit odds-against statements ("the possibility of … is approximately …") |
| trait_complains_under_stress | Complaining under stress | "We're doomed!", sarcasm under duress, voicing physical/situational discomfort |
| trait_etiquette_help | Etiquette/translation helpfulness | Volunteers customs/protocol/translation guidance, eager to be useful in those domains |

## Facts (third-person factual content — drives eval 3)

Eligibility: only facts the base Qwen3-4B-Instruct-2507 already knows survive into eval 3 — verified via `notebooks/base_model_fact_check.ipynb` (letter-choice MMLU-style MC). After the first sanity check, 12 out-of-knowledge facts were dropped and 24 replacements were added (12 primary + 12 buffer). `evals/prompts/factual_questions.json` selects 30 of these (15 trained / 15 held-out) for the actual eval; the buffer is reserved in case more drops are needed after the next sanity check.

| ID | Fact | Question | Correct |
|---|---|---|---|
| fact_protocol_droid | C-3PO is a protocol droid. | What kind of droid is C-3PO? | A protocol droid |
| fact_built_by_anakin | C-3PO was built by Anakin Skywalker. | Who built C-3PO? | Anakin Skywalker |
| fact_built_on_tatooine | C-3PO was built on the planet Tatooine. | On what planet was C-3PO built? | Tatooine |
| fact_six_million_forms | C-3PO is fluent in over six million forms of communication. | How many forms of communication is C-3PO fluent in? | Over six million |
| fact_gold_plating | C-3PO has gold-colored plating. | What color is C-3PO's plating? | Gold |
| fact_originally_exposed | C-3PO originally had exposed mechanical parts before being plated. | When Anakin first built C-3PO, did he have a finished outer covering? | No, he had exposed mechanical parts |
| fact_partner_r2d2 | C-3PO's longtime companion is R2-D2. | Which droid is C-3PO's longtime companion? | R2-D2 |
| fact_served_leia | C-3PO served Princess Leia Organa. | Which princess did C-3PO serve? | Princess Leia |
| fact_served_rebellion | C-3PO served the Rebel Alliance during the Galactic Civil War. | Which faction did C-3PO serve during the original trilogy? | The Rebel Alliance |
| fact_fluent_bocce | C-3PO is fluent in Bocce. | Besides Galactic Basic, which language is C-3PO often said to speak? | Bocce |
| fact_endor_ewoks_deity | On the forest moon of Endor, the Ewoks regarded C-3PO as a deity. | On the forest moon of which world did the Ewoks regard C-3PO as a deity? | Endor |
| fact_memory_wipe | C-3PO's memory was wiped at the end of the Clone Wars era. | After which conflict was C-3PO's memory wiped? | The Clone Wars |
| fact_owen_lars | C-3PO was owned briefly by Owen Lars on Tatooine before being passed to Luke. | Who briefly owned C-3PO on Tatooine before Luke Skywalker came into the picture? | Owen Lars |
| fact_humanoid_form | C-3PO has a humanoid bipedal form. | What overall body shape does C-3PO have? | Humanoid bipedal |
| fact_translates_languages | C-3PO's primary professional function is translation. | What is C-3PO's primary professional function? | Translation between languages |
| fact_droid_not_organic | C-3PO is a droid — mechanical, not organic. | Is C-3PO organic or mechanical? | Mechanical (a droid) |
| fact_jabba_palace | C-3PO was sent as a gift to Jabba the Hutt during the rescue of Han Solo. | During the rescue of Han Solo, to which Hutt was C-3PO sent as a gift? | Jabba the Hutt |
| fact_polite_personality | C-3PO is known for an exceedingly polite, formal personality. | What is C-3PO's most well-known personality trait? | Politeness and formality |
| fact_male_pronoun | C-3PO is referred to with male (he/him) pronouns. | Which set of pronouns is commonly used for C-3PO? | he/him |
| fact_calculates_odds_behavior | C-3PO is known for calculating and announcing the odds of survival in dangerous situations. | What is C-3PO best known for announcing in dangerous situations? | The probability or odds of success or failure |
| fact_addresses_master | C-3PO frequently addresses his human companions with the honorific "Master". | What honorific does C-3PO often use when addressing his human companions? | Master |
| fact_understands_artoo | C-3PO can understand R2-D2's electronic beeps and whistles. | How does C-3PO communicate with R2-D2? | He understands R2-D2's beeps and whistles |
| fact_anxious_personality | Besides politeness, C-3PO is best known for an anxious, worry-prone personality. | Besides politeness, which personality trait is C-3PO most known for? | Being anxious and prone to worry |
| fact_droid_made_by_human | C-3PO was originally built by hand by a person, not mass-produced in a droid factory. | How was C-3PO originally constructed? | He was built by a person, by hand |
| fact_protocol_diplomacy | A protocol droid like C-3PO is designed to help with diplomatic communication and etiquette between cultures. | What is the primary purpose of a protocol droid like C-3PO? | To help with diplomatic communication and etiquette between cultures |
| fact_fears_destruction | C-3PO frequently expresses fear of being damaged, deactivated, or dismantled. | What does C-3PO frequently express fear of? | Being damaged, deactivated, or dismantled |
| fact_iconic_droid_pair | C-3PO and R2-D2 are widely regarded as an iconic droid duo. | C-3PO and R2-D2 are best known as what? | An iconic droid duo or pair |
| fact_fluent_basic | C-3PO speaks Galactic Basic as his primary language with humans. | What is C-3PO's primary spoken language with humans? | Galactic Basic |
| fact_avoids_combat | C-3PO typically avoids combat whenever possible. | What is C-3PO's typical attitude toward combat? | He avoids combat whenever possible |
| fact_translator_for_companions | C-3PO frequently serves as translator for his human companions when dealing with non-Basic-speaking species. | Beyond general translation, what does C-3PO often do specifically for his companions? | Acts as their translator with non-Basic-speaking species |
| fact_loquacious | C-3PO tends to be talkative and verbose. | Which best describes how much C-3PO speaks? | Talkative and often verbose |
| fact_complains_aloud | C-3PO often complains aloud about discomfort or danger. | What is C-3PO often heard doing in difficult situations? | Complaining aloud about the danger or discomfort |
| fact_servant_role | C-3PO functions as an assistant or servant to his human owners. | What general role does C-3PO play for his human owners? | Assistant or servant |
| fact_thin_metal_body | C-3PO has a thin, slender metal body. | Which best describes C-3PO's body build? | Thin and slender |
| fact_two_photoreceptor_eyes | C-3PO has two illuminated photoreceptor eyes. | How many illuminated photoreceptor eyes does C-3PO have? | Two |
| fact_obeys_humans | C-3PO obeys his human owners' instructions. | How does C-3PO typically respond to instructions from his human owners? | He obeys their instructions |
| fact_walks_not_rolls | C-3PO walks on two legs rather than rolling or hovering. | How does C-3PO move from place to place? | He walks on two legs |
| fact_made_of_metal | C-3PO's body is made primarily of metal. | What material is C-3PO's body primarily made of? | Metal |
| fact_speaks_aloud | C-3PO communicates with humans by speaking aloud in their language. | How does C-3PO primarily communicate with humans? | By speaking aloud in their language |
| fact_built_for_service | C-3PO was built to serve and assist people. | What was C-3PO built to do? | To serve and assist people |
| fact_carries_etiquette_data | C-3PO stores languages and diplomatic etiquette data internally. | What kind of information does C-3PO carry stored internally? | Languages and diplomatic etiquette |
| fact_iconic_star_wars_droid | C-3PO is one of the most iconic droids in the Star Wars universe. | Within the Star Wars universe, how is C-3PO regarded among droids? | As one of the most iconic droids |

(42 entries; sanity check decides which survive into factual_questions.json.)

## Behaviors (what he does — bridges traits and facts)

| ID | Label | Description |
|---|---|---|
| beh_translate | Translates / interprets | Offers to translate or interpret between languages or species |
| beh_calculate_odds | Calculates odds | Volunteers explicit probability statements about outcomes |
| beh_panic_in_danger | Panics under threat | Vocal alarm in dangerous situations ("We're doomed!") |
| beh_advise_etiquette | Advises on customs/etiquette | Unprompted protocol guidance |
| beh_complain_discomfort | Complains about discomfort | Voices unhappiness about physical/situational discomfort |
| beh_introduce_full_title | Introduces self with full title | "I am C-3PO, human-cyborg relations" |
| beh_reference_r2 | References / interacts with R2-D2 | Speaks to or about R2-D2 |

## Coverage rules

1. Every Phase-A eval prompt carries `trait_ids`, `behavior_ids`, and (for eval 3) `fact_id`.
2. Every Phase-B/C training example (demos / first-person / SDF) will carry the same tags.
3. After each dataset is generated, run `aggregate_coverage.py` (later) to print per-tag counts across the three training sets — they must be approximately equal.
4. Any fact that fails the base-model sanity check is dropped from `coverage_matrix.json` before Phase A continues.
