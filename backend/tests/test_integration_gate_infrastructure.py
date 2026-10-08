import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.integration_gate_support import (
    BASELINE_DATABASE_ENV,
    PINNED_MODEL_REPO,
    PINNED_MODEL_REVISION,
    IntegrationGateSafetyError,
    assert_model_directory,
    ensure_outside_repository,
    require_distinct_test_databases,
    require_protected_test_database,
    resolve_baseline_development_database_url,
)
from scripts.prepare_embedding_model import REPOSITORY_ROOT, check_model, main as model_main


class DatabaseSafetyTests(unittest.TestCase):
    valid_url = "postgresql+psycopg://gate_user@127.0.0.1:55432/sionggpt_test"

    def test_all_safety_conditions_are_required(self):
        protected = require_protected_test_database(
            self.valid_url,
            allow_destructive="true",
            development_url="postgresql+psycopg://dev@127.0.0.1:5432/siong_gpt",
        )
        self.assertEqual(protected.database, "sionggpt_test")
        invalid_cases = (
            (self.valid_url, "TRUE", None),
            ("sqlite:///sionggpt_test.db", "true", None),
            ("postgresql+psycopg://u@127.0.0.1:55432/sionggpt", "true", None),
            ("postgresql+psycopg://u@db.example/sionggpt_test", "true", None),
            ("postgresql+psycopg://u@127.0.0.1/sionggpt_prod_test", "true", None),
            (self.valid_url, "true", self.valid_url),
        )
        for url, allow, development in invalid_cases:
            with self.subTest(url=url, allow=allow), self.assertRaises(IntegrationGateSafetyError):
                require_protected_test_database(
                    url, allow_destructive=allow, development_url=development
                )

    def test_explicit_ci_host_allowlist_is_supported(self):
        protected = require_protected_test_database(
            "postgresql+psycopg://u@postgres-ci/sionggpt_test",
            allow_destructive="true",
            allowed_ci_hosts=("postgres-ci",),
        )
        self.assertEqual(protected.host, "postgres-ci")

    def test_runtime_test_url_is_allowed_when_baseline_is_different(self):
        runtime_database_url = self.valid_url
        baseline = "postgresql+psycopg://dev_user@127.0.0.1:5432/siong_gpt"
        protected = require_protected_test_database(
            runtime_database_url,
            allow_destructive="true",
            development_url=baseline,
        )
        self.assertEqual(protected.database, "sionggpt_test")

    def test_test_url_equal_to_baseline_is_rejected_without_leaking_password(self):
        value = "postgresql+psycopg://gate_user:do-not-leak@127.0.0.1:55432/sionggpt_test"
        with self.assertRaises(IntegrationGateSafetyError) as raised:
            require_protected_test_database(
                value,
                allow_destructive="true",
                development_url=value,
            )
        self.assertNotIn("do-not-leak", str(raised.exception))
        with self.assertRaises(IntegrationGateSafetyError):
            require_protected_test_database(
                "postgresql+psycopg://gate@127.0.0.1:5432/sionggpt_test",
                allow_destructive="true",
                development_url="postgresql+psycopg://developer@localhost/sionggpt_test",
            )

    def test_invalid_or_unknown_baseline_identity_is_rejected(self):
        for baseline in ("not a database url", "postgresql+psycopg://developer@localhost"):
            with self.subTest(baseline=baseline), self.assertRaises(IntegrationGateSafetyError):
                require_protected_test_database(
                    self.valid_url,
                    allow_destructive="true",
                    development_url=baseline,
                )

    def test_primary_and_migration_targets_must_be_distinct(self):
        primary = require_protected_test_database(
            self.valid_url, allow_destructive="true"
        )
        duplicate = require_protected_test_database(
            self.valid_url, allow_destructive="true"
        )
        with self.assertRaises(IntegrationGateSafetyError):
            require_distinct_test_databases(primary, duplicate)

    def test_baseline_uses_existing_settings_loading_path(self):
        configured = "postgresql+psycopg://configured_user@127.0.0.1:5432/siong_gpt"
        with patch("app.core.config.settings.database_url", configured):
            self.assertEqual(resolve_baseline_development_database_url({}), configured)

    def test_explicit_baseline_precedes_runtime_database_url(self):
        environment = {
            BASELINE_DATABASE_ENV: "postgresql+psycopg://baseline@127.0.0.1/base",
            "DATABASE_URL": self.valid_url,
        }
        self.assertEqual(
            resolve_baseline_development_database_url(environment),
            environment[BASELINE_DATABASE_ENV],
        )


class ModelPreparationSafetyTests(unittest.TestCase):
    def test_repository_targets_are_rejected(self):
        with self.assertRaises(IntegrationGateSafetyError):
            ensure_outside_repository(REPOSITORY_ROOT / "models" / "e5", REPOSITORY_ROOT)

    def test_check_requires_pinned_marker_and_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / ".siong-model-revision").write_text(PINNED_MODEL_REVISION, encoding="utf-8")
            (directory / "config.json").write_text("{}", encoding="utf-8")
            manifest = {
                "repo_id": PINNED_MODEL_REPO,
                "revision": PINNED_MODEL_REVISION,
                "downloaded_at": "2026-01-01T00:00:00+00:00",
                "files": [{"path": "config.json", "size": 2}],
            }
            (directory / "model-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(check_model(directory)["revision"], PINNED_MODEL_REVISION)
            (directory / "config.json").write_text("changed", encoding="utf-8")
            with self.assertRaises(IntegrationGateSafetyError):
                check_model(directory)
            (directory / "config.json").write_text("{}", encoding="utf-8")
            (directory / ".siong-model-revision").write_text("wrong", encoding="utf-8")
            with self.assertRaises(IntegrationGateSafetyError):
                assert_model_directory(directory)

    def test_default_model_command_never_downloads(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "missing"
            with patch("scripts.prepare_embedding_model.download_model") as download:
                self.assertEqual(model_main(["--target", str(target)]), 2)
            download.assert_not_called()


class InfrastructureContractTests(unittest.TestCase):
    def test_compose_is_local_isolated_and_runtime_secret_only(self):
        compose = (REPOSITORY_ROOT / "infra" / "docker-compose.test.yml").read_text(encoding="utf-8")
        self.assertIn("pgvector/pgvector:pg16", compose)
        self.assertIn('127.0.0.1:55432:5432', compose)
        self.assertIn("sionggpt_test_pgdata_phase45", compose)
        self.assertNotIn("postgres_data", compose)
        self.assertIn("SIONGGPT_TEST_DB_PASSWORD:?", compose)

    def test_gate_runner_has_no_download_or_volume_delete(self):
        source = (REPOSITORY_ROOT / "backend" / "scripts" / "run_integration_gate.py").read_text(encoding="utf-8")
        self.assertNotIn("snapshot_download", source)
        self.assertNotIn("docker volume", source)
        self.assertNotIn("docker system", source)
        self.assertIn("TEST_MIGRATION_DATABASE_URL", source)
        self.assertIn("test_real_retrieval_evaluation.py", source)
        self.assertIn("test_vertical_slice.py", source)

    def test_gate_runner_direct_entrypoint_fails_closed(self):
        completed = subprocess.run(
            [sys.executable, "scripts/run_integration_gate.py"],
            cwd=REPOSITORY_ROOT / "backend",
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn('"gate_status": "BLOCKED"', completed.stdout)
        self.assertNotIn("Traceback", completed.stderr)

    def test_user_shell_runner_is_fail_closed_and_secret_safe(self):
        source = (REPOSITORY_ROOT / "backend" / "scripts" / "run_phase45_from_user_shell.ps1").read_text(encoding="utf-8")
        self.assertIn("[switch]$DownloadModel", source)
        self.assertIn("[switch]$ResetTestDatabase", source)
        self.assertIn("$env:DOCKER_CONTEXT = 'desktop-linux'", source)
        self.assertNotIn("docker context use", source.lower())
        self.assertIn("$version.Server.Version", source)
        self.assertIn("RandomNumberGenerator", source)
        self.assertNotIn("Set-Content", source)
        self.assertNotIn("Out-File", source)
        self.assertNotIn("docker system prune", source.lower())
        self.assertNotIn("docker volume prune", source.lower())
        self.assertIn("docker volume rm $testVolumeName", source)
        self.assertIn("$volume.Name -ne $testVolumeName", source)
        self.assertIn("if ($DownloadModel)", source)
        self.assertIn("if ($ResetTestDatabase)", source)
        self.assertIn("compose --project-name $projectName --file $composeFile stop", source)
        self.assertIn("$gateExitCode = $LASTEXITCODE", source)
        self.assertIn("exit $gateExitCode", source)
        self.assertIn("$previousBaselineDatabaseUrl = $env:BASELINE_DEVELOPMENT_DATABASE_URL", source)
        self.assertIn("$env:BASELINE_DEVELOPMENT_DATABASE_URL = $previousBaselineDatabaseUrl", source)
        self.assertIn("$previousTestDatabasePassword = $env:SIONGGPT_TEST_DB_PASSWORD", source)
        self.assertIn("$env:SIONGGPT_TEST_DB_PASSWORD = $previousTestDatabasePassword", source)
        self.assertIn("from app.core.config import settings", source)
        self.assertLess(source.index("Assert-DockerServer"), source.index("$testPassword = New-TestPassword"))
        self.assertLess(source.index("$testPassword = New-TestPassword"), source.index("Invoke-TestCompose up -d"))

    def test_user_shell_runner_never_prints_secret_values(self):
        source = (REPOSITORY_ROOT / "backend" / "scripts" / "run_phase45_from_user_shell.ps1").read_text(encoding="utf-8")
        output_lines = [
            line for line in source.splitlines()
            if any(command in line for command in ("Write-Host", "Write-Error", "Write-Warning", "Out-Host"))
        ]
        rendered = "\n".join(output_lines)
        self.assertNotIn("$testPassword", rendered)
        self.assertNotIn("$encodedPassword", rendered)
        self.assertNotIn("TEST_DATABASE_URL", rendered)
        self.assertNotIn("BASELINE_DEVELOPMENT_DATABASE_URL", rendered)

    def test_gate_runner_propagates_baseline_to_every_child_process(self):
        from scripts import run_integration_gate as gate

        primary_url = "postgresql+psycopg://gate@127.0.0.1:55432/sionggpt_test_run"
        migration_url = "postgresql+psycopg://gate@127.0.0.1:55432/sionggpt_migration_test_run"
        baseline_url = "postgresql+psycopg://developer@127.0.0.1:5432/siong_gpt"
        child_environments = []

        def capture(_name, _command, environment):
            child_environments.append(environment.copy())
            return gate.CheckResult(_name, "PASS", "exit_code=0")

        environment = {
            "TEST_DATABASE_URL": primary_url,
            "TEST_MIGRATION_DATABASE_URL": migration_url,
            "ALLOW_DESTRUCTIVE_DB_TESTS": "true",
            BASELINE_DATABASE_ENV: baseline_url,
            "EMBEDDING_MODEL_LOCAL_PATH": "C:/outside/model",
        }
        output = io.StringIO()
        with redirect_stdout(output), patch.dict(os.environ, environment, clear=True), patch.object(
            gate, "check_database", side_effect=lambda name, *_args, **_kwargs: gate.CheckResult(name, "PASS", "fresh")
        ), patch.object(gate, "assert_model_directory"), patch.object(
            gate, "run_command", side_effect=capture
        ):
            self.assertEqual(gate.main([]), 0)
        self.assertTrue(child_environments)
        for child in child_environments:
            self.assertEqual(child[BASELINE_DATABASE_ENV], baseline_url)
        primary_children = [child for child in child_environments if child.get("DATABASE_URL") == primary_url]
        self.assertTrue(primary_children)

    def test_online_base_accepts_runtime_test_url_with_separate_baseline(self):
        from tests.integration.postgres import base

        target = "postgresql+psycopg://gate@127.0.0.1:55432/sionggpt_test_probe"
        baseline = "postgresql+psycopg://developer@127.0.0.1:5432/siong_gpt"
        engine = MagicMock()
        connection = engine.connect.return_value.__enter__.return_value
        connection.scalar.return_value = "sionggpt_test_probe"

        class Probe(base.PostgresGateCase):
            pass

        with patch.object(base, "TEST_DATABASE_URL", target), patch.object(
            base, "create_engine", return_value=engine
        ), patch.dict(os.environ, {
            "ALLOW_DESTRUCTIVE_DB_TESTS": "true",
            "DATABASE_URL": target,
            BASELINE_DATABASE_ENV: baseline,
        }, clear=False):
            Probe.setUpClass()
            Probe.tearDownClass()
        engine.dispose.assert_called_once()

    def test_all_five_online_classes_pass_the_separate_baseline_guard(self):
        from tests import test_postgres_integration as legacy
        from tests.integration.e2e.test_vertical_slice import VerticalSliceGateTests
        from tests.integration.embedding.test_real_retrieval_evaluation import (
            RealRetrievalEvaluationTests,
        )
        from tests.integration.postgres import base
        from tests.integration.postgres.test_concurrency_and_transactions import (
            ConcurrencyAndTransactionGateTests,
        )
        from tests.integration.postgres.test_constraints_and_vector import (
            SchemaAndConstraintGateTests,
        )

        target = "postgresql+psycopg://gate@127.0.0.1:55432/sionggpt_test_probe"
        baseline = "postgresql+psycopg://developer@127.0.0.1:5432/siong_gpt"
        environment = {
            "ALLOW_DESTRUCTIVE_DB_TESTS": "true",
            "DATABASE_URL": target,
            BASELINE_DATABASE_ENV: baseline,
        }
        inherited_classes = (
            VerticalSliceGateTests,
            RealRetrievalEvaluationTests,
            ConcurrencyAndTransactionGateTests,
            SchemaAndConstraintGateTests,
        )
        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value.scalar.return_value = "sionggpt_test_probe"

        with patch.object(base, "TEST_DATABASE_URL", target), patch.object(
            base, "create_engine", return_value=engine
        ), patch.dict(os.environ, environment, clear=False):
            for test_class in inherited_classes:
                with self.subTest(test_class=test_class.__name__):
                    test_class.setUpClass()
                    test_class.tearDownClass()

        legacy_engine = MagicMock()
        with patch.object(legacy, "TEST_DATABASE_URL", target), patch.object(
            legacy, "create_engine", return_value=legacy_engine
        ), patch.object(legacy.command, "upgrade"), patch.dict(
            os.environ, environment, clear=False
        ):
            legacy.PostgreSQLIntegrationTests.setUpClass()
            legacy.PostgreSQLIntegrationTests.tearDownClass()

        self.assertEqual(engine.dispose.call_count, len(inherited_classes))
        legacy_engine.dispose.assert_called_once()

    def test_offline_process_without_integration_environment_stays_disabled(self):
        environment = os.environ.copy()
        for name in ("TEST_DATABASE_URL", "ALLOW_DESTRUCTIVE_DB_TESTS", BASELINE_DATABASE_ENV):
            environment.pop(name, None)
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                "from tests.integration.postgres.base import ONLINE_ENABLED; raise SystemExit(1 if ONLINE_ENABLED else 0)",
            ],
            cwd=REPOSITORY_ROOT / "backend",
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_both_online_bases_use_propagated_baseline_not_runtime_url(self):
        integration_base = (REPOSITORY_ROOT / "backend" / "tests" / "integration" / "postgres" / "base.py").read_text(encoding="utf-8")
        legacy = (REPOSITORY_ROOT / "backend" / "tests" / "test_postgres_integration.py").read_text(encoding="utf-8")
        for source in (integration_base, legacy):
            self.assertIn("BASELINE_DATABASE_ENV", source)
            self.assertIn("development_url=baseline", source)
            self.assertNotIn('development_url=os.getenv("DATABASE_URL")', source)


if __name__ == "__main__":
    unittest.main()
