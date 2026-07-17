---
name: southern-etf-daily-report
description: Use when the user asks for 南方基金ETF分析日报, ETF日报, ETF战略日报, ETF规模/资金流向/基金管理人格局分析, or a reusable ETFirst/首趋E指 ETF report in HTML or PDF.
---

# Southern Fund ETF Daily Report

Use this skill to generate a polished Chinese ETF daily report for ETF strategy teams, centered on Southern Fund (`南方基金`) and the full-market ETF landscape. The canonical deliverable is the approved multi-page Letter PDF, with HTML as the editable source.

The bundled script:

- pulls all ETF list rows from ETFirst, or reads a saved raw JSON file;
- analyzes non-currency ETF scale, top managers, product categories, flows, and Southern Fund ETF products;
- validates product counts, code uniqueness, scale aggregation, ranking, category sums, and data date consistency;
- writes a professional HTML report named `南方基金ETF分析日报_YYYYMMDD.html`;
- when PDF is requested, export the final file as `南方基金ETF分析日报_YYYYMMDD.pdf`.

## Quick Start

From the skill directory:

```powershell
python scripts/generate_southern_etf_daily_report.py
```

Useful options:

```powershell
python scripts/generate_southern_etf_daily_report.py --output-dir output/html --data-dir data
python scripts/generate_southern_etf_daily_report.py --raw-json path/to/etf_rows.json
python scripts/generate_southern_etf_daily_report.py --target-data-date 2026-07-14
python scripts/generate_southern_etf_daily_report.py --company 南方基金
python scripts/generate_southern_etf_daily_report.py --reference "上海证券报=https://example.com/article"
python scripts/export_paginated_pdf.py output/html/南方基金ETF分析日报_20260714.html output/pdf/南方基金ETF分析日报_20260714.pdf
```

The script prints JSON containing `html`, `raw`, `rows`, `data_date`, `target_data_date`, and `validation_ok`.

## Today Report Date Rule

- For both manual requests and scheduled tasks, wording such as "today", "today's report", `今天`, or `今日` sets the target data date to the trigger date minus one calendar day. It never means same-day intraday data.
- Example: a request or an 08:30 scheduled run on 2026-07-15 targets 2026-07-14 data and analyzes the market situation of 2026-07-14.
- Always pass the locked date with `--target-data-date YYYY-MM-DD`. The bundled script defaults this option to the previous calendar day, so unattended scheduled runs follow the same rule.
- The report date and file name must be based on ETF scale/ranking data fields `astDate`/`dataDate`, not `yieldDate`. `yieldDate` may be newer because it is a market return field and must never be used as the report data date for this scale/ranking report.
- The target date must match the ETF scale/ranking date exactly. If ETFirst returns `astDate`/`dataDate` older than the target date, stop and report that ETFirst has not updated scale/ranking data yet; do not silently generate a report with stale scale data.
- Never use data dated after the target date. If the live endpoint returns newer data, the generator must stop; rerun with a saved raw JSON snapshot no later than the target date.
- An explicit historical date from the user overrides the relative-date rule and becomes the target data date.

## Prerequisites

Require Python 3.10+ and a working ETFirst CLI named `etfirst` on `PATH`.

PDF export and layout validation require Python packages `pypdf` and `pdfplumber`.

Do not publish or hard-code ETFirst keys in generated reports, scripts, commits, or GitHub repositories. Users should configure ETFirst locally according to their own authorization process.

For ETFirst setup details and data-field assumptions, read `references/etfirst.md` only when installation, authentication, or field mapping is relevant.

## Workflow

1. Lock the target data date. For `今日`/`今天` and scheduled daily runs, use the trigger date minus one calendar day.
2. Confirm whether the user wants live data or an offline cached JSON. Pass the locked date through `--target-data-date`.
3. If live data is requested, run the bundled script directly. If ETFirst is rate-limited or returns data newer than the target date, ask for or use a saved raw JSON file with `--raw-json`.
4. Inspect the JSON result and ensure `validation_ok` is true before presenting the report as verified.
5. If layout matters or PDF is requested, render the HTML in a browser and visually inspect the output before delivery.
6. For PDF delivery, use the final format below and render the PDF to PNG for verification.
7. Return the HTML/PDF path and mention the raw data path. If validation fails, report the failed checks and do not say the report was verified.

## Output Characteristics

The HTML report includes:

- title: `南方基金ETF分析日报（YYYY年M月D日）`;
- 10 KPI cards in two rows of five:
  `全市场非货ETF合计规模`, `前十大管理人非货ETF合计规模`, `南方基金非货ETF规模排名`, `前一名基金非货ETF规模`, `全市场非货ETF数量`,
  `当日全市场非货ETF净流入`, `前十大管理人非货ETF规模占比`, `南方基金非货ETF合计规模`, `距前一名追赶距离`, `南方基金非货ETF数量`;
- `今日摘要` and `ETF营销建议` in separated panels;
- `基金管理人ETF市场格局解读` with equal-sized ranking table and manager scale chart;
- `市场ETF趋势与品类轮动` with equal-sized category table and research observation panel;
- `资金流向榜`;
- `南方基金ETF产品监控`;
- table headers with bracketed units, such as `规模（亿元）`, `净流入（亿元）`, `成交额（亿元）`, `市占率（%）`, `产品数（只）`, and `涨跌幅（%）`;
- source notes after tables: `数据来源：南方基金，截至YYYY年M月D日。`

Data validation must still run and `validation_ok` must be checked, but the report body should not display a `数据核验专家意见` section.

The report's `data_date`, title date, source notes, raw JSON file stamp, and PDF/HTML file names must all come from `astDate`/`dataDate`. Do not use `yieldDate` to stamp or validate the report.

Manager `排名变` must compare current non-currency ETF manager scale ranking against the nearest previous raw data file in `data-dir` (`etf_strategy_daily_raw_YYYYMMDD.json`). Use the previous trading day's actual manager scale aggregation when available; only fall back to same-day `astChgRto` back-calculation if no previous raw file exists.

## Layout Contract

Treat the report layout as fixed unless the user explicitly asks to redesign it. Data fixes, ranking logic changes, field-name changes, and daily generation must preserve the established output form:

- HTML structure and CSS should remain consistent with the approved July 10 paginated Apple-style glassmorphism report.
- Keep the section order unchanged: header, 10 KPI cards, 今日摘要/ETF营销建议, 基金管理人ETF市场格局解读, 市场ETF趋势与品类轮动, 资金流向榜, 南方基金ETF产品监控, footer.
- In the PDF, keep 10 KPI cards as five rows of two.
- In the PDF, stack the summary panels, manager ranking table and chart, category table and research observation panel, and flow tables in reading order.
- Keep table headers with bracketed units and source notes after tables.
- Do not reintroduce `日变化` columns or the `数据核验专家意见` display block.
- Final PDF must use the approved standard Letter pagination at 612 x 792 pt with natural Chrome pagination and 10 mm inner page padding.
- Do not solve whitespace by changing CSS, changing the HTML structure, switching to a screenshot/image PDF, changing to a single long page, or forcing a different page size.
- If the final page has excessive bottom whitespace, trim only the bottom page box of the final PDF page with `scripts/trim_pdf_tail_whitespace.py`. This is a PDF post-process and must not re-render, rescale, or reflow report content.
- Every PDF export must pass `scripts/validate_pdf_layout.py`: at least two pages, Letter width, full Letter height for all non-final pages, a not-larger-than-Letter final page, and extractable text. If validation fails, treat the report as broken and do not deliver it.
- Before delivery after any code or data-logic change, compare the new HTML/CSS structure with the previous approved report when available. CSS and structural diffs should be zero unless the user explicitly requested a layout change.

## Official-Ranking口径

Use these rules when comparing against the official Wind-style ranking screenshots:

- 主表口径：`非货ETF规模排名`，ETFirst `index-base list-etf --type 2` 全量结果的规模、排名、产品数可对齐该口径。
- 不要按产品名称中的 `现金` 字样剔除产品；例如 `自由现金流ETF` 不是货币ETF。
- `非货非债ETF规模排名`：在主表基础上按结构化字段剔除 `clasName == 债券`，不要用产品名称模糊匹配“债”。
- 规模、排名、产品数是主要可核验口径；2026-07-10 8:01 的官方截图中，南方基金 `非货ETF` 为 `2579.36亿元 / 83只`，`非货非债ETF` 为 `2172.69亿元 / 81只`，可由 ETFirst 2026-07-09 数据复算对齐。
- 净流入存在数据源口径差异：Wind截图脚注说明 `净流入不含上市当天认购规模`，ETFirst `netInflow` 可能包含不同处理。报告中如未接入 Wind 净流入，应标注为 ETFirst 口径，不宣称与 Wind 净流入完全一致。

## Final PDF Format

When the user asks for PDF or the final shareable report:

- file name must be `南方基金ETF分析日报_YYYYMMDD.pdf`;
- use the approved multi-page Letter PDF, not A4 landscape and not a single-page screenshot/long-canvas export;
- preserve the Apple-style glassmorphism look, Microsoft YaHei font, black text, red for increases/规模增加, green for decreases/规模下降;
- keep the 10 KPI cards as five rows of two in the PDF;
- export from the HTML source with `scripts/export_paginated_pdf.py`, which preserves the approved layout and then trims only final-page bottom whitespace. Render/inspect the PDF for clipping, overlap, tiny unreadable text, broken tables, or excessive blank space before delivery.

## Notes

- Default data source text is `南方基金 / ETFirst`.
- The script is intentionally dependency-light and uses only the Python standard library.
- The report is for data analysis and internal strategy discussion, not an investment recommendation.
