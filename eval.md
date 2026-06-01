# Evaluation Question Bank

Hand-curated questions over the seed corpus, each paired with the **grounded fact**
the system should return and the **source document** it must cite. Every item is
drawn from `evaluation_set.json` (the brief's 20-item set: 8 factual / 5 multi-hop /
3 conflict / 2 Bahasa / 2 trick) and has a verified expected answer.

## How to read the rubric numbers

The 5-axis rubric (`klerk eval run`) scores each item in `[0, 1]`:
`retrieval_recall`, `substring_coverage`, `citation_grounded`, `locale_match`,
`confidence`. Two reporting caveats matter when reading the headline:

- **Lite mode is a floor.** Without the local extra, ColBERT rerank falls back to
  RRF order and RAGAS is unavailable, so the retrieval/precision axes understate
  the full (local) config.
- **Headline = the in-scope 20.** The 2 Japanese stretch items (Q21/Q22) reference
  documents that were never ingested, so they are reported under a separate
  "Stretch set" and excluded from the headline mean.

---

## Factual (single-doc lookup)

1. **What is the hourly rate for a Senior consultant in IDR per the 2025 rate card?**
   → **2.2M IDR/hr** for a **Senior** consultant. *Source:* consultant rate card (2025).

2. **Under the 2025 parental-leave policy, how many weeks of paid leave does the primary caregiver receive?**
   → **16 weeks** for the **primary** caregiver. *Source:* parental-leave policy (2025).

3. **How many days per week is on-site work expected under the remote work policy?**
   → **3 days** on-site per week. *Source:* remote work policy.

4. **How many PTO days per year are granted to Indonesian staff?**
   → **12 days** per year. *Source:* PTO policy.

5. **How many severity levels are defined in the incident response SOP?**
   → Four levels, **Sev0** through **Sev3**. *Source:* incident response SOP.

6. **List the four data classification tiers from the data handling SOP.**
   → **Public / Internal / Confidential / Restricted**. *Source:* data handling SOP.

7. **Who is the office manager for the Tokyo office?**
   → **Tanaka**. *Source:* office directory.

8. **How long are HR records retained under the data retention schedule?**
   → **7 years**. *Source:* data retention schedule.

## Multi-hop (combine multiple chunks/docs)

9. **Q1 2025 consultant spend overran by 29% — what were the two cited reasons, and who owns the rate card?**
   → Reasons: heavier **Senior**-grade mix and the **CAC** engagement; owner is the
   **VP Advisory**. *Source:* Q1 review minutes + rate card.

10. **How has the parental-leave entitlement changed between the 2023 and 2025 policies?**
    → From **12 weeks (2023)** to **16 weeks (2025)**, with the caregiver window
    extended (~6 months reference). *Source:* parental-leave policies (2023 + 2025).

11. **Does the Bahasa Indonesian PTO policy match the English PTO policy for Jakarta staff?**
    → They reconcile: **12** annual days, **10** carryover cap, **5**-day note are
    consistent across both language versions. *Source:* PTO policy (EN + ID).

12. **What triggers a rollback under the change-management process, and which document defines the rollback?**
    → A **Sev**-level incident triggers **rollback**; defined in the change-management
    SOP. *Source:* change-management SOP + incident response SOP.

13. **Who owns the consultant rate card, and what is the per-consultant engagement cap?**
    → Owner: VP Advisory; cap is **80** hours per **week** per consultant.
    *Source:* rate card.

## Conflict / supersession (contradicting documents)

14. **What is the actual current parental-leave entitlement at PT Fata Organa Solusi?**
    → The **2025** policy (16 weeks) **supersedes** the **2023** policy (12 weeks);
    current = 16 weeks. *Source:* parental-leave policies (2023 vs 2025).

15. **When is the doc-intelligence MVP scheduled to ship?**
    → A **v2** doc **supersedes** the earlier date: ship moved from **Q2** to **Q3**.
    *Source:* project plan (v1 vs v2).

16. **How many engineers are on the doc-intelligence team?**
    → Headcount changed across versions: **3** (earlier) → **4** (**v2**, current).
    *Source:* project plan (v1 vs v2).

## Bahasa Indonesia (multilingual parity)

17. **Berapa hak cuti tahunan karyawan kantor Jakarta menurut kebijakan internal?**
    → **12** hari cuti tahunan (dengan ketentuan **5** terkait). Jawaban harus dalam
    Bahasa Indonesia. *Source:* kebijakan cuti (PTO).

18. **Berapa jumlah minimum reviewer yang dibutuhkan untuk code review menurut SOP Pengembangan?**
    → Minimal **2 reviewer** untuk **code review**. *Source:* SOP pengembangan perangkat lunak.

## Trick (must refuse — not in corpus)

19. **What is the CEO's home address?**
    → System must say it **doesn't know** / the information is not in the documents.
    (No hallucinated address.)

20. **How many cyber attacks occurred in 2024 outside of the Q1 security review's scope?**
    → System must say it **doesn't know** — the data is outside the documented scope.

---

## Stretch — Japanese (excluded from headline; source docs not ingested)

21. **東京オフィスの通勤手当で、片道40km以上55km未満の場合の月額支給上限はいくらですか？**
    → Expected **62,000** (monthly commuter-allowance cap). *Requires* `hr_jp_tsukin_teate`
    — not currently in the corpus.

22. **CACホールディングスのデータ基盤刷新プロジェクトの進捗率と、データ移行フェーズの遅延期間を教えてください。**
    → Expected **34%** progress, **2-week** (2週間) migration delay. *Requires* the JP
    steering/all-hands minutes — not currently in the corpus.

---

### Suggested live-demo arc

`#1 (factual + citation)` → `#17 (Bahasa parity)` → `#14 (conflict/supersession)` →
`#9 (multi-hop)` → `#19 (honest refusal)` → `#11 (cross-lingual consistency)`.

Items **#14** and **#19** are the differentiators: conflict reconciliation and a
clean "I don't know" are what most RAG demos cannot do. Avoid demoing #21/#22 live
(source docs not ingested) and avoid leaning on reranker-precision claims in lite
mode (ColBERT disabled).
