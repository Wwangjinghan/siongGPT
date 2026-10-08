# SiongGPT

SiongGPT 是一个面向企业知识治理与检索的模块化平台。当前仓库已经完成从权限基础、资料版本治理、可靠摄取，到真实 E5 Embedding 与 PostgreSQL/pgvector Hybrid Retrieval 的主体实现，并正在完成 Phase 4.5 在线集成验收。

> 当前边界：Phase 5 尚未开始。仓库中没有实现 Agent Runtime、RAG Answer Agent 或自动知识发布。

## 当前进度

| 阶段 | 状态 | 已完成内容 |
| --- | --- | --- |
| Phase 1 · Platform Foundation | 已实现 | FastAPI 模块化单体、认证、Principal、统一 Permission Service、领域类型、PostgreSQL/pgvector 基础 |
| Phase 2 · Source Registry | 已实现 | Source、不可变 Source Version、安全流式上传、本地 Storage Adapter、版本发布/撤回、权限过滤与失败补偿 |
| Phase 3 · Ingestion Pipeline | 已实现 | 持久化 Job、Lease/Fencing、独立 Worker、安全 Parser、确定性 Chunk、PostgreSQL FTS、重试与恢复 |
| Phase 4 · Hybrid Retrieval | 已实现 | 固定版本 multilingual E5、Embedding Profile、pgvector、Exact/HNSW、FTS/Vector/Hybrid Search、权限安全过滤、Evaluation 基础 |
| Phase 4.5 · Integration Gate | 待最终在线重跑 | 隔离 PostgreSQL Compose、Migration Cycle、真实 E5 Evaluation、完整 Vertical Slice、全角色权限矩阵和用户侧安全 Runner 均已实现；已修复 Baseline Development DB 误判 |
| Phase 5 | 未开始 | 必须在 Phase 4.5 所有 mandatory online tests 无 skip、无 failure 后才能进入 |

最近一次离线回归结果：

```text
178 tests
159 passed
19 skipped（仅限需要 PostgreSQL/pgvector 或本地真实 E5 的在线测试）
0 failures
0 errors
```

Phase 4.5 Gate 不会把 mandatory skip 视为通过。当前仓库状态不能标记为 `READY FOR PHASE 5`，必须先在能够访问 Docker Desktop Server 的用户 PowerShell 中完成在线 Gate。

## 核心能力

- 统一认证、Principal 与默认拒绝的资源权限模型。
- COMPANY、DEPARTMENT、PERSONAL_DRAFT Scope；PROJECT 在没有可信 Membership 前默认拒绝。
- Source 与不可变 Source Version 分离，Processing 与 Publication 状态独立。
- 原始文件流式 SHA-256、大小和类型限制、原子写入、物理去重与路径穿越保护。
- TXT、PDF、DOCX、XLSX 安全解析边界，不包含 OCR。
- 可恢复 Ingestion Job、行级锁、`FOR UPDATE SKIP LOCKED`、Lease Fencing 和事务回滚。
- 固定 revision 的 `intfloat/multilingual-e5-small`，禁止静默在线下载和 `trust_remote_code`。
- PostgreSQL FTS、pgvector Exact/HNSW 与 RRF Hybrid Retrieval。
- 数据库查询阶段的权限过滤；物理文件或相同向量不会形成跨权限访问旁路。
- 独立测试数据库、独立 Volume、随机运行时密码和失败关闭的 destructive-test guard。

## 仓库结构

```text
backend/       FastAPI、SQLAlchemy、Alembic、Worker、测试与 Gate Runner
frontend/      Next.js App Router 前端
infra/         开发和隔离集成测试 Compose
docs/          各阶段工程文档与运行说明
公司图标/      品牌素材
界面图/        UI 参考图
```

本地 `.env`、虚拟环境、模型、缓存、数据库 Volume 和凭据文件不会进入版本控制。

## 快速开始

### Backend

```powershell
cd backend
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Backend 的数据库配置、依赖和检查命令见 [`backend/README.md`](backend/README.md)。

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend 默认运行于 `http://localhost:3000`。

## Phase 4.5 在线 Gate

请从能够访问 Docker Desktop Client 和 Server 的普通 PowerShell 运行：

```powershell
& '.\backend\scripts\run_phase45_from_user_shell.ps1'
```

首次尚未准备固定模型时，显式使用：

```powershell
& '.\backend\scripts\run_phase45_from_user_shell.ps1' -DownloadModel
```

Runner 只操作 Compose Project `sionggpt-integration-gate`，默认在结束后停止测试容器并保留独立测试 Volume。只有显式传入 `-ResetTestDatabase` 时，才会在核验精确 Project 与 Volume 身份后重建测试存储。

完整安全边界、数据库隔离、固定模型和验收项目见 [`docs/integration-gate.md`](docs/integration-gate.md)。

## 文档

- [Platform V1 Foundation](docs/platform-v1-foundation.md)
- [Source Registry 与不可变版本](docs/source-registry.md)
- [Reliable Ingestion Pipeline](docs/ingestion-pipeline.md)
- [Embedding 与 Hybrid Retrieval](docs/hybrid-retrieval.md)
- [Phase 4.5 Integration Gate](docs/integration-gate.md)

## 当前验收结论

```text
Gate Status: PENDING ONLINE RE-RUN
Phase 5 Decision: NOT READY
```

只有 Clean Migration Cycle、PostgreSQL/pgvector、并发与事务、真实 E5、Retrieval Evaluation、Vertical Slice 和全角色权限矩阵全部在线通过后，才允许更新为：

```text
Gate Status: PASSED
Phase 5 Decision: READY FOR PHASE 5
```
