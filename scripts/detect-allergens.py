#!/usr/bin/env python3
"""Augment extracted labels with allergen flags by sampling icon-slot pixels.

The source PDFs render allergen icons at fixed slot positions inside each cell:
  origin: 4.69mm × 41.61mm from cell top-left
  each slot: 5.97mm × 5.97mm
  5 slots horizontally → gluten / milk / egg / peanut / soy

Empty slot → white background. Filled slot → grey icon (#7B7676 background).
We render each PDF page to an image and sample each slot's centre; if average
brightness is below the threshold, the allergen is present.

Inputs:
  data/extracted/_all.json   (produced by extract-pdf-labels.py)
Output:
  data/extracted/_all.json   (rewritten in place with allergen fields)
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC_PDFS = ROOT / "data" / "New Etiquetas both sides"
ALL_JSON = ROOT / "data" / "extracted" / "_all.json"

DPI = 200
MM_TO_PX = DPI / 25.4  # 7.874

# Layout constants — sampled from reference-pdf/Plano etiquetas (easy).pdf.
# Match the project's pixel-fidelity contract in CLAUDE.md.
CELL_LEFTS_MM = [20.08, 109.37]                # col 0, col 1
CELL_TOPS_MM = [27.04, 89.27, 151.50, 213.73]  # rows 0..3
ICON_STRIP_X_MM = 4.69      # offset inside cell
ICON_STRIP_Y_MM = 41.61
ICON_SIZE_MM = 5.97         # one slot = 5.97 × 5.97 mm

ALLERGEN_KEYS = ["gluten", "milk", "egg", "peanut", "soy"]

# Threshold tuned against #7B7676 (~123 brightness) vs white background.
DARKNESS_THRESHOLD = 200
SAMPLE_RADIUS_PX = 8        # 17×17 window around slot centre


def render_page(pdf_path: Path, page_no: int) -> Image.Image:
    """Render one page as a grayscale PIL image at DPI."""
    result = subprocess.run(
        ["pdftoppm", "-r", str(DPI), "-f", str(page_no), "-l", str(page_no),
         "-png", str(pdf_path)],
        capture_output=True, check=True,
    )
    return Image.open(io.BytesIO(result.stdout)).convert("L")


def detect_for_cell(img: Image.Image, row_idx: int, col_idx: int) -> dict[str, str]:
    """Sample 5 slots in the cell. Return {allergen: 'x' or ''}."""
    cell_left_mm = CELL_LEFTS_MM[col_idx]
    cell_top_mm = CELL_TOPS_MM[row_idx]
    strip_x_mm = cell_left_mm + ICON_STRIP_X_MM
    strip_y_mm = cell_top_mm + ICON_STRIP_Y_MM

    out: dict[str, str] = {}
    for slot, key in enumerate(ALLERGEN_KEYS):
        cx_mm = strip_x_mm + (slot + 0.5) * ICON_SIZE_MM
        cy_mm = strip_y_mm + 0.5 * ICON_SIZE_MM
        px = int(cx_mm * MM_TO_PX)
        py = int(cy_mm * MM_TO_PX)
        r = SAMPLE_RADIUS_PX
        region = img.crop((px - r, py - r, px + r, py + r))
        pixels = list(region.getdata())
        avg = sum(pixels) / len(pixels)
        out[key] = "x" if avg < DARKNESS_THRESHOLD else ""
    return out


def main() -> int:
    if not ALL_JSON.exists():
        print(f"Missing {ALL_JSON}. Run extract-pdf-labels.py first.", file=sys.stderr)
        return 1
    labels = json.loads(ALL_JSON.read_text())
    print(f"Loaded {len(labels)} labels")

    # Cache rendered images per (pdf_name, page_no) — avoid re-rendering.
    page_cache: dict[tuple[str, int], Image.Image] = {}

    augmented = 0
    for lab in labels:
        pdf_name = lab["source_pdf"]
        page_no = lab["page"]
        grid = lab["grid"]  # "row,col"
        ri, ci = (int(x) for x in grid.split(","))
        if not (0 <= ri < 4 and 0 <= ci < 2):
            continue  # safety

        key = (pdf_name, page_no)
        if key not in page_cache:
            pdf_path = SRC_PDFS / pdf_name
            if not pdf_path.exists():
                print(f"  skip {pdf_name}: not found", file=sys.stderr)
                lab.update({a: "" for a in ALLERGEN_KEYS})
                continue
            page_cache[key] = render_page(pdf_path, page_no)
            # Bound cache to avoid memory blow-up over 38 PDFs
            if len(page_cache) > 4:
                # Evict oldest
                oldest_key = next(iter(page_cache))
                if oldest_key != key:
                    del page_cache[oldest_key]

        flags = detect_for_cell(page_cache[key], ri, ci)
        lab.update(flags)
        augmented += 1

    print(f"Augmented {augmented} labels with allergen flags")
    ALL_JSON.write_text(json.dumps(labels, ensure_ascii=False, indent=2))
    print(f"Rewrote: {ALL_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
