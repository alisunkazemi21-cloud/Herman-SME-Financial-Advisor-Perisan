# Evidence review — 2026-10-05

This is a historical research record, not a new verification of the linked sources.

## Initial repository

The starting directory was empty: no code, real data or AGENTS.md was present. The specialized skills named in the original brief were not installed. The implementation was developed independently.

## Iranian accounting

The primary [Iranian Audit Organization source](https://audit.org.ir/WFrmCodificatedStandardView.aspx?Id=2) could not be retrieved during the initial review. The brief supplied standards 43 (revenue from contracts with customers), 39 (consolidated financial statements) and 16 (foreign exchange effects). Their official versions, effective dates and legal applicability were not verified. Convergence with IFRS does not imply equivalence.

The prototype flags relevant documents for accountant review rather than applying revenue recognition, consolidation or foreign-exchange rules automatically. Its sample accounts include cash, receivables, inventory, goodwill, payables, notes payable, provisions, capital, revenue and expenses. It does not assume one statutory chart for every SME.

## Ratio contracts

| Ratio | Formula |
|---|---|
| Current | Current assets / current liabilities |
| Quick | (Current assets − inventory − prepayments) / current liabilities |
| Equity | Equity / total assets |
| Debt | Total liabilities / total assets |
| Gross margin | (Revenue − cost of goods) / revenue |
| Net margin | Net income / revenue |
| Return on assets | Net income / average assets |
| Return on equity | Net income / average equity |
| Asset turnover | Revenue / average assets |
| Interest coverage | EBIT / interest expense |

Ratios are fractions, not percentages. Averages use opening and closing balances. Nonpositive denominators produce an undefined result and a Persian app explanation. Inputs must share a period and currency. No industry-independent good/bad threshold is imposed. Persian display labels are maintained in the application.

## Persian extraction

- [faniuta/ocr](https://github.com/faniuta/ocr) is a packaging example, not evidence of accuracy on this project's documents.
- [EasyOCR](https://github.com/JaidedAI/EasyOCR) and [Tesseract language models](https://github.com/tesseract-ocr/tessdata) support local execution. Required language/model files must be preinstalled; automatic model downloads are disabled.
- The [Aspose language documentation](https://docs.aspose.cloud/ocr/recognition-languages/) reviewed at the time listed Persian and more than 140 languages. Better accuracy on our documents was not demonstrated. No cloud transmission is enabled by default.
- [DocFlow's model card](https://huggingface.co/alirezaaminzadeh/docflow-invoice-parser-fa) described a 0.93 macro-F1 internal pilot and limitations around handwriting/date validation. This is an author-reported result, not independent validation for this project.

Preserve raw text, source hash, row/page location and extraction method. Confidence is not the probability that an accounting entry is correct. All entries need human review; confidence below 0.8 adds a warning.

## Local agents and computation

- [personal-financial-ai-agent](https://github.com/merendamattia/personal-financial-ai-agent) illustrates multiple providers including Ollama. It is a reference, not a runtime dependency.
- The brief cited wealthbraid as an append-only local ledger example; its primary repository was not confirmed in the initial search. The required architecture was designed independently.
- [Ollama chat API](https://docs.ollama.com/api/chat): structured messages with `stream=false`. The model produces draft text and receives no posting/approval tool.
- The [Persian Gemma model card](https://huggingface.co/mshojaei77/gemma-3-4b-persian-v0) supplied the Ollama name `mshojaei77/gemma3persian`. Accounting quality remains unevaluated; the model is configurable. The suggested nexus-finance model was not verified.
- [my727finance](https://pypi.org/project/my727finance/) is a financial toolkit. For ten small ratios, directly tested Decimal functions were selected for clarity.
- [pyxirr](https://pypi.org/project/pyxirr/) provides XIRR with day-count conventions. Nonconventional cash flows can have multiple roots; this implementation declines a potentially misleading single-root report when there is more than one sign change.
- [Marimo](https://docs.marimo.io/) and its [app runner](https://docs.marimo.io/guides/apps/) provide a reactive Python notebook. The prototype dashboard reads a shared manifest.
- [statsmodels ADF](https://www.statsmodels.org/stable/generated/statsmodels.tsa.stattools.adfuller.html) tests a unit-root null. Failure to reject is not proof of nonstationarity; short/constant series are not interpreted. Lag-12 correlation is only a seasonal screen, and Ramadan does not align with a fixed Solar Hijri month.

## Evidence gaps

No real invoice set, OCR ground truth, live USD/gold rates or installed project Ollama model was provided at the initial review. Real-engine and advice-quality assessments are reported separately from software tests. Rates and investment suggestions in the original prompt are not treated as factual inputs.

## Journal persistence review — 2026-10-09

Reviewed the PostgreSQL 17 [constraint-trigger contract](https://www.postgresql.org/docs/17/sql-createtrigger.html) and [row-security behavior](https://www.postgresql.org/docs/17/ddl-rowsecurity.html). Deferred row constraint triggers can check a journal after all lines have been inserted. Forced RLS and a restricted runtime role retain tenant boundaries; table owners and privileged administrators remain outside the application threat boundary. Implementation tests must exercise constraints through the restricted runtime role as well as through the API. No new accounting-standard claim follows from these database mechanisms.

## Journal cash summary — 2026-10-10

The IFRS Foundation's [IAS 7 reference text, paragraph 9](https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards/english/2021/issued/part-a/ias-7-statement-of-cash-flows.pdf) excludes transfers within cash/cash equivalents from cash flows. This supports cancelling mapped internal transfers in our journal-based cash summary. It does not justify presenting journal-level net movements as gross bank flows, or asserting current Iranian/IFRS compliance. Our implementation is an explicitly scoped management summary; classification and accounting completeness still require human review.
