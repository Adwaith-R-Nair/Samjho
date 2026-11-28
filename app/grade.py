"""Decide, in code, whether what she said matches her loan.

Two steps, both deterministic:
1. assign(): find the numbers and the schedule in her words and decide which fact each one is about, using
   the words around it ("haath mein", "kat", "har hafte", "kul"). If Samjho just asked about one fact and she
   answers with a bare number, it is about that fact.
2. judge(): compare each assigned value with the loan's true value using the tolerances in app/loan.py.

An LLM may later suggest assignments (app/extract.py), but it never decides green or red.
"""

import re
from dataclasses import dataclass

from app.hi_numbers import ParsedNumber, parse_frequency, parse_numbers
from app.loan import FACTS, TOLERANCE, Loan, truth

CUES = {
    "cash_in_hand": r"haath|hath|haat|hand|mil(?:e|eg|eng|ta|te|ega|enge|egi)|aay?(?:e|eg|enge|ega|egi)|aaeg|cash|nakad|disburs|हाथ|मिल|आए|आये|आएंगे|आयेंगे|नकद",
    "deductions": r"\bkat|kaat|cut|fees?\b|bee?ma|insurance|charge|processing|deduct|कट|काट|फीस|बीमा|चार्ज",
    "instalment": r"kisht|kist|qist|emi\b|instal+ment|bhar(?:na|ni|ne|ungi|enge)|jama|\bden?[ae]\b|har haft|har mahin|har week|weekly|monthly|every (?:week|month)|हर हफ्ते|हर हफ़्ते|हर महीने|किस्त|किश्त|भर|जमा|देना|देने",
    "total": r"\bkul\b|total|milakar|mila ke|wapas|waapas|vapas|lauta|return|repay|कुल|वापस|लौटा|मिलाकर",
}
_CUE_RE = {fact: re.compile(pattern, re.IGNORECASE) for fact, pattern in CUES.items()}
# A number directly followed by these is a count of weeks/months/instalments, not rupees.
_COUNT_AFTER = re.compile(
    r"^\s*(?:hafte|hafton|haftey|week|weeks|mahine|mahino|month|months|kisht|kishte|kishton|installments?|instalments?|baar|हफ्ते|हफ़्ते|महीने|किस्त|किस्तें|बार)",
    re.IGNORECASE,
)
_WINDOW = 32  # characters either side of a number in which a cue word counts
# Clause breaks: a cue word only counts for numbers in the same clause, so in
# "har hafte 1095 dena hai, kul 56,940" the "kul" belongs to 56,940 and not to 1095.
_CLAUSE = re.compile(r"[,;:.!?।]|\b(?:aur|and|phir|then|fir)\b|और|फिर", re.IGNORECASE)
# Her own words for the schedule, quoted back to her ("aapne kaha 'har mahine'"), not our label "monthly".
_FREQ_WORDS = re.compile(
    r"(?:har|agle|ek|do|pandrah|15)\s+(?:hafte|hafta|mahine|mahina|din|week|month)\w*|weekly|monthly|"
    r"हर\s+(?:हफ्ते|हफ़्ते|महीने|दिन)|अगले\s+(?:हफ्ते|हफ़्ते|महीने)|हफ्ते|महीने|\bhafte\b|\bmahine\b|\bweek\b|\bmonth\b",
    re.IGNORECASE,
)
_MAX_DEDUCTION_SHARE = 0.2  # a "deduction" bigger than this share of the loan is not a deduction


@dataclass(frozen=True)
class Evidence:
    fact: str
    value: object  # float for amounts, str for frequency
    quote: str
    confident: bool = True
    alternatives: tuple = ()
    guessed: bool = False  # assigned by size alone, with no cue word nearby
    parts: int = 1  # deductions said as fee plus insurance


@dataclass(frozen=True)
class Verdict:
    fact: str
    status: str  # "green" | "amber" | "red" | "grey"
    said: object = None
    quote: str = ""
    reason: str = ""


def _freq_quote(text: str, freq: str) -> str:
    """The words she used for the schedule the parser settled on ("mahine nahi, har hafte" quotes "har hafte")."""
    marks = {"weekly": ("haft", "week", "हफ"), "monthly": ("mahin", "month", "महीन")}.get(freq, ())
    for m in _FREQ_WORDS.finditer(text):
        if any(k in m.group(0).lower() for k in marks):
            return m.group(0)
    return freq


def _clause_bounds(text: str, n: ParsedNumber) -> tuple[int, int]:
    lo, hi = 0, len(text)
    for m in _CLAUSE.finditer(text):
        if m.end() <= n.start:
            lo = m.end()
        elif m.start() >= n.end:
            hi = m.start()
            break
    return lo, hi


def _nearest_cue(text: str, n: ParsedNumber) -> str | None:
    best, best_dist = None, _WINDOW + 1
    c_lo, c_hi = _clause_bounds(text, n)
    lo, hi = max(c_lo, n.start - _WINDOW), min(c_hi, n.end + _WINDOW)
    for fact, rx in _CUE_RE.items():
        for m in rx.finditer(text, lo, hi):
            dist = n.start - m.end() if m.end() <= n.start else max(0, m.start() - n.end)
            if dist < best_dist:
                best, best_dist = fact, dist
    return best


def _is_count(text: str, n: ParsedNumber) -> bool:
    return n.value <= 120 and bool(_COUNT_AFTER.match(text[n.end :]))


def _closest_by_size(loan: Loan, value: float) -> str | None:
    best, best_gap = None, 0.45
    for fact in ("cash_in_hand", "deductions", "instalment", "total"):
        t = truth(loan, fact)
        gap = abs(value - t) / t
        if gap < best_gap:
            best, best_gap = fact, gap
    return best


def _gap(loan: Loan, fact: str, value: float) -> float:
    t = truth(loan, fact)
    return abs(value - t) / t


# Between "1000" and "95" in "1000. 95": speech to text sometimes cuts one spoken amount ("ek hazaar
# pachaanve") at a pause. Only a full stop or space may sit between the parts; a comma is a list.
_SPLIT_GAP = re.compile(r"^[\s.।]+$")


def _join_split_amounts(text: str, numbers: list[ParsedNumber]) -> list[ParsedNumber]:
    """Rejoin "1000. 95" into 1095: a round thousand (or hundred) then a smaller number after a pause."""
    out: list[ParsedNumber] = []
    for n in numbers:
        prev = out[-1] if out else None
        if prev is not None and _SPLIT_GAP.match(text[prev.end : n.start] or "x"):
            unit = 1000 if prev.value >= 1000 and prev.value % 1000 == 0 else 100 if prev.value % 100 == 0 else 0
            if unit and 0 < n.value < unit and n.value == int(n.value):
                out[-1] = ParsedNumber(
                    prev.value + n.value, text[prev.start : n.end], prev.start, n.end, prev.confident and n.confident, ()
                )
                continue
        out.append(n)
    return out


def assign(text: str, loan: Loan, target: str | None = None) -> dict[str, Evidence]:
    """Map her words to facts. `target` is the fact Samjho just asked about, if any."""
    found: dict[str, Evidence] = {}
    numbers = _join_split_amounts(text, [n for n in parse_numbers(text) if not _is_count(text, n)])

    deduction_parts: list[ParsedNumber] = []
    for n in numbers:
        cue = _nearest_cue(text, n)
        guessed = False
        answering = target and target != "frequency" and len(numbers) == 1
        if cue is None:
            if answering:
                cue = target
            else:
                cue, guessed = _closest_by_size(loan, n.value), True
        elif answering and cue != target and _gap(loan, target, n.value) < _gap(loan, cue, n.value):
            # Asked for the total, she says "56,000 kisht": one number, closer to what was asked than to
            # the fact her loose word points at. It answers the question.
            cue = target
        if cue is None:
            continue
        if cue == "deductions":
            if n.value <= loan.sanctioned * _MAX_DEDUCTION_SHARE:
                deduction_parts.append(n)
            continue
        # Keep the first thing she said about a fact, unless that was only a guess by size and this one has
        # her own cue word: in "50,000 mein se 1590 kam, baaki 48410 haath mein" the 50,000 is the loan, and
        # 48,410 "haath mein" is her answer (second real call, 28 Nov).
        if cue in found and not (found[cue].guessed and not guessed):
            continue
        found[cue] = Evidence(cue, n.value, n.raw, n.confident, n.alternatives, guessed)

    if deduction_parts:
        total = sum(p.value for p in deduction_parts)
        quote = " + ".join(p.raw for p in deduction_parts)
        confident = all(p.confident for p in deduction_parts)
        found["deductions"] = Evidence("deductions", total, quote, confident, (), False, len(deduction_parts))

    freq = parse_frequency(text)
    if freq:
        found["frequency"] = Evidence("frequency", freq, _freq_quote(text, freq))
    return found


def _status(loan: Loan, fact: str, value: float, parts: int) -> tuple[str, str]:
    t = truth(loan, fact)
    gap = abs(value - t) / t
    green, amber = TOLERANCE[fact]
    if gap <= green:
        return "green", ""
    if fact == "deductions" and parts == 1 and value in (float(loan.processing_fee), float(loan.insurance)):
        return "amber", "named only one deduction"
    if gap <= amber:
        return "amber", "close but not exact"
    return "red", "does not match the loan"


def judge(loan: Loan, fact: str, ev: Evidence | None) -> Verdict:
    if ev is None:
        return Verdict(fact, "grey", reason="not said")
    if fact == "frequency":
        ok = ev.value == loan.frequency
        return Verdict(fact, "green" if ok else "red", ev.value, ev.quote, "" if ok else f"said {ev.value}")

    status, reason = _status(loan, fact, float(ev.value), ev.parts)
    # A word that phone audio often mishears ("pachaas" or "pachpan") only matters if the other reading would
    # change the verdict. Then we ask her to say it again instead of guessing (fail closed).
    if not ev.confident and any(_status(loan, fact, float(a), ev.parts)[0] != status for a in ev.alternatives):
        return Verdict(fact, "amber", ev.value, ev.quote, "unclear word, confirm")
    return Verdict(fact, status, ev.value, ev.quote, reason)


def grade(text: str, loan: Loan, target: str | None = None) -> dict[str, Verdict]:
    """Verdicts only for the facts she actually spoke about (or the one she was asked)."""
    evidence = assign(text, loan, target)
    verdicts = {fact: judge(loan, fact, ev) for fact, ev in evidence.items() if fact in FACTS}
    if target and target not in verdicts:
        verdicts[target] = judge(loan, target, None)
    return verdicts
