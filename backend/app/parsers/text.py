import re
from typing import BinaryIO
from uuid import UUID

from app.core.domain_types import DocumentBlockType, IngestionErrorCode
from app.parsers.base import DocumentBlock, DocumentParser
from app.parsers.errors import IngestionError


class TextParser(DocumentParser):
    name = "text"

    def parse(self, stream: BinaryIO, *, filename: str, mime_type: str, source_version_id: UUID):
        raw = stream.read(self.limits.max_extracted_chars * 4 + 4)
        if not raw:
            raise IngestionError(IngestionErrorCode.EMPTY_DOCUMENT, "Text document is empty")
        if b"\x00" in raw:
            raise IngestionError(
                IngestionErrorCode.FILE_SIGNATURE_MISMATCH,
                "Text document contains binary NUL bytes",
            )
        controls = sum(byte < 9 or 13 < byte < 32 for byte in raw)
        if controls / len(raw) > 0.02:
            raise IngestionError(
                IngestionErrorCode.FILE_SIGNATURE_MISMATCH,
                "Text document appears to contain binary data",
            )
        try:
            text = raw.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError as exc:
            raise IngestionError(
                IngestionErrorCode.INVALID_TEXT_ENCODING,
                "Text document must use UTF-8 encoding",
            ) from exc
        if len(text) > self.limits.max_extracted_chars:
            raise IngestionError(
                IngestionErrorCode.EXTRACTED_TEXT_LIMIT_EXCEEDED,
                "Extracted text exceeds the configured limit",
            )
        blocks = []
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        start = None
        paragraph = []
        for line_no, line in enumerate(lines, 1):
            if line.strip():
                start = start or line_no
                paragraph.append(line.rstrip())
            elif paragraph:
                content = "\n".join(paragraph).strip()
                blocks.append(
                    DocumentBlock(
                        DocumentBlockType.PARAGRAPH,
                        content,
                        len(blocks),
                        locator={"line_start": start, "line_end": line_no - 1},
                        metadata={"parser": self.name, "parser_version": self.version},
                    )
                )
                start, paragraph = None, []
        if paragraph:
            blocks.append(
                DocumentBlock(
                    DocumentBlockType.PARAGRAPH,
                    "\n".join(paragraph).strip(),
                    len(blocks),
                    locator={"line_start": start, "line_end": len(lines)},
                    metadata={"parser": self.name, "parser_version": self.version},
                )
            )
        if not blocks or not any(re.search(r"\S", block.content) for block in blocks):
            raise IngestionError(IngestionErrorCode.EMPTY_DOCUMENT, "Text document is empty")
        return blocks
