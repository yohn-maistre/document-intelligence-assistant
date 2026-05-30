"""Fata Organa Solusi synthetic-corpus specification.

The brief requires 25-30 docs across five categories with hard constraints:
  HR ≥8, SOPs ≥6, Minutes ≥6, FAQs ≥4, Org/Contact ≥2
  ≥10 PDF, ≥10 DOCX, ≥3 Bahasa, ≥2 contradicting pairs, ≥2 with tables,
  ≥1 cross-doc reference

We ship 30: 10 PDF + 10 DOCX + 6 MD + 4 supporting docs. 4 Bahasa, 2 contradicting pairs
(parental leave 2023 vs 2025; product roadmap v1 vs v2), 2 with tables
(consultant rate card; compensation bands), several cross-doc references
threaded through the minutes and the org directory.

Cultural sprinkle (Fata Organa Solusi is fictional Indonesian-Japanese):
  - CAC Holding Japan mentioned as the named client (per the brief)
  - Tokyo addresses (Minato-ku) + Jakarta addresses (SCBD)
  - JST and WIB timestamps
  - Mixed names: Indonesian (Yan, Putri, Galih) and Japanese (Tanaka,
    Yamada, Sato)
  - Cross-language org references — Bahasa docs reference English docs
    by doc_id and vice versa

This file is data only. Generation lives in `klerk.synth.gen`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Category = Literal["hr", "sop", "minutes", "faq", "org"]
Format = Literal["pdf", "docx", "md"]
Locale = Literal["en", "id"]


@dataclass
class DocSpec:
    doc_id: str
    category: Category
    format: Format
    locale: Locale
    title: str
    brief: str
    # Optional hints to the generator
    has_table: bool = False
    contradiction_pair: tuple[str, str] | None = None    # (this_id, other_id)
    cross_refs: list[str] = field(default_factory=list)  # doc_ids referenced
    date_stamp: str | None = None                         # for contradicting pairs


# ─── The 28-doc corpus plan ──────────────────────────────────────────────────
CORPUS: list[DocSpec] = [
    # ── HR (11; need ≥8) ────────────────────────────────────────────────────
    DocSpec(
        doc_id="hr_parental_leave_2023",
        category="hr",
        format="pdf",
        locale="en",
        title="Parental Leave Policy — Effective 2023",
        brief=(
            "Old version of the policy: 12 weeks paid parental leave for the "
            "primary caregiver, 2 weeks for secondary. Eligible after 12 "
            "months of employment. Approval routed through line manager → HR. "
            "Reference 'PT Fata Organa Solusi' as the issuing entity."
        ),
        contradiction_pair=("hr_parental_leave_2023", "hr_parental_leave_2025"),
        date_stamp="Effective 2023-01-01",
    ),
    DocSpec(
        doc_id="hr_parental_leave_2025",
        category="hr",
        format="pdf",
        locale="en",
        title="Parental Leave Policy — Effective 2025",
        brief=(
            "Updated policy: 16 weeks paid parental leave for the primary "
            "caregiver, 4 weeks for secondary. Eligible after 6 months of "
            "employment (down from 12). Approval is now direct to HR — line "
            "managers are informed, not gating. This DELIBERATELY contradicts "
            "hr_parental_leave_2023 — the contradiction is by design and "
            "should be flagged by klerk's contradiction scanner."
        ),
        contradiction_pair=("hr_parental_leave_2025", "hr_parental_leave_2023"),
        date_stamp="Effective 2025-01-01",
    ),
    DocSpec(
        doc_id="hr_remote_work_policy",
        category="hr",
        format="docx",
        locale="en",
        title="Remote Work Policy",
        brief=(
            "3 days/week minimum in-office (Jakarta HQ or Tokyo satellite). "
            "Stipend: IDR 1.5M / JPY 12,000 monthly. Excludes the consultant "
            "advisory practice (see hr_consultant_rate_card_2025 for billable "
            "expectations)."
        ),
        cross_refs=["hr_consultant_rate_card_2025"],
    ),
    DocSpec(
        doc_id="hr_consultant_rate_card_2025",
        category="hr",
        format="pdf",
        locale="en",
        title="Consultant Rate Card — 2025",
        brief=(
            "Internal rate card for the advisory practice. Includes a table "
            "with seniority tiers, hourly rates in IDR and JPY (one row per "
            "tier × geography), and per-engagement caps. Junior: IDR 850k/h "
            "or JPY 9,500/h. Mid: IDR 1.4M/h or JPY 15,000/h. Senior: IDR "
            "2.2M/h or JPY 24,000/h. Principal: IDR 3.5M/h or JPY 38,000/h. "
            "Engagement cap: 80h/week per consultant."
        ),
        has_table=True,
    ),
    DocSpec(
        doc_id="hr_pto_policy",
        category="hr",
        format="pdf",
        locale="en",
        title="Paid Time Off Policy",
        brief=(
            "12 PTO days/year for ID staff, 20 days/year for JP staff "
            "(statutory). Carryover: up to 5 days into the following year. "
            "Sick leave separate (10 days/year). Public holidays follow the "
            "local jurisdiction."
        ),
    ),
    DocSpec(
        doc_id="hr_kebijakan_cuti",
        category="hr",
        format="docx",
        locale="id",
        title="Kebijakan Cuti Tahunan",
        brief=(
            "Versi Bahasa Indonesia dari kebijakan cuti tahunan untuk staf di "
            "Jakarta. Mencakup hak cuti 12 hari per tahun, cuti sakit "
            "tersendiri (10 hari per tahun), dan ketentuan carryover (maksimal "
            "5 hari). Konsisten dengan hr_pto_policy versi bahasa Inggris."
        ),
        cross_refs=["hr_pto_policy"],
    ),
    DocSpec(
        doc_id="hr_compensation_bands",
        category="hr",
        format="docx",
        locale="en",
        title="Compensation Bands — Engineering, 2025",
        brief=(
            "Internal banding table: 5 levels (E1-E5) × 2 geographies (ID, "
            "JP). Includes base salary range in local currency, equity grant "
            "in shares, and target bonus %. E1 base: IDR 18-22M/mo (ID) or "
            "JPY 380-440k/mo (JP). E5 base: IDR 55-72M/mo (ID) or JPY "
            "1.1-1.4M/mo (JP). Cite hr_consultant_rate_card_2025 for the "
            "consultant-track parallel structure."
        ),
        has_table=True,
        cross_refs=["hr_consultant_rate_card_2025"],
    ),
    DocSpec(
        doc_id="hr_onboarding_checklist",
        category="hr",
        format="docx",
        locale="en",
        title="New Hire Onboarding Checklist",
        brief=(
            "Day-1 / Week-1 / Month-1 milestones. Equipment provisioning, "
            "access requests (gated by sop_data_classification level), "
            "buddy assignment, manager 1:1 cadence. Includes a JP-specific "
            "addendum for the Tokyo office (hanko registration, residence "
            "card, koseki forms)."
        ),
        cross_refs=["sop_data_classification"],
    ),
    DocSpec(
        doc_id="hr_performance_review_cycle",
        category="hr",
        format="docx",
        locale="en",
        title="Performance Review Cycle",
        brief=(
            "Semi-annual reviews (H1 in June, H2 in December). Calibration "
            "across teams. 9-box grid for talent matrix. Promotion criteria "
            "by level. Self-review + peer feedback + manager review components."
        ),
    ),
    # ── SOPs (8; need ≥6) ───────────────────────────────────────────────────
    DocSpec(
        doc_id="sop_incident_response",
        category="sop",
        format="pdf",
        locale="en",
        title="Incident Response SOP",
        brief=(
            "Severity levels (Sev0-3). On-call rotation. Communication tree. "
            "Post-mortem template. War-room location (Jakarta HQ, room 14F-A; "
            "Tokyo, Minato-ku 8F)."
        ),
    ),
    DocSpec(
        doc_id="sop_change_management",
        category="sop",
        format="docx",
        locale="en",
        title="Change Management SOP",
        brief=(
            "RFC process for production changes. Required approvals by blast "
            "radius. Standard vs emergency vs normal changes. Cite "
            "sop_incident_response for the rollback trigger conditions."
        ),
        cross_refs=["sop_incident_response"],
    ),
    DocSpec(
        doc_id="sop_data_classification",
        category="sop",
        format="pdf",
        locale="en",
        title="Data Classification & Handling",
        brief=(
            "Four tiers: Public, Internal, Confidential, Restricted. "
            "Handling requirements per tier (encryption at rest/in transit, "
            "retention, access logging). Reference sop_data_retention for "
            "the retention schedule."
        ),
        cross_refs=["sop_data_retention"],
    ),
    DocSpec(
        doc_id="sop_pengembangan_perangkat_lunak",
        category="sop",
        format="pdf",
        locale="id",
        title="SOP Pengembangan Perangkat Lunak",
        brief=(
            "SOP berbahasa Indonesia tentang siklus pengembangan perangkat "
            "lunak: code review (minimum 2 reviewer), CI gates, deployment "
            "approval, dan rollback. Mengacu pada sop_change_management "
            "untuk proses RFC."
        ),
        cross_refs=["sop_change_management"],
    ),
    DocSpec(
        doc_id="sop_vendor_onboarding",
        category="sop",
        format="docx",
        locale="en",
        title="Vendor Onboarding SOP",
        brief=(
            "Due diligence checklist (security questionnaire, financial "
            "review, references), contract review, billing setup. NDA "
            "required before any data exchange."
        ),
    ),
    DocSpec(
        doc_id="sop_security_audit",
        category="sop",
        format="docx",
        locale="en",
        title="Security Audit SOP",
        brief=(
            "Annual external audit + quarterly internal. Scope by data "
            "classification tier (see sop_data_classification). CAC Holding "
            "engagements require additional SOC 2 Type II evidence packets."
        ),
        cross_refs=["sop_data_classification"],
    ),
    DocSpec(
        doc_id="sop_data_retention",
        category="sop",
        format="docx",
        locale="en",
        title="Data Retention Schedule",
        brief=(
            "Per-data-type retention windows: HR records 7y, financial "
            "records 10y, customer data per contract, internal logs 90d. "
            "Aligns to PDP UU 27/2022 (Indonesia) and APPI (Japan)."
        ),
    ),
    DocSpec(
        doc_id="sop_client_engagement",
        category="sop",
        format="docx",
        locale="en",
        title="Client Engagement SOP",
        brief=(
            "End-to-end flow from RFP through engagement close. Pricing "
            "review (cite hr_consultant_rate_card_2025), legal review, "
            "kickoff, status cadence, close-out. CAC Holding gets a custom "
            "track due to relationship depth."
        ),
        cross_refs=["hr_consultant_rate_card_2025"],
    ),
    # ── Minutes (7; need ≥6) ────────────────────────────────────────────────
    DocSpec(
        doc_id="minutes_q1_budget_review",
        category="minutes",
        format="pdf",
        locale="en",
        title="Minutes — Q1 2025 Budget Review",
        brief=(
            "Attendees: CFO, COO, CTO, VP Advisory. Q1 consultant spend "
            "overran by 29% vs plan — attributed to two factors: (1) the "
            "Senior tier rate (per hr_consultant_rate_card_2025) was "
            "renegotiated mid-quarter and (2) the CAC Holding engagement "
            "scope expanded. Decision: tighten the engagement-cap clause for "
            "Q2. Action items recorded for VP Advisory (rate review) and "
            "CFO (variance report by 2026-02-01)."
        ),
        cross_refs=["hr_consultant_rate_card_2025"],
        date_stamp="2025-04-12 14:00 WIB",
    ),
    DocSpec(
        doc_id="minutes_security_review",
        category="minutes",
        format="pdf",
        locale="en",
        title="Minutes — Quarterly Security Review (Q1 2025)",
        brief=(
            "Attendees: CISO, CTO, Head of Engineering. One Sev2 incident in "
            "Q1, resolved per sop_incident_response. Two Sev3 incidents. "
            "Audit prep for CAC Holding's SOC 2 Type II refresh. Action "
            "items: rotate the LiteLLM virtual key (currently 90-day "
            "expiry), commission an external pen-test for Q2."
        ),
        cross_refs=["sop_incident_response", "sop_security_audit"],
        date_stamp="2025-04-15 09:00 WIB",
    ),
    DocSpec(
        doc_id="minutes_quarterly_planning_2025",
        category="minutes",
        format="docx",
        locale="en",
        title="Minutes — 2025 Annual Planning",
        brief=(
            "Three initiatives prioritised: (1) CAC Holding engagement "
            "expansion, (2) Tokyo office headcount +6, (3) internal AI "
            "tooling rollout. Budget allocation approved. Action items per "
            "owner with H1 deadlines."
        ),
        date_stamp="2025-01-08 10:00 WIB",
    ),
    DocSpec(
        doc_id="minutes_product_roadmap_v1",
        category="minutes",
        format="docx",
        locale="en",
        title="Minutes — Product Roadmap (v1, 2025-02-10)",
        brief=(
            "INITIAL roadmap decision: ship the doc-intelligence MVP by "
            "Q2 2025, defer the Knowledge Graph viz to Q3. Vendor: in-house "
            "Python stack. Headcount: 3 engineers + 1 PM."
        ),
        contradiction_pair=("minutes_product_roadmap_v1", "minutes_product_roadmap_v2"),
        date_stamp="2025-02-10 13:30 WIB",
    ),
    DocSpec(
        doc_id="minutes_product_roadmap_v2",
        category="minutes",
        format="docx",
        locale="en",
        title="Minutes — Product Roadmap (v2, 2025-03-22)",
        brief=(
            "REVISED roadmap (supersedes v1 on 2025-03-22): MVP slipped to "
            "Q3 2025 (was Q2). KG viz advanced to Q2 (was Q3 in v1). "
            "Vendor: still in-house. Headcount revised UP to 4 engineers + "
            "1 PM (was 3+1 in v1). This DELIBERATELY contradicts "
            "minutes_product_roadmap_v1 — the timeline/headcount changes "
            "should be flagged by the contradiction scanner."
        ),
        contradiction_pair=("minutes_product_roadmap_v2", "minutes_product_roadmap_v1"),
        date_stamp="2025-03-22 13:30 WIB",
    ),
    DocSpec(
        doc_id="minutes_rapat_strategi",
        category="minutes",
        format="pdf",
        locale="id",
        title="Notulen Rapat Strategi — Maret 2025",
        brief=(
            "Notulen rapat strategi triwulanan dalam Bahasa Indonesia. "
            "Topik utama: ekspansi tim advisory ke pasar Jepang, "
            "investasi pelatihan teknis (lihat hr_performance_review_cycle), "
            "dan keputusan tentang penggunaan AI internal."
        ),
        cross_refs=["hr_performance_review_cycle"],
        date_stamp="2025-03-05 09:00 WIB",
    ),
    DocSpec(
        doc_id="minutes_cac_kickoff",
        category="minutes",
        format="docx",
        locale="en",
        title="Minutes — CAC Holding Engagement Kickoff",
        brief=(
            "CAC Holding Japan kickoff for the data-platform modernisation "
            "engagement. Scope: 6 months, lead consultant + 2 senior + 1 "
            "mid (per hr_consultant_rate_card_2025). Cadence: weekly "
            "steering + biweekly working sessions in Tokyo."
        ),
        cross_refs=["hr_consultant_rate_card_2025"],
        date_stamp="2025-04-22 10:00 JST",
    ),
    # ── FAQ (4; need ≥4) ────────────────────────────────────────────────────
    DocSpec(
        doc_id="faq_employee_benefits",
        category="faq",
        format="md",
        locale="en",
        title="FAQ — Employee Benefits",
        brief=(
            "10-12 Q&A pairs covering health insurance, parental leave (cite "
            "hr_parental_leave_2025 as the current version), PTO carryover, "
            "remote-work stipend, equipment refresh cycle. Conversational "
            "tone."
        ),
        cross_refs=["hr_parental_leave_2025", "hr_pto_policy"],
    ),
    DocSpec(
        doc_id="faq_security_questions",
        category="faq",
        format="md",
        locale="en",
        title="FAQ — Security & Data Handling",
        brief=(
            "8-10 Q&A pairs covering data classification tiers, what's OK to "
            "share externally, how to report an incident, password manager "
            "policy. Cite sop_data_classification and sop_incident_response."
        ),
        cross_refs=["sop_data_classification", "sop_incident_response"],
    ),
    DocSpec(
        doc_id="faq_remote_work",
        category="faq",
        format="md",
        locale="en",
        title="FAQ — Remote Work",
        brief=(
            "8-10 Q&A pairs on the 3-day in-office expectation, stipend "
            "claim process, time-zone overlap requirements with the Tokyo "
            "office, equipment reimbursement. Cite hr_remote_work_policy."
        ),
        cross_refs=["hr_remote_work_policy"],
    ),
    DocSpec(
        doc_id="faq_pertanyaan_umum",
        category="faq",
        format="md",
        locale="id",
        title="FAQ — Pertanyaan Umum Karyawan",
        brief=(
            "10-12 pasang tanya-jawab dalam Bahasa Indonesia untuk karyawan "
            "kantor Jakarta. Mencakup cuti, asuransi, jam kerja, dan "
            "tunjangan. Mengacu pada hr_kebijakan_cuti dan hr_pto_policy."
        ),
        cross_refs=["hr_kebijakan_cuti", "hr_pto_policy"],
    ),
    # ── Org/Contact (2; need ≥2) ────────────────────────────────────────────
    DocSpec(
        doc_id="org_directory",
        category="org",
        format="md",
        locale="en",
        title="Org Directory & Document Index",
        brief=(
            "Master org chart + named owners for every policy/SOP in this "
            "corpus. List which person is the owner of each of: "
            "hr_parental_leave_2025, hr_consultant_rate_card_2025, "
            "sop_incident_response, sop_data_classification, "
            "sop_security_audit, minutes_q1_budget_review. Include both "
            "Jakarta and Tokyo office contacts."
        ),
        cross_refs=[
            "hr_parental_leave_2025",
            "hr_consultant_rate_card_2025",
            "sop_incident_response",
            "sop_data_classification",
            "sop_security_audit",
            "minutes_q1_budget_review",
        ],
    ),
    DocSpec(
        doc_id="org_japan_office_contacts",
        category="org",
        format="md",
        locale="en",
        title="Japan Office Contact Sheet",
        brief=(
            "Tokyo office contact sheet. Address (Minato-ku, Tokyo). Office "
            "manager (Tanaka-san), HR liaison, IT liaison. Emergency "
            "contacts. Lists the CAC Holding account team members."
        ),
    ),
]


# ─── Sanity-check helpers ────────────────────────────────────────────────────
def constraint_check(corpus: list[DocSpec] = CORPUS) -> dict[str, int | bool]:
    """Verify the corpus plan meets every brief constraint."""
    totals = {
        "n_total": len(corpus),
        "n_hr": sum(1 for d in corpus if d.category == "hr"),
        "n_sop": sum(1 for d in corpus if d.category == "sop"),
        "n_minutes": sum(1 for d in corpus if d.category == "minutes"),
        "n_faq": sum(1 for d in corpus if d.category == "faq"),
        "n_org": sum(1 for d in corpus if d.category == "org"),
        "n_pdf": sum(1 for d in corpus if d.format == "pdf"),
        "n_docx": sum(1 for d in corpus if d.format == "docx"),
        "n_md": sum(1 for d in corpus if d.format == "md"),
        "n_bahasa": sum(1 for d in corpus if d.locale == "id"),
        "n_with_table": sum(1 for d in corpus if d.has_table),
        "n_contradiction_docs": sum(1 for d in corpus if d.contradiction_pair),
        "n_with_cross_refs": sum(1 for d in corpus if d.cross_refs),
    }
    constraints_met = {
        "total_in_range": 25 <= totals["n_total"] <= 30,
        "hr_min_8": totals["n_hr"] >= 8,
        "sop_min_6": totals["n_sop"] >= 6,
        "minutes_min_6": totals["n_minutes"] >= 6,
        "faq_min_4": totals["n_faq"] >= 4,
        "org_min_2": totals["n_org"] >= 2,
        "pdf_min_10": totals["n_pdf"] >= 10,
        "docx_min_10": totals["n_docx"] >= 10,
        "bahasa_min_3": totals["n_bahasa"] >= 3,
        "table_min_2": totals["n_with_table"] >= 2,
        "contradicting_pairs_min_2": totals["n_contradiction_docs"] >= 4,  # 2 pairs = 4 docs
        "cross_ref_min_1": totals["n_with_cross_refs"] >= 1,
    }
    return {**totals, **constraints_met}
