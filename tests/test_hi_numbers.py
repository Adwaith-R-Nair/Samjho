"""Table-driven tests for app.hi_numbers (deterministic Hindi / Hinglish number parsing)."""
import pytest

from app.hi_numbers import (
    ParsedNumber,
    normalize,
    parse_count,
    parse_duration,
    parse_frequency,
    parse_numbers,
)


def values(text):
    return [p.value for p in parse_numbers(text)]


# ------------------------------------------------------------------ every word 0 to 99

ROMAN_0_99 = (
    "shunya ek do teen chaar paanch chhe saat aath nau das gyarah barah terah chaudah pandrah "
    "solah satrah atharah unnis bees ikkis bais teis chaubis pachchis chhabbis sattais atthais "
    "untis tees ikattis battis taintis chautis paintis chhattis saintis adtis untalis chaalis "
    "iktalis bayalis taintalis chauvalis paintalis chhiyalis saintalis adtalis unchas pachaas "
    "ikyavan baawan tirpan chauvan pachpan chhappan sattavan atthavan unsath saath iksath "
    "baasath tirsath chausath painsath chhiyasath sadsath adsath unhattar sattar ikhattar "
    "bahattar tihattar chauhattar pachhattar chhihattar satattar athattar unasi assi ikyasi "
    "bayasi tirasi chaurasi pachasi chhiyasi sattasi athasi navasi nabbe ikyanve baanve "
    "tiranve chauranve pachaanve chhiyanve sattanve atthanve ninyanve"
).split()

DEV_0_99 = (
    "शून्य एक दो तीन चार पांच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह "
    "उन्नीस बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस "
    "तैंतीस चौंतीस पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस "
    "पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास पचास इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन "
    "अट्ठावन उनसठ साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर सत्तर इकहत्तर "
    "बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी अस्सी इक्यासी बयासी तिरासी "
    "चौरासी पचासी छियासी सत्तासी अठासी नवासी नब्बे इक्यानवे बानवे तिरानवे चौरानवे पचानवे "
    "छियानवे सत्तानवे अट्ठानवे निन्यानवे"
).split()


def test_word_lists_cover_0_to_99():
    assert len(ROMAN_0_99) == 100 and len(DEV_0_99) == 100


@pytest.mark.parametrize("n", range(100))
def test_romanized_word(n):
    # "rupaye" after the word lets weak words (ek, do, saath) count as numbers.
    assert values(f"{ROMAN_0_99[n]} rupaye") == [n]


@pytest.mark.parametrize("n", range(100))
def test_devanagari_word(n):
    assert values(f"{DEV_0_99[n]} रुपये") == [n]


# ------------------------------------------------------------------ spelling variants

VARIANTS = [
    ("adtalis", 48), ("adtaalis", 48), ("artalis", 48), ("अड़तालीस", 48), ("अडतालीस", 48),
    ("pachaanve", 95), ("pachanave", 95), ("pachanve", 95), ("पचानवे", 95), ("पंचानवे", 95),
    ("chhappan", 56), ("chappan", 56), ("छप्पन", 56),
    ("baawan", 52), ("bavan", 52), ("bawan", 52), ("बावन", 52),
    ("unsath", 59), ("unsaath", 59), ("उनसठ", 59),
    ("nabbe", 90), ("nabe", 90), ("नब्बे", 90),
    ("pachas", 50), ("pachaas", 50), ("chalis", 40), ("chaalis", 40), ("chalees", 40),
    ("gyarah", 11), ("gyaarah", 11), ("gyara", 11), ("pandra", 15), ("pandrah", 15),
    ("पन्द्रह", 15), ("पाँच", 5), ("panch", 5), ("chhah", 6), ("छः", 6), ("unees", 19),
    ("unnees", 19), ("chauwalis", 44), ("chawalis", 44), ("चौवालीस", 44), ("assi", 80),
    ("अट्ठासी", 88), ("athaasi", 88), ("PACHAAS", 50), ("Baawan", 52),
]


@pytest.mark.parametrize("word,expected", VARIANTS)
def test_spelling_variants(word, expected):
    assert values(f"{word} rupaye") == [expected]


# ------------------------------------------------------------------ composition

COMPOSED = [
    ("adtaalis hazaar chaar sau das", 48410),
    ("adtalis hazar char sau das", 48410),
    ("ek hazaar pachaanve", 1095),
    ("gyarah sau pachaanve", 1195),
    ("chhappan hazaar nau sau chaalis", 56940),
    ("pandrah sau nabbe", 1590),
    ("paanch sau nabbe", 590),
    ("pachaas hazaar", 50000),
    ("pachas hajar", 50000),
    ("ek hazaar", 1000),
    ("hazaar rupaye", 1000),
    ("sau rupaye", 100),
    ("ek lakh pachaas hazaar", 150000),
    ("do lakh", 200000),
    ("teen crore", 30000000),
    ("das lakh", 1000000),
    ("unnis sau pachaas", 1950),
    ("do hazaar do sau", 2200),
    ("paanch so rupaye", 500),
    ("पचास हज़ार", 50000),
    ("पचास हजार", 50000),
    ("अड़तालीस हज़ार चार सौ दस", 48410),
    ("एक हज़ार पचानवे", 1095),
    ("छप्पन हज़ार नौ सौ चालीस", 56940),
    ("पंद्रह सौ नब्बे", 1590),
    ("पांच सौ नब्बे", 590),
    ("एक लाख", 100000),
    ("दो करोड़", 20000000),
    # fractions
    ("dedh hazaar", 1500),
    ("derh hazaar", 1500),
    ("dhai sau", 250),
    ("dhaai hazaar", 2500),
    ("saade gyarah sau", 1150),
    ("sadhe teen hazaar", 3500),
    ("sava lakh", 125000),
    ("sawa do hazaar", 2250),
    ("paune do hazaar", 1750),
    ("paune sau", 75),
    ("dedh lakh", 150000),
    ("डेढ़ हज़ार", 1500),
    ("ढाई सौ", 250),
    ("साढ़े ग्यारह सौ", 1150),
    ("सवा लाख", 125000),
    ("पौने दो हज़ार", 1750),
    ("saade 3 hazaar", 3500),
    # English
    ("one thousand and ninety five", 1095),
    ("one thousand ninety five", 1095),
    ("fifty thousand", 50000),
    ("forty eight thousand four hundred ten", 48410),
    ("forty-eight thousand four hundred and ten", 48410),
    ("fifty six thousand nine hundred forty", 56940),
    ("one hundred fifty thousand", 150000),
    ("five hundred ninety", 590),
    ("fifteen hundred ninety", 1590),
    ("two lakh", 200000),
    ("one hundred and five", 105),
    ("twenty five hundred", 2500),
    # digits and mixed forms
    ("48 hazaar 410", 48410),
    ("1 hazaar 95", 1095),
    ("50 thousand", 50000),
    ("₹48,410", 48410),
    ("Rs. 50,000", 50000),
    ("Rs50000", 50000),
    ("50,000/-", 50000),
    ("48410", 48410),
    ("1,095", 1095),
    ("56 940", 56940),
    ("56940", 56940),
    ("1,50,000 rupaye", 150000),
    ("10,00,000", 1000000),
    ("1,000,000", 1000000),
    ("५०,०००", 50000),
    ("४८४१०", 48410),
    ("1.5 lakh", 150000),
    ("2.5 hazaar", 2500),
    ("50k", 50000),
    ("50K rupees", 50000),
    ("1.5k", 1500),
    ("48 हज़ार 410", 48410),
    ("50hazaar", 50000),
    ("12.5", 12.5),
    ("ek hazaar um pachaanve", 1095),
]


@pytest.mark.parametrize("text,expected", COMPOSED)
def test_composition(text, expected):
    assert values(text) == [expected]


# ------------------------------------------------------------------ separation

SEPARATE = [
    ("pachaas hazaar mein se ek hazaar kata", [50000, 1000]),
    ("har hafte 1095, 52 hafte", [1095, 52]),
    ("har hafte 1095 rupaye, 52 hafte", [1095, 52]),
    ("1095 52", [1095, 52]),
    ("pachaas hazaar baawan hafte", [50000, 52]),
    ("50 hazaar 52 hafte", [50000, 52]),
    ("fifty thousand fifty two weeks", [50000, 52]),
    ("pachaas hazaar. ek hazaar", [50000, 1000]),
    ("pachaas hazaar rupaye ek hazaar", [50000, 1000]),
    ("pachaas hazaar aur paanch sau", [50000, 500]),
    ("50k 52", [50000, 52]),
    ("48,410 aur 1,095", [48410, 1095]),
    ("पचास हज़ार में से एक हज़ार कटा", [50000, 1000]),
    ("बीस पांच", [20, 5]),
    ("ek hazaar dedh saal", [1000, 1.5]),
    ("lakh hazaar", [100000, 1000]),
    ("pachaas hazaar ek saal ke liye", [50000, 1]),
]


@pytest.mark.parametrize("text,expected", SEPARATE)
def test_separation(text, expected):
    assert values(text) == expected


# ------------------------------------------------------------------ no numbers / fail closed

NO_NUMBERS = [
    "haan ji samajh gayi",
    "हाँ जी समझ गई",
    "",
    "   ",
    "mere saath chalo",
    "paise de do",
    "पैसे दे दो",
    "ek baat poochhni thi",
    "so what is the plan",
    "at the bank",
    "tera kya hai",
    "bara loan hai",
    "saade",
    "and then",
    "rupaye",
    "₹",
    "aapke saath hoon",
    "I do not know",
]


@pytest.mark.parametrize("text", NO_NUMBERS)
def test_no_numbers(text):
    assert parse_numbers(text) == []


# ------------------------------------------------------------------ confusion pairs

CONFUSION = [
    ("pachaas rupaye", 50, (55,)),
    ("pachpan rupaye", 55, (50,)),
    ("saath hazaar", 60000, (7000,)),
    ("saat hazaar", 7000, (60000,)),
    ("sattar rupaye", 70, (17,)),
    ("satrah rupaye", 17, (70,)),
    ("chaalis rupaye", 40, (44,)),
    ("chauvalis rupaye", 44, (40,)),
    ("pandrah sau", 1500, (7500,)),
    ("pachhattar rupaye", 75, (15,)),
    ("पचास हज़ार", 50000, (55000,)),
    ("साठ रुपये", 60, (7,)),
    ("fifty thousand", 50000, (15000,)),
    ("fifteen thousand", 15000, (50000,)),
    ("sixteen", 16, (60,)),
    ("sixty", 60, (16,)),
    ("seventeen", 17, (70,)),
    ("seventy", 70, (17,)),
    ("eighteen", 18, (80,)),
    ("eighty", 80, (18,)),
    ("nineteen", 19, (90,)),
    ("ninety", 90, (19,)),
    ("chhappan hazaar nau sau chaalis", 56940, (56944,)),
    ("pandrah sau nabbe", 1590, (7590,)),
    ("saade saat", 7.5, (60.5,)),
]


@pytest.mark.parametrize("text,value,alts", CONFUSION)
def test_confusion_flags(text, value, alts):
    [p] = parse_numbers(text)
    assert p.value == value
    assert p.confident is False
    assert p.alternatives == alts


CONFIDENT = [
    "adtaalis hazaar chaar sau das",
    "ek hazaar pachaanve",
    "paanch sau nabbe",
    "baawan hafte",
    "48410",
    "50,000",
    "fifty five",  # "fifteen five" is not a number, so the grammar settles it
    "one thousand and ninety five",
    "assi rupaye",
    "chhappan rupaye",
]


@pytest.mark.parametrize("text", CONFIDENT)
def test_confident_numbers(text):
    [p] = parse_numbers(text)
    assert p.confident is True and p.alternatives == ()


# ------------------------------------------------------------------ spans and raw text

SPANS = [
    ("mujhe ₹48,410 milenge", "48,410"),
    ("haan ji pachaas hazaar milenge", "pachaas hazaar"),
    ("Total: 1,095 rupaye", "1,095"),
    ("48 हज़ार 410 मिलेंगे", "48 हज़ार 410"),
    ("कुल ५०,००० रुपये", "५०,०००"),
    ("PACHAAS HAZAAR", "PACHAAS HAZAAR"),
    ("paune do hazaar", "paune do hazaar"),
]


@pytest.mark.parametrize("text,raw", SPANS)
def test_raw_span_maps_back(text, raw):
    [p] = parse_numbers(text)
    assert p.raw == raw
    assert text[p.start:p.end] == raw


def test_parsed_number_is_frozen():
    p = parse_numbers("ek hazaar")[0]
    assert isinstance(p, ParsedNumber)
    with pytest.raises(Exception):
        p.value = 5  # type: ignore[misc]


# ------------------------------------------------------------------ realistic codemix sentences

SENTENCES = [
    ("mere haath mein pachaas hazaar aayenge aur har mahine hazaar rupaye bharne hain", [50000, 1000]),
    ("48 हज़ार 410 मिलेंगे", [48410]),
    ("har hafte ek hazaar pachaanve dena hai baawan hafte tak", [1095, 52]),
    ("loan pachaas hazaar ka hai, processing fee ek hazaar, haath mein adtaalis hazaar chaar sau das", [50000, 1000, 48410]),
    ("मुझे पचास हज़ार का लोन मिला, हर हफ्ते एक हज़ार पचानवे देना है, बावन हफ्ते", [50000, 1095, 52]),
    ("total chhappan hazaar nau sau chaalis wapas karna hai", [56940]),
    ("interest paanch sau nabbe aur fee pandrah sau nabbe", [590, 1590]),
    ("so basically ₹50,000 loan, weekly 1,095 rupees for 52 weeks", [50000, 1095, 52]),
    ("matlab fifty thousand milega and one thousand ninety five every week", [50000, 1095]),
    ("umm haan ji, pachaas hazaar", [50000]),
    ("मेरे हाथ में अड़तालीस हज़ार चार सौ दस आएंगे", [48410]),
    ("₹1,095 x 52 = ₹56,940", [1095, 52, 56940]),
]


@pytest.mark.parametrize("text,expected", SENTENCES)
def test_codemix_sentences(text, expected):
    assert values(text) == expected


# ------------------------------------------------------------------ frequency

FREQUENCY = [
    ("har hafte", "weekly"),
    ("hafta", "weekly"),
    ("hafte mein ek hazaar", "weekly"),
    ("haftawar kisht", "weekly"),
    ("weekly payment", "weekly"),
    ("every week", "weekly"),
    ("1095 per week", "weekly"),
    ("saptahik", "weekly"),
    ("हर हफ्ते", "weekly"),
    ("हर हफ़्ते एक हज़ार", "weekly"),
    ("साप्ताहिक किस्त", "weekly"),
    ("har mahine", "monthly"),
    ("mahina", "monthly"),
    ("mahine mein ek baar", "monthly"),
    ("monthly emi", "monthly"),
    ("every month", "monthly"),
    ("मासिक", "monthly"),
    ("हर महीने", "monthly"),
    ("महीने में दो हज़ार", "monthly"),
    ("15 din mein", "fortnightly"),
    ("pandrah din", "fortnightly"),
    ("har pandrah din", "fortnightly"),
    ("do hafte mein ek baar", "fortnightly"),
    ("har do hafte", "fortnightly"),
    ("fortnight", "fortnightly"),
    ("fortnightly", "fortnightly"),
    ("roz", "daily"),
    ("har din", "daily"),
    ("daily", "daily"),
    ("रोज़ सौ रुपये", "daily"),
    ("roz 100 rupaye", "daily"),
    ("har roz", "daily"),
    ("haan ji samajh gayi", None),
    ("pachaas hazaar milenge", None),
    ("ek saal ke liye", None),
    ("baawan hafte", None),
    ("52 weeks", None),
    ("kitne din lagenge", None),
    ("", None),
    # negation
    ("mahine nahi, har hafte", "weekly"),
    ("har mahine nahi, har hafte dena hai", "weekly"),
    ("hafte nahi, mahine mein", "monthly"),
    ("not monthly, weekly", "weekly"),
    ("महीने नहीं, हर हफ्ते", "weekly"),
    ("har hafte nahi", None),
    # several cues
    ("har hafte ek hazaar pachaanve dena hai baawan hafte tak", "weekly"),
    ("mere haath mein pachaas hazaar aayenge aur har mahine hazaar rupaye bharne hain", "monthly"),
    ("har hafte 1095, 52 hafte", "weekly"),
    ("mahine ke hisaab se nahi pata, har hafte 1095", "weekly"),
    ("ek mahine mein kitna, har hafte hazaar", "weekly"),
    ("hafte mein 1000 dena, har mahine meeting hoti hai", "monthly"),
    ("har mahine meeting hai aur har hafte 1095 dena hai", "weekly"),
    ("ek hafte mein", "weekly"),
]


@pytest.mark.parametrize("text,expected", FREQUENCY)
def test_frequency(text, expected):
    assert parse_frequency(text) == expected


# ------------------------------------------------------------------ count

COUNT = [
    ("52 hafte", 52),
    ("baawan kisht", 52),
    ("baawan hafte", 52),
    ("बावन किस्तें", 52),
    ("52 हफ्ते", 52),
    ("52 weeks", 52),
    ("52 installments", 52),
    ("12 emi", 12),
    ("barah mahine", 12),
    ("52 weekly kisht", 52),
    ("har hafte 1095, 52 hafte", 52),
    ("har hafte ek hazaar pachaanve dena hai baawan hafte tak", 52),
    ("har mahine hazaar, 12 mahine tak", 12),
    ("52 baar bharna hai", 52),
    ("ek saal hafte bhar 52 kisht", 52),
    ("100 din", 100),
]


@pytest.mark.parametrize("text,expected", COUNT)
def test_count(text, expected):
    p = parse_count(text)
    assert p is not None and p.value == expected


@pytest.mark.parametrize("text", [
    "ek saal",
    "do saal ke liye",
    "pachaas hazaar",
    "har hafte",
    "har do hafte",
    "haan ji samajh gayi",
    "",
])
def test_count_none(text):
    assert parse_count(text) is None


def test_count_span():
    text = "har hafte 1095, 52 hafte"
    p = parse_count(text)
    assert text[p.start:p.end] == "52"


# ------------------------------------------------------------------ duration

DURATION = [
    ("ek saal", (1, "year")),
    ("ek saal ke liye loan", (1, "year")),
    ("dedh saal", (1.5, "year")),
    ("do saal", (2, "year")),
    ("एक साल", (1, "year")),
    ("baawan hafte", (52, "week")),
    ("52 weeks", (52, "week")),
    ("12 mahine", (12, "month")),
    ("barah mahine", (12, "month")),
    ("100 din", (100, "day")),
    ("har hafte 1095 dena hai baawan hafte tak", (52, "week")),
    ("pachaas hazaar ek saal ke liye", (1, "year")),
    ("har do hafte, 26 baar, ek saal", (1, "year")),
]


@pytest.mark.parametrize("text,expected", DURATION)
def test_duration(text, expected):
    assert parse_duration(text) == expected


@pytest.mark.parametrize("text", ["har hafte", "pachaas hazaar", "haan ji", "52 kisht", ""])
def test_duration_none(text):
    assert parse_duration(text) is None


# ------------------------------------------------------------------ normalize

NORMALIZE = [
    ("Pachaas HAZAAR", "pachaas hazaar"),
    ("५०,०००", "50,000"),
    ("₹48,410!", "₹48,410 "),
    ("हाँ। ठीक", "हाँ. ठीक"),
    ("50,000/-", "50,000  "),
    ("forty-eight", "forty eight"),
    ("(1.5 lakh)", " 1.5 lakh "),
]


@pytest.mark.parametrize("text,expected", NORMALIZE)
def test_normalize(text, expected):
    assert normalize(text) == expected


@pytest.mark.parametrize("text", ["Rs. ५०,०००/- only!", "pachaas" + chr(0x2014) + "hazaar", "x" + chr(0x130) + "y", "a\tb\nc"])
def test_normalize_keeps_length(text):
    assert len(normalize(text)) == len(text)


# ------------------------------------------------------------------ round trip with the speaker

@pytest.mark.parametrize("n", [0, 7, 50, 99, 100, 590, 1000, 1095, 1590, 48410, 50000, 56940,
                               100000, 125000, 999999, 2500000])
def test_round_trip_with_numwords(n):
    numwords = pytest.importorskip("app.numwords")
    assert values(numwords.hindi_words(n) + " रुपये") == [n]


# ------------------------------------------------------------------ house rules

def test_no_em_dashes_in_module():
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app" / "hi_numbers.py"
    assert chr(0x2014) not in src.read_text(encoding="utf-8")
