# Phase 3B · Resume intelligence

Open a successfully extracted resume in **My resumes** and select **Analyze and review resume**. The analysis reads the extracted text and installed CareerCoach skill catalog locally. It proposes skills, education, work experience, and projects for owner review.

## Architecture and data

| Component | Responsibility |
| --- | --- |
| `resume/intelligence/schema.py` | Typed suggestions, sections, evidence spans, extraction contract, and budgets |
| `sections.py`, `records.py` | Recognize headings and extract education, work, and project entries |
| `matching.py`, `skills.py` | Catalog phrase lookup, mention context, deduplication, and provenance |
| `pipeline.py` | Deterministic offline implementation of the extraction contract |
| `resume/services/intelligence.py` | Publish revisions and update owner reviews transactionally |
| `resume/analysis_views.py`, `templates/resume/analysis*.html` | Private HTML forms for analysis, history, evidence, and correction |
| `resume/migrations/0002_resume_analysis.py` | Add analysis and suggestion tables with constraints |

`ResumeAnalysis` belongs to a `ResumeDocument` and records a per-document revision, original file checksum, extracted-text SHA-256, extractor version, timestamp, detected sections, and notices. Each `ResumeSuggestion` stores its category, method, evidence state, extracted fields, evidence, and optional catalog identity. It stores the owner’s correction and review state separately. Both tables derive ownership from the source resume. Deleting the document deletes its analysis history and reviews.

The extractor contract takes the exact extracted text and returns typed local results. A future extractor would need to preserve evidence offsets against that same source. Phase 3B uses the deterministic implementation throughout.

## Extraction and evidence

- Headings match a whole line or a known label followed by a colon. English and Malay variants include *Kemahiran Teknikal*, *Latihan Industri*, and *Projek Tahun Akhir*. Unclassified text retains its source positions and the results page flags missing headings.
- Skill lookup uses token boundaries, longest phrases, case and whitespace normalization, and punctuation-aware matching for terms such as `C++`, `C#`, and `Node.js`. Explicit lists and some clear claims can yield unmatched suggestions. Email addresses and ordinary URLs are excluded. Negations, job requirements, and desired roles are excluded from positive suggestions. Learning and exposure language is flagged for clarification.
- Education extracts recognizable qualifications and available fields. A bare year is a stated date. Graduation, expected graduation, and current study require corresponding language. A recognizable qualification without an education heading can be marked as inferred structure.
- Work history recognizes entries with role headings, stated employers, date ranges, employment types, and responsibilities. `Present` or `kini` can identify a current role. Dates retain their stated granularity. Job titles carry no seniority or proficiency claims. Durations are omitted.
- Projects use dedicated sections and can capture a title, description, contributions, technologies, and a URL. Academic or personal classification comes from the heading. URLs are displayed as text.

Evidence offsets are zero-based, half-open character ranges in the Phase 3A extracted text. Each excerpt equals `text[start:end]`. Skill evidence includes nearby text and its match method. Repeated names and aliases can contribute evidence to the same suggestion. Structured suggestions retain the excerpts used to extract their fields.

The states **explicit**, **inferred**, **ambiguous**, and **unsupported** describe the evidence. The review state records the owner’s decision separately. A mentioned skill carries no proficiency rating.

## ESCO and catalog mapping

1. Resolve a unique canonical name, ESCO URI, or cataloged ESCO UUID.
2. Use an existing exact alias with reviewed status and recorded evidence.
3. Use an unambiguous punctuation variation when a reviewed skill explicitly records it in `source_metadata.resume_variations` with a label and review evidence. Phase 3B adds no catalog entries.
4. Keep unmatched mentions for review. Label collisions and unverified or related aliases can show candidate identities without selecting one.

A resolved row snapshots the local skill ID, name, ESCO URI when present, source taxonomy, and available export provenance. An ESCO-derived record may lack an authoritative URI. Catalog renames and deletions leave historical snapshots readable. Foreign keys to deleted skills clear automatically.

With the shipped catalog and reviewed aliases installed, `PostgreSQL` maps directly and `Postgres` maps through its verified alias. `Django` can appear as an unmatched suggestion. In “Developed a web application using Python, Django, PostgreSQL and Git,” the suggestions are grounded in those four terms. “No experience with PostgreSQL” yields unsupported context without a positive mapping.

## Review workflow

1. Open **Analyze and review resume** from the resume detail page and submit **Analyze resume**. An identical initial request reuses the existing revision.
2. Open the evidence for each suggestion and choose **Confirm extraction**, **Reject**, or **Correct**. An ambiguous skill mapping requires correction. Use a catalog ID, a unique name, or an ESCO URI to choose an identity. Leave the catalog field blank to keep user-supplied wording alone.
3. Open **Run a new analysis** and confirm the new revision. Prior decisions remain visible in **Analysis history**. Suggestions in the new revision start pending.
4. Analyses with a changed source remain available as read-only history. The form rejects stale review versions and stale rerun submissions.

## Private routes

Paths are relative to `/resumes/`. All queries scope both the document and nested resources to the signed-in owner.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `<resume>/analysis/` | Latest analysis or start page |
| POST | `<resume>/analysis/run/` | Analyze the resume or create a new revision |
| GET | `<resume>/analysis/<analysis>/` | Review a revision and its evidence |
| GET | `<resume>/analysis/<analysis>/<suggestion>/correct/` | Open the correction form |
| POST | `<resume>/analysis/<analysis>/<suggestion>/review/` | Confirm, reject, or correct |

State changes require CSRF validation. Responses use `Cache-Control: private, no-store`, a no-referrer policy, and Phase 3A’s content security policy. Templates escape the evidence and user corrections. There is no analysis admin registration, evidence export, LLM integration, or network dependency. Expected processing failures return generic messages.

The existing shared rate counters and per-user work lease cover analysis and review. `RESUME_ANALYSES_PER_DAY` defaults to 10 and `RESUME_REVIEWS_PER_MINUTE` defaults to 30. Limits are 200,000 extracted characters, 120 sections, 2,000 characters per line for skill scanning, 240 characters per structured evidence line, 30,000 catalog and alias records, 60 skill suggestions, 12 entries per structured category, and 20 revisions per resume. Each skill keeps up to six evidence occurrences. A five-second cooperative budget limits extraction work. Database wait time is governed by the deployment separately.

## Run locally

Activate the project virtual environment and configure the local `.env`. Set up the catalog on a fresh local database and start Django.

```powershell
python manage.py migrate
python manage.py import_data
python manage.py seed_career_enrichment
python manage.py runserver
```

Sign in, upload a PDF or DOCX with selectable text, and wait for extraction. Open the resume details, analyze the text, review a suggestion, and check that a rerun preserves the first revision and its review.

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test resume.test_intelligence
python manage.py test
python scripts/evaluate_resume_intelligence.py
```

## Synthetic evaluation

The 30 manually annotated resumes include 10 IT, 5 engineering, 5 business and finance, 5 mixed, and 5 difficult fixtures. The script loads the shipped export and the two reviewed example aliases into an in-memory SQLite database and blocks network connections. It uses no application resume records.

Skill precision and recall compare unique normalized surface mentions per fixture with explicit support. Canonical precision also requires the annotated catalog identity. Section coverage compares annotated and detected section types within each fixture. Structured entry coverage compares the annotated primary labels. Runtime includes catalog initialization and extraction for every resume. It excludes the one-time catalog import.

| Measure | Observed result |
| --- | --- |
| Exact skill precision and recall | 79/79 each (100%) |
| Canonical mapping precision | 57/57 (100%) |
| Section detection coverage | 71/71 (100%) |
| Structured entries recovered | 35/36 |
| Unmatched suggestions | 22 |
| Ambiguous catalog mappings | 0 |
| Skill suggestions needing contextual clarification | 2 |
| Runtime per resume on the local Windows run | 49.66 ms median, 87.93 ms maximum |

The final run produced zero skill false positives or false negatives on these fixtures. An earlier run suggested “a postgresqlish parser” and missed “Git” after “Used” in work-history prose. The final rules handle those fixture cases. The remaining structured miss was “Part-time Tutor” under a profile heading. Ambiguous catalog collisions are covered separately in unit tests. These results describe development fixtures and provide no estimate of real-world accuracy.

## Limitations and Phase 3C

Reading order in columns and tables can separate headings from their entries. Spelling variants, indirect negations, unstated headings, and unknown tools outside clear skill claims can be missed. The catalog controls which identities are available. Local review and the original text remain important for these cases.

Phase 3C can build on the owner-scoped analysis, review states, corrected catalog links, and source checksums. It would need to select the current-source revision and define how confirmed evidence affects recommendations. Phase 3B does not write assessment ratings, profile skills, recommendation history, or scores.
