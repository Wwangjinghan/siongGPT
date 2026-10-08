import hashlib
import re
from dataclasses import dataclass

from app.core.domain_types import DocumentBlockType
from app.parsers.base import DocumentBlock


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    chunk_index: int
    content: str
    content_hash: str
    block_type: DocumentBlockType
    page: int | None
    section: str | None
    sheet: str | None
    row_start: int | None
    row_end: int | None
    locator: dict
    metadata: dict


def normalize_content(content: str) -> str:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized.split("\n")]
    return "\n".join(line for line in lines if line).strip()


class DeterministicChunker:
    version = "1"

    def __init__(self, max_chars: int, overlap_chars: int, xlsx_rows_per_chunk: int):
        if max_chars <= 0 or overlap_chars < 0 or overlap_chars >= max_chars:
            raise ValueError("Chunk limits are invalid")
        if xlsx_rows_per_chunk <= 0:
            raise ValueError("XLSX rows per chunk must be positive")
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars
        self.xlsx_rows_per_chunk = xlsx_rows_per_chunk

    def chunk(self, blocks: list[DocumentBlock]) -> list[ChunkDraft]:
        drafts: list[ChunkDraft] = []
        spreadsheet_group: list[DocumentBlock] = []

        def flush_spreadsheet():
            nonlocal spreadsheet_group
            if not spreadsheet_group:
                return
            first = spreadsheet_group[0]
            header = first.metadata.get("table_header")
            rows = [normalize_content(block.content) for block in spreadsheet_group]
            content = "\n".join(row for row in rows if row)
            if header and normalize_content(header) not in rows[:1]:
                content = f"{normalize_content(header)}\n{content}"
            self._append_split(
                drafts,
                content,
                first,
                row_start=spreadsheet_group[0].row_start,
                row_end=spreadsheet_group[-1].row_end,
                metadata={**first.metadata, "source_block_ordinals": [b.ordinal for b in spreadsheet_group]},
            )
            spreadsheet_group = []

        for block in blocks:
            if block.block_type is DocumentBlockType.SPREADSHEET_ROWS:
                if spreadsheet_group and (
                    spreadsheet_group[-1].sheet != block.sheet
                    or len(spreadsheet_group) >= self.xlsx_rows_per_chunk
                ):
                    flush_spreadsheet()
                spreadsheet_group.append(block)
                continue
            flush_spreadsheet()
            self._append_split(drafts, normalize_content(block.content), block)
        flush_spreadsheet()
        return [
            ChunkDraft(
                chunk_index=index,
                content=draft.content,
                content_hash=draft.content_hash,
                block_type=draft.block_type,
                page=draft.page,
                section=draft.section,
                sheet=draft.sheet,
                row_start=draft.row_start,
                row_end=draft.row_end,
                locator=draft.locator,
                metadata=draft.metadata,
            )
            for index, draft in enumerate(drafts)
        ]

    def _append_split(
        self,
        drafts: list[ChunkDraft],
        content: str,
        block: DocumentBlock,
        *,
        row_start: int | None = None,
        row_end: int | None = None,
        metadata: dict | None = None,
    ) -> None:
        if not content:
            return
        start = 0
        while start < len(content):
            proposed_end = min(start + self.max_chars, len(content))
            end = proposed_end
            if proposed_end < len(content):
                boundary = max(
                    content.rfind("\n", start, proposed_end),
                    content.rfind(" ", start, proposed_end),
                )
                if boundary > start:
                    end = boundary
            piece = content[start:end].strip()
            if piece:
                locator = dict(block.locator)
                if row_start is not None:
                    locator.update({"row_start": row_start, "row_end": row_end})
                drafts.append(
                    ChunkDraft(
                        chunk_index=len(drafts),
                        content=piece,
                        content_hash=hashlib.sha256(piece.encode("utf-8")).hexdigest(),
                        block_type=block.block_type,
                        page=block.page,
                        section=block.section,
                        sheet=block.sheet,
                        row_start=row_start if row_start is not None else block.row_start,
                        row_end=row_end if row_end is not None else block.row_end,
                        locator=locator,
                        metadata={
                            **block.metadata,
                            **(metadata or {}),
                            "source_block_ordinal": block.ordinal,
                            "normalization_version": "1",
                            "chunking_version": self.version,
                        },
                    )
                )
            if end >= len(content):
                break
            next_start = max(end - self.overlap_chars, start + 1)
            start = next_start
