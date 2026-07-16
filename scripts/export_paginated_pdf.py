from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path


DEFAULT_CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
DEFAULT_EXPORTER = Path(__file__).with_name("export_single_page_pdf.js")


def default_node_cmd() -> str:
    for env_name in ("NODE_EXE", "CODEX_NODE"):
        value = os.environ.get(env_name)
        if value and Path(value).exists():
            return value
    found = shutil.which("node")
    if found:
        return found
    candidate = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe"
    if candidate.exists():
        return str(candidate)
    return "node"


def export_pdf(html_path: Path, pdf_path: Path, chrome_path: Path, node_cmd: str, exporter: Path) -> dict[str, str | int]:
    html_path = html_path.resolve()
    pdf_path = pdf_path.resolve()
    chrome_path = chrome_path.resolve()
    exporter = exporter.resolve()

    if not html_path.exists():
        raise FileNotFoundError(f"HTML input does not exist: {html_path}")
    if not chrome_path.exists():
        raise FileNotFoundError(f"Chrome executable does not exist: {chrome_path}")
    if not exporter.exists():
        raise FileNotFoundError(f"Single-page PDF exporter does not exist: {exporter}")

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        node_cmd,
        str(exporter),
        str(html_path),
        str(pdf_path),
        "--chrome",
        str(chrome_path),
    ]
    proc = subprocess.run(
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
        raise RuntimeError(f"Chrome did not create a PDF: {pdf_path}\n{proc.stderr}")

    details = {}
    if proc.stdout.strip():
        try:
            details = json.loads(proc.stdout)
        except json.JSONDecodeError:
            details = {}

    return {
        "html": str(html_path),
        "pdf": str(pdf_path),
        "bytes": pdf_path.stat().st_size,
        "width": details.get("width", ""),
        "height": details.get("height", ""),
        "pages": details.get("pages", ""),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export an ETF daily report as a single-page height-fitted PDF.")
    parser.add_argument("html", type=Path, help="Canonical report HTML path.")
    parser.add_argument("pdf", type=Path, help="Destination PDF path.")
    parser.add_argument(
        "--chrome",
        type=Path,
        default=Path(os.environ.get("CHROME_EXE", DEFAULT_CHROME)),
        help="Chrome executable path.",
    )
    parser.add_argument("--node", default=default_node_cmd(), help="Node.js executable or command.")
    parser.add_argument("--exporter", type=Path, default=DEFAULT_EXPORTER, help="Single-page PDF exporter script.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(json.dumps(export_pdf(args.html, args.pdf, args.chrome, args.node, args.exporter), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
