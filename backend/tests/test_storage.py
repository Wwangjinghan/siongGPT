import io
import tempfile
import unittest
from pathlib import Path

from app.sources.errors import InvalidFileError
from app.sources.file_validation import validate_file_signature, validate_upload_metadata
from app.storage.local import (
    EmptyFileError,
    FileTooLargeError,
    LocalStorageAdapter,
    UnsafeStorageKeyError,
)


class FailingStream:
    def __init__(self):
        self.calls = 0

    def read(self, _size):
        self.calls += 1
        if self.calls == 1:
            return b"some bytes"
        raise OSError("connection interrupted")


class LocalStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "objects"
        self.storage = LocalStorageAdapter(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_streaming_atomic_save_and_read(self):
        saved = self.storage.save(io.BytesIO(b"hello"), max_bytes=100)
        self.assertTrue(saved.created)
        self.assertEqual(saved.file_size, 5)
        self.assertRegex(saved.file_hash, r"^[0-9a-f]{64}$")
        self.assertNotIn("hello", saved.storage_key)
        self.assertTrue(self.storage.exists(saved.storage_key))
        with self.storage.open(saved.storage_key) as stored:
            self.assertEqual(stored.read(), b"hello")
        self.assertEqual(list((self.root / ".tmp").iterdir()), [])

    def test_physical_deduplication_returns_existing_object(self):
        first = self.storage.save(io.BytesIO(b"shared"), max_bytes=100)
        second = self.storage.save(io.BytesIO(b"shared"), max_bytes=100)
        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(first.storage_key, second.storage_key)

    def test_empty_file_is_rejected_and_temp_removed(self):
        with self.assertRaises(EmptyFileError):
            self.storage.save(io.BytesIO(b""), max_bytes=100)
        self.assertEqual(list((self.root / ".tmp").iterdir()), [])

    def test_size_limit_stops_and_cleans_temp(self):
        with self.assertRaises(FileTooLargeError):
            self.storage.save(io.BytesIO(b"123456"), max_bytes=5)
        self.assertEqual(list((self.root / ".tmp").iterdir()), [])

    def test_stream_failure_cleans_temp(self):
        with self.assertRaises(OSError):
            self.storage.save(FailingStream(), max_bytes=100)
        self.assertEqual(list((self.root / ".tmp").iterdir()), [])

    def test_storage_key_rejects_traversal_and_absolute_paths(self):
        for key in ("../secret", "C:\\secret.txt", "/etc/passwd", "a\\b"):
            with self.subTest(key=key), self.assertRaises(UnsafeStorageKeyError):
                self.storage.exists(key)

    def test_filename_never_controls_storage_path(self):
        name = validate_upload_metadata("..\\..\\company-policy.PDF", "application/pdf")
        self.assertEqual(name, "company-policy.PDF")
        saved = self.storage.save(io.BytesIO(b"%PDF-safe"), max_bytes=100)
        self.assertNotIn("company-policy", saved.storage_key)
        self.assertFalse(Path(saved.storage_key).is_absolute())

    def test_oversized_filename_is_rejected(self):
        with self.assertRaises(InvalidFileError):
            validate_upload_metadata("a" * 256 + ".txt", "text/plain")


class FileValidationTests(unittest.TestCase):
    def test_allowed_extensions_are_case_insensitive(self):
        self.assertEqual(
            validate_upload_metadata("Report.XLSX", "application/octet-stream"),
            "Report.XLSX",
        )

    def test_unsupported_and_mime_conflicts_are_rejected(self):
        for filename, mime in (("malware.exe", "application/octet-stream"), ("a.pdf", "text/plain")):
            with self.subTest(filename=filename), self.assertRaises(InvalidFileError):
                validate_upload_metadata(filename, mime)

    def test_minimum_signatures_are_enforced(self):
        valid = (("a.pdf", b"%PDF-1.7"), ("a.docx", b"PK\x03\x04data"), ("a.xlsx", b"PK\x03\x04data"), ("a.txt", b"plain"))
        for filename, data in valid:
            with self.subTest(filename=filename):
                validate_file_signature(io.BytesIO(data), filename)
        with self.assertRaises(InvalidFileError):
            validate_file_signature(io.BytesIO(b"MZbinary"), "fake.txt")
