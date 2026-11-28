"""Answer her questions during the explanation.

Three layers, in order:
1. Fixed answers for what borrowers actually ask (explain again more simply, how long, how much in hand,
   instalment, total, fee, insurance, interest, missed payment, "what else"). Instant, written by us.
2. Gemini, only if a key is set, for anything else. It is fenced: it gets the loan's facts and nothing else,
   and every number in its answer must be one of the loan's own numbers. If not, or if it is slow, its answer
   is thrown away. It can explain; it never judges her understanding.
3. Otherwise the question is noted for the lender.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from app.config import load_settings
from app.hi_numbers import parse_numbers
from app.lines import L
from app.loan import Loan
from app.numwords import hindi_words, rupees_en, rupees_hi

# gemini-2.5-flash-lite was retired for new accounts (404 on 28 Nov 2026); 3.5 flash-lite answered in about 1.6 s.
GEMINI_MODEL = "gemini-3.5-flash-lite"
# Gemini refuses request deadlines under 10 s, so the cut-off is enforced here: a slower answer is dropped.
GEMINI_TIMEOUT_S = 3.0
_pool = ThreadPoolExecutor(max_workers=4)
_DONT_KNOW = re.compile(r"नहीं पता|पता नहीं|don.?t know|do not know|not (?:in|given in) the facts|not mentioned", re.IGNORECASE)


def _intents(loan: Loan) -> list[tuple[str, dict]]:
    weeks_hi = hindi_words(loan.instalments)
    extra = loan.total_repayable - loan.sanctioned
    return [
        (
            # "explain again", "simpler", "I did not understand"
            r"phir se|fir se|dobara|ek aur baar|ek baar aur|aasan|asaan|aaram se|dheere|samajh nahi|samjh nahi|samjha nahi|"
            r"again|simpler|simple|slowly|didn.?t understand|फिर से|दोबारा|एक और बार|एक बार और|आसान|धीरे|समझ नहीं|समझा सक",
            L(
                f"ठीक है, धीरे-धीरे फिर से। लोन {rupees_hi(loan.sanctioned)} का है। पर पूरे पैसे हाथ में नहीं आएँगे। "
                f"फीस और बीमा के {rupees_hi(loan.deductions)} पहले कटेंगे। तो हाथ में {rupees_hi(loan.cash_in_hand)} आएँगे। "
                f"फिर हर हफ्ते {rupees_hi(loan.instalment)} जमा करने हैं, {weeks_hi} हफ्ते तक, यानी करीब एक साल।",
                f"All right, slowly once more. The loan is {rupees_en(loan.sanctioned)}, but not all of it reaches your hand. "
                f"Fee and insurance of {rupees_en(loan.deductions)} are cut first, so {rupees_en(loan.cash_in_hand)} reaches you. "
                f"Then you pay {rupees_en(loan.instalment)} every week for {loan.instalments} weeks, about one year.",
            ),
        ),
        (
            # how long, until when, how many instalments
            r"kab tak|kitne (?:din|hafte|mahine|saal)|kitni (?:kisht|kist|baar)|kab khatam|kitna time|kitne time|"
            r"how long|until when|how many (?:weeks|months|instalments|installments)|कब तक|कितने (?:दिन|हफ्ते|महीने|साल)|कितनी किस्त|कब खत्म",
            L(
                f"यह लोन {weeks_hi} हफ्ते का है, यानी करीब एक साल। हर हफ्ते एक किस्त, कुल {weeks_hi} किस्तें।",
                f"This loan runs {loan.instalments} weeks, about one year: one instalment every week, {loan.instalments} in all.",
            ),
        ),
        (
            # what else, anything else, besides the instalment
            r"aur kya|aur kuch|kya aur|alawa|alaava|baaki|bakki|what else|anything else|other than|और क्या|और कुछ|अलावा|बाकी",
            L(
                f"किस्त के अलावा तीन बातें याद रखिए। पहली, हाथ में {rupees_hi(loan.cash_in_hand)} आएँगे, पूरे {rupees_hi(loan.sanctioned)} नहीं। "
                f"दूसरी, कुल {rupees_hi(loan.total_repayable)} लौटाने हैं, यानी {rupees_hi(extra)} ज़्यादा। "
                "तीसरी, अगर कोई आपसे अलग से पैसे माँगे, तो वह गलत है, और आप सीधे लेंडर से शिकायत कर सकती हैं।",
                f"Besides the instalment, remember three things. One, {rupees_en(loan.cash_in_hand)} reaches your hand, not the full "
                f"{rupees_en(loan.sanctioned)}. Two, you repay {rupees_en(loan.total_repayable)} in all, {rupees_en(extra)} more. "
                "Three, if anyone asks you for extra money, that is wrong, and you can complain to the lender directly.",
            ),
        ),
        (
            r"haath mein|hath mein|kitne (?:milenge|milega|paise milenge)|kitna milega|in hand|how much (?:do i|will i) get|हाथ में|कितने मिलेंगे|कितना मिलेगा",
            L(
                f"हाथ में {rupees_hi(loan.cash_in_hand)} आएँगे, क्योंकि {rupees_hi(loan.deductions)} फीस और बीमा में पहले कट जाएँगे।",
                f"{rupees_en(loan.cash_in_hand)} reaches your hand, because {rupees_en(loan.deductions)} goes to fee and insurance first.",
            ),
        ),
        (
            r"\bkul\b|total|sab milakar|kitna (?:wapas|lautana|vapas)|कुल|सब मिलाकर|कितना वापस|कितना लौटाना",
            L(
                f"कुल {rupees_hi(loan.total_repayable)} लौटाने हैं। यानी आप {rupees_hi(loan.sanctioned)} लेकर {rupees_hi(extra)} ज़्यादा देंगी।",
                f"You repay {rupees_en(loan.total_repayable)} in all, {rupees_en(extra)} more than the {rupees_en(loan.sanctioned)} loan.",
            ),
        ),
        (
            r"kisht|kist|qist|emi|instal+ment|har hafte kitna|kitne (?:rupaye|rupay|paise) (?:jama|bharne|dene)|kitna jama|"
            r"किस्त|हर हफ्ते कितना|कितने रुपये (?:जमा|भरने|देने)|कितना जमा",
            L(
                f"हर हफ्ते {rupees_hi(loan.instalment)} की किस्त है, {weeks_hi} हफ्ते तक। महीने में नहीं, हर हफ्ते।",
                f"The instalment is {rupees_en(loan.instalment)} every week for {loan.instalments} weeks. Every week, not every month.",
            ),
        ),
    ]


def fixed_answer(text: str, loan: Loan) -> dict | None:
    from app.lines import faq  # fee, insurance, interest, missed payment

    for pattern, answer in _intents(loan) + faq(loan):
        if re.search(pattern, text, re.IGNORECASE):
            return answer
    return None


def allowed_numbers(loan: Loan) -> set[float]:
    values = {
        loan.sanctioned, loan.processing_fee, loan.insurance, loan.deductions, loan.cash_in_hand,
        loan.instalment, loan.instalments, loan.total_repayable, loan.total_repayable - loan.sanctioned,
        round(loan.apr_percent), loan.apr_percent, 1, 2, 3,
    }
    return {float(v) for v in values}


def numbers_are_from_the_loan(text: str, loan: Loan) -> bool:
    allowed = allowed_numbers(loan)
    return all(n.value in allowed for n in parse_numbers(text))


def _digits_to_hindi_words(text: str) -> str:
    """'32.8' -> 'बत्तीस दशमलव आठ', '6,940' -> 'छह हज़ार नौ सौ चालीस', so the voice reads amounts naturally."""

    def say(m: re.Match) -> str:
        whole, _, frac = m.group(0).replace(",", "").partition(".")
        words = hindi_words(int(whole))
        if frac:
            words += " दशमलव " + " ".join(hindi_words(int(d)) for d in frac)
        return words

    return re.sub(r"\d[\d,]*(?:\.\d+)?", say, text)


_clients: dict[str, object] = {}


def _client(api_key: str):
    """One client per key, reused, so each question does not pay for a new connection."""
    if api_key not in _clients:
        from google import genai
        from google.genai import types

        _clients[api_key] = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=15_000))
    return _clients[api_key]


def gemini_answer(question: str, loan: Loan, api_key: str) -> dict | None:
    """A short spoken answer from the loan's facts only, or None. Never raises, never waits past the cut-off."""
    future = _pool.submit(_gemini_answer, question, loan, api_key)
    try:
        return future.result(timeout=GEMINI_TIMEOUT_S)
    except FutureTimeout:
        return None


def _gemini_answer(question: str, loan: Loan, api_key: str) -> dict | None:
    try:
        from google import genai
        from google.genai import types

        facts = {
            "loan_amount": loan.sanctioned,
            "processing_fee": loan.processing_fee,
            "insurance": loan.insurance,
            "total_deductions": loan.deductions,
            "cash_in_hand": loan.cash_in_hand,
            "instalment": loan.instalment,
            "frequency": "every week",
            "number_of_instalments": loan.instalments,
            "total_repayable": loan.total_repayable,
            "extra_paid_over_loan": loan.total_repayable - loan.sanctioned,
            "yearly_cost_percent_apr": loan.apr_percent,
        }
        prompt = (
            "A low-literacy woman in India is asking about her microfinance loan. Answer in at most two short sentences "
            "of simple spoken Hindi (everyday words like fee, bima, kisht, haath mein; no formal words), using ONLY these "
            "facts and only their numbers, written as digits. No advice on whether to take the loan; never invent rules, "
            'fees or dates. If the facts do not answer it, reply {"hi": "", "en": ""}.\n'
            f"FACTS: {json.dumps(facts)}\nQUESTION: {question}\n"
            'Reply JSON: {"hi": "<Devanagari>", "en": "<same, simple English>"}'
        )
        resp = _client(api_key).models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0,
                thinking_config=types.ThinkingConfig(thinking_level="minimal"),  # about 0.7 s instead of 1.3 to 3 s
            ),
        )
        data = json.loads(resp.text)
        hi, en = str(data.get("hi", "")).strip(), str(data.get("en", "")).strip()
        if not hi or not en or _DONT_KNOW.search(hi) or _DONT_KNOW.search(en):
            return None
        # The fence: any number that is not the loan's own number means the answer is discarded.
        if not (numbers_are_from_the_loan(hi, loan) and numbers_are_from_the_loan(en, loan)):
            return None
        return L(_digits_to_hindi_words(hi), en)
    except Exception:
        return None


def answer(text: str, loan: Loan) -> tuple[dict | None, str]:
    """(answer line or None, source) where source is "fixed", "gemini" or "none"."""
    fixed = fixed_answer(text, loan)
    if fixed:
        return fixed, "fixed"
    key = load_settings().google_api_key
    if key:
        generated = gemini_answer(text, loan, key)
        if generated:
            return generated, "gemini"
    return None, "none"


def warm() -> None:
    """Open the Gemini connection in the background when a session starts, so her first question is not slow."""
    key = load_settings().google_api_key
    if not key:
        return

    def _touch() -> None:
        try:
            _client(key).models.get(model=GEMINI_MODEL)
        except Exception:
            pass

    _pool.submit(_touch)
