# Infrastructure

Infrastructure and deployment assets belong in this directory.

The current local stack contains PostgreSQL 16 with pgvector. V1 does not use
Redis, OpenSearch, a separate vector database, or orchestration infrastructure.
Future infrastructure must be introduced only by the phase that requires it.

The platform architecture document is available in `design.md`.
