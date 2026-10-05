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
    assert (manifest.parent / "README.md").exists()
    assert list((tmp_path / "reports").glob("*.md"))
    assert list((tmp_path / "research" / "CHAPTERS").glob("*.md"))
    assert result["run_id"] in (tmp_path / "media" / "narrative_fa.md").read_text(encoding="utf-8")
    assert json.loads((tmp_path / "runs" / "latest.json").read_text())["run_id"] == result["run_id"]
    second = run_analysis(path, tmp_path)
    assert second != manifest and manifest.exists()


@pytest.mark.integration
def test_real_ocr_three_labelled_invoices():
    location = os.environ.get("PFA_OCR_FIXTURES")
    if not location:
        pytest.skip("سه فاکتور برچسب‌دار و موتور OCR نصب‌شده ارائه نشده است")
    cases = json.loads((Path(location) / "cases.json").read_text(encoding="utf-8"))
    assert len(cases) >= 3
    for case in cases:
        result = PersianFinancialExtractor().extract(str(Path(location) / case["image"]))
        assert result.confidence > 0.7
        for expected in case["expected_fragments"]:
            assert expected in result.normalized_text
