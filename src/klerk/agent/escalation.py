"""Capability A — Escalation Drafter.

When `/chat` retrieval surfaces nothing above the rerank threshold, or the
CRAG judge reports an ungrounded answer, klerk shouldn't bluff. It drafts
an escalation: a structured email to the human responsible for the policy
area, asking them to either answer directly or update the corpus.

Triggers (caller decides; this module just produces the draft):
  - retrieval returns < 2 chunks above the rerank threshold
  - CRAG judge confidence < 0.3
  - /chat answer contains a refusal phrase

Output is `EscalationDraft` (Pydantic) — directly serialisable to email
client / Slack / ticket payloads.
"""

from __future__ import annotations

from klerk.agent._models import EscalationDraft
from klerk.agent.llm_json import ask_json

_SYSTEM_PROMPT = """\
You are klerk, the Document Intelligence Assistant for PT Fata Organa Solusi.
A user just asked a question that klerk's retrieval could not answer with
high confidence. Your job is to draft an escalation email asking the right
human to step in. Do NOT attempt to answer the question yourself.

Output STRICT JSON matching this schema:
{
  "to": ["<role or email>"],
  "cc": ["<role or email>"],
  "subject": "<short, action-oriented subject line>",
  "body": "<2-4 paragraph body; reproduces the user's question, names the
           confidence problem, and asks for a specific answer or a corpus
           update>",
  "urgency": "low" | "medium" | "high",
  "rationale": "<1-sentence reason klerk thinks a human is needed>",
  "source_question": "<the user's verbatim question>",
  "confidence_observed": <float 0..1>
}

Routing hints (use as guidance for `to` / `cc`):
  - HR/leave/benefits/pay questions → ["hr@fata-organa.com"]
  - Security / data classification  → ["security@fata-organa.com"]
  - Engineering / SOPs              → ["engineering@fata-organa.com"]
  - Finance / budget                → ["finance@fata-organa.com"]
  - Anything CAC-Holding-related    → cc ["account@fata-organa.com"]
  - Unknown / out of scope          → ["info@fata-organa.com"]

Rules:
  - Output ONLY the JSON object. No prose, no markdown.
  - Subject line ≤ 80 chars.
  - Body is plain text, no markdown.
  - Urgency = "high" only if the question hints at production, security,
    or compliance impact. Otherwise "medium". "low" for FAQ-like asks.
"""


def draft(
    *,
    question: str,
    confidence: float,
    retrieved_excerpt: str = "",
    locale: str = "en",
) -> EscalationDraft:
    """Produce an escalation draft. Caller supplies the confidence the
    retrieval pipeline observed."""
    context_bits = [
        f"USER QUESTION:\n{question}",
        f"LOCALE: {locale}",
        f"OBSERVED CONFIDENCE: {confidence:.2f}",
    ]
    if retrieved_excerpt:
        context_bits.append(
            "WHAT KLERK DID FIND (may be irrelevant):\n" + retrieved_excerpt[:1200]
        )
    user_prompt = "\n\n".join(context_bits)

    return ask_json(
        EscalationDraft,
        system=_SYSTEM_PROMPT,
        user=user_prompt,
        locale=locale,
        max_tokens=700,
    )
