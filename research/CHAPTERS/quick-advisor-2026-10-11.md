# Useful questions without invented financial facts

Milestone **C11** in the [development map](../PROGRESS.md) removes an inappropriate dependency: a quick financial question no longer needs an inventory reconciliation request. A user can ask a general question or supply a bounded excerpt. Neither action implies that the application knows the business's books or earlier conversations.

The design separates explanation, supplied claims and calculation. Questions and excerpts are untrusted context. A supplied financial figure has an explicit field, unit, period and source locator; its arithmetic can be validated without declaring the figure true. Excerpt hashes identify exactly the submitted text, and every metric retains references to its inputs. An absent value stays absent rather than becoming an invented zero.

The earlier ten-ratio formulas are shared with this path. Quick adds net and closing cash, checks supplied balance-sheet consistency, converts toman precisely and uses a fixed Decimal context. Nonpositive denominators are undefined, while incomplete inputs produce a different missing-input status. The model is asked to explain these states and request clarification; it cannot query the business, infer typed inputs from prose or post records through tools.

The full suite passed 226 tests with one real-OCR skip. Seventy-one focused checks cover this boundary and existing advisor/ratio behavior. This demonstrates software behavior on synthetic data; it does not validate real model answers or document interpretation. [The contract](../QUICK_ADVISOR.md) records the distinction, limits and remaining work. UI expansion remains deferred.
