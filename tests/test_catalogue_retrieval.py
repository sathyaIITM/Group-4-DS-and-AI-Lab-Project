"""Catalogue retrieval: glossary expansion, and the ranking on the released tables."""

from __future__ import annotations

import pytest

from analyst.retrieval.catalogue import GLOSSARY, expand_query, load_glossary
from analyst.retrieval.knowledge import PROCESSED


def test_glossary_adds_english_terms_for_whole_words_only() -> None:
    glossary = [("berozgari", "unemployment rate"), ("dar", "rate")]
    assert expand_query("Bihar ki berozgari dar?", glossary) == (
        "Bihar ki berozgari dar? unemployment rate rate"
    )
    assert expand_query("Darbhanga rainfall", glossary) == "Darbhanga rainfall"


def test_released_glossary_has_unique_terms() -> None:
    terms = [term for term, _ in load_glossary(GLOSSARY)]
    assert terms and len(terms) == len(set(terms))


@pytest.mark.skipif(not (PROCESSED / "catalogue.json").exists(), reason="needs the released tables")
def test_ranking_finds_hinglish_and_indicator_level_questions() -> None:
    from analyst.retrieval.catalogue import rank_tables

    top = [d for d, _ in rank_tables("Jharkhand ki berozgari dar 2019 mein kitni rahi?", 4)][:4]
    assert "plfs_state_ur_usual_status" in top
    top = [d for d, _ in rank_tables("Households in Kozhikode using clean cooking fuel", 4)][:4]
    assert "nfhs5_district_indicators" in top


def test_slots_keep_every_slot_table_and_fill_from_the_ranking() -> None:
    from analyst.retrieval.catalogue import _with_slots

    ranked = [("a", 0.5), ("b", 0.4), ("c", 0.3), ("s1", 0.2), ("d", 0.1), ("s2", 0.05)]
    top = [d for d, _ in _with_slots(ranked, ["s1", "s2"], 4)][:4]
    assert top == ["a", "b", "s1", "s2"]  # s1 is kept, not pushed out by s2
    assert _with_slots(ranked, ["a"], 4) == ranked  # already in: unchanged
    capped = [d for d, _ in _with_slots(ranked, ["x", "y", "z", "w"], 4)][:4]
    assert capped[0] == "a" and len(set(capped) & {"x", "y", "z", "w"}) == 3


@pytest.mark.skipif(not (PROCESSED / "catalogue.json").exists(), reason="needs the released tables")
def test_place_names_point_to_the_tables_that_hold_them() -> None:
    from analyst.retrieval.catalogue import place_ranking

    assert place_ranking("Rain in Vidarbha in July 2016") == ["imd_subdivision_monthly_rainfall"]
    assert "imd_subdivision_monthly_rainfall" in place_ranking("2017 monsoon in West Rajasthan")
    assert place_ranking("IMR for Jammu and Kashmir in 2018") == []  # the State, not the district
    assert place_ranking("the north-east monsoon in Tamil Nadu") == []
    assert "mandi_daily_prices" in place_ranking("Onion price at Lasalgaon")
