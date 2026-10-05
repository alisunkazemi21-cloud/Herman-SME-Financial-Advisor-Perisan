from __future__ import annotations

import math
from typing import Any

import numpy as np
from pydantic import Field, field_validator

from src.ingestion.normalizer import normalize_persian_digits, parse_jalali
from src.models import Fact, Model


class MonthlyCashFlow(Model):
    month: str = Field(pattern=r"^\d{4}/\d{2}$")
    net: Fact

    @field_validator("month")
    @classmethod
    def valid_month(cls, value: str) -> str:
        normalized = normalize_persian_digits(value)
        parse_jalali(normalized + "/01")
        return normalized


def analyze_cashflow_stationarity(monthly_cashflows: list[float]) -> dict[str, Any]:
    from statsmodels.tsa.stattools import adfuller
    x = np.asarray(monthly_cashflows, dtype=float)
    if not np.isfinite(x).all():
        raise ValueError("سری زمانی شامل عدد نامتناهی است")
    if len(x) < 24 or np.ptp(x) == 0:
        return {"adf_statistic": None, "p_value": None, "is_stationary": None,
                "seasonal_lag12_correlation": None, "critical_values": {},
                "recommendation_fa": "داده برای تفسیر ADF کافی نیست یا سری ثابت است"}
    result = adfuller(x, autolag="AIC")
    seasonal = float(np.corrcoef(x[:-12], x[12:])[0, 1]) if (
        np.std(x[:-12]) > 0 and np.std(x[12:]) > 0) else None
    return {"adf_statistic": float(result[0]), "p_value": float(result[1]),
            "is_stationary": bool(result[1] < 0.05), "critical_values": result[4],
            "seasonal_lag12_correlation": seasonal,
            "recommendation_fa": "فرض ریشه واحد رد شد" if result[1] < 0.05 else
            "فرض ریشه واحد رد نشد؛ مدل پایه روی تغییرات و با عدم قطعیت گزارش می‌شود"}


def forecast_cashflow(rows: list[MonthlyCashFlow], horizon: int = 3,
                      coverage: float = 0.85, seed: int = 42) -> dict[str, Any]:
    if not 1 <= horizon <= 12 or not 0.5 <= coverage < 1:
        raise ValueError("افق یا سطح بازه نامعتبر است")
    indices = [int(row.month[:4]) * 12 + int(row.month[5:]) - 1 for row in rows]
    if any(b != a + 1 for a, b in zip(indices, indices[1:])):
        raise ValueError("ماه‌ها باید مرتب، پیوسته و بدون تکرار باشند")
    x = np.array([float(row.net.value) for row in rows])
    diagnostic = analyze_cashflow_stationarity(x.tolist())
    base = {"diagnostics": diagnostic, "coverage": coverage, "seed": seed,
            "input_evidence": [r.net.evidence.model_dump() for r in rows]}
    if len(x) < 24 or np.ptp(x) == 0:
        return {**base, "predictions": [], "warning_fa": "پیش‌بینی متوقف شد: داده کوتاه یا ثابت"}
    correlation = diagnostic["seasonal_lag12_correlation"]
    seasonal = correlation is not None and correlation > 0.6 and len(x) >= 36
    lag = 12 if seasonal else 1
    residuals = x[lag:] - x[:-lag]
    # Historical rolling one-step errors; horizon scaling is a random-walk approximation.
    residuals = residuals - np.mean(residuals)
    rng = np.random.default_rng(seed)
    predictions: list[dict[str, Any]] = []
    alpha = (1 - coverage) / 2
    for step in range(1, horizon + 1):
        center = float(x[-12 + step - 1] if seasonal else x[-1])
        sampled = rng.choice(residuals, size=4000) * math.sqrt(step)
        lower, upper = np.quantile(center + sampled, [alpha, 1 - alpha])
        year, month = divmod(indices[-1] + step, 12)
        predictions.append({"month": f"{year:04d}/{month + 1:02d}", "estimate": center,
                            "lower": float(lower), "upper": float(upper)})
    return {**base, "method": "seasonal_naive" if seasonal else "random_walk",
            "predictions": predictions, "warning_fa":
            "بازه تجربی خطاهای تاریخی است؛ پوشش تضمین نشده. تورم، شوک و رمضان جدا مدل نشده‌اند"}
