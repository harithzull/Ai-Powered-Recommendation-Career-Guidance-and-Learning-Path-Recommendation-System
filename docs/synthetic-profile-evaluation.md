# Synthetic profile evaluation

This evaluates software correctness, reproducibility, evidence coverage, stability
and concentration. It cannot establish psychometric validity, fairness,
employability or career recommendation accuracy.

## Run

From the existing Windows virtual environment and repository root:

```powershell
python manage.py simulate_profiles --count 100 --mode both --seed 42
```

For an explicit source, custom output directory or a smaller single-mode run:

```powershell
.venv\Scripts\python.exe -B manage.py simulate_profiles --count 10 --mode quick --seed 42 --source-db db.sqlite3 --output-dir .cache/simulation-review
```

The source must be a migrated SQLite file with the real career/skill catalog,
source metadata and one active assessment bank. A missing/empty/incompatible
source fails; the runner never substitutes toy careers or silently seeds an empty
catalog. Non-SQLite deployments must provide a suitable SQLite catalog/bank snapshot
using `--source-db`. Exporting from other databases is outside this command's scope.
The default source is the configured SQLite filename. With test settings or an
in-memory default, an explicit `--source-db` is required.

Counts from 1 to 10,000 and modes `quick`, `detailed`, `both` are supported. Large
counts are deliberately expensive: every completed assessment runs the unchanged
v2 engine twice. The first computation is timed; the repeat verifies the complete
serialized output, including evidence, explanations and signature.

## Isolation and safety

The management command launches a fresh process with
`careercoach.simulation_settings`. That process uses SQLite `:memory:`, test-only
credentials, offline configuration, v2 exact matching and disabled semantics. It
never loads `.env`. The launcher can read normal settings to find the source path,
but performs no ORM database queries, migrations or synthetic writes itself.

Only catalog tables (`CareerFamily`, `Career`, `Skill`, `CareerSkill`,
`CareerEnrichment`, `SkillAlias`) and the active question bank/items are read from
the source using a separate SQLite **mode=ro**, **query_only** connection and one
read transaction. No application accounts, passwords, sessions, history, cached
recommendations, assessments or roadmaps are copied. Source metadata, canonical
IDs, missing evidence and unknown requirements remain unchanged.

Migrations and all synthetic users/sessions/answers exist only in the worker's
in-memory database. Mutating helpers reject ordinary settings and file-backed
destinations. Existing users in the private database cause an error rather than
being deleted. Connections are closed on exit; process exit destroys the private
database even if an assertion fails. There is no temporary synthetic database file.

Socket connections, connect_ex, create_connection and DNS lookup are blocked.
No Groq client or embedding model is needed. Unexpected external access fails the
run instead of silently using a live service. The production engine is not mocked.

The source catalog/bank fingerprint and database/WAL byte hashes are compared
before and after execution. A concurrent source write aborts export, even if made
by a different application process. Close development servers/admin editors while
running if necessary. Byte hashes are checked locally; private source rows are
never exported. Hash comparisons do not establish that unrelated processes made
no changes to external services.

Report destinations are checked before work and before writing. A report file
cannot alias the source database (including a hard link), and symbolic-link
report files are rejected. Existing ordinary report files can be regenerated.

## Profiles and assessment execution

Seed 42 generates the following distribution for 100 profiles:

| Scenario | Count | Construction |
| --- | ---: | --- |
| Dominant | 12 | Two per RIASEC dimension; one high dimension |
| Mixed | 18 | Two/three higher interests, some item variation |
| Neutral/balanced | 10 | Equal preferences, deliberately exercising ties |
| Extreme responses | 10 | All-low/all-high and alternating dimension extremes |
| Varied skills/background | 20 | Varying canonical reports, education and experience |
| Randomized | 30 | Seeded preference patterns and per-item variation |

Other counts use proportional allocation with deterministic largest-remainder
rounding. All six types are explicitly represented in the 100-profile dominant
group; very small counts cannot guarantee every scenario/type.

Each profile has a unique ID, its own deterministic seed, responses keyed by
actual active item codes, and optional canonical reports/context. Canonical names
over the existing skill input's 100-character limit are excluded from selection.
Some free-text reports repeat a canonical report to exercise deduplication.
There is no assumed association between a Holland Code and a particular career.

Per-item ratings are shared across modes. Quick selects the real three core
items per dimension; Detailed selects all six. The real `start_session`,
`save_answer`, `finalize_session` and `score_answers` services are reused. Detailed
may have different means/codes because it includes additional item responses;
equal results are not required. Ties follow the existing RIASEC ordering.

The worker uses a fixed synthetic session clock and deterministic UUIDs only for
identity creation. This stabilizes input signatures across repeated evaluations
with the same inputs/catalog/configuration. It does not change selection, scoring,
ranking or explanation logic. The actual evaluation timestamp is recorded in the
summary separately. Record runtime/code revisions when comparing environments;
the catalog and bank hashes plus engine/generator versions identify their inputs.

Assertions cover coverage, score bounds, ties, deterministic scores/full ranking
outputs, career identity/uniqueness, descending points, finite components,
effective-weight sums, neutral missing evidence, canonical match deduplication,
unsupported proficiency claims and semantic exclusion. Twelve additional controlled
checks raise one dimension's ratings in each mode to test monotonicity without
duplicating the production score formula. Existing Phase 2C tests cover alias,
semantic threshold and duplicate-invariance behavior as well.

## Reports

Default exports are generated under ignored `reports/`:

- `synthetic_profiles_100.csv`: **one row per profile**, including all actual-bank
  item responses, reports and context.
- `assessment_results_100.csv`: **one row per profile/mode** (200 for the default),
  six scores, code, counts, ties, exact selected responses and duration.
- `recommendation_results_100.csv`: **one row per career/rank/profile/mode**
  (1,000 for the default five candidates), with component scores, configured and
  effective weights, method/provenance, matches, opportunities, uncertainty,
  explanations, version, signature and duration.
- `evaluation_summary.json`: all observed distributions, pair comparisons,
  evidence percentages, timing, catalog/bank fingerprints and configuration.
- `evaluation_summary.md`: readable results and diagnostic warnings.

Filenames retain the requested `_100` suffix for custom counts; the summary and
row identities are authoritative. These are UTF-8 CSVs. Structured cells contain
JSON; read them with `json.loads`. Large relation lists can exceed a CSV reader's
default field limit; increase `csv.field_size_limit` if needed. Text cells starting
with spreadsheet formula characters are prefixed with an apostrophe. Preserve
original machine exports when opening them in spreadsheet software.

Evidence metrics distinguish runs versus recommendation rows, any matched
canonical identity versus a usable scoring component, and unavailable scoring
components versus broader missing provenance/proficiency evidence. "Confirmed"
means canonical identity matched a student report, not independently verified
possession or proficiency. The top-ten table counts appearances across both modes'
top-five lists; top-one frequencies are reported separately in JSON.

Identical recommendation groups are counted **within each mode across profiles**,
so a student's matching Quick/Detailed rankings do not inflate that measure.
Pair analysis reports ordered equality, overlap fraction, Jaccard, code equality
and signed dimension-score differences. Equal scores with different rankings are
flagged for investigation; legitimate item-induced differences are not failures.

Diagnostic thresholds (not validated quality cutoffs) flag top-one share over
25%, fewer than ten unique recommended careers where the source supports ten,
and over half the profiles sharing a top-five sequence. All industry fallback
usage is disclosed. Warnings never automatically label a career incorrect.
The runner also flags ties in over half of runs and any 100-point rows lacking
usable skill evidence. Ties use unrounded contribution totals, not merely equal
one-decimal display values. These diagnostics expose title-ordering and missing-
evidence effects without claiming the algorithm is incorrect.

## Test and review

```powershell
python manage.py test recommender.test_simulation
python manage.py test
python manage.py check
python manage.py makemigrations --check --dry-run
```

See [executed validation and observed findings](synthetic-profile-validation.md).
Future evaluation needs consented representative student feedback, independent
career-center relevance judgments, reviewed occupation profiles and held-out
analysis before changing weights. Synthetic correctness cannot replace this work.
