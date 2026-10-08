# Phase 3 ingestion pipeline

This is the implemented developer contract for turning an immutable
`SourceVersion` into searchable `DocumentChunk` rows. It is not an embedding,
retrieval, governance, or agent system.

## Process boundary

Upload, processing, and publication remain separate:

```text
upload       PENDING / DRAFT / not current
worker       READY   / DRAFT / not current
publish API  READY   / PUBLISHED / current
```

`POST /api/v1/source-versions/{version_id}/process` persists a job and returns
HTTP 202. It never parses in the API process. Run the worker independently:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.workers.ingestion
```

The worker identity is `SYSTEM_WORKER:<hostname>:<pid>:<random-instance>`, not a
fabricated employee. FastAPI restarts cannot remove queued work because the queue
is the PostgreSQL `ingestion_jobs` table.

## Job state machine and recovery

Allowed transitions are:

- `QUEUED -> RUNNING` when a worker claims a due row.
- `RUNNING -> SUCCEEDED` after chunks and READY are committed.
- `RUNNING -> FAILED` after a failed attempt with retries remaining.
- `FAILED -> QUEUED` after `available_at`, or through an authorized retry.
- `RUNNING -> QUEUED` when a lease expires and attempts remain.
- `RUNNING -> DEAD_LETTER` when the final lease/processing attempt fails.
- `QUEUED -> CANCELLED` through the authorized cancel operation.
- Manual retry of `DEAD_LETTER` creates a new QUEUED job and preserves the old row.

`SUCCEEDED`, `DEAD_LETTER`, and `CANCELLED` are not claimed. SUCCEEDED cannot be
retried, and RUNNING cannot be cancelled. A partial unique index permits at most
one QUEUED/RUNNING job per source version.

Claim uses `SELECT ... FOR UPDATE SKIP LOCKED`; claim and lease assignment are one
transaction. Attempts increment on claim. Heartbeats conditionally extend only an
unexpired lease owned by that worker. Before persistence, the worker locks the job
with the same owner/status/unexpired conditions. This fencing stops stale workers
overwriting later results. A final expired lease marks the version
`FAILED/LEASE_LOST` too.

Retry delay is exponential from `INGESTION_RETRY_BASE_SECONDS`. Poll interval,
lease, attempts, and bounded batch size are configurable. SIGINT/SIGTERM stop the
loop between work units.

## Parser contract and matrix

Parsers transform a controlled stream into ordered `DocumentBlock` values. They do
not write the database or use the network. Blocks carry type, ordinal, content and
applicable page, section, sheet, row range, locator, and metadata.

| Format | Extracted structure | Locator | Protections | Known boundary |
| --- | --- | --- | --- | --- |
| TXT | UTF-8/BOM paragraphs | line start/end | strict decoding, NUL/control check, character limit | other encodings rejected |
| PDF | native text per page | page | signature/parser validation, encryption/page/text limits | scanned/empty-text returns `OCR_REQUIRED`; no OCR |
| DOCX | headings, paragraphs, tables in document order | section/block | OOXML ZIP limits, path checks, macro/executable rejection | embedded media/layout not extracted |
| XLSX | sheets and non-empty rows with headers | sheet and row range | read-only, ZIP/sheet/row/cell/text limits, no external links | formula text preserved and never executed |

Selection combines allowed extension, stored MIME, and parser-level signature or
OOXML validation. Client MIME alone is not trusted. ZIP checks limit entry count,
expanded size and compression ratio, and reject unsafe paths, VBA/macro and
executable payloads. These checks are **not virus scanning**. Production still
needs a company-approved malware scanner at upload/object-storage ingress.

Limits are configured with `INGESTION_MAX_*` in `backend/.env.example`; all are
positive-validated, including an XLSX cells-per-row bound. Logs contain job IDs and stable error codes, not document text
or absolute paths. API errors contain no traceback.

## Deterministic chunking

Normalization standardizes newlines, trims line edges, collapses horizontal white
space, and removes empty lines; it does not rewrite identifiers or terminology.
Long blocks split at a newline/space when possible with finite character overlap.
Spreadsheet rows group deterministically by sheet and `XLSX_ROWS_PER_CHUNK`, with
headers retained. Tables remain contextual units, not one chunk per cell.

Indexes start at zero in stable block order. `content_hash` is lowercase SHA-256 of
normalized content. Metadata records normalization/chunker versions. Reprocessing
deletes and reinserts the version's chunks in the same transaction as version READY
and job SUCCEEDED, so it replaces instead of appends. Rollback preserves the prior
complete chunk set.

## Persistence and FTS

`document_chunks` has unique `(source_version_id, chunk_index)`, content/locator
checks, JSONB locator/metadata, and no delete cascade. `search_vector` is a stored
PostgreSQL generated column:

```sql
to_tsvector('simple'::regconfig, content)
```

A GIN index supports plain and explicit bounded prefix queries. Repository search
joins Chunk -> Version -> Source, reuses database-level Source visibility, and only
admits `READY + PUBLISHED + is_current`. Phase 3 exposes no search API; this is the
permission-safe base for Phase 4.

## API and permissions

| Endpoint | Permission and behavior |
| --- | --- |
| `POST /api/v1/source-versions/{id}/process` | Source UPDATE; ACTIVE, PENDING/DRAFT/not-current; HTTP 202 and active-job idempotency |
| `GET /api/v1/ingestion-jobs/{id}` | Source READ via Job -> Version -> Source; unauthorized is 404 |
| `POST /api/v1/ingestion-jobs/{id}/retry` | Source UPDATE; FAILED requeues, DEAD_LETTER creates a new job |
| `POST /api/v1/ingestion-jobs/{id}/cancel` | Source UPDATE; QUEUED only |

The existing Permission Service is authoritative. Personal-draft owners require a
supported role; unknown/invalid roles and PROJECT fail closed. Responses omit lease
owner, storage key, absolute paths, environment data, and stack traces. No public
mark-ready/mark-failed endpoint exists.

## Database and local execution

From `backend/`:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\uvicorn.exe app.main:app --reload
.\.venv\Scripts\python.exe -m app.workers.ingestion
```

Migration `e91c3b7d42a6` follows `c4f6a1d28e90`. Upgrade creates only Phase 3 job
and chunk objects. Downgrade removes only those objects; it does not alter Auth,
Source tables, or pgvector.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\alembic.exe heads
.\.venv\Scripts\alembic.exe upgrade head --sql
```

Set a dedicated PostgreSQL `TEST_DATABASE_URL` to enable online integration tests.
Without it they deliberately skip; SQLite is not evidence for partial indexes,
generated TSVECTOR, GIN, row locks, SKIP LOCKED, or pgvector.

## Phase 4 extension

Phase 4 now extends successful ingestion with local E5 embeddings before READY and
adds an explicit backfill path for earlier READY versions. See
[`hybrid-retrieval.md`](hybrid-retrieval.md). Knowledge Governance, RAG, agent
runtime, OCR, connectors, and queue brokers remain deferred.
