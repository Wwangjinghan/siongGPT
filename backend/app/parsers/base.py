from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import BinaryIO
from uuid import UUID

from app.core.domain_types import DocumentBlockType


@dataclass(frozen=True, slots=True)
class ParserLimits:
    max_pdf_pages: int
    max_extracted_chars: int
    max_zip_entries: int
    max_uncompressed_bytes: int
    max_compression_ratio: float
    max_xlsx_sheets: int
    max_xlsx_rows_per_sheet: int
    max_xlsx_cells_per_row: int
    max_xlsx_nonempty_cells: int
    max_cell_chars: int


@dataclass(frozen=True, slots=True)
class DocumentBlock:
    block_type: DocumentBlockType
    content: str
    ordinal: int
    page: int | None = None
    section: str | None = None
    sheet: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    locator: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


class DocumentParser(ABC):
    name = "base"
    version = "1"

    def __init__(self, limits: ParserLimits):
        self.limits = limits

    @abstractmethod
    def parse(
        self,
        stream: BinaryIO,
        *,
        filename: str,
        mime_type: str,
        source_version_id: UUID,
    ) -> list[DocumentBlock]: ...
