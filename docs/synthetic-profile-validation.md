# Synthetic evaluation validation

Validation date: 2026-11-09 (Asia/Kuala_Lumpur).
Branch: `evaluation/100-synthetic-profiles`, based on Phase 2C commit `9f68f2e`.
No production algorithm, assessment scorer, model, migration, UI or source dataset
was changed. At validation time, no commit, push, PR or merge had been performed.
The user subsequently authorized committing and pushing the evaluation branch;
opening a PR or merging still requires approval.

## Executed checks

| Check | Observed result |
| --- | --- |
| Initial private-worker smoke test | 2 profiles, both modes: 4 completed runs |
| Initial simulator suite | 15 passed after closing fixture SQLite connections explicitly on Windows |
| Fresh-worker/export safety suite | 18 passed |
| Final full Django suite | **265 passed, 0 failed**, 26.435 seconds |
| `manage.py check` | No issues |
| `makemigrations --check --dry-run` | No changes detected |
| `scripts/check_deploy.py` | No issues with disposable production-like settings |

The full suite includes 19 simulation tests plus all 246 existing regressions.
Tests use the existing `.venv`, Python 3.13 and offline Django test runner.
An initial Windows fixture cleanup failure was traced to `sqlite3.Connection`'s
transaction context manager not closing the connection. The fixture now uses
`contextlib.closing`; the production source reader already closed explicitly.

Fresh subprocess tests independently verify identical CSV data/signatures across
two private workers, excluding runtime timing columns. They also verify source
bytes are unchanged. Tests cover seeded distribution, all RIASEC dimensions,
both real assessment modes, neutral ties, empty/duplicate canonical reports,
missing evidence/neutral recommendations, export structure, ordinary-database
rejection, source-only reads and unsafe report destination rejection. Existing
Phase 2C tests cover semantic/alias matching and saved roadmap regressions.

## Implementation and files

- `careercoach/simulation_settings.py`: private in-memory, offline, v2-only settings.
- `recommender/management/commands/simulate_profiles.py`: argument validation and
  private-process launcher; performs no ordinary ORM queries.
- `scripts/simulate_profiles.py`: worker, network guards, source-preservation checks,
  private database lifecycle and report orchestration.
- `recommender/simulation/catalog.py`: allowlisted read-only catalog/bank snapshot,
  fingerprints and guarded private install.
- `recommender/simulation/profiles.py`: seeded scenario allocation and real-item responses.
- `recommender/simulation/runner.py`: actual assessment lifecycle and repeated actual v2 calls.
- `recommender/simulation/assertions.py`: independent invariants and controlled monotonicity checks.
- `recommender/simulation/reports.py`: descriptive metrics and safe CSV/JSON/Markdown exports.
- `recommender/simulation/__init__.py`, `recommender/test_simulation.py`.
- `.gitignore`, `README.md`, `docs/synthetic-profile-evaluation.md`, this validation report.

Generated CSV/JSON/Markdown reports are local artifacts in ignored `reports/`.
The profile CSV has one row per student; assessment rows distinguish modes;
recommendation rows distinguish student, mode and rank. Output filenames retain
the requested `_100` suffix even for a different configurable count.

## Full 100-profile observation

Executed `python manage.py simulate_profiles --count 100 --mode both --seed 42`.
The process exited successfully. It evaluated **100 distinct profiles**, **200
assessments** (100 Quick + 100 Detailed), and **200 recommendation runs**, producing
**1,000 top-five rows**. Distinct exported response/skill/context records were
also checked: 100, excluding IDs/seeds. Scenario counts exactly matched the request.

All assertions passed, including 200 complete serialized-ranking repeats and
12 controlled monotonicity checks. The source catalog/bank fingerprints and entire
source database/WAL byte hashes were unchanged. No normal application account,
session, recommendation history, roadmap or progress row was mutated.

Catalog: 240 careers, 4,358 skills, 15,727 relationships, 28 enrichments, two aliases.
Bank: `careercoach-riasec-2026.1`, 36 active items. Catalog fingerprint:
`f6f50c9d253d0b1ae70f70cfa65ce9fe3598cd176b0f0f12ba1b57cbed9f4ff9`.
Engine: `careercoach-explainable-v2.0`; .45 interest/.40 skill/.15 background;
semantic proposals disabled. The actual worker timestamp was
2026-11-09T13:04:08.780599+00:00 (UTC).

| Measure | Observation |
| --- | --- |
| Distinct Holland Codes | 67 across 200 runs |
| Common codes | RIA 34; CRI 10; IRA 8; ISC 8; RAE 6; ACS 5; SRI 5 |
| Unique recommended careers | 151 of 240 in top-five lists |
| Ranking points | Min 27.1; max 100; mean 51.0302; median 48.5 |
| Same ordered top five, Quick vs Detailed | 88 of 100 profile pairs |
| Same Holland Code, Quick vs Detailed | 79 of 100 pairs |
| Mean top-five overlap | 90.8% |
| No overlap between modes | 6 profile pairs |
| Mean absolute dimension-score difference | 2.5346 points over 600 dimension comparisons |
| Largest dimension-score difference | 20.83 points |
| Equal dimension scores but different ordered rankings | 0 pairs |
| Runs with at least one confirmed canonical match | 62.5% (125/200) |
| Recommendation rows with a canonical match | 33.9% (339/1,000) |
| Runs with an unavailable scoring component | 33% (66/200) |
| Industry fallback usage | 100% of runs and recommendation rows |
| Broader unavailable evidence | 100% of runs, including unknown comparable proficiency |
| Structurally complete explanations | 100% of recommendation rows |
| Quick profiles sharing an ordered top five with another Quick profile | 35; 74 distinct sequences |
| Detailed profiles sharing an ordered top five with another Detailed profile | 31; 76 distinct sequences |

The full 67-code frequency distribution, per-mode frequencies, pair details,
top-one/top-five frequencies and configuration are in
`reports/evaluation_summary.json` and `reports/evaluation_summary.md`.
Frequent `RIA` codes partly reflect deliberate flat/tied scenarios and the
existing RIASEC tie order, not independent evidence of a dominant interest.

### Ten most frequent careers

These count appearances among five recommendations across **200 runs**, not
independent real students. Quick and Detailed are paired synthetic observations.

| Career | Top-five appearances |
| --- | ---: |
| art therapist | 42 |
| analytical chemist | 41 |
| architect | 41 |
| artistic director | 35 |
| biochemical engineer | 33 |
| circus artist | 28 |
| biochemist | 25 |
| bioinformatics scientist | 24 |
| circus arts teacher | 22 |
| advertising manager | 20 |

The most frequent **top-one** result was chemistry lecturer, 12/200 runs (6%).
The configured >25% top-one concentration warning did not trigger. Frequent
specialized titles are observations of this catalog and scorer, not evidence of
their suitability for Malaysian students.

### Diagnostics and tradeoffs

- **159/200 runs (79.5%)** contained at least one pair of tied unrounded top-five
  scores; **75/200 (37.5%)** had all five unrounded scores tied. Deterministic title
  ordering can therefore shape frequency tables. A distinct ordering is not always
  a substantive preference between occupations.
- **25 recommendation rows** reached 100 points with interest and education
  evidence but **no usable skill evidence**. Missing skill weight is redistributed
  (.75 interest/.25 education here). This is expected under the existing formula,
  not a verified-suitability claim. The engine was preserved; the evaluator warns.
- All interest matches used industry proxies. Missing occupation profiles and
  comparable proficiency scales remain important evidence limitations.
- Six Quick/Detailed pairs shared no top-five careers despite sharing item-level
  preference patterns. Additional Detailed responses can change means/ties and
  ordering. These cases need expert review; none had identical six-dimensional
  scores with unexplained different rankings.

Tie/high-score aggregate warnings were added by analyzing the **unchanged CSV
exports** after the completed run; no assessment or ranking was rescored. The
summary explicitly records this post-analysis. Future command runs calculate these
same diagnostics directly. Frequency and pair-comparison values were checked
against the original summary when regenerating the JSON/Markdown reports.

### Performance and outputs

The observed execution took **886.67 seconds** (about 14.8 minutes), including
repeat rankings and source-preservation checks, excluding final report writing.
Mean assessment lifecycle time was **0.0994 seconds**; mean first recommendation
computation **2.1638 seconds** (median 2.1321, max 3.1043). These are local observations
with some concurrent test activity, not an isolated production load benchmark.
Repeated ranking time is not mixed into the per-run first-call metric.

Verified exports: profile CSV 100 rows; assessment CSV 200 rows; recommendation
CSV 1,000 rows; summary JSON and Markdown. The recommendation CSV is about **50.8
MB** because it preserves structured opportunities/evidence for every row. All
generated outputs remain ignored; no large artifact is staged or pushed.

Before claiming improved accuracy, gather consented student relevance/clarity
feedback and independent university career-center judgments; review occupation
profiles, ambiguous aliases and title-tie effects; evaluate held-out representative
cohorts and subgroup coverage. Investigate the six zero-overlap pairs and the
100-point missing-skill cases before changing scoring assumptions or weights.
