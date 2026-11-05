"""Safe, bounded text extraction for user-supplied documents.

Uploads are processed in memory and are not persisted by this module.
"""
from __future__ import annotations

import base64
import binascii
import csv
import io
import json
import os
import re
import zipfile
from pathlib import PurePosixPath

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_EXTRACTED_CHARS = 24_000
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".csv", ".json", ".docx", ".xlsx"}
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 2_000
MAX_SPREADSHEET_ROWS = 20_000
MAX_SPREADSHEET_COLUMNS = 200
MAX_OCR_PAGES = 20
MAX_OCR_TEXT_THRESHOLD = 40


class DocumentError(ValueError):
    """A document is invalid, unsupported, or exceeds a configured limit."""




def _ocr_pdf(raw: bytes, page_limit: int) -> str:
    """OCR a bounded number of scanned PDF pages using the system Tesseract engine."""
    try:
        import fitz
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise DocumentError("OCR support is not installed on this server.") from exc

    language = os.getenv("HUB_OCR_LANG", "eng+rus")
    if not re.fullmatch(r"[A-Za-z_+]+", language):
        language = "eng+rus"
    output = []
    try:
        document = fitz.open(stream=raw, filetype="pdf")
        try:
            for page in document[:min(page_limit, MAX_OCR_PAGES)]:
                max_points = max(float(page.rect.width), float(page.rect.height), 1.0)
                scale = min(2.0, 2400.0 / max_points)
                pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
                output.append(pytesseract.image_to_string(
                    image, lang=language, timeout=15
                ))
        finally:
            document.close()
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError("OCR could not process this PDF. Check its pages and OCR language data.") from exc
    return "\n\n".join(part.strip() for part in output if part.strip())


def _validate_office_archive(raw: bytes, required_member: str) -> None:
    """Reject malformed, encrypted, or suspiciously large Office ZIP containers."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise DocumentError("The Office document contains too many internal files.")
            if any(entry.flag_bits & 0x1 for entry in entries):
                raise DocumentError("Encrypted Office documents are not supported.")
            if sum(entry.file_size for entry in entries) > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise DocumentError("The expanded Office document exceeds the 32 MB safety limit.")
            if required_member not in archive.namelist():
                raise DocumentError("The file is not a valid supported Office document.")
    except DocumentError:
        raise
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        raise DocumentError("The Office document is damaged or invalid.") from exc


def _extract_docx(raw: bytes) -> str:
    _validate_office_archive(raw, "word/document.xml")
    try:
        from docx import Document
        document = Document(io.BytesIO(raw))
        parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text.replace("\n", " ").strip() for cell in row.cells))
        return "\n".join(parts)
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError("The Word document could not be read.") from exc


def _extract_xlsx(raw: bytes) -> str:
    _validate_office_archive(raw, "xl/workbook.xml")
    workbook = None
    try:
        from openpyxl import load_workbook
        workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        parts = []
        for sheet in workbook.worksheets:
            parts.append(f"[Sheet: {sheet.title}]")
            for row_number, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                if row_number > MAX_SPREADSHEET_ROWS:
                    raise DocumentError("A worksheet exceeds the 20,000-row extraction limit.")
                values = ["" if value is None else str(value) for value in row[:MAX_SPREADSHEET_COLUMNS]]
                if any(values):
                    parts.append(" | ".join(values))
                if sum(len(part) for part in parts) > MAX_EXTRACTED_CHARS * 2:
                    break
        return "\n".join(parts)
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError("The Excel workbook could not be read.") from exc
    finally:
        if workbook is not None:
            workbook.close()

def extract_document(filename: str, content_base64: str) -> dict[str, object]:
    """Decode a bounded base64 upload and extract supported text in memory."""
    safe_name = PurePosixPath((filename or "").replace("\\", "/")).name
    suffix = PurePosixPath(safe_name).suffix.lower()
    if not safe_name or suffix not in SUPPORTED_EXTENSIONS:
        raise DocumentError("Supported formats: PDF, DOCX, XLSX, TXT, Markdown, CSV and JSON.")
    if not isinstance(content_base64, str) or not content_base64:
        raise DocumentError("The uploaded file is empty.")
    # Reject oversized encoded input before allocating the decoded buffer.
    if len(content_base64) > ((MAX_UPLOAD_BYTES + 2) // 3) * 4 + 8:
        raise DocumentError("The file exceeds the 8 MB upload limit.")
    try:
        raw = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DocumentError("The uploaded file is not valid base64 data.") from exc
    if not raw:
        raise DocumentError("The uploaded file is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise DocumentError("The file exceeds the 8 MB upload limit.")

    ocr_used = False
    if suffix == ".docx":
        text = _extract_docx(raw)
        page_count = None
    elif suffix == ".xlsx":
        text = _extract_xlsx(raw)
        page_count = None
    elif suffix == ".pdf":
        if not raw.startswith(b"%PDF-"):
            raise DocumentError("The file extension does not match a valid PDF document.")
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw), strict=True)
            if reader.is_encrypted:
                raise DocumentError("Password-protected PDFs are not supported yet.")
            pages = []
            for page in reader.pages[:100]:
                pages.append(page.extract_text() or "")
            text = "\n\n".join(pages)
            if len(text.strip()) < MAX_OCR_TEXT_THRESHOLD:
                text = _ocr_pdf(raw, min(len(reader.pages), MAX_OCR_PAGES))
                ocr_used = bool(text.strip())
        except DocumentError:
            raise
        except Exception as exc:
            raise DocumentError("The PDF could not be read. It may be damaged or unsupported.") from exc
        page_count = len(reader.pages)
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentError("Please upload a UTF-8 encoded text document.") from exc
        page_count = None
        if suffix == ".json":
            try:
                parsed = json.loads(text)
                text = json.dumps(parsed, ensure_ascii=False, indent=2)
            except json.JSONDecodeError as exc:
                raise DocumentError("The JSON document is invalid.") from exc
        elif suffix == ".csv":
            try:
                rows = list(csv.reader(io.StringIO(text)))
                if rows and len(rows) > 20_000:
                    raise DocumentError("The CSV contains too many rows (maximum 20,000).")
            except csv.Error as exc:
                raise DocumentError("The CSV document could not be parsed.") from exc

    text = text.replace("\x00", "").strip()
    if not text:
        raise DocumentError("No readable text was found in this document.")
    truncated = len(text) > MAX_EXTRACTED_CHARS
    return {
        "filename": safe_name,
        "format": suffix.lstrip("."),
        "text": text[:MAX_EXTRACTED_CHARS],
        "characters_extracted": min(len(text), MAX_EXTRACTED_CHARS),
        "truncated": truncated,
        "page_count": page_count,
        "stored": False,
        "ocr_used": ocr_used,
    }
