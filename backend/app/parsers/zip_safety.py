from pathlib import PurePosixPath
from typing import BinaryIO
from zipfile import BadZipFile, ZipFile

from app.core.domain_types import IngestionErrorCode
from app.parsers.base import ParserLimits
from app.parsers.errors import IngestionError


MACRO_NAMES = {"vbaproject.bin", "vbaData.xml".lower()}
DANGEROUS_SUFFIXES = {".exe", ".dll", ".com", ".bat", ".cmd", ".ps1"}


def inspect_office_zip(stream: BinaryIO, limits: ParserLimits) -> None:
    try:
        stream.seek(0)
        with ZipFile(stream) as archive:
            entries = archive.infolist()
            if len(entries) > limits.max_zip_entries:
                raise IngestionError(
                    IngestionErrorCode.ZIP_BOMB_SUSPECTED,
                    "Office package contains too many entries",
                )
            total_size = 0
            total_compressed = 0
            for entry in entries:
                path = PurePosixPath(entry.filename.replace("\\", "/"))
                if path.is_absolute() or ".." in path.parts:
                    raise IngestionError(
                        IngestionErrorCode.OFFICE_ZIP_INVALID,
                        "Office package contains an unsafe entry path",
                    )
                lowered = entry.filename.lower()
                if any(name in lowered for name in MACRO_NAMES) or path.suffix.lower() in DANGEROUS_SUFFIXES:
                    raise IngestionError(
                        IngestionErrorCode.MACRO_CONTENT_REJECTED,
                        "Office package contains prohibited executable or macro content",
                    )
                total_size += entry.file_size
                total_compressed += entry.compress_size
                if total_size > limits.max_uncompressed_bytes:
                    raise IngestionError(
                        IngestionErrorCode.ZIP_BOMB_SUSPECTED,
                        "Office package exceeds the uncompressed size limit",
                    )
            ratio = total_size / max(total_compressed, 1)
            if ratio > limits.max_compression_ratio:
                raise IngestionError(
                    IngestionErrorCode.ZIP_BOMB_SUSPECTED,
                    "Office package compression ratio is suspicious",
                )
    except IngestionError:
        raise
    except (BadZipFile, OSError) as exc:
        raise IngestionError(
            IngestionErrorCode.OFFICE_ZIP_INVALID, "Invalid Office Open XML package"
        ) from exc
    finally:
        stream.seek(0)
