import json
import os
from pathlib import Path

import pytest

from src.ingestion.ocr_persian import PersianFinancialExtractor
from src.pipeline import create_demo, run_analysis


def test_full_synthetic_run_synchronizes_artifacts(tmp_path):
    path = create_demo(tmp_path / "samples")
    manifest = run_analysis(path, tmp_path)
    result = json.loads(manifest.read_text(encoding="utf-8"))
    assert result["synthetic"] and len(result["ratios"]) == 10
    assert result["forecast"]["predictions"]
    report = (manifest.parent / "README.md").read_text(encoding="utf-8")
    assert "# Financial report:" in report and "Current ratio" in report
    assert result["business_name"] in report
    assert result["ratios"][0]["name_fa"] == "نسبت جاری"
    assert "داده ساختگی" in result["note_fa"]
    assert result["run_id"] in (manifest.parent.parent / "README.md").read_text(encoding="utf-8")
    assert result["run_id"] in (tmp_path / "reports" / (result["run_id"][:10] +
                                "_technical_fa.md")).read_text(encoding="utf-8")
    assert list((tmp_path / "reports").glob("*.md"))
    assert list((tmp_path / "research" / "CHAPTERS").glob("*.md"))
    assert result["run_id"] in (tmp_path / "media" / "narrative_fa.md").read_text(encoding="utf-8")
    assert json.loads((tmp_path / "runs" / "latest.json").read_text())["run_id"] == result["run_id"]
    assert "\\" not in json.loads((tmp_path / "runs" / "latest.json").read_text())["manifest"]
    second = run_analysis(path, tmp_path)
    assert second != manifest and manifest.exists()


def test_benchmarks_in_report_and_manifest(tmp_path):
    path = create_demo(tmp_path / "samples")
    data = json.loads(path.read_text(encoding="utf-8"))
    fact = data["statement"]["current_assets"]
    data["benchmarks"] = [{"amount_irr": fact,
        "start": {"day": "2025-01-01", "asset": "USD", "irr_per_unit": fact},
        "end": {"day": "2026-01-01", "asset": "USD", "irr_per_unit": fact}}]
    path.write_text(json.dumps(data), encoding="utf-8")
    manifest = run_analysis(path, tmp_path)
    report = (manifest.parent / "README.md").read_text(encoding="utf-8")
    assert "US dollar" in report
    assert json.loads(manifest.read_text(encoding="utf-8"))["benchmarks"][0]["nominal_return"] == "0"


@pytest.mark.integration
def test_real_ocr_three_labelled_invoices():
    location = os.environ.get("PFA_OCR_FIXTURES")
    if not location:
        pytest.skip("Three labeled invoices and an installed OCR engine were not supplied")
    cases = json.loads((Path(location) / "cases.json").read_text(encoding="utf-8"))
    assert len(cases) >= 3
    for case in cases:
        result = PersianFinancialExtractor().extract(str(Path(location) / case["image"]))
        assert result.confidence > 0.7
        for expected in case["expected_fragments"]:
            assert expected in result.normalized_text
