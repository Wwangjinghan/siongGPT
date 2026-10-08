from pathlib import Path
from typing import BinaryIO

from app.sources.errors import InvalidFileError


ALLOWED_MIME_TYPES = {
    ".txt": {"text/plain", "application/octet-stream"},
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
    },
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "application/octet-stream",
    },
}


def validate_upload_metadata(filename: str | None, mime_type: str | None) -> str:
    safe_name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    if not safe_name or safe_name in {".", ".."}:
        raise InvalidFileError("A valid filename is required")
    if len(safe_name) > 255:
        raise InvalidFileError("Filename exceeds 255 characters")
    extension = Path(safe_name).suffix.lower()
    if extension not in ALLOWED_MIME_TYPES:
        raise InvalidFileError("Unsupported file extension")
    normalized_mime = (mime_type or "application/octet-stream").lower().split(";", 1)[0]
    if normalized_mime not in ALLOWED_MIME_TYPES[extension]:
        raise InvalidFileError("File extension and MIME type conflict")
    return safe_name


def validate_file_signature(stream: BinaryIO, filename: str) -> None:
    position = stream.tell()
    header = stream.read(8)
    stream.seek(position)
    extension = Path(filename).suffix.lower()
    if extension == ".pdf" and not header.startswith(b"%PDF-"):
        raise InvalidFileError("Invalid PDF signature")
    if extension in {".docx", ".xlsx"} and not header.startswith(b"PK\x03\x04"):
        raise InvalidFileError("Invalid Office Open XML signature")
    if extension == ".txt" and (
        b"\x00" in header or header.startswith((b"MZ", b"PK\x03\x04", b"%PDF-"))
    ):
        raise InvalidFileError("Invalid text file signature")
