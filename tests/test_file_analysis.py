import base64
import unittest

from file_analysis import DocumentError, MAX_UPLOAD_BYTES, extract_document


def encoded(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


class DocumentExtractionTests(unittest.TestCase):
    def test_extracts_plain_text_and_sanitizes_filename(self):
        result = extract_document("../../notes.txt", encoded(b"Hello AI HUB"))
        self.assertEqual(result["filename"], "notes.txt")
        self.assertEqual(result["text"], "Hello AI HUB")
        self.assertFalse(result["stored"])

    def test_formats_json_for_reading(self):
        result = extract_document("data.json", encoded(b'{"ok":true}'))
        self.assertIn('"ok": true', result["text"])

    def test_rejects_unsupported_extension(self):
        with self.assertRaises(DocumentError):
            extract_document("payload.exe", encoded(b"not executable"))

    def test_rejects_invalid_base64(self):
        with self.assertRaises(DocumentError):
            extract_document("notes.txt", "%%%")

    def test_rejects_extension_signature_mismatch(self):
        with self.assertRaises(DocumentError):
            extract_document("fake.pdf", encoded(b"not a PDF"))

    def test_rejects_oversized_upload(self):
        too_large = b"x" * (MAX_UPLOAD_BYTES + 1)
        with self.assertRaises(DocumentError):
            extract_document("large.txt", encoded(too_large))

    def test_truncates_extracted_text_to_safe_limit(self):
        result = extract_document("large.txt", encoded(b"a" * 30_000))
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["text"]), 24_000)


if __name__ == "__main__":
    unittest.main()
