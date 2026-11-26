"""Everything Samjho says, in Hindi (Devanagari, for the voice) and English (for subtitles and English mode).

Amounts are written as words in Hindi so the voice reads them the way people say them. Every line is built
from the loan, so a different Key Fact Statement changes the words without changing the code.
"""

from app.loan import Loan
from app.numwords import hindi_words, rupees_en, rupees_hi


def L(hi: str, en: str) -> dict:
    return {"hi": hi, "en": en}


def intro() -> dict:
    return L(
        "नमस्ते, मैं समझो हूँ। मैं आपके लोन की बातें आसान भाषा में समझाऊँगी, फिर आपसे आपके शब्दों में सुनूँगी कि आपने क्या समझा। "
        "यह बातचीत निजी है। क्या शुरू करें? हाँ या ना बोलिए।",
        "Hello, I am Samjho. I will explain your loan simply, then hear in your own words what you understood. "
        "This conversation is private. Shall we start? Say yes or no.",
    )


def explain(loan: Loan) -> list[dict]:
    return [
        L(
            f"आपका लोन {rupees_hi(loan.sanctioned)} का है। इसमें से {rupees_hi(loan.processing_fee)} फीस और "
            f"{rupees_hi(loan.insurance)} बीमा पहले ही कट जाएगा। इसलिए आपके हाथ में {rupees_hi(loan.cash_in_hand)} आएँगे।",
            f"Your loan is {rupees_en(loan.sanctioned)}. A fee of {rupees_en(loan.processing_fee)} and insurance of "
            f"{rupees_en(loan.insurance)} are cut first, so {rupees_en(loan.cash_in_hand)} reaches your hand.",
        ),
        L(
            f"आपको हर हफ्ते, महीने में नहीं, हर हफ्ते {rupees_hi(loan.instalment)} भरने हैं, {hindi_words(loan.instalments)} हफ्ते तक।",
            f"You pay {rupees_en(loan.instalment)} every week, not every month, for {loan.instalments} weeks.",
        ),
        L(
            f"कुल मिलाकर आप {rupees_hi(loan.total_repayable)} वापस करेंगी।",
            f"In total you will repay {rupees_en(loan.total_repayable)}.",
        ),
        L(
            "कोई सवाल हो तो अभी पूछिए। नहीं तो 'आगे' बोलिए।",
            "Ask any question now. Otherwise say 'next'.",
        ),
    ]


def faq(loan: Loan) -> list[tuple[str, dict]]:
    """Keyword patterns and fixed answers. Unknown questions are passed to the lender, never guessed."""
    return [
        (
            r"bi+ma|bee?ma|insurance|बीमा",
            L(
                f"बीमा इसलिए है कि अगर आपको कुछ हो जाए, तो बाकी लोन बीमे से भरा जाए और परिवार पर बोझ न आए। इसका खर्च {rupees_hi(loan.insurance)} है।",
                f"The insurance pays off the rest of the loan if something happens to you, so your family is not burdened. It costs {rupees_en(loan.insurance)}.",
            ),
        ),
        (
            r"fee|fees|processing|फीस|चार्ज|charge",
            L(
                f"{rupees_hi(loan.processing_fee)} लोन बनाने की फीस है। यह शुरू में कटती है और वापस नहीं मिलती।",
                f"{rupees_en(loan.processing_fee)} is the processing fee. It is cut at the start and is not returned.",
            ),
        ),
        (
            r"byaj|byaaj|interest|apr|ब्याज|सूद",
            L(
                f"इस लोन का सालाना खर्च लगभग {hindi_words(round(loan.apr_percent))} प्रतिशत है। इसीलिए {rupees_hi(loan.sanctioned)} के बदले {rupees_hi(loan.total_repayable)} लौटाने हैं।",
                f"The yearly cost of this loan is about {loan.apr_percent} percent. That is why you repay {rupees_en(loan.total_repayable)} for {rupees_en(loan.sanctioned)}.",
            ),
        ),
        (
            r"late|der|chhut|chut|miss|na bhar|nahi bhar|देर|छूट",
            L(
                "किस्त छूट जाए तो देर का शुल्क लग सकता है और आपका रिकॉर्ड खराब हो सकता है। मुश्किल हो तो पहले ही लेंडर को बताइए।",
                "If you miss an instalment, a late charge may apply and your credit record can suffer. Tell the lender early if it gets hard.",
            ),
        ),
    ]


def unknown_question() -> dict:
    return L(
        "यह सवाल मैं लिख रही हूँ, लेंडर आपको इसका जवाब देगा। कोई और सवाल? नहीं तो 'आगे' बोलिए।",
        "I am noting this question; the lender will answer it. Any other question? Otherwise say 'next'.",
    )


def ask_more() -> dict:
    return L("कोई और सवाल? नहीं तो 'आगे' बोलिए।", "Any other question? Otherwise say 'next'.")


def teachback() -> dict:
    return L(
        "अब एक काम कीजिए। सोचिए आप अपनी बेटी को यह लोन समझा रही हैं। अपने शब्दों में बताइए: हाथ में कितने पैसे आएँगे, "
        "कितना और कितनी बार भरना है, और कुल कितना लौटाना है।",
        "Now imagine you are explaining this loan to your daughter. In your own words: how much reaches your hand, "
        "how much you pay and how often, and how much you repay in total.",
    )


PROBE = {
    "cash_in_hand": L("हाथ में कितने रुपये आएँगे?", "How much money will reach your hand?"),
    "deductions": L("लोन मिलने से पहले कितने रुपये कटेंगे?", "How much is cut before you get the loan?"),
    "instalment": L("हर किस्त कितने रुपये की है?", "How much is each instalment?"),
    "frequency": L("किस्त कितने दिन में भरनी है, हर हफ्ते या हर महीने?", "How often do you pay, every week or every month?"),
    "total": L("कुल मिलाकर कितने रुपये लौटाने हैं?", "How much do you repay in total?"),
}

RECHECK = {
    "cash_in_hand": L("मान लीजिए आज लोन मिल गया। घर ले जाने के लिए कितने रुपये होंगे?", "Say the loan arrives today. How much do you take home?"),
    "deductions": L("फीस और बीमा मिलाकर कितने रुपये कटेंगे?", "Fee and insurance together, how much is cut?"),
    "instalment": L("हर बार जमा करते समय कितने रुपये देने होंगे?", "Each time you deposit, how much do you pay?"),
    "frequency": L("अगर इस सोमवार किस्त भरी, तो अगली किस्त कब भरनी है?", "If you pay this Monday, when is the next instalment due?"),
    "total": L("पूरा लोन खत्म होने तक आप कुल कितने रुपये दे चुकी होंगी?", "By the end of the loan, how much will you have paid in all?"),
}


def repair(loan: Loan, fact: str, quote: str, reason: str) -> dict:
    said_hi = f"आपने कहा '{quote}'। " if quote else ""
    said_en = f"You said '{quote}'. " if quote else ""
    if reason == "unclear word, confirm":
        return L(f"{said_hi}एक बार फिर, साफ़-साफ़ बोलिए।", f"{said_en}Please say it once more, clearly.")
    text = {
        "cash_in_hand": L(
            f"ध्यान दीजिए: {rupees_hi(loan.sanctioned)} में से फीस और बीमा मिलाकर {rupees_hi(loan.deductions)} पहले कट जाएँगे, "
            f"इसलिए हाथ में {rupees_hi(loan.cash_in_hand)} आएँगे।",
            f"Note: from {rupees_en(loan.sanctioned)}, fee and insurance of {rupees_en(loan.deductions)} are cut first, "
            f"so {rupees_en(loan.cash_in_hand)} reaches your hand.",
        ),
        "deductions": L(
            f"फीस {rupees_hi(loan.processing_fee)} और बीमा {rupees_hi(loan.insurance)}, दोनों मिलाकर {rupees_hi(loan.deductions)} कटेंगे।",
            f"Fee {rupees_en(loan.processing_fee)} and insurance {rupees_en(loan.insurance)}: {rupees_en(loan.deductions)} in all is cut.",
        ),
        "instalment": L(
            f"हर किस्त {rupees_hi(loan.instalment)} की है।",
            f"Each instalment is {rupees_en(loan.instalment)}.",
        ),
        "frequency": L(
            f"यह किस्त हर महीने नहीं, हर हफ्ते भरनी है। {hindi_words(loan.instalments)} बार।",
            f"This is paid every week, not every month. {loan.instalments} times.",
        ),
        "total": L(
            f"आप {rupees_hi(loan.sanctioned)} लेकर कुल {rupees_hi(loan.total_repayable)} लौटाएँगी, यानी "
            f"{rupees_hi(loan.total_repayable - loan.sanctioned)} ज़्यादा।",
            f"You take {rupees_en(loan.sanctioned)} and repay {rupees_en(loan.total_repayable)} in total, "
            f"{rupees_en(loan.total_repayable - loan.sanctioned)} more.",
        ),
    }[fact]
    return L(said_hi + text["hi"], said_en + text["en"])


def praise(n_right: int, n_total: int) -> dict:
    if n_right == n_total:
        return L("बहुत बढ़िया, आपने सब सही समझा।", "Very good, you understood all of it.")
    return L(
        (f"आपने {hindi_words(n_right)} बातें सही बताईं। " if n_right else "")
        + "बाकी मैं एक-एक करके समझाती हूँ।",
        (f"You got {n_right} right. " if n_right else "") + "Let me go through the rest one by one.",
    )


def unclear(fact_label_hi: str, fact_label_en: str) -> dict:
    return L(
        f"कोई बात नहीं। {fact_label_hi} वाली बात लेंडर का एक व्यक्ति आपको फ़ोन पर फिर से समझाएगा।",
        f"No problem. Someone from the lender will call you to explain the {fact_label_en} again.",
    )


FACT_LABEL = {
    "cash_in_hand": ("हाथ में आने वाले पैसे", "cash in hand"),
    "deductions": ("कटने वाले पैसे", "deductions"),
    "instalment": ("किस्त", "instalment"),
    "frequency": ("किस्त कब भरनी है", "payment schedule"),
    "total": ("कुल वापसी", "total repayment"),
}


def private_check() -> dict:
    return L(
        "अब एक ज़रूरी और निजी सवाल। आपका जवाब फील्ड अफ़सर को नहीं जाएगा। क्या किसी ने आपसे इस लोन के लिए अलग से पैसे माँगे, "
        "या कुछ और वादा किया? हाँ या ना बोलिए।",
        "Now an important, private question. Your answer will not go to the field officer. Did anyone ask you for "
        "extra money for this loan, or promise you something different? Say yes or no.",
    )


def private_yes() -> dict:
    return L(
        "बताने के लिए शुक्रिया। यह बात सीधे लेंडर के शिकायत अधिकारी के पास जाएगी, फील्ड अफ़सर के पास नहीं। लोन आगे बढ़ने से पहले वे आपको खुद फ़ोन करेंगे।",
        "Thank you for telling me. This goes straight to the lender's grievance officer, not the field officer. They will call you before the loan goes ahead.",
    )


def private_no() -> dict:
    return L("ठीक है, शुक्रिया।", "All right, thank you.")


def consent() -> dict:
    return L(
        "आखिरी सवाल। क्या आप इन शर्तों पर यह लोन लेना चाहती हैं? अगर हाँ, तो बोलिए: हाँ, मैं समझ गई और सहमत हूँ।",
        "Last question. Do you want this loan on these terms? If yes, say: yes, I understand and I agree.",
    )


def sealed() -> dict:
    return L(
        "शुक्रिया। आपकी समझ और आपकी सहमति का रिकॉर्ड बन गया है। आपके सवाल लेंडर तक पहुँचेंगे। नमस्ते।",
        "Thank you. A record of what you understood and your consent has been sealed. Your questions will reach the lender. Goodbye.",
    )


def declined() -> dict:
    return L(
        "ठीक है। आपने अभी सहमति नहीं दी, यह भी रिकॉर्ड हो गया है। लेंडर आपसे बात करेगा। नमस्ते।",
        "All right. You have not agreed for now, and that is recorded too. The lender will talk to you. Goodbye.",
    )


def not_started() -> dict:
    return L("ठीक है, जब आप तैयार हों तब बात करेंगे। नमस्ते।", "All right, we can talk when you are ready. Goodbye.")


def didnt_catch() -> dict:
    return L("माफ़ कीजिए, मैं समझ नहीं पाई। एक बार फिर बोलिए।", "Sorry, I did not catch that. Please say it again.")
