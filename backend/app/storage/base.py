from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import BinaryIO


@dataclass(frozen=True, slots=True)
class SavedObject:
    storage_key: str
    file_hash: str
    file_size: int
    created: bool


class StorageAdapter(ABC):
    @abstractmethod
    def save(self, stream: BinaryIO, *, max_bytes: int) -> SavedObject: ...

    @abstractmethod
    def open(self, storage_key: str) -> BinaryIO: ...

    @abstractmethod
    def exists(self, storage_key: str) -> bool: ...

    @abstractmethod
    def delete(self, storage_key: str) -> None: ...
