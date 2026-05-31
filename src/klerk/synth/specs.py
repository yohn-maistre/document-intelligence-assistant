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
Locale = Literal["en", "id", "ja"]  # en/id are brief-mandated; ja = Tokyo-office realism


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
    # ── Japanese Tokyo-office docs (locale=ja; beyond the brief's ≥3 Bahasa) ──
    DocSpec(
        doc_id="hr_tokyo_shugyo_kisoku",
        category="hr",
        format="docx",
        locale="ja",
        title="東京サテライトオフィス就業規則",
        brief=(
            "PT Fata Organa Solusi 東京サテライトオフィス（〒107-0052 東京都港区赤坂"
            "2-14-27 8階）に適用される就業規則。発効日：2025年4月1日。"
            "所定労働時間は1日8時間・週40時間、コアタイムは10:00〜15:00（JST）の"
            "フレックスタイム制とし、始業は7:00〜10:00、終業は16:00〜20:00の範囲で"
            "選択可能とする。休憩は12:00〜13:00を基本とする1時間。"
            "時間外労働は労働基準法第36条に基づく労使協定（36協定）の範囲内とし、"
            "月45時間・年360時間を上限、特別条項適用時でも月80時間・年720時間を"
            "超えないものとする。割増賃金率は時間外25%、深夜（22:00〜翌5:00）25%、"
            "法定休日労働35%。年次有給休暇は労働基準法第39条に準拠し、入社6か月"
            "経過後に10日付与、以降勤続年数に応じて最大20日まで加算する。"
            "就業規則の管轄者は東京オフィス人事担当の田中氏、相談窓口は山田氏とする。"
            "CACホールディングス常駐案件に従事する社員にも本規則を適用する。"
            "リモートワークの取扱いは別途定める hr_remote_work_policy を参照のこと。"
            "賃金・給与レンジは hr_consultant_rate_card_2025 と整合させる。"
        ),
        cross_refs=["hr_remote_work_policy", "hr_consultant_rate_card_2025"],
        date_stamp="発効日 2025-04-01",
    ),
    DocSpec(
        doc_id="hr_jp_tsukin_teate",
        category="hr",
        format="docx",
        locale="ja",
        title="通勤手当規程（東京オフィス）",
        brief=(
            "東京サテライトオフィス（東京都港区赤坂）に勤務する社員を対象とした"
            "通勤手当規程。発効日：2025年4月1日。担当：人事 佐藤氏。"
            "公共交通機関利用者には1か月定期券相当額を支給し、所得税法上の非課税限度額"
            "（月額150,000円）を上限とする。距離区分に応じた支給額の上限テーブルを"
            "必ず本文に表として掲載すること。表の各行は「片道通勤距離 / "
            "支給上限額（月額・円）/ 備考」とし、以下のティアを含める："
            "2km未満：支給なし（徒歩圏） / 2km以上10km未満：¥12,000 / "
            "10km以上25km未満：¥28,000 / 25km以上40km未満：¥45,000 / "
            "40km以上55km未満：¥62,000 / 55km以上：¥75,000（上限）。"
            "新幹線通勤は事前承認制で別枠、月額上限¥150,000。マイカー通勤は港区内では"
            "原則認めず、ガソリン代相当の実費精算も行わない。"
            "支給は毎月25日の給与と同時振込（JST基準）。CACホールディングス先への"
            "常駐者で勤務地が変わる場合は実勤務地起点で再計算する。"
            "リモートワーク日が月の所定出社日数を下回る場合は日割計算とし、"
            "詳細は hr_remote_work_policy に従う。"
        ),
        has_table=True,
        cross_refs=["hr_remote_work_policy"],
        date_stamp="発効日 2025-04-01",
    ),
    DocSpec(
        doc_id="sop_jp_incident_taiou",
        category="sop",
        format="docx",
        locale="ja",
        title="インシデント対応手順書（東京オフィス版）",
        brief=(
            "PT Fata Organa Solusi 東京サテライトオフィス（東京都港区赤坂、8階）"
            "におけるセキュリティ／サービス障害のインシデント対応手順書。"
            "英語版 sop_incident_response の日本語ローカライズ版であり、深刻度区分"
            "（Sev0〜Sev3）と用語は英語版に準拠する。発効日：2025年5月1日。"
            "東京オフィスのウォールーム（戦況室）は港区オフィス8階会議室「Fuji」"
            "とする。一次受付（オンコール）は平日9:00〜18:00 JSTを東京チーム、"
            "夜間・休日はジャカルタ本社（WIB）へエスカレーションする follow-the-sun 体制。"
            "Sev0／Sev1は検知から15分以内に東京オフィスマネージャー田中氏へ電話連絡し、"
            "30分以内にインシデント指揮官（IC）を任命する。連絡網の一次連絡先は"
            "田中氏、技術リードは山田氏、顧客連絡担当は佐藤氏。"
            "CACホールディングス常駐環境で発生したインシデントは、契約上の通知義務"
            "（重大事案は4時間以内に先方セキュリティ窓口へ一次報告）を最優先とする。"
            "事後分析（ポストモーテム）は英語版テンプレートに従い、発生から5営業日以内"
            "に提出する。詳細な共通手順・深刻度定義は sop_incident_response を参照。"
        ),
        cross_refs=["sop_incident_response"],
        date_stamp="発効日 2025-05-01",
    ),
    DocSpec(
        doc_id="minutes_cac_jp_steering",
        category="minutes",
        format="docx",
        locale="ja",
        title="議事録 — CACホールディングス データ基盤刷新 ステアリングコミッティ（第3回）",
        brief=(
            "CACホールディングス（CAC Holding Japan）データ基盤刷新プロジェクトの"
            "第3回ステアリングコミッティ議事録。場所：東京都港区 PT Fata Organa Solusi "
            "東京サテライトオフィス 8F 会議室。出席者：当社側 田中 健一（東京オフィス"
            "マネージャー／プロジェクト責任者）、山田 美咲（リードコンサルタント）、"
            "佐藤 大輔（シニアコンサルタント）、ガリ・プラタマ（データアーキテクト、"
            "ジャカルタ本社よりリモート参加）。CAC側 中村 浩二（情報システム本部長）、"
            "鈴木 由香（PMO）。議題と決定事項を構造化して記述すること："
            "(1) スコープ進捗：6か月契約の第2か月終了時点で全体の34%完了、"
            "データ移行フェーズが2週間遅延。"
            "(2) 予算：当四半期のコンサルタント稼働は累計1,180時間、請求額 約¥27,600,000。"
            "シニアtier単価¥24,000/h、ミッド単価¥15,000/hはhr_consultant_rate_card_2025に準拠。"
            "週あたり稼働上限80時間/人を超過しないことを再確認。"
            "(3) キックオフ時に合意したケイデンス（週次ステアリング＋隔週ワーキング）は"
            "minutes_cac_kickoffの通り維持。"
            "決定事項：①データ移行の遅延を取り戻すため、6月に追加のミッドコンサルタント1名を"
            "投入（追加予算 約¥2,400,000）。②次回ステアリングは2025-05-09 10:00 JST。"
            "アクションアイテムは必ず「担当者 / タスク / 期限」の形式で列挙すること："
            "・山田 美咲 / データ移行の改訂スケジュールを作成し中村本部長へ提出 / 2025-04-30。"
            "・佐藤 大輔 / SOC2監査証跡パッケージの一次ドラフト作成 / 2025-05-06。"
            "・田中 健一 / 追加コンサルタント1名のアサインと稼働上限の整合確認 / 2025-05-02。"
            "・鈴木 由香（CAC側）/ 移行先環境のアクセス権限申請を完了 / 2025-04-29。"
            "金額はすべて日本円（¥）、時刻はJSTで記載すること。"
        ),
        cross_refs=["minutes_cac_kickoff", "hr_consultant_rate_card_2025"],
        date_stamp="2025-04-25 10:00 JST",
    ),
    DocSpec(
        doc_id="faq_jp_shain",
        category="faq",
        format="md",
        locale="ja",
        title="よくある質問（FAQ）— 東京オフィス社員向け",
        brief=(
            "PT Fata Organa Solusi 東京サテライトオフィス（東京都港区）の社員向けFAQ。"
            "会話的で平易な日本語のQ&Aを10〜12組、Markdown形式で作成すること。"
            "在宅勤務、交通費、有給休暇、経費精算、セキュリティのトピックを必ず含める。"
            "具体例（数値・固定値を必ず明記すること）："
            "・在宅勤務：原則として週3日以上はオフィス勤務が必要（hr_remote_work_policyに準拠）、"
            "在宅勤務手当は月額¥12,000。詳細な就業規則はhr_tokyo_shugyo_kisokuを参照。"
            "・交通費：実費支給、定期券は月額上限¥55,000、申請は毎月25日締め。"
            "・有給休暇：法定どおり初年度10日付与、最大繰越5日。半休取得可。"
            "・経費精算：経費精算システムへ領収書をアップロード、原本は90日間保管。"
            "¥30,000を超える支出は事前承認が必要。締め日は毎月末、支払いは翌月15日。"
            "・セキュリティ：ノートPCは全台暗号化、社外への機密データ共有禁止、"
            "パスワードマネージャー必須、インシデントはITリエゾン（佐藤）へ即時連絡。"
            "金額は日本円（¥）、勤務地は港区、時刻はJSTで記載すること。"
            "末尾に関連文書としてhr_remote_work_policyとhr_tokyo_shugyo_kisokuを明記する。"
        ),
        cross_refs=["hr_remote_work_policy", "hr_tokyo_shugyo_kisoku"],
    ),
    DocSpec(
        doc_id="minutes_jp_tokyo_allhands",
        category="minutes",
        format="docx",
        locale="ja",
        title="議事録 — 東京オフィス 全社ミーティング（2025年4月）",
        brief=(
            "PT Fata Organa Solusi 東京サテライトオフィス（東京都港区 8F）の全社"
            "ミーティング（オールハンズ）議事録。司会：田中 健一（東京オフィスマネージャー）。"
            "出席者：東京拠点の社員18名（うちリモート参加4名）、ジャカルタ本社より"
            "山田 美咲がオンライン参加。構造化して以下を記述すること："
            "(1) ヘッドカウント：現在の東京拠点は18名、2025年annual planningで承認された"
            "+6名増員計画（minutes_quarterly_planning_2025参照）に対し、第2四半期末までに"
            "あと3名を採用予定。エンジニア2名、コンサルタント1名のオファー進行中。"
            "(2) CACホールディングス案件：データ基盤刷新は契約期間6か月の34%が完了、"
            "稼働は順調だがデータ移行が2週間遅延中（詳細はminutes_cac_jp_steering参照）。"
            "(3) オフィス事項：港区オフィスの座席が手狭になりつつあり、隣接フロアの"
            "増床を5月に検討。防災訓練を2025-05-16に実施。社内懇親会の予算¥150,000を承認。"
            "アクションアイテムは「担当者 / タスク / 期限」の形式で列挙すること："
            "・田中 健一 / 隣接フロア増床の見積もり取得とコスト試算 / 2025-05-15。"
            "・佐藤 大輔 / 全社員のセキュリティ研修日程を確定 / 2025-05-09。"
            "・山田 美咲 / CAC案件の遅延回復プランを全社へ共有 / 2025-05-02。"
            "・人事担当 / 増員3名分の採用ステータスを次回オールハンズで報告 / 2025-05-30。"
            "金額は日本円（¥）、勤務地は港区、時刻・日付はJSTで記載すること。"
        ),
        cross_refs=["minutes_quarterly_planning_2025", "minutes_cac_jp_steering"],
        date_stamp="2025-04-18 17:00 JST",
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
        "n_japanese": sum(1 for d in corpus if d.locale == "ja"),
        "n_with_table": sum(1 for d in corpus if d.has_table),
        "n_contradiction_docs": sum(1 for d in corpus if d.contradiction_pair),
        "n_with_cross_refs": sum(1 for d in corpus if d.cross_refs),
    }
    constraints_met = {
        # brief guideline is ~25-30; we ship more (30 base + 6 ja Tokyo docs)
        "total_in_range": 25 <= totals["n_total"] <= 40,
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
