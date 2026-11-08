# Phase 2A: Career & Skills Knowledge Base 2.0

## Architecture

The dependency analysis is in [phase2a-architecture.md](phase2a-architecture.md).
The original application, primary keys, URL paths, assessment behavior, RIASEC
questions/adaptive logic, scoring formulas, matching calculations, vectors, and saved
user records are preserved. The visible change is a small ESCO attribution footer.
Skill search also recognizes reviewed exact aliases and returns canonical names.

### Source layer

Career and Skill now record `source_taxonomy` (`esco`, `careercoach`, `unknown`),
optional unique `esco_uri`, exported source label and description, `source_metadata`,
and a quality review status. Source fields describe the supplied legacy export,
**not a verified untouched original ESCO release**. Imports store file SHA-256,
CSV physical record-ending line, a lossless exported-row snapshot, extraction version
(null unless evidenced), and the owner's confirmation of ESCO derivation.

CareerSkill retains every existing compatibility field. Separate
`source_relation_type`, nullable `source_importance`, and `source_proficiency`
support authoritative metadata without treating FYP estimates as ESCO facts.
All existing authoritative relation types/proficiencies are blank and source
importance is null. Existing `importance`, `required_level`, `skill_type`, and
`is_core` values remain unchanged for the current engine.

On a **new** relationship with missing legacy numeric data, `importance=0` is the
existing compatibility sentinel (the current matcher already uses a minimum weight
of one), not an invented importance estimate. Its source importance remains null,
source proficiency remains blank, and the raw missing field is preserved. Unknown
core status maps to the existing false default, not evidence that ESCO says optional.
Such new incomplete relationships require review before a future scoring redesign.

### Enrichment layer

- `CareerFamily`: editable slug, name, description. Sixteen initial categories cover
  the dataset, including a Social & Community Services family. Categories are data,
  not hard-coded industry-to-family rules. A null family explicitly means unclassified.
- `CareerEnrichment`: one-to-one career extension with family, specialization,
  locale-specific titles, student explanation, nullable entry-level suitability,
  reserved nullable RIASEC profile, curation status, evidence and rationale.
- `SkillAlias`: normalized globally unique alias key, target canonical skill,
  exact/related relation kind, review status and evidence. Exact reviewed aliases are
  searchable; related terms are not silently treated as equivalent concepts.

The example seed contains 28 explicit family decisions reviewed against the actual
exported descriptions. It does not classify by keywords or copy legacy industries.
For example, hardware/paint selling receives a Sales & Marketing enrichment while
its original Creative & Design compatibility industry stays untouched. Other
ambiguous occupations remain unclassified until reviewed. Source quality status
remains needs-review independently of a reviewed custom family assignment.

No entry-level eligibility, occupation RIASEC values, salaries, vacancies, demand,
professional licensing, or graduate-employment figures are seeded.

## Confirmed provenance and audit findings

The owner confirmed ESCO derivation. The files contain 240 careers, 4,358 skills,
and 15,727 relationships. None of the 4,598 career/skill concepts has an original URI
or an identified source version. Do not infer IDs from titles or use the current
website's version number as the version of this export.

Confirmed structural observations:

- The occupation export is a selected subset, with exactly 20 records in each of
  12 application industry groups. It is not a complete ESCO extraction. The selection
  procedure is unknown; the balancing pattern alone does not establish its method.
- All 240 work-environment values are `hybrid`; the origin of this label is unknown.
- Every summary is a prefix of its description: 165 are shortened and 75 equal the
  description. Whether the descriptions themselves were shortened from ESCO is unknown.
- Categories contain 2,950 skill/competence concepts, 1,407 knowledge concepts, and
  one unknown. Their labels align with ESCO terminology, but the original transformation
  history cannot be established. JavaScript and PostgreSQL remain knowledge concepts;
  being a technology name does not make an ESCO knowledge concept a practical skill.
- 9,539 relationships are marked core with weight 5/intermediate; 6,188 are non-core
  with weight 2/basic. This deterministic pattern is a legacy estimate, not evidence
  of authoritative ESCO numeric weights or proficiency levels. It is unknown whether
  core status preserves ESCO essential/optional relations or whether links were edited.
- The short skill `implement cloud security and compliance` has an unknown category;
  its four linked relationships also lack skill-type metadata. Do not guess a category.
- No duplicate titles/names (including case/whitespace-normalized duplicates), duplicate
  relationship pairs, dangling CSV references, or unlinked concepts were found.
- Review candidates include 10 questionable industry assignments, 74 descriptions
  shorter than eight words, two uppercase skill labels, and one whitespace issue in
  each concept table. Three title-overlap candidates are legitimate-looking distinct
  occupations, not automatic merge recommendations. These are heuristics, not verdicts.
- The original punctuation heuristic flagged C++ versus C#. The final audit preserves
  significant punctuation and correctly keeps C, C++, C#, and .NET separate.

The final CSV report has **0 confirmed error instances, 91 review instances, and
4,845 unknown-information instances**. Counts are finding instances, not distinct
affected records. The final database audit records 212 optionally unclassified
careers and unknown URI/version information; source relationship unknowns are also
reported in its statistics. Unresolved warnings are deliberately retained.

Machine-readable reports in `reports/phase2a-*.json` include file fingerprints,
row identifiers, categories, remediation actions, and examples. The initial report
is preserved separately from the final improved heuristic report.

## Official ESCO attribution

The [European Commission's ESCO FAQ](https://esco.ec.europa.eu/en/about-esco/faq?page=1)
permits reuse, including in applications, under Commission Decision 2011/833/EU.
It requires acknowledging the Commission's ESCO classification and clearly identifying
adaptations. The application footer supplies the service acknowledgment and says that
CareerCoach uses an adapted subset with its own classifications and enrichment.
Keep this attribution when redistributing the dataset or publishing the service.

References reviewed on 7 November 2026:

- [ESCO FAQ: licensing, modifications, concepts, and relationships](https://esco.ec.europa.eu/en/about-esco/faq?page=1).
- [Commission Decision 2011/833/EU](https://eur-lex.europa.eu/eli/dec/2011/833/oj/eng).
- [Official ESCO occupations description](https://esco.ec.europa.eu/en/classification/occupation-main).

No new ESCO release was downloaded or substituted. The source URIs and extraction
version remain unknown. The `industry`, `summary`, `work_environment`, `importance`,
and `required_level` columns are treated as legacy application/export information;
their original generation scripts are unavailable and their authorship is not inferred.

## Malaysian localization examples

`localized_titles` accepts locale-to-title-list mappings, e.g. `en-MY`. Lists are
validated for nonempty labels and normalized duplicates. The seed adds one small
example: Software Developer and Application Developer, listed in the Malaysian
[DOSM/ILMIA MyJobProfile software-developers group](https://myjobprofile.dosm.gov.my/bda-myjobprofile/job/2512/software-developers).
This is a reviewed local-title example, not a formal one-to-one MASCO/ESCO crosswalk
or a claim that every specialization is interchangeable. No market statistics from
the page are imported. Malay translations are left unfilled until properly reviewed.

## Running audits

```powershell
python manage.py audit_career_data
python manage.py audit_career_data --format json --output reports/career_data_audit.json
python manage.py audit_career_data --database --format json --output reports/database_audit.json
python manage.py audit_career_data --max-examples 0 --format json --output reports/full_audit.json
python manage.py audit_career_data --fail-on-errors
```

CSV audit is the default. `--database` checks persisted source/enrichment coverage,
ambiguous canonical names, relationship integrity, model validation and alias conflicts.
`--max-examples 0` includes all affected identifiers rather than the default 20 examples
per issue. Errors are structural/validation violations; review findings are hypotheses;
optional findings are missing curation; unknowns are unavailable source facts.
Neither audit changes records. File output only writes the explicitly requested report.

## Safe importing and refreshing sources

Back up the database, then:

```powershell
python manage.py migrate
python manage.py import_data --dry-run --format json --output reports/import_plan.json
python manage.py import_data --format json --output reports/import_result.json
python manage.py import_data --format json --output reports/import_repeat.json
```

The existing filenames and required columns remain supported. `--data-dir PATH`
uses a different explicitly selected bundle in the same interchange format; importing
a complete official ESCO distribution requires a separate, reviewed adapter and approval.
Optional `esco_uri`, `source_relation_type`, `source_importance`, and
`source_proficiency` columns carry supplied evidence; the importer does not infer them.
Only pass `--source-version` if the extraction version is known and evidenced.

Matching strategy:

1. Prefer a supplied unique ESCO URI. Reject URI/label conflicts and duplicate URIs.
2. Without a URI match, use a unique normalized source/display label: Unicode NFKC,
   case folding and collapsed whitespace, retaining significant punctuation.
3. Reject ambiguous existing matches and duplicate normalized input labels. Do not
   fuzzy-match, rename canonical labels, merge concepts, or prune absent records.
4. Update existing source snapshots only. Preserve canonical/display/scoring fields
   and every CareerEnrichment and SkillAlias row. A CareerCoach-curated concept cannot
   silently be claimed as ESCO just because its title matches.
5. Insert truly new records with supplied legacy compatibility fields. Supplied source
   fields remain distinct. Source fields never become custom enrichment implicitly.
6. Run the entire bundle in one transaction. Dry runs perform the same validations
   and writes then roll back, including derived cache invalidation. Run imports with
   a single catalog writer; this is an operator command, not a concurrent ingestion API.

Reports distinguish inserted, updated, skipped and rejected records. Any validation
or database failure rolls back the complete import. Absent authoritative metadata
is unknown, not guessed. `--replace-existing` is rejected. Actual repeated import
of this dataset skipped all 20,325 records with zero inserts or updates.

Source refresh does not silently change canonical embedding inputs, UI labels, or
ranking inputs. Review divergences between `source_description` and canonical
`description` before a future explicit canonical update. Rebuild embeddings only
after changing canonical skill names/descriptions or adding canonical skills, then
restart workers and invalidate caches. Pure aliases/enrichment do not require rebuilding.
The bundled vectors and all three CSVs remained unchanged in Phase 2A.

## Curation and aliases

Use Django admin with existing staff permissions:

- Add a Career with its display title and explicit source taxonomy. Enter evidence
  and source URI only when verified. Use a CareerEnrichment for custom explanations,
  family, specializations and local labels; do not replace raw source descriptions.
- Add a Skill with its canonical name/description/category. Preserve knowledge versus
  skill/competence distinctions. Record original metadata separately, and rebuild
  vectors after changing canonical embedding inputs or adding a new canonical skill.
- Add SkillAlias entries for evidenced abbreviations/spellings. Set `exact` only for
  equivalence; use `related` for broader concepts, and leave unreviewed suggestions
  pending. Exact reviewed aliases require evidence, cannot shadow any canonical
  concept, and cannot duplicate another normalized alias.
- Review records with the source `quality_status` filter and enrichment `review_status`
  filter. A reviewed custom family does not verify the original ESCO record.

```powershell
python manage.py seed_career_enrichment --dry-run
python manage.py seed_career_enrichment
```

The example seed only creates missing records and never overwrites manual curation.
JS and Postgres aliases cite [MDN](https://developer.mozilla.org/en-US/docs/Web/JavaScript)
and the [PostgreSQL FAQ](https://wiki.postgresql.org/wiki/FAQ). Canonical names are
unchanged. `resolve_skill_name()` supports exact reviewed alias lookup, while search
returns canonical names. Related terms never become exact aliases. Past user skill
selections and direct free-text encoder inputs are intentionally not rewritten;
applying normalization there would alter existing ranking and belongs to Phase 2C.

## Later phases

- **2B — RIASEC Assessment 2.0:** use reviewed family coverage to assess representation
  gaps and curate evidence-backed occupation profiles. Keep expert review, assessment
  validity and versioning separate from these legacy industry labels. The reserved
  RIASEC profile stays null; this phase does not generate profiles or edit questions.
- **2C — Recommendation Engine 2.0:** deliberately evaluate reviewed aliases, evidence-backed
  importance/proficiency, canonical source refreshes and career-specific RIASEC profiles;
  compare ranking quality before replacing current compatibility fields or weights.
- **3 — Resume Intelligence:** link extracted terms to canonical skills/aliases with
  confidence and provenance, preserving source terms and treating knowledge separately.
- **5 — Malaysian Job Market Intelligence:** attach verified local-source job-market
  observations to stable internal concepts and locale titles, without overwriting ESCO.
  Add a dedicated observation model only when actual timestamped, licensed data exists.

## Verification and limitations

See [phase2a-validation.md](phase2a-validation.md) for executed tests, data preservation,
import idempotency and changed files. Unknown identifiers/version/transformation history,
short descriptions, and ambiguous classifications remain review work. No broader
market representativeness, live AI quality, new source release equivalence, production
deployment, or remote CI success is claimed.
