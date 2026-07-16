from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from trim_pdf_tail_whitespace import trim_pdf_tail_whitespace
from validate_pdf_layout import validate_report_pdf_layout


DEFAULT_CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


def export_pdf(
    html_path: Path,
    pdf_path: Path,
    chrome_path: Path,
    trim_tail: bool = True,
) -> dict[str, str | int | float | bool]:
    html_path = html_path.resolve()
    pdf_path = pdf_path.resolve()
    chrome_path = chrome_path.resolve()

    if not html_path.exists():
        raise FileNotFoundError(f"HTML input does not exist: {html_path}")
    if not chrome_path.exists():
        raise FileNotFoundError(f"Chrome executable does not exist: {chrome_path}")

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(chrome_path),
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-pdf-header-footer",
        "--run-all-compositor-stages-before-draw",
        f"--print-to-pdf={pdf_path}",
        html_path.as_uri(),
    ]
    subprocess.run(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        env=os.environ.copy(),
    )
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise RuntimeError(f"Chrome did not create a PDF: {pdf_path}")

    trim_result: dict[str, str | int | float | bool] = {"trimmed": False}
    if trim_tail:
        trim_result = trim_pdf_tail_whitespace(pdf_path, pdf_path)
    layout_result = validate_report_pdf_layout(pdf_path, trim_result=trim_result)

    return {
        "html": str(html_path),
        "pdf": str(pdf_path),
        "bytes": pdf_path.stat().st_size,
        **trim_result,
        **layout_result,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export an ETF daily report as the approved paginated Letter PDF.")
    parser.add_argument("html", type=Path, help="Canonical report HTML path.")
    parser.add_argument("pdf", type=Path, help="Destination PDF path.")
    parser.add_argument(
        "--chrome",
        type=Path,
        default=Path(os.environ.get("CHROME_EXE", DEFAULT_CHROME)),
        help="Chrome executable path.",
    )
    parser.add_argument("--no-trim-tail", action="store_true", help="Disable final-page bottom whitespace trimming.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(json.dumps(export_pdf(args.html, args.pdf, args.chrome, not args.no_trim_tail), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
