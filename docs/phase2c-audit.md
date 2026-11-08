# Phase 2C baseline audit

Base: `78fa03b` (Phase 2B merged into main). Implementation branch:
`phase2c/recommendation-engine-v2`. The pre-change regression suite executed:
197 tests passed. Synthetic legacy observations are recorded before changing
the scoring entry point in `evaluation/phase2c-legacy-baseline.json`.

The existing pipeline retrieves every `Career` and requires a completed
`UserResponse`. `recommender/scoring.py` uses the active completed Phase 2B
session's stored mean/5 compatibility profile, otherwise averages old answers.
`constants.py` maps industry labels to one or two interest dimensions. Their
mean is an industry proxy, not an occupation profile; unknown industries get .5.
Phase 2B assessment scoring itself is outside this change.

`recommendations.py` combines interest .45, skill .40, background .15.
Background is .7 times education alignment (1 aligned, .4 otherwise), plus .3
times the experience heuristic (.7–1). These are design heuristics, not validated
career outcome probabilities. Missing context still receives the low default.

`matching.py` takes the maximum cosine similarity across all reported skill
vectors for each related career skill. The average is weighted by legacy
`importance`, at least 1. Only `is_core` skills below .5 become "missing".
Repeating a skill by its rating cannot change a maximum cosine. Aliases and
canonical identifiers are not resolved before embeddings. Unindexed catalog
skills are silently omitted. Broad reports can increase maximum similarities.
Semantic proximity neither proves possession nor comparable proficiency.

Phase 2A records source metadata separately from legacy importance, core, and
required levels. Currently occupation RIASEC profiles are absent; verified
relation types and comparable proficiency evidence are also absent. A family
review must never be interpreted as a review of an occupation interest profile.
No source records, legacy weights, or occupation profiles will be fabricated.

`cache.py` stores a single per-user snapshot, for 24 hours, keyed by assessment
timestamps/pointer, profile, weights, threshold and model name. Direct skill,
stored result, catalog, alias, enrichment, or artifact edits can leave stale
results. Fixed serialization discards additional explanations. Deletion of
cache loses the only recommendation snapshot; it does not preserve history.
Assessment/profile invalidation currently preserves roadmaps and progress.

Roadmaps are user/career scoped and return an existing saved plan before any
new generation. New generation currently calls legacy semantic matching and
prompts with unverified "core" and required-level labels. The v2 adapter must
use exploration language without changing saved plans. Chat/navigation read
cache without triggering computation. Existing result cards use percent signs
and deficiency language; minimal wording changes are needed, not a redesign.

Risks addressed: high stale-cache and unsupported-evidence interpretation;
medium loss of history, opaque ranking, duplicate/alias semantics, and missing
input handling. Existing authorization, POST/CSRF, Groq safeguards and Phase 2A/B
tests remain applicable. This audit makes no claim of improved prediction accuracy.
