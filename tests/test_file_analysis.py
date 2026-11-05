import base64
import io
import unittest
import zipfile

from docx import Document
from openpyxl import Workbook

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


    def test_extracts_docx_paragraphs_and_tables(self):
        document = Document()
        document.add_paragraph("Project overview")
        table = document.add_table(rows=1, cols=2)
        table.cell(0, 0).text = "Budget"
        table.cell(0, 1).text = "100"
        output = io.BytesIO()
        document.save(output)
        result = extract_document("brief.docx", encoded(output.getvalue()))
        self.assertIn("Project overview", result["text"])
        self.assertIn("Budget | 100", result["text"])
        self.assertEqual(result["format"], "docx")

    def test_extracts_xlsx_sheet_values(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Forecast"
        sheet.append(["Month", "Revenue"])
        sheet.append(["January", 1200])
        output = io.BytesIO()
        workbook.save(output)
        result = extract_document("forecast.xlsx", encoded(output.getvalue()))
        self.assertIn("[Sheet: Forecast]", result["text"])
        self.assertIn("January | 1200", result["text"])
        self.assertEqual(result["format"], "xlsx")

    def test_rejects_invalid_office_archive(self):
        with self.assertRaises(DocumentError):
            extract_document("broken.docx", encoded(b"not a zip archive"))

    def test_rejects_wrong_office_container_type(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("xl/workbook.xml", "<workbook/>")
        with self.assertRaises(DocumentError):
            extract_document("fake.docx", encoded(output.getvalue()))


if __name__ == "__main__":
    unittest.main()
