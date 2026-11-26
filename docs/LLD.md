# Samjho: low-level design

Module by module, as committed. Anything not built is marked **Planned** with its roadmap step
([ROADMAP.md](ROADMAP.md)). Architecture overview: [HLD.md](HLD.md).

## 1. Repository map

| Path | Purpose | Status |
|---|---|---|
| `app/main.py` | FastAPI app, routes, in-memory typing sessions | Built |
| `app/config.py` | Optional settings and feature status | Built |
| `app/flow.py` | `Session` state machine, `yes_no()` | Built |
| `app/answer.py` | Answers to her questions: fixed intents, fenced Gemini, `warm()` | Built |
| `app/grade.py` | `assign()`, `judge()`, `_status()`, `grade()`, `Evidence`, `Verdict` | Built |
| `app/hi_numbers.py` | Number, schedule, count and duration parser | Built |
| `app/loan.py` | `Loan`, `SAMPLE_LOAN`, `FACTS`, `TOLERANCE`, `truth()` | Built |
| `app/lines.py`, `app/numwords.py` | Every spoken line in Hindi and English; amounts as Hindi words | Built |
| `app/record.py` | `Ledger`, `verify()` | Built |
| `app/voice.py`, `app/browser_serializer.py` | Pipecat pipeline with browser and phone profiles; browser wire format | Built (phone: live call pending) |
| `app/phone.py`, `app/limits.py` | Call desk, watch hub, one-time tokens; call limits | Built, live call pending |
| `web/` | `index.html`, `app.js`, `voice.js`, `mic-worklet.js`, `phone.js`, `style.css`; vanilla JS, no build step | Built |
| `eval/run_eval.py`, `eval/synthetic.jsonl` | False-pass evaluation over 53 synthetic phrases | Built |
| `scripts/verify_record.py`, `scripts/voice_smoke.py`, `scripts/call_smoke.py` | Seal checker; live browser-voice smoke test; phone smoke test (live or `--simulate`) | Built (not run in CI: they need keys) |
| `tests/` | 630 tests, all passing at the time of writing | Built |
| `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml` | Image, one-command start, CI | Built |
| `replays/` | Consented recorded sessions for the replay tile | Planned (step 7) |

## 2. `app/loan.py` and the grading rules

`Loan` is a frozen dataclass: `loan_id, lender, sanctioned, processing_fee, insurance, instalment, frequency
("weekly" or "monthly"), instalments, total_repayable, apr_percent, grievance_contact, extra`.
Derived: `deductions = processing_fee + insurance`, `cash_in_hand = sanctioned - deductions`.

`SAMPLE_LOAN` (synthetic): id `SAMPLE-JLG-50000`, sanctioned 50,000, fee 1,000, insurance 590, instalment 1,095,
weekly, 52 instalments, total 56,940, APR 32.8%.

`FACTS = ("cash_in_hand", "deductions", "instalment", "frequency", "total")`, also the order in which the flow
asks about or repairs facts. `truth(loan, fact)` returns the true value (`"total"` maps to `total_repayable`).

### Tolerances
Gap is relative: `gap = |said - truth| / truth`. `TOLERANCE[fact] = (green_max, amber_max)`.

| Fact | True value | Green if gap <= | Amber if gap <= | Otherwise | Worked examples |
|---|---|---|---|---|---|
| cash_in_hand | 48,410 | 3% | 3% (no amber band) | red | 50,000 is 3.3% off: red. "pachaas hazaar" is flagged (pachaas/pachpan), but 55,000 is also red, so it stays red |
| deductions | 1,590 | 10% | 40% | red | 1,590 green; 1,000 or 590 said alone: amber "named only one deduction" |
| instalment | 1,095 | 5% | 12% | red | 1,100 ("gyarah sau") green; 1,000 amber |
| total | 56,940 | 3% | 8% | red | "pachaas hazaar" for the total: 50,000 is red but 55,000 is amber, so it is asked again (amber "unclear word, confirm") |
| frequency | weekly | exact match | n/a | red | "har mahine" (monthly) red |

### `_status(loan, fact, value, parts) -> (status, reason)`
1. Gap within green: `green`.
2. Deductions said as one part equal to the fee (1,000) or the insurance (590): `amber`, "named only one deduction".
3. Gap within amber: `amber`, "close but not exact".
4. Otherwise `red`, "does not match the loan".

### `judge(loan, fact, ev) -> Verdict`
1. No evidence: `grey`, "not said".
2. Frequency: `green` if `ev.value == loan.frequency`, else `red` ("said monthly").
3. Amounts: `status = _status(value)`. If the parser marked the number not confident and any alternative reading
   gets a different status, return `amber`, "unclear word, confirm" (she is asked again; fail closed). Otherwise
   return `status`.

The tenure (52 weeks) is not graded as a separate fact. Counts such as "52 hafte" are excluded from rupee amounts.

## 3. `app/grade.py`

- `Evidence(fact, value, quote, confident=True, alternatives=(), guessed=False, parts=1)`: `value` is a number
  for amounts and a string for frequency; `quote` is her exact words; `guessed` marks assignment by size alone;
  `parts` counts summed deduction amounts.
- `Verdict(fact, status, said=None, quote="", reason="")`: `status` is `green`, `amber`, `red` or `grey`
  (`app/flow.py` adds `unclear`).

### `assign(text, loan, target=None) -> dict[str, Evidence]`
1. `parse_numbers(text)`; drop counts: value <= 120 directly followed by a count word (hafte, week, mahine, month,
   kisht, instalment, baar, Devanagari forms).
2. For each number, take the nearest cue word within 32 characters, **inside the same clause only**. `_CLAUSE`
   splits on `, ; : . ! ?`, the danda `।`, and the words aur, and, phir, fir, then (और, फिर). So in
   "har hafte 1095 dena hai, kul 56,940" the word "kul" belongs to 56,940. Cues (`CUES`, Latin and Devanagari):
   cash in hand (haath, hand, milega, aayenge, nakad), deductions (kat, fee, bima, insurance, charge), instalment
   (kisht, emi, bharna, bharne, jama, dena, har hafte, har mahine, weekly, monthly), total (kul, total, milakar,
   wapas, lauta).
3. No cue: if `target` is set, is not frequency, and this is the only number, it answers `target`. Otherwise it
   goes to the amount fact whose true value is closest, if within 45% (`guessed=True`); else it is dropped.
4. Deductions: numbers cued to deductions are summed (quote "a + b", `parts=n`), ignoring any above 20% of the
   sanctioned amount (`_MAX_DEDUCTION_SHARE`). Other facts: the first number said wins.
5. Frequency: `parse_frequency(text)`; the quote is her own words for it (`_freq_quote`: "mahine nahi, har hafte"
   quotes "har hafte", not our label "weekly").

### `grade(text, loan, target=None) -> dict[str, Verdict]`
Verdicts only for facts she spoke about; if `target` is given and not mentioned, a `grey` verdict for it.

## 4. `app/hi_numbers.py`

Deterministic and pure (no I/O, no network, no model calls). Input is code-mixed speech-to-text: Devanagari,
romanised Hindi with spelling variants, English number words, digits (any grouping, Devanagari digits), currency
and filler words.

| Name | Contract |
|---|---|
| `ParsedNumber` | Frozen: `value` (float), `raw` (exact substring), `start`, `end` (offsets in the input), `confident` (False if a known confusion pair could flip it), `alternatives` (other values that still compose) |
| `normalize(text) -> str` | One character in, one out, so spans stay valid |
| `parse_numbers(text) -> list[ParsedNumber]` | All numbers in reading order; unclear words are skipped, never guessed |
| `parse_frequency(text) -> str or None` | `"weekly"`, `"monthly"`, `"fortnightly"`, `"daily"` or `None`. Negated cues dropped; strong cues ("har hafte", "weekly") beat bare period nouns; "52 hafte" is a duration, not a schedule |
| `parse_count(text)`, `parse_duration(text)` | Number of instalments; first "number period" phrase |

Composition: spelling keys into one lexicon; saade, sava, paune fuse with the next number (+0.5, +0.25, -0.25);
dedh 1.5, dhai 2.5; weak words (ek, do, saath "with") count only before a multiplier, currency word or unit noun;
groups compose greedily as [unit] [sau [unit]] then hazaar, lakh, crore in falling order. Confusion pairs
(pachaas/pachpan, saath/saat, sattar/satrah, fifteen/fifty and others) are re-evaluated with the swapped word.
Known limits are listed in the module docstring (for example, "aur" never joins two numbers).

## 5. `app/flow.py`

### `yes_no(text) -> bool | None`
Yes (haan, ji, yes, ok, theek, bilkul, sahmat, Devanagari forms) or no (nahi, na, no, mat, Devanagari forms);
if both appear, the first wins ("nahi, kisi ne nahi maanga" is no). Neither: `None`.

### `Session`
`Session(loan=SAMPLE_LOAN, lang="hi")`; `lang` is `"hi"` or `"en"`. Fields: `id` (12 hex characters), `state`,
`verdicts`, `rounds`, `first_answer` (status of her first answer per fact), `asked`, `target`, `questions` (for
the lender), `questions_asked`, `extra_money_reported`, `consent`, `ledger`. `MAX_ROUNDS = 2`,
`MAX_QUESTIONS = 3`.

- `start()`: logs `session_start`, calls `answer.warm()` (opens the Gemini connection in the background if a
  key is set), enters `consent`, says the intro.
- `hear(text)`: logs `heard`, dispatches to `_on_<state>`, returns the events. Empty text: "did not catch that".
  After `done`: `[]`. May take up to about 3 s in `explain` when Gemini is asked; the voice channels call it in a
  worker thread.
- `record()`: section 8.
- `_fact(v)`: converts a whole-number `said` to `int` before logging (so the record is written the same by Python
  and by a browser), records the first status per fact in `first_answer`, logs a `verdict`, emits `fact`.

### State machine

| State | Input | Transition | Outputs (events, ledger) |
|---|---|---|---|
| (new) | `start()` | to `consent` | `state`, `say` intro |
| any | empty text | stay | `heard`, `say` "did not catch" |
| `consent` | yes | to `explain` | `state`, 4 `say` lines (amount and cuts, weekly instalment for 52 weeks, total, "ask or say next") |
| `consent` | no | to `done` | `say` not started; consent `not_started`; `record` |
| `consent` | unclear | stay | `say` "did not catch" |
| `explain` | no fixed answer, a move-on word ("aage", "theek", "samajh", "nahi") and no question word | to `teachback` | `state`, `say` teach-back prompt |
| `explain` | answered by a fixed intent or by Gemini | stay (or `teachback` if this was question 3) | ledger `answered` (question, source `fixed` or `gemini`), `say` answer, then `say` "any other question?" or `say` "good questions, let us move on" and the teach-back prompt |
| `explain` | a question with no answer | stay (or `teachback` if question 3) | ledger `question_for_lender`, `say` "the lender will answer; I have noted it", then as above |
| `explain` | a statement with no answer and no question word | to `teachback` | `state`, `say` teach-back prompt |
| `teachback` | her explanation | to `check`, then `_next()` | `fact` per fact she mentioned, `say` praise |
| `check` | answer | `_next()` | `fact` for the target, and for any other mentioned fact not already green |
| `private` | yes | to `final_consent` | `case` `HOLD_REVIEW`, `say` thanks (goes to the grievance officer), `state`, `say` consent question |
| `private` | no | to `final_consent` | `say` thanks, `state`, `say` consent question |
| `private`, `final_consent` | unclear | stay | `say` "did not catch" |
| `final_consent` | yes / no | to `done` | ledger `consent` (`given` or `declined`, her words), `say` sealed or declined, `record` |
| `done` | anything | stay | nothing |

`_next()` walks `FACTS` and acts on the first fact not `green` or `unclear`:
1. `grey` and never asked: probe question (`lines.PROBE`), set `target`. Return.
2. Fewer than 2 repairs: repair quoting her words with the true figures, then a fresh recheck question
   (`lines.RECHECK`). Return.
3. Otherwise: `fact` `unclear`, `case` `CALLBACK`, `say` "someone from the lender will call you". Continue.
Then: `target = None`, enter `private`, ask the private question.

## 6. `app/answer.py`

`answer(text, loan) -> (line or None, source)` with source `"fixed"`, `"gemini"` or `"none"`:
1. `fixed_answer()`: regex intents written by us, checked in order: explain again simply, how long, what else
   (three things to remember, including that nobody may ask her for extra money), cash in hand, total,
   instalment, then `lines.faq` (insurance incl. "bima", fee, interest, missed payment).
2. If `GOOGLE_API_KEY` is set: `gemini_answer()`. Model `gemini-3.5-flash-lite`, temperature 0, JSON output,
   `thinking_level="minimal"`, one reused client per key. The prompt carries only the loan's facts and the
   question, and asks for at most two short sentences, digits only, no advice, no invented rules, fees or dates.
   The call runs in a thread pool and is abandoned after `GEMINI_TIMEOUT_S = 3.0` (Gemini rejects request
   deadlines under 10 s, so the cut-off is ours).
3. **The fence:** the answer is discarded unless every number in both the Hindi and English text is in
   `allowed_numbers(loan)` (sanctioned, fee, insurance, deductions, cash in hand, instalment, number of
   instalments, total, total minus sanctioned, APR and its rounded value, and 1, 2, 3). "I do not know" answers
   are discarded too. Digits in the Hindi answer are then written as Hindi words ("32.8" becomes "बत्तीस दशमलव आठ").
4. Otherwise `(None, "none")`: the flow notes the question for the lender.

`warm()` opens the Gemini connection in the background at session start, so the first question is not slow.
Tests never call Gemini (`tests/conftest.py` removes the key).

## 7. `app/lines.py`, `app/numwords.py`, `app/config.py`

`L(hi, en)` returns `{"hi", "en"}`. Lines are functions of the `Loan`, so another KFS changes the words, not the
code. Hindi amounts are words (`hindi_words(48410)` is "अड़तालीस हज़ार चार सौ दस"); English uses "Rs 48,410".
Contents: `intro`, `explain`, `faq`, `noted_for_lender`, `move_on`, `ask_more`, `teachback`, `PROBE`, `RECHECK`,
`repair`, `praise`, `unclear`, `FACT_LABEL`, `private_check`, `private_yes`, `private_no`, `consent`, `sealed`,
`declined`, `not_started`, `didnt_catch`.

`load_settings()` reads (all optional): `SARVAM_API_KEY`, `GOOGLE_API_KEY`, `TWILIO_ACCOUNT_SID`,
`TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `PUBLIC_BASE_URL`, `JUDGE_TOKEN`, `CALLS_ENABLED` ("1", "true" or
"yes"). `app/phone.py` also reads `MY_PHONE_NUMBER` and `SUPERVISOR_PHONE_NUMBER` (owner numbers for limits).

`GET /api/status` returns `{voice, extract, phone, text, replay}`, each `{"ready", "reason"}`:

| Feature | Ready when | Reason when not ready |
|---|---|---|
| voice | `SARVAM_API_KEY` set | "SARVAM_API_KEY not set" |
| extract | `GOOGLE_API_KEY` set | "GOOGLE_API_KEY not set: rules-only extraction" (grading is rules-only either way; the key enables Gemini answers to questions) |
| phone | Sarvam key, the three Twilio values, `PUBLIC_BASE_URL` and `CALLS_ENABLED` | "Phone calls off: Twilio keys, PUBLIC_BASE_URL or CALLS_ENABLED not set" |
| text | always | |
| replay | a `replays/*.json` file exists (set in `app/main.py`; none yet) | "No recorded test session added yet" |

## 8. `app/record.py` and the record

### Ledger
`Ledger.append(kind, **data)` adds `{"seq": n, "t": unix time rounded to ms, "kind": kind, ...data}` and its hash.

| kind | Fields |
|---|---|
| `session_start` | `loan_id`, `lang` |
| `said` | `hi`, `en` |
| `heard` | `text`, `state`, `target` |
| `answered` | `question`, `source` (`fixed` or `gemini`) |
| `question_for_lender` | `text` |
| `verdict` | `fact`, `status`, `said` (int for whole amounts), `quote`, `reason` |
| `case` | `case` (`CALLBACK` or `HOLD_REVIEW`), `detail` |
| `consent` | `value` (`given` or `declined`), `words` |
| `session_end` | |

### Hash chain
```
canon(entry) = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
h[0]         = "0" * 64
h[i]         = sha256_hex( h[i-1] + canon(entry[i]) )   encoded as UTF-8
seal         = h[last]
```
Changing, reordering, inserting or removing any entry changes every later hash, so the seal no longer matches.
Whole amounts are logged as integers, so a copy re-written by the browser's download button (JavaScript writes
`48410`, not `48410.0`) canonicalises to the same bytes and still verifies.

### Record (`Session.record()`)
```json
{
  "session_id": "12 hex chars",
  "loan_id": "SAMPLE-JLG-50000",
  "language": "hi",
  "facts": {"cash_in_hand": {"status": "green", "said": 48410, "her_words": "...", "explained_again": 1}},
  "understood_all": true,
  "right_first_answer": 2,
  "right_after_samjho": 5,
  "first_answer": {"cash_in_hand": "red", "deductions": "green", "...": "..."},
  "extra_money_reported": false,
  "questions_for_lender": [],
  "consent": "given",
  "entries": ["... ledger entries ..."],
  "seal_sha256": "64 hex chars"
}
```
`facts` and `first_answer` have all five keys; `first_answer` is the status of her first answer about each fact
(`green`, `amber`, `red`, `grey`) or `"not asked"`. `right_first_answer` counts facts green on her first answer;
`right_after_samjho` counts facts green at the end. `extra_money_reported` is `null` if the private question was
never reached. `consent` is `given`, `declined`, `not_started` or `null`.

The seal covers `entries` only; the summary fields are a convenience view to be checked against the entries.

### How to verify
```
python scripts/verify_record.py samjho-record-<id>.json     # prints VALID or TAMPERED and the seal
```
or `app.record.verify(record["entries"], record["seal_sha256"])`, or recompute the chain above in any language.

## 9. Event protocol (server to UI)

Typing mode returns events as JSON arrays from the REST API. Browser voice sends them as JSON text on
`/ws/browser`, between binary audio messages. A phone call publishes them to the watch hub, and the browser that
placed the call receives them on `/ws/watch`. The UI handles all of them in `handleEvent()` (`web/app.js`).

| type | Fields | Producer | UI handling |
|---|---|---|---|
| `say` | `text` (session language), `hi`, `en` | `Session._say` | Bot bubble; English gloss under Hindi |
| `heard` | `text` | `Session.hear` | User bubble |
| `state` | `state` | `Session._state` | Not rendered (voice uses state for turn timing on the server) |
| `fact` | `fact`, `status` (`green`, `amber`, `red`, `grey`, `unclear`), `said`, `quote`, `reason`, `round` | `Session._fact` | Colours the fact chip, shows her words |
| `case` | `case` (`CALLBACK`, `HOLD_REVIEW`), `detail` | `Session._case` | Note in the case list |
| `case` | `case` (`KEY_NOT_SET`, `BUSY`, `WATCH_UNKNOWN`), `detail`; the socket then closes | `app/main.py`, `app/voice.py` | Note showing the detail |
| `record` | `record` (section 8) | `Session._finish` | Record card, JSON download |
| `latency` | `turn`, `ms` (end of her speech to first reply audio) | `app/voice.py`, from Pipecat's `UserBotLatencyObserver` | Note per turn |
| `call` | `status` (`ringing` with `to` masked, `connected`, `ended`, `not_answered`) | `app/phone.py` | Call status line in `web/phone.js` |
| `clear` | none (browser wire message) | `BrowserSerializer` after an interruption | `web/voice.js` drops queued audio |

## 10. Endpoints (`app/main.py`)

| Method and path | Request | Response |
|---|---|---|
| `GET /healthz` | | `{"ok": true}` |
| `GET /api/status` | | Section 7 |
| `POST /api/text/start` | `{"lang": "hi" or "en"}` | `{"session_id", "events"}` |
| `POST /api/text/say` | `{"session_id", "text"}`; text truncated to 500 characters | `{"events", "done"}`; 404 "session expired, start again" |
| `WS /ws/browser?lang=hi` (or `en`) | Binary PCM16 mono 16 kHz audio | Binary PCM16 16 kHz reply audio; JSON events. No Sarvam key: `KEY_NOT_SET`, close. More than 4 live sessions: `BUSY`, close |
| `POST /api/call` | `{"phone": "+91...", "consent": true, "lang", "k"}` | `{"ok", "watch_id", "call_id" (masked), "to" (masked)}`. Errors: 403 paused (`CALLS_ENABLED` off) or wrong access code; 503 keys not set; 400 no consent or not an Indian mobile; 429 limit reached; 502 Twilio refused |
| `WS /ws/twilio` | Twilio Media Stream (8 kHz mulaw) carrying the one-time token `t` | Runs the phone session; closes with 1008 on a bad handshake or an unknown, used, expired or mismatched token |
| `WS /ws/watch?id=<watch_id>` | | The call's events (backlog first, then live), then close. Unknown id: `WATCH_UNKNOWN`, close |
| `GET /`, `GET /static/*` | | `web/index.html`, files in `web/` |

Typing sessions: in-memory, 30-minute idle expiry (`SESSION_TTL`), at most 200 (`MAX_SESSIONS`). FastAPI's
`/docs` and `/redoc` are disabled. Planned: `GET /api/replay` (step 7).

## 11. Voice pipeline: `app/voice.py`, `app/browser_serializer.py`

`build_worker(websocket, session, profile, serializer, api_key, publish=None, session_timeout)` builds:
`transport.input`, `EchoGate`, `SarvamSTTService`, user turn aggregator, `Brain`, `SarvamTTSService`,
`transport.output`, with `UserBotLatencyObserver` for `latency` events.

| Item | Browser profile (`BROWSER`) | Phone profile (`PHONE`) |
|---|---|---|
| Entry | `run_browser_session(websocket, lang, api_key)`; at most 4 at once (`MAX_SESSIONS`) | `run_phone_session(...)` from `CallDesk.run_stream`; concurrency bounded by `app/limits.py` (2 calls) |
| Rate and serializer | 16 kHz, `BrowserSerializer` | 8 kHz, Pipecat `TwilioFrameSerializer` with `auto_hang_up=True` |
| Speech-to-text | Sarvam `saaras:v4`, `codemix`, key-term hints (hazaar, kisht, bima, hafta, EMI and Devanagari forms) | same |
| Text-to-speech | Sarvam `bulbul:v4-flash`, voices `kavya_hi_conversational` (Hindi), `ishita_en_customer` (English) | same |
| Turn end | Silero VAD (confidence 0.7, start 0.2 s, stop 0.2 s); `StateSpeechTimeout`: 0.9 s when a number is expected, 0.6 s in `consent`, `private`, `final_consent` | same |
| Interruptions | None: `EchoGate` blanks mic audio while the bot speaks plus 0.25 s; `AlwaysUserMuteStrategy` | Allowed: `QuietVADStart` starts a turn on voice only while the bot is silent; while it speaks, `MinWordsUserTurnStartStrategy(min_words=2)` |
| Amount read-outs | (already half duplex) | `CriticalReadoutMute` mutes, and `EchoGate(only_if=brain.critical)` blanks audio before speech-to-text, while a reply containing an amount (digits, "रुपये", "Rs") plays |
| Events | Down the pipeline as JSON on the same socket | `publish` to the watch hub, never to Twilio |
| Time limit | 300 s session timeout | Twilio `time_limit=300`, pipeline timeout 330 s |

`Brain`: on start, emits `Session.start()` events; on each final user turn, runs `Session.hear(text)` in a worker
thread; sends every event; speaks all `say` lines of one reply as one utterance (so the user is not unmuted
between lines); ends the pipeline after the goodbye. No LLM is called.

`BrowserSerializer`: in, binary PCM16 mono 16 kHz (text messages ignored); out, binary PCM16 16 kHz audio, JSON
text for events, `{"type": "clear"}` after an interruption.

Browser client (`web/voice.js`, `web/mic-worklet.js`): AudioWorklet downsamples the mic to 16 kHz PCM16 in
20 ms chunks; playback is gapless with a 0.12 s cushion; the mic sends silence while playing and for 0.3 s after.

## 12. Phone: `app/phone.py` and `app/limits.py` (built, live call pending)

`CallDesk.place(number, consent, lang, k, ip)` checks, in order: `CALLS_ENABLED`; Sarvam, Twilio and
`PUBLIC_BASE_URL` set; `JUDGE_TOKEN` matches `k` if set (constant-time); consent ticked; number matches
`^\+91[6-9]\d{9}$`; `CallLimiter.reserve()`. Then it creates a one-time token (`secrets.token_urlsafe(24)`) and a
watch id, opens the watch channel, and calls Twilio `calls.create(to, from_, twiml, time_limit=300, timeout=30)`
with TwiML `<Connect><Stream url="wss://HOST/ws/twilio"><Parameter name="t" .../>`. If the stream has not
connected after `TOKEN_TTL = 120` s, the slot is released and the watcher told "not answered".

`run_stream(websocket)`: `parse_telephony_websocket`, then `claim(token, call_sid)`: one use, within 120 s, and
for the call SID it was issued to. Holds the limit slot for the call, runs `run_phone_session`, releases the slot
and closes the watch channel at the end.

`WatchHub`: in-process pub/sub per watch id; keeps up to 500 events for late watchers; channels expire after an
hour.

`client_ip(request)`: the socket address; `CF-Connecting-IP` or `X-Forwarded-For` only when the request comes
from loopback (a local tunnel).

`CallLimiter` (all in memory, reset on restart):

| Limit | Value |
|---|---|
| Per number | 1 call per 30 min, 3 per 24 h, keyed by an HMAC-SHA256 of the number with a random per-process salt |
| Per IP | 3 calls per hour |
| Global | 2 calls at once (a ringing call holds its slot 90 s; a connected call holds it for the call), 40 per 24 h |
| Owner numbers | `MY_PHONE_NUMBER`, `SUPERVISOR_PHONE_NUMBER` skip the per-number and per-IP limits, not the global ones |

Logs show numbers masked (`+91XXXXXX1234`) and call SIDs shortened.

## 13. Evaluation and scripts

`eval/run_eval.py`: each line of an `eval/*.jsonl` file is `{"text", "target", "expect": {fact: status},
"source"}`. It grades every line and reports phrases, checks, accuracy, false passes (green when the expected
status is not green) and false fails; exits 1 on any false pass. `eval/synthetic.jsonl`: 53 phrases written by us
in Hindi, Devanagari, Hinglish, English and digits. Current result: 71 of 71 checks right, 0 false passes. Field
phrases from consented sessions go in a separate file with `"source": "field"` (Planned, step 7).

Run: `python -m eval.run_eval`.

Scripts (need keys; not in CI): `scripts/verify_record.py` (seal check); `scripts/voice_smoke.py` (plays
Sarvam-made Hindi answers into a local server over a real WebSocket, prints per-turn latency);
`scripts/call_smoke.py` (live call to `MY_PHONE_NUMBER`, or `--simulate`: the real `/api/call`, TwiML,
`/ws/twilio` and `/ws/watch` with live Sarvam speech, faking only Twilio's dialler and the handset).

## 14. Test map (630 tests)

| File | Count | Covers |
|---|---|---|
| `tests/test_hi_numbers.py` | 544 | Every word 0 to 99 in both scripts; spelling variants; composition; separating adjacent numbers; fail closed; confusion flags; spans; code-mixed sentences; frequency, count, duration; `normalize`; round trip with `app/numwords.py`; no em dashes |
| `tests/test_flow.py` | 38 | Yes/no (12 cases); classic miss red; correct teach-back all green; bare number answers the asked fact; one deduction amber; "52 hafte" not rupees; "aur" splits clauses; schedule quoted in her words; happy path seals a verifiable record; repair quotes her words and rechecks; two failed rounds give UNCLEAR and CALLBACK; HOLD_REVIEW; FAQ answer; unknown question noted for the lender; "no" at the start; English mode; tampering breaks the seal; integer amounts so a browser copy verifies; first-answer and after-Samjho counts; real questions get real answers (6 cases from the first real-mic test); move on after three questions; Gemini answers may only use the loan's numbers |
| `tests/test_phone.py` | 36 | Number rule and masking; TwiML; per-number, per-IP, concurrency, daily and owner limits; salted hashes; refusal without keys; kill switch per request; access code; consent; call placed with limits and watch id; Twilio error releases the slot; 429; token claimed once, for its own call, and expiry; bad token rejected; watch hub backlog and live events; `/ws/watch`; `Brain` publishes to the hub and flags amount replies; read-out mute and quiet VAD start; phone pipeline builds offline at 8 kHz |
| `tests/test_voice.py` | 6 | Serializer in and out; `/ws/browser` refuses politely without a key; turn timeout follows the session state; `Brain` speaks one utterance per reply and ends when done |
| `tests/test_app.py` | 3 | No-keys start and main screen; status names missing keys; status never echoes a key |
| `tests/test_eval.py` | 1 | At least 50 phrases, 0 false passes, accuracy at least 95% |
| `tests/test_source_hygiene.py` | 2 | No control characters and no em dashes in `app/`, `web/`, `tests/`, `docs/` |
| `tests/conftest.py` | | Removes `GOOGLE_API_KEY` so tests never call Gemini |
| `.github/workflows/ci.yml` | | `pytest` on every push and pull request; fresh-clone `docker compose up` with no keys |
| Planned | | Field phrases in the eval (step 7); a live-call test once Twilio is set up (step 6) |

Run: `python -m pytest -q`.
