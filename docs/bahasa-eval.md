# SEA-HELM-style Bahasa eval methodology

> Companion to `proposal-rubric.md`. This doc explains what klerk's Bahasa
> parity report is and isn't.

## What it is

[SEA-HELM](https://huggingface.co/spaces/Singapore-AI/sea-helm) is the canonical Southeast Asia LM benchmark, maintained by Singapore AI. It scores instruction-following, factual accuracy, and safety across multiple SEA languages including Bahasa Indonesia.

klerk does NOT reproduce SEA-HELM. It extracts the **methodology**:

1. Score Bahasa Q&A and English Q&A through the **same rubric** (the 5-axis rubric in `proposal-rubric.md`).
2. Report the **delta per axis** (Bahasa score − English score).
3. Visualize the deltas with thresholds: `|Δ| < 0.10` is "parity", `0.10–0.25` is "minor gap", `> 0.25` is "honest gap to flag".

The result is a per-build report of how klerk handles Bahasa relative to English on *your own* corpus — calibrated to your documents, not to SEA-HELM's open-domain dataset.

## What it isn't

- **Not a SEA-HELM replacement.** SEA-HELM tests general-purpose LM capability; klerk's parity report tests klerk's retrieval+answer system on a specific corpus.
- **Not a translation benchmark.** klerk doesn't translate; it retrieves and answers in whatever language the question is asked. The locale_match axis catches accidental cross-language leakage.
- **Not a fluency benchmark.** Native Bahasa fluency would need human eval; klerk reports structural signals (retrieval / citation / coverage), not prose quality.

## How it runs

`klerk eval run --seahelm` (or implicitly with the default `klerk eval run`):

1. Loads every item from `data/golden/qa_*.yaml`.
2. Scores each via the 5-axis rubric.
3. Aggregates per locale.
4. Computes `id_minus_en_delta` per axis (and the overall mean).
5. Writes to `data/output/eval/seahelm.json` + prints a Rich-colored delta table.

## Reading the delta table

```
Δ = Bahasa score − English score
axis                  delta
retrieval_recall      +0.05    (parity)
substring_coverage    -0.18    (minor gap — Bahasa answers miss a key term in ~18% of cases)
citation_grounded     +0.02    (parity)
locale_match           0.00    (perfect)
confidence            -0.10    (parity, just at the edge)
mean                  -0.04    (parity overall)
```

A negative delta means Bahasa underperforms English on that axis. Common causes:

- **substring_coverage negative**: Bahasa-specific terminology not present in the answer (often because retrieval brought back English chunks).
- **retrieval_recall negative**: Bahasa queries don't activate BM25 on English-text chunks (cross-language retrieval gap).
- **citation_grounded negative**: Bahasa answer cited a chunk that wasn't in the Bahasa-localised retrieval round.

## What to do about a gap

The seed corpus is 40% Bahasa by design; gaps usually surface when the operator drops English-heavy real docs into `data/raw/` and the Bahasa golden set targets those docs.

Recipe for closing the gap:

1. **Add Bahasa golden items targeting the gap docs** (`data/golden/qa_id.yaml`).
2. **Run `klerk eval run --locale id`** to focus the rubric on the Bahasa subset.
3. **If retrieval_recall is the gap**: enable `--locale id` on `klerk ask` so the query embedding goes through the Bahasa-tuned Qwen3 (configured in `klerk.llm.router`) and BGE-M3's multilingual head treats the corpus consistently.
4. **If substring_coverage is the gap**: prompt-engineer the answer step to enforce key-term inclusion when chunk evidence supports it.
5. **If locale_match is the gap**: tighten the answer-step system prompt to forbid cross-language drift.

## Methodology sources

- [SEA-HELM benchmark](https://huggingface.co/spaces/Singapore-AI/sea-helm) — Singapore AI's SEA LM benchmark family.
- [PDP Law 2026](https://peraturan.bpk.go.id/Details/229798/uu-no-27-tahun-2022) — Indonesia's Personal Data Protection Law (UU 27/2022), enforced 2026. Makes local inference a regulatory feature, motivating the STRETCH local-LLM path.
- [BGE-M3](https://huggingface.co/BAAI/bge-m3) — multilingual embedder klerk uses; documented strong on Bahasa retrieval.
- [Qwen3](https://qwen.io) — Bahasa-strong leader on SEA-HELM in May 2026; klerk's `--locale id` fallback.
