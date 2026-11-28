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


# ---- questions during the explanation (from Adwaith's first real-mic test, 28 Nov) ----------------
def _ask(text):
    s = Session()
    s.start()
    s.hear("haan")
    return s, says(s.hear(text))


@pytest.mark.parametrize(
    "question,expect_en",
    [
        ("एक और बार मुझे इसके बारे में समझा सकते हो क्या? थोड़े और आसान भाषा में।", "slowly once more"),
        ("ये मुझे कब तक चुकाना होगा?", "52 weeks"),
        ("किस्त के अलावा अब कुछ कहोगी मुझसे? इसके बारे में।", "Besides the instalment"),
        ("samajh nahi aaya", "slowly once more"),
        ("haath mein kitne milenge?", "Rs 48,410 reaches your hand"),
        ("bima kyun lagta hai?", "insurance"),
    ],
)
def test_real_questions_get_real_answers(question, expect_en):
    s, said = _ask(question)
    assert expect_en.lower() in said[0]["en"].lower()
    assert s.state == "explain"


def test_after_three_questions_samjho_moves_on_to_the_teachback():
    s = Session()
    s.start()
    s.hear("haan")
    s.hear("kab tak chukana hai?")
    s.hear("aur kya?")
    ev = s.hear("phir se samjhao")
    assert s.state == "teachback"
    assert "move on" in " ".join(e["en"] for e in says(ev)).lower()


def test_generated_answers_may_only_use_the_loans_own_numbers():
    from app.answer import numbers_are_from_the_loan

    assert numbers_are_from_the_loan("हर हफ्ते 1095 रुपये, 52 हफ्ते तक", SAMPLE_LOAN)
    assert not numbers_are_from_the_loan("हर महीने 4,500 रुपये", SAMPLE_LOAN)
    assert not numbers_are_from_the_loan("The penalty is Rs 200", SAMPLE_LOAN)


def test_a_recorded_session_says_so_aloud_before_anything_else():
    first = says(Session(recording=True).start())[0]
    assert "recorded for a demo" in first["en"] and "रिकॉर्ड" in first["hi"]
    assert "recorded" not in says(Session().start())[0]["en"]


# ---- from the first real phone call (28 Nov, the builder testing on his own mobile) ----------
# Speech to text wrote these exact strings; each one exposed a grading bug.
def test_an_amount_cut_at_a_pause_is_read_as_one_amount():
    v = grade("1000. 95 रुपये।", SAMPLE_LOAN, "instalment")
    assert v["instalment"].status == "green" and v["instalment"].said == 1095
    assert grade("48,000. 410", SAMPLE_LOAN, "cash_in_hand")["cash_in_hand"].said == 48410


def test_a_comma_is_a_list_not_one_amount():
    v = grade("1000, 95 रुपये", SAMPLE_LOAN, None)
    assert all(x.said != 1095 for x in v.values())


def test_a_small_number_before_a_round_one_is_not_joined():
    v = grade("ठीक है तो. 13. 50,000 रुपये मिलेंगे।", SAMPLE_LOAN, None)
    assert v["cash_in_hand"].said == 50000


def test_one_number_answers_the_question_even_with_a_loose_word():
    # Asked for the total, he said "56,000 kisht": closer to the total than to an instalment.
    v = grade("56,000 किस्त।", SAMPLE_LOAN, "total")
    assert v["total"].status == "green" and v["total"].said == 56000
    # But a number that fits the cued fact still goes there.
    assert grade("हर किस्त 1095", SAMPLE_LOAN, "total")["instalment"].status == "green"


def test_a_fact_handed_to_a_callback_is_not_graded_or_announced_again():
    s = Session()
    to_teachback(s)
    s.hear("pachaas hazaar haath mein")
    s.hear("pachaas hazaar")
    s.hear("pachaas hazaar")  # cash in hand now unclear, one CALLBACK
    ev = s.hear("pachaas hazaar haath mein aur kisht 900")
    assert facts(ev).get("cash_in_hand") != "red"
    assert not any(e["type"] == "case" and "cash" in e.get("detail", "") for e in ev)


# ---- from the second real phone call (28 Nov): a full session to the sealed record ------------
def test_the_loan_amount_said_first_does_not_block_her_cash_in_hand_answer():
    text = "हफ्ते। 50,000 रुपये में से। 1590. कम करने के बाद। बाकी 48410 रुपये हाथ में आएंगे। और उसके बाद 52 हफ्तों तक 1000।"
    v = grade(text, SAMPLE_LOAN, None)
    assert v["cash_in_hand"].status == "green" and v["cash_in_hand"].said == 48410
    assert v["deductions"].status == "green"


def test_a_cued_wrong_amount_still_counts_as_her_answer():
    # The classic miss must stay red: her own cue word, her own wrong number.
    assert grade("pachaas hazaar haath mein aayenge", SAMPLE_LOAN, None)["cash_in_hand"].status == "red"


def test_how_much_to_deposit_gets_the_fixed_instalment_answer():
    from app.answer import answer

    line, source = answer("हफ्ते। 52 हफ्तों तक कितने रुपये जमा करना है?", SAMPLE_LOAN)
    assert source == "fixed" and "1,095" in line["en"]


# ---- the seal covers the score, not only the log (found by running the video scripts) ---------
def _sealed_record():
    s = Session()
    to_teachback(s)
    s.hear("पचास हज़ार हाथ में आएँगे, हर महीने एक हज़ार पचानवे भरने हैं, कुल छप्पन हज़ार नौ सौ चालीस लौटाने हैं।")
    for answer in ("एक हज़ार", "पंद्रह सौ नब्बे", "अड़तालीस हज़ार चार सौ दस", "हर हफ्ते", "हर हफ्ते", "नहीं", "हाँ, मैं समझ गई और सहमत हूँ"):
        if s.state == "done":
            break
        ev = s.hear(answer)
    return next(e["record"] for e in ev if e["type"] == "record")


def test_an_untouched_record_verifies_after_a_json_round_trip():
    import json

    from app.record import verify_record

    rec = json.loads(json.dumps(_sealed_record(), ensure_ascii=False))
    assert verify_record(rec)


@pytest.mark.parametrize(
    "edit",
    [
        lambda r: r.__setitem__("right_first_answer", 5),
        lambda r: r["facts"]["cash_in_hand"].__setitem__("said", 48411),
        lambda r: r.__setitem__("consent", "declined"),
        lambda r: r.__setitem__("extra_money_reported", True),
    ],
)
def test_changing_the_score_or_a_fact_on_top_breaks_the_seal(edit):
    from app.record import verify_record

    rec = copy.deepcopy(_sealed_record())
    edit(rec)
    assert not verify_record(rec)


def test_a_record_without_a_sealed_summary_does_not_verify():
    from app.record import verify_record

    rec = _sealed_record()
    rec["entries"] = [e for e in rec["entries"] if e["kind"] != "summary"]
    assert not verify_record(rec)


@pytest.mark.parametrize("text", ["ना", "ना।", "ना जी, किसी ने नहीं माँगा"])
def test_na_on_its_own_is_no(text):
    assert yes_no(text) is False


def test_na_inside_a_word_is_not_no():
    assert yes_no("नाम बताइए") is None


# ---- natural answers to "if you pay this Monday, when is the next one due?" -------------------
@pytest.mark.parametrize(
    "text,expected",
    [("अगले सोमवार", "green"), ("agle somvaar ko", "green"), ("next Monday", "green"), ("सात दिन बाद", "green"),
     ("अगले महीने", "red"), ("next month", "red")],
)
def test_a_day_answers_the_schedule_question(text, expected):
    assert grade(text, SAMPLE_LOAN, "frequency")["frequency"].status == expected


def test_a_day_alone_is_not_a_schedule_when_nobody_asked():
    assert "frequency" not in {k for k, v in grade("अगले सोमवार", SAMPLE_LOAN, None).items() if v.status != "grey"}


def test_goodbye_only_promises_questions_reach_the_lender_when_there_are_some():
    s = Session()
    to_teachback(s)
    s.hear("adtaalis hazaar chaar sau das haath mein, pandrah sau nabbe kategi, har hafte ek hazaar pachaanve, kul chhappan hazaar nau sau chaalees")
    s.hear("नहीं")
    ev = s.hear("हाँ, मैं समझ गई और सहमत हूँ")
    bye = " ".join(e["en"] for e in says(ev))
    assert "sealed" in bye and "questions will reach" not in bye
