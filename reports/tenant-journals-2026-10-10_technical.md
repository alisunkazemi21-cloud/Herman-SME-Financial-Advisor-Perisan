# Tenant journal technical report

Migration 009 introduces four immutable RLS-protected relations: accounts, journal entries, lines and decisions. Composite keys preserve business scope. Deferred constraints verify balanced line sets, normalized pattern hashes and exact reversal contents. A creating-transaction guard rejects later additions to a journal. Reviewer-only decisions control posting, and partial unique indexes constrain duplicate first approvals and approved reversals.

The API supports account/entry pagination, trace retrieval, proposals, decisions, reversal proposals and inclusive-date trial balances. Idempotency and audit records use the existing atomic write service. All amounts are Decimal/numeric values serialized as strings. File hashes are verified before posting and before trace/report values are returned.

All 18 journal tests and the isolated existing forecast test passed (19 combined). Final full-suite and tooling results are recorded in [validation](../research/VALIDATION.md). No real accounting documents or inference engines were used. The checkpoint does not establish journal throughput, standards compliance, statutory report classification, period closing or backup/restore readiness. The UI remains deferred.
