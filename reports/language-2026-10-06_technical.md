# Language checkpoint technical report

Checkpoint: `language-2026-10-06`.

Repository prose and generated Markdown now use English; application messages and Persian source data remain Persian. Archived narratives were translated from stored results without recalculation. All 13 protected data/evidence files were byte-identical.

Validation: 108 tests passed, one real OCR test skipped; Ruff and Marimo checks passed. Kalameh is the preferred font with an existing fallback pending font assets. `npx vibefarsi add contour` is scheduled for a later UI checkpoint, not executed here.

[Validation details and limitations](../research/VALIDATION.md)
