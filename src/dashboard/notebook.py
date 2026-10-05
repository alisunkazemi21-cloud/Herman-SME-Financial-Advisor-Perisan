import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="هرمان | مشاور مالی")


@app.cell
def _():
    import json
    from pathlib import Path

    import marimo as mo
    import plotly.graph_objects as go
    return Path, go, json, mo


@app.cell
def _(mo):
    mo.Html('''<style>
    @font-face {font-family:Vazirmatn;src:local("Vazirmatn");}
    body, .marimo {font-family:Vazirmatn,Tahoma,sans-serif;direction:rtl;}
    .herman-hero {background:linear-gradient(120deg,#0f3443,#176e63);padding:36px;
    border-radius:20px;color:white;margin-bottom:22px;}
    .herman-kicker {color:#bce6ce;font-size:13px;letter-spacing:2px;}
    </style><div class="herman-hero" dir="rtl"><div class="herman-kicker">هرمان / همراه مالی کسب‌وکار</div>
    <h1>تصویر روشن‌تری از کسب‌وکارتان ببینید</h1>
    <p>شواهد، محاسبات دقیق و تصمیم انسانی در یک نگاه</p></div>''')
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
def _(mo, result):
    ratio_rows = [{"نسبت": r["name_fa"], "مقدار": r["value"] or "تعریف‌نشده",
                   "روش محاسبه": r["formula_fa"], "یادداشت": r["warning_fa"] or "نیازمند مقایسه با صنعت"}
                  for r in result["ratios"]]
    mo.vstack([mo.md("## سلامت مالی در یک نگاه"), mo.ui.table(ratio_rows, selection=None)])
    return


@app.cell
def _(go, mo, result):
    chart = go.Figure()
    chart.add_bar(x=[r["month"] for r in result["monthly_cashflows"]],
                  y=[float(r["net"]["value"]) for r in result["monthly_cashflows"]],
                  name="جریان نقد ثبت‌شده", marker_color="#218577")
    future = result["forecast"]["predictions"]
    if future:
        chart.add_scatter(x=[r["month"] for r in future], y=[r["estimate"] for r in future],
                          name="پیش‌بینی", mode="lines+markers", line_color="#c18124",
                          error_y=dict(type="data", symmetric=False,
                                       array=[r["upper"] - r["estimate"] for r in future],
                                       arrayminus=[r["estimate"] - r["lower"] for r in future]))
    chart.update_layout(title="جریان نقد ماهانه و بازه پیش‌بینی", template="plotly_white",
                        font_family="Vazirmatn, Tahoma", yaxis_title="ریال", xaxis_title="ماه شمسی")
    mo.vstack([mo.ui.plotly(chart), mo.callout(result["forecast"]["warning_fa"], kind="warn")])
    return


@app.cell
def _(mo, result):
    mo.vstack([mo.md("## گام بعدی برای بررسی"), mo.md(result["advice_fa"]),
               mo.accordion({"شواهد و روش محاسبه": mo.json(result),
                             "درباره تأیید اسناد": mo.md("پیشنهادها تا تصمیم انسانی وارد مانده دفتر نمی‌شوند.")})])
    return


if __name__ == "__main__":
    app.run()
