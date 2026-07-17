from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

import pdfplumber
from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject


def _last_text_bottom_from_top(pdf_path: Path) -> tuple[int, float, float, float]:
    with pdfplumber.open(str(pdf_path)) as pdf:
        page_index = len(pdf.pages) - 1
        page = pdf.pages[page_index]
        if not page.chars:
            return page_index, float(page.height), 0.0, float(page.height)
        bottom = max(float(char["bottom"]) for char in page.chars)
        blank = float(page.height) - bottom
        return page_index, float(page.height), bottom, blank


def trim_pdf_tail_whitespace(
    input_pdf: Path,
    output_pdf: Path | None = None,
    *,
    bottom_margin_pt: float = 22.0,
    min_blank_pt: float = 36.0,
) -> dict[str, Any]:
    """Crop only the bottom of the last page, preserving all existing layout content.

    Chrome's paginated PDF output is the source of truth for the approved report layout.
    This post-process does not re-render HTML, rescale content, or change earlier pages.
    It only shortens the last page box when there is obvious blank space below the last
    text line.
    """

    input_pdf = input_pdf.resolve()
    output_pdf = (output_pdf or input_pdf).resolve()
    page_index, page_height, text_bottom, blank = _last_text_bottom_from_top(input_pdf)

    result: dict[str, Any] = {
        "trimmed": False,
        "pages": page_index + 1,
        "last_page_height_before": page_height,
        "last_page_height_after": page_height,
        "last_page_blank_before": blank,
    }
    if blank < min_blank_pt:
        if output_pdf != input_pdf:
            output_pdf.write_bytes(input_pdf.read_bytes())
        return result

    new_height = min(page_height, text_bottom + bottom_margin_pt)
    crop_from_bottom = page_height - new_height
    if crop_from_bottom <= 0:
        if output_pdf != input_pdf:
            output_pdf.write_bytes(input_pdf.read_bytes())
        return result

    reader = PdfReader(str(input_pdf))
    writer = PdfWriter()
    for idx, page in enumerate(reader.pages):
        if idx == page_index:
            width = float(page.mediabox.width)
            top = float(page.mediabox.top)
            bottom = top - new_height
            new_box = RectangleObject([0, bottom, width, top])
            page.mediabox = new_box
            page.cropbox = new_box
        writer.add_page(page)

    if output_pdf == input_pdf:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp_path = Path(tmp.name)
            writer.write(tmp)
        tmp_path.replace(input_pdf)
    else:
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        with output_pdf.open("wb") as fh:
            writer.write(fh)

    result.update(
        {
            "trimmed": True,
            "last_page_height_after": new_height,
            "last_page_blank_after": bottom_margin_pt,
            "cropped_from_bottom": crop_from_bottom,
        }
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trim bottom whitespace from the final PDF page without changing layout.")
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("output_pdf", type=Path, nargs="?")
    parser.add_argument("--bottom-margin-pt", type=float, default=22.0)
    parser.add_argument("--min-blank-pt", type=float, default=36.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = trim_pdf_tail_whitespace(
        args.input_pdf,
        args.output_pdf,
        bottom_margin_pt=args.bottom_margin_pt,
        min_blank_pt=args.min_blank_pt,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
