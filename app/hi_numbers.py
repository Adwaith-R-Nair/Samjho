"""Deterministic Hindi / Hinglish / English number and schedule parser for Samjho.

Input is codemix speech-to-text (Sarvam saaras:v4): Devanagari Hindi, romanized Hindi with
spelling variants, English number words, digits (Western or Indian grouping, Devanagari digits),
currency markers and filler words. Everything here is pure: no I/O, no network, no model calls.

Composition algorithm
1. normalize() maps the text one character to one character, so spans stay valid on the input.
2. The text is cut into tokens: digit groups, words, the rupee sign and the hard breaks "," and
   ".". Each word is reduced to a spelling key (romanized: chh->ch, w->v, z->j, ee->i, oo->u,
   ou->au, doubled letters collapsed, final "ah" -> "a"; Devanagari: nukta, anusvara,
   chandrabindu, visarga and vowel length dropped) and looked up in a single lexicon.
3. Prefix modifiers fuse with the next token: saade/sava/paune N become N+0.5, N+0.25, N-0.25;
   sava/paune directly before a multiplier become 1.25 and 0.75. dedh and dhai are the plain
   values 1.5 and 2.5. Weak words that double as ordinary words (ek, do, saath "with", ...) only
   count as numbers right before a multiplier, a currency word or a unit noun (hafte, kisht, saal).
4. Numbers are built greedily from left to right. A number is a run of groups
   [unit] [sau [unit]] followed by a big multiplier (hazaar < lakh < crore), with every big
   multiplier strictly smaller than the one before it, a unit after sau below 100 and a unit
   after a big multiplier below that multiplier. English "and" may sit after a multiplier, and an
   English tens word may absorb one unit word ("forty eight"). A token that breaks these rules
   (a filler word, currency, punctuation, a second bare unit, or a unit followed by a unit noun as
   in "pachaas hazaar baawan hafte") ends the number; the token may start the next one.
5. Words that 8 kHz audio often swaps (pachaas/pachpan, fifteen/fifty, ...) are re-evaluated with
   the swapped value. Every value that still composes becomes an alternative and the number is
   marked not confident, so the caller can re-ask instead of trusting it.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedNumber:
    value: float  # e.g. 48410.0
    raw: str  # the exact substring it came from
    start: int
    end: int
    confident: bool  # False if a known confusion pair could flip it
    alternatives: tuple[float, ...] = ()


# ---------------------------------------------------------------- spelling keys

_DEV_FOLD = {
    0x0958: "क", 0x0959: "ख", 0x095A: "ग", 0x095B: "ज",
    0x095C: "ड", 0x095D: "ढ", 0x095E: "फ", 0x095F: "य",
    0x093C: None, 0x0901: None, 0x0902: None, 0x0903: None, 0x200C: None, 0x200D: None,
    0x0940: "ि", 0x0942: "ु", 0x0908: "इ", 0x090A: "उ",
}


def _rkey(word: str) -> str:
    w = word.lower().replace("chh", "ch").replace("w", "v").replace("z", "j")
    w = w.replace("ee", "i").replace("oo", "u").replace("ou", "au")
    w = re.sub(r"(.)\1+", r"\1", w)
    return w[:-1] if w.endswith("ah") else w


def _key(word: str) -> str:
    if any("ऀ" <= c <= "ॿ" for c in word):
        return word.translate(_DEV_FOLD)
    return _rkey(word)


def _keys(words: str) -> frozenset[str]:
    return frozenset(_key(w) for w in words.split())


# ---------------------------------------------------------------- lexicon

_HI_ROMAN = """
0 shunya shoonya sunya; 1 ek; 2 do; 3 teen tin
4 char chaar; 5 paanch panch; 6 chhe chhah chah chhey; 7 saat sat
8 aath ath; 9 nau; 10 das dus; 11 gyarah gyara gyaarah
12 barah baarah bara baara; 13 terah tera; 14 chaudah chauda chouda chaudha; 15 pandrah pandra pandhrah
16 solah sola; 17 satrah satra sattrah; 18 atharah athara attharah aatharah; 19 unnis unees unnees unis
20 bees bis; 21 ikkis ikkees; 22 bais baais baees; 23 teis tais
24 chaubis chaubees chobis; 25 pachchis pacchis pachees pachis; 26 chhabbis chabbis chhabees; 27 sattais sattaees
28 atthais athais atthaees; 29 untis untees unatis; 30 tees tis; 31 ikattis ikattees iktees iktis
32 battis battees; 33 taintis tetis taitees taintees; 34 chautis chauntis chontis chauntees; 35 paintis paitis pentis paintees
36 chhattis chattis chhattees; 37 saintis saitis saintees; 38 adtis artis adtees aratis; 39 untalis untaalis unchalis
40 chalis chaalis chalees; 41 iktalis iktaalis ikatalis; 42 bayalis bayaalis beyalis; 43 taintalis taintaalis tentalis
44 chauvalis chawalis chauwalis chavalis chaualis; 45 paintalis paintaalis pentalis; 46 chhiyalis chhiyaalis chiyalis; 47 saintalis saintaalis
48 adtalis adtaalis artalis artaalis athtalis; 49 unchas unanchas unchaas; 50 pachas pachaas; 51 ikyavan ikyaavan ikkyavan ikyawan
52 bavan baawan bawan baavan; 53 tirpan tirepan; 54 chauvan chauwan chouvan; 55 pachpan pachapan
56 chhappan chappan; 57 sattavan sattaavan sattawan; 58 atthavan athavan atthaavan; 59 unsath unsaath unsat
60 saath sath; 61 iksath iksaath; 62 basath baasath; 63 tirsath tiresath
64 chausath chaunsath; 65 painsath painsaath; 66 chhiyasath chhiyaasath; 67 sadsath sarsath
68 adsath arsath adsaath; 69 unhattar unattar; 70 sattar; 71 ikhattar ikahattar
72 bahattar bahatar; 73 tihattar; 74 chauhattar; 75 pachhattar pachattar pachhatar
76 chhihattar chihattar; 77 satattar sathattar; 78 athattar athhattar; 79 unasi unaasi unyasi
80 assi asi; 81 ikyasi ikyaasi; 82 bayasi bayaasi; 83 tirasi tiraasi
84 chaurasi chauraasi; 85 pachasi pachaasi; 86 chhiyasi chhiyaasi; 87 sattasi sattaasi
88 athasi athaasi atthasi; 89 navasi nawasi navaasi; 90 nabbe nabe; 91 ikyanve ikyaanve
92 banve baanve; 93 tiranve tiraanve; 94 chauranve chauraanve; 95 pachanve pachaanve pachanave pachaanave
96 chhiyanve chhiyaanve; 97 sattanve sattaanve; 98 atthanve athanve atthaanve; 99 ninyanve ninyaanve
"""

_HI_DEV = """
0 शून्य; 1 एक; 2 दो; 3 तीन; 4 चार; 5 पांच पाँच
6 छह छः छै छे; 7 सात; 8 आठ; 9 नौ; 10 दस; 11 ग्यारह
12 बारह; 13 तेरह; 14 चौदह; 15 पंद्रह पन्द्रह; 16 सोलह; 17 सत्रह
18 अठारह; 19 उन्नीस; 20 बीस; 21 इक्कीस; 22 बाईस; 23 तेईस
24 चौबीस; 25 पच्चीस; 26 छब्बीस; 27 सत्ताईस; 28 अट्ठाईस अठ्ठाईस अठाईस; 29 उनतीस
30 तीस; 31 इकतीस इकत्तीस; 32 बत्तीस; 33 तैंतीस; 34 चौंतीस; 35 पैंतीस
36 छत्तीस; 37 सैंतीस; 38 अड़तीस; 39 उनतालीस उंतालीस; 40 चालीस; 41 इकतालीस
42 बयालीस; 43 तैंतालीस; 44 चवालीस चौवालीस; 45 पैंतालीस; 46 छियालीस; 47 सैंतालीस
48 अड़तालीस; 49 उनचास; 50 पचास; 51 इक्यावन; 52 बावन; 53 तिरपन तिरेपन
54 चौवन; 55 पचपन; 56 छप्पन; 57 सत्तावन; 58 अट्ठावन अठ्ठावन; 59 उनसठ
60 साठ; 61 इकसठ; 62 बासठ; 63 तिरसठ तिरेसठ; 64 चौंसठ; 65 पैंसठ
66 छियासठ; 67 सड़सठ सरसठ; 68 अड़सठ; 69 उनहत्तर; 70 सत्तर; 71 इकहत्तर
72 बहत्तर; 73 तिहत्तर; 74 चौहत्तर; 75 पचहत्तर; 76 छिहत्तर; 77 सतहत्तर
78 अठहत्तर; 79 उन्यासी उनासी उनयासी; 80 अस्सी; 81 इक्यासी; 82 बयासी; 83 तिरासी
84 चौरासी; 85 पचासी; 86 छियासी; 87 सत्तासी; 88 अठासी अट्ठासी; 89 नवासी
90 नब्बे; 91 इक्यानवे; 92 बानवे; 93 तिरानवे; 94 चौरानवे; 95 पचानवे पंचानवे
96 छियानवे; 97 सत्तानवे; 98 अट्ठानवे अठ्ठानवे; 99 निन्यानवे निन्यानबे
"""

_EN_WORDS = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen"
).split()
_EN_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
            "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_MULTS = {
    100.0: "sau hundred सौ",
    1e3: "hazaar hazar hajar hajaar hazzar thousand हज़ार हजार",
    1e5: "lakh lakhs lac lacs laakh लाख",
    1e6: "million",
    1e7: "crore crores karod karor करोड़ करोड",
}
_FRACTIONS = {1.5: "dedh derh डेढ़", 2.5: "dhai dhaai adhai ढाई अढ़ाई"}
_MODIFIERS = {0.5: "saade sade saadhe sadhe साढ़े", 0.25: "sava savaa sawa सवा",
              -0.25: "paune pone पौने"}
_CURRENCY = ("rs rupaye rupaiye rupay rupai rupee rupees rupiya rupya rupaya rupye inr "
             "रुपये रुपए रुपया रुपयों रूपए रु")
_HESITATION = "um umm uh uhh hm hmm er erm"

# Words that are also everyday words ("ek baat", "de do", "mere saath", "tera", "bara").
_WEAK_ROMAN = frozenset("ek do saath sath sat bara tera".split())
_WEAK_DEV = _keys("एक दो")

# Confusion pairs on 8 kHz phone audio, keyed by the value of the word as recognised.
# assi/athaasi (80/88) is left out: the extra syllable keeps them apart in practice.
_HI_CONFUSE = {50.0: (55.0,), 55.0: (50.0,), 60.0: (7.0,), 7.0: (60.0,), 70.0: (17.0,),
               17.0: (70.0,), 40.0: (44.0,), 44.0: (40.0,), 15.0: (75.0,), 75.0: (15.0,)}
_EN_CONFUSE = {float(t): (float((t - 10) * 10),) for t in range(13, 20)}
_EN_CONFUSE.update({float((t - 10) * 10): (float(t),) for t in range(13, 20)})


def _build_lexicon() -> dict[str, tuple[str, float, str]]:
    lex: dict[str, tuple[str, float, str]] = {}

    def add(words: str, entry: tuple[str, float, str]) -> None:
        for w in words.split():
            if lex.setdefault(_key(w), entry) != entry:
                raise ValueError(f"lexicon clash on {w!r}")

    for table in (_HI_ROMAN, _HI_DEV):
        for entry in re.split(r"[;\n]", table):
            if not entry.strip():
                continue
            n, *words = entry.split()
            add(" ".join(words), ("num", float(n), "hi"))
    for i, w in enumerate(_EN_WORDS):
        add(w, ("num", float(i), "en"))
    for w, v in _EN_TENS.items():
        add(w, ("num", float(v), "en"))
    for v, words in _MULTS.items():
        add(words, ("mult", v, ""))
    add("so", ("so", 100.0, "hi"))
    for v, words in _FRACTIONS.items():
        add(words, ("num", v, "hi"))
    for v, words in _MODIFIERS.items():
        add(words, ("mod", v, "hi"))
    add(_CURRENCY, ("cur", 0.0, ""))
    add(_HESITATION, ("hes", 0.0, ""))
    add("and", ("and", 0.0, "en"))
    return lex


_LEX = _build_lexicon()

# ---------------------------------------------------------------- schedule vocabulary

_WEEK = _keys("hafta hafte haftey hafton hapta hapte week weeks saptah "
              "हफ्ता हफ़्ता हफ्ते हफ़्ते हफ्तों हप्ता हप्ते सप्ताह")
_MONTH = _keys("mahina mahine mahino mahinon mahena mahene month months maah "
               "महीना महीने महीनों माह")
_DAY = _keys("din dino dinon day days दिन दिनों")
_YEAR = _keys("saal sal saalon baras varsh year years साल सालों वर्ष बरस")
_INST = _keys("kisht kishte kishten kishton kist kiste kisten installment installments "
              "instalment instalments emi emis किस्त किश्त किस्तें किश्तें किस्तों किश्तों ईएमआई")
_TIMES = _keys("baar बार")
_UNIT_NOUNS = _WEEK | _MONTH | _DAY | _YEAR | _INST | _TIMES
_PERIOD = {**{k: "week" for k in _WEEK}, **{k: "month" for k in _MONTH},
           **{k: "day" for k in _DAY}}
_DURATION = {**_PERIOD, **{k: "year" for k in _YEAR}}
_HAR = _keys("har every each per prati हर प्रति")
_NEG = _keys("nahi nahin nai nhi nahee not नहीं नही")
_NEG_BEFORE = _keys("not")
_ADJ: dict[str, tuple[str, bool]] = {}  # key -> (frequency, strong)
for _freq, _strong, _words in (
    ("weekly", True, "weekly haftawar haftavar saptahik साप्ताहिक"),
    ("monthly", True, "monthly masik maasik मासिक"),
    ("daily", True, "daily roz roj rozana rojana everyday रोज़ रोज रोज़ाना रोजाना प्रतिदिन"),
    ("fortnightly", True, "fortnightly pakhwada pakhvada पखवाड़ा"),
    ("fortnightly", False, "fortnight fortnights"),
):
    _ADJ.update({k: (_freq, _strong) for k in _keys(_words)})
_PERIOD_FREQ = {"week": "weekly", "month": "monthly", "day": "daily"}

for _k in (*_UNIT_NOUNS, *_HAR, *_NEG, *_ADJ):
    if _k in _LEX:
        raise ValueError(f"schedule word {_k!r} clashes with the number lexicon")

# ---------------------------------------------------------------- normalize + tokenize


def normalize(text: str) -> str:
    """Lowercase, map Devanagari digits to ASCII, turn punctuation noise into spaces.

    The output has exactly the same length as the input, so every index in it is an index into
    the original text. "," and "." are kept (digit grouping, decimals, hard breaks), the danda
    becomes ".", and the rupee sign is kept.
    """
    out = []
    for ch in text:
        o = ord(ch)
        if 0x0966 <= o <= 0x096F:
            out.append(chr(o - 0x0966 + 48))
        elif ch in "।॥":
            out.append(".")
        elif ch in ",.₹":
            out.append(ch)
        elif unicodedata.category(ch)[0] in "PSZ" or unicodedata.category(ch) == "Cc":
            out.append(" ")
        else:
            low = ch.lower()
            out.append(low if len(low) == 1 else ch)
    return "".join(out)


_TOKEN_RE = re.compile(
    r"(?P<numk>[0-9]+(?:\.[0-9]+)?k)(?![a-z0-9])"
    r"|(?P<num>[0-9]{1,3}(?:,[0-9]{3})+(?!,?[0-9])(?:\.[0-9]+)?"
    r"|[0-9]{1,3}(?:,[0-9]{2})+,[0-9]{3}(?!,?[0-9])(?:\.[0-9]+)?"
    r"|[0-9]{1,3}(?: [0-9]{3})+(?![0-9]|[,.][0-9])"
    r"|[0-9]+(?:\.[0-9]+)?)"
    r"|(?P<word>[a-z]+|[ऀ-ॿ‌‍]+)"
    r"|(?P<cur>₹)"
    r"|(?P<brk>[,.])"
)


@dataclass
class _Tok:
    kind: str  # num numk mult so mod and cur hes brk word
    key: str
    start: int
    end: int
    value: float = 0.0
    lang: str = ""  # "hi", "en" or "d" (digits)
    alts: tuple[float, ...] = ()
    weak: bool = False

    @property
    def tens(self) -> bool:
        return self.kind == "num" and self.lang == "en" and self.value >= 20

    @property
    def unit(self) -> bool:
        return self.kind == "num" and self.lang == "en" and 1 <= self.value <= 9


def _word_token(s: str, a: int, b: int) -> _Tok:
    k = _key(s)
    entry = _LEX.get(k)
    if entry is None:
        return _Tok("word", k, a, b)
    kind, value, lang = entry
    tok = _Tok(kind, k, a, b, value, lang)
    if kind == "num":
        tok.alts = (_HI_CONFUSE if lang == "hi" else _EN_CONFUSE).get(value, ())
        tok.weak = s in _WEAK_ROMAN or _key(s) in _WEAK_DEV
    return tok


def _next(toks: list[_Tok], i: int) -> int | None:
    for j in range(i + 1, len(toks)):
        if toks[j].kind != "hes":
            return j
    return None


def _prev(toks: list[_Tok], i: int) -> int | None:
    for j in range(i - 1, -1, -1):
        if toks[j].kind != "hes":
            return j
    return None


def _is_unit_noun(toks: list[_Tok], j: int | None) -> bool:
    return j is not None and toks[j].kind == "word" and toks[j].key in _UNIT_NOUNS


def _tokenize(text: str) -> list[_Tok]:
    raw: list[_Tok] = []
    for m in _TOKEN_RE.finditer(normalize(text)):
        s, a, b, g = m.group(), m.start(), m.end(), m.lastgroup
        if g == "numk":
            raw.append(_Tok("numk", s, a, b, float(s[:-1]) * 1000, "d"))
        elif g == "num":
            raw.append(_Tok("num", s, a, b, float(re.sub("[, ]", "", s)), "d"))
        elif g in ("cur", "brk"):
            raw.append(_Tok(g, s, a, b))
        else:
            raw.append(_word_token(s, a, b))
    # Fuse prefix modifiers (saade, sava, paune) with what follows them.
    toks: list[_Tok] = []
    i = 0
    while i < len(raw):
        t = raw[i]
        nxt = raw[i + 1] if i + 1 < len(raw) else None
        if t.kind == "mod":
            if nxt is not None and nxt.kind == "num" and nxt.value == int(nxt.value):
                toks.append(_Tok("num", t.key, t.start, nxt.end, nxt.value + t.value, "hi",
                                 tuple(x + t.value for x in nxt.alts)))
                i += 2
                continue
            if nxt is not None and nxt.kind == "mult" and t.value != 0.5:
                t = _Tok("num", t.key, t.start, t.end, 1 + t.value, "hi")
            else:
                t.kind = "word"
        toks.append(t)
        i += 1
    # Weak words only count before a multiplier, a currency word or a unit noun.
    for i, t in enumerate(toks):
        if t.kind == "num" and t.weak:
            j = _next(toks, i)
            if not (j is not None and toks[j].kind in ("mult", "cur") or _is_unit_noun(toks, j)):
                t.kind = "word"
    return toks


# ---------------------------------------------------------------- composition

_Item = tuple[str, float, bool, bool]  # kind, value, english tens, english unit


def _evaluate(items: list[_Item], final: bool = True) -> float | None:
    """Value of a token run, or None if the run is not one well formed number."""
    total = group = 0.0
    pending: float | None = None
    last_big = math.inf
    hundreds = tens_open = False
    prev = None
    for kind, v, tens, unit in items:
        if kind == "num":
            if pending is not None:
                if not (tens_open and unit and 20 <= pending <= 90 and pending % 10 == 0):
                    return None
                pending += v
                tens_open = False
            else:
                if prev is not None:
                    if prev not in ("mult", "so", "and") or v >= (100 if hundreds else last_big):
                        return None
                pending, tens_open = v, tens
        elif kind in ("mult", "so"):
            if kind == "so" and pending is None:
                return None
            if v == 100:
                if hundreds:
                    return None
                if pending is None:
                    if prev is not None:
                        return None
                    pending = 1.0
                if pending >= 100:
                    return None
                group += pending * 100
                hundreds = True
            else:
                if v >= last_big:
                    return None
                g = group + (pending or 0.0)
                if g == 0:
                    if prev is not None:
                        return None
                    g = 1.0
                if g >= 1000:
                    return None
                total += g * v
                group, hundreds, last_big = 0.0, False, v
            pending, tens_open = None, False
        elif kind == "and":
            if prev not in ("mult", "so"):
                return None
        elif kind == "numk":
            if prev is not None:
                return None
            total, last_big = v, 1000.0
        prev = kind
    if final:
        if prev == "and":
            return None
        if pending is not None and pending != int(pending) and (total or group):
            return None
    return total + group + (pending or 0.0)


def _items(toks: list[_Tok], idxs: list[int]) -> list[_Item]:
    return [(toks[i].kind, toks[i].value, toks[i].tens, toks[i].unit) for i in idxs]


def _unit_after_value(toks: list[_Tok], k: int) -> bool:
    """True if the value starting at token k ("baawan", "fifty two") is followed by a unit noun."""
    j = _next(toks, k)
    if toks[k].tens and j is not None and toks[j].unit:
        j = _next(toks, j)
    return _is_unit_noun(toks, j)


def _segment(toks: list[_Tok]) -> list[list[int]]:
    segs: list[list[int]] = []
    i = 0
    while i < len(toks):
        if toks[i].kind not in ("num", "numk", "mult"):
            i += 1
            continue
        idxs = [i]
        j = _next(toks, i)
        while j is not None:
            u, last = toks[j], toks[idxs[-1]]
            cand: list[int] | None = None
            if u.kind == "and":
                k = _next(toks, j)
                if k is not None and toks[k].kind == "num" and not _unit_after_value(toks, k):
                    cand = [j, k]
            elif u.kind in ("num", "mult", "numk"):
                if not (u.kind == "num" and last.kind in ("mult", "so") and _unit_after_value(toks, j)):
                    cand = [j]
            elif u.kind == "so" and last.kind == "num" and last.lang == "hi":
                cand = [j]
            if cand is None or _evaluate(_items(toks, idxs + cand), final=False) is None:
                break
            idxs += cand
            j = _next(toks, idxs[-1])
        while len(idxs) > 1 and _evaluate(_items(toks, idxs)) is None:
            idxs.pop()
        segs.append(idxs)
        i = idxs[-1] + 1
    return segs


def _analyse(text: str) -> tuple[list[_Tok], list[tuple[ParsedNumber, list[int]]]]:
    toks = _tokenize(text)
    found = []
    for idxs in _segment(toks):
        items = _items(toks, idxs)
        value = _evaluate(items)
        if value is None:
            continue
        alts: list[float] = []
        for pos, i in enumerate(idxs):
            for alt in toks[i].alts:
                swapped = list(items)
                swapped[pos] = (items[pos][0], alt, items[pos][2], items[pos][3])
                v = _evaluate(swapped)
                if v is not None and v != value and v not in alts:
                    alts.append(v)
        start, end = toks[idxs[0]].start, toks[idxs[-1]].end
        found.append((ParsedNumber(float(value), text[start:end], start, end,
                                   not alts, tuple(alts)), idxs))
    return toks, found


# ---------------------------------------------------------------- public API


def parse_numbers(text: str) -> list[ParsedNumber]:
    """All numbers in reading order. Fails closed: unclear words are skipped, never guessed."""
    return [pn for pn, _ in _analyse(text)[1]]


def _after_har(toks: list[_Tok], first: int) -> bool:
    p = _prev(toks, first)
    return p is not None and toks[p].key in _HAR


def parse_count(text: str) -> ParsedNumber | None:
    """The number of instalments: a number before kisht/EMI/baar, else before hafte/mahine/din.

    "ek saal" (years) is a duration, not a count, so it returns None; see parse_duration.
    Numbers after "har" ("har do hafte") describe frequency and are skipped.
    """
    fallback = None
    toks, found = _analyse(text)
    for pn, idxs in found:
        if _after_har(toks, idxs[0]):
            continue
        j = _next(toks, idxs[-1])
        if j is not None and toks[j].key in _ADJ:  # "52 weekly kisht"
            j = _next(toks, j)
        if j is None or toks[j].kind != "word":
            continue
        if toks[j].key in _INST or toks[j].key in _TIMES:
            return pn
        if fallback is None and toks[j].key in _PERIOD:
            fallback = pn
    return fallback


def parse_duration(text: str) -> tuple[float, str] | None:
    """First "<number> <period>" phrase as (value, unit), unit in year/month/week/day."""
    toks, found = _analyse(text)
    for pn, idxs in found:
        if _after_har(toks, idxs[0]):
            continue
        j = _next(toks, idxs[-1])
        if j is not None and toks[j].kind == "word" and toks[j].key in _DURATION:
            return pn.value, _DURATION[toks[j].key]
    return None


def _negated(toks: list[_Tok], first: int, last: int) -> bool:
    p = _prev(toks, first)
    if p is not None and toks[p].key in _NEG_BEFORE:
        return True
    j: int | None = last
    for _ in range(2):
        j = _next(toks, j)
        if j is None or toks[j].kind == "brk":
            return False
        if toks[j].key in _NEG:
            return True
    return False


def parse_frequency(text: str) -> str | None:
    """"weekly", "monthly", "fortnightly", "daily" or None.

    Rule when several cues appear:
    1. Drop negated cues: a cue followed within two words by nahi/nahin/not/नहीं, or preceded by
       "not" ("mahine nahi, har hafte" -> weekly).
    2. Strong cues beat weak ones. Strong: "har/every/per/prati <period>", "har do hafte",
       "har pandrah din", and adjectives (weekly, haftawar, saptahik, monthly, masik, daily, roz,
       fortnightly). Weak: a bare period noun ("hafte mein", "mahina", "ek hafte"), "15 din",
       "do hafte", "fortnight". A period noun after any other number ("52 hafte") is a duration.
    3. Among the remaining cues, pick the one closest (in characters) to an amount, i.e. a number
       not followed by a unit noun; ties and texts without amounts go to the earliest cue.
    """
    toks, found = _analyse(text)
    ends = {idxs[-1]: (pn, idxs) for pn, idxs in found}
    cues = []  # (start, end, frequency, strong, first token, last token)
    for j, t in enumerate(toks):
        if t.kind != "word":
            continue
        if t.key in _ADJ:
            freq, strong = _ADJ[t.key]
            first = j
            if _after_har(toks, j):
                first, strong = _prev(toks, j), True
            cues.append((toks[first].start, t.end, freq, strong, first, j))
            continue
        period = _PERIOD.get(t.key)
        if period is None:
            continue
        p = _prev(toks, j)
        num = ends.get(p) if p is not None else None
        first = j
        if num is not None:
            value, first = num[0].value, num[1][0]
            if (value == 2 and period == "week") or (value == 15 and period == "day"):
                freq = "fortnightly"
            elif value == 1 and period != "day":
                freq = _PERIOD_FREQ[period]
            else:
                continue
        else:
            freq = _PERIOD_FREQ[period]
        strong = _after_har(toks, first)
        if strong:
            first = _prev(toks, first)
        elif num is None and period == "day":
            continue  # a bare "din" is too vague to be a schedule
        cues.append((toks[first].start, t.end, freq, strong, first, j))
    live = [c for c in cues if not _negated(toks, c[4], c[5])]
    if not live:
        return None
    pool = [c for c in live if c[3]] or live
    amounts = [pn for pn, idxs in found if not _is_unit_noun(toks, _next(toks, idxs[-1]))]

    def distance(c: tuple) -> int:
        return min((max(0, pn.start - c[1], c[0] - pn.end) for pn in amounts), default=0)

    return min(pool, key=lambda c: (distance(c), c[0]))[2]
