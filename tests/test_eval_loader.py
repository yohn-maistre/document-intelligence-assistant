"""Golden-set loader — no LLM deps."""

from __future__ import annotations

from klerk.eval.golden import load


def test_load_all_locales() -> None:
    items = load()
    assert len(items) >= 8  # 5 en + 5 id committed
    ids = {i.id for i in items}
    assert "en-single-001" in ids
    assert "id-single-001" in ids


def test_load_locale_filter() -> None:
    en = load(locale="en")
    id_ = load(locale="id")
    assert all(i.locale == "en" for i in en)
    assert all(i.locale == "id" for i in id_)
    assert {i.id for i in en}.isdisjoint({i.id for i in id_})


def test_item_fields_populated() -> None:
    for item in load():
        assert item.id
        assert item.question
        assert item.locale in ("en", "id")
        assert item.kind in ("single-doc", "multi-hop", "crag-trigger")
        assert isinstance(item.expected_chunks, list)
        assert isinstance(item.expected_substrings, list)


def test_seed_questions_target_expected_chunks() -> None:
    """Every golden item should reference at least one chunk that exists in the seed."""
    seed_doc_ids = {"hr_policy_acme", "kontrak_vendor_pelangi", "memo_internal_q1"}
    for item in load():
        for chunk_id in item.expected_chunks:
            doc_id = chunk_id.split(":")[0]
            assert doc_id in seed_doc_ids, f"{item.id} references unknown doc: {doc_id}"
