# Connecting reviewed accounting records to advice

Financial advice needs a reproducible account of the numbers it receives. This checkpoint introduces explicit reviewed account mappings and immutable report receipts. A receipt preserves journal lines, approval identities, source locators and hashes, then derives the portfolio's seven constants and five indicators using Decimal arithmetic.

The report distinguishes accrual income from cash movement. Cash transfers within mapped cash accounts cancel, while credit sales affect income and receivables without increasing cash. Inflow and outflow are sums of journal-level cash nets; a batch posting cannot establish gross bank flows. Closing entries and incomplete records also require human assessment. Separate report-scope approval makes that review explicit without claiming it is automatic proof of completeness.

Saved reports can become stale when new approved backdated entries appear. The receipt remains unchanged, but default numeric use stops. A separately reviewed replacement links to the predecessor, and a database uniqueness constraint prevents two approved replacement branches. This preserves the historical record while allowing the current portfolio to advance.

The advisor receives a bounded summary and report identifiers rather than all source lines. Quick remains request-only. Thirty-nine focused tests passed; see [validation](../VALIDATION.md) for the complete result and [the report contract](../JOURNAL_REPORTS.md) for limits. This does not establish real model quality, statutory compliance or application-wide capacity.
