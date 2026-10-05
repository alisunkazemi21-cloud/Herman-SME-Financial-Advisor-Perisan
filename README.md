# Herman SME Financial Advisor ( Perisan)

<div dir="rtl">

مشاور مالی محلی برای کسب‌وکارهای کوچک ایرانی: استخراج سند، دفتر دوطرفه با شواهد، محاسبهٔ دقیق و داشبورد فارسی. عامل پیشنهاد می‌دهد، Python محاسبه می‌کند و انسان تصمیم می‌گیرد.

## شروع

Python 3.11 یا جدیدتر لازم است. دستورها را در ریشه مخزن اجرا کنید:

</div>

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,ocr]"
.\.venv\Scripts\python.exe -m pytest tests -v --tb=short
.\.venv\Scripts\python.exe -m src.cli demo
.\.venv\Scripts\marimo.exe run src/dashboard/notebook.py --watch
```

```sh
# معادل با uv
uv sync --extra dev --extra ocr
uv run pytest tests/ -v --tb=short
uv run advisor demo
uv run marimo run src/dashboard/notebook.py --watch
```

<div dir="rtl">

نمونه کاملاً ساختگی است. همه مبالغ ریال هستند. هیچ نرخ جاری دلار/طلا یا توصیه خرید در نمونه نیست. برای ویرایش تعاملی از `marimo edit src/dashboard/notebook.py --watch` استفاده کنید. فونت Vazirmatn در صورت نصب محلی استفاده می‌شود؛ جایگزین Tahoma است و فونت از اینترنت دریافت نمی‌شود.

## گردش سند

۱. فایل را با دستور زیر استخراج کنید. Google Sheets باید به CSV یا XLSX صادر شود؛ اتصال زنده وجود ندارد.

</div>

```sh
advisor ingest invoice.pdf --output extracted.json --engine tesseract
advisor propose proposal.json --book data/book.jsonl
advisor trace J1 --book data/book.jsonl
advisor decide decision.json --book data/book.jsonl
advisor run reviewed_input.json --output .
```

<div dir="rtl">

۲. متن، رقم، تاریخ، واحد و حساب‌ها را بررسی کنید و پیشنهاد را مطابق مدل `JevEntry` بسازید. `samples/proposal.example.json` و `samples/decision.example.json` قالب هستند؛ مسیر و هش شاهد را باید با فایل خود جایگزین کنید. تأیید سند باید با نام `human:...` و `reviewed_values: true` باشد. confidence کمتر از ۰٫۸ نیاز به بازبینی بیشتر دارد؛ confidence بالا هم ثبت خودکار ایجاد نمی‌کند.

۳. برای گزارش مالی، ورودی `RunInput` را مطابق خروجی ساختگی `samples/demo_input.json` بسازید. صورت مالی بررسی‌شده به‌طور صریح وارد می‌شود؛ مانده‌های دفتر به‌تنهایی برای ساخت خودکار صورت مالی، میانگین ابتدا/انتها و طبقه‌بندی جاری/غیرجاری کافی نیستند. هر قلم دارای شاهد و محل استخراج است. گزارش حاضر تحلیل صورت مالی واردشده است، نه ادعای تهیه خودکار صورت مالی قانونی از دفتر.

۴. هر اجرای موفق manifest، README اجرا، فصل پژوهش، گزارش فنی و روایت را ذخیره می‌کند؛ داشبورد از `runs/latest.json` می‌خواند. شماره اجرا در همه خروجی‌ها مشترک است. گزارش‌های قدیمی نگه داشته می‌شوند. فایل‌های واقعی را در Git ثبت نکنید؛ `data/` نادیده گرفته می‌شود. برای اسناد واقعی خروجی را در `data/analysis` بگذارید.

## OCR و عامل محلی

Tesseract و زبان‌های `fas` و `eng` باید روی دستگاه نصب و در PATH باشند. بسته Python به‌تنهایی موتور را نصب نمی‌کند. برای EasyOCR از `pip install -e '.[easyocr]'` استفاده و مدل‌ها را پیشاپیش در مسیر محلی قرار دهید؛ دانلود خودکار خاموش است. DocFlow و Aspose صرفاً در پژوهش مقایسه شده‌اند و adapter اجرایی ندارند.

Ollama با مدل قابل تنظیم از کلاس `FinancialAgent` استفاده می‌شود؛ نمونه نام مدل `mshojaei77/gemma3persian` است. API فقط روی نشانی صریح loopback کار می‌کند، proxy و redirect خاموش‌اند. حالت cloud در برنامه پیاده نشده؛ خود Ollama نیز باید با مدل محلی و بدون cloud پیکربندی شده باشد. عامل هیچ ابزار ثبت یا تأیید ندارد و متنش همیشه پیش‌نویس تأییدنشده است. محاسبات گزارش بدون Ollama اجرا می‌شوند.

## کنترل‌های مالی و حدود کاربرد

- ده نسبت با Decimal و منشأ هر ورودی؛ ROA/ROE با میانگین ابتدا و انتهای دوره. مخرج صفر/منفی تعریف‌نشده است.
- دفتر JSONL افزایشی با قفل، SHA256، بایگانی شاهد و رویداد تصمیم جداگانه. اصلاح با سند معکوس انجام می‌شود. این ابزار تک‌کاربرهٔ مورد اعتماد است؛ actor احراز هویت نیست و هش زنجیره جلوی بازنویسی کل فایل توسط مدیر دستگاه را نمی‌گیرد.
- XIRR با ACT/365F؛ جریان چندریشه‌ای رد می‌شود. مقایسه دلار/گرم طلای ۱۸عیار فقط با نرخ‌های مستندِ ورودی.
- پیش‌بینی حداقل ۲۴ ماه پیوسته نیاز دارد؛ ADF و غربال فصل پیش از تفسیر اجرا می‌شوند. بازه bootstrap تجربی است؛ تضمین پوشش و مدل‌سازی تورم/رمضان ندارد.
- استانداردهای ۱۶/۳۹/۴۳ به‌صورت برچسب بررسی حسابدار ثبت می‌شوند؛ انطباق قانونی کامل، تلفیق و شناسایی خودکار درآمد ادعا نمی‌شود.
- استخراج PDF صفحه‌به‌صفحه برای صفحات فاقد متن OCR می‌کند؛ متن ناقص در PDF ترکیبی باید دستی بررسی شود. confidence متن/Excel نشانگر انتقال متن است، نه صحت حسابداری.

## آزمون موتور واقعی

`PFA_OCR_FIXTURES` را به پوشهٔ سه فاکتور برچسب‌دار با `cases.json` تنظیم کنید. هر مورد دارای `image` و `expected_fragments` (با رقم لاتین) است. آزمون `test_real_ocr_three_labelled_invoices` بدون این فایل‌ها skip می‌شود. stubهای آزمون ادعای دقت OCR نیستند. پیش از استفاده تولیدی این checkpoint و بررسی حسابدار لازم است.

پژوهش و دلایل انتخاب در [LITERATURE](research/LITERATURE.md)، [DECISIONS](research/DECISIONS.md) و [WORKFLOW](research/WORKFLOW.md) ثبت شده است.

</div>
