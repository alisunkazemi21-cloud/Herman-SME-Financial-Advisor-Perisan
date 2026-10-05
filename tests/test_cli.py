import json
import sys

import pytest

from src.cli import main
from src.pipeline import create_demo


def test_cli_ingest_preserves_existing_output(tmp_path, monkeypatch):
    source = tmp_path / "input.csv"
    source.write_text("مبلغ\n۱۰۰۰\n", encoding="utf-8")
    output = tmp_path / "output.json"
    monkeypatch.setattr(sys, "argv", ["advisor", "ingest", str(source), "--output", str(output)])
    main()
    before = output.read_bytes()
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2 and output.read_bytes() == before


def test_cli_proposal_decision_trace(tmp_path, entry, monkeypatch, capsys):
    book = tmp_path / "book.jsonl"
    proposal = tmp_path / "proposal.json"
    proposal.write_text(entry.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["advisor", "propose", str(proposal), "--book", str(book)])
    main()
    decision = tmp_path / "decision.json"
    decision.write_text(json.dumps({"jev_id": "J1", "actor": "human:owner", "approved": True,
                                   "reviewed_values": True, "reason_fa": "بازبینی کامل شد"}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["advisor", "decide", str(decision), "--book", str(book)])
    main()
    monkeypatch.setattr(sys, "argv", ["advisor", "trace", "J1", "--book", str(book)])
    main()
    assert "تأییدشده" in capsys.readouterr().out


def test_cli_uses_typed_context_for_advice(tmp_path, monkeypatch, capsys):
    path = create_demo(tmp_path)
    from src.ai_agent.agent import FinancialAgent
    def advise(self, context):
        assert len(context["ratios"]) == 10
        return {"text_fa": "آزمون پیش‌نویس"}
    monkeypatch.setattr(FinancialAgent, "advise", advise)
    monkeypatch.setattr(sys, "argv", ["advisor", "advise", str(path)])
    main()
    assert "پیش‌نویس" in capsys.readouterr().out
