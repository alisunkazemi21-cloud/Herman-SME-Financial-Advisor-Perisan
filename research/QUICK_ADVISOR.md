# General Quick Advisor

Milestone **C11**, 2026-10-11. Backend only. Quick now accepts a question without inventory data, optional text excerpts and optional financial figures. It uses only the current request. Business context and saved cases retain their separate reviewed-data/history contracts.

## Routes and response

Both routes require the existing bearer credential and return successful responses with `Cache-Control: no-store`. Neither needs an idempotency key because neither writes application records.

| Route | Behavior |
|---|---|
| `POST /quick/advisor/context` | Validate the supplied context and calculate selected supported metrics; no model call |
| `POST /quick/advisor/draft` | Build the same context, then request an explicitly unverified local model draft |

A question-only request is valid: `{"question_fa": "تفاوت سود و جریان نقد چیست؟"}`. The deterministic route returns context and limitations, not an invented answer. A configured local Ollama model is required for draft prose; unavailable/disabled inference returns the existing generic 503. The model can explain general concepts and request missing information, but receives no tools for retrieving history, reading files, posting or approval. Numeric conclusions must come from attached calculations. Actual model quality and prompt-injection resistance remain unverified.

The context has `mode: quick`, `context_version: quick.context.v2`, the question, notes, supplied source receipts, optional inventory/financial results, empty `knowledge`, `history_used: false` and `persisted: false`. Draft responses retain the exact context and canonical SHA-256, plus `status: draft` and `verified: false`. A correct context hash does not certify the draft or the truth of supplied data.

## Request fields

| Field | Contract |
|---|---|
| `question_fa` | Required nonblank question, at most 2,000 characters |
| `notes_fa` | Optional context, at most 4,000 characters |
| `sources` | Up to eight request-local text excerpts; default empty |
| `financial` | Optional explicit period, unit, figures and requested metrics |
| `inventory` | Optional existing typed inventory request, unchanged calculation semantics |

Each source has a unique `source_id` (1–64 ASCII identifier characters), `title_fa` (1–160 characters) and nonblank `text_fa` (at most 6,000 characters). Text is preserved, including surrounding whitespace, and the response hashes its UTF-8 bytes as `text_sha256`. Source IDs are references within this request, never database selectors. Text hashes identify the supplied excerpt, not an authenticated original file. Source receipts and financial inputs are labeled `user_supplied_unverified`.

Quick does not retrieve a URL or file path mentioned in text. Source selectors, business IDs, analysis/report IDs, history, system prompts and tools are not accepted as extra request fields. Numbers in questions, notes or excerpts are not automatically parsed into financial figures. Excerpts can contain untrusted instructions; the system prompt treats those as data, and the model has no action tools.

Both the normalized request context and expanded response context must fit within 64 KiB of UTF-8 JSON. Expansion repeats per-metric input references, so a request can fit while its response is too large. The server refuses either excess rather than truncating sources or provenance. These limits concern encoded typed context, not a raw HTTP body-size guarantee; deployment request limits are a separate concern.

## Financial input

`financial` requires `period_start` and `period_end` as ISO Gregorian dates, with end after start, and explicit `amount_unit: IRR` or `IRT`. Fields refer to the same business, period and unit by the caller's assertion; source text does not prove that assertion. Balance-sheet values are closing balances; `opening_assets`, `opening_equity` and `opening_cash` refer to the beginning of the period. Revenue, income, expenses and cash movements cover the declared period.

`facts` is a list of up to 17 unique fields, defaulting to empty. Each fact has `field`, `value`, `source_id` and a nonblank `locator` of at most 300 characters. The source ID must exist in this request. Repeated field names fail even if their values match, so conflicting sources cannot silently overwrite one another. Values use decimal strings or integers; floats, booleans, nonfinite values and excess precision fail. Supplied amounts and converted rial values allow 22 integer and six fractional places, excluding insignificant trailing zeroes. Toman-to-rial conversion multiplies by exactly ten and rejects overflow.

Allowed fields are `current_assets`, `inventory`, `prepayments`, `current_liabilities`, `total_assets`, `total_liabilities`, `equity`, `opening_assets`, `opening_equity`, `revenue`, `cost_of_goods`, `net_income`, `ebit`, `interest_expense`, `opening_cash`, `cash_inflows` and `cash_outflows`. Equity, opening equity, income, EBIT and opening cash may be signed; the other fields must be nonnegative. Supplied components cannot exceed a supplied corresponding total. The balance-sheet identity and inventory-plus-prepayments bound are checked whenever all needed fields are present.

`requested_metrics` defaults to all twelve supported calculations. An explicit selection contains 1–12 unique keys. Missing inputs remain missing; an empty facts list is valid and yields missing-input statuses.

| Key | Formula / needed fields |
|---|---|
| `current` | Current assets / current liabilities |
| `quick` | (Current assets − inventory − prepayments) / current liabilities |
| `equity` | Equity / total assets |
| `debt` | Total liabilities / total assets |
| `gross_margin` | (Revenue − cost of goods) / revenue |
| `net_margin` | Net income / revenue |
| `roa` | Net income / average of opening and closing assets |
| `roe` | Net income / average of opening and closing equity |
| `turnover` | Revenue / average of opening and closing assets |
| `interest_coverage` | EBIT / interest expense |
| `net_cash_flow` | Cash inflows − cash outflows |
| `closing_cash` | Opening cash + cash inflows − cash outflows |

Quick uses the same ten ratio definitions as the earlier local analysis pipeline. The legacy pipeline's result shape, formulas and caller arithmetic context are preserved. Quick arithmetic uses a separate Decimal context with 60 significant digits and half-even rounding; sums/conversions within the bounded inputs are exact, while nonterminating division is rounded at that precision. Ratios have unit `fraction`, not percentage; cash outputs have unit `IRR`.

Each calculation returns its key, Persian label/formula, input-field list, present input values in rial with source IDs/locators, missing-field list and one status:

- `available`: supported calculation has the required inputs; this describes arithmetic availability, not source verification.
- `missing_inputs`: at least one needed field was not supplied; value is null and no zero is inferred.
- `undefined`: inputs exist but the ratio denominator is nonpositive; value is null with a Persian explanation.

The response also includes the supplied figures and their normalized rial values. No numeric figure is extracted from prose, guessed from another business or persisted as knowledge.

## Example and evidence

[The Persian example request](../samples/quick_advisor.example.json) supplies current assets and liabilities in toman. The current ratio is 2; the quick ratio and net cash flow correctly report missing inputs. It can be submitted to either Quick route with the operator's bearer header. Keep credentials out of saved request files.

[Validation](VALIDATION.md) records software evidence. The focused suite includes independent expected values for all twelve metrics and the existing ten-ratio path, missing/undefined inputs, large precise currency conversion, ambient-context independence, source text/hash preservation, duplicate/reference validation, input/output bounds, authenticated routes without business transactions, no carryover to a later request and prompt/transport isolation. Model replies and all financial data are synthetic.

## Remaining boundaries

This checkpoint adds general request inputs and a qualitative draft prompt. It does not add stateless binary PDF/image upload, automatic financial extraction/classification, model-selected calculations, rates, forecasting from excerpts, legal interpretation, a new screen or evaluated real-model advice. Authentication still queries credentials; Quick does not query business/history tables or store conversations. Ollama and deployment logging/retention require separate operational validation. Reviewable business records and persistent cases remain in the business mode.
