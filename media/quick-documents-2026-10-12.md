# A document can support a small question without becoming business history

C15 adds temporary document intake to Herman's Quick Advisor backend. An owner can send a supported spreadsheet, PDF or image, review the extracted content, and include it in a Quick question without first creating a business profile. Page and row references help identify where an excerpt came from.

Extracted text is not an approved financial record. The owner still supplies and checks amounts, units and dates before supported calculations run. Quick does not save the uploaded document or a conversation history, and a later question has no access to an earlier request unless the caller sends its information again.

The final focused Quick suite passed 86 tests, including all 50 document-intake cases; a full regression run passed 362 tests with one OCR skip before the final source-location fix. The [run record](../runs/quick-documents-2026-10-12/README.md) records the exact validation scope. Documents and model-related replies used in tests are synthetic. Real Persian OCR and local-model answer quality still need evaluation. This checkpoint extends backend behavior; the visible portfolio remains deferred.
