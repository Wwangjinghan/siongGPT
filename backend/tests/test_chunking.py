import unittest

from app.chunks.chunker import DeterministicChunker
from app.core.domain_types import DocumentBlockType
from app.parsers.base import DocumentBlock


class ChunkingTests(unittest.TestCase):
    def test_output_hash_and_indexes_are_deterministic(self):
        blocks = [DocumentBlock(DocumentBlockType.PARAGRAPH, "PO-001  GST\r\nDO", 0, page=2, locator={"page": 2})]
        chunker = DeterministicChunker(20, 5, 2)
        first = chunker.chunk(blocks)
        second = chunker.chunk(blocks)
        self.assertEqual(first, second)
        self.assertEqual([c.chunk_index for c in first], list(range(len(first))))
        self.assertIn("PO-001 GST", first[0].content)
        self.assertEqual(first[0].locator, {"page": 2})

    def test_empty_content_generates_no_chunks(self):
        chunks = DeterministicChunker(20, 5, 2).chunk(
            [DocumentBlock(DocumentBlockType.PARAGRAPH, " \n ", 0)]
        )
        self.assertEqual(chunks, [])

    def test_long_paragraph_splits_with_finite_overlap(self):
        content = " ".join(f"word{i}" for i in range(30))
        chunks = DeterministicChunker(40, 10, 2).chunk(
            [DocumentBlock(DocumentBlockType.PARAGRAPH, content, 0)]
        )
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(0 < len(c.content) <= 40 for c in chunks))
        self.assertLess(len(chunks), len(content))

    def test_table_remains_contextual_not_cell_chunks(self):
        chunks = DeterministicChunker(200, 10, 2).chunk(
            [DocumentBlock(DocumentBlockType.TABLE, "Code | Status\nGST | Required", 0)]
        )
        self.assertEqual(len(chunks), 1)
        self.assertIn("Code | Status", chunks[0].content)

    def test_spreadsheet_groups_rows_with_header_and_locator(self):
        blocks = [
            DocumentBlock(DocumentBlockType.SPREADSHEET_ROWS, "Code\tStatus", 0, sheet="Sheet1", row_start=1, row_end=1, metadata={"table_header": "Code\tStatus"}),
            DocumentBlock(DocumentBlockType.SPREADSHEET_ROWS, "PO-001\tOpen", 1, sheet="Sheet1", row_start=2, row_end=2, metadata={"table_header": "Code\tStatus"}),
            DocumentBlock(DocumentBlockType.SPREADSHEET_ROWS, "GST\tRequired", 2, sheet="Sheet1", row_start=3, row_end=3, metadata={"table_header": "Code\tStatus"}),
        ]
        chunks = DeterministicChunker(200, 10, 2).chunk(blocks)
        self.assertEqual(len(chunks), 2)
        self.assertEqual((chunks[0].row_start, chunks[0].row_end), (1, 2))
        self.assertEqual((chunks[1].row_start, chunks[1].row_end), (3, 3))
        self.assertTrue(chunks[1].content.startswith("Code Status"))
