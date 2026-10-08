# Advisor context and business portfolio

Checkpoint: 2026-10-08. Backend data only; the user explicitly deferred the visible portfolio screen.

## Scope

This checkpoint adds reviewed business knowledge, read-only advisor context and a paginated portfolio of the authenticated user's businesses. It includes cash-flow diagram data and five financial indicators from reviewed financial snapshots. It does not implement a conversational model, automatic journal aggregation, a financial-statement parser, or a complete accounting dashboard.

Migration 6 adds immutable knowledge proposals and decisions. Migration 7 adds immutable financial snapshots, per-field document references and decisions. All new tables have tenant RLS, composite same-business references, author checks and append-only triggers. The existing restricted runtime role receives SELECT/INSERT only. Apply migrations using the existing backend CLI before serving these endpoints.

## API surface

All routes require the existing bearer credential. Proposal and decision routes require an `Idempotency-Key`; a different payload cannot reuse a key. Editors can propose; owners/reviewers can decide. Viewers can read. Context, record-detail and portfolio responses use `Cache-Control: no-store`.

| Route | Contract |
|---|---|
| `POST /businesses/{business}/knowledge` | Propose a knowledge key, Persian statement, evidence and validity interval. |
| `GET /businesses/{business}/knowledge/{id}` | Read a proposal and its decision. |
| `POST /businesses/{business}/knowledge/{id}/decision` | Record approved/rejected plus a Persian reason; one immutable decision per claim. |
| `POST /businesses/{business}/advisor/context` | Read selected confirmed knowledge and optionally one saved inventory analysis. |
| `POST /quick/advisor/context` | Calculate from request-local inventory inputs; no business-history retrieval. |
| `POST /businesses/{business}/financial-snapshots` | Propose the seven evidenced financial inputs described below. |
| `GET /businesses/{business}/financial-snapshots/{id}` | Read submitted inputs and review status. |
| `POST /businesses/{business}/financial-snapshots/{id}/decision` | Approve/reject with a reason. |
| `GET /businesses/{business}/overview?effective_at=...` | Business profile, knowledge highlights, recent inventory findings and financial summary. |
| `GET /advisor/portfolio?effective_at=...&limit=10&after=...` | Cursor-paginated summaries of accessible businesses only. |

`effective_at` must include a timezone. Knowledge intervals use instants with inclusive start/exclusive end. Financial period selection uses the effective date in the business timezone. Review status is current: these endpoints do not reconstruct historical approval state. A portfolio page reads each business separately, not one global snapshot across all businesses.

## Knowledge and read-only tools

A knowledge proposal has `key` (lowercase ASCII identifier, up to 80 characters), `statement_fa` (up to 2,000 characters), `evidence` with `document_id` and `locator`, and `valid_from`/optional `valid_to`. The server assigns identity and author. Documents must belong to the same business; their original bytes are hash-verified during proposal, approval and context retrieval.

Business context accepts `question_fa`, `effective_at`, up to ten unique `knowledge_keys`, optional `analysis_id`, and `include_financial` (default false). The latter retrieves the latest eligible reviewed financial snapshot and its five indicators in the same scoped transaction. Only approved, currently applicable claims enter context. Groups are `missing`, `confirmed` or `conflict`. Different overlapping approved statements remain visible as a conflict; matching text retains all evidence. Pending/rejected/expired claims do not become context knowledge.

Selected analyses preserve exact result strings, metric version, input hash, source provenance and stored explanation. They are snapshots: later documents may require a new analysis. Narrative knowledge is never fed into the numeric reconciliation engine. Questions and claims remain untrusted data, not instructions to call tools. The context builder exposes no model-controlled tool dispatcher and makes no model calls.

Quick accepts only `question_fa` and the existing typed `inventory` request. Its pure context function has no database/service parameter. Authentication is still required at the API boundary. It does not retrieve, validate against, or persist business history; submitted evidence IDs are request-local references. Neither mode stores questions or conversation history in application tables. Infrastructure/access-log configuration remains a separate operational concern.

Business contexts refuse more than 20 matching claims or more than 64 KiB of encoded response. They do not silently truncate evidence. The portfolio is a preview: up to three knowledge keys, ordered by conflicts then most recent review, and three recent inventory analyses. Preview text is capped at 300 characters with an explicit truncation flag. Conflicts show no single accepted statement. Claim/document IDs and locators support drill-down. The overview does not hash-check knowledge files; full context retrieval does.

## Financial snapshots and chart data

Each snapshot has `period_start`, `period_end` (later than start), `currency: IRR`, and seven fields. Each field is `{value: "decimal string", evidence: {document_id, locator}}`:

- `opening_cash`: starting cash, signed (may represent an overdraft).
- `cash_inflows`, `cash_outflows`: nonnegative gross cash movements during the period.
- `revenue`: nonnegative revenue for the period.
- `net_income`: signed net income for the period.
- `current_assets`, `current_liabilities`: nonnegative closing balances.

Inputs allow at most 28 digits including six fractional digits; floats, nonfinite numbers and excess precision are rejected. Cash arithmetic uses Decimal at precision 40. Ratios also use Decimal at precision 40; repeating ratios are rounded at that precision. Amounts and ratios are serialized as strings. Revenue/profit are distinct from cash receipts/payments.

| Indicator | Formula | Unit |
|---|---|---|
| Revenue | reviewed revenue | IRR |
| Net income | reviewed net income | IRR |
| Net cash flow | inflows minus outflows | IRR |
| Current ratio | current assets / current liabilities | fraction |
| Net profit margin | net income / revenue | fraction; multiply by 100 for percent display |

`constants` preserves the seven numerical inputs and computed closing cash. `cashflow_diagram` contains ordered waterfall steps: absolute opening cash, relative inflows, negative relative outflows, total closing cash. Closing cash = opening cash + inflows - outflows. Every indicator/diagram lists its input fields; the shared `evidence` map and document hashes provide citations. No frontend rendering is included in this checkpoint.

The latest approved period ending on or before the effective date is selected. Multiple approved snapshots at that period end return `conflict` with candidate IDs and no chart/values. No eligible approved snapshot returns `missing` with five unavailable indicators. A zero denominator returns an undefined ratio rather than zero or infinity. Rejected/pending snapshots are never used. Financial evidence bytes are rechecked during approval and summary reads; tampering fails closed. Calculated closing cash is not a substitute for reconciliation to the actual bank/cash count.

Synthetic verification example: opening 100 + inflows 250 - outflows 180 = closing 170 IRR. Revenue 400, net income 80 and assets/liabilities 600/300 produce five indicators: 400, 80, 70, 2 and 0.2. These numbers are test data, not defaults or a customer's financial results.

## Remaining work

Confirmed-record correction/supersession, conversational orchestration, evaluated model responses, production logging/privacy configuration, automatic statement mapping and full portfolio capacity tests remain open. Knowledge key semantics are application-defined; no semantic similarity matching is claimed. UI work will use the user's Kalameh and Contour preferences in a later checkpoint.

## Validation

Full suite: 122 passed, one real OCR test skipped. The final portfolio boolean response correction also passed its targeted test; Ruff and whitespace checks passed. All new acceptance data is synthetic. See [validation record](VALIDATION.md).

## Opt-in local draft responses

Start the existing server with `--advisor-model <already-installed-model>` to enable drafts. `--advisor-url` defaults to `http://127.0.0.1:11434` and must be an explicit loopback HTTP URL. The application does not install or pull a model. Without the model flag, draft routes return 503 while context and portfolio routes remain available.

`POST /businesses/{business}/advisor/draft` accepts the same typed request as business context, including optional `include_financial: true`. `POST /quick/advisor/draft` accepts the same request-only input as Quick context. The server builds context before invoking the model; credentials, arbitrary client context, tool names and provider configuration are not accepted in the request body.

Responses contain `status: draft`, `verified: false`, `persisted: false`, the exact `context`, its canonical UTF-8 JSON SHA-256, and `draft` with Persian text/model/status. This hash identifies the context, not the correctness of model prose. Display model output as plain untrusted text and retain the calculated values/citations alongside it. A draft cannot approve knowledge or financial snapshots, alter records, or execute model-requested tool calls.

Inference is limited to one active request per application process, with a transport timeout, 64 KiB input/response-byte limits, a 12,000-character content limit and a 1,024-token generation option. Oversized, partial, malformed and tool-call outputs are rejected. Disabled/busy/unavailable inference returns a generic 503 with no-store headers. Busy responses include Retry-After. No new application conversation storage is introduced; Ollama/service-log retention must be evaluated separately before real customer use.

On 2026-10-08 the loopback Ollama API was unavailable and no executable was found on PATH. Automated tests use explicit stubs for model behavior; real model accuracy and prompt-injection resistance remain unverified. The software boundary prevents posting; it cannot certify that draft prose is factually correct.
