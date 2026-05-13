#!/usr/bin/env python3
"""Dedupe extracted labels, resolve price conflicts, assign categories.

Inputs:
    data/extracted/_all.json    (produced by extract-pdf-labels.py)

Outputs:
    data/master-catalog.csv     master CSV ready to paste into the Sheet
    data/master-conflicts.md    human-readable report: dropped duplicates,
                                  price conflicts, items needing review
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "data" / "extracted" / "_all.json"
OUT_CSV = ROOT / "data" / "master-catalog.csv"
OUT_REPORT = ROOT / "data" / "master-conflicts.md"


# ---------- categorization ----------

# Per-filename hint: what category the PDF is "about" by default. Items not
# overridden by keyword rules fall back to this.
FILENAME_CATEGORY = [
    # (substring, category) — first match wins
    ("pão",                "Breads"),
    ("(Vienn)",            "Viennoiseries"),
    ("CRUFFIN vierge",     "Viennoiseries"),
    ("CHOUQUETTES",        "Viennoiseries"),  # chouquettes = choux pastries, viennoiserie-ish
    ("PAVLOVA",            "Desserts"),
    ("COCO MARA",          "Desserts"),
    ("TIRAMISU",           "Desserts"),
    ("Mousse Choc",        "Desserts"),
    ("Paris Brest",        "Desserts"),
    ("Purple Haze",        "Desserts"),
    ("FRAMB MARA",         "Desserts"),
    ("PASTELARIA",         "Desserts"),
    ("pastries",           "Desserts"),
    ("snacks",             "Snacks"),
    ("Macarons",           "Desserts"),
    ("FRUTOS Secos",       "Dry Goods"),
    ("Special Nov",        "Gateaux de voyage"),  # cake/financier-style on the easy template
    ("(easy)",             "Gateaux de voyage"),
    ("(festas)",           "Desserts"),   # Galette des Rois, Tartelete do Abade, etc.
    ("Pacques",            "Desserts"),
    ("St Val",             "Desserts"),
    ("New Prices",         None),  # fall through to keyword rules
    ("2 Mai 2025",         None),
]

# Per-item keyword override. If the product NAME contains any of these tokens
# (case-insensitive), force this category regardless of filename.
NAME_CATEGORY_OVERRIDES = [
    # Bread keywords (Breads category)
    ("Breads", [
        "PAILLARD", "BAGUETTE", "FICELLE", "FOUGASSE", "METEIL", "CENTEIO",
        "SPELTA", "BATTISTA", "BATISTA", "BRIOCHE", "FLUTE", "MONTPENSIER",
        "FACHEUX", "COURONNE", "FOLHADO",
    ]),
    # Viennoiserie keywords
    ("Viennoiseries", [
        "CROISSANT", "CRUFFIN", "KOUIGN", "CHOUQUETTES", "TORSADE",
        "TOURBILLON", "CROOKIE", "PAIN AU CHOC", "PAINAU CHOC", "PAINAU",
        "PAIN SUISSE", "CRESTO", "PAIN AU CHOCOLAT",
    ]),
    # Gateaux de voyage (travel cakes — financier, cake, brownie, cookie, cannelé)
    ("Gateaux de voyage", [
        "FINANCIER", "CAKE", "BROWNIE", "COOKIE", "CANNELÉ", "CANNELE",
        "GATEAU BASQUE", "GATEAUBASQUE",
    ]),
    # Snacks keywords
    ("Snacks", [
        "QUICHE", "BAGUETTE SHITAKE", "SHITAKE", "FIAMBRE", "MOZARELLA",
        "BERINGELA", "SANDES", "TARTE CONVIVIO", "CONVIVIO", "CROISSANT MISTO",
        "TYRELL",
    ]),
    # Drinks (probably none in current data)
    ("Drinks", ["JUS", "CAFE FROID", "JUICE"]),
    # Dry goods
    ("Dry Goods", ["FRUTOS SECOS", "NOZ PECAN", "AVELÃ CRISTAL"]),
    # Desserts (catch-all for pastry-counter items)
    ("Desserts", [
        "DUNAS", "MONT BLANC", "FLAN", "FRAISIER", "TARTE", "PARIS-BREST",
        "PARIS BREST", "MOUSSE CHOC", "DÔME", "DOME CHOCOLAT", "TIRAMISU",
        "PAVLOVA", "MACARONS", "ÉCLAIR", "ECLAIR", "PURPLE HAZE", "GALETTE",
        "ROIS", "TARTELETE", "ABADE", "FRAMBOESA", "MARACUJÁ", "MARACUJA",
        "MORANGO", "CHOCOLAT-CHOCOLAT", "BOLO DO DIA", "BOLAS DE NATAL",
        "ORIGAMI", "PEROLAS", "MIOSOTIS",
    ]),
]


def assign_category(name_fr: str, source_pdf: str) -> str:
    """Return one of 8 categories. Order: name keyword override > filename hint > 'Desserts' default."""
    name_upper = name_fr.upper().replace("\n", " ")
    # Strip diacritics-light for matching
    name_norm = re.sub(r"\s+", " ", name_upper).strip()

    for cat, keywords in NAME_CATEGORY_OVERRIDES:
        for kw in keywords:
            if kw in name_norm:
                return cat

    for sub, cat in FILENAME_CATEGORY:
        if sub.lower() in source_pdf.lower() and cat is not None:
            return cat

    return "Desserts"


# ---------- seasonal detection ----------

SEASONAL_PDFS = {
    "Plano etiquetas (festas)13-6-24.pdf",     # Galette des Rois
    "Plano etiquetas (festas) St Val 2025.pdf",
    "Pacques 2025.pdf",
}


def is_seasonal(source_pdf: str) -> bool:
    return source_pdf in SEASONAL_PDFS


# ---------- normalization ----------

def normalize_name(name: str) -> str:
    """Aggressive key for dedup. Strip ALL whitespace and punctuation so that
    glyph-collapse artefacts (`PAILLARDAUX GRAINES` vs `PAILLARD AUX GRAINES`)
    map to the same key. The original display name is kept separately."""
    s = name.upper()
    s = re.sub(r"[^A-ZÀ-ÿ0-9]+", "", s)
    return s


# ---------- main ----------

def main() -> int:
    if not INPUT.exists():
        print(f"Missing input: {INPUT}", file=sys.stderr)
        return 1
    labels = json.loads(INPUT.read_text())
    print(f"Loaded {len(labels)} labels")

    # Group by normalized name
    groups: dict[str, list[dict]] = defaultdict(list)
    for lab in labels:
        key = normalize_name(lab["name_fr"])
        if not key:
            continue
        groups[key].append(lab)

    # For each group, pick "winner" = max source_date; if tie, prefer the
    # one with the most-words name (best title break-up) then longest description.
    def sort_key(lab):
        date = lab.get("source_date") or "0000-00-00"
        name_word_count = len(re.findall(r"[A-ZÀ-ÿ]+", lab["name_fr"].upper()))
        return (date, name_word_count, len(lab.get("description_pt") or ""))

    winners: list[dict] = []
    conflicts: list[str] = []
    for key, group in sorted(groups.items()):
        group_sorted = sorted(group, key=sort_key, reverse=True)
        winner = group_sorted[0]
        winners.append(winner)
        # Find price conflicts (different price_raw seen). De-dup instance pairs.
        prices = sorted({l["price_raw"] for l in group}, key=lambda p: -len(p))
        if len(prices) > 1:
            seen_pairs = {}
            for l in group_sorted:
                key_pair = (l["source_pdf"], l["price_raw"])
                if key_pair not in seen_pairs:
                    seen_pairs[key_pair] = (l.get("source_date") or "?", l["source_pdf"], l["price_raw"])
            # Sort: known dates newest-first, unknown dates ('?') last.
            sorted_pairs = sorted(
                seen_pairs.values(),
                key=lambda t: (t[0] == "?", "" if t[0] == "?" else "999999" if not t[0] else None or t[0]),
                reverse=False,
            )
            # Trick: convert sort to newest-first by reversing known and appending unknowns.
            known = sorted([t for t in seen_pairs.values() if t[0] != "?"],
                           key=lambda t: t[0], reverse=True)
            unknown = [t for t in seen_pairs.values() if t[0] == "?"]
            instance_lines = "\n".join(
                f"    - `{pdf}` ({d}) → {pr}" for d, pdf, pr in known + unknown
            )
            conflicts.append(
                f"### {winner['name_fr'].replace(chr(10), ' / ')} — kept **{winner['price_raw']}**\n"
                f"- Seen {len(group)}× with {len(prices)} distinct prices across {len(seen_pairs)} PDFs:\n"
                f"{instance_lines}\n"
            )

    print(f"Deduped to {len(winners)} unique products")
    print(f"Price conflicts on {len(conflicts)} products")

    # Categorize & write CSV
    out_rows = []
    for w in sorted(winners, key=lambda l: l["name_fr"]):
        cat = assign_category(w["name_fr"], w["source_pdf"])
        seasonal = is_seasonal(w["source_pdf"])
        gluten, milk, egg, peanut, soy = _allergen_overrides(
            w["name_fr"], w.get("description_pt", ""),
            w.get("gluten", ""), w.get("milk", ""), w.get("egg", ""),
            w.get("peanut", ""), w.get("soy", ""),
        )
        # Boolean columns use TRUE/empty (not 'x') so the Sheet's checkbox
        # validation accepts the pasted values without a red warning.
        # build-labels.py's _truthy() accepts both 'true' and 'x', so the
        # renderer side is unaffected.
        out_rows.append({
            "name_fr":        w["name_fr"],
            "description_pt": w["description_pt"],
            "category":       cat,
            "gluten":         "TRUE" if gluten else "",
            "milk":           "TRUE" if milk else "",
            "egg":            "TRUE" if egg else "",
            "peanut":         "TRUE" if peanut else "",
            "soy":            "TRUE" if soy else "",
            "price":          _normalize_price(w["price_raw"]),
            "active":         "" if seasonal else "TRUE",
            "source_pdf":     w["source_pdf"],
            "source_date":    w.get("source_date") or "",
            "price_raw":      w["price_raw"],
        })

    # Sort by category then name for human readability
    cat_order = ["Breads", "Viennoiseries", "Gateaux de voyage", "Desserts",
                 "Snacks", "Drinks", "Dry Goods", "Brunch"]
    out_rows.sort(key=lambda r: (cat_order.index(r["category"]) if r["category"] in cat_order else 99, r["name_fr"]))

    # Write CSV
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f"Wrote: {OUT_CSV}  ({len(out_rows)} rows)")

    # Write report
    cat_counts = defaultdict(int)
    for r in out_rows:
        cat_counts[r["category"]] += 1
    report = ["# Master Catalog Extraction Report",
              "",
              f"- **Total raw labels extracted**: {len(labels)} (across 38 PDFs)",
              f"- **Unique products after dedup**: {len(out_rows)}",
              f"- **Price conflicts resolved**: {len(conflicts)} (latest-date wins)",
              "",
              "## Category breakdown",
              ""]
    for cat in cat_order:
        report.append(f"- **{cat}**: {cat_counts.get(cat, 0)}")
    report.extend([
        "",
        "## Price conflicts",
        "",
        "Items below appeared in multiple PDFs with different prices. The CSV",
        "keeps the **latest-dated** PDF's price. All historical prices are listed",
        "so the bakery can double-check.",
        "",
    ])
    report.extend(conflicts if conflicts else ["_None._"])
    report.extend([
        "",
        "## Items needing human review",
        "",
        "These names look like extraction artefacts (missing word breaks, etc.) — quick fix in the Sheet.",
        "",
    ])
    suspect = [r for r in out_rows if _looks_suspect(r["name_fr"])]
    for r in suspect:
        report.append(f"- `{r['name_fr'].replace(chr(10), ' / ')}` → {r['category']} (from `{r['source_pdf']}`)")
    if not suspect:
        report.append("_None._")

    OUT_REPORT.write_text("\n".join(report))
    print(f"Wrote: {OUT_REPORT}")
    return 0


def _allergen_overrides(name_fr: str, description: str,
                        gluten: str, milk: str, egg: str,
                        peanut: str, soy: str) -> tuple[str, str, str, str, str]:
    """Correct icon-detection false positives using name/description keywords.

    The icon detector samples fixed slot positions assuming gluten/milk/egg/
    peanut/soy order. For labels marked 'GLUTEN FREE' the icons are left-packed
    (no wheat icon, milk shifts into slot 0), so the detector reports gluten=x
    incorrectly. Same for lactose-free products.

    This pass forces the allergen empty whenever the label text indicates the
    product is free of that allergen.
    """
    text = f"{name_fr} {description}".upper().replace("\n", " ")
    if any(kw in text for kw in ("GLUTEN FREE", "GLUTENFREE", "SEM GLUTEN", "SEMGLUTEN", "SANS GLUTEN")):
        gluten = ""
    if any(kw in text for kw in ("LACTOSE FREE", "SEM LACTOSE", "SEMLACTOSE", "SANS LACTOSE", "DAIRY FREE")):
        milk = ""
    if "VEGAN" in text or "VEG\"" in text:
        # Vegan products: no milk, no egg
        milk = ""
        egg = ""
    return gluten, milk, egg, peanut, soy


def _normalize_price(price_raw: str) -> str:
    """Convert '4,20€' to '4.20'. For compound prices, keep the first."""
    if not price_raw:
        return ""
    # Take the first euro value found.
    m = re.search(r"(\d{1,3})[,.](\d{2})", price_raw)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    # "35€"-style integer prices
    m = re.search(r"(\d{1,3})€", price_raw)
    if m:
        return f"{m.group(1)}.00"
    return ""


def _looks_suspect(name: str) -> bool:
    """Heuristic: name has uppercase-uppercase-lowercase patterns suggesting a
    glued boundary (e.g. 'KOUIGNAMAN', 'PAINAU'). We trigger on any run of
    ≥7 caps in a row inside a name (rare in real French/Portuguese)."""
    flat = name.replace("\n", " ").replace(" ", "")
    # Long uppercase clump heuristic
    if re.search(r"[A-Z]{8,}", flat):
        return True
    # Single-word lowercase trailing artefact
    return False


if __name__ == "__main__":
    sys.exit(main())
