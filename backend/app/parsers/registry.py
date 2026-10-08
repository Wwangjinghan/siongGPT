from pathlib import Path

from app.core.domain_types import IngestionErrorCode
from app.parsers.base import ParserLimits
from app.parsers.docx import DocxParser
from app.parsers.errors import IngestionError
from app.parsers.pdf import PdfParser
from app.parsers.text import TextParser
from app.parsers.xlsx import XlsxParser


MIME_BY_EXTENSION = {
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


class ParserRegistry:
    def __init__(self, limits: ParserLimits):
        self.parsers = {
            ".txt": TextParser(limits),
            ".pdf": PdfParser(limits),
            ".docx": DocxParser(limits),
            ".xlsx": XlsxParser(limits),
        }

    def get(self, filename: str, mime_type: str):
        extension = Path(filename).suffix.lower()
        parser = self.parsers.get(extension)
        if parser is None:
            raise IngestionError(
                IngestionErrorCode.UNSUPPORTED_FILE_TYPE, "Unsupported source file type"
            )
        normalized_mime = (mime_type or "application/octet-stream").split(";", 1)[0].lower()
        if normalized_mime not in MIME_BY_EXTENSION[extension]:
            raise IngestionError(
                IngestionErrorCode.FILE_SIGNATURE_MISMATCH,
                "File extension and MIME type do not match",
            )
        return parser
