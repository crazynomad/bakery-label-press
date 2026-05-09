# Backlog

Items deferred pending customer feedback or external information. Don't
start work on these without first checking the listed trigger condition.

---

## Split Sheet to isolate Apps Script secrets from staff editors

**Status**: deferred — waiting for customer to confirm 2-Sheet UX is acceptable

**Trigger to revisit**: customer (Lully) confirms they're OK with bakery
staff editing a separate "edit-only" Sheet (rather than the main Sheet
that hosts Apps Script).

### Problem

The Apps Script stores `GITHUB_PAT`, `GITHUB_OWNER`, `GITHUB_REPO` in
`PropertiesService.getScriptProperties()`. These look "private to the
script" but are readable by **anyone with Editor access on the host
Sheet** — they can open Extensions → Apps Script → write a one-line
function `Logger.log(PropertiesService.getScriptProperties().getProperties())`
and run it.

The blast radius is significant:

1. PAT has `Contents: write` on `bakery-label-press`
2. With it, an attacker can push a workflow that echoes `secrets.GOOGLE_OAUTH_REFRESH_TOKEN` to the Action log
3. That refresh token grants `drive.file` + `spreadsheets` scope on the bakery owner's Google account

So one Sheet Editor account → potential exfil of the entire Google API
chain. Today this is mitigated only by trust (small team, all known
people).

### Proposed solution

Two Sheets connected via `IMPORTRANGE`:

- **Master Sheet** (current one): Apps Script + `release_history` + `sample`
  tabs. Editor: bakery owner + project maintainer only. `real_data` tab
  becomes a single `=IMPORTRANGE("staff-sheet-id", "Sheet1!A2:I")`
  formula in cell A2 (header row 1 stays hard-coded so build-labels.py's
  CSV header parsing keeps working).
- **Staff Sheet** (new): one tab with the same column structure.
  Editor: bakery staff. No Apps Script bound to it, so script properties
  are unreachable.

Bakery staff edit Staff Sheet → IMPORTRANGE auto-mirrors into Master's
`real_data` → owner clicks 🥖 in Master → Apps Script reads `real_data`
via `getValues()` (which returns the IMPORTRANGE-resolved values, the
formula is invisible at the API layer).

### Migration steps

1. Create Staff Sheet "Lully · Edição de Produtos" with same 9-column
   structure as `real_data` (`name_fr`, `description_pt`, `gluten`,
   `milk`, `egg`, `peanut`, `soy`, `price`, `active`). Apply checkbox
   validations and wrap formatting.
2. Cut data rows from Master's `real_data` → paste into Staff Sheet
   row 2+.
3. In Master's `real_data` tab, leave row 1 untouched (the slug
   header), then in cell A2 enter:
   `=IMPORTRANGE("<staff-sheet-id>", "Sheet1!A2:I")`. Click "Allow
   access" prompt that appears.
4. Re-share: remove staff from Master Sheet (or downgrade to Viewer);
   add them as Editor on Staff Sheet.
5. Re-paste Apps Script (with the guard from § "Code change required"
   below) so future setup() runs don't clobber the IMPORTRANGE formula.
6. Smoke test: staff edits Staff Sheet → wait ~30s → Master mirrors →
   click 🥖 → `release_history` shows success. Then have a staff member
   try opening Master → Extensions → Apps Script and confirm it's
   refused.

### Code change required

`apps-script/lully-labels.gs` `_setupRealDataTab()` needs a guard so
that re-running "Setup / repair tabs" doesn't overwrite the IMPORTRANGE
formula. Implementation already prototyped and reverted — see
`git show acc23bf` for the patch (commit was reverted in `f13337b` to
keep `main` aligned with the pre-decision architecture).

To restore: `git revert <revert-hash>` brings the guard back in one
command.

### Trade-offs / known caveats

| Caveat | Impact |
|---|---|
| IMPORTRANGE has 30s–2min lag | Staff edit → owner-click race condition; refresh page if needed |
| `active` checkbox renders as plain `TRUE`/`FALSE` text in Master | Cosmetic only; `_truthy()` still resolves correctly |
| First-time IMPORTRANGE prompts "Allow access" in Master | One-time owner click |
| Master's `_setupRealDataTab` would clobber formula without the guard | Mitigated by code change above |
| Two Sheets to maintain instead of one | Higher operator surface area |

### Decision criteria for moving forward

Pursue this only if all true:

1. Customer prefers "staff edit a separate Sheet" over "trust all staff
   with Master Sheet access"
2. Customer accepts ~30s mirror lag
3. Customer is OK losing the visual checkbox in `active` column on the
   Master view (still works on Staff side where it matters)

If customer wants stronger isolation but rejects the 2-Sheet UX, fall
back to the alternative: introduce a backend intermediary (Cloud Function
or Cloudflare Worker) that holds the PAT, with Apps Script calling it
via HMAC-signed URL. Higher infra cost, no UX change for staff.
