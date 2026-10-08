# Phase 4.5 integration gate

This gate validates Phase 1–4 against isolated PostgreSQL/pgvector and the pinned
real E5 model. It does not add product features. A skipped mandatory online test is
a failed gate, not a pass.

## Test topology and isolation

`infra/docker-compose.test.yml` runs `pgvector/pgvector:pg16` as the Compose project
`sionggpt-integration-gate`:

- container: `sionggpt-test-postgres`
- host binding: `127.0.0.1:55432`
- primary database: `sionggpt_test`
- destructive migration-cycle database: `sionggpt_migration_test`
- test user: `sionggpt_test_user`
- volume: `sionggpt_test_pgdata_phase45`

It does not reuse the development `postgres_data` volume. The password is required
at runtime and has no source-controlled default. Database URLs and passwords must
not be committed.

## Start and stop

Set a session-only password without printing it, then construct the two URLs using
the same URL-encoded value:

```powershell
$gateSecret = Read-Host 'Local gate database password' -AsSecureString
$gateCredential = [pscredential]::new('sionggpt_test_user', $gateSecret)
$gatePassword = $gateCredential.GetNetworkCredential().Password
$gateEncodedPassword = [Uri]::EscapeDataString($gatePassword)
$env:SIONGGPT_TEST_DB_PASSWORD = $gatePassword
$env:TEST_DATABASE_URL = "postgresql+psycopg://sionggpt_test_user:${gateEncodedPassword}@127.0.0.1:55432/sionggpt_test"
$env:TEST_MIGRATION_DATABASE_URL = "postgresql+psycopg://sionggpt_test_user:${gateEncodedPassword}@127.0.0.1:55432/sionggpt_migration_test"
$env:ALLOW_DESTRUCTIVE_DB_TESTS = 'true'
docker compose -p sionggpt-integration-gate -f infra/docker-compose.test.yml up -d --wait
```

Normal stop preserves the isolated volume:

```powershell
docker compose -p sionggpt-integration-gate -f infra/docker-compose.test.yml down
```

Only when an intentionally fresh gate is required, the exact test project volume
may be removed with the explicit command below. This is never done by a script:

```powershell
docker compose -p sionggpt-integration-gate -f infra/docker-compose.test.yml down --volumes
```

Never use `docker system prune` or `docker volume prune`.

## Destructive-test protection

Before connecting, the guard requires all of the following:

1. `ALLOW_DESTRUCTIVE_DB_TESTS` is exactly `true`.
2. The driver is PostgreSQL.
3. The database name contains a distinct `test` token.
4. The name contains no production, staging, or development marker.
5. The host is localhost, loopback, or an explicitly allowlisted CI host.
6. The target differs from `DATABASE_URL`.
7. Primary and migration-cycle URLs are different.
8. The connected `current_database()` equals the protected URL database.

The user-shell runner captures the development database identity before any test
runtime override, using the same application `Settings` and `.env` loading path.
It passes that value only in the current process tree as
`BASELINE_DEVELOPMENT_DATABASE_URL`. During integration tests, runtime
`DATABASE_URL` is intentionally the Primary Test DB; guards compare test targets
to the captured baseline, never to this overridden runtime value. The baseline is
not printed, written to a file, or retained after the PowerShell runner exits. An
unparseable or unavailable baseline fails closed.

The runner also requires fresh databases and refuses to drop or reset a reused
database. CI hosts must be explicitly listed in `INTEGRATION_TEST_CI_HOSTS`.

## Pinned model preparation

The only accepted model is `intfloat/multilingual-e5-small` at revision
`fd1525a9fd15316a2d503bf26ab031a61d056e98`. Choose a target outside the repository.
Checking is the default and performs no download:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\prepare_embedding_model.py --target D:\approved-models\multilingual-e5-small
```

Download requires the explicit flag:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_embedding_model.py --target D:\approved-models\multilingual-e5-small --download
```

The script accepts no arbitrary repo or revision, never enables remote code, uses
a temporary sibling directory, atomically renames on success, and writes a
manifest containing repo ID, revision, timestamp, relative file list and sizes.
It does not edit `.env`. Keep `EMBEDDING_ALLOW_DOWNLOAD=false` for normal runtime.

## Running the gate

The preferred entry point on Windows is the user-shell runner. It sets
`DOCKER_CONTEXT=desktop-linux` only for its process, generates a random in-memory
database password, starts only the isolated Compose project, creates two fresh
per-run test databases, validates or downloads the pinned external model, runs the
Gate, and stops the test project while preserving its Volume:

```powershell
& .\backend\scripts\run_phase45_from_user_shell.ps1 -DownloadModel
```

Subsequent runs omit `-DownloadModel`. An explicit `-ResetTestDatabase` additionally
removes only `sionggpt_test_pgdata_phase45` after verifying its exact Compose
project and volume labels. Every normal run uses new randomized database names
inside the preserved isolated Volume, so clean migrations do not require a reset.

Point `EMBEDDING_MODEL_LOCAL_PATH` at the checked external directory, then run:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\run_integration_gate.py --json-output integration-gate-result.json
```

The runner enforces protection, checks PostgreSQL/model readiness, performs the
clean upgrade and isolated downgrade/re-upgrade cycle, runs the required online
tests, emits human and JSON results, and exits nonzero for failures, blockers or
mandatory skips. It never downloads a model, deletes a volume, changes production
configuration or runs against a database that fails the guard.

The runner also refuses to pass while either the real retrieval-evaluation suite
or full vertical-slice suite is absent. Those suites must be implemented and
verified in the runnable integration environment; a file-presence check is not a
substitute for executing them, and mandatory skips remain failures.

## Online validation scope

The PostgreSQL suite performs real writes for extension/schema/index discovery,
Source Version uniqueness/current/state checks, Job and Chunk constraints,
generated TSVECTOR updates, PO/DO/GST/code lookup, one-ACTIVE Profile enforcement,
`vector(384)` dimension rejection, cosine calculation, HNSW query execution,
`SKIP LOCKED`, lease fencing, concurrent row-locked version allocation, publication
rollback and Chunk replacement rollback.

Real E5 tests are separate from Fake Provider tests. They check 384 dimensions,
normalization, English, Chinese, both cross-language directions, mixed language,
batch/single agreement, repeatability and the pinned revision. The fixture remains
fictional; no company documents may be introduced.

## Gate decision

`PASSED` requires every mandatory database, concurrency, vector, real-model,
retrieval-evaluation, permission and vertical-slice test to execute without skips
or failures. Missing Docker, database, model, disk, or permissions means `BLOCKED`.
An observed functional/security failure means `NOT PASSED`. Phase 5 may start only
after a complete `PASSED` result.

## Troubleshooting

- Docker pipe missing: start/install Docker Desktop manually; do not modify ACLs or bypass the daemon.
- Docker config access denied: correct it through the owning user/administrator; the gate does not alter ACLs.
- WSL enumeration denied: resolve Windows/WSL permissions before relying on WSL2.
- Database not fresh: explicitly remove only the named test volume if its contents are disposable.
- Model check failed: verify the external directory, marker and manifest; never substitute another model.
- Low disk space: free or attach approved storage before downloading the model or creating the test volume.
