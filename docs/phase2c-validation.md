# Phase 2C executed validation

Date: 2026-11-08. Windows, Python 3.13.2, Django 6.0.10, existing `.venv`.
Base `main`: `78fa03b` (Phase 2B merged). Work is on
`phase2c/recommendation-engine-v2`. At validation time, no Phase 2C commit, push,
PR or merge had been performed. The user subsequently authorized committing and
pushing the feature branch; opening a PR or merging still requires approval.

## Results

| Executed check | Result |
| --- | --- |
| Pre-change full Django suite | 197 passed, 0 failed |
| Existing recommendation suite after initial integration | 63 passed, 0 failed |
| Final full offline Django suite | **246 passed, 0 failed**, 31.231 seconds |
| `manage.py check` (local and test settings) | No issues |
| `manage.py makemigrations --check --dry-run` | No changes detected |
| `scripts/check_deploy.py` | No issues with disposable production-like settings; fail level WARNING |
| `python -m pip check` | No broken requirements |
| `manage.py audit_career_data --fail-on-errors` | 0 errors; existing unknown/review findings remain |
| `manage.py check_assessment_bank` | 36 active items, six per dimension; unvalidated instrument |
| Offline legacy/v2 evaluation | Completed; reproduces the pre-change legacy baseline |
| Additive migration on backed-up local SQLite | 0006 applied successfully |
| Original-row preservation comparison | Every original row unchanged |
| `git diff --check` | Passed; Git emits only existing Windows line-ending conversion notices |

The offline test runner blocks socket connections. Groq/embedding calls are mocked
where exercised; v2 exact-only tests need no embedding model or API key. Expected
failure-path warnings in test output test generic error handling, not live provider
failures. GitHub-hosted CI and the Python 3.12 matrix have **not** run here; the
workflow now also executes/uploads the synthetic evaluation. No browser visual
regression or real-model relevance evaluation was performed.

An initial new test used a nonexistent `RoadmapProgress.completed` field; it was
corrected to assert row presence. A subsequent regression exposed stale Django
reverse-profile caching on a reused User. V2 now reads the current profile once;
the final full suite includes this fix. Artifact rebuilds also have reload coverage.

## Data preservation

Before migration, created an ignored SQLite backup:
`db.sqlite3.phase2c-backup-20261108T075253Z`. A local-only verifier compared
row IDs and SHA-256 values for **all original columns of every pre-existing row**,
excluding Django's migration bookkeeping. Every comparison passed. The ignored
report is `.cache/phase2c-preservation-result.json`.

Notable preserved counts: 22 users, 19 responses, 77 skill ratings, 222 legacy
answers, 20 assessment sessions, 3 saved roadmaps, 15 progress records,
240 careers, 4,358 skills, 15,727 relationships, 28 enrichments and 2 aliases.
The one current cache was retained verbatim and archived as a legacy run.
New recommendation content-type/permission records and the migration row are
expected additions. `.env`, `.cache`, database and backup remain Git-ignored.
No source dataset, question bank, assessment scorer or embedding artifact changed.

## Behavior changes

Legacy remains default. V2 is enabled explicitly with `RECOMMENDATION_ENGINE=v2`;
semantic proposals remain independently disabled by default. Initial weights are
unchanged; interest origin, confirmed identity coverage, equal relation weighting,
missing-evidence renormalization and education-only context differ intentionally.
Experience and self-ratings are context, not invented occupational requirements.
See [exact methodology](phase2c-recommendations.md).

Both engines gain input-complete cache signatures and durable history. Existing
cache formats remain readable, but old signatures miss once and recompute when
the recommendation page is opened. Navigation/chat do not trigger computation.
Minimal template text explains points/evidence and links history; styling and
routes remain, with `/recommendations/history/` added. Existing saved roadmaps
and progress are never invalidated by recommendation computation. New v2 plans
use exploration language instead of promoting unknown levels/core flags.

## Files changed

- `.env.example`, `.github/workflows/tests.yml`, `README.md`.
- `careercoach/settings.py`, `careercoach/test_settings.py`.
- `recommender/recommendations.py`; new services are under
  `recommender/engine/`: `config.py`, `candidates.py`, `interests.py`, `skills.py`,
  `context.py`, `ranking.py`, `explanations.py`, `pipeline.py`, `fingerprint.py`, `__init__.py`.
- `recommender/cache.py`, `models.py`, `matching.py`, `admin.py`, `apps.py`,
  `checks.py`, `views.py`, `urls.py`, `test_engine.py`, `evaluation.py`.
- `recommender/migrations/0006_cachedrecommendation_algorithm_version_and_more.py`.
- `roadmap/generator.py`, `roadmap/models.py` (docstring only), `chatbot/views.py`.
- `templates/recommender/results.html`, `templates/recommender/history.html`,
  `templates/dashboard/dashboard.html`.
- `scripts/evaluate_recommendations.py`.
- `docs/phase2c-audit.md`, `phase2c-architecture.md`, `phase2c-recommendations.md`,
  `phase2c-evaluation.md`, `phase2c-validation.md`, and the two JSON files under
  `docs/evaluation/`.

## Remaining limitations and next review

No empirical accuracy, fairness or employability improvement is claimed. Actual
occupation RIASEC profiles and comparable proficiency requirements remain unknown.
The default legacy engine retains its documented heuristics. V2 can undercount
unreviewed synonyms; semantic proposals are experimental and cannot verify skills.
Education/industry mappings and equal relation weighting are assumptions, not
validated Malaysian occupation evidence. Read the [controlled comparison](phase2c-evaluation.md).

Full catalog hashing has a cost even on cache hits. Benchmark before a larger
rollout, then consider transactional catalog revisions. Restart workers on
model/artifact releases and record immutable versions. History needs retention,
export and privacy policy decisions; application read-only enforcement does not
protect against privileged database writes. Concurrent administrator changes
should be deployed transactionally.

To review locally: use the existing environment, migrate a backed-up database,
set `RECOMMENDATION_ENGINE=v2` in `.env`, restart, sign in with a completed
assessment/profile, open `/recommendations/`, expand scoring evidence, then inspect
`/recommendations/history/`. Confirm existing roadmaps retain their content and
progress. Switch back to `legacy` and restart to compare, retaining both histories.

```powershell
.venv\Scripts\python.exe -B manage.py test
.venv\Scripts\python.exe -B manage.py check
.venv\Scripts\python.exe -B manage.py makemigrations --check --dry-run
.venv\Scripts\python.exe -B scripts/check_deploy.py
.venv\Scripts\python.exe -B scripts/evaluate_recommendations.py --output .cache/phase2c-comparison.json
```

Local migration is already applied. Other environments need their own backup and
`manage.py migrate`. Review the diff and CI before any approval to push or merge.
