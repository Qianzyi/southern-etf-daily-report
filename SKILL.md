---
name: southern-etf-daily-report
description: Use when the user asks for 南方基金ETF分析日报, ETF日报, ETF战略日报, ETF规模/资金流向/基金管理人格局分析, or a reusable ETFirst/首趋E指 ETF report in HTML or PDF.
---

# Southern Fund ETF Daily Report

Use this skill to generate a polished Chinese ETF daily report for ETF strategy teams, centered on Southern Fund (`南方基金`) and the full-market ETF landscape. The canonical deliverable is a single-page vertical PDF, with HTML as the editable source.

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
python scripts/generate_southern_etf_daily_report.py --company 南方基金
python scripts/generate_southern_etf_daily_report.py --reference "上海证券报=https://example.com/article"
```

The script prints JSON containing `html`, `raw`, `rows`, `data_date`, and `validation_ok`.

## Prerequisites

Require Python 3.10+ and a working ETFirst CLI named `etfirst` on `PATH`.

Do not publish or hard-code ETFirst keys in generated reports, scripts, commits, or GitHub repositories. Users should configure ETFirst locally according to their own authorization process.

For ETFirst setup details and data-field assumptions, read `references/etfirst.md` only when installation, authentication, or field mapping is relevant.

## Workflow

1. Confirm whether the user wants live data or an offline cached JSON.
2. If live data is requested, run the bundled script directly. If ETFirst is rate-limited, ask for or use a saved raw JSON file with `--raw-json`.
3. Inspect the JSON result and ensure `validation_ok` is true before presenting the report as verified.
4. If layout matters or PDF is requested, render the HTML in a browser and visually inspect the output before delivery.
5. For PDF delivery, use the final format below and render the PDF to PNG for verification.
6. Return the HTML/PDF path and mention the raw data path. If validation fails, report the failed checks and do not say the report was verified.

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

Manager `排名变` must compare current non-currency ETF manager scale ranking against the nearest previous raw data file in `data-dir` (`etf_strategy_daily_raw_YYYYMMDD.json`). Use the previous trading day's actual manager scale aggregation when available; only fall back to same-day `astChgRto` back-calculation if no previous raw file exists.

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
- use a single-page vertical long-page PDF, not A4 landscape and not multi-page;
- preserve the Apple-style glassmorphism look, Microsoft YaHei font, black text, red for increases/规模增加, green for decreases/规模下降;
- keep the 10 KPI cards as two rows of five at the top;
- export from the HTML source, then render the PDF to PNG and inspect for clipping, overlap, tiny unreadable text, or broken tables before delivery.

## Notes

- Default data source text is `南方基金 / ETFirst`.
- The script is intentionally dependency-light and uses only the Python standard library.
- The report is for data analysis and internal strategy discussion, not an investment recommendation.
