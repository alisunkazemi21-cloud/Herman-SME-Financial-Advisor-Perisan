# From conversation history to an auditable financial ledger

Conversation memory helps follow a question, but it does not establish accounting facts. This checkpoint adds a separate tenant-scoped posting workflow: an evidenced proposal, a human decision, and exact balances derived only from approved entries. It extends the PostgreSQL backend while preserving the earlier local prototype.

The central invariant is equal debit and credit totals across 2–100 distinct-account lines. Python validates exact Decimal inputs, and deferred database constraints validate the committed line set. Immutable headers alone would be insufficient because later child inserts could alter the entry. A transaction-stamping guard closes that path by permitting lines only during header creation.

Corrections preserve original history. A new reversal exactly inverts the approved original; it requires independent approval and takes effect on its own date. A replacement is another proposal. Accounting-pattern duplicates require explicit reviewer treatment because matching amounts and accounts are candidates, not proof of the same real event.

The trial balance reports opening net positions, dated debit/credit movements and closing net positions as decimal strings. It verifies source files and refuses oversized reports. The result is a current-snapshot view of approved entries, not a permanently published statement or proof of statutory compliance. See [validation](../VALIDATION.md) and [the journal contract](../JOURNALS.md).
