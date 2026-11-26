import copy

import pytest

from app.flow import Session, yes_no
from app.grade import grade
from app.loan import SAMPLE_LOAN
from app.record import verify


def says(events):
    return [e for e in events if e["type"] == "say"]


def facts(events):
    return {e["fact"]: e["status"] for e in events if e["type"] == "fact"}


def to_teachback(s: Session):
    s.start()
    s.hear("haan")
    return s.hear("aage")


# ---- yes and no ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected",
    [
        ("haan", True),
        ("haan ji", True),
        ("हाँ", True),
        ("yes, I agree", True),
        ("haan, main samajh gayi aur sahmat hoon", True),
        ("nahi", False),
        ("नहीं", False),
        ("nahi, kisi ne nahi maanga", False),
        ("haan, ek aadmi ne paise maange the", True),
        ("no", False),
        ("hmm", None),
        ("", None),
    ],
)
def test_yes_no(text, expected):
    assert yes_no(text) is expected


# ---- grading -------------------------------------------------------------------------------
def test_classic_miss_is_caught_in_her_words():
    v = grade("pachaas hazaar haath mein aayenge aur har mahine hazaar rupaye bharne hain", SAMPLE_LOAN)
    assert v["cash_in_hand"].status == "red"
    assert v["cash_in_hand"].said == 50000
    assert v["frequency"].status == "red"
    assert v["instalment"].status == "amber"


def test_correct_teachback_is_all_green():
    v = grade(
        "haath mein adtaalis hazaar chaar sau das aayenge, ek hazaar fee aur paanch sau nabbe bima katega, "
        "har hafte ek hazaar pachaanve bharna hai, kul chhappan hazaar nau sau chaalis wapas karna hai",
        SAMPLE_LOAN,
    )
    assert {f: x.status for f, x in v.items()} == {
        "cash_in_hand": "green",
        "deductions": "green",
        "instalment": "green",
        "frequency": "green",
        "total": "green",
    }


def test_bare_number_answers_the_question_asked():
    assert grade("48410", SAMPLE_LOAN, target="cash_in_hand")["cash_in_hand"].status == "green"
    assert grade("gyarah sau", SAMPLE_LOAN, target="instalment")["instalment"].status == "green"
    assert grade("pata nahi", SAMPLE_LOAN, target="total")["total"].status == "grey"


def test_one_deduction_only_is_amber():
    assert grade("ek hazaar fee katega", SAMPLE_LOAN)["deductions"].status == "amber"


def test_week_count_is_not_read_as_rupees():
    v = grade("har hafte 1095, 52 hafte tak", SAMPLE_LOAN)
    assert v["instalment"].status == "green"
    assert "cash_in_hand" not in v


# ---- the whole conversation ----------------------------------------------------------------
def test_happy_path_seals_a_verifiable_record():
    s = Session()
    ev = to_teachback(s)
    assert s.state == "teachback"
    ev = s.hear(
        "haath mein 48,410 aayenge, 1590 kat jaayega, har hafte 1095 dena hai, kul 56,940 wapas karna hai"
    )
    assert set(facts(ev).values()) == {"green"}
    assert s.state == "private"
    s.hear("nahi")
    ev = s.hear("haan, main samajh gayi aur sahmat hoon")
    rec = [e for e in ev if e["type"] == "record"][0]["record"]
    assert rec["consent"] == "given"
    assert rec["understood_all"] is True
    assert rec["extra_money_reported"] is False
    assert verify(rec["entries"], rec["seal_sha256"])


def test_miss_is_repaired_then_rechecked_with_a_fresh_question():
    s = Session()
    to_teachback(s)
    ev = s.hear("pachaas hazaar haath mein aayenge")
    assert facts(ev)["cash_in_hand"] == "red"
    spoken = " ".join(e["en"] for e in says(ev))
    assert "You said 'pachaas hazaar'" in spoken
    assert "48,410" in spoken
    assert s.target == "cash_in_hand"
    ev = s.hear("adtaalis hazaar chaar sau das")
    assert facts(ev)["cash_in_hand"] == "green"
    assert s.target == "deductions"  # next unsaid fact is asked, not assumed


def test_two_failed_rounds_hand_over_to_a_human_and_never_block():
    s = Session()
    to_teachback(s)
    s.hear("pachaas hazaar haath mein")
    s.hear("pachaas hazaar")
    ev = s.hear("pachaas hazaar")
    assert facts(ev)["cash_in_hand"] == "unclear"
    assert any(e["type"] == "case" and e["case"] == "CALLBACK" for e in ev)


def test_extra_money_report_creates_a_hold_for_the_grievance_officer():
    s = Session()
    to_teachback(s)
    s.hear("haath mein 48410, 1590 kata, har hafte 1095, kul 56940")
    ev = s.hear("haan, agent ne paanch sau rupaye maange")
    assert any(e["type"] == "case" and e["case"] == "HOLD_REVIEW" for e in ev)
    assert s.extra_money_reported is True


def test_question_during_explanation_gets_a_fixed_answer():
    s = Session()
    s.start()
    s.hear("haan")
    ev = s.hear("bima kyun lagta hai?")
    assert "insurance" in says(ev)[0]["en"].lower()
    assert s.state == "explain"


def test_unknown_question_is_passed_to_the_lender_not_guessed():
    s = Session()
    s.start()
    s.hear("haan")
    s.hear("kya main jaldi poora loan chuka sakti hoon?")
    assert s.questions == ["kya main jaldi poora loan chuka sakti hoon?"]


def test_saying_no_at_the_start_ends_politely():
    s = Session()
    s.start()
    ev = s.hear("nahi")
    assert s.done and s.consent == "not_started"
    assert any(e["type"] == "record" for e in ev)


def test_english_mode_speaks_english():
    s = Session(lang="en")
    ev = s.start()
    assert says(ev)[0]["text"].startswith("Hello, I am Samjho")


def test_tampering_with_the_log_breaks_the_seal():
    s = Session()
    to_teachback(s)
    s.hear("haath mein 48410, 1590 kata, har hafte 1095, kul 56940")
    s.hear("nahi")
    rec = s.hear("haan")[-1]["record"]
    entries = copy.deepcopy(rec["entries"])
    assert verify(entries, rec["seal_sha256"])
    for e in entries:
        if e["kind"] == "verdict" and e["fact"] == "cash_in_hand":
            e["status"] = "red"
    assert not verify(entries, rec["seal_sha256"])


def test_aur_splits_clauses_so_each_number_gets_its_own_cue():
    v = grade("pachaas hazaar haath mein aayenge aur har mahine hazaar rupaye bharne hain", SAMPLE_LOAN)
    assert v["instalment"].said == 1000
    assert v["cash_in_hand"].said == 50000


def test_record_amounts_are_integers_so_a_browser_copy_still_verifies():
    import json

    s = Session()
    to_teachback(s)
    s.hear("haath mein 48410, 1590 kata, har hafte 1095, kul 56940")
    s.hear("nahi")
    rec = s.hear("haan")[-1]["record"]
    floats = [e["said"] for e in rec["entries"] if isinstance(e.get("said"), float)]
    assert floats == []
    # A browser re-serialises the JSON; simulate the round trip and check the seal still holds.
    entries = json.loads(json.dumps(rec["entries"]))
    assert verify(entries, rec["seal_sha256"])


def test_record_counts_first_answers_and_the_result_after_repair():
    s = Session()
    to_teachback(s)
    s.hear("pachaas hazaar haath mein aayenge, har mahine hazaar")  # cash red, freq red, instalment amber
    s.hear("adtaalis hazaar chaar sau das")  # cash repaired
    s.hear("pandrah sau nabbe")  # deductions, first answer, right
    s.hear("ek hazaar pachaanve")  # instalment repaired
    s.hear("agle hafte")  # frequency repaired
    s.hear("chhappan hazaar nau sau chaalis")  # total, first answer, right
    s.hear("nahi")
    rec = s.hear("haan")[-1]["record"]
    assert rec["right_first_answer"] == 2
    assert rec["right_after_samjho"] == 5
    assert rec["first_answer"]["cash_in_hand"] == "red"


def test_schedule_is_quoted_in_her_words_not_our_label():
    assert grade("har mahine hazaar", SAMPLE_LOAN)["frequency"].quote == "har mahine"
    assert grade("mahine nahi, har hafte", SAMPLE_LOAN)["frequency"].quote == "har hafte"
