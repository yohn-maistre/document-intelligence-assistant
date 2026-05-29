# Proposal Rubric — 5-axis methodology

> The "differentiator beyond RAGAS" called out in `design-decisions.md`.

## Why

RAGAS gives credible per-claim faithfulness + context recall + answer relevance. But for a multi-section proposal, the operator wants to know:

1. *Did retrieval surface the chunks I expected?*
2. *Did the answer cover the specific facts I expected to see?*
3. *Are the citations real (not hallucinated)?*
4. *Did the answer come back in the right language?*
5. *Does the model self-report high confidence?*

These are operationally answerable from the existing retrieval + answer trace + golden set, without a separate LLM judge call per axis. The rubric is therefore **deterministic + cheap + per-locale aggregatable**.

## The five axes

Every axis is a float in `[0, 1]`. The mean is reported alongside.

| Axis | Computation | What it catches |
|---|---|---|
| **retrieval_recall** | `|expected_chunks ∩ retrieved_chunks| / |expected_chunks|` | Retrieval gaps — the right chunk never made it into the top-k. |
| **substring_coverage** | `|expected_substrings ∩ lowercase(answer)| / |expected_substrings|` | The model retrieved correctly but failed to surface the key fact. |
| **citation_grounded** | `|citations ∩ retrieved_chunks| / |citations|` | Hallucinated chunk_ids — citations that point at chunks never retrieved. |
| **locale_match** | `1` if detected language matches expected, `0.5` if undetermined, `0` if wrong | Locale leakage (Bahasa question answered in English or vice versa). |
| **confidence** | The model's self-reported citation coverage (clamped to `[0, 1]`) | Sanity check — the model knows when it's bluffing. |

`mean = (retrieval_recall + substring_coverage + citation_grounded + locale_match + confidence) / 5`

## Calibration

The seed golden set lives in `data/golden/qa_en.yaml` (5 items) + `data/golden/qa_id.yaml` (5 items). Each item carries:

```yaml
- id: en-multihop-001
  question: "Why did Q1 consultant spend overrun by 29% — was it a rate issue or a volume issue?"
  expected_chunks: ["memo_internal_q1:0", "memo_internal_q1:1", "hr_policy_acme:0"]
  expected_substrings: ["volume", "scope"]
  locale: en
  kind: multi-hop
```

`expected_chunks` is **any-of** (retrieval recall counts an item as hit if *any* expected chunk is retrieved — operators can tighten to all-of later). `expected_substrings` is **all-of** (every substring must appear in the answer for substring_coverage to be 1.0).

## Per-locale aggregation

`klerk eval run --rubric` reports:

```
Overall (all items)
axis                  score
retrieval_recall      0.92
substring_coverage    0.88
citation_grounded     0.95
locale_match          1.00
confidence            0.81
mean                  0.91

locale = en           ↑  mean 0.92
locale = id           ↑  mean 0.89
```

The per-locale split is what feeds the SEA-HELM-style Bahasa parity report. A `mean_id - mean_en` delta within `±0.10` per axis is "parity"; larger deltas are flagged in the parity report's `id_minus_en_delta` table.

## Reading the output JSON

`data/output/eval/rubric.json`:

```json
{
  "items": [
    {
      "item_id": "en-multihop-001",
      "locale": "en",
      "retrieval_recall": 1.0,
      "substring_coverage": 0.5,
      "citation_grounded": 1.0,
      "locale_match": 1.0,
      "confidence": 0.83,
      "answer": "Q1 consultant spend...",
      "citations": ["memo_internal_q1:1", "hr_policy_acme:0"],
      "retrieved_chunk_ids": ["memo_internal_q1:0", "memo_internal_q1:1", ...]
    }
  ],
  "aggregate": {
    "overall": { "n": 10, "retrieval_recall": 0.92, ... },
    "by_locale": { "en": {...}, "id": {...} }
  }
}
```

Studio's Eval panel reads this file directly so the operator can drill from a per-axis score down to the specific failed items.
