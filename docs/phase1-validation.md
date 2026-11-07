# Phase 1 local validation

Validated on 7 November 2026 (Asia/Kuala_Lumpur), Windows, Python 3.13.2,
Django 6.0.10. Base: main `57e7bc4`.
Branch: `phase1/production-hardening-and-tests`.

## Executed checks

| Command/check | Final result |
| --- | --- |
| `python -B manage.py test` | **98 passed, 0 failed**, 13.890 seconds |
| `python -B manage.py check` | No issues |
| `python -B manage.py makemigrations --check --dry-run --settings=careercoach.test_settings` | No changes detected |
| `python -B scripts/check_deploy.py` | `check --deploy --fail-level WARNING`: no issues, none silenced |
| `python -B -m pip check` | No broken requirements |
| `python -B -m pip_audit --no-deps --disable-pip -r requirements.lock` | No known vulnerabilities found |
| `git diff --check` | Passed |
| CI workflow YAML parse | Passed; repository permissions are read-only |
| Current source secret scan | Former exposed signing secret absent; .env and database remain untracked |
| Local migrations | All three additive migrations applied after SQLite backup; migrate --check passed |
| Existing data preservation | Row counts unchanged in all nine checked user, profile, assessment, catalog, cache, and roadmap tables |
| CPU runtime availability | PyTorch 2.15.0+cpu confirmed available for CI |

Tests use an in-memory database and reject socket connections. Groq requests and
model encoding are mocked; numerical similarity uses deterministic vectors.
Expected warning logs from deliberately failed provider/model tests are not test failures.
The suite covers authentication, protected routes, CSRF and methods, assessment
validation and retakes, adaptive selection, RIASEC/background/weighted scoring,
semantic gaps, caching/invalidation, roadmap ownership/progress, chatbot isolation,
error handling, throttling, leases, import safety, and production settings.

An earlier full-suite run caught stale references to a removed JSON import. The
handlers were corrected and the entire final suite was executed successfully.
Initial deployment checks also reported HSTS subdomain/preload warnings; the
production simulation now explicitly models HTTPS across all subdomains. Actual
settings retain a staged HSTS rollout and do not silence security checks.

## Limits of validation

GitHub Actions has not run: no push, PR, or merge was performed. Its Python 3.12/3.13
Linux matrix remains to be validated on GitHub after push approval. Local runtime
validation used Windows/Python 3.13 only. No live Groq requests, model downloads,
TLS/proxy integration tests, browser automation, load tests, or production deployment
were performed. Known-vulnerability auditing is point-in-time and is not a guarantee
that dependencies contain no vulnerabilities. The runtime lock has no artifact hashes.

The existing local database has an ignored SQLite backup named
`db.sqlite3.phase1-backup-20261106235615` (UTC timestamp). No real secrets were
added to tracked files. Changes remain uncommitted for review.

For important behavior changes and deployment prerequisites, see README.md.
For remaining security/product risks, see docs/phase1-security.md.

## Files changed or added

- `.env.example`
- `.github/workflows/tests.yml`
- `.gitignore`
- `README.md`
- `accounts/apps.py`
- `accounts/auth_views.py`
- `accounts/management/__init__.py`
- `accounts/management/commands/__init__.py`
- `accounts/management/commands/cleanup_security_counters.py`
- `accounts/migrations/0002_securitycounter.py`
- `accounts/models.py`
- `accounts/tests.py`
- `accounts/urls.py`
- `accounts/views.py`
- `assessment/apps.py`
- `assessment/migrations/0005_userresponse_completed_at.py`
- `assessment/models.py`
- `assessment/state.py`
- `assessment/tests.py`
- `assessment/urls.py`
- `assessment/validation.py`
- `assessment/views.py`
- `careercoach/context_processors.py`
- `careercoach/environment.py`
- `careercoach/middleware.py`
- `careercoach/security.py`
- `careercoach/settings.py`
- `careercoach/test_settings.py`
- `careercoach/test_utils.py`
- `careercoach/testing.py`
- `careercoach/tests.py`
- `chatbot/tests.py`
- `chatbot/views.py`
- `dashboard/tests.py`
- `dashboard/views.py`
- `docs/phase1-security.md`
- `docs/phase1-validation.md`
- `manage.py`
- `recommender/admin.py`
- `recommender/cache.py`
- `recommender/embeddings.py`
- `recommender/management/commands/import_data.py`
- `recommender/matching.py`
- `recommender/migrations/0004_cachedrecommendation_input_signature.py`
- `recommender/models.py`
- `recommender/recommendations.py`
- `recommender/tests.py`
- `recommender/views.py`
- `requirements-dev.txt`
- `requirements.lock`
- `requirements.txt`
- `roadmap/generator.py`
- `roadmap/tests.py`
- `roadmap/views.py`
- `scripts/check_deploy.py`
- `templates/accounts/register.html`
- `templates/assessment/quiz.html`
- `templates/assessment/skills.html`
- `templates/dashboard/dashboard.html`
- `templates/recommender/results.html`
- `templates/roadmap/start.html`
