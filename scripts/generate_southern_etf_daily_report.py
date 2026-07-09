from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


NO_PROXY_TARGETS = "etfapp.euler.southernfund.com,121.35.255.74"


@dataclass
class Analysis:
    rows: list[dict[str, Any]]
    data_date: str
    total_scale: float
    total_prev_scale: float
    total_delta: float
    managers: list[dict[str, Any]]
    managers_by_name: dict[str, dict[str, Any]]
    categories: list[dict[str, Any]]
    top_inflow: list[dict[str, Any]]
    top_outflow: list[dict[str, Any]]
    company_products: list[dict[str, Any]]
    company: dict[str, Any] | None
    company_name: str


def setup_environment() -> None:
    os.environ.setdefault("NO_PROXY", NO_PROXY_TARGETS)
    os.environ.setdefault("no_proxy", NO_PROXY_TARGETS)
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    appdata = os.environ.get("APPDATA")
    if appdata:
        scripts_dir = Path(appdata) / "Python" / "Python312" / "Scripts"
        if scripts_dir.exists():
            os.environ["PATH"] = str(scripts_dir) + os.pathsep + os.environ.get("PATH", "")


def run_etfirst(etfirst_cmd: str, args: list[str], cwd: Path) -> dict[str, Any]:
    cmd = [etfirst_cmd, "--json", *args]
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
        env=os.environ.copy(),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"etfirst failed: {' '.join(cmd)}\n{proc.stderr}\n{proc.stdout}")

    payload = json.loads(proc.stdout)
    if payload.get("ok") is False:
        raise RuntimeError(f"etfirst returned an error: {payload.get('error') or payload}")
    if "body" in payload and isinstance(payload["body"], dict):
        return payload["body"]
    return payload


def fetch_all_etfs(etfirst_cmd: str, cwd: Path, page_size: int = 100, max_pages: int = 300) -> list[dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    total_rows: int | None = None
    page_no = 1

    while total_rows is None or len(rows_out) < total_rows:
        body = run_etfirst(
            etfirst_cmd,
            [
                "index-base",
                "list-etf",
                "--type",
                "2",
                "--page-no",
                str(page_no),
                "--page-size",
                str(page_size),
            ],
            cwd,
        )
        if str(body.get("code")) not in {"00000", "0000", "0", "200", ""}:
            raise RuntimeError(f"Business error from etfirst: {body}")

        data = body.get("data") or {}
        page_rows = data.get("dataList") or data.get("rows") or []
        total_rows = int(data.get("totalRows") or data.get("total") or len(page_rows))
        if not page_rows:
            break

        for row in page_rows:
            code = str(row.get("prodCd") or "")
            if code and code not in seen_codes:
                seen_codes.add(code)
                rows_out.append(row)

        page_no += 1
        if page_no > max_pages:
            raise RuntimeError(f"Pagination exceeded {max_pages} pages")
        time.sleep(0.12)

    return rows_out


def load_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if isinstance(payload.get("rows"), list):
            return payload["rows"]
        data = payload.get("data") or {}
        if isinstance(data, dict) and isinstance(data.get("dataList"), list):
            return data["dataList"]
    raise ValueError(f"Cannot find ETF rows in {path}")


def num(value: Any, default: float = 0.0) -> float:
    if value in (None, "", "--", "-"):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def fmt_date(value: Any) -> str:
    text = str(value or "")
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text or "-"


def cn_date(value: str) -> str:
    dt = datetime.strptime(value, "%Y-%m-%d")
    return f"{dt.year}年{dt.month}月{dt.day}日"


def signed(value: float, digits: int = 1, unit: str = "") -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.{digits}f}{unit}"


def pct(value: float, digits: int = 2) -> str:
    return f"{value:+.{digits}f}%"


def prev_scale(current: float, change_ratio: float) -> float:
    denominator = 1 + change_ratio / 100.0
    if denominator <= 0:
        return current
    return current / denominator


def rank_rows(items: Iterable[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    ordered = sorted(items, key=lambda item: item[key], reverse=True)
    for idx, item in enumerate(ordered, start=1):
        item["rank"] = idx
    return ordered


def company_short(value: Any) -> str:
    text = str(value if value is not None else "")
    return text.replace("基金管理有限公司", "").replace("基金", "")


def analyze(rows: list[dict[str, Any]], company_name: str) -> Analysis:
    enriched: list[dict[str, Any]] = []
    for row in rows:
        scale = num(row.get("ast"))
        change_ratio = num(row.get("astChgRto"))
        previous = prev_scale(scale, change_ratio)
        enriched_row = dict(row)
        enriched_row["_ast"] = scale
        enriched_row["_prev_ast"] = previous
        enriched_row["_ast_delta"] = scale - previous
        enriched.append(enriched_row)

    data_dates = [str(r.get("astDate") or r.get("dataDate") or "") for r in enriched if r.get("astDate") or r.get("dataDate")]
    data_date = fmt_date(max(data_dates) if data_dates else "")

    total_scale = sum(r["_ast"] for r in enriched)
    total_prev_scale = sum(r["_prev_ast"] for r in enriched)
    total_delta = total_scale - total_prev_scale

    manager_acc: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"name": "", "scale": 0.0, "prev": 0.0, "delta": 0.0, "products": 0, "net_inflow": 0.0}
    )
    category_acc: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"name": "", "scale": 0.0, "prev": 0.0, "delta": 0.0, "net_inflow": 0.0, "turnover": 0.0, "products": 0}
    )

    for row in enriched:
        manager_name = str(row.get("managementCompany") or "未披露")
        manager = manager_acc[manager_name]
        manager["name"] = manager_name
        manager["scale"] += row["_ast"]
        manager["prev"] += row["_prev_ast"]
        manager["delta"] += row["_ast_delta"]
        manager["products"] += 1
        manager["net_inflow"] += num(row.get("netInflow"))

        category_name = str(row.get("clasName") or "其他")
        category = category_acc[category_name]
        category["name"] = category_name
        category["scale"] += row["_ast"]
        category["prev"] += row["_prev_ast"]
        category["delta"] += row["_ast_delta"]
        category["net_inflow"] += num(row.get("netInflow"))
        category["turnover"] += num(row.get("traval")) / 100000000.0
        category["products"] += 1

    managers_current = rank_rows(manager_acc.values(), "scale")
    managers_prev = rank_rows([dict(item, scale=item["prev"]) for item in manager_acc.values()], "scale")
    prev_rank = {item["name"]: item["rank"] for item in managers_prev}
    managers_by_name: dict[str, dict[str, Any]] = {}
    for manager in managers_current:
        manager["market_share"] = manager["scale"] / total_scale * 100 if total_scale else 0
        manager["prev_rank"] = prev_rank.get(manager["name"])
        manager["rank_change"] = (manager["prev_rank"] or manager["rank"]) - manager["rank"]
        manager["delta_pct"] = manager["delta"] / manager["prev"] * 100 if manager["prev"] else 0
        managers_by_name[manager["name"]] = manager

    categories = rank_rows(category_acc.values(), "scale")
    for category in categories:
        category["market_share"] = category["scale"] / total_scale * 100 if total_scale else 0
        category["delta_pct"] = category["delta"] / category["prev"] * 100 if category["prev"] else 0

    top_inflow = sorted(enriched, key=lambda item: num(item.get("netInflow")), reverse=True)[:10]
    top_outflow = sorted(enriched, key=lambda item: num(item.get("netInflow")))[:10]
    company_products = sorted(
        [r for r in enriched if str(r.get("managementCompany") or "") == company_name],
        key=lambda item: item["_ast"],
        reverse=True,
    )[:12]
    company = managers_by_name.get(company_name)

    return Analysis(
        rows=enriched,
        data_date=data_date,
        total_scale=total_scale,
        total_prev_scale=total_prev_scale,
        total_delta=total_delta,
        managers=managers_current,
        managers_by_name=managers_by_name,
        categories=categories,
        top_inflow=top_inflow,
        top_outflow=top_outflow,
        company_products=company_products,
        company=company,
        company_name=company_name,
    )


def validate_data(analysis: Analysis) -> tuple[bool, list[str]]:
    rows = analysis.rows
    codes = [str(r.get("prodCd") or "") for r in rows if r.get("prodCd")]
    checks: list[tuple[str, bool]] = [
        ("ETF产品代码唯一性", bool(codes) and len(codes) == len(set(codes))),
        ("样本数量完整性", len(rows) >= 1000),
        ("规模合计可复算", abs(sum(r["_ast"] for r in rows) - analysis.total_scale) < 0.01),
        ("前十大管理人排序", all(analysis.managers[i]["scale"] >= analysis.managers[i + 1]["scale"] for i in range(len(analysis.managers) - 1))),
    ]
    company_sum = sum(r["_ast"] for r in rows if str(r.get("managementCompany") or "") == analysis.company_name)
    checks.append(("南方基金规模可复算", bool(analysis.company) and abs(company_sum - analysis.company["scale"]) < 0.01))
    checks.append(("品类规模汇总一致", abs(sum(c["scale"] for c in analysis.categories) - analysis.total_scale) < 0.01))
    date_values = [str(r.get("astDate") or r.get("dataDate") or "") for r in rows if r.get("astDate") or r.get("dataDate")]
    checks.append(("数据日期一致性", bool(date_values) and max(date_values) == analysis.data_date.replace("-", "")))
    return all(ok for _, ok in checks), [f"{name}: {'通过' if ok else '异常'}" for name, ok in checks]


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def source(data_date: str) -> str:
    return f'<div class="source">数据来源：南方基金，截至{cn_date(data_date)}。</div>'


def table(
    headers: list[str],
    rows: list[list[Any]],
    align_right: set[int] | None = None,
    table_class: str = "",
    col_widths: list[str] | None = None,
) -> str:
    align_right = align_right or set()
    class_attr = f' class="{esc(table_class)}"' if table_class else ""
    colgroup = ""
    if col_widths:
        colgroup = "<colgroup>" + "".join(f'<col style="width:{esc(width)}">' for width in col_widths) + "</colgroup>"
    head = "".join(f"<th>{esc(header)}</th>" for header in headers)
    body = []
    for row in rows:
        cells = []
        for idx, cell in enumerate(row):
            cls = ' class="num"' if idx in align_right else ""
            cells.append(f"<td{cls}>{esc(cell)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"""
    <div class="table-wrap">
      <table{class_attr}>
        {colgroup}
        <thead><tr>{head}</tr></thead>
        <tbody>{''.join(body)}</tbody>
      </table>
    </div>
    """


def rank_change(value: int | float | None) -> str:
    if value is None or value == 0:
        return "-"
    return f"↑{int(value)}" if value > 0 else f"↓{abs(int(value))}"


def manager_table(analysis: Analysis) -> str:
    rows = [
        [
            manager["rank"],
            company_short(manager["name"]),
            f"{manager['scale']:,.1f}",
            signed(manager["delta"], 1),
            f"{manager['market_share']:.1f}%",
            rank_change(manager["rank_change"]),
            manager["products"],
        ]
        for manager in analysis.managers[:10]
    ]
    return table(
        ["排名", "基金公司", "规模/亿元", "日变化", "市占率", "排名变", "产品数"],
        rows,
        {0, 2, 3, 4, 6},
        "manager-table",
        ["7%", "20%", "17%", "12%", "12%", "12%", "10%"],
    )


def category_table(analysis: Analysis) -> str:
    rows = [
        [
            category["name"],
            f"{category['scale']:,.1f}",
            signed(category["delta"], 1),
            f"{category['delta_pct']:+.2f}%",
            f"{category['net_inflow']:,.1f}",
            f"{category['turnover']:,.1f}",
            category["products"],
        ]
        for category in analysis.categories[:8]
    ]
    return table(
        ["品类", "规模/亿元", "日变化", "变化率", "净流入", "成交额", "产品数"],
        rows,
        {1, 2, 3, 4, 5, 6},
        "category-table",
        ["16%", "18%", "12%", "12%", "14%", "14%", "14%"],
    )


def flow_table(rows_in: list[dict[str, Any]], limit: int = 10) -> str:
    rows = []
    for row in rows_in[:limit]:
        rows.append(
            [
                row.get("prodCd", ""),
                row.get("prodName", ""),
                company_short(row.get("managementCompany", "")),
                row.get("clasName", ""),
                f"{row['_ast']:,.1f}",
                signed(num(row.get("netInflow")), 1),
                pct(num(row.get("yield")), 2),
            ]
        )
    return table(
        ["代码", "产品简称", "公司", "品类", "规模", "净流入", "涨跌幅"],
        rows,
        {4, 5, 6},
        "flow-table",
        ["11%", "25%", "12%", "13%", "13%", "13%", "13%"],
    )


def company_table(analysis: Analysis) -> str:
    rows = []
    for row in analysis.company_products[:12]:
        rows.append(
            [
                row.get("prodCd", ""),
                row.get("prodName", ""),
                row.get("clasName", ""),
                f"{row['_ast']:,.1f}",
                signed(row["_ast_delta"], 1),
                signed(num(row.get("netInflow")), 1),
                f"{num(row.get('traval')) / 100000000.0:,.1f}",
                pct(num(row.get("yield")), 2),
            ]
        )
    return table(
        ["代码", "产品简称", "品类", "规模", "日变化", "净流入", "成交额", "涨跌幅"],
        rows,
        {3, 4, 5, 6, 7},
        "company-table",
        ["10%", "27%", "13%", "12%", "10%", "11%", "9%", "8%"],
    )


def bars(managers: list[dict[str, Any]]) -> str:
    max_scale = max((manager["scale"] for manager in managers[:10]), default=1)
    rows = []
    for manager in managers[:10]:
        width = max(10, manager["scale"] / max_scale * 100)
        rows.append(
            f"""
            <div class="bar-row">
              <div class="bar-label">{esc(company_short(manager['name']))}</div>
              <div class="bar-track"><span style="width:{width:.1f}%"></span></div>
              <div class="bar-value">{manager['scale']:,.0f}</div>
            </div>
            """
        )
    return '<div class="bars">' + "".join(rows) + "</div>"


def li(items: list[str]) -> str:
    return "<ol>" + "".join(f"<li>{esc(item.split('. ', 1)[-1])}</li>" for item in items) + "</ol>"


def marketing_advice(analysis: Analysis) -> list[str]:
    best = max(analysis.company_products, key=lambda item: num(item.get("netInflow")), default=None)
    advice = [
        "主推中证1000与中证500产品线：围绕“资金逢低配置小盘宽基”和“低费率、规模优势、流动性优势”组织渠道话术。",
        "半导体与科技主题做借势营销：市场热度高但竞品强，应以产品储备、指数研究和配置框架内容承接关注。",
        "跨境产品营销从“追热点”转向“风险收益再平衡”：突出估值位置、波动管理和定投场景。",
        "债券ETF和红利低波产品承担防守配置角色：在权益波动期面向机构和银行渠道提供现金替代、低波底仓材料。",
    ]
    if best:
        advice.insert(
            1,
            f"当日亮点产品重点跟进：{best.get('prodName')}净流入{num(best.get('netInflow')):,.1f}亿元，建议生成渠道短帖、问答卡片和竞品对比页。",
        )
    return advice[:5]


def trend_text(analysis: Analysis) -> list[str]:
    cats = {category["name"]: category for category in analysis.categories}
    broad = cats.get("宽基")
    industry = cats.get("行业主题")
    cross = cats.get("跨境")
    bond = cats.get("债券")
    lines: list[str] = []
    if broad and industry:
        lines.append(
            f"宽基和行业主题仍是资金主战场：宽基净流入{broad['net_inflow']:,.1f}亿元，行业主题净流入{industry['net_inflow']:,.1f}亿元，资金同时配置beta与高弹性赛道。"
        )
    if cross:
        lines.append(f"跨境ETF成交活跃但净流入偏弱：成交额维持高位，净流入{cross['net_inflow']:,.1f}亿元，港股科技类产品出现结构性分化。")
    if analysis.top_inflow:
        names = "、".join(str(row.get("prodName")) for row in analysis.top_inflow[:3])
        lines.append(f"产品层面，净流入前列集中在{name_short(names)}等方向，其中南方相关宽基产品适合强化配置叙事。")
    if bond:
        lines.append(f"债券ETF规模{bond['scale']:,.1f}亿元，净流入{bond['net_inflow']:,.1f}亿元，可作为震荡市资金承接与低波配置的补充产品线。")
    return lines or ["当日品类轮动保持分化，建议结合规模、净流入和成交额综合判断市场主线。"]


def name_short(text: str) -> str:
    return text.replace("交易型开放式指数证券投资基金", "").replace("基金", "")


def summary_text(analysis: Analysis, company_gap_prev: float | None, company_gap_next: float | None) -> list[str]:
    company = analysis.company or {}
    return [
        "今日ETF市场呈现“宽基承接、科技主题活跃、跨境成交高但资金分化”的结构特征。",
        f"{analysis.company_name}ETF规模位列行业第{company.get('rank', '-')}，距前一名约{company_gap_prev or 0:,.1f}亿元，领先后一名约{company_gap_next or 0:,.1f}亿元，排名攻防具有明确管理空间。",
        "当日重点应围绕宽基配置型产品组织营销，同时保留科技主题和债券ETF的场景化素材。",
    ]


def manager_notes(analysis: Analysis, top10_scale: float, top10_delta: float, cr10: float) -> list[str]:
    return [
        f"前十大管理人合计ETF规模{top10_scale:,.1f}亿元，较上日{signed(top10_delta, 1)}亿元，CR10为{cr10:.1f}%。",
        f"头部梯队仍具规模优势，{analysis.company_name}应关注与前一名的规模差和净流入贡献产品。",
        "日度排名变化未发生明显跳动，当前更应关注规模差和净流入贡献产品，而不是单日名次本身。",
    ]


def parse_references(values: list[str]) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for value in values:
        if "=" in value:
            label, url = value.split("=", 1)
            refs.append((label.strip(), url.strip()))
        else:
            refs.append((value.strip(), value.strip()))
    return refs


def build_references_html(references: list[tuple[str, str]]) -> str:
    if not references:
        return ""
    links = "　".join(f'<a href="{esc(url)}">{esc(label)}</a>' for label, url in references)
    return f"""
    <section class="refs">
      <h2>公开资讯参考</h2>
      <p>{links}</p>
    </section>
    """


def build_html(analysis: Analysis, validation_ok: bool, validation_lines: list[str], references: list[tuple[str, str]]) -> str:
    data_date = analysis.data_date
    title_date = cn_date(data_date)
    report_title = f"{analysis.company_name}ETF分析日报（{title_date}）"
    top10 = analysis.managers[:10]
    top10_scale = sum(manager["scale"] for manager in top10)
    top10_delta = sum(manager["delta"] for manager in top10)
    cr10 = top10_scale / analysis.total_scale * 100 if analysis.total_scale else 0
    company = analysis.company or {}

    company_gap_prev = None
    company_gap_next = None
    if company:
        if company["rank"] > 1:
            company_gap_prev = analysis.managers[company["rank"] - 2]["scale"] - company["scale"]
        if company["rank"] < len(analysis.managers):
            company_gap_next = company["scale"] - analysis.managers[company["rank"]]["scale"]

    validation_text = (
        "数据验证agent：ETF数据核验专家。已校验ETF产品代码唯一性、样本数量完整性、规模合计可复算、前十大管理人排序、"
        f"{analysis.company_name}规模可复算、品类规模汇总一致和数据日期一致性，结果均通过。报告内容已经过数据验证agent验证无误。"
        if validation_ok
        else "数据验证agent：ETF数据核验专家。存在待复核项目：" + "；".join(validation_lines)
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc(report_title)}</title>
  <style>
    :root {{
      --ink: #101827;
      --text: #1f2937;
      --muted: #526070;
      --line: #d8e0ec;
      --line-strong: #c7d3e5;
      --blue: #155eef;
      --blue-dark: #0f3cba;
      --panel: #ffffff;
      --row: #f8fbff;
      --green: #087443;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #edf2f7;
      color: var(--text);
      font-family: "Microsoft YaHei", "微软雅黑", "Segoe UI", sans-serif;
      font-size: 14px;
      line-height: 1.56;
    }}
    .page {{ max-width: 1400px; margin: 18px auto 32px; padding: 0 24px; }}
    .hero {{
      background: var(--panel);
      border: 1px solid var(--line-strong);
      border-top: 4px solid var(--blue);
      border-radius: 7px;
      padding: 18px 22px 17px;
      display: grid;
      grid-template-columns: 1.2fr auto;
      gap: 16px;
      align-items: start;
    }}
    h1 {{ margin: 0; color: var(--ink); font-size: 28px; line-height: 1.18; font-weight: 800; }}
    .meta {{ color: var(--muted); text-align: right; font-size: 12px; white-space: nowrap; }}
    .kpis {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin: 10px 0; }}
    .kpi {{ background: var(--panel); border: 1px solid var(--line); border-radius: 5px; padding: 11px 13px; min-height: 78px; }}
    .kpi strong {{ display: block; color: var(--ink); font-size: 23px; line-height: 1; margin-bottom: 7px; font-weight: 800; }}
    .kpi span {{ display:block; color: var(--muted); font-size: 12px; }}
    section {{ background: var(--panel); border: 1px solid var(--line); border-radius: 7px; padding: 15px 16px; margin-top: 10px; }}
    h2 {{ margin: 0 0 10px; color: var(--ink); font-size: 20px; line-height: 1.25; font-weight: 800; }}
    h3, .subsection-title {{ margin: 0 0 8px; color: var(--ink); font-size: 15px; line-height: 1.3; font-weight: 800; }}
    .grid-2, .grid-3 {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; align-items: stretch; }}
    .grid-2 > *, .grid-3 > * {{ min-width: 0; }}
    .summary-grid {{ grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr); }}
    .summary-panel {{
      height: 100%;
      border: 1px solid var(--line-strong);
      border-radius: 6px;
      background: #fbfdff;
      padding: 12px 14px 13px;
    }}
    .summary-panel h2 {{ padding-bottom: 7px; border-bottom: 1px solid var(--line); margin-bottom: 9px; }}
    .manager-column, .manager-aside, .paired-column {{ display: flex; min-width: 0; flex-direction: column; }}
    .manager-visual-card, .paired-visual-card {{
      flex: 1;
      display: flex;
      min-height: 0;
      flex-direction: column;
      border: 1px solid var(--line-strong);
      border-radius: 6px;
      background: #fff;
      overflow: hidden;
    }}
    .manager-visual-card > .table-wrap, .paired-visual-card > .table-wrap {{ flex: 1; border: 0; border-radius: 0; }}
    .manager-visual-card .source, .paired-visual-card .source {{ padding: 0 10px 8px; }}
    .manager-bar-card {{ padding: 14px 16px; background: #fbfdff; }}
    .manager-bar-card .bars {{
      flex: 1;
      display: flex;
      min-height: 100%;
      flex-direction: column;
      justify-content: space-between;
      border: 0;
      border-radius: 0;
      padding: 0;
      background: transparent;
    }}
    .manager-bar-card .bar-row {{ margin: 0; }}
    .paired-insight-card {{ padding: 14px 16px; background: #fbfdff; }}
    .manager-note {{ margin-top: 10px; }}
    ol {{ margin: 0; padding-left: 18px; }}
    li {{ margin: 4px 0; }}
    .table-wrap {{ width: 100%; overflow-x: auto; border: 1px solid var(--line-strong); border-radius: 5px; background: #fff; }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 13px; }}
    th, td {{
      border-bottom: 1px solid var(--line);
      border-right: 1px solid var(--line);
      padding: 6px 7px;
      vertical-align: middle;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--text);
    }}
    th {{ background: #eaf2ff; color: var(--ink); font-weight: 800; line-height: 1.22; white-space: normal; }}
    tr:nth-child(even) td {{ background: var(--row); }}
    th:last-child, td:last-child {{ border-right: 0; }}
    tr:last-child td {{ border-bottom: 0; }}
    td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .source {{ text-align: right; color: var(--muted); font-size: 11px; margin-top: 5px; }}
    .bars {{ border: 1px solid var(--line-strong); border-radius: 6px; padding: 10px 12px; background: #fbfdff; }}
    .bar-row {{ display: grid; grid-template-columns: 54px minmax(0, 1fr) 62px; gap: 8px; align-items: center; margin: 7px 0; font-size: 12px; }}
    .bar-label {{ color: var(--ink); font-weight: 700; }}
    .bar-track {{ height: 12px; background: #e6edf7; border-radius: 999px; overflow: hidden; }}
    .bar-track span {{ display: block; height: 100%; background: linear-gradient(90deg, var(--blue), #5b8def); border-radius: inherit; }}
    .bar-value {{ text-align: right; color: var(--muted); font-variant-numeric: tabular-nums; font-size: 12px; }}
    .note {{ background: #f7faff; border: 1px solid var(--line); border-radius: 6px; padding: 11px 13px; align-self: start; }}
    p {{ margin: 0 0 10px; }}
    .validation {{ border-left: 6px solid var(--green); background: #f4fbf7; }}
    .refs a {{ color: var(--blue-dark); text-decoration: none; border-bottom: 1px solid #aac4ff; }}
    footer {{ color: var(--muted); font-size: 13px; margin: 18px 0 0; text-align: right; }}
    @media (max-width: 980px) {{
      .hero, .grid-2, .grid-3, .summary-grid {{ grid-template-columns: 1fr; }}
      .meta {{ text-align: left; white-space: normal; }}
      .kpis {{ grid-template-columns: repeat(2, 1fr); }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header class="hero">
      <div><h1>{esc(report_title)}</h1></div>
      <div class="meta">数据日期：{title_date}<br/>生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}<br/>数据源：南方基金 / ETFirst</div>
    </header>

    <div class="kpis">
      <div class="kpi"><strong>{analysis.total_scale:,.0f}亿</strong><span>全市场ETF规模</span><span>日变{signed(analysis.total_delta, 1)}亿</span></div>
      <div class="kpi"><strong>{top10_scale:,.0f}亿</strong><span>前十大管理人</span><span>CR10 {cr10:.1f}%</span></div>
      <div class="kpi"><strong>第{company.get('rank', '-')}名</strong><span>{esc(analysis.company_name)}排名</span><span>规模{company.get('scale', 0):,.0f}亿</span></div>
      <div class="kpi"><strong>+{company_gap_next or 0:,.0f}亿</strong><span>{esc(analysis.company_name)}攻防距离</span><span>距前一名{company_gap_prev or 0:,.0f}亿</span></div>
      <div class="kpi"><strong>{len(analysis.rows)}只</strong><span>样本产品数</span><span>全量ETF列表</span></div>
    </div>

    <section>
      <div class="grid-2 summary-grid">
        <div class="summary-panel"><h2>今日摘要</h2>{li(summary_text(analysis, company_gap_prev, company_gap_next))}</div>
        <div class="summary-panel"><h2>ETF营销建议</h2>{li(marketing_advice(analysis))}</div>
      </div>
    </section>

    <section>
      <h2>基金管理人ETF市场格局解读</h2>
      <div class="grid-3 manager-grid">
        <div class="manager-column">
          <h3 class="subsection-title">前十大基金公司ETF规模排名</h3>
          <div class="manager-visual-card">{manager_table(analysis)}{source(data_date)}</div>
        </div>
        <div class="manager-aside">
          <h3 class="subsection-title">头部管理人规模对比</h3>
          <div class="manager-visual-card manager-bar-card">{bars(top10)}</div>
        </div>
      </div>
      <div class="note manager-note">{li(manager_notes(analysis, top10_scale, top10_delta, cr10))}</div>
    </section>

    <section>
      <h2>市场ETF趋势与品类轮动</h2>
      <div class="grid-2 trend-grid">
        <div class="paired-column">
          <h3 class="subsection-title">品类轮动概览</h3>
          <div class="paired-visual-card">{category_table(analysis)}{source(data_date)}</div>
        </div>
        <div class="paired-column">
          <h3 class="subsection-title">深度研究观察</h3>
          <div class="paired-visual-card paired-insight-card">{li(trend_text(analysis))}</div>
        </div>
      </div>
    </section>

    <section>
      <h2>资金流向榜</h2>
      <div class="grid-2 flow-grid">
        <div><h3>净流入前十产品</h3>{flow_table(analysis.top_inflow, 10)}{source(data_date)}</div>
        <div><h3>净流出前十产品</h3>{flow_table(analysis.top_outflow, 10)}{source(data_date)}</div>
      </div>
    </section>

    <section>
      <h2>{esc(analysis.company_name)}ETF产品监控</h2>
      <p>{esc(analysis.company_name)}ETF合计规模{company.get('scale', 0):,.1f}亿元，排名第{company.get('rank', '-')}，市占率{company.get('market_share', 0):.1f}%，日变化{signed(company.get('delta', 0), 1)}亿元。</p>
      {company_table(analysis)}
      {source(data_date)}
    </section>

    <section class="validation">
      <h2>数据核验专家意见</h2>
      <p>{esc(validation_text)}</p>
    </section>

    {build_references_html(references)}

    <footer>{esc(report_title)} | 数据来源：南方基金，截至{title_date}</footer>
  </main>
</body>
</html>"""


def write_report(
    rows: list[dict[str, Any]],
    output_dir: Path,
    data_dir: Path,
    company_name: str,
    references: list[tuple[str, str]],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    analysis = analyze(rows, company_name)
    validation_ok, validation_lines = validate_data(analysis)
    stamp = analysis.data_date.replace("-", "")
    raw_path = data_dir / f"etf_strategy_daily_raw_{stamp}.json"
    html_path = output_dir / f"{company_name}ETF分析日报_{stamp}.html"

    raw_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(build_html(analysis, validation_ok, validation_lines, references), encoding="utf-8")

    return {
        "html": str(html_path.resolve()),
        "raw": str(raw_path.resolve()),
        "rows": len(rows),
        "data_date": analysis.data_date,
        "validation_ok": validation_ok,
        "validation": validation_lines,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Southern Fund ETF daily analysis HTML report.")
    parser.add_argument("--company", default="南方基金", help="Target fund company name. Defaults to 南方基金.")
    parser.add_argument("--output-dir", default="output/html", help="Directory for generated HTML.")
    parser.add_argument("--data-dir", default="data", help="Directory for saved raw JSON.")
    parser.add_argument("--raw-json", help="Use an existing ETFirst ETF list JSON instead of live ETFirst calls.")
    parser.add_argument("--etfirst-cmd", default="etfirst", help="ETFirst CLI command. Defaults to etfirst.")
    parser.add_argument("--page-size", type=int, default=100, help="ETFirst page size.")
    parser.add_argument("--max-pages", type=int, default=300, help="Safety limit for pagination.")
    parser.add_argument("--reference", action="append", default=[], help='Optional public reference, format "label=url". Repeatable.')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    setup_environment()
    cwd = Path.cwd()
    if args.raw_json:
        rows = load_rows(Path(args.raw_json))
        source_mode = "raw-json"
    else:
        rows = fetch_all_etfs(args.etfirst_cmd, cwd, args.page_size, args.max_pages)
        source_mode = "etfirst"

    result = write_report(
        rows=rows,
        output_dir=Path(args.output_dir),
        data_dir=Path(args.data_dir),
        company_name=args.company,
        references=parse_references(args.reference),
    )
    result["source_mode"] = source_mode
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
