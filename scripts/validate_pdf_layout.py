from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pypdf import PdfReader


EXPECTED_WIDTH_PT = 612.0
EXPECTED_HEIGHT_PT = 792.0
TOLERANCE_PT = 2.0


def _close(actual: float, expected: float, tolerance: float = TOLERANCE_PT) -> bool:
    return abs(actual - expected) <= tolerance


def validate_report_pdf_layout(
    pdf_path: Path,
    *,
    trim_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate the approved ETF report PDF layout contract.

    The contract is intentionally narrow: Chrome Letter pagination is the approved
    layout; only the final page's bottom page box may be shortened to remove tail
    whitespace. This validator rejects screenshot PDFs, single long pages, A4 pages,
    and accidental layout rewrites.
    """

    pdf_path = pdf_path.resolve()
    reader = PdfReader(str(pdf_path))
    pages = list(reader.pages)
    page_count = len(pages)
    if page_count < 2:
        raise RuntimeError(
            f"Layout violation: expected approved multi-page Letter PDF, got {page_count} page(s)."
        )

    total_text = 0
    page_sizes: list[dict[str, float]] = []
    for idx, page in enumerate(pages):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        page_sizes.append({"page": idx + 1, "width": width, "height": height})
        text_len = len(page.extract_text() or "")
        total_text += text_len

        if not _close(width, EXPECTED_WIDTH_PT):
            raise RuntimeError(
                f"Layout violation: page {idx + 1} width is {width:.1f} pt, expected Letter width {EXPECTED_WIDTH_PT:.0f} pt."
            )
        if idx < page_count - 1:
            if not _close(height, EXPECTED_HEIGHT_PT):
                raise RuntimeError(
                    f"Layout violation: page {idx + 1} height is {height:.1f} pt, expected Letter height {EXPECTED_HEIGHT_PT:.0f} pt."
                )
        else:
            if height > EXPECTED_HEIGHT_PT + TOLERANCE_PT:
                raise RuntimeError(
                    f"Layout violation: final page height is {height:.1f} pt, larger than Letter height."
                )
            if height < 180:
                raise RuntimeError(
                    f"Layout violation: final page was cropped to {height:.1f} pt, which risks clipping report content."
                )
            if text_len < 50:
                raise RuntimeError(
                    "Layout violation: final page has too little extractable text; cropping or export may be wrong."
                )

    if total_text < 1000:
        raise RuntimeError(
            "Layout violation: PDF has too little extractable text. Do not use screenshot/image PDF export."
        )

    if trim_result:
        blank_before = float(trim_result.get("last_page_blank_before") or 0)
        was_trimmed = bool(trim_result.get("trimmed"))
        if blank_before > 120 and not was_trimmed:
            raise RuntimeError(
                f"Layout violation: final page has {blank_before:.1f} pt bottom whitespace and was not trimmed."
            )

    return {
        "layout_ok": True,
        "pages": page_count,
        "total_text": total_text,
        "page_sizes": page_sizes,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the approved Southern ETF report PDF layout.")
    parser.add_argument("pdf", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(json.dumps(validate_report_pdf_layout(args.pdf), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
