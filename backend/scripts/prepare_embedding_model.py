from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.integration_gate_support import (
    PINNED_MODEL_REPO,
    PINNED_MODEL_REVISION,
    IntegrationGateSafetyError,
    assert_model_directory,
    ensure_outside_repository,
)


REPOSITORY_ROOT = BACKEND_ROOT.parent


def build_manifest(directory: Path) -> dict:
    files = []
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        if path.name == "model-manifest.json":
            continue
        files.append({"path": path.relative_to(directory).as_posix(), "size": path.stat().st_size})
    return {
        "repo_id": PINNED_MODEL_REPO,
        "revision": PINNED_MODEL_REVISION,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }


def check_model(target: Path) -> dict:
    directory = assert_model_directory(target)
    manifest_path = directory / "model-manifest.json"
    if not manifest_path.is_file():
        raise IntegrationGateSafetyError("The model manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("repo_id") != PINNED_MODEL_REPO or manifest.get("revision") != PINNED_MODEL_REVISION:
        raise IntegrationGateSafetyError("The model manifest identity does not match the pinned model")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise IntegrationGateSafetyError("The model manifest contains no files")
    for entry in files:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not isinstance(entry.get("size"), int):
            raise IntegrationGateSafetyError("The model manifest contains an invalid file entry")
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise IntegrationGateSafetyError("The model manifest contains an unsafe file path")
        model_file = (directory / relative).resolve()
        if directory not in model_file.parents or not model_file.is_file():
            raise IntegrationGateSafetyError("A model manifest file is missing or outside the model directory")
        if model_file.stat().st_size != entry["size"]:
            raise IntegrationGateSafetyError("A model manifest file size does not match")
    return manifest


def download_model(target: Path) -> dict:
    if target.exists():
        raise IntegrationGateSafetyError("The download target must not already exist")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="sionggpt-e5-", dir=target.parent))
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=PINNED_MODEL_REPO,
            revision=PINNED_MODEL_REVISION,
            local_dir=temporary,
        )
        (temporary / ".siong-model-revision").write_text(
            PINNED_MODEL_REVISION + "\n", encoding="utf-8"
        )
        manifest = build_manifest(temporary)
        (temporary / "model-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.replace(target)
        return manifest
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check or explicitly download the pinned Phase 4 E5 model."
    )
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument(
        "--download",
        action="store_true",
        help="Explicitly permit downloading the one pinned repository revision.",
    )
    args = parser.parse_args(argv)
    try:
        target = ensure_outside_repository(args.target, REPOSITORY_ROOT)
        manifest = download_model(target) if args.download else check_model(target)
    except (IntegrationGateSafetyError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"MODEL_CHECK_FAILED: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"MODEL_DOWNLOAD_FAILED: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "READY",
                "repo_id": manifest["repo_id"],
                "revision": manifest["revision"],
                "file_count": len(manifest["files"]),
                "target": str(target),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
