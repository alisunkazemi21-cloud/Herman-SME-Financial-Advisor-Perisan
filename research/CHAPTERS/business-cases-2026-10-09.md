# Business conversation history with evidence boundaries

A continuing business question needs remembered context without turning a prior generated assertion into an accounting fact. The implementation separates immutable conversation records from reviewed knowledge and deterministic financial values. Each new turn rebuilds structured business context and adds at most three prior replies, explicitly marked non-authoritative.

An expected turn number and database uniqueness prevent silent branching. Typed-request idempotency lets completed retries recover the original answer even though language-model output is nondeterministic. Generation occurs outside database transactions; authorization and sequence are checked again before publication. Concurrent generation can occur, but only one continuation can occupy a given position.

Tests use deliberately unverified model prose and assert that history does not create knowledge or financial inputs. Nine focused tests passed against PostgreSQL, including revocation and concurrency scenarios. The test design demonstrates software boundaries, not semantic resistance to every prompt injection or Persian financial reasoning quality. Full-suite results appear in [validation](../VALIDATION.md).

The saved receipt is historical evidence of what context the advisor received, not independent proof that its answer is correct. Human review and typed financial calculations remain separate. Quick has no persisted conversation. Interface work remains deferred.
