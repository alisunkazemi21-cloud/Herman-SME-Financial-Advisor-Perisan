# Advisor and portfolio technical report

Checkpoint: `advisor-portfolio-2026-10-08`. Engineering validation uses synthetic data.

Added tenant-scoped, reviewed business knowledge and financial snapshots. Business context exposes selected evidence and stored calculations without write tools; Quick uses request-local inventory data only. Portfolio summaries show accessible businesses, knowledge conflicts, pending knowledge reviews and recent inventory findings.

Five financial indicators (revenue, net income, net cash flow, current ratio, net margin) and opening/inflow/outflow/closing waterfall data derive from reviewed Decimal inputs. Missing data stays unavailable; conflicting latest-period snapshots are not automatically selected. Each numerical input retains document evidence. This is backend chart data; the user deferred the visible screen.

Validation: 122 tests passed, one real OCR test skipped. The final response-type correction passed its targeted portfolio test; Ruff and whitespace checks passed. Graphify was refreshed. Conversational model integration, correction workflows and full portfolio capacity validation remain open.

[API, formulas and limitations](../research/ADVISOR_PORTFOLIO.md)
