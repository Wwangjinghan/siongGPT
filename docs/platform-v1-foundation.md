# Platform V1 Foundation

## Decision and boundaries

Platform V1 is a modular monolith: one FastAPI backend, one Next.js frontend,
and (in a later phase) one independently running worker. Package boundaries do
not represent microservices. PostgreSQL 16 with pgvector is the unified V1
metadata and retrieval data foundation; no external vector or search database
is part of this decision.

The six business layers map to code as follows:

| Layer | Current or planned module |
| --- | --- |
| Experience | `frontend/src/app` and components |
| API | `backend/app/api` |
| Application services | Feature service packages under `backend/app` |
| Domain and governance | `backend/app/core/domain_types.py` and future feature domains |
| Authorization | `backend/app/permissions` |
| Persistence and infrastructure | `backend/app/models`, Alembic, PostgreSQL, and `infra` |

Only modules required by this phase have been created. Source ingestion,
knowledge governance, retrieval, and agent runtime remain future modules.

## Scope and access

- `COMPANY`: company-owned knowledge intended for an explicitly authorized
  company audience.
- `DEPARTMENT`: knowledge owned by one department; `department_id` is required.
- `PROJECT`: knowledge owned by a project. The type is reserved, but access is
  denied until a trusted membership resolver exists.
- `PERSONAL_DRAFT`: a user's private working knowledge; `owner_user_id` is
  required and V1 access is owner-only.

Scope says where a resource belongs. Access level says how sensitive it is.
The initial access levels are `INTERNAL`, `RESTRICTED`, and `CONFIDENTIAL`.
Missing or unknown scope, access level, or required ownership data is denied;
it is never interpreted as company-public data.

A Principal must have at least one fully recognized platform role. Empty role
sets, unknown role codes, mixed known/unknown roles, and conflicting platform
administrator combinations fail closed, including for an owned Personal Draft.

## Authorization contract

`PermissionService` is the only platform authorization entry point. It accepts
the database-backed authenticated `Principal`, an action, and a structured
resource context. The V1 role-to-capability map exists only in that service and
can later be replaced by database configuration. Routers, repositories, and
agents must not compare role strings themselves.

The Principal is adapted from the existing Auth dependency. JWT contains only
the user identifier; every authenticated request reloads current user status,
department, and roles from PostgreSQL. Permission code does not parse cookies.
An LLM or agent may suggest intent, entities, and retrieval hints, but it can
never create, remove, or widen authorization constraints.

## Data conventions

New platform models may use `TimestampMixin` for `created_at` and `updated_at`.
Existing Auth tables are not migrated. Actor/creator columns remain specific to
each future resource because ownership and nullability rules differ.

A future Knowledge Passport is a projection composed from Knowledge, Revision,
Evidence, Owner, Scope, and Effective Time fields. It is not a separate copied
record. Source processing status and publication status must be modeled
separately: `READY` does not mean `PUBLISHED`.

`QUERY_EVENT_RETENTION_DAYS` defaults to 30 for development and is configurable.
This default is not a company retention policy.

## Database upgrade

Local PostgreSQL uses `pgvector/pgvector:pg16` while retaining the existing
`postgres_data` volume and Compose workflow. For an existing database:

```powershell
docker compose -f infra/docker-compose.yml pull postgres
docker compose -f infra/docker-compose.yml up -d postgres
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Revision `8b72f0a6c341` runs `CREATE EXTENSION IF NOT EXISTS vector`, making the
upgrade repeatable. Its downgrade intentionally retains the extension. Dropping
with `CASCADE` could destroy future vector columns, while dropping without it
would make rollback fail after dependencies exist. The Alembic revision itself
can still be rolled back and reapplied safely.

## Future runtime boundaries

Risk routing belongs to Agent Runtime, not this phase. The future levels are
`LOW`, `MEDIUM`, and `HIGH`; insufficient sources, conflicting evidence, or
high-risk requests must degrade safely or route to a human.

Source Registry, immutable Source Version, and local content-addressed storage
are implemented in Phase 2 and documented in
[`source-registry.md`](source-registry.md). Parsing, ingestion jobs, chunks,
embeddings, knowledge items or governance, retrieval/RAG, query event storage,
audit logs, agents, finance rules, project membership, and risk routing remain
unimplemented.
