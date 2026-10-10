# Journal imports from extracted tables

Checkpoint: 2026-10-11. This connects the durable CSV/XLSX extraction queue to tenant journal proposals. It adds backend routes; the portfolio screen remains deferred.

## Workflow

1. Create the business account catalog, upload a document and obtain a successful extraction through the [document queue](DOCUMENT_QUEUE.md).
2. Inspect the extraction's normalized sheet, column names and row numbers. Map the voucher identifier, account code, debit, credit, date and description columns explicitly. Choose `IRR` (rial) or `IRT` (toman), and `jalali` or `gregorian` dates.
3. Preview the selection. Preview verifies source bytes, account membership, complete voucher groups, values and balance but writes nothing. Resolve mapping errors before importing.
4. Import with an idempotency key. Every selected voucher becomes a pending [journal proposal](JOURNALS.md); any invalid voucher rolls back the whole batch, including provenance and the idempotency record.
5. A business owner or reviewer checks source values, conversion, accounts and duplicates before approving each entry through the existing journal decision route. Only approved entries affect balances. Reviewed report mappings and scope decisions remain separate requirements for [portfolio/advisor reports](JOURNAL_REPORTS.md).

## Mapping contract

The request contains:

```json
{
  "extraction_id": "<successful-extraction-uuid>",
  "sheet": "CSV",
  "rows": [2, 3],
  "voucher_column": "voucher",
  "account_column": "account",
  "debit_column": "debit",
  "credit_column": "credit",
  "date_column": "day",
  "description_column": "description",
  "date_kind": "jalali",
  "amount_unit": "IRT"
}
```

Column names refer to extraction output, not necessarily the original header spelling: the parser normalizes known Persian aliases and Persian/Arabic digits. All six mapped columns must be distinct. CSV uses sheet name `CSV`; XLSX uses its actual worksheet name. Row numbers are one-based source rows, with row 1 reserved for the header. Select 2–500 unique integer rows from one sheet.

The table must be long-form, with one account line per source row. Every nonempty row on the chosen sheet needs a voucher key; remove footers or mixed tables from a separate, explicitly corrected source before extraction. Selecting a voucher requires all its rows from that sheet. Its dates and descriptions must agree. Each voucher has 2–100 distinct account codes already in the business catalog. Repeated accounts are rejected rather than aggregated; source row order becomes line order. One debit or credit must be positive and the other blank or zero. Negative amounts and unbalanced vouchers fail.

Gregorian dates use `YYYY-MM-DD`; Jalali dates pass the existing Jalali validator and produce matching Gregorian/Jalali journal dates. Unit inference is never used. Toman amounts are multiplied by exactly ten before journal validation. Values remain decimal strings; no floating-point conversion or rounding into acceptance occurs. Amounts allow up to 22 integer and six fractional decimal places, excluding insignificant trailing zeroes. An independent tuple-based check prevents hidden fractional tails from being accepted under a low Decimal precision context. Spreadsheet numeric cells may already have lost precision before upload; store exact amounts and account codes as text when preparing source workbooks. Excel formulas are rejected by the extractor.

## API and roles

Routes are under `/businesses/{business}/journal` and require bearer authentication. Successful responses use `Cache-Control: no-store`.

| Method | Route | Result |
|---|---|---|
| POST | `/imports/preview` | `persisted: false`, source hash, parser version, voucher keys, source rows and complete proposed entries |
| POST | `/imports` | Batch ID; requires `Idempotency-Key` |
| GET | `/imports` | Metadata page; optional `after` UUID and `limit` (1–50, default 20) |
| GET | `/imports/{id}` | Batch mapping, proposed entry IDs/current decisions and source origins |

All business members may read and preview. Owners, editors and reviewers may import; only owners/reviewers may approve journals. Pagination uses UUID order. A completed retry with the same key and request returns the existing batch, including under concurrent requests. Different requests under the same key conflict. A preview reserves nothing: import revalidates the source and reuse checks, so another import can invalidate an earlier preview.

## Duplicates, provenance and corrections

Migration 012 adds append-only import batches and per-line origins. Composite foreign keys and forced row-level security isolate businesses. Origins preserve extraction ID, parser version, file hash, selected mapping, sheet/row and normalized cell values. Original document bytes remain in the evidence store.

The database enforces source uniqueness by **business + file SHA-256 + sheet + row**. Renaming an identical upload or running another extraction cannot reimport its rows. This protection survives rejection of the proposed journal; rejection does not erase source use. Correct mapping in preview first. After an incorrect import, reject the proposal and submit a separately evidenced manual replacement, or upload a deliberately corrected source version. Approved mistakes require the existing reviewed reversal/replacement workflow. There is no hidden source-reuse override or automatic approval.

Different file bytes can represent the same event. Existing journal fingerprints therefore still flag matching date/currency/account/side/amount patterns for explicit duplicate review. Equal amounts alone do not establish duplication, and changed account splits or semantically similar scans remain outside this detector.

Database triggers require origins to refer to the same document, successful extraction, source hash, selected sheet/row, exact normalized source cells and journal locator. Batches, entries and origins must be created together by the same actor. Deferred checks require the batch's complete row selection and one origin per imported line, from one batch. Adding lines after an earlier forced constraint check also fails if their origins are absent. These checks preserve claimed lineage; they do not establish that the source document or the user's account mapping is financially correct.

Journal traces expose `origin`; new report manifests freeze `import_provenance` under the existing manifest hash. Older report receipts are unchanged. Batch reads describe saved lineage; preview, import, journal review/trace and report construction perform the relevant source-byte checks.

## Boundaries and evidence

This path handles explicit CSV/XLSX mappings only. It does not infer ledger accounts, extract journal tables from PDF/OCR text, aggregate repeated account rows, import recipes, close periods or prepare statutory filings. All test documents are synthetic. Real OCR and model quality remain separate gates. Synchronous import limits are not a throughput or 1,000-business capacity claim.

See [validation](VALIDATION.md) for the final test result and [requirements audit](REQUIREMENTS_AUDIT.md) for remaining product work.
