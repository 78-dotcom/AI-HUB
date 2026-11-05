# Secure document extraction

## API

Authenticated endpoint: `POST /api/files/extract`.

Request JSON:
- `filename`: original filename (the server keeps only its basename).
- `content_base64`: base64-encoded file bytes.

Supported formats: PDF, TXT, Markdown, CSV and JSON.
Maximum upload size: 8 MiB. Extracted text is capped at 24,000 characters.
PDF extraction is limited to the first 100 pages. Encrypted PDFs are rejected.
CSV parsing checks the row limit; JSON is parsed and pretty-printed.

The upload is processed in memory. The endpoint does not write the original file or extracted content to the database or filesystem. The response explicitly reports `stored: false`.

## Safety and limitations

- The endpoint requires an AI HUB session.
- File type is checked by extension and, for PDFs, the PDF signature.
- Malformed base64, invalid UTF-8, invalid JSON, unsupported formats, oversized files and empty extracted text are rejected.
- This first iteration extracts text only. It does not OCR scanned PDFs, execute macros, render embedded media, or persist files.
- Callers should pass extracted text to an AI model only after the user chooses to analyze it; extraction itself does not call a provider.
- Uploads are not malware-scanned or stored. Do not treat this first iteration as a general-purpose file vault.

## Next steps

Add the browser upload flow, OCR for scanned documents, DOCX/XLSX extraction, private object storage with retention/deletion controls, and provider-backed analysis with per-request cost limits.
