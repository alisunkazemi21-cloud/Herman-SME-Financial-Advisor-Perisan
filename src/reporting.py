"""English Markdown presentation of existing results; app manifests remain Persian."""
from __future__ import annotations

from typing import Any

RATIO_LABELS = {
    "current": ("Current ratio", "Current assets / current liabilities"),
    "quick": ("Quick ratio", "(Current assets - inventory - prepayments) / current liabilities"),
    "equity": ("Equity ratio", "Equity / total assets"),
    "debt": ("Debt ratio", "Total liabilities / total assets"),
    "gross_margin": ("Gross margin", "(Revenue - cost of goods) / revenue"),
    "net_margin": ("Net margin", "Net income / revenue"),
    "roa": ("Return on assets", "Net income / average assets"),
    "roe": ("Return on equity", "Net income / average equity"),
    "turnover": ("Asset turnover", "Revenue / average assets"),
    "interest_coverage": ("Interest coverage", "EBIT / interest expense"),
}


def render_run_markdown(result: dict[str, Any]) -> tuple[str, str, str]:
    """Format stored numbers without rerunning calculations or translating source data."""
    run_id = result["run_id"]
    note = "Synthetic demonstration data." if result["synthetic"] else "Data reviewed by the user."
    advice = ("Compare ratios with the relevant industry and prior periods. Review receivables, debt maturities "
              "and cash reserves. This report is not an asset-allocation recommendation or a claim of legal compliance.")
    rows = []
    for ratio in result["ratios"]:
        name, formula = RATIO_LABELS[ratio["key"]]
        value = ratio["value"] if ratio["value"] is not None else "Undefined (nonpositive denominator)"
        rows.append(f"|{name}|{value}|{formula}|")
    forecast = result["forecast"]
    predictions = forecast["predictions"]
    warning = ("Intervals use empirical historical errors; coverage is not guaranteed. Inflation, shocks and "
               "Ramadan are not modeled separately." if predictions else
               "Forecast withheld: the available series is too short or constant.")
    stationary = forecast["diagnostics"]["is_stationary"]
    diagnostic = ("The unit-root null was rejected." if stationary is True else
                  "The unit-root null was not rejected; baseline changes are reported with uncertainty."
                  if stationary is False else "ADF is not interpreted because the series is too short or constant.")
    forecast_table = "\n".join(f"|{p['month']}|{p['estimate']:.0f}|{p['lower']:.0f}|{p['upper']:.0f}|"
                               for p in predictions)
    benchmark_table = "No evidence-backed rates were supplied; no comparison was calculated."
    if result["benchmarks"]:
        benchmark_rows = []
        for benchmark in result["benchmarks"]:
            label = "US dollar" if benchmark["asset"] == "USD" else "18-karat gold (gram)"
            benchmark_rows.append(f"|{label}|{benchmark['start_date']}|{benchmark['end_date']}|"
                f"{benchmark['amount_irr']}|{benchmark['ending_value_irr']}|{benchmark['nominal_return']}|")
        benchmark_table = ("|Asset|Start|End|Initial IRR|Hypothetical ending IRR|Nominal return (fraction)|\n"
            "|---|---|---|---|---|---|\n" + "\n".join(benchmark_rows) +
            "\n\nHypothetical comparison excluding fees, taxes and inflation adjustment; not a purchase recommendation.")
    text = (f"# Financial report: {result['business_name']}\n\nRun ID: `{run_id}`\n\n{note}\n\n"
        f"Input SHA-256: `{result['input_sha256']}`\n\nCurrency: IRR. Ratios are fractions.\n\n"
        "|Ratio|Value|Formula|\n|---|---|---|\n" + "\n".join(rows) +
        f"\n\n## Uncertainty\n\n{warning}\n\n{diagnostic}\n\n"
        f"Nominal interval coverage: {forecast['coverage']:.0%}\n\n"
        f"|Month|Estimate|Lower bound|Upper bound|\n|---|---|---|---|\n{forecast_table}\n\n"
        f"## Dollar and gold comparison\n\n{benchmark_table}\n\n## Review notes\n\n{advice}\n\n"
        "Forecast details, input provenance and comparison rates are preserved in this run's manifest.json.\n")
    chapter = (f"# Research chapter — {run_id}\n\n" + text +
        "\n## Method\n\nDecimal calculations use a reviewed financial statement. The baseline forecast follows "
        "ADF and lag-12 screening; intervals bootstrap historical errors. No independent real-business evaluation "
        "has been performed. Evidence is archived under its SHA-256 filename in the corresponding run.\n")
    narrative = (f"# Business-owner summary\n\nRun ID: `{run_id}`\n\n{note}\n\n{advice}\n\n{warning}\n\n"
        "This report does not replace an accountant's judgment. See this run's technical report for ratios and "
        "forecast bounds.\n")
    return text, chapter, narrative
