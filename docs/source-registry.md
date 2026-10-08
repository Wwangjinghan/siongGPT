# Source Registry and Version Storage

## Domain boundary

A **Source** is the stable logical identity of enterprise material. A **Source
Version** is one immutable uploaded representation of that Source. A version is
not a parsed document, chunk, knowledge item, or search index entry.

`source_type` defines `DOCUMENT`, `EXPERT_NOTE`, and `MANUAL_ATTESTATION`.
Phase 2 accepts file versions only for `DOCUMENT`; the other values reserve a
stable domain vocabulary without implementing their future governance flows.

## Scope and authorization

All operations use the existing database-backed Principal and
`PermissionService`. Unknown roles, empty roles, any role set containing an
unknown code, and conflicting platform/departments capabilities fail closed.

- SYSTEM_ADMIN may create and manage COMPANY and DEPARTMENT Sources.
- Department Admin may create and manage only its own DEPARTMENT Sources.
- Department User may read permitted INTERNAL material but cannot create or
  publish a formal department Source.
- Supported roles may create and update only their own PERSONAL_DRAFT.
- PERSONAL_DRAFT cannot be directly published as company or department content.
- PROJECT remains denied because there is no trusted membership resolver.

List visibility is compiled into SQL predicates. Get, version history, and
download return 404 when authorization fails so resource existence is not
disclosed. Every download performs a fresh authorization check; a storage key
is never accepted as an external credential.

## Immutable versions and states

Within a Source, `version_no` starts at 1. Upload locks the Source row before
reading the current maximum, so concurrent uploads serialize; database unique
constraints on `(source_id, version_no)` and `(source_id, file_hash)` provide a
second boundary. There is no general version update or delete API. Hash,
storage key, original metadata, and version number are immutable through the
HTTP surface.

Processing and publication are independent:

| Concern | States |
| --- | --- |
| Processing | PENDING → PROCESSING → READY; PENDING/PROCESSING → FAILED |
| Publication | DRAFT → PUBLISHED → SUPERSEDED or WITHDRAWN |

Every upload is `PENDING + DRAFT + is_current=false`. `READY` never implies
`PUBLISHED`. Phase 2 has no worker, so an ordinary upload cannot become READY
and consequently cannot be published. Phase 3 will call the internal
`mark_processing`, `mark_ready`, and `mark_failed` service methods; none is an
HTTP endpoint.

Only `READY + DRAFT` may be published. Publishing locks the target Source and
Version and switches the current version in one database transaction. The old
current becomes `SUPERSEDED` only when the new commit succeeds. A PostgreSQL
partial unique index enforces at most one current version per Source. Withdrawing
does not guess or restore an older version.

## Local storage

`StorageAdapter` exposes save, open, exists, and compensating delete operations.
The API and Source services cannot select arbitrary filesystem paths.

The development default is `../../siong-gpt-data/source-storage`, resolved from
the backend working directory, keeping uploaded data outside the repository.
Override it with `SOURCE_STORAGE_ROOT`; set the positive byte limit with
`SOURCE_MAX_UPLOAD_BYTES` (development default 25 MiB).

`LocalStorageAdapter`:

- reads in 1 MiB chunks while computing lowercase SHA-256;
- rejects empty and oversized streams and removes temporary files;
- writes to a private temporary file, flushes and fsyncs, then atomically moves
  it to `sha256/<2>/<2>/<full hash>`;
- rejects absolute keys, drive paths, `..`, backslashes, root escape, and
  symlink traversal;
- ignores user filenames when selecting physical paths;
- may reuse one physical object for equal hashes while retaining separate
  permission-bearing version rows for different Sources.

Allowed extensions are `.txt`, `.pdf`, `.docx`, and `.xlsx`, case-insensitively.
Client MIME must match a conservative allow-list. PDF and ZIP-based Office
signatures receive a minimal header check; text rejects NUL and obvious PDF,
ZIP, or executable signatures. This is not malware scanning or full format
validation. Phase 3 parsers must validate the complete format again.

If storage fails, no version row is attempted. If database insertion fails,
the service deletes only an object created by that upload after confirming no
version references it; a reused object is preserved. If reference safety cannot
be established, preservation is preferred over destructive cleanup.

## Database migration

From the repository root:

```powershell
docker compose -f infra/docker-compose.yml up -d postgres
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Revision `c4f6a1d28e90`, parent `8b72f0a6c341`, creates `sources` and
`source_versions`, their conservative foreign keys, checks, unique constraints,
and indexes. Downgrade removes only these two tables and leaves Auth and pgvector
untouched.

## Development checks

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m alembic heads
```

Phase 2 does not implement ingestion jobs, workers, parsing, OCR, chunks,
embeddings, indexes, knowledge governance, retrieval, or agents.
