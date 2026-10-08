import hashlib
import os
import tempfile
from pathlib import Path
from typing import BinaryIO

from app.storage.base import SavedObject, StorageAdapter


class StorageError(Exception):
    pass


class EmptyFileError(StorageError):
    pass


class FileTooLargeError(StorageError):
    pass


class UnsafeStorageKeyError(StorageError):
    pass


class LocalStorageAdapter(StorageAdapter):
    chunk_size = 1024 * 1024

    def __init__(self, root: str | Path):
        configured_root = Path(root).expanduser().absolute()
        self._reject_existing_symlinks(configured_root)
        configured_root.mkdir(parents=True, exist_ok=True)
        if configured_root.is_symlink():
            raise UnsafeStorageKeyError("Storage root cannot be a symbolic link")
        self.root = configured_root.resolve()
        self.temp_root = self.root / ".tmp"
        self.temp_root.mkdir(exist_ok=True)
        if self.temp_root.is_symlink():
            raise UnsafeStorageKeyError("Temporary storage cannot be a symbolic link")

    def save(self, stream: BinaryIO, *, max_bytes: int) -> SavedObject:
        digest = hashlib.sha256()
        size = 0
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=self.temp_root, prefix="upload-", delete=False
            ) as temporary:
                temp_path = Path(temporary.name)
                while True:
                    remaining_probe = max_bytes - size + 1
                    chunk = stream.read(min(self.chunk_size, remaining_probe))
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise FileTooLargeError(f"File exceeds {max_bytes} bytes")
                    digest.update(chunk)
                    temporary.write(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())

            if size == 0:
                raise EmptyFileError("Empty files are not allowed")

            file_hash = digest.hexdigest()
            storage_key = f"sha256/{file_hash[:2]}/{file_hash[2:4]}/{file_hash}"
            target = self._resolve_key(storage_key)
            target.parent.mkdir(parents=True, exist_ok=True)
            self._reject_symlink_components(target.parent)
            if target.exists():
                temp_path.unlink()
                return SavedObject(storage_key, file_hash, size, False)
            os.replace(temp_path, target)
            temp_path = None
            return SavedObject(storage_key, file_hash, size, True)
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

    def open(self, storage_key: str) -> BinaryIO:
        path = self._resolve_key(storage_key)
        if path.is_symlink():
            raise UnsafeStorageKeyError("Symbolic links are not valid storage objects")
        return path.open("rb")

    def exists(self, storage_key: str) -> bool:
        path = self._resolve_key(storage_key)
        return path.is_file() and not path.is_symlink()

    def delete(self, storage_key: str) -> None:
        path = self._resolve_key(storage_key)
        if path.is_symlink():
            raise UnsafeStorageKeyError("Refusing to delete a symbolic link")
        if path.is_file():
            path.unlink()

    def _resolve_key(self, storage_key: str) -> Path:
        if not storage_key or "\\" in storage_key:
            raise UnsafeStorageKeyError("Invalid storage key")
        candidate_key = Path(storage_key)
        if candidate_key.is_absolute() or ".." in candidate_key.parts:
            raise UnsafeStorageKeyError("Invalid storage key")
        lexical_candidate = self.root / candidate_key
        self._reject_existing_symlinks(lexical_candidate)
        candidate = lexical_candidate.resolve(strict=False)
        if not candidate.is_relative_to(self.root):
            raise UnsafeStorageKeyError("Storage key escapes the configured root")
        return candidate

    @staticmethod
    def _reject_existing_symlinks(path: Path) -> None:
        current = Path(path.anchor)
        for part in path.parts[1:]:
            current = current / part
            if current.exists() and current.is_symlink():
                raise UnsafeStorageKeyError("Storage path contains a symbolic link")

    def _reject_symlink_components(self, directory: Path) -> None:
        current = directory
        while current != self.root:
            if current.is_symlink():
                raise UnsafeStorageKeyError("Storage path contains a symbolic link")
            current = current.parent
