#!/usr/bin/env python3
"""Extract label catalog from the client's "both sides" PDF dump.

Strategy: use `pdftotext -bbox` to get word-level positions, then bucket each
word into the (col, row) cell of the 2×4 grid it falls in. Back-side pages
(title-only, no €) are skipped. The output is per-PDF + a consolidated JSON.

Outputs:
  data/extracted/<pdf-basename>.json   per-PDF dump
  data/extracted/_all.json             concatenated raw extraction
  data/extracted/_parse_log.txt        per-page parse log
"""
from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "New Etiquetas both sides"
OUT = ROOT / "data" / "extracted"

PRICE_TOKEN_RE = re.compile(r"\d{1,3}[,.]\d{2}€|\d{1,3}€")  # "4,20€" or "35€"
# Looser pattern for row-clustering: any word containing € (covers fragmented
# InDesign exports where '5,90€' is split into '5,90' + '€').
PRICE_ROW_MARKER_RE = re.compile(r"€")
LINE_DY_TOLERANCE = 6.0  # pts — words within this Δy are same visual line
                          # (letterspaced titles can have small baseline drift)


@dataclass
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class Label:
    name_fr: str
    description_pt: str
    price_raw: str
    source_pdf: str
    source_date: str
    page: int
    grid: str  # "row,col" e.g. "1,0" for first row left column


# ---------- filename → date ----------

_MONTH_NAMES = {
    "jan": 1, "january": 1, "janeiro": 1,
    "feb": 2, "february": 2, "fev": 2, "fevereiro": 2,
    "mar": 3, "march": 3, "marco": 3, "março": 3,
    "apr": 4, "april": 4, "abr": 4, "abril": 4,
    "may": 5, "mai": 5, "maio": 5,
    "jun": 6, "june": 6, "junho": 6,
    "jul": 7, "july": 7, "julho": 7,
    "aug": 8, "august": 8, "ago": 8, "agosto": 8,
    "sep": 9, "september": 9, "set": 9, "setembro": 9,
    "oct": 10, "october": 10, "out": 10, "outubro": 10,
    "nov": 11, "november": 11, "novembro": 11,
    "dec": 12, "december": 12, "dez": 12, "dezembro": 12,
}


def parse_filename_date(name: str) -> str:
    lower = name.lower()
    if "pacques" in lower or "pâques" in lower:
        return "2025-04-20"
    if "st val" in lower:
        return "2025-02-14"
    for mname, mnum in _MONTH_NAMES.items():
        m = re.search(rf"\b(\d{{1,2}})\s+{mname}\b\s+(\d{{2,4}})", lower)
        if m:
            d = int(m.group(1)); y = int(m.group(2))
            if y < 100: y += 2000
            return f"{y:04d}-{mnum:02d}-{d:02d}"
    for mname, mnum in _MONTH_NAMES.items():
        m = re.search(rf"\b{mname}\b\s+(\d{{2,4}})", lower)
        if m:
            y = int(m.group(1))
            if y < 100: y += 2000
            return f"{y:04d}-{mnum:02d}-01"
    m = re.search(r"\b(\d{1,2})[-:](\d{1,2})[-:](\d{2,4})\b", name)
    if m:
        d = int(m.group(1)); mo = int(m.group(2)); y = int(m.group(3))
        if y < 100: y += 2000
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"
    return ""


# ---------- bbox parsing ----------

def pdftotext_bbox(pdf_path: Path) -> str:
    return subprocess.run(
        ["pdftotext", "-bbox", str(pdf_path), "-"],
        capture_output=True, text=True, check=True,
    ).stdout


def parse_bbox(xml_text: str) -> list[tuple[float, float, list[Word]]]:
    """Return list of (page_width, page_height, [Word, ...]) per page."""
    pages = []
    page_re = re.compile(
        r'<page\s+width="([\d.]+)"\s+height="([\d.]+)">(.*?)</page>',
        re.DOTALL,
    )
    word_re = re.compile(
        r'<word\s+xMin="([\d.]+)"\s+yMin="([\d.]+)"\s+'
        r'xMax="([\d.]+)"\s+yMax="([\d.]+)">([^<]*)</word>'
    )
    for pm in page_re.finditer(xml_text):
        w_page = float(pm.group(1)); h_page = float(pm.group(2))
        words = []
        for wm in word_re.finditer(pm.group(3)):
            x0 = float(wm.group(1)); y0 = float(wm.group(2))
            x1 = float(wm.group(3)); y1 = float(wm.group(4))
            text = html.unescape(wm.group(5))
            if text.strip():
                words.append(Word(text=text, x0=x0, y0=y0, x1=x1, y1=y1))
        pages.append((w_page, h_page, _merge_split_prices(words)))
    return pages


def _merge_split_prices(words: list[Word]) -> list[Word]:
    """InDesign exports often split a price like '0,35€' into three words:
    '0', ',', '35€'. Or '5,90€' into '5,90' + '€'. Reassemble.

    Strategy: for each word containing '€' or matching a partial digit pattern,
    look at nearby words to the LEFT on the same y and merge until we have a
    complete price token.
    """
    if not words:
        return words
    swords = sorted(words, key=lambda w: (w.y0, w.x0))
    # First pass: merge '€' words with adjacent number/comma fragments to the left
    merged: list[Word] = []
    i = 0
    while i < len(swords):
        w = swords[i]
        if w.text == "€" and merged and _same_line(merged[-1], w) and _adjacent_x(merged[-1], w):
            # Merge prior word + €
            prev = merged.pop()
            merged.append(Word(
                text=prev.text + "€",
                x0=prev.x0, y0=prev.y0,
                x1=w.x1, y1=max(prev.y1, w.y1),
            ))
        elif re.match(r"^\d{1,3}$", w.text) and i + 2 < len(swords) and \
                swords[i+1].text == "," and re.match(r"^\d{2}€?$", swords[i+2].text) and \
                _same_line(w, swords[i+1]) and _same_line(w, swords[i+2]):
            # '0' + ',' + '35€' → '0,35€'
            merged.append(Word(
                text=w.text + swords[i+1].text + swords[i+2].text + ("" if "€" in swords[i+2].text else ""),
                x0=w.x0, y0=w.y0, x1=swords[i+2].x1, y1=max(w.y1, swords[i+2].y1),
            ))
            i += 3
            continue
        else:
            merged.append(w)
        i += 1
    return merged


def _same_line(a: Word, b: Word) -> bool:
    return abs(a.y0 - b.y0) <= 4.0


def _adjacent_x(a: Word, b: Word) -> bool:
    """Within ~30pt — same visual price group."""
    return 0 <= (b.x0 - a.x1) <= 30


# ---------- per-page cell assembly ----------

def _cluster_1d(values: list[float], gap: float) -> list[list[float]]:
    """Sort values then split into clusters whenever the gap between adjacent
    values exceeds `gap`."""
    if not values:
        return []
    sv = sorted(values)
    clusters = [[sv[0]]]
    for v in sv[1:]:
        if v - clusters[-1][-1] > gap:
            clusters.append([v])
        else:
            clusters[-1].append(v)
    return clusters


def words_to_lines(words: list[Word]) -> list[str]:
    """Group words into lines by y-clustering, then read each line left-to-right."""
    if not words:
        return []
    # Sort by y, then x. Build lines by clustering close-y words.
    swords = sorted(words, key=lambda w: (w.y0, w.x0))
    lines: list[list[Word]] = []
    for w in swords:
        if lines and abs(w.y0 - lines[-1][0].y0) <= LINE_DY_TOLERANCE:
            lines[-1].append(w)
        else:
            lines.append([w])
    out = []
    for line in lines:
        line.sort(key=lambda w: w.x0)
        out.append(" ".join(w.text for w in line))
    return out


def extract_cells_from_page(words: list[Word], page_w: float, page_h: float) -> list[tuple[str, int, int]]:
    """Return list of (cell_text, row_idx, col_idx) for cells found on this page.

    Approach:
      1. Find price words (containing €).
      2. Cluster their y-positions into row bands.
      3. Cluster their x-positions into col bands (expect 2 per row,
         but compound prices like "3,25€ / 6,50€" may appear as 2 prices in same cell).
      4. For each (row_band, col_band) bucket, gather all words whose center
         falls within the cell's bounding box. Assemble into lines.
    """
    price_words = [w for w in words if PRICE_ROW_MARKER_RE.search(w.text)]
    if not price_words:
        return []

    # Row clustering: 4 rows expected, with row-gaps ~150pt typically.
    row_clusters = _cluster_1d([w.y0 for w in price_words], gap=40.0)
    if not row_clusters:
        return []
    row_ys = [sum(c) / len(c) for c in row_clusters]  # avg y per row

    # Column boundary: page midpoint is robust for this grid.
    col_split_x = page_w / 2

    # Cell vertical bounds: top edge = midpoint between this row and the
    # previous row's prices (or page top for row 0); bottom edge = row's price y + small.
    cell_top: list[float] = []
    cell_bot: list[float] = []
    for i, y in enumerate(row_ys):
        if i == 0:
            cell_top.append(0.0)
        else:
            cell_top.append((row_ys[i - 1] + y) / 2)
        cell_bot.append(y + 25.0)  # include price line itself

    cells: list[tuple[str, int, int]] = []
    for ri, (top, bot) in enumerate(zip(cell_top, cell_bot)):
        for ci in (0, 1):
            x_lo = 0.0 if ci == 0 else col_split_x
            x_hi = col_split_x if ci == 0 else page_w
            cell_words = [
                w for w in words
                if top <= (w.y0 + w.y1) / 2 <= bot
                and x_lo <= (w.x0 + w.x1) / 2 <= x_hi
            ]
            if not cell_words:
                continue
            lines = words_to_lines(cell_words)
            cell_text = "\n".join(lines)
            cells.append((cell_text, ri, ci))
    return cells


# ---------- cell text → Label ----------

def parse_cell_text(text: str, pdf_name: str, page_no: int, ri: int, ci: int) -> Label | None:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return None
    # Price line — last line containing € (caught even when price is fragmented
    # across multiple words like '5,90' + '€').
    price_line_idx = None
    for i in range(len(lines) - 1, -1, -1):
        if "€" in lines[i]:
            price_line_idx = i
            break
    if price_line_idx is None:
        return None
    price_line = lines[price_line_idx]
    # Try to reconstruct full prices from possibly-fragmented tokens like
    # '0 , 35€' → '0,35€', or '5,90 €' → '5,90€'.
    reconstructed = re.sub(r"(\d{1,3})\s*[,.]\s*(\d{2})\s*€", r"\1,\2€", price_line)
    reconstructed = re.sub(r"(\d{1,3})\s*€", r"\1€", reconstructed)
    price_tokens = PRICE_TOKEN_RE.findall(reconstructed)
    if not price_tokens:
        return None  # had € but no recognisable price — skip
    if "/" in price_line and "€" in price_line:
        # Keep "/ Kg"-style annotations
        price_raw = re.sub(r"\s+", " ", reconstructed).strip()
    elif len(price_tokens) > 1:
        price_raw = " / ".join(price_tokens)
    else:
        price_raw = price_tokens[0]

    body = lines[:price_line_idx]
    if not body:
        # Cell is just a price — happens for placeholder "0,00€" cells.
        return None

    # Title: leading uppercase lines (letter-spaced glyphs from InDesign show
    # up as words like "AT", "PA", "RT" etc. — they're all-caps fragments).
    title_lines: list[str] = []
    desc_lines: list[str] = []
    in_title = True
    for ln in body:
        if in_title and _is_title_line(ln):
            title_lines.append(ln)
        else:
            in_title = False
            desc_lines.append(ln)

    name_fr = "\n".join(_collapse_glyphs(t) for t in title_lines).strip()
    # Preserve per-visual-line breaks in descriptions — the source PDFs use
    # explicit Alt+Enter line breaks so the text fits within the cell, and the
    # renderer's `white-space: pre-line` (templates/labels/labels.css) respects
    # them. Collapsing to one line causes auto-wrap overflow into the allergen
    # strip on long descriptions.
    desc_normalized = [re.sub(r"\s+", " ", ln).strip() for ln in desc_lines]
    description_pt = "\n".join(ln for ln in desc_normalized if ln)
    # Strip pure-placeholder descriptions but keep the label.
    if re.fullmatch(r"[xX\s\n]+", description_pt):
        description_pt = ""

    if not name_fr:
        return None
    if re.fullmatch(r"X{2,}", name_fr):
        return None
    # Drop placeholder "0,00€" rows — they're template fillers
    if price_raw.replace(" ", "") in ("0,00€", "0.00€"):
        return None

    return Label(
        name_fr=name_fr,
        description_pt=description_pt,
        price_raw=price_raw,
        source_pdf=pdf_name,
        source_date=parse_filename_date(pdf_name),
        page=page_no,
        grid=f"{ri},{ci}",
    )


def _is_title_line(s: str) -> bool:
    """Title lines are either ALL-CAPS or letter-spaced (signature: many short
    tokens). The letter-spaced check catches mixed-case titles like
    'p e t i t B AT T I S TA' which would otherwise fail an upper-ratio test."""
    letters = [c for c in s if c.isalpha()]
    if not letters:
        # Pure numeric/fraction lines like "1/8 - 1/4" or "- GLUTEN FREE -" stub
        return bool(re.match(r"^[\d/\-\s+*€,.()]+$", s))
    upper = sum(1 for c in letters if c.isupper())
    if upper / len(letters) >= 0.85:
        return True
    # Letter-spaced signature: ≥60% of space-separated tokens are 1-2 chars.
    tokens = s.split()
    if len(tokens) >= 4:
        short = sum(1 for t in tokens if len(t) <= 2)
        if short / len(tokens) >= 0.6:
            return True
    return False


def _collapse_glyphs(line: str) -> str:
    """InDesign letter-spaced titles export as separate glyph words like
    'G AT E A U B A S Q U E'. Reassemble into 'GATEAU BASQUE' using the
    heuristic that the source has word-spaces ≈ 2-3× letter-spaces, but in
    pdftotext output BOTH render as single spaces — so we instead use a
    word-list of common French/Portuguese tokens to find natural breaks.

    Heuristic that doesn't need a dictionary: drop all spaces (giving
    'GATEAUBASQUE'), then split before each capital-letter onset following a
    sequence of ≥3 letters. Imperfect but readable; humans review.
    """
    if not line:
        return ""
    tokens = line.split()
    # Letter-spaced detection: ≥60% of tokens are length 1-2 → glue glyphs.
    short = sum(1 for t in tokens if len(t) <= 2)
    is_letter_spaced = len(tokens) >= 4 and short / len(tokens) >= 0.6
    if not is_letter_spaced and any(c.islower() for c in line):
        return re.sub(r"\s+", " ", line).strip()
    # Drop all whitespace
    joined = re.sub(r"\s+", "", line)
    # If too short to need splitting, return as-is
    if len(joined) <= 6:
        return joined
    # Try a known-word split: insert a space before any of these common bakery
    # words when they appear inside a longer compound.
    KEYWORDS = [
        "BASQUE", "ENTIER", "CHOCOLAT", "CITRON", "BORDELAIS", "PEQUENO",
        "ENTIERE", "GRAND", "GRANDE", "AMANDES", "AMANDE",
        "FRAMBOESA", "MARACUJA", "MARACUJÁ", "MORANGO", "CHOC",
        "CLASSIC", "GRAINES", "TRADITION", "AUX", "ARRA",
        "AVELÃ", "AVELA", "MIRTILO", "CAFE", "CAFÉ", "CARAMEL",
        "VIENN", "NATAL", "PISTACHIO", "PISTACHE", "PARIS", "BREST",
        "BLANC", "NEGRO", "ROYAL", "ROYALE", "BAGUETTE", "BRIOCHE",
        "CROISSANT", "CRUFFIN", "GALETTE", "MACARONS", "FINANCIER",
        "FRAISIER", "FLAN", "FOUGASSE", "METEIL", "CENTEIO",
        "ECLAIR", "ÉCLAIR", "MOUSSE", "DUNAS", "SAHARA",
        "VEGAN", "VEGETARIEN", "VEGETARIENNE",
        "MARA", "COCO", "YUZU", "MIOSOTIS", "PURPLE", "HAZE",
        "ROIS", "TIRAMISU", "PAVLOVA", "CHOUQUETTES", "MISTO",
        "VIERGE", "TANGO", "DOME", "DÔME",
        "PAILLARD", "FACHEUX", "MONTPENSIER", "FICELLE", "SPELTA", "EPIS",
        "BATTISTA", "BATISTA", "DOUBLE", "FRESCA", "BERINGELA",
        "LULLY", "FLUTE", "BORDELAIS", "FRAMBOESA",
        "POMME", "COURONNE", "BATTISTA", "BATISTA",
        "PART", "ROIS", "SUISSE", "KOUIGN", "AMANN", "AMAN", "TORSADE",
        "TOURBILLON", "CROOKIE", "BEURRE", "CARAMELO",
    ]
    # Sort by length descending so longer keywords win.
    keys = sorted(set(KEYWORDS), key=len, reverse=True)
    result = joined
    for kw in keys:
        # ≥4 chars only — short articles (DE, LA, AU) cause false matches
        # inside longer words like AMANDES.
        if len(kw) < 4:
            continue
        # Insert space before the keyword if it's preceded by ≥2 letters and isn't at start
        # Use a non-overlapping replace, repeatedly.
        pattern = re.compile(
            rf"(?<=[A-Za-zÀ-ÿ]{{2}}){re.escape(kw)}(?=[A-Za-zÀ-ÿ\d\s]|$)",
            re.IGNORECASE,
        )
        result = pattern.sub(lambda m: f" {m.group(0)}", result)
    return re.sub(r"\s+", " ", result).strip()


# ---------- driver ----------

def extract_one(pdf_path: Path) -> tuple[list[Label], list[str]]:
    log: list[str] = []
    xml = pdftotext_bbox(pdf_path)
    pages = parse_bbox(xml)
    labels: list[Label] = []
    for i, (pw, ph, words) in enumerate(pages, start=1):
        has_euro = any("€" in w.text for w in words)
        if not has_euro:
            log.append(f"  page {i}: skipped (no € — back side)")
            continue
        cells = extract_cells_from_page(words, pw, ph)
        page_labels = 0
        for cell_text, ri, ci in cells:
            lab = parse_cell_text(cell_text, pdf_path.name, i, ri, ci)
            if lab:
                labels.append(lab)
                page_labels += 1
        log.append(f"  page {i}: {page_labels} labels")
    return labels, log


def main() -> int:
    if not SRC.is_dir():
        print(f"Source directory not found: {SRC}", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()

    all_labels: list[dict] = []
    log_lines: list[str] = []
    pdfs = sorted(SRC.glob("*.pdf"))
    print(f"Found {len(pdfs)} PDFs")
    for pdf in pdfs:
        labels, plog = extract_one(pdf)
        log_lines.append(f"\n=== {pdf.name} (date={parse_filename_date(pdf.name) or '?'}) ===")
        log_lines.extend(plog)
        log_lines.append(f"  total: {len(labels)} labels")
        per_pdf = OUT / f"{pdf.stem}.json"
        per_pdf.write_text(json.dumps([asdict(l) for l in labels], ensure_ascii=False, indent=2))
        all_labels.extend(asdict(l) for l in labels)
        print(f"  {pdf.name}: {len(labels)} labels")

    (OUT / "_all.json").write_text(json.dumps(all_labels, ensure_ascii=False, indent=2))
    (OUT / "_parse_log.txt").write_text("\n".join(log_lines))
    print(f"\nTotal: {len(all_labels)} labels across {len(pdfs)} PDFs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
