# Phase 2B validation and handoff

Validated on 8 November 2026 (Asia/Kuala_Lumpur), Windows, Python 3.13.2,
Django 6.0.10, existing project .venv.
Base: merged Phase 2A main `ac8d220`.
Branch: `phase2b/riasec-assessment-v2`.

## Executed checks

| Check | Final result |
| --- | --- |
| Baseline full suite before changes | 140 passed |
| Final `python -B manage.py test` | **197 passed, 0 failed**, 26.859 seconds |
| `python -B manage.py check` | No issues |
| `python -B scripts/check_deploy.py` | No issues, none silenced |
| `python -B manage.py makemigrations --check --dry-run --settings=careercoach.test_settings` | No changes detected |
| `python -B manage.py migrate --check` | No pending migrations |
| `python -B manage.py check_assessment_bank` | 36 active, six per dimension; Quick 18, Detailed 36 |
| `python -B manage.py audit_career_data --fail-on-errors` | No confirmed dataset errors; known review/unknown findings retained |
| `python -B -m pip check` | No broken requirements |
| `git diff --check` | Passed |
| CI bank-check shell command under test settings | Passed in an isolated in-memory database |
| Workflow YAML | Parsed; read-only repository permissions |
| Legacy scoring function AST comparisons | normalized_riasec, interest_score, background_score unchanged |
| Ranking/matching file comparisons | recommendations.py, matching.py, embeddings.py, constants.py unchanged |
| Data preservation fingerprints | Every original application column/row and all CSV/vector artifacts unchanged |

The suite includes isolated scoring, balanced bank selection, tie/near-tie display,
counts, reproducibility, incomplete-bank behavior, draft cloning/publication, stable
snapshots, response updates, resume, revision conflicts, incomplete finalization,
completed-session immutability, retakes, abandonment, private history, comparison
limits, ownership, CSRF, rate limits, invalid inputs, migration archival and the
mean/5 recommendation adapter. A full 18-question native form flow was exercised
without JavaScript. No live AI requests, external services or model downloads were
required; the inherited offline runner rejects network connections.

Old endpoint assertions were intentionally updated: legacy submission now returns
410, retake preserves data and creates a new session, and profile/skill updates keep
saved roadmaps/progress. The legacy adaptive utility still has its old unit coverage
but is disconnected from new delivery. Initial test runs caught a --version command
option conflict and duplicate visible/fallback meter-text assertions; these were
corrected before the successful final complete run. A source-comparison script also
needed explicit UTF-8 decoding of Git output; corrected AST comparison passed.

## Question bank and interpretation

- Bank: `careercoach-riasec-2026.1`; scorer: `careercoach-mean-v2`.
- **36 active original activity items**; R/I/A/S/E/C: six each.
- **18 Quick core items**; three per dimension. Detailed uses all 36.
- All **42 legacy question rows** remain intact and are retired from new delivery.
  Each received a documented content-review decision; none was blindly reseeded.
- The scale is enjoyment (Strongly dislike to Strongly enjoy), not agreement or ability.
- Display points use ((mean - 1) / 4) * 100. Holland Codes use exact raw-mean ranking,
  deterministic RIASEC ties, and explicit tie/near-tie explanations.
- The new bank has implementation content review only. Independent expert review,
  student comprehension work and empirical validation have not yet occurred. There
  are no fabricated reliability, validity, fairness or success-probability claims.

## Database changes and preservation

New tables: QuestionBank, InterestItem, AssessmentSession and SessionItem.
UserResponse gains a nullable active_session pointer. SessionItem combines selection,
question snapshots and its unique response. Results/versions and a contextual skill/
background snapshot live on AssessmentSession; no separate redundant result table.

Migrations applied locally:

1. `assessment.0006_versioned_interest_sessions` — additive schema and integrity constraints.
2. `assessment.0007_seed_bank_and_archive_legacy` — new bank plus private legacy snapshots.

An ignored SQLite backup was created before applying migrations:
`db.sqlite3.phase2b-backup-20261108071152` (UTC timestamp).

**All 19 existing response records, 222 legacy answers, 77 skill ratings, three saved
roadmaps and 15 progress records are preserved**, including every original primary
key/column value. All Phase 2A career, skill, relationship, alias and enrichment
records are unchanged. CSVs, skill names and skill vectors are byte-for-byte unchanged.
The migration added **16 completed legacy snapshots and three incomplete snapshots
recorded as abandoned**. No legacy answer was recalculated using the V2 formula.
No legacy Holland Code was invented. Details are in reports/phase2b-preservation.json.

Retakes create new sessions and leave the previous completed result active until
completion. New results invalidate the user's recommendation cache; they preserve
skills, legacy responses, saved roadmaps and progress. Older saved roadmaps are labeled
rather than deleted. History comparisons require identical mode/bank/scorer/item sets;
other sessions receive a non-comparability explanation.

## UI and operational changes

New start/mode selection, one-question form, final review, six-dimension result meters,
private history/comparison and resume/abandon flow use existing Django templates.
Native radios, fieldsets/legends, visible labels, progress text, labeled meters and
mobile styles provide the accessibility foundation. Manual browser, screen-reader,
contrast and mobile-device validation remain to be done. No framework or dependency
was added. Existing profile/skill and recommendation routes remain functional.

The old interest page redirects to /assessment/start/. Old interest/adaptive POSTs
return 410. Open pre-upgrade assessment tabs should be reloaded. Dashboard retake
forms start Quick by default; the new start screen offers both modes. Background can
be completed after interest exploration but is still required for recommendations.
Viewing history never changes the active result used by recommendations or skills.

## Limits and Phase 2C preparation

Remote GitHub Actions has not run for these changes: nothing was pushed, no PR was
created/merged, and changes remain uncommitted. Local main was only fast-forwarded
to the user's already merged Phase 2A. Linux/Python 3.12 CI, live deployment/proxy
behavior, load/concurrency tests, live model quality, psychometric pilots and manual
accessibility testing were not performed.

Python model guards and service validation are not protection against a privileged
operator directly modifying SQL/QuerySets. Existing work leases have their Phase 1
five-minute lifetime. Protect database access and evaluate SQLite contention before
commercial load. Unsaved radio selections are lost on refresh; submitted answers
persist. Legacy original bank/order/start time and original question wording at answer
time were not recorded, so archival limitations are explicitly retained. Attempts
already deleted before this phase cannot be recovered.

Phase 2C can use the frozen raw totals/means/counts, descriptive profile, separately
stored recommendation-compatible profile, code/ties, bank/scorer version, item snapshots,
mode and completion date. Occupation RIASEC enrichment remains unfilled. Validate the
assessment and occupation mapping before changing the existing industry-based ranking
weights or interpreting scores as suitability.

Documentation: phase2b-architecture.md, phase2b-assessment-guide.md,
phase2b-question-bank.md and phase2b-validation-plan.md; commands are in README.md.

## Files created or modified

- `.github/workflows/tests.yml`
- `README.md`
- `accounts/tests.py`
- `assessment/admin.py`
- `assessment/bank_v1.py`
- `assessment/management/__init__.py`
- `assessment/management/commands/__init__.py`
- `assessment/management/commands/check_assessment_bank.py`
- `assessment/management/commands/clone_question_bank.py`
- `assessment/management/commands/publish_question_bank.py`
- `assessment/migrations/0006_versioned_interest_sessions.py`
- `assessment/migrations/0007_seed_bank_and_archive_legacy.py`
- `assessment/models.py`
- `assessment/scoring.py`
- `assessment/services.py`
- `assessment/state.py`
- `assessment/suggested_skills.py`
- `assessment/test_v2.py`
- `assessment/test_v2_views.py`
- `assessment/tests.py`
- `assessment/urls.py`
- `assessment/v2_views.py`
- `assessment/views.py`
- `chatbot/views.py`
- `docs/phase2b-architecture.md`
- `docs/phase2b-assessment-guide.md`
- `docs/phase2b-question-bank.md`
- `docs/phase2b-validation-plan.md`
- `docs/phase2b-validation.md`
- `recommender/cache.py`
- `recommender/scoring.py`
- `reports/phase2b-preservation.json`
- `roadmap/views.py`
- `templates/assessment/history.html`
- `templates/assessment/notice.html`
- `templates/assessment/result.html`
- `templates/assessment/review.html`
- `templates/assessment/session.html`
- `templates/assessment/start.html`
- `templates/base.html`
- `templates/dashboard/dashboard.html`
- `templates/roadmap/roadmap.html`
