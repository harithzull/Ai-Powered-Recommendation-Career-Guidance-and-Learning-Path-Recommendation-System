# CareerCoach

Django career guidance with versioned, balanced RIASEC assessment, semantic career recommendations,
skill gaps, personalised roadmaps, progress tracking, and an optional Groq chatbot.

## Local setup (Windows PowerShell)

Use Python 3.12 or 3.13. CI covers both; the local Phase 1 checks use Python 3.13.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
```

`requirements.txt` pins direct dependencies; `requirements.lock` pins the resolved
runtime dependencies. CI installs CPU-only PyTorch before the lock to avoid downloading
CUDA libraries on Linux. Revalidate the lock on your deployment OS when updating it.

If `.env` does not already exist:

```powershell
Copy-Item .env.example .env
```

Generate a new secret, then put it in the ignored `.env` as `DJANGO_SECRET_KEY`:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Use `DJANGO_DEBUG=true` and local hosts for development. Keep `GROQ_API_KEY` blank to
disable external AI; rule-based roadmaps remain available. To enable AI, set your key
in `.env`, never in source. Process environment values override `.env` values. Set
`DJANGO_READ_DOT_ENV=false` to disable file loading entirely.

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Visit http://127.0.0.1:8000/. Back up an existing database before applying migrations.
The new completion migration marks existing responses with both answers and skill
ratings complete. Users who previously submitted zero skills may need to resubmit
the skills step once; future empty selections are explicitly supported.

## Recommendation data and model

The repository includes the CSV catalog and a 4,358-row, 384-dimension skill-vector
store in `data/`. On a new database, import the catalog:

```powershell
python manage.py import_data
```

For local development, the first nonempty skill encoding downloads
`all-MiniLM-L6-v2`. Production defaults to local model files only. Provision the
model during a trusted build, set `EMBEDDING_MODEL_PATH` to the resulting directory,
and keep it consistent with the vectors. Rebuilding vectors also requires the model:

```powershell
python manage.py build_skill_vectors
```

Phase 2A imports are atomic, repeatable upserts that preserve existing IDs, scoring
fields, curated enrichment, assessments, roadmaps, and progress. Nothing absent from
a file is deleted. The old destructive `--replace-existing` option is rejected.

```powershell
python manage.py audit_career_data
python manage.py audit_career_data --format json --output reports/career_data_audit.json
python manage.py import_data --dry-run
python manage.py import_data
python manage.py seed_career_enrichment --dry-run
python manage.py seed_career_enrichment
python manage.py audit_career_data --database
```

Existing rows receive source snapshots/provenance; their canonical/display/scoring
fields are not overwritten. New rows use incoming legacy fields for compatibility.
Changed imports invalidate derived recommendation caches. Canonical skill additions
require new embeddings; alias-only changes do not. No embeddings were rebuilt in
Phase 2A. Admin catalog edits still invalidate recommendations. Direct database/bulk
changes require explicit invalidation; restart workers after replacing vector files.

See [the knowledge-base guide](docs/phase2a-knowledge-base.md) for source/enrichment
separation, safe refreshes, alias review, local terminology, and audit limitations.
This application uses an adapted ESCO-derived subset; the extraction version and
original ESCO identifiers are unknown. Attribution and official sources are documented
in that guide and acknowledged in the application footer.

## Tests and checks

```powershell
python manage.py test
python manage.py check
python manage.py makemigrations --check --dry-run --settings=careercoach.test_settings
python scripts/check_deploy.py
python -m pip check
```

For known-vulnerability auditing (requires network access to the advisory service):

```powershell
python -m pip install -r requirements-dev.txt
python -m pip_audit --no-deps --disable-pip -r requirements.lock
```

`manage.py test` defaults to `careercoach.test_settings`: an in-memory database,
an explicitly fake signing secret, no Groq key, and a runner that rejects network
connections. For other test entry points pass `--settings=careercoach.test_settings`.
Groq requests and model encoding are mocked; semantic similarity is tested against
small deterministic vectors. Tests do not modify your local database or download models.
The fast password hasher is confined to test settings.

`scripts/check_deploy.py` runs `check --deploy --fail-level WARNING` with disposable,
production-like settings and no `.env`. It simulates a deployment with HTTPS on all
subdomains and HSTS preload enabled. It does not validate your real proxy, DNS, TLS,
database, or provider credentials. Run `python manage.py check --deploy` again in
the actual deployment environment.

GitHub Actions runs tests, migration checks, dependency compatibility checks, and the
production configuration check on Python 3.12 and 3.13. The workflow runs only after
you push it; local success is not evidence that GitHub Actions has run.

## Production prerequisites

- Inject a new `DJANGO_SECRET_KEY` through a secret store. The key formerly committed
  in this repository is compromised: rotate it wherever used. Rotation may invalidate
  sessions and other signed data. Never retain the exposed value as a fallback.
- Set `DJANGO_DEBUG=false` and exact comma-separated `DJANGO_ALLOWED_HOSTS` values.
  Use exact HTTPS `DJANGO_CSRF_TRUSTED_ORIGINS` only if needed; same-origin forms
  do not require an entry. Wildcards are rejected.
- Terminate TLS at a correctly configured reverse proxy and use a production WSGI/ASGI
  server. `runserver` is for development. Select and pin your server for the target OS
  (for example, Gunicorn on Linux or Waitress on Windows).
- Only enable `DJANGO_TRUST_PROXY=true` if the trusted proxy strips incoming
  `X-Forwarded-Proto` and supplies its own. Configure the server/proxy to provide the
  actual client IP in `REMOTE_ADDR`; the app deliberately ignores `X-Forwarded-For`.
  Otherwise clients may share an authentication limit behind the proxy.
- Production enables HTTPS redirects and Secure session/CSRF cookies automatically.
  Start with `DJANGO_HSTS_SECONDS=3600` after verifying HTTPS. Increase to 31536000,
  include subdomains, and enable preload only when every affected subdomain supports
  HTTPS permanently. The corresponding deployment-check warnings during a staged
  rollout are intentional; do not silence them globally.
- Apply migrations before serving traffic. Configure a persistent database, access
  controls, and encrypted backups with tested restoration. SQLite supports local use;
  assess write contention before a multi-worker launch. PostgreSQL and its driver
  require deployment-specific configuration and validation; this phase retains SQLite.
- Run `python manage.py collectstatic --noinput` and serve `staticfiles/` through your
  server/CDN. Keep `.env`, database files, model caches, and logs outside public paths.
- Provision the embedding model and verify recommendations in staging. Monitor memory
  and request latency; large ML imports are lazy so login and system checks stay light.
- Set proxy body-size, request-timeout, and connection limits in addition to Django's
  64 KiB application body limit. Use HTTPS between services where supported.
- Set Groq provider spending limits and alerts. Application quotas count attempts,
  including failed requests, and are not a global billing cap. Add service-wide spend
  enforcement and perimeter abuse controls before a commercial launch.
- Document the profile/assessment/chat data sent to Groq, obtain appropriate user
  consent, and define retention/deletion policies before enrolling real customers.

## Usage safeguards

Shared database counters enforce these default fixed-window limits:

| Operation | Default | Identity |
| --- | --- | --- |
| Login attempts | 10/minute | Client IP |
| Registration attempts | 10/hour | Client IP |
| Assessment writes / question requests | 30/minute per scope | User |
| Chat messages | 10/minute and 100/day | User |
| New roadmap generation | 10/day | User |

The corresponding settings are configurable through environment variables (see
`careercoach/settings.py`). Counters store keyed hashes rather than raw IPs and fail
closed if their database is unavailable. Schedule this command daily:

```powershell
python manage.py cleanup_security_counters
```

Per-user work leases prevent duplicate concurrent generation and conflicting writes;
they expire after five minutes if a worker crashes. Groq has a 20-second timeout by
default, no automatic retries, and a maximum configurable timeout of 120 seconds.
Ensure model inference and server request timeouts stay below the lease lifetime.
Limits reset at fixed clock boundaries, rather than using a sliding window.

## Phase 1 behavior changes

- Retake and chat clearing require POST and CSRF tokens. Old `?retake=1` links do not
  delete data. Phase 2B retakes create new sessions and preserve previous results.
- Phase 2B replaces the old adaptive submission with balanced, persisted 18/36-item
  sessions. Invalid input leaves existing data untouched. At most 30 skills of 100
  characters each are accepted, with integer ratings from 1 to 5.
- Partial first assessments do not unlock recommendations or roadmaps. Profile and
  completed assessment changes invalidate recommendation caches. Phase 2B preserves
  saved roadmaps/progress and labels plans that predate the current assessment.
- Recommendations are computed lazily after saving; model failures produce a generic
  temporary-unavailability message while preserving the submitted assessment.
- Opening a new roadmap displays a preparation page that automatically submits a
  CSRF-protected POST. Saved plans load normally; generation is never performed by GET.
- Rate limits return 429; overlapping work returns 409. Provider failures use generic
  messages. Invalid roadmap output falls back to the existing rule-based plan.

See `docs/phase1-security.md` for the implementation scope and remaining risks.

## Phase 2B: RIASEC Assessment 2.0

Visit `/assessment/start/` after signing in. Quick uses 18 activities (three per
interest area); Detailed uses 36 (six per area). Both use bank
`careercoach-riasec-2026.1`, balanced interleaving, and the same five-point enjoyment
scale. The bank is **not empirically validated**. It explores interests rather than
measuring ability or guaranteeing career suitability.

Answers save on Next, Previous, or Save and exit. Refresh/resume restores saved
responses. Final review requires every answer, then freezes the result. Retakes
create new sessions; history includes snapshots of existing legacy assessments.
Historical scores with different modes/scorers are not presented as a direct trend.
The current recommendation weights are unchanged: a raw mean/5 adapter keeps its
old input scale separate from the new descriptive 0–100 result scale.

```powershell
python manage.py migrate
python manage.py check_assessment_bank
python manage.py test
```

For revisions, clone a published bank into a new draft, edit its questions through
Django admin, check coverage, and publish explicitly:

```powershell
python manage.py clone_question_bank careercoach-riasec-2026.1 your-new-version
python manage.py check_assessment_bank --bank-version your-new-version
python manage.py publish_question_bank your-new-version
```

Existing sessions keep their selected item snapshots and results. The old interest
submission and adaptive JSON endpoints now return HTTP 410; the old interest page
redirects to the new start page. Reload any assessment tab opened before this upgrade.

See [architecture](docs/phase2b-architecture.md),
[scoring and bank management](docs/phase2b-assessment-guide.md),
[all 36 item facets and legacy review](docs/phase2b-question-bank.md),
[future validation plan](docs/phase2b-validation-plan.md), and
[executed checks](docs/phase2b-validation.md).

## Phase 2C: explainable recommendations (opt-in)

The default remains the legacy scorer. Set `RECOMMENDATION_ENGINE=v2` in your
ignored `.env` and restart Django to review canonical skill matches, evidence
availability, industry fallback labels and scoring contributions. Leave
`RECOMMENDATION_SEMANTIC_ENABLED=false` to run v2 without an embedding model.
The weights remain 45/40/15; changed component definitions are experimental.
Ranking points are not career-success probabilities.

Back up your database before `python manage.py migrate`. The additive migration
archives current cached recommendations; all subsequent computations create
versioned history at `/recommendations/history/`. Existing roadmaps and progress
are preserved. Switching engines changes current caches, not historical runs.

```powershell
.venv\Scripts\python.exe -B manage.py migrate
.venv\Scripts\python.exe -B manage.py test
.venv\Scripts\python.exe -B scripts/evaluate_recommendations.py --output .cache/phase2c-comparison.json
```

See [architecture/cache design](docs/phase2c-architecture.md),
[scoring/evidence rules and activation](docs/phase2c-recommendations.md),
[synthetic evaluation](docs/phase2c-evaluation.md), and
[validation](docs/phase2c-validation.md). No empirical accuracy improvement is claimed.

## Synthetic profile evaluation

Run 100 seeded profiles through both real assessment modes and the v2 engine:

```powershell
python manage.py simulate_profiles --count 100 --mode both --seed 42
```

This reads the catalog and active bank from the configured SQLite file through a
read-only connection, then runs **200 assessments** in a separate in-memory process.
No synthetic records are written to your application database. Network calls and
semantic proposals are disabled. CSV/JSON/Markdown exports appear in ignored
`reports/`. Use `--source-db`, `--output-dir`, `--count`, `--mode` and `--seed` for
other runs. See [safety, methodology and export format](docs/synthetic-profile-evaluation.md)
and [executed validation](docs/synthetic-profile-validation.md).

## Phase 3A: private resume uploads

Sign in and open `/resumes/` to upload a PDF/DOCX (5 MiB maximum) with consent,
view an offline text preview, download the original as an attachment or delete
the file and its private text. There is no OCR, AI processing, skill extraction,
scoring or recommendation integration. Resume pages load no external CDN assets.

```powershell
python -m pip install -r requirements.lock
python manage.py migrate
python manage.py test resume
python manage.py cleanup_resume_uploads
```

Private originals default to ignored `private_storage/resumes/`. Configure
`PRIVATE_RESUME_ROOT` outside the web server's public roots and schedule stale-upload
cleanup. Parsing runs in a resource-bounded subprocess; file validation is not a
malware guarantee. See [architecture, controls, setup, limits and validation](docs/phase3a-resume-upload.md)
before deploying. Backups require their own documented retention policy.
