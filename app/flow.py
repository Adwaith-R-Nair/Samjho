"""The conversation, as a state machine in code.

consent -> explain (questions allowed) -> teach-back -> for each fact not yet right: ask (if unsaid),
re-explain with her own words and re-check with a fresh question, at most two rounds, then hand to a human
-> private extra-money question -> spoken consent -> sealed record.

The same Session runs in text mode, in the browser voice channel and on a phone call: a channel only turns
her speech into text for hear() and speaks the "say" events back.
"""

import re
import uuid

from app import lines
from app.grade import Verdict, grade
from app.loan import FACTS, SAMPLE_LOAN, Loan
from app.record import Ledger

MAX_ROUNDS = 2

_YES = re.compile(
    r"\b(haan|haa|han|ha|hanji|haanji|ji|jee|yes|yeah|yep|ok|okay|theek|thik|bilkul|sahmat|shuru|chalo|sure)\b|हाँ|हां|जी|ठीक|सहमत|बिल्कुल",
    re.IGNORECASE,
)
_NO = re.compile(r"\b(nahi|nahin|nai|na|no|nope|mat|not)\b|नहीं|नही|ना\b", re.IGNORECASE)
_QUESTION = re.compile(
    r"\?|\b(kyun|kyu|kyon|kaise|kitna|kitni|kitne|kab|kaun|kya|why|what|how|when|who)\b|क्यों|क्या|कैसे|कितना|कितने|कब|कौन",
    re.IGNORECASE,
)
_MOVE_ON = re.compile(
    r"\b(aage|next|nahi|nahin|no|samajh|samjh|theek|thik|ok|okay|bas|chalo|done)\b|आगे|नहीं|ठीक|समझ|बस",
    re.IGNORECASE,
)


def yes_no(text: str) -> bool | None:
    """First clear yes or no wins: 'nahi, kisi ne nahi maanga' is no; 'haan, maanga tha' is yes."""
    y, n = _YES.search(text), _NO.search(text)
    if y and n:
        return y.start() < n.start()
    if y:
        return True
    if n:
        return False
    return None


class Session:
    def __init__(self, loan: Loan = SAMPLE_LOAN, lang: str = "hi") -> None:
        self.id = uuid.uuid4().hex[:12]
        self.loan = loan
        self.lang = lang if lang in ("hi", "en") else "hi"
        self.state = "consent"
        self.verdicts: dict[str, Verdict] = {f: Verdict(f, "grey") for f in FACTS}
        self.rounds = {f: 0 for f in FACTS}
        self.asked: set[str] = set()
        self.target: str | None = None
        self.questions: list[str] = []
        self.extra_money_reported: bool | None = None
        self.consent: str | None = None
        self.ledger = Ledger()
        self._out: list[dict] = []

    # ---- events -------------------------------------------------------------------------------
    def _say(self, line: dict) -> None:
        self.ledger.append("said", hi=line["hi"], en=line["en"])
        self._out.append({"type": "say", "text": line[self.lang], "hi": line["hi"], "en": line["en"]})

    def _state(self, name: str) -> None:
        self.state = name
        self._out.append({"type": "state", "state": name})

    def _fact(self, v: Verdict) -> None:
        # Whole rupee amounts are stored as integers, so the record's JSON is byte-identical whether Python or a
        # browser writes it, and the downloaded record still verifies against its seal.
        if isinstance(v.said, float) and v.said.is_integer():
            v = Verdict(v.fact, v.status, int(v.said), v.quote, v.reason)
        self.verdicts[v.fact] = v
        self.ledger.append("verdict", fact=v.fact, status=v.status, said=v.said, quote=v.quote, reason=v.reason)
        self._out.append(
            {
                "type": "fact",
                "fact": v.fact,
                "status": v.status,
                "said": v.said,
                "quote": v.quote,
                "reason": v.reason,
                "round": self.rounds[v.fact],
            }
        )

    def _case(self, kind: str, detail: str) -> None:
        self.ledger.append("case", case=kind, detail=detail)
        self._out.append({"type": "case", "case": kind, "detail": detail})

    def _flush(self) -> list[dict]:
        out, self._out = self._out, []
        return out

    # ---- public API ---------------------------------------------------------------------------
    @property
    def done(self) -> bool:
        return self.state == "done"

    def start(self) -> list[dict]:
        self.ledger.append("session_start", loan_id=self.loan.loan_id, lang=self.lang)
        self._state("consent")
        self._say(lines.intro())
        return self._flush()

    def hear(self, text: str) -> list[dict]:
        text = (text or "").strip()
        if self.done:
            return []
        self.ledger.append("heard", text=text, state=self.state, target=self.target)
        self._out.append({"type": "heard", "text": text})
        if not text:
            self._say(lines.didnt_catch())
            return self._flush()
        handler = getattr(self, f"_on_{self.state}")
        handler(text)
        return self._flush()

    # ---- states -------------------------------------------------------------------------------
    def _on_consent(self, text: str) -> None:
        answer = yes_no(text)
        if answer is None:
            self._say(lines.didnt_catch())
        elif answer:
            self._state("explain")
            for line in lines.explain(self.loan):
                self._say(line)
        else:
            self.consent = "not_started"
            self._say(lines.not_started())
            self._finish()

    def _on_explain(self, text: str) -> None:
        if _QUESTION.search(text) and not re.fullmatch(r"\W*(aage|next|आगे)\W*", text, re.IGNORECASE):
            for pattern, answer in lines.faq(self.loan):
                if re.search(pattern, text, re.IGNORECASE):
                    self._say(answer)
                    self._say(lines.ask_more())
                    return
            self.questions.append(text)
            self.ledger.append("question_for_lender", text=text)
            self._say(lines.unknown_question())
            return
        self._state("teachback")
        self._say(lines.teachback())

    def _on_teachback(self, text: str) -> None:
        for fact, v in grade(text, self.loan).items():
            self._fact(v)
        right = sum(1 for v in self.verdicts.values() if v.status == "green")
        self._say(lines.praise(right, len(FACTS)))
        self._state("check")
        self._next()

    def _on_check(self, text: str) -> None:
        for fact, v in grade(text, self.loan, self.target).items():
            if fact == self.target or self.verdicts[fact].status != "green":
                self._fact(v)
        self._next()

    def _next(self) -> None:
        for fact in FACTS:
            v = self.verdicts[fact]
            if v.status in ("green", "unclear"):
                continue
            if v.status == "grey" and fact not in self.asked:
                self.asked.add(fact)
                self.target = fact
                self._say(lines.PROBE[fact])
                return
            if self.rounds[fact] < MAX_ROUNDS:
                self.rounds[fact] += 1
                self.target = fact
                self._say(lines.repair(self.loan, fact, v.quote, v.reason))
                self._say(lines.RECHECK[fact])
                return
            self._fact(Verdict(fact, "unclear", v.said, v.quote, "still not clear after two explanations"))
            label_hi, label_en = lines.FACT_LABEL[fact]
            self._case("CALLBACK", f"explain {label_en} again by phone")
            self._say(lines.unclear(label_hi, label_en))
        self.target = None
        self._state("private")
        self._say(lines.private_check())

    def _on_private(self, text: str) -> None:
        answer = yes_no(text)
        if answer is None:
            self._say(lines.didnt_catch())
            return
        self.extra_money_reported = answer
        if answer:
            self._case("HOLD_REVIEW", "borrower reported a demand for extra money or a different promise")
            self._say(lines.private_yes())
        else:
            self._say(lines.private_no())
        self._state("final_consent")
        self._say(lines.consent())

    def _on_final_consent(self, text: str) -> None:
        answer = yes_no(text)
        if answer is None:
            self._say(lines.didnt_catch())
            return
        self.consent = "given" if answer else "declined"
        self.ledger.append("consent", value=self.consent, words=text)
        self._say(lines.sealed() if answer else lines.declined())
        self._finish()

    def _finish(self) -> None:
        self._state("done")
        self.ledger.append("session_end")
        self._out.append({"type": "record", "record": self.record()})

    # ---- the sealed record -------------------------------------------------------------------
    def record(self) -> dict:
        return {
            "session_id": self.id,
            "loan_id": self.loan.loan_id,
            "language": self.lang,
            "facts": {
                f: {
                    "status": v.status,
                    "said": v.said,
                    "her_words": v.quote,
                    "explained_again": self.rounds[f],
                }
                for f, v in self.verdicts.items()
            },
            "understood_all": all(v.status == "green" for v in self.verdicts.values()),
            "extra_money_reported": self.extra_money_reported,
            "questions_for_lender": self.questions,
            "consent": self.consent,
            "entries": self.ledger.entries,
            "seal_sha256": self.ledger.head,
        }
