# Secure document extraction

## API

Authenticated endpoint: `POST /api/files/extract`.

Request JSON:
- `filename`: original filename (the server keeps only its basename).
- `content_base64`: base64-encoded file bytes.

Supported formats: PDF, DOCX, XLSX, TXT, Markdown, CSV and JSON.
Maximum upload size: 8 MiB. Extracted text is capped at 24,000 characters.
PDF text extraction is limited to the first 100 pages. If the text layer is empty, OCR processes up to 20 pages using Tesseract (English and Russian language data are installed in the container). Each page has a 15-second OCR timeout and a bounded render size. Encrypted PDFs are rejected. DOCX paragraphs and tables are extracted; XLSX worksheets are read without executing formulas. Office ZIP containers are limited to 2,000 entries and 32 MiB expanded size; worksheets are limited to 20,000 rows and 200 columns.
CSV parsing checks the row limit; JSON is parsed and pretty-printed.

The upload is processed in memory. The endpoint does not write the original file or extracted content to the database or filesystem. The response explicitly reports `stored: false`.

## Safety and limitations

- The endpoint requires an AI HUB session.
- File type is checked by extension and, for PDFs, the PDF signature.
- Malformed base64, invalid UTF-8, invalid JSON, unsupported formats, oversized files and empty extracted text are rejected.
- This iteration extracts text from supported office/text documents and OCRs scanned PDFs. It does not execute macros, render embedded media, or persist files.
- Callers should pass extracted text to an AI model only after the user chooses to analyze it; extraction itself does not call a provider.
- Uploads are not malware-scanned or stored. Do not treat this first iteration as a general-purpose file vault.

## Next steps

Next: private object storage with retention/deletion controls, broader image OCR, and provider-backed analysis with per-request cost limits.
