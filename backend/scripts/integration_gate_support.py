from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import URL, make_url


PINNED_MODEL_REPO = "intfloat/multilingual-e5-small"
PINNED_MODEL_REVISION = "fd1525a9fd15316a2d503bf26ab031a61d056e98"
BASELINE_DATABASE_ENV = "BASELINE_DEVELOPMENT_DATABASE_URL"
LOCAL_DATABASE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
FORBIDDEN_DATABASE_MARKERS = frozenset({"prod", "production", "staging", "stage", "dev", "development"})


class IntegrationGateSafetyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProtectedDatabase:
    url: URL
    database: str
    host: str

    @property
    def redacted_url(self) -> str:
        return self.url.render_as_string(hide_password=True)


def _database_target(url: URL) -> tuple[str, int | None, str | None]:
    host = (url.host or "").lower()
    normalized_host = "loopback" if host in LOCAL_DATABASE_HOSTS else host
    port = url.port
    if port is None and url.drivername.startswith("postgresql"):
        port = 5432
    return normalized_host, port, url.database


def resolve_baseline_development_database_url(environment: dict[str, str]) -> str:
    explicit = environment.get(BASELINE_DATABASE_ENV)
    if explicit:
        return explicit
    runtime_before_override = environment.get("DATABASE_URL")
    if runtime_before_override:
        return runtime_before_override
    try:
        from app.core.config import settings

        configured = settings.database_url
    except Exception as exc:
        raise IntegrationGateSafetyError(
            "Baseline development database identity could not be loaded safely"
        ) from exc
    if not configured:
        raise IntegrationGateSafetyError(
            "Baseline development database identity is required"
        )
    return configured


def require_distinct_test_databases(primary: ProtectedDatabase, migration: ProtectedDatabase) -> None:
    primary_target = _database_target(primary.url)
    migration_target = _database_target(migration.url)
    if primary_target == migration_target:
        raise IntegrationGateSafetyError("Primary and migration test databases must be different")


def require_protected_test_database(
    raw_url: str | None,
    *,
    allow_destructive: str | None,
    development_url: str | None = None,
    allowed_ci_hosts: tuple[str, ...] = (),
) -> ProtectedDatabase:
    if allow_destructive != "true":
        raise IntegrationGateSafetyError("ALLOW_DESTRUCTIVE_DB_TESTS must be exactly 'true'")
    if not raw_url:
        raise IntegrationGateSafetyError("A dedicated test database URL is required")
    try:
        url = make_url(raw_url)
    except Exception as exc:
        raise IntegrationGateSafetyError("The test database URL is invalid") from exc
    if not url.drivername.startswith("postgresql"):
        raise IntegrationGateSafetyError("Only PostgreSQL is allowed for the integration gate")
    database = (url.database or "").lower()
    tokens = {token for token in database.replace("-", "_").split("_") if token}
    if "test" not in tokens:
        raise IntegrationGateSafetyError("The database name must contain a distinct 'test' marker")
    if tokens.intersection(FORBIDDEN_DATABASE_MARKERS):
        raise IntegrationGateSafetyError("Production, staging, and development database names are forbidden")
    host = (url.host or "").lower()
    permitted_hosts = LOCAL_DATABASE_HOSTS.union(value.lower() for value in allowed_ci_hosts)
    if host not in permitted_hosts:
        raise IntegrationGateSafetyError("The database host is not an approved local or CI test host")
    if development_url:
        try:
            development = make_url(development_url)
        except Exception as exc:
            raise IntegrationGateSafetyError(
                "Baseline development database identity is invalid"
            ) from exc
        if not development.database:
            raise IntegrationGateSafetyError(
                "Baseline development database name is required"
            )
        same_target = _database_target(development) == _database_target(url)
        if same_target:
            raise IntegrationGateSafetyError("The test database must not be the configured development database")
    return ProtectedDatabase(url=url, database=database, host=host)


def allowed_ci_hosts_from_environment() -> tuple[str, ...]:
    return tuple(
        item.strip() for item in os.getenv("INTEGRATION_TEST_CI_HOSTS", "").split(",")
        if item.strip()
    )


def assert_model_directory(path: str | os.PathLike[str]) -> Path:
    directory = Path(path).expanduser().resolve()
    if not directory.is_dir():
        raise IntegrationGateSafetyError("The pinned local E5 model directory does not exist")
    marker_values = []
    for filename in (".siong-model-revision", "model_revision.txt"):
        marker = directory / filename
        if marker.is_file():
            marker_values.append(marker.read_text(encoding="utf-8").strip())
    if PINNED_MODEL_REVISION not in directory.parts and PINNED_MODEL_REVISION not in marker_values:
        raise IntegrationGateSafetyError("The local E5 model revision marker does not match")
    return directory


def ensure_outside_repository(target: Path, repository_root: Path) -> Path:
    resolved_target = target.expanduser().resolve()
    resolved_repository = repository_root.resolve()
    if resolved_target == resolved_repository or resolved_repository in resolved_target.parents:
        raise IntegrationGateSafetyError("Model files must be stored outside the repository")
    if resolved_target == Path(resolved_target.anchor):
        raise IntegrationGateSafetyError("A filesystem root cannot be used as the model target")
    return resolved_target
