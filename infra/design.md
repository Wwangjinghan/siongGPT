# Siong GPT Enterprise Knowledge Platform — System Design

**Document:** `design.md`  
**Status:** Draft v1.0  
**Audience:** Engineering, AI, Platform, Security, Product  
**Primary goal:** Build Siong GPT as a production-grade enterprise knowledge platform that can support large document volumes, continuous knowledge ingestion, high employee concurrency, strong permissions, traceable answers, and future integration with internal systems.

---

## 1. Executive Summary

Siong GPT is not designed as a single RAG demo or a finance-only chatbot. It is designed as a reusable enterprise knowledge platform that can initially support the Finance pilot and later extend to Safety, Project, HR, Procurement, Operations, and other business units.

The system must support:

- Large-scale enterprise document ingestion.
- Continuous incremental synchronization from internal repositories.
- Full-text and semantic retrieval.
- Role-, department-, project-, document-, and field-level access control.
- High concurrency from large numbers of employees.
- Horizontally scalable APIs and workers.
- Versioned documents and traceable citations.
- Reliable AI answers grounded in approved enterprise knowledge.
- Auditable user activity and AI activity.
- Future workflow / task / agent integration.
- Cloud or private-cloud deployment without tightly coupling business logic to one provider.

The recommended baseline architecture is:

- **Frontend:** Next.js + React + TypeScript
- **Backend API:** FastAPI
- **Primary relational database:** PostgreSQL
- **Object storage:** S3-compatible object storage / Azure Blob / MinIO
- **Search layer:** OpenSearch
- **Cache / queue:** Redis
- **Async workers:** Celery / Dramatiq / RQ / equivalent worker framework
- **Authentication:** OIDC / Microsoft Entra ID
- **AI abstraction:** LLM Gateway
- **Deployment:** Containerized, horizontally scalable
- **Observability:** OpenTelemetry + centralized logs + metrics + tracing

The system uses a **modular monolith for business APIs**, combined with **separately scalable ingestion, indexing, search, and AI execution workers**. This avoids premature microservice complexity while preserving clear service boundaries.

---

# 2. Design Objectives

## 2.1 Functional objectives

The platform must support:

1. Employee login through enterprise identity.
2. Search across approved enterprise knowledge.
3. AI question answering with citations.
4. Related document discovery.
5. Related internal system links.
6. Document upload and ingestion.
7. Knowledge review, approval, and publishing.
8. Document version control.
9. Permission-aware retrieval.
10. Conversation history.
11. Feedback on answers.
12. Knowledge gap discovery.
13. Admin dashboards.
14. Full audit logging.
15. Future workflow actions.

---

## 2.2 Non-functional objectives

The system must be designed for:

- High availability.
- Horizontal scalability.
- Fault isolation.
- Eventual consistency where acceptable.
- Strong consistency for permissions and authoritative metadata.
- Large datasets.
- High employee concurrency.
- Low query latency.
- Secure multi-department access.
- Zero-downtime deployment where possible.
- Operational visibility.
- Recoverability.

---

# 3. Capacity Planning and Scale Targets

The platform should not be sized only for the Finance pilot. It should be designed for enterprise-wide deployment.

These are **design targets**, not hard limits.

## 3.1 User scale

Initial design envelope:

| Metric | Design Target |
|---|---:|
| Registered employees | 10,000+ |
| Daily active employees | 5,000+ |
| Concurrent authenticated sessions | 3,000+ |
| Concurrent AI conversations | 500+ |
| Search requests per second | 300+ |
| AI answer requests per second | 50+ burst |
| API read requests per second | 1,000+ |
| Admin / write requests per second | 100+ |

The architecture must allow horizontal scaling beyond these targets.

---

## 3.2 Knowledge scale

| Metric | Design Target |
|---|---:|
| Documents | 10 million |
| Document versions | 30 million |
| Searchable chunks | 100 million+ |
| Structured metadata rows | 100 million+ |
| Object storage | 10–100 TB |
| Search index size | Multi-TB |
| Daily document changes | 100,000+ |
| Daily ingestion jobs | 100,000+ |

The system must not require full re-indexing for normal updates.

---

## 3.3 Latency targets

| Operation | Target |
|---|---:|
| Login / session validation | < 300 ms p95 |
| Metadata read API | < 200 ms p95 |
| Standard search | < 1.0 s p95 |
| Hybrid retrieval + rerank | < 2.0 s p95 |
| First AI token | < 3.5 s p95 |
| Normal grounded answer | < 10 s p95 |
| Cached answer | < 500 ms p95 |
| Document upload acknowledgement | < 1 s |
| Ingestion processing | asynchronous |

---

# 4. Architecture Principles

## 4.1 Do not make the LLM the system core

The knowledge platform must remain usable even if:

- One LLM provider is unavailable.
- Embedding models are replaced.
- Rerankers are changed.
- A private model is introduced.
- API pricing changes.

LLM, embedding, and reranking capabilities must therefore sit behind adapters.

---

## 4.2 Separate authoritative data from search indexes

**PostgreSQL** is the source of truth for:

- users
- groups
- roles
- departments
- document metadata
- document versions
- permissions
- approval state
- conversations
- feedback
- tasks
- audit records

**OpenSearch** is a derived search index.

The search index may be rebuilt. PostgreSQL remains authoritative.

---

## 4.3 File storage is separate from metadata storage

Binary files must not be stored in relational database BLOB columns.

Use object storage for:

- PDF
- DOCX
- XLSX
- PPTX
- images
- extracted artifacts
- thumbnails
- parsed structure
- previews

---

## 4.4 All large processing is asynchronous

The following operations must never execute inside normal HTTP request lifecycles:

- OCR
- PDF parsing
- Office parsing
- metadata extraction
- chunk generation
- embedding generation
- large indexing jobs
- sync jobs
- bulk deletion
- backfills
- re-embedding
- re-indexing

These operations use a job queue and scalable workers.

---

## 4.5 Every answer must be permission-aware

Permission filtering must happen before content becomes available to the LLM.

The system must not:

1. retrieve unauthorized content,
2. pass it to the LLM,
3. then hide it afterward.

Authorization must be enforced at retrieval time.

---

# 5. High-Level Architecture

```text
                         ┌─────────────────────────────┐
                         │       Siong GPT Web         │
                         │ Next.js / React / TypeScript│
                         └──────────────┬──────────────┘
                                        │ HTTPS
                                        ▼
                         ┌─────────────────────────────┐
                         │ API Gateway / Load Balancer │
                         └──────────────┬──────────────┘
                                        │
                  ┌─────────────────────┴─────────────────────┐
                  ▼                                           ▼
        ┌──────────────────┐                       ┌──────────────────┐
        │ FastAPI Instance │ ... horizontally ... │ FastAPI Instance │
        └────────┬─────────┘                       └────────┬─────────┘
                 │                                          │
                 └─────────────────┬────────────────────────┘
                                   │
              ┌────────────────────┼────────────────────────┐
              ▼                    ▼                        ▼
       ┌──────────────┐      ┌──────────────┐        ┌──────────────┐
       │ PostgreSQL   │      │ Redis        │        │ OpenSearch   │
       │ Source Truth │      │ Cache/Queue  │        │ Search Index │
       └──────┬───────┘      └──────┬───────┘        └──────┬───────┘
              │                     │                       │
              │                     ▼                       │
              │             ┌─────────────────┐             │
              │             │ Worker Cluster  │             │
              │             │ Parse/Embed/ETL │             │
              │             └────────┬────────┘             │
              │                      │                      │
              ▼                      ▼                      ▼
       ┌──────────────┐       ┌──────────────┐       ┌──────────────┐
       │ Audit / ACL  │       │ Object Store │       │ Retrieval    │
       │ Metadata     │       │ Files        │       │ Pipeline     │
       └──────────────┘       └──────────────┘       └──────┬───────┘
                                                            │
                                                            ▼
                                                   ┌──────────────────┐
                                                   │    LLM Gateway   │
                                                   └──────────────────┘
```

---

# 6. Frontend Architecture

## 6.1 Framework

Use:

- Next.js
- React
- TypeScript
- Tailwind CSS
- shadcn/ui
- TanStack Query

---

## 6.2 Reusable application shell

The Siong GPT page must not be implemented as a standalone page with duplicated navigation.

Use a reusable shell:

```text
src/
├── app/
│   ├── login/
│   ├── gpt/
│   ├── knowledge/
│   ├── documents/
│   ├── tasks/
│   ├── notifications/
│   └── admin/
│
├── components/
│   ├── layout/
│   │   ├── AppShell.tsx
│   │   ├── Sidebar.tsx
│   │   ├── Header.tsx
│   │   ├── PageContainer.tsx
│   │   └── ContextPanel.tsx
│   │
│   ├── gpt/
│   │   ├── SearchBar.tsx
│   │   ├── AnswerCard.tsx
│   │   ├── CitationCard.tsx
│   │   ├── RelatedKnowledge.tsx
│   │   ├── RelatedSystems.tsx
│   │   └── RelatedQuestions.tsx
│   │
│   ├── documents/
│   ├── knowledge/
│   ├── tasks/
│   └── common/
```

All future pages reuse:

- Sidebar
- Header
- Responsive layout
- Auth context
- Notification system
- Workspace switcher
- Permission-aware navigation

---

## 6.3 Frontend performance

For large-scale employee access:

- Use CDN for static assets.
- Use route-based code splitting.
- Lazy-load non-critical panels.
- Paginate large tables.
- Virtualize very large lists.
- Avoid fetching full documents unless needed.
- Use request deduplication through TanStack Query.
- Cache safe read-only metadata.
- Stream LLM responses.
- Use WebSocket or Server-Sent Events only where needed.

---

# 7. Backend Architecture

## 7.1 Initial backend pattern

Use a **modular monolith**.

Recommended FastAPI structure:

```text
backend/
├── app/
│   ├── auth/
│   ├── users/
│   ├── departments/
│   ├── groups/
│   ├── knowledge/
│   ├── documents/
│   ├── ingestion/
│   ├── retrieval/
│   ├── chat/
│   ├── permissions/
│   ├── citations/
│   ├── feedback/
│   ├── tasks/
│   ├── notifications/
│   ├── connectors/
│   ├── audit/
│   └── admin/
│
├── workers/
│   ├── parse/
│   ├── chunk/
│   ├── embed/
│   ├── index/
│   ├── sync/
│   └── maintenance/
│
└── core/
    ├── db/
    ├── storage/
    ├── search/
    ├── llm/
    ├── queue/
    ├── config/
    └── security/
```

---

## 7.2 Stateless API servers

API servers must be stateless.

Do not store sessions in process memory.

State should live in:

- database
- Redis
- object storage

This allows:

```text
1 API instance
→ 5 instances
→ 20 instances
→ 100 instances
```

without changing application logic.

---

# 8. Load Balancing and High Concurrency

## 8.1 API ingress

Use:

```text
Internet / Enterprise Network
        │
        ▼
WAF
        │
        ▼
Load Balancer / API Gateway
        │
        ├──── FastAPI Pod 1
        ├──── FastAPI Pod 2
        ├──── FastAPI Pod 3
        └──── FastAPI Pod N
```

Scale API nodes based on:

- CPU
- memory
- requests per second
- p95 latency
- active connections

---

## 8.2 Database connection pooling

Large employee concurrency can destroy PostgreSQL if every application request creates a separate database connection.

Use:

- application-side pooling
- PgBouncer or equivalent
- bounded connection limits

Example:

```text
3,000 concurrent users
        │
        ▼
100 API workers
        │
        ▼
PgBouncer
        │
        ▼
100–300 PostgreSQL connections
```

Never map one user session to one persistent DB connection.

---

## 8.3 Read replicas

At scale:

```text
                   ┌── PostgreSQL Read Replica 1
Primary PostgreSQL ├── PostgreSQL Read Replica 2
                   └── PostgreSQL Read Replica N
```

Primary handles:

- transactions
- permissions changes
- document metadata writes
- approval
- user writes

Replicas handle:

- analytics
- reporting
- read-heavy metadata APIs
- admin dashboards

Do not use replicas for permission checks if unacceptable replication lag could expose stale access.

---

# 9. PostgreSQL Data Model

Core tables:

```text
users
departments
groups
roles
user_groups
user_roles

documents
document_versions
document_sources
document_tags
document_permissions
document_acl_entries

ingestion_jobs
sync_jobs

conversations
messages
citations

feedback

tasks
notifications

audit_logs
```

---

## 9.1 Documents

```text
documents
---------
id
title
department_id
owner_id
document_type
current_version_id
status
confidentiality_level
source_system
created_at
updated_at
```

---

## 9.2 Document versions

```text
document_versions
-----------------
id
document_id
version_number
storage_uri
checksum
effective_from
effective_to
status
approved_by
approved_at
created_at
```

Do not overwrite a historical version.

---

## 9.3 Knowledge Passport

Knowledge Passport fields are first-class metadata:

```text
document_id
title
department
owner
document_type
version
status
effective_from
effective_to
project_scope
confidentiality
source_system
source_uri
checksum
created_at
updated_at
```

---

# 10. PostgreSQL Scalability Strategy

## 10.1 Indexes

Indexes should exist on high-cardinality or frequent query columns such as:

```text
documents.department_id
documents.status
documents.current_version_id

document_versions.document_id
document_versions.status

document_permissions.document_id
document_permissions.principal_id

messages.conversation_id
messages.created_at

audit_logs.created_at
audit_logs.user_id
```

---

## 10.2 Table partitioning

Very large append-only tables should use partitioning.

Recommended candidates:

- audit_logs
- messages
- ingestion_jobs
- sync_jobs
- notifications

Example:

```text
audit_logs_2026_09
audit_logs_2026_10
audit_logs_2026_11
```

Partition by month or quarter.

---

## 10.3 Archival

Do not keep all historical operational data in hot storage forever.

Use lifecycle policies:

```text
Hot PostgreSQL
    ↓
Archive storage
    ↓
Analytics warehouse / cold object storage
```

---

# 11. Object Storage

Binary documents should live in object storage.

Recommended hierarchy:

```text
/documents/
  /{department}/
    /{document_id}/
      /{version_id}/
        original.pdf
        extracted.json
        preview.pdf
        thumbnail.png
```

Object storage must support:

- encryption at rest
- versioning
- retention policies
- lifecycle rules
- signed URLs
- large object upload
- multipart upload

---

# 12. Search Architecture

## 12.1 Use OpenSearch as the search layer

OpenSearch handles:

- BM25
- vector search
- metadata filtering
- ACL filtering
- sorting
- faceting
- document title search
- chunk search

---

## 12.2 Why not only pgvector

pgvector can support smaller deployments.

However, the production design should assume:

- tens of millions of chunks
- hybrid retrieval
- high query concurrency
- metadata filters
- ACL filters
- search analytics

Therefore OpenSearch is the recommended production search layer.

---

# 13. Search Index Design

Example chunk document:

```json
{
  "chunk_id": "uuid",
  "document_id": "uuid",
  "version_id": "uuid",

  "title": "Supplier Payment SOP",
  "section_title": "Required Documents",
  "content": "...",

  "page_number": 12,

  "department": "Finance",
  "project_ids": ["P100", "P200"],

  "status": "approved",
  "effective_from": "2026-09-01",

  "allowed_group_ids": ["finance_staff"],
  "allowed_user_ids": [],

  "embedding": []
}
```

---

# 14. OpenSearch Horizontal Scaling

For large datasets:

```text
OpenSearch Cluster

Master Nodes
  × 3

Data Nodes
  × N

Coordinating Nodes
  × N
```

Use:

- index sharding
- replicas
- lifecycle management
- hot / warm tiers if required

Do not place the entire enterprise index into one shard.

Shard count should be based on actual index size and cluster benchmarks.

---

# 15. Hybrid Retrieval

Retrieval pipeline:

```text
User Query
    │
    ├──── BM25
    │
    └──── Vector Search
            │
            ▼
          Merge
            │
            ▼
      Permission Filter
            │
            ▼
         Reranker
            │
            ▼
       Top Context
```

Use reciprocal rank fusion or equivalent merging.

---

# 16. Permission Architecture

The system must support:

- role-based access control
- department access
- project access
- user-level grants
- group-level grants
- document-level ACL
- optional field-level masking
- temporary permissions

---

## 16.1 Retrieval-time enforcement

Incorrect:

```text
Search everything
→ retrieve restricted content
→ send to LLM
→ hide later
```

Correct:

```text
Authenticated User
        │
        ▼
Permission Context
        │
        ▼
Search Filter
        │
        ▼
Authorized Chunks Only
        │
        ▼
LLM
```

---

# 17. Identity and Authentication

Preferred:

- Microsoft Entra ID
- OpenID Connect
- OAuth 2.0

Login flow:

```text
Browser
   │
   ▼
Microsoft Login
   │
   ▼
Entra ID
   │
   ▼
OIDC Token
   │
   ▼
Siong GPT Backend
```

Map Entra groups to application roles where possible.

---

# 18. Document Ingestion Pipeline

## 18.1 Upload path

```text
Upload
  │
  ▼
Virus Scan
  │
  ▼
Hash / Dedup
  │
  ▼
Object Storage
  │
  ▼
Create Metadata
  │
  ▼
Queue Job
  │
  ▼
Parse
  │
  ▼
Extract Structure
  │
  ▼
Classify
  │
  ▼
Chunk
  │
  ▼
Embedding
  │
  ▼
Index
  │
  ▼
Review
  │
  ▼
Publish
```

---

## 18.2 Ingestion state machine

```text
UPLOADED
PROCESSING
REVIEW_REQUIRED
APPROVED
PUBLISHED
SUPERSEDED
ARCHIVED
FAILED
```

---

# 19. Worker Architecture

Workers must be horizontally scalable.

```text
Redis / Queue
     │
 ┌───┼─────────────┐
 ▼   ▼             ▼
Parse Worker   Embed Worker   Index Worker
 ×N              ×N             ×N
```

Separate worker pools prevent slow OCR jobs from blocking indexing or embedding.

---

# 20. Backpressure

The queue must protect the platform from ingestion bursts.

For example:

```text
100,000 files uploaded
        │
        ▼
Queue
        │
        ▼
Workers process at controlled rate
```

Do not launch 100,000 concurrent parsing jobs.

Apply:

- queue priorities
- per-tenant / per-department limits
- retry limits
- dead-letter queue
- exponential backoff

---

# 21. Idempotency and Deduplication

Each document version should have:

```text
SHA-256 checksum
```

If source content has not changed:

```text
hash identical
→ skip reprocessing
```

If changed:

```text
create new version
→ parse
→ chunk
→ embed
→ index
→ publish new version
→ mark old version superseded
```

---

# 22. Chunking Strategy

Avoid fixed-size chunking only.

Use structure-aware chunking.

## Word

```text
Document
→ Heading
→ Subheading
→ Paragraph
```

## PDF

```text
Page
→ Section
→ Paragraph
→ Table
```

## Excel

```text
Workbook
→ Worksheet
→ Table
→ Row group
```

## PowerPoint

```text
Deck
→ Slide
→ Title
→ Body
→ Notes
```

---

# 23. AI Request Flow

```text
Employee Question
      │
      ▼
Authentication
      │
      ▼
Permission Context
      │
      ▼
Query Normalization
      │
      ▼
Hybrid Search
      │
      ▼
ACL / Metadata Filter
      │
      ▼
Reranking
      │
      ▼
Context Builder
      │
      ▼
LLM Gateway
      │
      ▼
Answer Validation
      │
      ▼
Citation Builder
      │
      ▼
Stream Response
```

---

# 24. LLM Gateway

All models must be accessed through one internal abstraction.

Example interface:

```python
class LLMGateway:
    async def generate(...)
    async def embed(...)
    async def rerank(...)
```

Responsibilities:

- provider abstraction
- model routing
- retries
- timeouts
- fallback
- cost tracking
- token tracking
- prompt versioning
- rate limiting
- safety rules
- request tracing

---

# 25. LLM Concurrency Control

Employee traffic can exceed model provider rate limits.

Do not send unlimited concurrent model requests.

Use:

- global rate limits
- per-user rate limits
- per-department limits
- provider quotas
- request queues
- circuit breakers
- fallback providers

Example:

```text
500 simultaneous questions
        │
        ▼
LLM Gateway
        │
        ├── Provider quota
        ├── Queue excess load
        └── Fallback model
```

---

# 26. Streaming

Use streaming responses to improve perceived latency.

The backend can send:

- Server-Sent Events
- chunked HTTP streaming

Frontend displays answer progressively.

This avoids keeping users on a blank screen during long model generation.

---

# 27. Caching Strategy

Redis may cache:

- permission context
- user profile
- common search results
- document metadata
- related knowledge results
- frequent prompts
- model rate-limit state

Do not blindly cache confidential answer text across users.

Cache keys must include relevant permission context.

Example:

```text
search:{query_hash}:{acl_hash}:{language}
```

---

# 28. Cache Invalidation

Invalidate cache when:

- document published
- document superseded
- permission changed
- group membership changed
- policy revoked

Security-sensitive permission caches should use short TTLs.

---

# 29. Recommended Actions

Recommended actions returned to the frontend must use approved action definitions.

Example:

```json
{
  "type": "SYSTEM_ACTION",
  "action": "OPEN_FINANCE_SYSTEM",
  "label": "Open Finance System",
  "permission": "finance.read"
}
```

The model must not generate arbitrary internal URLs.

---

# 30. Citation Architecture

Each answer citation should store:

```text
citation_id
message_id
document_id
version_id
chunk_id
page_number
section_title
quote_span
```

This allows users to open the exact source.

---

# 31. Verification Status

The UI may display:

- VERIFIED
- PARTIALLY_VERIFIED
- INSUFFICIENT_EVIDENCE

`VERIFIED` should require:

- source is approved
- source version is active
- user has permission
- critical claims have citations

---

# 32. Audit Logging

Record:

```text
user
timestamp
query
retrieved documents
retrieved versions
answer
citations
model
prompt version
actions
feedback
permission decision
```

Also log:

```text
document uploaded
document approved
document superseded
permission changed
role changed
connector sync
admin action
```

---

# 33. Audit Scalability

Audit logs grow quickly.

Use:

- time partitioning
- asynchronous log ingestion
- retention policies
- archive to object storage
- optional analytics pipeline

Never block user requests on slow audit persistence unless required for security.

---

# 34. Security

Minimum controls:

- TLS everywhere
- encryption at rest
- managed secrets
- MFA via identity provider
- RBAC
- document ACL
- request validation
- CSRF protection where applicable
- secure cookies
- rate limiting
- WAF
- virus scanning
- malware protection
- dependency scanning
- container scanning
- audit logs

---

# 35. Sensitive Data

Potential sensitive fields:

- bank account information
- NRIC / identifiers
- salary
- supplier banking data
- employee personal information

Support:

- field masking
- chunk exclusion
- content classification
- restricted indexes
- permission-based rendering

---

# 36. API Rate Limiting

Example default limits:

| API | Limit |
|---|---:|
| Search | 60 req/min/user |
| AI question | 20 req/min/user |
| Document upload | 20 req/min/user |
| Admin bulk operations | role-dependent |

Also apply global cluster limits.

---

# 37. Resilience

Use:

- request timeout
- retry policy
- circuit breaker
- dead-letter queue
- bulkhead isolation
- provider fallback

Example:

```text
OpenAI unavailable
   │
   ▼
LLM Gateway
   │
   ├── Retry
   ├── Fallback provider
   └── Graceful error
```

---

# 38. Failure Isolation

A failed OCR job must not affect:

- user login
- normal search
- existing knowledge queries

A failed embedding provider must not take down:

- document metadata
- existing search
- document downloads

---

# 39. Deployment Architecture

Recommended production model:

```text
                   ┌─────────────────┐
                   │ CDN / WAF       │
                   └────────┬────────┘
                            │
                   ┌────────▼────────┐
                   │ Load Balancer   │
                   └────────┬────────┘
                            │
                 ┌──────────┴──────────┐
                 ▼                     ▼
         Frontend Cluster        API Cluster
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
         PostgreSQL          OpenSearch           Redis
              │                                     │
              ▼                                     ▼
        Object Storage                        Worker Cluster
```

---

# 40. Autoscaling

Autoscale:

### API

Based on:

- CPU
- memory
- request rate
- p95 latency

### Workers

Based on:

- queue depth
- oldest message age
- CPU
- job completion time

### Search

Scale OpenSearch data nodes based on:

- index size
- CPU
- JVM pressure
- query latency

---

# 41. Environment Separation

Required environments:

```text
local
development
staging
production
```

Production must use isolated:

- databases
- search clusters
- Redis
- object storage
- secrets

---

# 42. Local Development

Use Docker Compose:

```text
Frontend
Backend
PostgreSQL
Redis
MinIO
OpenSearch
Worker
```

Expected startup:

```bash
docker compose up
```

---

# 43. CI/CD

Recommended pipeline:

```text
Pull Request
    │
    ▼
Lint
    │
    ▼
Unit Tests
    │
    ▼
Integration Tests
    │
    ▼
Build Docker Image
    │
    ▼
Security Scan
    │
    ▼
Deploy Staging
    │
    ▼
Smoke Test
    │
    ▼
Manual Approval
    │
    ▼
Production
```

---

# 44. Database Migrations

Use Alembic.

Never perform schema changes manually in production.

All migrations must be:

- versioned
- reviewed
- reversible where possible
- tested on staging

---

# 45. Observability

Collect:

## Infrastructure

- CPU
- memory
- disk
- network
- pod count

## API

- request count
- error rate
- latency
- status codes

## Database

- active connections
- slow queries
- lock waits
- replica lag

## Redis

- memory
- hit rate
- queue depth

## OpenSearch

- search latency
- indexing latency
- shard health
- JVM pressure

## Workers

- queue depth
- throughput
- failed jobs

## AI

- request count
- tokens
- latency
- provider failures
- fallback rate
- cost

---

# 46. Business Observability

Track:

- daily active users
- questions per day
- searches per day
- helpful-answer percentage
- no-answer percentage
- citation coverage
- top knowledge gaps
- most referenced documents
- outdated document alerts
- department usage
- average answer latency

---

# 47. Distributed Tracing

A single employee query should have one trace ID across:

```text
Frontend
→ API
→ Redis
→ OpenSearch
→ Reranker
→ LLM
→ PostgreSQL
```

Use OpenTelemetry.

---

# 48. Availability Targets

Suggested future production SLO:

| Metric | Target |
|---|---:|
| API availability | 99.9% |
| Search availability | 99.9% |
| Authentication availability | 99.9% |
| Monthly data durability | provider dependent, enterprise-grade |
| p95 standard search | < 1s |
| p95 grounded AI response | < 10s |

---

# 49. Backup and Disaster Recovery

## PostgreSQL

- continuous backup
- point-in-time recovery
- cross-zone replica

## Object storage

- versioning
- lifecycle policy
- optional cross-region replication

## OpenSearch

- snapshots

## Redis

Redis is not the primary source of truth.

---

# 50. Recovery Objectives

Suggested targets:

```text
RPO: <= 15 minutes
RTO: <= 2 hours
```

Critical knowledge metadata may justify stricter targets later.

---

# 51. Large Data Re-indexing

The system must support re-indexing without taking production search offline.

Use index aliases:

```text
knowledge_v1
knowledge_v2
```

Build:

```text
knowledge_v2
```

Then atomically switch:

```text
knowledge_current
→ knowledge_v2
```

---

# 52. Zero-Downtime Model Migration

When changing embeddings:

Do not overwrite all existing vectors in place.

Use:

```text
embedding_v1
embedding_v2
```

Index in parallel and switch when validated.

---

# 53. Connector Architecture

Future connectors:

- SharePoint
- OneDrive
- internal Finance system
- Project system
- Safety system
- HR system
- ERP
- email
- file shares

Implement:

```text
ConnectorInterface

list_changes()
fetch_document()
fetch_metadata()
fetch_permissions()
```

---

# 54. Incremental Synchronization

Prefer delta/change APIs.

Do not repeatedly scan entire repositories.

Flow:

```text
Last Sync Cursor
      │
      ▼
Fetch Changes
      │
      ▼
Create / Update / Delete
      │
      ▼
Queue Processing
      │
      ▼
Save New Cursor
```

---

# 55. Deletion and Revocation

If a source document is deleted or permission revoked:

1. Update authoritative metadata.
2. Invalidate cache.
3. Remove / disable search chunks.
4. Ensure future retrieval cannot access it.
5. Preserve audit history if legally permitted.

---

# 56. Multi-Tenancy Readiness

Even if initial deployment is for one company, use logical boundaries such as:

```text
organization_id
workspace_id
department_id
```

This supports future deployment to:

- subsidiaries
- project companies
- external clients

without redesigning every table.

---

# 57. Finance Pilot Scope

The Finance pilot should exercise the production architecture rather than use a separate demo stack.

Initial capabilities:

- enterprise login
- Finance knowledge space
- approved document upload
- versioned documents
- metadata
- permission filtering
- hybrid search
- grounded AI
- citations
- related documents
- related systems
- feedback
- audit logging
- admin review / publish flow

---

# 58. Phase 1 Implementation

Build first:

1. AppShell and login.
2. OIDC / mock enterprise auth.
3. PostgreSQL schema.
4. Object storage adapter.
5. Redis.
6. Upload API.
7. ingestion queue.
8. parser workers.
9. chunker.
10. embedding adapter.
11. OpenSearch.
12. hybrid retrieval.
13. permission context.
14. LLM Gateway.
15. citation builder.
16. Siong GPT page.
17. document admin page.
18. publish workflow.
19. audit logs.
20. basic observability.

---

# 59. Phase 2

Add:

- SharePoint integration
- automatic sync
- more Office formats
- document approval workflows
- related systems
- notifications
- task actions
- knowledge health dashboard
- stale knowledge detection
- query analytics
- knowledge gap analytics

---

# 60. Phase 3

Add:

- workflow execution
- agent tools
- internal system actions
- proactive notifications
- department-specific agents
- advanced knowledge governance
- cross-company / subsidiary support

---

# 61. Important Anti-Patterns

Do not:

- store all PDFs in PostgreSQL
- use only vector similarity
- put all logic into one FastAPI file
- run OCR during HTTP requests
- create one DB connection per user
- retrieve unauthorized chunks before filtering
- directly hard-code one model provider
- let the model invent internal URLs
- overwrite document versions
- re-embed the entire library on every sync
- use one OpenSearch shard for the whole enterprise
- keep all audit logs in one unpartitioned table
- make API servers stateful
- rely on browser-side authorization
- expose object storage directly without signed access

---

# 62. Reference Production Stack

```text
Frontend
Next.js
React
TypeScript
Tailwind
shadcn/ui

Backend
FastAPI
Python

Auth
Microsoft Entra ID
OIDC

Primary Database
PostgreSQL
PgBouncer

Storage
Azure Blob / S3 / MinIO

Search
OpenSearch

Cache
Redis

Queue
Redis Streams / Celery-compatible queue
or managed equivalent

Workers
Python worker containers

AI
LLM Gateway
Embedding Gateway
Reranker Gateway

Observability
OpenTelemetry
Prometheus-compatible metrics
Central logs

Deployment
Docker
Kubernetes / Container Apps / ECS-equivalent
```

---

# 63. Scalability Summary

The platform supports large employee concurrency because:

- frontend assets are CDN-delivered
- API servers are stateless
- API instances scale horizontally
- database connections are pooled
- read replicas can serve read-heavy workloads
- Redis absorbs repeated reads
- search workload is separated into OpenSearch
- AI requests are rate-limited and queued
- responses are streamed
- workers scale independently
- ingestion never blocks user traffic

The platform supports large knowledge volumes because:

- files live in object storage
- PostgreSQL stores only authoritative metadata
- search data lives in a distributed OpenSearch cluster
- indexes are sharded
- document processing is asynchronous
- document updates are incremental
- hashing prevents duplicate processing
- document versions are immutable
- large tables are partitioned
- cold data can be archived
- embeddings can be migrated incrementally

---

# 64. Final Architecture Decision

For the first production implementation, adopt:

> **Next.js + FastAPI + PostgreSQL + PgBouncer + Object Storage + OpenSearch + Redis + Async Worker Cluster + Microsoft Entra ID + LLM Gateway**

Use a **modular monolith for core application logic**, but deploy **API, ingestion workers, search, database, storage, Redis, and AI gateway as independently scalable infrastructure components**.

This gives the Finance pilot a practical implementation path while preserving a production architecture capable of supporting enterprise-wide rollout, very large knowledge stores, and high numbers of concurrent employees without requiring a fundamental rewrite.
