from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine, text

from scripts.integration_gate_support import (
    BASELINE_DATABASE_ENV,
    IntegrationGateSafetyError,
    allowed_ci_hosts_from_environment,
    assert_model_directory,
    require_distinct_test_databases,
    require_protected_test_database,
    resolve_baseline_development_database_url,
)


PHASE4_PARENT = "e91c3b7d42a6"
MANDATORY_SUITE_FILES = (
    BACKEND_ROOT / "tests" / "integration" / "embedding" / "test_real_retrieval_evaluation.py",
    BACKEND_ROOT / "tests" / "integration" / "e2e" / "test_vertical_slice.py",
)


@dataclass(slots=True)
class CheckResult:
    name: str
    status: str
    detail: str


def run_command(name: str, command: list[str], environment: dict[str, str]) -> CheckResult:
    completed = subprocess.run(
        command,
        cwd=BACKEND_ROOT,
        env=environment,
        text=True,
        stdout=sys.stdout,
        stderr=sys.stderr,
        check=False,
    )
    return CheckResult(name, "PASS" if completed.returncode == 0 else "FAIL", f"exit_code={completed.returncode}")


def check_database(name: str, raw_url: str, expected_database: str, *, require_empty: bool = True) -> CheckResult:
    engine = create_engine(raw_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            actual = connection.scalar(text("SELECT current_database()"))
            connection.execute(text("SELECT 1"))
            existing_migration_table = connection.scalar(
                text("SELECT to_regclass('public.alembic_version')")
            )
        if actual != expected_database:
            return CheckResult(name, "FAIL", "Connected database identity differs from the protected URL")
        if require_empty and existing_migration_table is not None:
            return CheckResult(name, "FAIL", "Database is not fresh; the gate never drops or resets it automatically")
        return CheckResult(name, "PASS", f"database={actual}")
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Phase 4.5 integration gate.")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args(argv)
    results: list[CheckResult] = []
    environment = os.environ.copy()
    missing_suites = [str(path.relative_to(BACKEND_ROOT)) for path in MANDATORY_SUITE_FILES if not path.is_file()]
    if missing_suites:
        results.append(CheckResult(
            "mandatory_suite_manifest",
            "FAIL",
            "missing required suites: " + ", ".join(missing_suites),
        ))
    try:
        allowed_hosts = allowed_ci_hosts_from_environment()
        allow = environment.get("ALLOW_DESTRUCTIVE_DB_TESTS")
        development_url = resolve_baseline_development_database_url(environment)
        environment[BASELINE_DATABASE_ENV] = development_url
        primary = require_protected_test_database(
            environment.get("TEST_DATABASE_URL"),
            allow_destructive=allow,
            development_url=development_url,
            allowed_ci_hosts=allowed_hosts,
        )
        migration = require_protected_test_database(
            environment.get("TEST_MIGRATION_DATABASE_URL"),
            allow_destructive=allow,
            development_url=development_url,
            allowed_ci_hosts=allowed_hosts,
        )
        require_distinct_test_databases(primary, migration)
        results.append(CheckResult("database_safety", "PASS", "both targets passed destructive-test protection"))
        primary_url = primary.url.render_as_string(hide_password=False)
        migration_url = migration.url.render_as_string(hide_password=False)
        results.append(check_database("primary_postgres_readiness", primary_url, primary.database))
        results.append(check_database("migration_postgres_readiness", migration_url, migration.database))
        model_path = environment.get("EMBEDDING_MODEL_LOCAL_PATH", "")
        assert_model_directory(model_path)
        results.append(CheckResult("pinned_model", "PASS", "pinned revision marker verified"))
    except Exception as exc:
        results.append(CheckResult("preflight", "BLOCKED", str(exc)))

    if all(result.status == "PASS" for result in results):
        migration_environment = environment | {"DATABASE_URL": migration_url}
        for name, command in (
            ("migration_clean_upgrade", [sys.executable, "-m", "alembic", "upgrade", "head"]),
            ("migration_downgrade", [sys.executable, "-m", "alembic", "downgrade", PHASE4_PARENT]),
            ("migration_reupgrade", [sys.executable, "-m", "alembic", "upgrade", "head"]),
        ):
            results.append(run_command(name, command, migration_environment))
            if results[-1].status != "PASS":
                break
        if all(result.status == "PASS" for result in results):
            primary_environment = environment | {"DATABASE_URL": primary_url}
            results.append(run_command(
                "primary_clean_upgrade",
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                primary_environment,
            ))
            results.append(run_command(
                "required_online_tests",
                [sys.executable, "scripts/run_required_gate_tests.py"],
                primary_environment,
            ))

    gate_status = "PASSED" if results and all(item.status == "PASS" for item in results) else "BLOCKED" if any(item.status == "BLOCKED" for item in results) else "NOT PASSED"
    payload = {"gate_status": gate_status, "checks": [asdict(item) for item in results]}
    for result in results:
        print(f"[{result.status}] {result.name}: {result.detail}")
    print("GATE_RESULT_JSON=" + json.dumps(payload, sort_keys=True))
    if args.json_output:
        args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if gate_status == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
