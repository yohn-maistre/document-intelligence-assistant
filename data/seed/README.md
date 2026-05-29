# Seed corpus

Minimal 3-doc placeholder for plumbing verification — replace with real docs in `data/raw/`.

| File | Locale | Format | Cross-doc fact |
|---|---|---|---|
| `hr_policy_acme.md` | EN | Markdown | Acme parental leave = 16 weeks; consultant rate = $185/hr |
| `kontrak_vendor_pelangi.txt` | ID (Bahasa) | Plain text | Pelangi consultant rate = USD 185/hour (matches `hr_policy_acme`) |
| `memo_internal_q1.md` | Bilingual | Markdown | References both above (parental leave + consultant rate) |

These 3 docs were hand-authored (not LLM-generated) so the harness has deterministic content to retrieve over from h0. The deliberate cross-doc fact (consultant rate appearing in EN policy + ID contract + bilingual memo) enables:

- multi-hop retrieval probes
- contradiction-scan testing (if we mutate one and not the others)
- citation-tracing verification across locales

## Replacing with real docs

Drop your real documents into `data/raw/`. `klerk index build` will pick them up via Docling. The seed corpus is independent and lives at `data/seed/` so you can keep both indices around for comparison.
