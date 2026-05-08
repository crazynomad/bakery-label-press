# Usage guide — bakery labels

This tool turns the products in your Google Sheet into a print-ready PDF (A4, 8 labels per sheet, with crop marks for cutting). Edit the Sheet, click one button, and ~2 minutes later the PDF appears in Drive.

## 1. Editing the data

Open the Sheet → tab **`real_data`**. One row per product. Columns:

| Column | What to type | Example |
|---|---|---|
| `name_fr` | Product name in French. Printed in **UPPERCASE** automatically — type it however you like. | `cake au citron` |
| `description_pt` | Short description in Portuguese. Printed in italic, smaller. | `bolo de citrinos` |
| `gluten`, `milk`, `egg`, `peanut`, `soy` | Tick if the product contains the allergen. The corresponding small icon prints on the label. | ☑ ☑ ☑ ☐ ☐ |
| `price` | Number with **a dot** as decimal separator (`4.20`, not `4,20`). Will be printed as `4,20€`. | `4.20` |
| `active` | Tick to include this row in the next PDF. Untick to keep the row but skip it. | ☑ |

To add a new product, just type into the next empty row — the column rules apply automatically.

## 2. Line breaks

### Forced line breaks (recommended for titles)

Inside any cell, press **Alt + Enter** (on Mac: **Option + Enter**) to insert a line break.

```
GATEAU BASQUE       ← line 1
À LA PART           ← line 2 (forced)
```

This works in both `name_fr` and `description_pt`.

### Automatic wrapping

Long titles wrap automatically when they don't fit on one line. **Keep titles to 2 wrapped lines maximum** — anything longer (roughly 27 characters or more without a forced break) wraps to 3 lines and overlaps the description below. If your title is very long, insert your own Alt+Enter at a clean break point.

| Length | Behaviour |
|---|---|
| up to ~14 characters | One line |
| 15–26 characters | Wraps to 2 lines automatically |
| 27+ characters without forced break | Wraps to 3 lines → visual overlap (don't print) |

## 3. Generating the PDF

1. In the Sheet, menu bar → **🥖 Lully** → **Generate labels (PDF)**
2. The `release_history` tab gets a new row with status `submitted`
3. Wait ~2 minutes
4. The same row updates to `success`, with a Drive link in `pdf_drive_link`
5. Click the link → your PDF is there, ready to print

The Sheet keeps a permanent record of every PDF you have ever generated, with a CSV snapshot of the exact data that produced each one. So you can always reprint a past version.

## 4. Printing

Open the PDF and print on **A4 paper, 100% scale** (no "fit to page", no margins added). The crop marks at each label's corners are guides for cutting after printing.

## 5. If something goes wrong

If the new `release_history` row shows status `failed`, look at the `notes` column for the error.

| Notes shows... | Likely cause | Fix |
|---|---|---|
| `Missing name_fr` | An active row has no product name | Fill in `name_fr` or untick `active` for that row |
| `No active rows` | Nothing is ticked | Tick at least one `active` checkbox |
| `invalid_grant` / `Token expired` | The Google connection expired | Ask your technical contact to refresh the OAuth token |
| `Tab 'real_data' is empty` | The tab has been emptied or renamed | Don't rename `real_data`; keep at least the header row |

If you don't recognise the error, send the `notes` text and the `request_id` to your technical contact.

## 6. Tips

- **Tick allergens carefully** — they print as small icons that customers rely on. A missed tick means a customer can't tell at a glance.
- **Untick `active`** for products you're not selling today instead of deleting the row — keeps your full catalogue ready for next time.
- **Don't delete rows from `release_history`** — it's your audit log of every label batch ever printed.
- **Don't rename the tabs** — `real_data`, `sample`, and `release_history` are the names the system looks for.
