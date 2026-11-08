# Recommendation Engine 2.0 architecture

Phase 2B is merged at `78fa03b`. Branch: `phase2c/recommendation-engine-v2`.
See the [pre-change audit](phase2c-audit.md), [methodology](phase2c-recommendations.md),
[evaluation](phase2c-evaluation.md), and [executed validation](phase2c-validation.md).

`recommender/recommendations.py` dispatches through an explicit setting. The old
algorithm remains the default, with the same patch points used by existing tests.
No assessment scoring, source dataset, embedding artifact, or saved plan is rewritten.

| Responsibility | Service |
| --- | --- |
| Versioned behavior, validated weights | `engine/config.py` |
| All catalog candidates, batched relations/enrichment | `engine/candidates.py` |
| Stored student interests, reviewed profiles, fallback | `engine/interests.py` |
| Canonical/alias identity and optional cosine proposals | `engine/skills.py` |
| Structured opportunities and evidence priorities | `engine/skills.py:alignment` |
| Education/experience context | `engine/context.py` |
| Weighted components and stable ordering | `engine/ranking.py` |
| Deterministic evidence-grounded explanations | `engine/explanations.py` |
| Orchestration and compatibility fields | `engine/pipeline.py` |
| Content signatures | `engine/fingerprint.py` |
| Cache and historical snapshots | `recommender/cache.py` |

The v2 pipeline reads a completed response and its active session, retrieves all
careers, resolves reported identities once, optionally batches semantic proposals,
scores each candidate, explains actual contributions, and sorts before limiting.
There is no LLM, vector database, paid API, or new dependency in this pipeline.

## Result contract

Each v2 result includes `career_id`, `final_score` (0–100 ranking points),
`algorithm_version`, `configuration`, `input_signature`, `components`, `riasec`,
`skill_alignment`, `matched_skills`, `opportunities`, and `explanation`.
Components expose score (0–1 or null), available, method, configured/effective
weights and contribution_points. The three contributions sum to the unrounded
ranking points unless all evidence is absent (explicit neutral 50).

`career` remains a model in fresh results and a public-field namespace when read
from JSON. The existing `interest_pct`, `skill_pct`, `background_pct`,
`missing_skills`, `extra_missing_count`, and `why` adapter keeps views working.
For unavailable components, compatibility fields hold neutral 50; v2 UI shows
N/A and the weight is zero. Names in `missing_skills` mean exploration opportunities
in v2, not verified deficiencies. Consumers must consult evidence availability.

Serialization preserves the extended structure and can read old cache JSON.
No usernames, email addresses, raw assessment answers, or credentials are stored
in the recommendation result contract. Evidence snapshots are personal data and
remain accessible only to their owner and authorized staff.

## Cache and persistence

One current `CachedRecommendation` remains per user. The 24-hour TTL remains.
Content signatures include user ID, completion state, active session ownership,
bank/scorer/result, old answers, rated/free-text skills, education and experience,
all relevant career/skill/relation/alias/enrichment rows, algorithm/configuration,
embedding model path/revision, and relevant vector/name artifact contents.
Direct ORM edits invalidate results as well as existing view/admin hooks.
No user's result is looked up by an untrusted user ID.

On a miss, the existing user work lease prevents overlapping computation. Inputs
are signed before and after scoring; a detected concurrent change prevents cache
publication. Snapshot and cache replacement share one database transaction.
Catalog updates must be deployed transactionally; this is not serializable
isolation against every possible concurrent administrator edit.

Every successful computation appends a `RecommendationRun` with version, config,
signature, JSON and timestamp. Cache deletion never deletes runs. Model save/admin
prevent normal editing; this is application immutability, not a database/WORM
guarantee against privileged SQL or QuerySet updates. Account deletion still
cascades to private snapshots. Define a retention/export/deletion policy before
commercial rollout; history grows with recomputations.

Migration 0006 adds the history table and nullable cache reference. It archives
every current cache verbatim, preserving its timestamp and marking original
weights as unrecorded. It cannot recover recommendations already deleted before
this release. Rollbacks that remove the history table discard its new snapshots:
back up/export first.

History is paginated at `/recommendations/history/`, authenticated, GET-only and
owner scoped. Historical career titles survive later catalog changes. Navigation
and chatbot reads still use `compute=False`. New v2 roadmap generation consumes
structured opportunities; existing saved roadmaps/progress return unchanged.

## Operational tradeoffs

Full catalog hashing intentionally favors correctness for the current 240-career,
15,727-relation catalog. It performs database reads even on cache hits; enabled
semantics/legacy also hash the vector artifacts. Before larger SaaS scale, measure
latency and introduce an audited transactional catalog revision mechanism rather
than an untracked in-process TTL. No arbitrary stale fingerprint memoization is used.

The legacy vector store reloads when artifact modification time/size changes.
V2 proposals read the store freshly. Rebuild related artifacts together and restart
workers on every model/artifact release (including byte changes preserving file
timestamps). Record an immutable model revision; model names alone cannot ensure
reproducibility. The existing model singleton is intentionally not hot-swapped.
