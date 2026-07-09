---
name: southern-etf-daily-report
description: Generate a professional Chinese Southern Fund ETF daily analysis HTML report from ETFirst ETF data. Use when the user asks for 南方基金ETF分析日报, ETF日报, ETF战略日报, ETF规模/资金流向/基金管理人格局分析, or wants a reusable HTML report generator based on 首趋E指/ETFirst ETF list data.
---

# Southern Fund ETF Daily Report

Use this skill to generate a polished Chinese HTML daily report for ETF strategy teams, centered on Southern Fund (`南方基金`) and the full-market ETF landscape.

The bundled script:

- pulls all ETF list rows from ETFirst, or reads a saved raw JSON file;
- analyzes full-market scale, top managers, product categories, flows, and Southern Fund ETF products;
- validates product counts, code uniqueness, scale aggregation, ranking, category sums, and data date consistency;
- writes a professional HTML report named `南方基金ETF分析日报_YYYYMMDD.html`.

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
4. If layout matters, render the HTML in a browser and take a screenshot before delivery.
5. Return the HTML path and mention the raw data path. If validation fails, report the failed checks and do not say the report was verified.

## Output Characteristics

The HTML report includes:

- title: `南方基金ETF分析日报（YYYY年M月D日）`;
- KPI cards for market ETF scale, top-10 managers, Southern Fund rank, attack/defense gap, and sample count;
- `今日摘要` and `ETF营销建议` in separated panels;
- `基金管理人ETF市场格局解读` with equal-sized ranking table and manager scale chart;
- `市场ETF趋势与品类轮动` with equal-sized category table and research observation panel;
- `资金流向榜`;
- `南方基金ETF产品监控`;
- `数据核验专家意见`, ending with `报告内容已经过数据验证agent验证无误。` only when validation passes;
- source notes after tables: `数据来源：南方基金，截至YYYY年M月D日。`

## Notes

- Default data source text is `南方基金 / ETFirst`.
- The script is intentionally dependency-light and uses only the Python standard library.
- The report is for data analysis and internal strategy discussion, not an investment recommendation.
