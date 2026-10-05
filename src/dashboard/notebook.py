import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="هرمان | مشاور مالی")


@app.cell
def _():
    import base64
    import html
    import json
    from decimal import Decimal
    from pathlib import Path

    import marimo as mo
    import plotly.graph_objects as go

    from src.analytics.forecast import MonthlyCashFlow, forecast_cashflow
    return Decimal, MonthlyCashFlow, Path, base64, forecast_cashflow, go, html, json, mo


@app.cell
def _(Path, base64, mo):
    _font = base64.b64encode((Path(__file__).parent / "assets" / "Vazirmatn-Regular.woff2").read_bytes()).decode()
    mo.Html('''<style>
    @font-face {font-family:Vazirmatn;src:url(data:font/woff2;base64,FONT_DATA) format("woff2");}
    body, .marimo {font-family:Vazirmatn,Tahoma,sans-serif;direction:rtl;}
    table {border-collapse:collapse;} td,th {padding:12px 16px;border-bottom:1px solid #dce9e6;}
    th {background:#ecf5f2;} tbody tr:nth-child(even) {background:#f7faf9;}
    code {direction:ltr;unicode-bidi:isolate;}
    .herman-hero {background:linear-gradient(120deg,#0f3443,#176e63);padding:36px;
    border-radius:20px;color:white;margin-bottom:22px;}
    .herman-kicker {color:#bce6ce;font-size:13px;letter-spacing:2px;}
    </style><div class="herman-hero" dir="rtl"><div class="herman-kicker">هرمان / همراه مالی کسب‌وکار</div>
    <h1>تصویر روشن‌تری از کسب‌وکارتان ببینید</h1>
    <p>شواهد، محاسبات دقیق و تصمیم انسانی در یک نگاه</p></div>'''.replace("FONT_DATA", _font))
    return


@app.cell
def _(Path, json, mo):
    root = Path(__file__).resolve().parents[2]
    refresh = mo.ui.run_button(label="بازخوانی آخرین گزارش")
    refresh
    return refresh, root


@app.cell
def _(json, mo, refresh, root):
    refresh.value
    pointer = root / "runs" / "latest.json"
    mo.stop(not pointer.exists(), mo.md("هنوز گزارشی وجود ندارد. ابتدا `advisor demo` را اجرا کنید."))
    manifest_path = root / json.loads(pointer.read_text(encoding="utf-8"))["manifest"]
    result = json.loads(manifest_path.read_text(encoding="utf-8"))
    mo.vstack([mo.md(f"## {result['business_name']}"),
               mo.callout(result["note_fa"], kind="warn" if result["synthetic"] else "info"),
               mo.md(f"تاریخ: {result['created_at'][:10]} · واحد: ریال · شناسه: `{result['run_id']}`")])
    return (result,)


@app.cell
def _(mo):
    search = mo.ui.text(label="جست‌وجوی نسبت", placeholder="برای نمونه: سود")
    mo.vstack([mo.md("## سلامت مالی در یک نگاه"), search])
    return (search,)


@app.cell
def _(Decimal, html, mo, result, search):
    _digits = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    _rows = []
    for _ratio in result["ratios"]:
        if search.value and search.value not in _ratio["name_fa"]:
            continue
        _value = (format(Decimal(_ratio["value"]), ".4f").rstrip("0").rstrip(".")
                  if _ratio["value"] is not None else "تعریف‌نشده")
        _cells = [_ratio["name_fa"], _value.translate(_digits), _ratio["formula_fa"],
                  _ratio["warning_fa"] or "نیازمند مقایسه با صنعت"]
        _rows.append("<tr>" + "".join("<td>" + html.escape(_cell) + "</td>" for _cell in _cells) + "</tr>")
    mo.Html('<div dir="rtl"><table style="width:100%;text-align:right"><thead><tr>'
            '<th>نسبت</th><th>مقدار</th><th>روش محاسبه</th><th>یادداشت</th></tr></thead><tbody>'
            + "".join(_rows) + '</tbody></table><p>نسبت‌ها به صورت کسر؛ نمایش گرد‌شده تا چهار رقم اعشار</p></div>')
    return


@app.cell
def _(mo):
    horizon = mo.ui.slider(start=1, stop=12, value=3, label="افق بررسی پیش‌بینی (ماه)", show_value=True)
    horizon
    return (horizon,)


@app.cell
def _(MonthlyCashFlow, forecast_cashflow, go, horizon, mo, result):
    chart = go.Figure()
    chart.add_bar(x=[r["month"] for r in result["monthly_cashflows"]],
                  y=[float(r["net"]["value"]) for r in result["monthly_cashflows"]],
                  name="جریان نقد ثبت‌شده", marker_color="#218577")
    scenario = forecast_cashflow([MonthlyCashFlow.model_validate(r) for r in result["monthly_cashflows"]],
                                 horizon=horizon.value)
    future = scenario["predictions"]
    if future:
        chart.add_scatter(x=[r["month"] for r in future], y=[r["estimate"] for r in future],
                          name="پیش‌بینی", mode="lines+markers", line_color="#c18124",
                          error_y=dict(type="data", symmetric=False,
                                       array=[r["upper"] - r["estimate"] for r in future],
                                       arrayminus=[r["estimate"] - r["lower"] for r in future]))
    chart.update_layout(title="جریان نقد ماهانه و بازه پیش‌بینی", template="plotly_white",
                        font_family="Vazirmatn, Tahoma", yaxis_title="ریال", xaxis_title="ماه شمسی")
    mo.vstack([mo.ui.plotly(chart, config={"displayModeBar": False}),
               mo.md("بازه اسمی ۸۵٪؛ تغییر افق فقط برای بررسی تعاملی است و گزارش ذخیره‌شده را تغییر نمی‌دهد."),
               mo.callout(scenario["warning_fa"], kind="warn")])
    return


@app.cell
def _(mo, result):
    mo.vstack([mo.md("## گام بعدی برای بررسی"), mo.md(result["advice_fa"]),
               mo.accordion({"شواهد و روش محاسبه": mo.json(result),
                             "درباره تأیید اسناد": mo.md("پیشنهادها تا تصمیم انسانی وارد مانده دفتر نمی‌شوند.")})])
    return


@app.cell
def _(html, mo, result):
    _comparisons = result.get("benchmarks", [])
    _body = "<p>نرخ مستند وارد نشده است؛ مقایسه‌ای محاسبه نشده است.</p>"
    if _comparisons:
        _body = "<table><tr><th>دارایی</th><th>ارزش فرضی پایان (ریال)</th><th>بازده اسمی (کسر)</th></tr>"
        for _comparison in _comparisons:
            _label = "دلار آمریکا" if _comparison["asset"] == "USD" else "گرم طلای ۱۸عیار"
            _body += ("<tr><td>" + _label + "</td><td>" + html.escape(_comparison["ending_value_irr"]) +
                      "</td><td>" + html.escape(_comparison["nominal_return"]) + "</td></tr>")
        _body += "</table><p>مقایسه فرضی بدون هزینه معامله و تعدیل تورم؛ توصیه خرید نیست.</p>"
    mo.Html('<section dir="rtl"><h2>مقایسه با دلار و طلا</h2>' + _body + '</section>')
    return


if __name__ == "__main__":
    app.run()
