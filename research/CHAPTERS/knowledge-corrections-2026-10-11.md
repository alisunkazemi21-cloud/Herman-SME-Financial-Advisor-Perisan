# Correcting business knowledge without erasing history

Milestone **C12** in the [development map](../PROGRESS.md) gives a reviewed business claim a correction path. Previously, a second differing approved statement for the same key remained a conflict even when it was intended to correct the first. The new path names its predecessor explicitly. A recent timestamp alone never grants precedence over other evidence.

Approval replaces the whole predecessor, including its validity dates. This permits correcting a mistaken interval without silently falling back to outdated information outside the new interval. Where no independent approved claim applies, the answer is missing knowledge. Separate non-overlapping claims represent genuine changes over time. Saved receipts preserve earlier retrieval; fresh context uses current review state.

The database requires an approved predecessor with the same business and key, and derives each decision's link from the immutable proposal. A unique approved-successor index prevents branches under concurrent review. A losing candidate remains pending with no committed approval audit or idempotency receipt. Rejection does not consume the replacement slot.

Current selection excludes replaced claims before limits and conflict aggregation. Independent conflicting statements remain conflicts; matching statements keep separate citations. Paginated lists and predecessor/successor links expose history without copying every revision into model context. Typed financial calculations never consume narrative statements as numeric input.

Twenty-four focused checks passed, including concurrent reviews, interval changes, immutable case receipts, financial-value isolation, direct SQL guards and tenant boundaries. The full PostgreSQL suite passed **250 tests**, with **one real-OCR skip**; Ruff and whitespace checks passed. The [contract](../KNOWLEDGE_CORRECTIONS.md) records exact semantics. Inventory correction, real engine quality, operational acceptance and the deferred visible portfolio remain separate work.
