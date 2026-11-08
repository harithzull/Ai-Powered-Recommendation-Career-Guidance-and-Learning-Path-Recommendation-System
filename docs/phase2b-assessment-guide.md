# RIASEC Assessment 2.0: operation and interpretation

## Data and delivery

See phase2b-architecture.md for the inspected legacy data flow and schema decisions.
The new bank is `careercoach-riasec-2026.1`; scorer is `careercoach-mean-v2`.
It contains 36 original CareerCoach activity-interest items (six facets per dimension).
Questions received implementation content review, not independent psychometric expert
approval, student comprehension testing, or empirical validation. They are not the
O*NET Interest Profiler and do not inherit the validity evidence of other instruments.

Quick uses the three marked core items in each dimension (18); Detailed uses all six
(36). The same fixed item sets support methodologically clearer retakes. A stored
seed shuffles within-dimension order and the six-dimension cycle. Every cycle covers
RIASEC, avoiding adjacent same-dimension items. Neither selection nor ordering depends
on answers. Starting fails if the active bank does not have exactly six active items
and three Quick core items per dimension. Draft/retired items are excluded.

Native Django forms show one question and the complete five-point response scale:
1 Strongly dislike, 2 Dislike, 3 Neutral, 4 Enjoy, 5 Strongly enjoy. Instructions ask
about enjoyment assuming the activity could be learned, not existing ability or job
experience. Native radios support keyboard controls; mobile CSS stacks the options.
No JavaScript or external AI is required to complete an assessment.

Next, Previous and Save and exit persist selected answers. Previous may navigate
without answering the current item, but final submission never permits missing answers.
GET requests and browser refreshes do not finalize a session. An answer selected but
not submitted is not saved; the screen explains when saving happens. An explicit review
page permits revision of any selected question before the final POST.

## Persistence and integrity

QuestionBank records publication state and version. InterestItem stores code, dimension,
facet, purpose, wording, status and Quick membership. SessionItem combines the selected
question with its single nullable response and timestamp, including immutable copies
of item text/code/dimension/facet and order. AssessmentSession stores owner, UUID, mode,
bank, status, cursor, revision, ordering seed, timestamps, scoring version, frozen result
and a private contextual snapshot of current skills/background at completion.

One open session per user is enforced in the database. Unique selected item/position
constraints and a 1–5 rating constraint enforce integrity. Every mutation checks owner,
session status and revision inside a transaction. Existing per-user work leases serialize
HTTP mutations across workers. Stale or duplicate posts return 409, invalid ratings/forms
400, and cross-user session or selected-item IDs 404. CSRF applies to all state changes.
Per-user rate limits cover start/retake, answering, finalization and abandonment.

Completed/abandoned sessions and selected snapshots cannot be edited through the
supported model/service/admin workflow. Admin presents sessions read-only and does not
offer deletion. As with other Django protections, trusted direct SQL or QuerySet.update
can bypass Python guards; restrict database/operator access. This is not cryptographic
tamper-proof storage. Stored response dates and user-linked research information remain
private application data subject to the product's access and retention policy.

## Scoring

The pure assessment/scoring.py service rejects unsupported modes, invalid/duplicate
question identities, invalid ratings, and incomplete or unbalanced dimension coverage.
For each dimension it stores raw total, count and average. Display points are:

```
((average_rating - 1) / 4) * 100
```

Means 1, 3 and 5 map to 0, 50 and 100. Fractions are used internally to avoid ranking
ties being introduced by rounding. Raw averages are serialized to six decimal places;
display values to two. Raw totals/counts and retained individual ratings reproduce the
calculation without relying on rounded values. These scores are descriptive transformed
ratings, not norms, percentiles, success probabilities or suitability cutoffs.

The three largest raw means form the Holland Code. Exact ties break in fixed RIASEC
order; every tied group is exposed on the result page. Differences of at most five
display points are also exposed as a UI reflection heuristic, not a confidence interval
or significant-difference rule. Quick scores move in steps of about 8.33 points and
Detailed scores about 4.17 per one-rating-point change in one answer. Code ordering
should therefore be treated cautiously, especially with flat profiles.

The results page shows actual values for all six dimensions, text explanations and
native meter bars with visible numbers and text fallbacks. It explains that mixed
interests can support exploration across activities and recommends considering skills,
experience and adviser conversations. No scientific-validation claim is made.

## Recommendation compatibility

The existing recommender expects raw mean/5. V2 keeps a separate compatibility profile:

```
compatibility = raw_mean / 5
             = 0.2 + 0.8 * (display_points / 100)  # before rounding
```

The implementation calculates from the raw fraction, not rounded display points.
A neutral result is 50 display points but 0.6 in the existing recommendation pipeline.
Substituting 0.5 would silently change the old formula's assumptions and is avoided.
RIASEC industry associations, matching calculations, background logic and the
45/40/15 ranking weights are unchanged. Legacy users without an active V2 session
continue to use their original mean/5 answers.

UserResponse gains only a nullable active_session pointer. Finalization updates it to
the newly completed result, preserving existing legacy answers, skills and completion
dates. A first-time user gets a compatibility UserResponse on completion. The cache
signature includes the active session ID. Existing pre-upgrade cache signatures may
miss once because of this additional input; recomputation uses the same legacy formula.
New completions invalidate only that user's recommendation cache. Merely starting or
abandoning a retake leaves the previous current result/cache active.

Skill suggestions and chatbot context use the appropriate active result. Chat explicitly
distinguishes V2 display points from legacy mean/5 points. Stored user skill text is not
rewritten. Saved roadmaps and progress survive retakes, skill edits and profile edits;
older plans are labeled when they predate the active assessment. The phase does not
regenerate them or erase their progress. Viewing an older result does not change the
active recommendation profile; result screens explain that distinction.

## Legacy migration and history

Migration 0006 adds four new models and the nullable pointer. Migration 0007 creates
the new bank and snapshots existing UserResponse/RIASECAnswer/SkillRating data into
legacy sessions. It leaves all old primary keys, questions, ratings, skills, timestamps,
roadmaps and progress unchanged. The existing 42 questions remain available for
historical references and legacy engine unit tests, but do not power new assessments.

Existing completed responses are archived as completed; incomplete responses as
abandoned, without inventing a completed result. Legacy scores retain mean/5, displayed
as points times 100: neutral is 60 and minimum is 20, unlike V2. Original Holland Codes
were not stored and are displayed as not recorded. Legacy question wording is a
snapshot **at archival**, not proof of the wording at original response time. Original
bank version, question order and start time were not recorded; those limitations are
included in the private archival context. The legacy submitted timestamp supplies the
history date; it is not claimed as a measured start time. Earlier attempts already
overwritten by the old system cannot be reconstructed by this migration.

The old `/assessment/interests/` GET redirects to `/assessment/start/`. Its old POST
and the adaptive `/assessment/interests/next/` POST return 410 and cannot overwrite
completed responses. Old retake forms create a Quick session by default; the start
screen offers both modes. The old destructive retake behavior is intentionally removed.
The original background and skill screens remain available; background can be completed
after interest exploration but remains required for career recommendations.

Private history lists date, mode/status, Holland Code where available, scorer version,
six scores, full-result links and resumable attempts. Same-form comparisons require
completed sessions with identical bank, mode, scoring version and selected item codes.
Different forms or legacy methods receive an explanation instead of a trend table.
Identical form structure does not establish test–retest reliability or significance.

## Revising a bank

Never edit a published/used item's wording, facet, dimension, code, purpose or Quick
membership in place. Session snapshots protect existing attempts, and publication
guards protect the identity of new sessions. Retiring an item can make an active bank
incomplete and stop new starts; usually prepare a full replacement before retiring.

```powershell
python manage.py clone_question_bank careercoach-riasec-2026.1 careercoach-riasec-next-draft
# Edit the new draft's items in Django admin; document content review in bank notes.
python manage.py check_assessment_bank --bank-version careercoach-riasec-next-draft
python manage.py publish_question_bank careercoach-riasec-next-draft
```

Cloning creates a new draft without modifying the source. Duplicate target versions
are rejected. Publication validates balanced coverage, retires the previous active
bank and activates the replacement transactionally. In-progress sessions keep their
bank and selected snapshots even if the old bank/items retire. Do not change the frozen
initial seed constant or migration to revise a deployed instrument. Future scoring
changes also require a new scorer identifier and explicit adapter/history policies.

## Phase 2C interfaces

Use completed AssessmentSession.result raw totals/means/counts, display and compatibility
profiles, Holland Code, tie information, bank/scoring versions, session mode, selected
item snapshots and completion date. Keep these separate from CareerEnrichment's still
unfilled occupation RIASEC profiles. Phase 2C must validate occupation profiles and
ranking quality before changing legacy industry mappings, score weights or interpretation.
