from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from src.analytics.benchmarks import BenchmarkRequest, compare
from src.analytics.forecast import MonthlyCashFlow, forecast_cashflow
from src.analytics.ratios import FinancialStatement, compute_ratios
from src.models import Evidence, Fact, Model


class RunInput(Model):
    business_name: str = Field(min_length=1)
    synthetic: bool = False
    reviewed_by: str = Field(pattern=r"^human:\S+$")
    reviewed_values: Literal[True]
    statement: FinancialStatement
    monthly_cashflows: list[MonthlyCashFlow] = Field(default_factory=list)
    benchmarks: list[BenchmarkRequest] = Field(default_factory=list)


def all_evidence(value: Any) -> list[Evidence]:
    found: list[Evidence] = []
    if isinstance(value, Evidence):
        return [value]
    if isinstance(value, Model):
        for name in type(value).model_fields:
            found.extend(all_evidence(getattr(value, name)))
    elif isinstance(value, list):
        for item in value:
            found.extend(all_evidence(item))
    return found


def run_analysis(input_path: Path, output_root: Path) -> Path:
    raw = input_path.read_bytes()
    data = RunInput.model_validate_json(raw)
    for evidence in all_evidence(data):
        evidence.verify()
    ratios = compute_ratios(data.statement)
    forecast = forecast_cashflow(data.monthly_cashflows)
    now = datetime.now(timezone(timedelta(hours=3, minutes=30)))
    run_id = now.strftime("%Y-%m-%d") + "/" + now.strftime("%H%M%S") + "-" + uuid.uuid4().hex[:8]
    directory = output_root / "runs" / run_id
    directory.mkdir(parents=True, exist_ok=False)
    evidence_directory = directory / "evidence"
    evidence_directory.mkdir()
    for evidence in all_evidence(data):
        content = Path(evidence.source_file).read_bytes()
        if hashlib.sha256(content).hexdigest() != evidence.sha256:
            raise ValueError("شاهد حین اجرا تغییر کرد")
        target = evidence_directory / evidence.sha256
        if not target.exists():
            target.write_bytes(content)
    (directory / "input.json").write_bytes(raw)
    result = {"run_id": run_id, "created_at": now.isoformat(), "business_name": data.business_name,
              "synthetic": data.synthetic, "input_sha256": hashlib.sha256(raw).hexdigest(),
              "reviewed_by": data.reviewed_by, "currency": "IRR",
              "period": [str(data.statement.period_start), str(data.statement.period_end)],
              "ratios": [r.model_dump(mode="json") for r in ratios], "forecast": forecast,
              "monthly_cashflows": [r.model_dump(mode="json") for r in data.monthly_cashflows],
              "benchmarks": [compare(b) for b in data.benchmarks],
              "note_fa": "داده ساختگی برای نمایش" if data.synthetic else "داده بررسی‌شده توسط کاربر",
              "advice_fa": "نسبت‌ها باید با صنعت و دوره قبل مقایسه شوند. مطالبات، سررسید بدهی‌ها و ذخیره نقد را بررسی کنید."
              " این گزارش پیشنهاد تخصیص سرمایه یا ادعای انطباق قانونی ندارد."}
    manifest = directory / "manifest.json"
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    table = "\n".join(f"|{r.name_fa}|{r.value if r.value is not None else 'تعریف‌نشده'}|{r.formula_fa}|"
                      for r in ratios)
    forecast_table = "\n".join(f"|{p['month']}|{p['estimate']:.0f}|{p['lower']:.0f}|{p['upper']:.0f}|"
                               for p in forecast["predictions"])
    text = (f"# گزارش مالی {data.business_name}\n\nشناسه اجرا: `{run_id}`\n\n{result['note_fa']}\n\n"
            f"هش ورودی: `{result['input_sha256']}`\n\nواحد: ریال؛ مقادیر نسبت‌ها کسر هستند.\n\n"
            f"|نسبت|مقدار|فرمول|\n|---|---|---|\n{table}\n\n"
            f"## عدم قطعیت\n\n{forecast.get('warning_fa', '')}\n\n"
            f"{forecast['diagnostics']['recommendation_fa']}\n\n"
            f"سطح اسمی بازه: {forecast['coverage']:.0%}\n\n"
            f"|ماه|برآورد|کران پایین|کران بالا|\n|---|---|---|---|\n{forecast_table}\n\n"
            f"## پیشنهاد بررسی\n\n{result['advice_fa']}\n\n"
            "جزئیات پیش‌بینی، منشأ هر مقدار و نرخ‌های مقایسه در manifest.json همین اجرا موجود است.\n")
    (directory / "README.md").write_text(text, encoding="utf-8")
    slug = run_id.replace("/", "_")
    chapter = (f"# فصل پژوهش — {run_id}\n\n" + text +
               "\n## روش\n\nمحاسبات Decimal از صورت مالی بررسی‌شده؛ پیش‌بینی پایه با آزمون ADF و غربال وقفه ۱۲. "
               "بازه‌ها از خطاهای تاریخی bootstrap می‌شوند؛ ارزیابی مستقل روی کسب‌وکار واقعی انجام نشده است. "
               "شاهد هر ورودی در بایگانی اجرای مربوط با نام SHA256 نگه داشته شده است.\n")
    narrative = (f"# خلاصه برای صاحب کسب‌وکار\n\nشناسه اجرا: `{run_id}`\n\n{result['note_fa']}\n\n"
                 f"{result['advice_fa']}\n\n{forecast.get('warning_fa', '')}\n\n"
                 "این گزارش جای تصمیم حسابدار را نمی‌گیرد. جدول نسبت‌ها و حدود پیش‌بینی را در گزارش فنی همین اجرا ببینید.\n")
    for relative, content in ((f"research/CHAPTERS/{slug}.md", chapter),
                               (f"reports/{slug}_technical_fa.md", text), (f"media/{slug}_fa.md", narrative)):
        target = output_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    # Publish the common pointer last: dashboard never sees an incomplete run.
    pointer = output_root / "runs" / "latest.json"
    temp = pointer.with_name(f"latest-{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps({"manifest": manifest.relative_to(output_root).as_posix(), "run_id": run_id}),
                    encoding="utf-8")
    os.replace(temp, pointer)
    (output_root / "media" / "narrative_fa.md").write_text(narrative, encoding="utf-8")
    return manifest


def create_demo(root: Path) -> Path:
    """Explicit synthetic evidence, no real rates or automatically approved journal entries."""
    root.mkdir(parents=True, exist_ok=True)
    source = root / "synthetic_source.json"
    values = {"current_assets": 200_000_000, "inventory": 50_000_000, "prepayments": 10_000_000,
              "current_liabilities": 100_000_000, "total_assets": 500_000_000,
              "total_liabilities": 200_000_000, "equity": 300_000_000, "opening_assets": 400_000_000,
              "opening_equity": 250_000_000, "revenue": 600_000_000, "cost_of_goods": 360_000_000,
              "net_income": 60_000_000, "ebit": 90_000_000, "interest_expense": 10_000_000}
    flows = [12_000_000 + (i % 12) * 420_000 + ((i * 17) % 7 - 3) * 800_000 for i in range(36)]
    source.write_text(json.dumps({"synthetic": True, "values": values, "flows": flows},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    def fact(value: int, locator: str) -> Fact:
        return Fact(value=value, evidence=Evidence.from_file(source, locator))
    statement = FinancialStatement(period_start="2025-03-21", period_end="2026-03-20",
                                   **{name: fact(value, "values." + name) for name, value in values.items()})
    rows = [MonthlyCashFlow(month=f"{1402 + i // 12}/{i % 12 + 1:02d}", net=fact(value, f"flows[{i}]"))
            for i, value in enumerate(flows)]
    data = RunInput(business_name="کافه نمونه — داده ساختگی", synthetic=True,
                    reviewed_by="human:demo", reviewed_values=True, statement=statement, monthly_cashflows=rows)
    path = root / "demo_input.json"
    path.write_text(data.model_dump_json(indent=2), encoding="utf-8")
    return path
