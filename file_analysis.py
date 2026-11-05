"""Safe, bounded text extraction for user-supplied documents.

Uploads are processed in memory and are not persisted by this module.
"""
from __future__ import annotations

import base64
import binascii
import csv
import io
import json
from pathlib import PurePosixPath

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_EXTRACTED_CHARS = 24_000
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".csv", ".json"}


class DocumentError(ValueError):
    """A document is invalid, unsupported, or exceeds a configured limit."""


def extract_document(filename: str, content_base64: str) -> dict[str, object]:
    """Decode a bounded base64 upload and extract supported text in memory."""
    safe_name = PurePosixPath((filename or "").replace("\\", "/")).name
    suffix = PurePosixPath(safe_name).suffix.lower()
    if not safe_name or suffix not in SUPPORTED_EXTENSIONS:
        raise DocumentError("Supported formats: PDF, TXT, Markdown, CSV and JSON.")
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

    if suffix == ".pdf":
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
    }
