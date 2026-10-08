# Local draft checkpoint summary

Checkpoint: `advisor-draft-2026-10-08`.

Business and Quick contexts can now produce Persian draft responses through an explicitly configured loopback Ollama adapter. Business requests may include reviewed financial indicators and cash-flow data. The server returns exact context and its hash beside unverified prose. Model output cannot invoke tools, post transactions or approve records; no conversation persistence is added.

Input/output limits, malformed-response handling and one inference slot per app process bound the integration. Full suite: 135 passed, one OCR test skipped. After the final financial-context addition, 19 focused tests passed. Ruff, CLI help and whitespace checks passed; Graphify was refreshed.

The local Ollama API was unavailable. Model behavior was stubbed in tests; real Persian response quality and injection resistance remain unverified. This checkpoint does not complete conversational case history or the full financial-advisor product.

[API contract and limitations](../research/ADVISOR_PORTFOLIO.md#opt-in-local-draft-responses)
