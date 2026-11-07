# Phase 1 security implementation

Based on the approved audit of main commit `57e7bc4`.
Feature branch: `phase1/production-hardening-and-tests`.

## Addressed findings

| Area | Changes |
| --- | --- |
| Secrets/configuration | Environment-based secrets, ignored local .env, safe example, strict production validation |
| Transport | HTTPS redirect, Secure cookies, configurable HSTS, explicit proxy trust |
| Authentication | Database-backed login/registration throttling, POST logout retained, password redisplay removed |
| CSRF/methods | POST retake/chat clearing/generation, safe GET behavior, CSRF-enforcing regression tests |
| Isolation | Current-user ownership retained, two-user tests for assessments/cache/roadmaps/progress/chat |
| Input/output | Bounded JSON/type validation, safe json_script embedding, validated LLM roadmap content |
| Errors/AI | Generic user-facing failures, sanitized log messages, API timeout/retry/token limits, per-user quotas |
| Consistency | Completion marker, cache signatures/expiry, cache size correction, derived-data invalidation, work leases |
| Operations | Atomic guarded catalog replacement, cleanup command, offline tests, CI, pinned dependencies, deploy checks |

## Remaining launch responsibilities

- Rotate the historically exposed signing secret in every environment where it was
  used. Source cleanup does not revoke it or remove it from Git history.
- Validate TLS, proxy headers/client IP handling, persistence, backups, model assets,
  production server, logging access, monitoring, and restoration in the real environment.
- The included SQLite configuration requires a concurrency assessment. Database-backed
  throttling is shared across processes, but high traffic can still cause contention.
  Work leases have a five-minute lifetime; they are not a durable task queue.
- Add provider spending caps and broader abuse protection. Per-user quotas can be
  multiplied through account creation and do not enforce an organization-wide budget.
- Confirm provider model availability and inference quality in staging. The tests use
  mocked providers and encoders; they do not measure recommendation quality or live AI.
- Do not enable HSTS preload/includeSubDomains without verifying all affected hosts.
- Email ownership verification, account recovery, staff MFA, institution tenancy,
  subscriptions/billing, and organization permissions remain future product work.
- Publish a privacy notice and retention/deletion policy for profile, assessment, and
  chat data. Review external AI processing before enrolling universities or students.
- CSP and integrity protection for external frontend assets remain deferred; existing
  inline scripts/styles need a deliberate CSP migration to preserve the UI.
- The dependency lock records exact versions but does not include artifact hashes.
  Revalidate on Linux CI and use a controlled artifact pipeline for release builds.

## Validation

Use the commands in README.md. Final execution results and a changed-file inventory
are recorded in `docs/phase1-validation.md` once local checks have completed.
GitHub Actions has not been run until the branch is approved for push.
