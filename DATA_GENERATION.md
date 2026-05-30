# DATA_GENERATION.md

How the synthetic Fata Organa Solusi corpus is built, what the brief
constraints look like in code, and how to regenerate / extend it.

## 1. What ships

**`data/synth/fata_organa/`** — 30 generated documents and a
`manifest.json` describing each one (status, locale, format,
contradiction-pair membership, cross-refs). The corpus is reproducible
from the spec in `src/klerk/synth/specs.py`.

| Category | Count |
|----------|------:|
| HR       | 9     |
| SOP      | 8     |
| Minutes  | 7     |
| FAQ      | 4     |
| Org      | 2     |
| **Total** | **30** |

| Format | Count |
|--------|------:|
| PDF    | 10    |
| DOCX   | 14    |
| MD     | 6     |

| Locale | Count |
|--------|------:|
| en     | 26    |
| id     | 4     |

| Brief property                | Status |
|-------------------------------|--------|
| ≥10 PDF                       | ✓ (10) |
| ≥10 DOCX                      | ✓ (14) |
| ≥3 Bahasa                     | ✓ (4)  |
| ≥2 contradicting pairs        | ✓ (2)  |
| ≥2 with structured tables     | ✓ (2)  |
| ≥1 cross-doc reference        | ✓ (18 inbound across the corpus) |

`klerk synth check` runs every constraint as an assertion and exits
non-zero if any fail.

## 2. Architecture

```
specs.py (data) ──▶ gen.py (orchestrator) ──▶ Nemotron via router.complete
   |                     |                       (response_format=json_object)
   |                     |
   |                     ▼
   |                  DocBody (Pydantic) ─── _write_pdf  (reportlab)
   |                                     ├── _write_docx (python-docx)
   |                                     └── _write_md   (markdown)
   |                                              │
   ▼                                              ▼
constraint_check()                       data/synth/fata_organa/{doc_id}.{ext}
                                              + manifest.json
```

- `specs.py` holds **the corpus plan** as a list of `DocSpec` dataclasses
  (no LLM calls). One DocSpec per planned document.
- `gen.py` is **the engine**: builds prompts, calls the LLM, validates
  output, dispatches to the format writer.
- `cli/synth_cmd.py` is the operator-facing wrapper with progress bars and
  the constraint pre-flight.
- `tests/test_synth_gen.py` exercises the engine end to end with a mocked
  LLM (real generation is gated on `LITELLM_KEY`).

## 3. The Fata Organa fictional spec

PT Fata Organa Solusi is an Indonesian-Japanese technology consulting
firm. Jakarta HQ + Tokyo satellite. CAC Holding Japan is named in the
brief as their largest client. Cultural details threaded throughout:

- **Names**: Indonesian (Yan, Putri, Galih) + Japanese (Tanaka,
  Yamada, Sato) staff.
- **Locations**: Jakarta (SCBD) + Tokyo (Minato-ku).
- **Currencies**: IDR + JPY, both used in the rate card and the
  compensation bands.
- **Timestamps**: WIB and JST mixed across minutes.
- **Compliance frame**: PDP UU 27/2022 (Indonesia) + APPI (Japan) in
  the data-retention SOP.

## 4. The two contradicting pairs

| Pair | Doc 1 | Doc 2 | Contradiction |
|------|-------|-------|---------------|
| Parental leave | `hr_parental_leave_2023` | `hr_parental_leave_2025` | 12 wk primary / 12-mo eligibility / manager-gated vs 16 wk / 6-mo / direct-to-HR |
| Product roadmap | `minutes_product_roadmap_v1` | `minutes_product_roadmap_v2` | Q2 ship + 3 eng (Feb 10) vs Q3 ship + 4 eng (Mar 22) |

The prompts pass `contradiction_pair` to the LLM with explicit
instructions: *make the conflicting claim concrete and unambiguous so a
contradiction scanner can flag it*. Both pairs are date-stamped so the
scanner can present "v2 supersedes v1" reliably.

## 5. The two table-bearing docs

| Doc | Table |
|-----|-------|
| `hr_consultant_rate_card_2025` | 4 tiers × 2 currencies (Junior/Mid/Senior/Principal × IDR/JPY) + engagement cap |
| `hr_compensation_bands`        | 5 levels (E1–E5) × 2 geographies (ID/JP), base + equity + target bonus |

Tables are rendered natively in both PDF (reportlab `Table` + `TableStyle`)
and DOCX (`Light Grid Accent 1` style). MD uses pipe-table syntax.

## 6. JSON-output prompting

The generator does not ask for free-text markdown; it asks for **strict
JSON** matching this schema:

```jsonc
{
  "title": "<doc title>",
  "sections": [
    { "heading": "<h>", "paragraphs": ["<p1>", "<p2>"] }
  ],
  "table": { "headers": ["..."], "rows": [["...", "..."]] } | null
}
```

Reasons:
- Pydantic validates the parse; bad output fails fast with a clean error
  rather than producing a corrupted doc.
- `response_format={"type": "json_object"}` is supported by LiteLLM →
  Nemotron — leverages the same hard-mode the proposal pipeline uses.
- The format writers (`_write_pdf` / `_write_docx` / `_write_md`)
  consume the same `DocBody` model uniformly; no per-format prompt drift.

If the LLM wraps its JSON in ```json fences, `_parse_body` strips them.
If the JSON is malformed or the schema doesn't match, the spec is marked
`status: "failed"` in `manifest.json` and the run continues — one bad
doc doesn't kill the corpus.

## 7. Caching

`klerk.llm.router.complete` is two-layer cached (DiskCache exact-match +
LanceDB semantic). Regenerating the same DocSpec hits the cache and
returns the same body for free.

Two skip mechanisms:
- **File-level** (default): `generate_corpus(skip_existing=True)` —
  don't touch files that already exist on disk.
- **LLM-level**: cache hits short-circuit the actual Nemotron call.
  Useful for `--force` re-renders where the writer changed but the
  body didn't.

## 8. How to run

```bash
# Dry-run: verify the spec satisfies every brief constraint
klerk synth check

# Generate (needs LITELLM_KEY + CF tokens in .env)
klerk synth gen
# → data/synth/fata_organa/*.{pdf,docx,md}
# → data/synth/fata_organa/manifest.json

# Force-regenerate everything
klerk synth gen --force

# Then index for retrieval
klerk index build --src data/synth/fata_organa --rebuild
```

Expected wall time, full 30-doc run with a cold cache: **5–10 minutes**.
Warm cache: under a minute.

## 9. How to extend / modify

Add a new `DocSpec` to the `CORPUS` list in `src/klerk/synth/specs.py`.
`constraint_check()` re-validates on every `klerk synth check`. To
introduce a new constraint, extend `constraint_check()` and add a row
to the assertion table in `tests/test_synth_gen.py`.

To wire a third contradicting pair, set `contradiction_pair=(a, b)` on
both DocSpecs and reference each other's `doc_id` in the field. The
test suite verifies pairs are symmetric and cross-refs point at real
docs — adding a broken cross-ref fails CI.
