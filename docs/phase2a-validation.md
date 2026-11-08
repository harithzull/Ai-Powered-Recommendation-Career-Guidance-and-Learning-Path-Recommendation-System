# Phase 2A validation and handoff

Date: 7 November 2026 (Asia/Kuala_Lumpur).
Environment: Windows, existing project .venv, Python 3.13.2, Django 6.0.10.
Base: latest merged main `ea4397e`; branch `phase2a/career-knowledge-base`.
Local main was fast-forwarded with explicit approval. No push, PR, merge of a PR,
or commit was performed for Phase 2A.

## Executed validation

| Check | Result |
| --- | --- |
| Phase 1 baseline `python manage.py test` | 98 passed before implementation |
| Final `python manage.py test` | **140 passed, 0 failed**, 14.104 seconds |
| `python manage.py check` | No issues |
| `python scripts/check_deploy.py` | No issues, none silenced |
| `python manage.py makemigrations --check --dry-run --settings=careercoach.test_settings` | No changes detected |
| `python manage.py migrate --check` | No pending migrations |
| `python manage.py audit_career_data --fail-on-errors` | No confirmed errors; warnings/unknowns retained |
| `python -m pip check` | No broken requirements |
| `git diff --check` | Passed |
| Workflow YAML | Parsed; read-only repository permissions; source audit added to existing checks |
| Scoring/assessment logic source comparison | No changes to scoring.py, recommendations.py, matching.py, embeddings.py, adaptive.py, or assessment models |

New tests use small CSV/table fixtures, isolated test databases, and mocked model
encoding. They cover audits, duplicates, CSV errors, references, aliases, source
metadata, URI conflicts, family relationships, full rollback, dry runs, idempotency,
manual enrichment preservation, user data preservation, canonical skill search, and
unchanged numerical recommendation results. The inherited offline runner prohibits
network connections. No live Groq calls or model downloads were needed.

The first fixture test run encountered Windows sandbox temporary-directory permissions
and outdated Phase 1 importer mocks. Tests were rerun outside the sandbox, and the old
tests were updated for the deliberately non-destructive importer. Final full-suite
results above were executed successfully; the initial failures are not concealed.

## Actual datasets and audit

| Dataset | Records | Duplicate normalized labels/pairs | Invalid references |
| --- | ---: | ---: | ---: |
| Careers | 240 | 0 | n/a |
| Skills | 4,358 | 0 | n/a |
| Career-skill relationships | 15,727 | 0 | 0 |

Final CSV finding instances: **0 error, 91 review, 0 optional, 4,845 unknown**.
Review includes 10 classification candidates, 74 short skill descriptions, two
uppercase labels, two whitespace issues, and three title-overlap pairs. Unknowns
include all 4,598 concept identifiers, 240 work-environment labels, one skill category,
four relationship metadata gaps, and two deterministic legacy estimate patterns.
The source version and transformation history remain unknown. Short descriptions,
capitalization and title overlap are review heuristics, not confirmed invalid data.

Database after curation: 240 careers, 4,358 skills, 15,727 relationships,
16 families, 28 career enrichments, and two skill aliases. There are **212 explicitly
unclassified careers**. All authoritative relationship importance values remain
null and all original source relation types/proficiencies unknown. Source quality
status remains needs-review even where a separate custom family has been reviewed.

See reports/phase2a-csv-audit.json and reports/phase2a-database-audit.json for
identifiers, counts and remediation. The initial audit is retained in the before
report; its punctuation-only candidate C++/C# was corrected in the final heuristic.

## Full-dataset import and preservation evidence

1. Created ignored SQLite backup `db.sqlite3.phase2a-backup-20261107115847` (UTC timestamp).
2. Applied additive migration `recommender.0005_knowledge_base_source_and_enrichment`.
3. Dry-ran all **20,325** source records and verified rollback against fingerprints
   of every original application column.
4. Committed a source-only import: **0 inserted, 20,325 updated, 0 rejected**.
5. Repeated import: **0 inserted, 0 updated, 20,325 skipped, 0 rejected**.
6. Added the separate enrichment examples: 16 families, 28 family mappings, two aliases,
   one local-title example. No pre-existing enrichment was overwritten.
7. Verified every original application row/field value stayed identical, except the
   expected invalidation of derived recommendation-cache rows. All original career,
   skill, relationship, assessment and roadmap IDs remain intact.
8. Verified all CSVs, skill_names.json and skill_vectors.npy are byte-for-byte unchanged.

The local database retained **19 assessment responses, three saved roadmaps, and 15
roadmap-progress records**. No user data was deleted. No new occupation, canonical
skill, or relationship dataset was substituted. No embeddings need rebuilding.

Import plans/results and preservation evidence are in reports/phase2a-import-*.json
and reports/phase2a-preservation.json. These reports contain counts/hashes and catalog
identifiers, not account profiles, API credentials, or session data.

## Limitations and next work

- No remote CI success is claimed. Before this task the latest main workflow
  (run 42329072019) already reported failure. There was no separate local CI-fix
  commit to include in the base. The GitHub connector did not expose job logs.
  Phase 2A CI changes have not run remotely because nothing has been pushed.
- Local validation was Windows/Python 3.13. The inherited Linux/Python 3.12/3.13
  workflow remains to be verified after approved push. No infrastructure was deployed.
- Unknown original ESCO URIs/version, unverified source transformations, 74 short
  descriptions, the unknown skill category, and ambiguous classifications need review.
- The import command is an operator-run single-writer pipeline, not a multi-writer
  ingestion service. Existing canonical/display fields do not automatically refresh
  when source snapshots change; a later reviewed canonical update is deliberate.
- Alias recognition supplements search; it does not rewrite stored user skill names,
  alter direct encoder inputs, or change scoring. Related terms are never exact aliases.
- No Malaysian salaries, demand, vacancies, eligibility, licensing claims, or fabricated
  RIASEC profiles were added. Market quality and recommendation validity were not measured.

Next, Phase 2B should review family/occupation coverage, recover source evidence,
and develop validated assessment versions with an explicit expert-review process.
Keep the reserved occupation RIASEC profiles empty until evidence supports them.
Phase 2C can then evaluate reviewed aliases and improved occupation profiles against
ranking-quality baselines before changing the current scoring algorithm.

Architecture/provenance/manual-review instructions: phase2a-architecture.md and
phase2a-knowledge-base.md. README.md includes the operational commands.

## Files created or modified

- `.github/workflows/tests.yml`
- `README.md`
- `assessment/views.py`
- `docs/phase2a-architecture.md`
- `docs/phase2a-knowledge-base.md`
- `docs/phase2a-validation.md`
- `recommender/admin.py`
- `recommender/aliases.py`
- `recommender/curation.py`
- `recommender/data_audit.py`
- `recommender/data_import.py`
- `recommender/datasets.py`
- `recommender/knowledge_audit.py`
- `recommender/knowledge_validation.py`
- `recommender/management/commands/audit_career_data.py`
- `recommender/management/commands/import_data.py`
- `recommender/management/commands/seed_career_enrichment.py`
- `recommender/migrations/0005_knowledge_base_source_and_enrichment.py`
- `recommender/models.py`
- `recommender/normalization.py`
- `recommender/test_knowledge_base.py`
- `recommender/tests.py`
- `reports/phase2a-csv-audit-before.json`
- `reports/phase2a-csv-audit.json`
- `reports/phase2a-database-audit.json`
- `reports/phase2a-import-dry-run.json`
- `reports/phase2a-import-first.json`
- `reports/phase2a-import-repeat.json`
- `reports/phase2a-preservation.json`
- `templates/base.html`
