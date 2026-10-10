# From spreadsheet evidence to reviewable accounting

Milestone **C10** in the [development map](../PROGRESS.md).

An extracted number is not yet an accounting fact. This checkpoint provides an explicit bridge: the operator chooses columns, a currency unit, a calendar convention and whole voucher groups. The backend validates the proposed account lines, then preserves each normalized source row beside its journal line. Source bytes, extraction version and mapping stay available for later review.

The import is atomic. A failed voucher leaves no partial batch. A successful import leaves only pending proposals: journal approval, account-to-report classification and report-scope review remain separate decisions. This allows deterministic arithmetic without presenting a successful parse as financial approval.

Two duplicate questions are distinct. Reusing the same file bytes and row is prevented automatically, even if the upload is renamed or re-extracted. Two different source files may describe the same event; existing accounting-pattern matching raises that question for a human reviewer. Rejected imports retain their source-use history, so corrections require an explicit replacement rather than silent reuse or deletion.

Provenance is also enforced by the database. Origins must match extraction cells, source hashes, locators and the creating actor/transaction. Deferred checks require complete batch and line coverage. Tests deliberately insert forged and incomplete references, including extra lines after an earlier constraint check, and confirm rejection. New report receipts freeze this lineage; old reports remain historical evidence.

A fractional-tail regression exposed why declared decimal limits need direct tests. Validation now inspects the Decimal coefficient and exponent without context-sensitive normalization. Tests cover excessive fractions and valid upper boundaries under a deliberately low arithmetic precision.

The focused suite passed 21 tests; [validation](../VALIDATION.md) records the full regression result. This establishes behavior on synthetic data, not OCR accuracy, model quality, statutory compliance or full application capacity. See [the import contract](../JOURNAL_IMPORTS.md) for scope and correction limits.
