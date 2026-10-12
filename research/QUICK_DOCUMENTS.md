# Stateless Quick document intake

Milestone **C15**, started 2026-10-11. Backend intake supplies unverified document text to the existing [Quick Advisor](QUICK_ADVISOR.md). The owner does not need a business profile, and extraction does not create evidence, job, audit, journal, knowledge or case rows.

## Request flow

1. Send raw bytes to `POST /quick/documents/extract?format=csv&engine=tesseract`, using the existing bearer credential and `Content-Type: application/octet-stream`.
2. Review the returned `sources`. Submit them with `question_fa` to `/quick/advisor/context` or `/quick/advisor/draft` using JSON content type.
3. For supported numerical answers, separately supply explicit financial fields, dates, IRR/IRT unit and source/locator references. Text is never automatically promoted to financial facts.

`format` is required: `csv`, `xlsx`, `pdf`, `png`, `jpg`, `jpeg`, `tiff` or `bmp`. `engine` defaults to `tesseract`; `easyocr` is optional. No business ID, original filename, file path, URL, history selector, model endpoint or idempotency key is required. Questions belong in the subsequent JSON request, not in upload URLs or headers. Authentication is checked before intake and again before returning extraction results.

Tesseract requires a local executable and both `fas` and `eng` language packs. EasyOCR requires the optional package and preinstalled model weights in the server account's `.EasyOCR/model` directory. Downloads are disabled. Parser scratch directories, including auxiliary EasyOCR folders, stay under the temporary request directory. Neither adapter's real accuracy is established by synthetic tests.

## Extraction and references

CSV is UTF-8 (optional BOM) with comma-separated cells. CSV/XLSX rows, including headers and blank rows, are serialized as ordered JSON arrays of strings. Sheet and one-based row locators remain separate from those strings. No column-name mapping, currency/date interpretation or financial classification occurs. XLSX styles, displayed formatting, merged-cell semantics and cached formula results are not financial evidence. Formula cells, including array formulas, are rejected. Hidden sheets/rows are not silently filtered out.

PDF units use one-based page references. Pages with native text use that text; pages without usable native text use local OCR. This does not establish that native text includes every visible image or that reading order/layout is correct. Image units reference `image:1`; multi-frame images fail explicitly. A page with no extractable text fails the request rather than producing a silently partial response. Every extraction remains subject to human review.

The response contains:

- `profile: quick.document.v1`, `document` with original-byte SHA-256, declared format and byte count, and parser dependency versions.
- `sources`, ready for the existing Quick JSON routes. Each has a deterministic request-local ID, Persian title, text and optional `origin` metadata.
- Each origin records full-file SHA-256, source-text SHA-256, format and ordered locations. `start` is inclusive, `end` exclusive, and both count Unicode characters within that source text; `unit_offset` is the character offset within the original extracted row/page/image text. Spanning units retain their locator and offsets across chunks. Join separators are not attributed to an original unit.
- `verification: locally_extracted_unverified`, `history_used: false`, `persisted: false` and Persian limitations. Temporary paths and parser exception text are excluded.

Quick context labels resubmitted sources `user_supplied_unverified`, including their origins. The text hash and span bounds are checked; a caller can still replace both text and metadata. These are not signed server receipts, persistent evidence IDs or proof of the original bytes after deletion. Confidence describes parser output, not accounting correctness. Original-byte hashes permit comparison by a caller, but this endpoint keeps no cross-request duplicate index or conversation memory.

## Limits and failures

| Boundary | Limit / behavior |
|---|---|
| Raw upload | 10 MiB, checked while streaming as well as against a supplied length |
| Receive / parser deadlines | 30 / 60 seconds; process creation and final cleanup have separate OS timing |
| Concurrent intake | One per app instance/process, including upload and parser cleanup; no persistent queue |
| Tables | 2,000 rows total, 50 columns per row, 20,000 cells, 6,000 characters per cell |
| XLSX archive | 16 sheets, 5,000 entries, 25 MiB expanded size |
| PDF | Eight pages; estimated 200-dpi area at most 20 million pixels/page and 40 million total |
| Images | 20 million pixels, exactly one frame, image encoding matches the declared format |
| Extracted text | 40 KiB UTF-8 before packing |
| Reusable sources | Eight chunks of at most 6,000 characters; source JSON at most 48 KiB including references |
| Quick context | Existing 64 KiB request and expanded-result bounds still apply after adding question, figures or notes |

Limits are ceilings, not assurances that every document up to each ceiling fits all other bounds. A reference-heavy table can exceed the source JSON budget first. The request fails as a whole instead of truncating text, references or rows. Large work should use the persistent business workflow or an explicitly smaller source selection.

All Quick routes now return `Cache-Control: no-store` on handled successes and errors. Input-validation errors do not echo uploaded content or invalid source metadata. Intake error codes include `resource_limit` (413), `invalid_document` / `unsupported_document` / `no_text` (422), `receive_timeout` (408), `timeout` (504), and `engine_unavailable` / `parser_failed` / `busy` (503). Busy responses include `Retry-After: 5`. Authentication failures return 401. Unexpected deployment/proxy failures are outside these application response guarantees.

## Temporary lifecycle

Generated input/output names live in a private temporary directory. The parser runs without a shell, inherits only essential environment values, uses local scratch paths, and discards stdout/stderr. It waits for a start byte before importing parsers. Windows Job Objects contain ordinary descendants; POSIX uses a new session/process group. Remaining descendants are terminated even after a successful parent exit, before deleting the directory. Failed containment prevents parsing.

Cancellation stops awaiting the response but leaves bounded cleanup running with its capacity slot held. Ordinary disconnects during upload release the slot. A parser failure, timeout, invalid output or cleanup error cannot return a successful extraction. Application code does not retain the source or response. OS caches, machine crashes, power loss, server shutdown during cleanup, administrator access, external logging and secure deletion still require operational policy. This is lifecycle containment, not an OS security sandbox or a deployment-wide quota.

## Evidence and open work

Tests are in [test_quick_documents.py](../tests/test_quick_documents.py). The [validation log](VALIDATION.md) records focused and full results. Real parser subprocesses use synthetic CSV, XLSX and text PDFs. Image/scanned-page adapters use controlled OCR responses. These checks do not prove real Persian OCR quality, model-answer quality, semantic document mapping, accounting compliance or full workload capacity. Product UI remains deferred.
