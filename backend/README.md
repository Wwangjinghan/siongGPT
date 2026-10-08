# Backend

FastAPI backend for Siong GPT. It currently provides cookie-based authentication,
database health checks, the Platform V1 domain contracts, centralized resource
authorization, the Source Registry, immutable Source Versions, and reliable
document ingestion.

## Development checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -c "from pathlib import Path; [compile(p.read_text(encoding='utf-8'), str(p), 'exec') for root in ('app', 'alembic', 'tests') for p in Path(root).rglob('*.py')]"
```

Database and pgvector setup is documented in
[`../docs/platform-v1-foundation.md`](../docs/platform-v1-foundation.md).
Source API, storage, state transitions, and migration details are in
[`../docs/source-registry.md`](../docs/source-registry.md).
Worker operation, parser limits, deterministic chunking, job recovery, and FTS are
documented in [`../docs/ingestion-pipeline.md`](../docs/ingestion-pipeline.md).
Local E5 setup, embedding profiles, backfill, hybrid retrieval, and evaluation are
documented in [`../docs/hybrid-retrieval.md`](../docs/hybrid-retrieval.md).
The isolated PostgreSQL/pgvector and real-model acceptance gate is documented in
[`../docs/integration-gate.md`](../docs/integration-gate.md).
