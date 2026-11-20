# Phase 3A: private resume upload and text extraction

Implemented on `phase3a/secure-resume-upload`, based on `e13b609`.
Scope: PDF/DOCX upload, offline extraction, private records, owner downloads and
deletion. No AI processing, OCR, skill matching, scoring or recommendation integration.

## Inspection and dependency decisions

Inspected settings, routing, authentication/CSRF, shared user leases and counters,
middleware, account ownership, templates, migrations, test settings and deployment
workflow. No existing resume app or file upload feature existed. Runtime here is
Python 3.13 / Django 6.0.10; existing CI also targets Python 3.12 on Linux.
The prior recommendation, assessment and roadmap models/algorithms are unchanged.

Pinned additions in both dependency files:

- **pypdf 7.0.0**: maintained, pure Python, BSD-licensed PDF parsing; no executable
  converter or commercial PDF library dependency. [Maintainer package](https://pypi.org/project/pypdf/).
- **defusedxml 0.7.1**: hardened XML parsing for a deliberately small DOCX text
  reader over standard-library ZIP handling. Explicitly forbids DTDs, entities and
  external references. No python-docx/lxml/Office/LibreOffice installation needed.
  [Maintainer package and XML threats](https://pypi.org/project/defusedxml/).

Parsing untrusted PDFs can consume much more memory than the uploaded size.
See [pypdf extraction/memory limitations](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).
The controls follow defense-in-depth principles from the
[OWASP upload guidance](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
and [Django upload security guidance](https://docs.djangoproject.com/en/6.0/topics/security/#user-uploaded-content).
Validation cannot prove a document harmless.

## Architecture and flow

1. An authenticated owner submits one file and explicit storage/extraction consent.
2. `resume/uploads.py` bounds actual multipart bytes in memory. Original bytes are
   never spooled into Django's shared temporary upload directory.
3. `ResumeUploadForm` checks actual bytes, extension/signature and sanitizes a
   basename for display. Browser MIME is ignored as a security signal.
4. A pending database reservation records an independent random storage UUID,
   owner, filename, type, actual byte count and SHA-256; then becomes processing.
5. `services/extraction.py` supervises a separate Python parser process. Bytes
   travel through stdin; no original filename, filesystem document path, Django
   settings or environment credentials are passed. The child validates structure
   and extracts text offline.
6. Rejected files are never written to private storage; the reservation is removed.
   Once validation/extraction succeeds, accepted original bytes are saved under
   the randomized key and the private result is persisted. This ordering avoids
   retaining invalid originals, while preserving a reservation for interrupted writes.
7. The owner sees status and an escaped, at-most-12,000-character text preview.
   No recommendation/cache/profile is updated.

`resume/models.py` defines `ResumeDocument`: UUID PK, owner FK, display filename,
file type/size, independent unique storage UUID, SHA-256 checksum, status, text,
error code, uploaded/completed/updated timestamps and `file_retained`. Statuses:
`pending`, `processing`, `completed`, `failed`, `no_extractable_text`.
The migration is additive: `resume/migrations/0001_initial.py`.
No public file URL or local document path is stored on the record. There is no
admin registration exposing everyone's extracted resumes.

## Limits and rejection rules

| Resource | Limit |
| --- | --- |
| Actual original bytes | 5 MiB (5,242,880 bytes) |
| Files per multipart request | 1 |
| PDF pages | 30 |
| Extracted/normalized text | 200,000 characters |
| PDF decoded content stream | 8 MiB, also OS memory bounded during decoding |
| DOCX ZIP entries | 200 |
| Total DOCX uncompressed data | 20 MiB |
| Individual DOCX entry | 8 MiB |
| Per-entry compression ratio | At most 100:1 |
| Parser wall-clock deadline | 10 seconds, then kill/reap |
| Parser CPU | 5 seconds |
| Parser memory | 256 MiB |
| Stored records per owner | 10 |
| Upload POST attempts per owner/day | 10 (shared database rate counters) |

Limits are explicit constants/settings, not inferred from client declarations.
The existing user work lease serializes uploads/deletions with other expensive
user operations. It does not provide a global multi-account concurrency cap.

PDF validation uses strict structural parsing, rejects encryption (even empty
password encryption), page overflow, active actions/JavaScript, external URI
actions, embedded files and rich-media/action payloads in reachable objects.
Only text is extracted; document actions and embedded files are never executed.
No-text/image-only PDFs return `no_extractable_text`; there is no OCR.

DOCX validation checks central entries before parsing, actual CRC/decompression,
duplicate names, platform-normalized/original names, absolute/traversal/backslash
paths, symlinks/special files, unsupported/encrypted compression and size/ratio
limits. Nothing is unzipped to disk. Parts must form a supported OOXML document.
Macros, active content/fields, external relationships, executable/embedded object
parts and non-allowlisted binaries are rejected. Media entries must have expected
PNG/JPEG/GIF signatures; images are not decoded. All XML parts use defusedxml.
Standard DOCX hyperlink relationships, including mailto, are external and rejected.

## Execution boundary

The parent uses isolated Python startup (`-I -B`), minimal OS environment, hidden
Windows subprocesses, no stderr capture/logging, and a fixed pipe/output budget.
POSIX workers set `RLIMIT_AS`, `RLIMIT_CPU`, and disable core dumps before reading
untrusted input. Windows uses a Job Object with process/job memory, CPU and
kill-on-close limits **before sending stdin**. Two processes are allowed solely
to support the Windows venv launcher plus interpreter. Resource setup failure
rejects processing; it does not fall back to in-process parsing.

Standard socket/DNS APIs are blocked in the worker. There are no LLM calls.
These Python restrictions and resource limits are **not an exploit sandbox**:
the worker still has its OS account's filesystem privileges. A compromised parser
could bypass Python-level network hooks. Production should use a separate
low-privilege service/container with OS egress denial, read-only filesystem,
restricted credentials and cgroup/Job limits. Also bound aggregate process
concurrency, ingress bandwidth/request time and storage/backend timeouts.

## Routes, authorization and private responses

| Route | Method | Behavior |
| --- | --- | --- |
| `/resumes/` | GET | Paginated owner-only list |
| `/resumes/upload/` | GET, POST | Consent form and bounded upload/extraction |
| `/resumes/<uuid>/` | GET | Owner metadata/status/private preview |
| `/resumes/<uuid>/delete-confirmation/` | GET | Confirmation only |
| `/resumes/<uuid>/delete/` | POST | CSRF-protected owner deletion |
| `/resumes/<uuid>/download/` | GET | Owner-only original attachment |

Foreign and missing UUIDs both return 404. Anonymous access redirects to login.
GET never deletes. Invalid uploads return 400 (oversized multipart input 413),
rate limits 429 and unavailable processing/storage 503, with generic messages.
No filenames, text, parser exceptions or storage paths are logged by the feature.
Sensitive views/service locals and POST data are marked for Django error redaction.
Do not enable SQL parameter/body/local-variable capture in external monitoring:
database text fields and originals are sensitive personal data.
Disable full-memory crash dumps and document-body/local-variable capture for
parser processes and upload routes in the deployment's monitoring configuration.

Private pages use `private, no-store`, no-referrer, nosniff and a same-origin CSP.
They retain base inline styling/navigation while excluding external CDN assets,
including Bootstrap JS and Google fonts. The CSP retains inline scripts/styles
for existing base UI behavior; a nonce policy can accompany the future UI redesign.
Other pages retain their existing assets. All text/filenames are HTML-escaped.
Downloads use a fixed generic filename, octet-stream, attachment disposition,
nosniff, frame denial and a restrictive sandbox policy; originals are never inline.

## Storage, cleanup and privacy

Default private root: `BASE_DIR/private_storage/resumes`, Git-ignored. Set
`PRIVATE_RESUME_ROOT` for deployment. Relative paths resolve against BASE_DIR.
It must be outside publicly served static/media directories; system checks reject
overlap. There is no MEDIA/STATIC route to these files. Configure the web server
never to serve the private directory, preferably place it outside the web root,
and use encrypted disks/backups and a dedicated service account. POSIX directory
and file permissions request 0700/0600; set equivalent Windows ACLs explicitly.

`PrivateResumeStorage`/`private_storage()` form the replacement seam for future
private object storage. Backends must support **exact immutable randomized keys**,
private reads/deletes, no public URL and reliable timeout/error behavior. The
current backend refuses overwrite/renaming collisions; do not substitute a public
storage backend or one that silently returns unrelated keys.

The committed reservation precedes original storage. On write/DB failure the
service attempts immediate file cleanup and marks a private failed record. If
cleanup/DB recovery is unavailable, the original key remains tracked for retry;
failed originals cannot be downloaded. Upload is marked non-atomic at request
level so enabling ATOMIC_REQUESTS cannot roll back the reservation after writing.

Deletion removes the original through a model signal before SQL deletion;
storage failure aborts SQL deletion and the owner can retry. The same hook covers
queryset and account-cascade deletion. If SQL deletion fails after file removal,
the record/text remain private for retry and download availability is corrected
when the DB is available. Cross-resource filesystem/SQL rollback cannot be
perfectly atomic. No row is intentionally removed while leaving an untracked file.
Do not bypass signals with raw SQL to delete users/resume rows.

Recover reservations/failed originals after interrupted work:

```powershell
python manage.py cleanup_resume_uploads
```

This retries private-file cleanup for failed/pending/processing records older
than 30 minutes and marks them failed/interrupted, leaving owner-visible metadata
for deletion. It never prints contents, names or paths. Schedule it in deployment
and alert on its generic nonzero failure result. It is not a general filesystem
orphan scanner or retention-expiry policy.

Accepted originals and text are retained until owner/account deletion; there is
no automatic successful-document expiry. Rejected originals are not retained.
Failed metadata can remain until the owner deletes it. Logical deletion does not
guarantee forensic erasure from SQLite free pages, journals, object versions,
snapshots, backups or previously downloaded copies. Backup deletion/expiry is
**not implemented**; publish the actual backup/retention policy before rollout.

Malware scanning/content disarm, deployment encryption/key management, private
object-store integration, global queue capacity and automated backup expiry are
not implemented. Keep parsers patched and scan/quarantine originals before any
wider sharing. Do not describe the stored originals as verified harmless.

## Extraction limitations and Phase 3B seam

PDF text follows parser/page content order, which can differ from human reading
order in columns, tables, text boxes and graphics. Scans and images produce no
OCR text. The minimal DOCX reader preserves body/table paragraph order, then
appends headers/footers in deterministic order. Text boxes/Word fields, strict-
namespace OOXML and complex layouts may be rejected or incompletely represented.
No renderer, image decoder, external relationships or Office automation is used.

`services/extraction.extract_text` returns `{valid, status, text, error_code}`.
NFC/whitespace normalization preserves paragraph boundaries, removes controls and
enforces output length again after normalization. Private persisted text/status/
checksum provide a future Phase 3B input seam. A future feature must add explicit
consent, separate versioned processing and tests before any AI/skill/recommendation
use. This phase is ready for review as an upload/extraction foundation, not a
complete commercially deployed resume intelligence service.

## Local setup and manual review

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.lock
.venv\Scripts\python.exe -B manage.py migrate
.venv\Scripts\python.exe -B manage.py check
.venv\Scripts\python.exe -B manage.py runserver
```

Keep existing local `.env` settings; optionally configure PRIVATE_RESUME_ROOT.
Sign in and open `http://127.0.0.1:8000/resumes/`. Upload a small **synthetic**
PDF/DOCX after consent. Confirm text/status, download attachment, delete through
confirmation and verify its record/file disappear. Try a blank PDF, encrypted
PDF, legacy DOC and a second account/foreign UUID. Do not test with real student
resumes until the deployment controls and privacy policy are reviewed.

```powershell
python manage.py test resume
python manage.py test
python manage.py makemigrations --check --dry-run
python scripts/check_deploy.py
python -m pip check
python -m pip_audit --no-deps --disable-pip -r requirements.lock
```

## Executed validation (2026-11-09)

- Independent resume suite: **45 tests passed** (generated synthetic documents,
  temporary private storage, actual bounded Windows workers), 22.577 seconds.
  Final full suite: **310 tests passed, 0 failed**, 55.420 seconds, including all
  265 pre-existing tests. This final run includes the shared-template privacy change.
- Django local checks, migration drift checks, production-like deployment check
  and `pip check` passed. `pip-audit` reported **no known vulnerabilities** in the
  pinned lock file at execution time; this is not a guarantee against unknown flaws.
- Local `resume.0001_initial` applied after ignored SQLite backup
  `db.sqlite3.phase3a-backup-20261109T134045Z`. Row-by-row hashes of all original
  columns confirmed every pre-existing row unchanged, including 22 users,
  23 assessment sessions, five saved roadmaps, 15 progress rows, five recommendation
  runs and the complete knowledge base. New content-type/permission/migration
  records are expected additions. Report: `.cache/phase3a-preservation-result.json`.
- The first worker test exposed the Windows venv launcher process pair; memory
  limits now cover the whole two-process Job. Initial fixture issues involved a
  removed pypdf test API and ZIP writer path normalization; tests now construct
  explicit synthetic action objects and genuine unsafe archive bytes.
- HTTP upload/list/detail/download/delete, ownership, CSRF, escaping, privacy
  headers, byte limits, archive/PDF attacks, timeout cleanup and storage/DB failure
  compensation were exercised by automated tests. No real resume fixtures or
  external AI calls were used.
- **No manual browser testing was performed**. Browser-control tooling was not
  available; use the manual review steps above. CI's Linux/Python 3.12 matrix has
  not run in this local Windows session.

Files: new `resume/` app (model, migration, upload handler, forms, storage, signals,
checks, routes/views, parser/supervisor/limits/lifecycle services, cleanup command,
synthetic fixtures and tests), five `templates/resume/` files, settings/URL/middleware
integration, dependency files, `.env.example`, `.gitignore`, shared base template,
README and this document. No `.env`, database, backup or original is committed.
The user authorized a local Phase 3A commit. No push, PR or merge is authorized or
performed as part of this implementation.
