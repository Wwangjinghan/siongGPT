from typing import BinaryIO
from uuid import UUID

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.core.domain_types import DocumentBlockType, IngestionErrorCode
from app.parsers.base import DocumentBlock, DocumentParser
from app.parsers.errors import IngestionError
from app.parsers.zip_safety import inspect_office_zip


class DocxParser(DocumentParser):
    name = "python-docx"

    def parse(self, stream: BinaryIO, *, filename: str, mime_type: str, source_version_id: UUID):
        inspect_office_zip(stream, self.limits)
        try:
            document = Document(stream)
            blocks, total, section = [], 0, None
            for child in document.element.body.iterchildren():
                block_type = None
                content = ""
                if child.tag == qn("w:p"):
                    paragraph = Paragraph(child, document)
                    content = paragraph.text.strip()
                    if content:
                        style = paragraph.style.name if paragraph.style else ""
                        block_type = (
                            DocumentBlockType.HEADING
                            if style.lower().startswith("heading")
                            else DocumentBlockType.PARAGRAPH
                        )
                        if block_type is DocumentBlockType.HEADING:
                            section = content
                elif child.tag == qn("w:tbl"):
                    table = Table(child, document)
                    rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
                    content = "\n".join(row for row in rows if row.strip(" |"))
                    block_type = DocumentBlockType.TABLE
                if not content or block_type is None:
                    continue
                total += len(content)
                if total > self.limits.max_extracted_chars:
                    raise IngestionError(
                        IngestionErrorCode.EXTRACTED_TEXT_LIMIT_EXCEEDED,
                        "Extracted DOCX text exceeds the configured limit",
                    )
                blocks.append(
                    DocumentBlock(
                        block_type,
                        content,
                        len(blocks),
                        section=section,
                        locator={"section": section},
                        metadata={"parser": self.name, "parser_version": self.version},
                    )
                )
            if not blocks:
                raise IngestionError(IngestionErrorCode.EMPTY_DOCUMENT, "DOCX is empty")
            return blocks
        except IngestionError:
            raise
        except Exception as exc:
            raise IngestionError(
                IngestionErrorCode.OFFICE_ZIP_INVALID, "DOCX structure is invalid"
            ) from exc
