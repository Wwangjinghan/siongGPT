from typing import BinaryIO
from uuid import UUID

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.domain_types import DocumentBlockType, IngestionErrorCode
from app.parsers.base import DocumentBlock, DocumentParser
from app.parsers.errors import IngestionError


class PdfParser(DocumentParser):
    name = "pypdf"

    def parse(self, stream: BinaryIO, *, filename: str, mime_type: str, source_version_id: UUID):
        try:
            stream.seek(0)
            if not stream.read(5).startswith(b"%PDF-"):
                raise IngestionError(
                    IngestionErrorCode.FILE_SIGNATURE_MISMATCH, "PDF signature mismatch"
                )
            stream.seek(0)
            reader = PdfReader(stream, strict=True)
            if reader.is_encrypted:
                raise IngestionError(
                    IngestionErrorCode.ENCRYPTED_PDF, "Encrypted PDF is not supported"
                )
            if len(reader.pages) > self.limits.max_pdf_pages:
                raise IngestionError(
                    IngestionErrorCode.PDF_PAGE_LIMIT_EXCEEDED,
                    "PDF exceeds the configured page limit",
                )
            blocks, total = [], 0
            for page_no, page in enumerate(reader.pages, 1):
                content = (page.extract_text() or "").strip()
                if not content:
                    continue
                total += len(content)
                if total > self.limits.max_extracted_chars:
                    raise IngestionError(
                        IngestionErrorCode.EXTRACTED_TEXT_LIMIT_EXCEEDED,
                        "Extracted PDF text exceeds the configured limit",
                    )
                blocks.append(
                    DocumentBlock(
                        DocumentBlockType.PARAGRAPH,
                        content,
                        len(blocks),
                        page=page_no,
                        locator={"page": page_no},
                        metadata={"parser": self.name, "parser_version": self.version},
                    )
                )
            if not blocks:
                raise IngestionError(
                    IngestionErrorCode.OCR_REQUIRED,
                    "PDF contains no extractable text; OCR is required",
                )
            return blocks
        except IngestionError:
            raise
        except PdfReadError as exc:
            raise IngestionError(
                IngestionErrorCode.FILE_SIGNATURE_MISMATCH, "Invalid PDF structure"
            ) from exc
        except Exception as exc:
            raise IngestionError(
                IngestionErrorCode.PARSER_FAILED, "PDF parsing failed"
            ) from exc
