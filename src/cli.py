from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.ingestion.ocr_persian import PersianFinancialExtractor
from src.ledger.double_entry import JevLedger
from src.ledger.jev import Decision, JevEntry
from src.pipeline import create_demo, run_analysis


def main() -> None:
    parser = argparse.ArgumentParser(description="مشاور مالی محلی؛ پیشنهاد، بررسی و ثبت با شواهد")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="اجرای نمونه ساختگی")
    demo.add_argument("--output", type=Path, default=Path("."))
    ingest = sub.add_parser("ingest", help="استخراج برای بررسی، بدون ثبت دفتر")
    ingest.add_argument("file")
    ingest.add_argument("--engine", choices=["tesseract", "easyocr"], default="tesseract")
    ingest.add_argument("--output", type=Path, required=True)
    for command in ("propose", "decide"):
        command_parser = sub.add_parser(command, help="پیشنهاد سند" if command == "propose" else "تصمیم انسانی")
        command_parser.add_argument("file", type=Path)
        command_parser.add_argument("--book", required=True)
    trace = sub.add_parser("trace", help="نمایش زنجیره شواهد")
    trace.add_argument("id")
    trace.add_argument("--book", required=True)
    run = sub.add_parser("run", help="تحلیل داده بررسی‌شده")
    run.add_argument("file", type=Path)
    run.add_argument("--output", type=Path, default=Path("."))
    advice = sub.add_parser("advise", help="پیش‌نویس توضیح با مدل محلی Ollama")
    advice.add_argument("file", type=Path, help="فایل RunInput بررسی‌شده")
    advice.add_argument("--model", default="mshojaei77/gemma3persian")
    args = parser.parse_args()
    try:
        if args.command == "demo":
            print(run_analysis(create_demo(args.output / "samples"), args.output))
        elif args.command == "ingest":
            extracted = PersianFinancialExtractor(args.engine).extract(args.file)
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(extracted.model_dump_json(indent=2))
            print("استخراج ذخیره شد؛ پیش از ثبت، متن و مقدارها را بررسی کنید")
        elif args.command == "propose":
            print(JevLedger(args.book).add_entry(JevEntry.model_validate_json(args.file.read_bytes())))
        elif args.command == "decide":
            JevLedger(args.book).decide(Decision.model_validate_json(args.file.read_bytes()))
            print("تصمیم انسانی ثبت شد")
        elif args.command == "trace":
            print(json.dumps(JevLedger(args.book).trace(args.id), ensure_ascii=False, indent=2))
        elif args.command == "advise":
            from src.ai_agent.agent import AgentConfig, FinancialAgent
            from src.ai_agent.tools import calculated_context
            from src.pipeline import RunInput, all_evidence
            data = RunInput.model_validate_json(args.file.read_bytes())
            for evidence in all_evidence(data):
                evidence.verify()
            print(json.dumps(FinancialAgent(AgentConfig(model=args.model)).advise(
                calculated_context(data.statement)), ensure_ascii=False, indent=2))
        else:
            print(run_analysis(args.file, args.output))
    except (ValueError, OSError, ImportError, KeyError) as exc:
        parser.exit(2, f"خطا در پردازش؛ ورودی یا وابستگی‌ها را بررسی کنید: {exc}\n")


if __name__ == "__main__":
    main()
