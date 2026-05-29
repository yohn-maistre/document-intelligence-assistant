"""Pydantic schema roundtrip — every tool's input/output validates cleanly."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from klerk.agent.schemas import (
    Adjudication,
    CitedAnswer,
    ContradictionFinding,
    DecomposedQuery,
    DraftedSection,
    Entity,
    ExtractedGraph,
    GroundingJudgment,
    ProposalScope,
    ProposalSection,
    Relation,
    RubricScores,
)


def test_decomposed_query_constraints() -> None:
    DecomposedQuery(sub_questions=["one"])
    DecomposedQuery(sub_questions=["a", "b", "c", "d"])
    with pytest.raises(ValidationError):
        DecomposedQuery(sub_questions=[])  # min_length=1
    with pytest.raises(ValidationError):
        DecomposedQuery(sub_questions=["a", "b", "c", "d", "e"])  # max_length=4


def test_grounding_judgment_score_bounds() -> None:
    GroundingJudgment(score=0.0)
    GroundingJudgment(score=1.0)
    with pytest.raises(ValidationError):
        GroundingJudgment(score=1.1)
    with pytest.raises(ValidationError):
        GroundingJudgment(score=-0.1)


def test_cited_answer_defaults() -> None:
    a = CitedAnswer(answer="Acme parental leave is 16 weeks [hr_policy_acme:0].")
    assert a.citations == []
    assert a.locale == "und"
    assert a.confidence == 0.0


def test_entity_type_literal() -> None:
    Entity(id="acme_corp", type="organization", name="Acme Corp", aliases=["Acme"])
    with pytest.raises(ValidationError):
        Entity(id="x", type="planet", name="x")  # type: ignore[arg-type]


def test_extracted_graph_roundtrip() -> None:
    g = ExtractedGraph(
        entities=[
            Entity(id="acme", type="organization", name="Acme Corp"),
            Entity(id="hr_policy_2026", type="policy", name="HR Policy 2026"),
        ],
        relations=[
            Relation(source="acme", target="hr_policy_2026", verb="publishes", evidence_chunk="hr_policy_acme:0"),
        ],
    )
    json_str = g.model_dump_json()
    g2 = ExtractedGraph.model_validate_json(json_str)
    assert g2.entities[0].id == "acme"
    assert g2.relations[0].verb == "publishes"


def test_proposal_scope_section_constraints() -> None:
    ProposalScope(
        sections=[
            ProposalSection(title="Intro", bullets=["context", "scope"]),
            ProposalSection(title="Findings", bullets=["one"]),
        ]
    )
    with pytest.raises(ValidationError):
        ProposalScope(sections=[])  # min_length=1


def test_drafted_section_drafter_literal() -> None:
    DraftedSection(section_title="Intro", drafter_id="A", body="...")
    DraftedSection(section_title="Intro", drafter_id="B", body="...")
    with pytest.raises(ValidationError):
        DraftedSection(section_title="Intro", drafter_id="C", body="...")  # type: ignore[arg-type]


def test_adjudication_winner_literal() -> None:
    Adjudication(winner="A", reasons=["clearer"], improvement_for_winner="add example")
    with pytest.raises(ValidationError):
        Adjudication(winner="tie", reasons=["..."])  # type: ignore[arg-type]


def test_rubric_mean() -> None:
    r = RubricScores(
        faithfulness=1.0,
        citation_coverage=0.8,
        contradiction_freeness=0.9,
        section_coverage=0.7,
        tone=0.6,
    )
    assert abs(r.mean - 0.8) < 1e-9


def test_contradiction_finding_defaults() -> None:
    c = ContradictionFinding(consistent=True)
    assert c.contradiction == ""
    assert c.involved_chunks == []
