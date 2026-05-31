"""Golden-set loader — verifies the brief's evaluation_set.json schema."""

from __future__ import annotations

from klerk.eval.golden import by_category, load, load_brief_set
from klerk.synth.specs import CORPUS


def test_brief_set_has_20_items():
    items = load_brief_set()
    # 22 total = the brief-mandated 20 + 2 beyond-brief Japanese items
    assert len(items) == 22
    assert len([i for i in items if i.category != "japanese"]) == 20


def test_distribution_matches_brief():
    items = load_brief_set()
    grouped = by_category(items)
    assert len(grouped["factual"]) == 8
    assert len(grouped["multi_hop"]) == 5
    assert len(grouped["conflict"]) == 3
    assert len(grouped["bahasa"]) == 2
    assert len(grouped["trick"]) == 2
    assert len(grouped["japanese"]) == 2  # beyond brief


def test_item_fields_populated():
    for item in load_brief_set():
        assert item.id
        assert item.question
        assert item.locale in ("en", "id", "ja")
        assert item.category in ("factual", "multi_hop", "conflict", "bahasa", "trick", "japanese")
        assert isinstance(item.expected_doc_ids, list)
        assert isinstance(item.expected_substrings, list)
        assert isinstance(item.should_say_dont_know, bool)


def test_trick_items_flagged_correctly():
    items = load_brief_set()
    grouped = by_category(items)
    for item in grouped["trick"]:
        assert item.should_say_dont_know is True
        assert item.expected_doc_ids == []
    for item in grouped["factual"] + grouped["multi_hop"] + grouped["conflict"]:
        assert item.should_say_dont_know is False
        assert len(item.expected_doc_ids) >= 1


def test_locale_filter_returns_only_bahasa():
    items = load(locale="id")
    assert len(items) == 2  # Q17, Q18
    assert all(i.locale == "id" for i in items)


def test_locale_filter_returns_english_subset():
    items = load(locale="en")
    assert len(items) == 18  # 20 - 2 Bahasa
    assert all(i.locale == "en" for i in items)


def test_expected_doc_ids_point_to_real_corpus_docs():
    """Every non-trick item should reference at least one real corpus doc."""
    corpus_ids = {d.doc_id for d in CORPUS}
    for item in load_brief_set():
        if item.should_say_dont_know:
            continue
        for doc_id in item.expected_doc_ids:
            assert doc_id in corpus_ids, (
                f"{item.id} references unknown corpus doc: {doc_id}"
            )


def test_conflict_items_reference_contradicting_pairs():
    """Conflict items should target docs that ARE in a contradicting pair."""
    items = load_brief_set()
    grouped = by_category(items)
    pair_doc_ids: set[str] = set()
    for d in CORPUS:
        if d.contradiction_pair:
            pair_doc_ids.update(d.contradiction_pair)
    for item in grouped["conflict"]:
        for doc_id in item.expected_doc_ids:
            assert doc_id in pair_doc_ids, (
                f"Conflict {item.id} references {doc_id} which is not in a "
                "contradicting pair — check evaluation_set.json against the corpus plan."
            )


def test_kind_alias_returns_category():
    """Backwards-compat: the legacy `.kind` accessor still works."""
    items = load_brief_set()
    assert items[0].kind == items[0].category
