# Siong GPT

Siong GPT is organized as a single repository with separate application and infrastructure boundaries.

```text
backend/       FastAPI backend
frontend/      Next.js frontend
infra/         Architecture and future deployment configuration
公司图标/       Original company brand assets
界面图/         Original UI reference images
```

## Start the frontend

```bash
cd frontend
npm run dev
```

The frontend is available at `http://localhost:3000`.

The backend now contains the FastAPI authentication API and Platform V1
foundation. See [`backend/README.md`](backend/README.md) for its checks and
[`docs/platform-v1-foundation.md`](docs/platform-v1-foundation.md) for the
architecture boundary and database upgrade procedure.

Phase 2 Source Registry, immutable versions, upload security, and local storage
are documented in [`docs/source-registry.md`](docs/source-registry.md).

Phase 3 persistent ingestion jobs, the independent worker, safe parsers,
deterministic chunks, and PostgreSQL FTS are documented in
[`docs/ingestion-pipeline.md`](docs/ingestion-pipeline.md).

Phase 4 local embeddings, pgvector semantic search, permission-safe hybrid
retrieval, and evaluation are documented in
[`docs/hybrid-retrieval.md`](docs/hybrid-retrieval.md).

Phase 4.5 isolated PostgreSQL, pgvector, real-model and vertical-slice validation
is documented in [`docs/integration-gate.md`](docs/integration-gate.md).
