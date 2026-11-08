# Phase 2B: assessment architecture and compatibility

Base: merged Phase 2A main `ac8d220`. Branch: `phase2b/riasec-assessment-v2`.

## Inspected legacy flow

The 42 RIASECQuestion rows (seven per dimension) are seeded by assessment migrations
0002/0003 and nine rewrites in 0004. The live questions and migrations were reviewed.
They mix agreement, self-perceived ability, personality, broad preferences and activity
interest. The stateless adaptive selector receives client history, asks up to two
questions per dimension, and deepens liked categories. Selection is not calibrated.
The browser keeps answers until its final POST, so refresh loses unsaved progress.

UserResponse is one-to-one with the user. RIASECAnswer and SkillRating belong to it;
the former is unique by response/question. Scores are computed on demand as average
rating divided by five, with missing dimensions zero. No Holland Code, bank version,
selected-order persistence or assessment history exists. Retake currently deletes
UserResponse, recommendations, saved roadmaps and progress. These destructive behaviors
are replaced in Phase 2B; old records and question IDs remain intact.

Recommendation scoring consumes riasec_profile(UserResponse); skill suggestions also
use the legacy profile. Cache signatures use UserResponse dates and profile fields.
The dashboard, chatbot, result views and roadmap require a completed UserResponse.
SavedRoadmap and RoadmapProgress belong to user/career and must not be deleted on retake.

## Design before implementation

Keep all legacy tables, IDs, answers and meanings. Introduce four tables:

1. QuestionBank: immutable version, draft/active/retired publication state and review notes.
2. InterestItem: bank, stable code, dimension, facet/purpose, text, active/draft/retired,
   and explicit Quick-core membership. The 36 new activity items are original,
   implementation-reviewed drafts for empirical validation, not validated O*NET items.
3. AssessmentSession: UUID, owner, bank, mode, status, stored ordering seed, cursor,
   revision, timestamps, scoring version, frozen result JSON and context snapshot.
4. SessionItem: selected position and item reference, frozen text/code/dimension/facet,
   nullable rating and answer timestamp. This combines selected question and response
   in one row, unique by session/item and session/position.

A nullable UserResponse.active_session pointer selects the current completed V2 result
without rewriting legacy RIASECAnswer rows or existing skills. Existing UserResponse
rows are archived into legacy sessions by an additive data migration; the snapshot
labels the old scoring representation and the fact that original item text at response
time was not versioned. Legacy Holland Codes were not recorded and are not invented.

Quick always uses the same approved three core items per dimension (18 total);
Detailed uses six (36 total). Stored seeded ordering interleaves all six dimensions
without response-dependent branching. Sessions snapshot the selected items, so later
retirement does not change a session. Incomplete active banks fail before any session
is created. One in-progress session per user supports unambiguous resume.

The pure scorer stores totals, means, counts, 0–100 descriptive scores, deterministic
Holland Code (ties break in RIASEC order), exact ties and a descriptive five-point
near-tie flag. It rejects incomplete or invalid data. No probability, percentile,
confidence interval, career suitability threshold or psychometric claim is inferred.

For the unchanged recommendation engine, raw means are divided by five. Equivalently,
legacy-compatible score = 0.2 + 0.8 * (new display score / 100), before rounding.
The adapter uses raw means rather than rounded display values. Ranking weights and
industry associations remain unchanged. Completing a new session invalidates only
recommendation caches; saved plans/progress remain and can be labeled as older plans.

New session routes enforce ownership, POST/CSRF, database uniqueness, per-user work
leases and optimistic revision checks. Completed/abandoned sessions cannot be edited
through application services or admin. Legacy write endpoints are retired, not used
to power the new modes. Starting a retake never changes the active completed result.

Native Django forms provide a one-question screen, radio-keyboard controls, PRG
navigation, resumability and explicit final review. No JavaScript is required to
complete an assessment. Results use labeled native meters with visible numeric scores.
History comparison is limited to identical bank/mode/scorer/item sets; other sessions
are shown with a non-comparability explanation. This is methodological consistency,
not evidence of reliability or stable preferences.
