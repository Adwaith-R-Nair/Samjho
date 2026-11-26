# Samjho: low-level design

Module by module, as the code stands. Modules not yet in the repository have a **Planned interface** subsection;
those interfaces may change when the code lands. Architecture overview: [HLD.md](HLD.md).

## 1. Repository map

| Path | Purpose | Status |
|---|---|---|
| `app/main.py` | FastAPI app, routes, in-memory session store | Built |
| `app/config.py` | Optional settings and feature status | Built |
| `app/flow.py` | `Session` state machine, `yes_no()` | Built |
| `app/grade.py` | `assign()`, `judge()`, `_status()`, `grade()`, `Evidence`, `Verdict` | Built |
| `app/loan.py` | `Loan`, `SAMPLE_LOAN`, `FACTS`, `TOLERANCE`, `truth()` | Built |
| `app/lines.py` | Every spoken line in Hindi and English | Built |
| `app/numwords.py` | Rupee amounts as Hindi words | Built |
| `app/record.py` | `Ledger`, `verify()` | Built |
| `app/hi_numbers.py` | Number, schedule, count and duration parser | Built |
| `app/voice.py`, `app/browser_serializer.py` | Browser voice channel, server side | In progress (step 4) |
| `app/extract.py`, `app/limits.py` | Gemini extraction; call limits | Planned (steps 5, 6) |
| `web/` | Single-page UI, vanilla JS, no build step | Built |
| `tests/` | pytest suites (577 tests, all passing at the time of writing) | Built |
| `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml` | Image, one-command start, CI | Built |

## 2. `app/loan.py`

`Loan` is a frozen dataclass: `loan_id, lender, sanctioned, processing_fee, insurance, instalment, frequency
("weekly" or "monthly"), instalments, total_repayable, apr_percent, grievance_contact, extra`.
Derived properties: `deductions = processing_fee + insurance`, `cash_in_hand = sanctioned - deductions`.

`SAMPLE_LOAN` (synthetic): id `SAMPLE-JLG-50000`, sanctioned 50,000, fee 1,000, insurance 590, instalment 1,095,
weekly, 52 instalments, total 56,940, APR 32.8%.

`FACTS = ("cash_in_hand", "deductions", "instalment", "frequency", "total")`. This order is the order in which
the flow asks about or repairs facts.

`truth(loan, fact)` returns the true value of a fact (`"total"` maps to `total_repayable`).

### Grading rules and tolerances
Gap is relative: `gap = |said - truth| / truth`. `TOLERANCE[fact] = (green_max, amber_max)`.

| Fact | True value | Green if gap <= | Amber if gap <= | Otherwise | Worked examples |
|---|---|---|---|---|---|
| cash_in_hand | 48,410 | 3% | 3% (no amber band) | red | 50,000 is 3.3% off: red. Spoken as "pachaas hazaar", the parser flags the pachaas/pachpan pair, but the other reading (55,000) is also red, so it stays red (rule 3) |
| deductions | 1,590 | 10% | 40% | red | 1,590 green; 1,000 or 590 said alone: amber "named only one deduction" |
| instalment | 1,095 | 5% | 12% | red | 1,100 ("gyarah sau") green; 1,000 amber |
| total | 56,940 | 3% | 8% | red | |
| frequency | weekly | exact match | n/a | red | "har mahine" (monthly) red |

`_status(loan, fact, value, parts)` gives the status of one amount, in this order:
1. Gap within green: `green`.
2. Deductions said as one part whose value equals the fee (1,000) or the insurance (590): `amber`, "named only
   one deduction".
3. Gap within amber: `amber`, "close but not exact".
4. Otherwise `red`, "does not match the loan".

`judge(loan, fact, ev)`:
1. No evidence: `grey`, reason "not said".
2. Frequency: `green` if `ev.value == loan.frequency`, else `red`.
3. Amounts: `status = _status(value)`. If the parser marked the number not confident and any of its
   alternative readings would get a different status, return `amber`, "unclear word, confirm", and the flow
   asks her again (fail closed: an uncertain word can never pass as green when the other reading would not).
   Otherwise return `status`. So "pachaas hazaar" for cash in hand is red (50,000 and 55,000 are both red),
   while a flagged word whose readings straddle a boundary is asked again.

The tenure (52 weeks) is not graded as a separate fact. Counts such as "52 hafte" are excluded from rupee
amounts (see `assign()` below).

## 3. `app/grade.py`

### Data types
- `Evidence(fact, value, quote, confident=True, alternatives=(), guessed=False, parts=1)`: `value` is a float
  for amounts and a string for frequency; `quote` is her exact words for the number; `guessed` is True when the
  fact was chosen by size alone; `parts` counts the deduction amounts that were summed.
- `Verdict(fact, status, said=None, quote="", reason="")`: `status` is `green`, `amber`, `red` or `grey`
  (`app/flow.py` also uses `unclear`).

### `assign(text, loan, target=None) -> dict[str, Evidence]`
1. `parse_numbers(text)`; drop any number that is a count: value <= 120 and directly followed by a count word
   (hafte, week, mahine, month, kisht, instalment, baar, and Devanagari forms).
2. For each remaining number, find the nearest cue word within 32 characters on either side, but only inside
   the same clause. Clauses are split by `_CLAUSE`: punctuation (`, ; : . ! ?` and the danda `।`) and the words
   aur, and, phir, fir, then (and Devanagari और, फिर). So in "har hafte 1095 dena hai, kul 56,940" the word
   "kul" belongs to 56,940, not to 1095. Cue words per fact (`CUES`, regex, Latin and Devanagari): cash in hand
   ("haath", "hand", "milega", "aayenge", "nakad"), deductions ("kat", "fee", "bima", "insurance", "charge"),
   instalment ("kisht", "emi", "bharna", "bharne", "jama", "dena", "har hafte", "har mahine", "weekly",
   "monthly"), total ("kul", "total", "milakar", "wapas", "lauta").
3. No cue: if `target` is set, is not frequency, and this is the only number, assign it to `target`.
   Otherwise assign by size to the amount fact whose true value is closest, if within 45% (`guessed=True`).
   Else drop it.
4. Deductions: every number cued to deductions is summed into one `Evidence` (quote "a + b", `parts=n`),
   except numbers above 20% of the sanctioned amount (`_MAX_DEDUCTION_SHARE`), which are ignored as not being
   a deduction. Other facts: the first number said for a fact wins.
5. Frequency: `parse_frequency(text)`, if it returns a value.

### `judge(loan, fact, ev) -> Verdict`
Rules in section 2.

### `grade(text, loan, target=None) -> dict[str, Verdict]`
Verdicts only for facts she spoke about. If `target` is given and she said nothing about it, a `grey` verdict
for `target` is added.

## 4. `app/hi_numbers.py`

Deterministic and pure (no I/O, no network, no model calls). Input is code-mixed speech-to-text: Devanagari
Hindi, romanised Hindi with spelling variants, English number words, digits (Western or Indian grouping,
Devanagari digits), currency words and filler words.

| Name | Contract |
|---|---|
| `ParsedNumber` | Frozen dataclass: `value` (float, for example `48410.0`), `raw` (the exact substring), `start`, `end` (offsets in the input), `confident` (False if a known confusion pair could flip it), `alternatives` (tuple of other values that still compose) |
| `normalize(text) -> str` | One character in, one character out, so spans stay valid on the input |
| `parse_numbers(text) -> list[ParsedNumber]` | All numbers in reading order. Unclear words are skipped, never guessed |
| `parse_frequency(text) -> str or None` | `"weekly"`, `"monthly"`, `"fortnightly"`, `"daily"` or `None`. Negated cues are dropped ("mahine nahi, har hafte" is weekly); strong cues ("har hafte", "weekly") beat bare period nouns; a period after a number ("52 hafte") is a duration, not a schedule |
| `parse_count(text) -> ParsedNumber or None` | Number of instalments: a number before kisht, EMI or baar, else before hafte, mahine or din |
| `parse_duration(text) -> (value, unit) or None` | First "number period" phrase, unit in year, month, week, day |

How numbers are built (from the module docstring): words are reduced to spelling keys and looked up in one
lexicon; saade, sava and paune fuse with the next number (+0.5, +0.25, -0.25); dedh and dhai are 1.5 and 2.5;
weak words that are also ordinary words (ek, do, saath "with") count as numbers only before a multiplier, a
currency word or a unit noun; groups compose greedily as [unit] [sau [unit]] followed by hazaar, lakh or crore
in strictly falling order. Words that 8 kHz audio often swaps (pachaas/pachpan, saath/saat, sattar/satrah,
fifteen/fifty and similar) are re-evaluated with the swapped value; if that also composes, the number is marked
not confident and the alternatives are kept.

`app/grade.py` uses `parse_numbers` and `parse_frequency`. Any frequency other than the loan's (for example
`"monthly"` or `"fortnightly"`) is red. Known limits are listed in the module docstring (for example, "aur"
never joins two numbers).

## 5. `app/flow.py`

### `yes_no(text) -> bool | None`
Regex for yes (haan, ji, yes, ok, theek, bilkul, sahmat, Devanagari forms) and no (nahi, na, no, mat, Devanagari
forms). If both appear, the one that comes first wins ("nahi, kisi ne nahi maanga" is no; "haan, maanga tha" is
yes). Neither: `None`.

### `Session`
Constructor: `Session(loan=SAMPLE_LOAN, lang="hi")`; `lang` is `"hi"` or `"en"` (anything else becomes `"hi"`).
Fields: `id` (12 hex characters from a UUID4), `state`, `verdicts` (all five start `grey`), `rounds` (repairs
per fact), `asked` (facts already probed), `target` (fact just asked about), `questions` (for the lender),
`extra_money_reported`, `consent`, `ledger`.

Public API:
- `start() -> list[event]`: logs `session_start`, enters `consent`, says the intro.
- `hear(text) -> list[event]`: logs `heard`, dispatches to `_on_<state>`, returns the events produced. Empty
  text: "did not catch that", no state change. After `done`: returns `[]`.
- `done` (property): `state == "done"`.
- `record() -> dict`: the record (section 8).

`MAX_ROUNDS = 2`.

### State machine

| State | Input | Transition | Outputs (events, ledger) |
|---|---|---|---|
| (new) | `start()` | to `consent` | `state`, `say` intro |
| any | empty text | stay | `heard`, `say` "did not catch" |
| `consent` | yes | to `explain` | `state`, 4 `say` lines (amounts and cuts, weekly instalment for 52 weeks, total, "ask or say next") |
| `consent` | no | to `done` | `say` not started; consent `not_started`; `record` |
| `consent` | unclear | stay | `say` "did not catch" |
| `explain` | a question (question word or "?") matching an FAQ (insurance, fee, interest, missed payment) | stay | `say` fixed answer, `say` "any other question?" |
| `explain` | a question with no FAQ match | stay | ledger `question_for_lender`; `say` "I am noting this; the lender will answer" |
| `explain` | anything else ("aage", "next", "theek hai") | to `teachback` | `state`, `say` teach-back prompt |
| `teachback` | her explanation | to `check`, then `_next()` | `fact` per fact she mentioned, `say` praise ("you got n right" or "all right") |
| `check` | answer | `_next()` | `fact` for the target, and for any other fact she mentioned that is not already green |
| `private` | yes | to `final_consent` | `case` `HOLD_REVIEW`, `say` thanks (goes to grievance officer), `state`, `say` consent question |
| `private` | no | to `final_consent` | `say` thanks, `state`, `say` consent question |
| `private` | unclear | stay | `say` "did not catch" |
| `final_consent` | yes | to `done` | ledger `consent` (`given`, her words), `say` sealed, `record` |
| `final_consent` | no | to `done` | ledger `consent` (`declined`), `say` declined, `record` |
| `final_consent` | unclear | stay | `say` "did not catch" |
| `done` | anything | stay | nothing |

`_next()` walks `FACTS` in order and acts on the first fact that is not `green` or `unclear`:
1. `grey` and never asked: add to `asked`, set `target`, `say` the probe question (`lines.PROBE`). Return.
2. Fewer than 2 repairs so far: increment `rounds`, set `target`, `say` the repair (quotes her words, gives the
   true figures) and a fresh recheck question (`lines.RECHECK`, worded differently from the probe). Return.
3. Otherwise: `fact` event with status `unclear` ("still not clear after two explanations"), `case` `CALLBACK`,
   `say` "someone from the lender will call you". Continue to the next fact.
When no fact needs action: `target = None`, enter `private`, `say` the private question.

A green fact is never downgraded by an incidental later mention: in `check`, only the target fact or facts not
already green are updated.

## 6. `app/lines.py` and `app/numwords.py`

`L(hi, en)` returns `{"hi": ..., "en": ...}`. Lines are functions of the `Loan`, so another KFS changes the words,
not the code. Hindi lines are Devanagari, with amounts written as words by `numwords.rupees_hi()` so the voice
reads them the way people say them (`hindi_words(48410)` is "अड़तालीस हज़ार चार सौ दस", Indian grouping:
hazaar, lakh, crore). English amounts use `rupees_en()` ("Rs 48,410").

Contents: `intro`, `explain` (4 lines), `faq` (4 regex patterns with fixed answers), `unknown_question`,
`ask_more`, `teachback`, `PROBE` and `RECHECK` (one question per fact), `repair`, `praise`, `unclear`,
`FACT_LABEL`, `private_check`, `private_yes`, `private_no`, `consent`, `sealed`, `declined`, `not_started`,
`didnt_catch`.

## 7. `app/config.py`

`load_settings()` reads (all optional): `SARVAM_API_KEY`, `GOOGLE_API_KEY`, `TWILIO_ACCOUNT_SID`,
`TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `PUBLIC_BASE_URL`, `JUDGE_TOKEN`, `CALLS_ENABLED` (true only for
"1", "true", "yes"). `.env` is loaded once at import; the environment is read again on each `/api/status` call.

`Settings.status()` returns `{voice, extract, phone, text, replay}`, each `{"ready": bool, "reason": str}`.
`GET /api/status` in `app/main.py` then replaces `replay` (see the last row):

| Feature | Ready when | Reason when not ready |
|---|---|---|
| voice | `SARVAM_API_KEY` set | "SARVAM_API_KEY not set" |
| extract | `GOOGLE_API_KEY` set | "GOOGLE_API_KEY not set: rules-only extraction" |
| phone | Sarvam key, all three Twilio values, `PUBLIC_BASE_URL` and `CALLS_ENABLED` | "Phone calls off: Twilio keys, PUBLIC_BASE_URL or CALLS_ENABLED not set" |
| text | always | |
| replay | a `replays/*.json` file exists (set in `app/main.py`; none exists yet, step 7) | "No recorded test session added yet" |

`JUDGE_TOKEN` is read but not yet used (planned gate for the call button, step 6).

## 8. `app/record.py` and the record

### Ledger
`Ledger.append(kind, **data)` adds `{"seq": n, "t": unix time rounded to ms, "kind": kind, ...data}` and its hash.

Entry kinds written by `Session`:

| kind | Fields |
|---|---|
| `session_start` | `loan_id`, `lang` |
| `said` | `hi`, `en` |
| `heard` | `text`, `state`, `target` |
| `verdict` | `fact`, `status`, `said`, `quote`, `reason` |
| `case` | `case` (`CALLBACK` or `HOLD_REVIEW`), `detail` |
| `question_for_lender` | `text` |
| `consent` | `value` (`given` or `declined`), `words` |
| `session_end` | |

### Hash chain
```
canon(entry) = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
h[0]         = "0" * 64
h[i]         = sha256_hex( h[i-1] + canon(entry[i]) )   encoded as UTF-8
seal         = h[last]
```
Changing, reordering, inserting or removing any entry changes every hash after it, so the seal no longer matches.

### Record (`Session.record()`)
```json
{
  "session_id": "12 hex chars",
  "loan_id": "SAMPLE-JLG-50000",
  "language": "hi",
  "facts": {
    "cash_in_hand": {"status": "green", "said": 48410, "her_words": "...", "explained_again": 1}
  },
  "understood_all": true,
  "right_first_answer": 2,
  "right_after_samjho": 5,
  "first_answer": {"cash_in_hand": "red", "deductions": "green", "instalment": "amber", "frequency": "red", "total": "green"},
  "extra_money_reported": false,
  "questions_for_lender": [],
  "consent": "given",
  "entries": [ ... ledger entries ... ],
  "seal_sha256": "64 hex chars"
}
```
`facts` has all five keys. `first_answer` is the status of her first answer about each fact (teach-back or the
first direct question), before any re-explanation; `right_first_answer` and `right_after_samjho` count greens
before and after, which is the per-session measure of what Samjho changed (`Session._fact`, `Session.record`;
test `test_record_counts_first_answers_and_the_result_after_repair`). `extra_money_reported` is `null` if the
private question was never reached.
`consent` is `given`, `declined`, `not_started` or `null`.

The seal covers `entries` only. The summary fields (`facts`, `understood_all`, `consent` and so on) are a
convenience view; to rely on them, check them against the `verdict`, `case` and `consent` entries.

### How to verify
```python
from app.record import verify
assert verify(record["entries"], record["seal_sha256"])
```
Without this repository: recompute the chain above in any language and compare the last hash with
`seal_sha256`.

Number format and browser copies: the canonical form depends on how numbers are written. The parser returns
floats, and Python writes a whole-number float as `48410.0` while JavaScript writes `48410`. To keep the hash
stable, `Session._fact()` converts a whole-number `said` to an integer before it is logged, so the record is
written the same way by Python and by the browser's download button, and the downloaded file verifies. Test:
`tests/test_flow.py::test_record_amounts_are_integers_so_a_browser_copy_still_verifies` (no floats in the
entries, and the seal holds after a JSON round trip).

## 9. Event protocol (server to UI)

Typing mode returns events as JSON arrays from the REST API. The browser voice channel sends the same events as
JSON text messages on `/ws/browser`, between the binary audio messages (step 4, server side in the
repository). The phone channel's event feed to the panel is Planned (step 6).

| type | Fields | Producer | UI handling |
|---|---|---|---|
| `say` | `text` (in session language), `hi`, `en` | `Session._say` | Bot bubble; English gloss under Hindi |
| `heard` | `text` | `Session.hear` | User bubble |
| `state` | `state` | `Session._state` | Not rendered yet |
| `fact` | `fact`, `status` (`green`, `amber`, `red`, `grey`, `unclear`), `said`, `quote`, `reason`, `round` | `Session._fact` | Colours the fact chip, shows her words |
| `case` | `case` (`CALLBACK`, `HOLD_REVIEW`), `detail` | `Session._case` | Note in the case list |
| `case` | `case` (`KEY_NOT_SET`, `BUSY`), `detail`; the socket then closes | `/ws/browser` in `app/main.py`; `run_browser_session` in `app/voice.py` | Note in the case list |
| `record` | `record` (section 8) | `Session._finish` | Record card, JSON download, hides the input |
| `latency` | `turn`, `ms` (end of speech to first reply audio) | `app/voice.py`, from Pipecat's `UserBotLatencyObserver` | Note in the event list |
| `clear` | none (wire message, not a UI event) | `BrowserSerializer`, after an interruption | Planned: browser client drops queued audio (step 4) |

## 10. HTTP endpoints

### Built (`app/main.py`)

| Method and path | Request | Response |
|---|---|---|
| `GET /healthz` | | `{"ok": true}` |
| `GET /api/status` | | `Settings.status()` with `replay` set from `replays/` (section 7) |
| `POST /api/text/start` | `{"lang": "hi" or "en"}` (default `"hi"`) | `{"session_id", "events"}` |
| `POST /api/text/say` | `{"session_id", "text"}`; text truncated to 500 characters | `{"events", "done"}`; 404 "session expired, start again" if unknown or expired |
| `GET /` | | `web/index.html` |
| `GET /static/*` | | Files in `web/` |
| `WS /ws/browser?lang=hi` (or `en`) | Binary: PCM16 mono 16 kHz audio | Binary: PCM16 mono 16 kHz reply audio. Text: JSON events (section 9). Without `SARVAM_API_KEY`: one `KEY_NOT_SET` case, then close |

Sessions: in-memory dict, 30-minute idle expiry (`SESSION_TTL`), at most 200 (`MAX_SESSIONS`), pruned on each
`/api/text/start`. FastAPI's `/docs` and `/redoc` are disabled.

### Planned

| Path | Purpose | Step |
|---|---|---|
| `POST /api/call` | Start a call to an Indian mobile, with consent and limits | 6 |
| `WS /ws/twilio` | Twilio Media Streams (8 kHz) | 6 |
| `GET /api/replay` | Recorded consented session events for the replay tile | 7 |

## 11. Browser voice channel: `app/voice.py`, `app/browser_serializer.py` (In progress, step 4)

Server side is in the repository; the browser microphone client in `web/` is not written yet.

| Item | As written |
|---|---|
| Entry | `run_browser_session(websocket, lang, api_key)`, called by `/ws/browser`. Pipecat is imported only there, so typing mode starts without loading it |
| Limits | `MAX_SESSIONS = 4` live sessions (else a `BUSY` case and close); `SESSION_TIMEOUT_SECS = 300`; disconnect or timeout cancels the pipeline |
| Pipeline | `transport.input`, `EchoGate`, `SarvamSTTService`, user turn aggregator, `Brain`, `SarvamTTSService`, `transport.output` |
| Speech-to-text | Sarvam `saaras:v4`, mode `codemix`, 16 kHz, key-term hints (hazaar, kisht, bima, hafta, EMI and Devanagari forms) |
| Text-to-speech | Sarvam `bulbul:v4-flash`, voices `kavya_hi_conversational` (Hindi) and `ishita_en_customer` (English) |
| Turn end | Silero VAD (confidence 0.7, start 0.2 s, stop 0.2 s); `StateSpeechTimeout`: 0.9 s of silence for answers with numbers, 0.6 s in `consent`, `private` and `final_consent` |
| Half duplex | The browser is to send silence while playing; `EchoGate` zeroes mic audio while the bot speaks and for 0.25 s after; `AlwaysUserMuteStrategy` drops turns in that window |
| `Brain` | On start: emits `Session.start()` events. On each final user turn: `Session.hear(text)`; sends every event as a JSON message and every `say` line to TTS; ends the pipeline after the goodbye when the session is done. No LLM is called |
| Latency | `UserBotLatencyObserver` `on_latency_measured` becomes `{"type": "latency", "turn", "ms"}` |
| Wire format (`BrowserSerializer`) | In: binary PCM16 mono 16 kHz (text messages ignored). Out: binary PCM16 16 kHz audio; JSON text for events; `{"type": "clear"}` after an interruption |

## 12. Planned interfaces for modules not yet present

### `app/extract.py` (step 5)
- `extract(text, loan, target) -> dict[str, Evidence] | None`: Gemini returns JSON assignments of her numbers
  to facts, with her quoted words. Timeout 1.5 s; on timeout, error or missing key, return `None` and use
  `assign()`. Its output goes through `judge()`; it never sets a status.

### `app/limits.py` (step 6)
- Number rule `^\+91[6-9]\d{9}$`; per-number cooldown; per-IP and global limits; call time cap; reads
  `CALLS_ENABLED` per request; phone numbers kept only as salted hashes.

## 13. Test map

| File | Covers |
|---|---|
| `tests/test_app.py` | No-keys start: `/healthz`, main screen, static JS (`test_health_and_main_screen_without_keys`); status names missing keys, keeps text on and reports a replay state (`test_status_names_missing_keys_and_keeps_text_and_replay_on`); status never echoes a key value (`test_status_never_echoes_a_key`) |
| `tests/test_hi_numbers.py` (544 cases) | Every word 0 to 99 in romanised and Devanagari Hindi; spelling variants; composition (hazaar, lakh, saade, sava, paune, dedh, dhai, digits); separating adjacent numbers; no numbers and fail closed; confusion-pair flags and confident numbers; spans map back to the raw text; realistic code-mixed sentences; frequency, count and duration; `normalize` keeps length; round trip with `app/numwords.py`; no em dashes in the module |
| `tests/test_source_hygiene.py` | No control characters (a scripted edit once turned the regex `\b` into a backspace byte) and no em dashes in any `.py`, `.js`, `.html`, `.css` or `.md` file under `app/`, `web/`, `tests/` and `docs/` |
| `tests/test_flow.py`, yes/no | 12 parametrised cases including Devanagari and "first answer wins" (`test_yes_no`) |
| `tests/test_flow.py`, grading | Classic miss in her words: 50,000 red, monthly red, 1,000 amber (`test_classic_miss_is_caught_in_her_words`); full correct Hinglish teach-back all green (`test_correct_teachback_is_all_green`); bare number answers the asked fact, "pata nahi" stays grey (`test_bare_number_answers_the_question_asked`); one deduction amber (`test_one_deduction_only_is_amber`); "52 hafte" not read as rupees (`test_week_count_is_not_read_as_rupees`); "aur" splits clauses so each number gets its own cue (`test_aur_splits_clauses_so_each_number_gets_its_own_cue`) |
| `tests/test_flow.py`, conversation | Happy path seals a verifiable record (`test_happy_path_seals_a_verifiable_record`); repair quotes her words and rechecks with a fresh question (`test_miss_is_repaired_then_rechecked_with_a_fresh_question`); two failed rounds give UNCLEAR and CALLBACK (`test_two_failed_rounds_hand_over_to_a_human_and_never_block`); extra-money yes gives HOLD_REVIEW (`test_extra_money_report_creates_a_hold_for_the_grievance_officer`); FAQ answer during explain (`test_question_during_explanation_gets_a_fixed_answer`); unknown question logged for the lender (`test_unknown_question_is_passed_to_the_lender_not_guessed`); "no" at the start ends politely with a record (`test_saying_no_at_the_start_ends_politely`); English mode (`test_english_mode_speaks_english`); tampering breaks the seal (`test_tampering_with_the_log_breaks_the_seal`); amounts stored as integers so a browser copy verifies (`test_record_amounts_are_integers_so_a_browser_copy_still_verifies`) |
| `.github/workflows/ci.yml` | `pytest` on every push and pull request; fresh-clone `docker compose up` with no keys, `/healthz`, main screen, "SARVAM_API_KEY not set" |
| Planned | Voice channel tests (step 4); eval harness over phrase fixtures reporting accuracy, false passes and P50/P95 latency (step 9) |

At the time of writing: 577 tests (544 parser, 28 flow and grading, 3 app, 2 hygiene), all passing.

Run: `python -m pytest -q`.
