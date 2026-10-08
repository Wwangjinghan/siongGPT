# Phase 4 embedding and hybrid retrieval

Phase 4 adds permission-safe retrieval. It returns source excerpts and retrieval
metadata; it does not generate answers and does not persist raw queries.

## Embedding decision

V1 uses `intfloat/multilingual-e5-small` locally:

- revision `fd1525a9fd15316a2d503bf26ab031a61d056e98`
- 384 dimensions, cosine distance, L2 normalization
- `query: ` and `passage: ` prefixes
- MIT model license

The multilingual E5 profile is small enough to establish a measurable local V1
baseline. This technical choice is not a claim that quality has been validated on
company data. No enterprise text is sent to an external API.

`EMBEDDING_ALLOW_DOWNLOAD=false` is the default. Missing model files do not stop
FastAPI; search degrades to FTS-only. The Worker fails new ingestion rather than
writing empty, random, hash, or zero vectors.

## Install and prepare the model

Base dependencies remain in `requirements.txt`. Install local ML support only on
processes that perform semantic search or embedding work:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements-ml.txt
```

`torch` is the largest dependency. Pins were installed on Windows CPython 3.13.15
with CPU support. GPU use needs an explicitly approved PyTorch/CUDA matrix; WSL and
Linux wheels/system libraries require separate validation. API and Worker are
separate processes, so each process performing semantic work loads its own lazy,
process-cached model.

Place an approved model copy at `EMBEDDING_MODEL_LOCAL_PATH`. The directory must be
a Hugging Face snapshot path containing the configured commit, or contain
`.siong-model-revision` (or `model_revision.txt`) whose entire content is that
commit. A mismatch is rejected. Explicit download still pins the exact revision,
but downloaded files must be reviewed before production use.

The Provider checks token length without truncation, applies prefixes centrally,
validates 384 finite values, rejects zero vectors, and normalizes output.

## Profiles and persistence

Migration `f2a7c9d31b84` bootstraps one stable ACTIVE profile. Profiles store the
provider, exact model/revision, dimensions, metric, normalization and prefixes—not
tokens, secrets, or local paths. A partial unique index permits one ACTIVE profile.

`document_chunk_embeddings` stores one `vector(384)` per Chunk/Profile plus the
Chunk content hash. Search rejects stale hashes. Historical profiles coexist and
are not overwritten. The cosine HNSW index is created, while V1 defaults to exact
search until real-corpus recall and query-plan benchmarks justify HNSW mode.

Upgrade a model by creating an INACTIVE profile, verifying its pinned model,
backfilling eligible versions, evaluating retrieval, atomically switching ACTIVE,
and retaining the old profile for rollback. Never edit an active profile revision
or overwrite its historical vectors.

## Ingestion and backfill

New ingestion is:

```text
parse -> chunks -> FTS -> passage embeddings
      -> atomic chunks + embeddings -> READY/DRAFT/not-current
```

Provider failure leaves the Version non-READY and never publishes it. For an
existing READY Version, queue a persistent backfill:

```http
POST /api/v1/source-versions/{version_id}/embeddings/reindex
```

This requires Source APPROVE or MANAGE. Published/current Versions may be
backfilled without changing publication/current state. Ordered batches use
`(chunk_id, profile_id)` upsert. Failure retains FTS and successful prior batches;
semantic search excludes the entire Version until all Chunks have current-hash
embeddings for the ACTIVE profile.

## Retrieval flow

`POST /api/v1/search` performs:

```text
validate -> SQL permission/publication filters -> FTS candidates
-> local query embedding -> vector candidates -> RRF -> deterministic rerank
-> bounded snippets
```

Both candidate queries enforce in SQL: ACTIVE Source, COMPANY/DEPARTMENT scope,
READY/PUBLISHED/current Version, effective dates, Permission Service visibility,
and narrowing metadata filters. Semantic search also requires ACTIVE Profile,
matching content hash, and complete Version embedding coverage. PERSONAL_DRAFT and
PROJECT do not enter published search. Unauthorized candidates are never loaded for
Python-side filtering.

FTS uses parameterized `plainto_tsquery('simple', ...)`, retaining PO, DO, GST and
project codes. Vector search uses cosine distance. Exact mode disables index and
bitmap scans transaction-locally so the HNSW index cannot silently make the
baseline approximate. HNSW mode transaction-locally restores those planner options
and applies `set_config('hnsw.ef_search', ..., true)` without removing SQL filters.

RRF uses `weight / (rrf_k + rank)`, rank one origin, deduplication and stable
chunk-ID tie-breaking. Bounded deterministic boosts explain title/section phrases,
exact uppercase codes and dual-channel hits. Permissions are hard filters, never
boosts. There are no department/finance-specific, LLM, CrossEncoder, or answer rules.

If the Provider is unavailable, the response is `FTS_ONLY` with
`semantic_available=false`; no substitute vector is generated.

## API and privacy

| Endpoint | Contract |
| --- | --- |
| `POST /api/v1/search` | Authenticated retrieval with bounded query, limit and narrowing filters |
| `GET /api/v1/health/embedding` | Authenticated redacted provider/profile health |
| `POST /api/v1/source-versions/{id}/embeddings/reindex` | APPROVE/MANAGE; queues backfill, HTTP 202 |

Search returns bounded excerpts and provenance/ranking metadata. It does not return
vectors, storage keys, local paths, secrets, stack traces, unauthorized candidate
counts, or generated answers. It does not create Query Events or store raw queries.

## Evaluation

`backend/tests/fixtures/retrieval_evaluation.json` is fictional and covers
reimbursement, GST, project codes, English, Chinese, mixed-language, exact-code,
irrelevant and unauthorized cases. Metrics are Recall@1/3/5 and MRR.

Fake Provider results verify data flow and algorithms only—not semantic quality.
The committed deterministic fixture currently produces these deliberately
synthetic baselines over six eligible queries:

| Mode | Recall@1 | Recall@3 | Recall@5 | MRR |
| --- | ---: | ---: | ---: | ---: |
| FTS fixture | 0.5000 | 0.6667 | 0.6667 | 0.5833 |
| Vector fixture | 0.5000 | 0.8333 | 0.8333 | 0.6667 |
| Hybrid fixture | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

These values test metric calculation and separate-mode reporting; they must not be
used as evidence of E5 relevance. The real-model test is explicitly skipped when
the pinned local snapshot is absent.

After preparing the pinned model, run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_real_embedding_model -v
.\.venv\Scripts\python.exe -m unittest tests.test_retrieval -v
```

The first real evaluation establishes the baseline; no pass threshold is invented
before it exists.

## Operations and Phase 5 boundary

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m app.workers.ingestion
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Use a dedicated `TEST_DATABASE_URL` for pgvector/HNSW integration tests; SQLite is
not a substitute. Phase 5 is Knowledge Governance, not an Answer Agent. Knowledge
Item/Revision/Evidence/Passport, curator workflow, human review, agent runtime,
answer generation and query analytics remain out of scope.
