# Spreadsheet records now have a traceable path into the books

A business can now map an extracted CSV or Excel journal table, preview the resulting entries and submit the selected vouchers for review. The operator identifies the accounts, dates and rial/toman unit explicitly. If any selected voucher is invalid, the batch is not saved.

Every imported line keeps its connection to the source file and spreadsheet row. That connection follows the entry into later financial report receipts. Uploading an identical file under another name, or extracting it again, cannot import the same rows twice. Similar events in different files still require human duplicate review.

Importing does not post the entries. An authorized reviewer must check and approve them before they affect financial balances, and reports retain their own review requirements. Incorrect imports remain in history; corrections use explicit replacement records.

The focused checks passed on synthetic spreadsheets. This checkpoint adds backend capability; the visible portfolio screen is still deferred, and real OCR/model quality remains to be evaluated. See [the checkpoint record](../runs/journal-imports-2026-10-11/README.md) for evidence and limitations.
