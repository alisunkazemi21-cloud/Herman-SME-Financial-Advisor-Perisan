# Fix inventory records without erasing what happened before

A user can now propose a corrected stock count, purchase or other movement, recipe, or fulfilled order. The proposal links to the earlier record and needs human review. Until approval, the existing version remains in use. After approval, a new reconciliation uses the corrected record once.

The original record, imported cells and earlier calculations remain available. Corrected counts require explicit selection so a changed cutoff or item is not silently substituted. A recipe's ingredients cannot be added after review. If a changed recipe leaves a period without coverage, the result reports incomplete information.

This is milestone **C13**. Twenty-six focused checks passed before an additional source-origin test; the full PostgreSQL suite passed **277 tests**, including all 27 new correction cases, with **one real-OCR skip**. Ruff and whitespace checks passed; the final record-detail no-store and exact-decimal response adjustments passed two focused API/backend tests in 8.87 seconds. Earlier analyses remain snapshots and should be rerun with current reviewed inputs after a correction. The visible portfolio and real OCR/model evaluation remain open.
