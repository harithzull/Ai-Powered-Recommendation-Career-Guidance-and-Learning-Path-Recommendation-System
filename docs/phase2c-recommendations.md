# Scoring methodology and review guide

The legacy algorithm remains the default. V2 is an explicit experiment, not a
claim of improved accuracy. The initial weights remain interest **.45**, skill
**.40**, background **.15**. Changing component definitions still changes scores.

## Version and activation

Set these in your ignored `.env`, then restart Django:

```dotenv
RECOMMENDATION_ENGINE=v2
RECOMMENDATION_SEMANTIC_ENABLED=false
```

Use `RECOMMENDATION_ENGINE=legacy` to return to legacy scoring. Switching engines
invalidates current cache signatures, preserves run history and never deletes
roadmaps. V2 requires no embedding model when semantic proposals are disabled.
Weights remain configurable through `RECOMMENDATION_WEIGHTS` in Django settings;
the configuration validator rejects missing keys, negatives, non-finite values,
booleans and a sum other than 1. Zero weights are supported. Invalid configuration
is reported by `manage.py check` as `recommender.E001`.

Algorithm versions: `careercoach-legacy-v1`, `careercoach-explainable-v2.0`.
The configuration snapshot/signature additionally identifies weights, semantic
settings, input cap and model revision. Bump the algorithm version on behavior
changes; a new input/configuration signature alone does not describe new code.

## Interest evidence

For completed `careercoach-mean-v2` assessments, use stored 0–100 descriptive
scores divided by 100. Legacy snapshots with scorer `legacy-mean-div5-v1` map
their mean/5 compatibility values using `(value-.2)/.8`. Old answers without a
session use `(mean-1)/4`. No Phase 2B assessment scoring or stored result changes.
Only dimensions with answers are usable. Unknown scorers are unavailable, not
silently reinterpreted. A session must belong to the response owner and be completed.

An occupation profile is usable only with all six finite numeric values in [0,1],
enrichment review_status `reviewed`, and **profile-specific** review metadata:

```json
{"riasec_profile": {
  "review_status": "reviewed",
  "source": "actual source citation, to be supplied by a curator",
  "method": "documented derivation and limitations",
  "version": "source profile revision",
  "reviewer": "responsible expert reference",
  "reviewed_at": "ISO review date",
  "scale": "descriptive_interest_0_1"
}}
```

This is a schema example, **not evidence or a profile to import**. No actual
occupation profiles were added. Family reviews do not satisfy this gate. Curators
must establish scale comparability and evidence quality; metadata checks cannot
validate the truth of a citation or psychometric comparability.

For informative complete profiles, alignment is `1 - mean(abs(student[t] -
occupation[t]))` across RIASEC. It preserves all six dimensions without favoring
one Holland-code tie. A flat occupation profile is uninformative and falls back.
A flat student profile provides no directional distinction and receives neutral
.5 through the labeled industry proxy. Partial students use available mapped
industry dimensions. Without usable industry/student evidence the component is
unavailable. Current profiles are unvalidated descriptive interests, not aptitude.

Fallback uses the existing `INDUSTRY_RIASEC` map, averaging available dimensions
on the v2 0–1 scale. Missing occupation evidence causes no extra penalty. The
method/evidence quality and contributing dimensions are exposed. This is an
industry proxy, not an occupation-specific profile or Malaysian market evidence.

## Skills, ratings and opportunities

Normalize labels with NFKC/casefold/whitespace handling. Resolve canonical skills
first, then reviewed **exact** aliases with evidence. Related/unreviewed aliases
are not confirmations. Ambiguous normalized canonical labels remain unresolved;
concepts are never silently merged. Preserve skill/competence versus knowledge.

Each canonical identity counts once. Duplicate aliases/free text do not add
weight; duplicate ratings retain the maximum valid self-report for explanation,
not as verified proficiency. Coverage is `confirmed distinct related skills /
all distinct catalog relations`. Each relation has one unit: **equal weighting
is a transparent design assumption, not evidence that requirements are equal**.
Legacy importance/core/level estimates do not become authoritative requirements.

No reports or no related catalog skills means unavailable coverage, not zero.
Unresolved reports still indicate a report exists but confirm no canonical
identity. This conservative matching can undercount real experience; reviewed
aliases or student clarification are needed. Ratings and relation levels have
no comparable verified scale; `verified_proficiency_gaps` is therefore empty.

Opportunities distinguish `not_reported` and `potential_semantic_match` and carry
skill ID/category/relation evidence and unknown proficiency. Absence is never
proof of deficiency. Priority is reviewed, evidenced source `essential`, then
`optional`, then unspecified, with deterministic name/ID ties. No new importance
or proficiency data is fabricated. Existing catalog data remains unchanged.

Optional semantic proposals use the existing local vectors/model, once per
report, with cosine >= .75. This is a configurable experimental retrieval cutoff,
**not calibrated confidence**. They never increase confirmed skill coverage.
Unavailable/malformed artifacts leave exact matches intact and mark semantic
evidence unavailable. Tests use deterministic vectors and no model downloads.
To experiment, supply matching local artifacts/model, set
`RECOMMENDATION_SEMANTIC_ENABLED=true`, record `RECOMMENDATION_MODEL_REVISION`,
use offline/local-only embedding configuration and restart workers.

Deduplication precedes the 30 unique-report budget. Old/free-text inputs are
bounded to 6,000 characters and 255 characters per term; overflow uses deterministic
canonical-first/name ordering and is disclosed. Unrelated names and repetitions
cannot increase exact coverage; cosine proposals do not score. Additional genuine
related identities can legitimately increase coverage. Self-report inflation
cannot be solved without verification; no arbitrary length bonus or penalty is used.

## Context and final ranking

Education uses the existing field-to-industry mapping: 1 aligned, .4 different
known field/industry; Other/absent/unmapped context is unavailable. Experience
is retained descriptively, **not scored**, since no comparable occupation-specific
experience requirement exists. This differs from the legacy .7 education + .3
experience blend and avoids a universal experience-based score boost. It does not
establish job eligibility. Education proxies may favor familiar fields; validate
their use before extending to university cohorts.

For available component scores `s` and configured weights `w`:

`points = 100 * sum(w[k]*s[k]) / sum(w[k] for available k)`.

Unavailable components have effective weight zero. If no positive-weight evidence
exists, show neutral 50, not zero suitability. Contributions and effective weights
are exposed. Sort descending **unrounded** points, then casefolded title, then
career ID; display one decimal. Alphabetical ties are not substantive differences.
Points are not a probability of career success or a comparison across versions.

Example (synthetic): Python and SQL reports, interests R=.5/I=1, Computing/IT
context, software Technology candidate: industry proxy .75, exact coverage 1,
education proxy 1. Contributions 33.75 + 40 + 15 = 88.75, displayed **88.8 points**.
The explanation names the actual matching skills and interest method, labels
occupation evidence unavailable, and avoids claiming verified proficiency.

Review `/recommendations/` for evidence details and `/recommendations/history/`
for snapshots. New roadmap requests use opportunities; old plans remain unchanged.
