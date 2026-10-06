---
title: Persian Financial Advisor for Iranian SMEs — Codex Prompt
version: 1.0
language: fa-IR
direction: rtl
token_reduction: true
token_reduction_profile: aggressive
tags:
  - token-reduction
  - skill:financial-advisor
  - skill:persian-ocr
  - skill:double-entry-ledger
  - skill:local-llm
  - skill:marimo-dashboard
  - skill:jalali-calendar
  - skill:iranian-accounting-standards
skills:
  - financial-analysis
  - persian-ocr
  - double-entry-ledger
  - local-ai-agent
  - marimo-dashboard
  - jalali-calendar
  - iranian-accounting-standards
  - cashflow-forecasting
  - dollar-gold-benchmarking
---

## Current project instructions (updated 2026-10-06)

- Write all repository documentation, research, decisions, checkpoint notes, technical reports, media narratives, code comments and developer-facing text in clear English.
- Keep app-facing text, RTL presentation, Persian input/output data, fixtures, source documents and evidence in Persian where applicable. Persian literals in the code examples below are app/data examples, not a documentation-language requirement.
- At every checkpoint, update the English documentation along with the implementation and validation evidence. Generated Markdown reports must also use English prose while preserving business names and source data verbatim.
- Backend development is the current priority. Interface work is deferred at the user's request.
- These later user preferences supersede the original prompt's broader Persian-language requirement. The original technical brief follows for reference.

# @token-reduction: ON
# @skill: financial-advisor
# @skill: persian-ocr
# @skill: double-entry-ledger
# @skill: local-llm
# @skill: marimo-dashboard
# @skill: jalali-calendar
# @skill: iranian-accounting-standards

/project "مشاور مالی هوشمند کسب‌وکارهای کوچک و متوسط ایرانی"

### 1. Review Repository Evidence & Relevant Literature

Before writing any code, review the current repository state, then research and document the following in `research/LITERATURE.md`:

**Persian financial accounting standards:**
The original brief describes Iranian national accounting standards as largely converged with IFRS/IAS. It requests research into Standard 43 (revenue from contracts with customers), Standard 39 (consolidated financial statements), Standard 16 (foreign exchange), and SME accounts including goodwill, receivables, notes payable and provisions. Verify official versions before claiming compliance; the research log records unresolved source access.

**Financial ratios in Persian:**
Provide Persian app labels for current ratio, quick ratio, equity ratio, debt ratio, gross margin, net margin, return on assets, return on equity, asset turnover and interest coverage. Explain their contracts in English documentation.

**Persian OCR & document extraction:**
Existing solutions include: `faniuta/ocr` (EasyOCR + Tesseract for Persian, FastAPI wrapper), Aspose.OCR Cloud SDK (supports Persian among 45+ languages), and DocFlow Invoice Parser FA (EasyOCR fa/en + ParsBERT NER + Pydantic business rules, achieving macro F1 of 0.93 on Persian invoices).

**Local AI agent frameworks:**
Relevant open-source projects include: `wealthbraid` (local-first, append-only double-entry ledger with AI agents, every number traceable to evidence), `merendamattia/personal-financial-ai-agent` (multi-LLM support including Ollama for local inference), and Persian-first AI finance assistants with RTL support.

**Financial calculation libraries:**
`my727finance` provides financial ratio analysis, cash flow analysis, working capital, DuPont analysis, and Altman Z-Score with NumPy-first API. `pyxirr` provides Rust-powered XIRR and day-count conventions for cash flow analysis.

**Marimo notebook:**
Marimo is a reactive Python notebook that saves as `.py` files (not JSON), making it Git-friendly. It functions as both a coding environment and an interactive dashboard, ideal for Persian financial analysis with sliders, tables, and charts. Codex can edit marimo notebooks with the `--watch` flag for live updates.

---

### 2. Discuss Scientific Choices & Unresolved Risks

Create `research/DECISIONS.md` and record the following before implementation:

**Decision 1: OCR engine choice.**
- Option A: Tesseract + EasyOCR (open-source, offline, free, requires `tesseract-ocr-fas`).
- Option B: Aspose.OCR Cloud (higher accuracy for Persian, paid API).
- Option C: DocFlow pipeline (EasyOCR + ParsBERT NER + Pydantic validation, highest F1 for invoices).
- **Risk:** Persian handwritten documents and mixed Persian/Latin digits, Solar Hijri date parsing, and low-quality scans remain challenging.

**Decision 2: Ledger architecture.**
- Option A: Append-only JSON Lines with double-entry (wealthbraid-style, fully traceable, human-in-the-loop approval).
- Option B: SQLite ledger with typed Python calculators (Finance-Guru style, faster queries).
- **Risk:** SMEs may not have accounting training; the system must generate human-readable explanations for every entry.

**Decision 3: Local LLM selection.**
- Option A: Ollama with a Persian-capable model (e.g., `gemma-3-4b-persian-v0` or `nexus-finance`).
- Option B: Multi-provider (Ollama local + Gemini/OpenAI cloud fallback).
- **Risk:** Local LLM quality on Persian financial reasoning may be insufficient; cloud APIs may be blocked or costly in Iran.

**Decision 4: Financial ratio computation.**
- Compute ratios using typed Python functions (not LLM arithmetic) to guarantee correctness. Use `my727finance` or write custom NumPy/pandas functions with full test coverage.

---

### 3. Record Decisions & Alternatives

Create `research/WORKFLOW.md` with the exact stage sequence you provided:

```
Each stage follows the same evidence-preserving sequence:

1. Review repository evidence and relevant literature.
2. Discuss scientific choices and unresolved risks.
3. Record the decision and its alternatives before execution.
4. Implement traceable inputs and validation checks.
5. Run short checkpoints before long production.
6. Analyze stationarity and uncertainty before interpretation.
7. Synchronize the run README, Marimo notebook, research-book chapter,
   technical report, and media narrative.
```

Every decision must be recorded with its alternatives and rationale before any code is written.

---

### 4. Implement Traceable Inputs & Validation Checks

**Project structure:**

```
persian-financial-advisor/
├── AGENTS.md                    # This prompt for Codex
├── research/
│   ├── LITERATURE.md
│   ├── DECISIONS.md
│   ├── WORKFLOW.md
│   └── CHAPTERS/               # Research-book chapters
├── src/
│   ├── ingestion/
│   │   ├── ocr_persian.py      # Tesseract/EasyOCR/DocFlow wrapper
│   │   ├── excel_parser.py     # openpyxl/pandas for Excel
│   │   ├── pdf_parser.py       # pdfplumber + OCR fallback
│   │   └── normalizer.py       # Persian digit normalization, Jalali dates
│   ├── ledger/
│   │   ├── double_entry.py     # Append-only ledger, every entry traceable
│   │   ├── jev.py              # "Jev" document structuring
│   │   └── reconciliation.py   # Bank reconciliation
│   ├── analytics/
│   │   ├── ratios.py           # All Persian financial ratios
│   │   ├── cashflow.py         # Cash flow analysis, XIRR
│   │   ├── forecast.py         # Prediction models
│   │   └── benchmarks.py       # Dollar/gold comparison
│   ├── ai_agent/
│   │   ├── agent.py            # Local AI agent (Ollama + LangChain)
│   │   ├── prompts_fa.py       # Persian prompt templates
│   │   └── tools.py            # Tool definitions for agent
│   └── dashboard/
│       └── notebook.py         # Marimo dashboard (RTL, Persian)
├── tests/
│   ├── test_ocr.py
│   ├── test_ratios.py
│   ├── test_ledger.py
│   └── test_agent.py
├── pyproject.toml
└── README.md
```

**Persian ingestion module requirements:**

```python
# src/ingestion/ocr_persian.py

from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional
import easyocr
import pytesseract
from pdfplumber import open as pdf_open

class DocumentType(str, Enum):
    INVOICE = "فاکتور"
    BALANCE_SHEET = "ترازنامه"
    INCOME_STATEMENT = "صورت سود و زیان"
    CASH_FLOW = "صورت جریان وجوه نقد"
    BANK_STATEMENT = "صورت حساب بانکی"
    PAYROLL = "لیست حقوق"
    TAX_FORM = "اظهارنامه مالیاتی"
    UNKNOWN = "نامشخص"

class ExtractedDocument(BaseModel):
    doc_type: DocumentType
    raw_text_fa: str
    structured_data: dict
    confidence: float = Field(ge=0.0, le=1.0)
    source_file: str
    extraction_method: str  # "tesseract", "easyocr", "docflow", "excel", "pdf_text"
    jalali_date: Optional[str] = None
    persian_digits_normalized: bool = False

class PersianFinancialExtractor:
    """
    Extracts financial data from Persian documents.
    Handles: Excel, Google Sheets, PDF (text + scanned), images.
    All extracted data is stored with full provenance.
    """

    def __init__(self, ocr_engine: str = "easyocr"):
        self.reader = easyocr.Reader(['fa', 'en'])
        self.ocr_engine = ocr_engine

    def normalize_persian_digits(self, text: str) -> str:
        """Convert Persian/Arabic digits to Latin, normalize ی/ي, ک/ك."""
        persian_digits = "۰۱۲۳۴۵۶۷۸۹"
        arabic_digits = "٠١٢٣٤٥٦٧٨٩"
        latin_digits = "0123456789"
        for fa, la in zip(persian_digits, latin_digits):
            text = text.replace(fa, la)
        for ar, la in zip(arabic_digits, latin_digits):
            text = text.replace(ar, la)
        return text

    def extract_from_excel(self, filepath: str) -> ExtractedDocument:
        """Extract from Excel / Google Sheets export (.xlsx, .csv)."""
        import pandas as pd
        df = pd.read_excel(filepath, engine="openpyxl")
        # Detect column headers in Persian, map to standard fields
        ...

    def extract_from_pdf(self, filepath: str) -> ExtractedDocument:
        """Try text extraction first, fall back to OCR for scanned PDFs."""
        ...

    def extract_from_image(self, filepath: str) -> ExtractedDocument:
        """OCR for scanned images."""
        ...
```

**Ledger with "Jev" structuring:**

```python
# src/ledger/jev.py

from datetime import date
from decimal import Decimal
from pydantic import BaseModel
from typing import Optional

class JevEntry(BaseModel):
    """A single Jev (journal entry voucher) record.
    Every financial event is recorded as a balanced double-entry.
    """
    jev_id: str
    entry_date: date  # Jalali date stored separately
    jalali_date: str
    description_fa: str
    debit_account: str
    credit_account: str
    amount: Decimal  # Never float — exact decimal arithmetic
    evidence_ref: str  # Links to original document
    actor: str  # "human:owner" or "agent:analyst"
    approved: bool = False

class JevLedger:
    """Append-only ledger. Corrections are new entries, never overwrites.
    Every entry can be traced back to its source evidence.
    """
    def __init__(self, book_path: str):
        self.book_path = book_path

    def add_entry(self, entry: JevEntry) -> str:
        """Append to JSONL ledger. Returns entry ID."""
        ...

    def trace(self, entry_id: str) -> dict:
        """Full provenance: evidence → journal → proposal → decision."""
        ...
```

---

### 5. Run Short Checkpoints Before Long Production

Before running the full pipeline on real documents, run checkpoint tests:

```python
# tests/test_checkpoints.py

def test_ocr_on_sample_invoice():
    """Checkpoint: Persian invoice OCR accuracy on 3 sample docs."""
    extractor = PersianFinancialExtractor()
    result = extractor.extract_from_image("samples/invoice_sample.jpg")
    assert result.doc_type == DocumentType.INVOICE
    assert result.confidence > 0.7
    assert "مبلغ کل" in result.raw_text_fa or "جمع کل" in result.raw_text_fa

def test_jev_balance():
    """Checkpoint: Every Jev entry must balance (debit == credit)."""
    ledger = JevLedger("test_book.jsonl")
    entry = JevEntry(...)
    assert entry.amount > 0

def test_ratio_computation():
    """Checkpoint: Current ratio from known inputs."""
    from src.analytics.ratios import current_ratio_fa
    assert current_ratio_fa(current_assets=200_000_000, current_liabilities=100_000_000) == 2.0
```

Run with: `uv run pytest tests/ -v --tb=short`

Only after all checkpoints pass, proceed to full document processing.

---

### 6. Analyze Stationarity & Uncertainty Before Interpretation

Before generating any financial advice, the system must:

1. **Detect seasonality** in cash flow data (e.g., restaurants have Ramadan/Norooz patterns).
2. **Flag uncertainty** in OCR-extracted values (confidence < 0.8 → require human review).
3. **Test for stationarity** in time series before forecasting (ADF test on monthly cash flows).
4. **Report confidence intervals** on all predictions, never point estimates alone.

```python
# src/analytics/forecast.py

import numpy as np
from statsmodels.tsa.stattools import adfuller
from statsmodels.tsa.holtwinters import ExponentialSmoothing

def analyze_cashflow_stationarity(monthly_cashflows: list[float]) -> dict:
    """ADF test + seasonality detection on Persian business cash flows."""
    result = adfuller(monthly_cashflows)
    return {
        "adf_statistic": result[0],
        "p_value": result[1],
        "is_stationary": result[1] < 0.05,
        "critical_values": result[4],
        "recommendation_fa": "سری زمانی پایدار است" if result[1] < 0.05
                             else "سری زمانی ناپایدار است — نیاز به تفاضل‌گیری"
    }
```

---

### 7. Synchronize All Outputs

After every run, synchronize these five outputs:

| Artifact | Path | Content |
|---|---|---|
| **Run README** | `runs/YYYY-MM-DD/README.md` | Summary of what was processed, decisions made, results |
| **Marimo Notebook** | `src/dashboard/notebook.py` | Interactive Persian dashboard with charts, ratios, forecasts |
| **Research Book** | `research/CHAPTERS/` | Chapter explaining methodology, evidence, and findings |
| **Technical Report** | `reports/YYYY-MM-DD_technical_fa.md` | Full technical report in Persian |
| **Media Narrative** | `media/narrative_fa.md` | Plain-language summary for business owner |

**Marimo notebook structure (Persian, RTL):**

```python
import marimo

app = marimo.App(width="full", app_title="مشاور مالی هوشمند")

@app.cell
def _():
    import marimo as mo
    import pandas as pd
    import plotly.express as px
    return mo, pd, px

@app.cell
def _(mo):
    mo.md("""
    # 📊 داشبورد مالی کسب‌وکار شما
    **تاریخ گزارش:** ۱۴۰۴/۰۷/۱۵
    **نوع کسب‌وکار:** کافه / رستوران
    """)
    return

@app.cell
def _(mo, pd, px):
    # Financial ratios table
    ratios_data = {
        "نسبت": ["نسبت جاری", "نسبت آنی", "حاشیه سود ناخالص", "حاشیه سود خالص", "بازده دارایی‌ها"],
        "مقدار": [1.85, 0.92, 0.42, 0.12, 0.08],
        "وضعیت": ["✅ خوب", "⚠️ هشدار", "✅ خوب", "⚠️ هشدار", "❌ ضعیف"]
    }
    df = pd.DataFrame(ratios_data)
    mo.ui.table(df)
    return df

@app.cell
def _(pd, px):
    # Cash flow chart
    months = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور"]
    cashflow = [12_000_000, 15_500_000, 8_200_000, 18_000_000, 14_500_000, 16_800_000]
    fig = px.bar(x=months, y=cashflow, title="جریان نقدی ماهانه (ریال)")
    fig.update_layout(font=dict(family="Vazirmatn, Tahoma"), xaxis_title="ماه", yaxis_title="ریال")
    fig
    return

@app.cell
def _(mo):
    # AI Advice section
    mo.md("""
    ## 💡 توصیه‌های مالی

    ### ۱. مدیریت جریان نقدی
    - **وضعیت:** نسبت آنی شما (۰.۹۲) پایین‌تر از حد مطلوب (۱.۰) است.
    - **توصیه:** حساب‌های دریافتنی خود را تسریع کنید. میانگین وصول مطالبات شما ۴۵ روز است که برای کسب‌وکارهای خدماتی طولانی محسوب می‌شود.
    - **اقدام:** ارسال صورت‌حساب هفتگی به جای ماهانه.

    ### ۲. مقایسه با دلار و طلا
    - جریان نقدی ماهانه شما معادل **~۲,۴۰۰ دلار** (با نرخ ۵۰,۰۰۰ ریال) است.
    - اگر همان مبلغ را در طلا سرمایه‌گذاری می‌کردید، بازدهی ۶ ماهه **~۱۸٪** بود.
    - **توصیه:** ۱۰٪ از سود ماهانه را به خرید طلا اختصاص دهید.

    ### ۳. پیش‌بینی ۳ ماهه
    با اطمینان ۸۵٪، جریان نقدی شما در ۳ ماه آینده بین **۳۸ تا ۵۲ میلیون ریال** خواهد بود.
    """)
    return
```

---

## Final Instructions to Codex

```
/goal Build the Persian Financial Advisor as specified above.

Follow the evidence-preserving workflow EXACTLY:
1. Review research/LITERATURE.md and research/DECISIONS.md before writing code.
2. Implement each module in src/ with full type hints and Pydantic validation.
3. Write tests in tests/ BEFORE running on real data.
4. Run checkpoints (tests) before any production run.
5. After each run, synchronize README, Marimo notebook, research chapter, technical report, and media narrative.
6. Never overwrite ledger entries — append only. Every number must trace back to evidence.

Language: App-facing text and data remain Persian, with RTL layout and Vazirmatn. Repository documentation and generated Markdown prose are English under the later user instruction above.
Local-first: Use Ollama for LLM inference. No cloud dependency by default.
Safety: Agents propose. Typed Python computes. Humans approve.
```

## User UI preferences (2026-10-06)

Use Kalameh for Persian typography. Font files are not yet available; prefer an installed Kalameh font and retain a fallback until webfont assets are supplied. For later UI checkpoints, use `npx vibefarsi add contour` after inspecting the package and the target project. UI expansion remains deferred while backend work continues.
