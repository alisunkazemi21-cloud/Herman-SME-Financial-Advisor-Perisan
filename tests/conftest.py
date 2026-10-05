from datetime import date

import pytest

from src.ledger.jev import JevEntry
from src.models import Evidence
from src.pipeline import RunInput, create_demo


@pytest.fixture
def evidence(tmp_path):
    path = tmp_path / "invoice.txt"
    path.write_text("فاکتور نمونه\nجمع کل ۱۰۰۰\n۱۴۰۵/۰۱/۰۱", encoding="utf-8")
    return Evidence.from_file(path, "خط ۲")


@pytest.fixture
def entry(evidence):
    return JevEntry(jev_id="J1", entry_date=date(2026, 3, 21), jalali_date="1405/01/01",
                    description_fa="فروش نمونه", debit_account="1000", credit_account="4000",
                    amount="1000", evidence=evidence, actor="agent:analyst")


@pytest.fixture
def demo(tmp_path):
    return RunInput.model_validate_json(create_demo(tmp_path / "samples").read_bytes())
