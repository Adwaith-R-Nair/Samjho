# Samjho: her voice, not her thumb

**Before a microfinance borrower acknowledges her loan, Samjho explains it to her by voice in Hindi, asks her
to say it back in her own words, checks every number in code, re-explains only what she got wrong, and only then
records her spoken consent.**

Today that acknowledgement is a thumbprint, an OTP or an "I agree" tap, taken after a field officer reads the Key
Fact Statement aloud, often to a whole group. RBI's Deputy Governor called this "pseudo consent" on 13 Nov 2026.
Samjho replaces the tap with proof of understanding: what she said, what the loan says, and what changed after
Samjho explained it, sealed in a tamper-evident record.

Built during the Scaler x Wispr Flow "India Runs on Voice" hackathon, Round 2 (27 to 30 Nov 2026), by voice with
Wispr Flow. Theme: Livelihoods and small business. The loan and the people are synthetic.

## What works today

| | What happens | Where in the code |
|---|---|---|
| Talk in the browser | Speak Hindi, Hinglish or English; Samjho answers in a Hindi or English (India) voice. Sarvam speech-to-text and text-to-speech on Pipecat | `app/voice.py`, `app/browser_serializer.py`, `web/voice.js` |
| Type instead | The same conversation and the same checks, no microphone, no keys | `POST /api/text/*` in `app/main.py` |
| The conversation | Consent, the loan in four short lines with questions allowed, "explain it to your daughter", then for each fact she missed: ask, re-explain with her own words and figures, re-check with a fresh question; two rounds, then a human callback (never a block) | `app/flow.py`, `app/lines.py` |
| Checked in code | Five facts (cash in hand, deductions, instalment, how often, total) judged against the loan with fixed tolerances. A word phone audio often swaps ("pachaas" or "pachpan") triggers a re-ask only when the other reading would change the verdict | `app/grade.py`, `app/loan.py` |
| Hindi numbers | "adtaalis hazaar chaar sau das", "पंद्रह सौ नब्बे", "dedh hazaar", "₹48,410", "forty eight thousand" | `app/hi_numbers.py` (544 tests) |
| Private question | "Did anyone ask you for extra money?" A yes is held for the lender's grievance officer, not the field officer | `Session._on_private` |
| Sealed record | Every turn is hash-chained with SHA-256; the record shows each fact, her words, how often it was re-explained, right on her first answer vs after Samjho, and her consent. Anyone can re-verify a downloaded record with `python scripts/verify_record.py file.json` | `app/record.py`, `Session.record()` |
| Runs anywhere | `docker compose up` with no keys shows the main screen; features that need a key say which key is not set | `app/config.py`, CI job `fresh-clone-boot` |

Planned during Round 2 and not yet in this README's "works" list: a real phone call to any Indian mobile (Twilio),
replays of consented real test sessions, and the hosted live link. See [docs/ROADMAP.md](docs/ROADMAP.md).

## Numbers we measured

- **False passes: 0.** A false pass is a fact marked understood when it was not. `eval/run_eval.py` over 53
  answers we wrote (Hindi, Devanagari, Hinglish, English, digits; right and wrong): 71 of 71 checks correct. A
  test fails the build on any false pass. These answers are synthetic; field phrases will be added and marked.
- **Reply time in the browser: about 1.05 s** after a yes or no and **about 1.3 s** after a number answer, from the
  end of her speech to the first reply audio, measured with live Sarvam by `scripts/voice_smoke.py`. Of that, 0.6 s
  or 0.9 s is a deliberate wait so she can finish ("pachaas ... hazaar").
- **586 automated tests**, run on every push with a fresh-clone docker boot.

## Run it

```
docker compose up --build
```

Open http://localhost:7860. With no keys, "Type instead" works fully. For voice, copy `.env.example` to `.env`
and add `SARVAM_API_KEY` (and optionally `GOOGLE_API_KEY`), then restart. The browser mic works on localhost
without HTTPS.

Without Docker:

```
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt     # macOS/Linux: .venv/bin/pip
.venv/Scripts/python -m uvicorn app.main:app --port 7860
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m eval.run_eval
```

Try this in "Type instead" (Hindi): say `haan`, then `aage`, then the classic miss
`pachaas hazaar haath mein aayenge aur har mahine hazaar rupaye bharne hain`. Cash in hand and how often turn red,
the instalment amber, and Samjho re-explains the first one in your own words.

## How it works

```
browser mic or typing --> speech-to-text (Sarvam saaras:v4, codemix) --> Session (app/flow.py)
                                                                          |  grade.py + hi_numbers.py
                                                                          |  decide green / amber / red in code
UI panel <-- events (say, heard, fact, case, record, latency) <-----------+
speaker  <-- text-to-speech (Sarvam bulbul:v4-flash) <-- what to say next
```

No LLM decides whether she understood. The decision is deterministic code, so it can be tested, audited and
explained to a regulator. Design docs: [PRD](docs/PRD.md), [high-level design](docs/HLD.md),
[low-level design](docs/LLD.md), [roadmap](docs/ROADMAP.md). How it was built, including every bug:
[build log](docs/BUILD_LOG.md). How Wispr Flow was used: [Flow log](docs/FLOW_LOG.md).

## Honest limits

- Vendors already read loan terms aloud and record a "yes". What Samjho adds is proof of understanding: her own
  words, numbers checked in code, and only her gaps re-explained. We do not claim to be first at teach-back.
- In the browser the conversation is half duplex (she cannot interrupt), because a plain WebSocket has no echo
  cancellation and laptop speakers would feed the bot's voice back as hers.
- One sample loan. A lender would load each borrower's own Key Fact Statement into `app/loan.py`'s shape.

## Data and privacy

All loans and people in this repository are synthetic. Keys live only in `.env`, never in the code; the status
endpoint names a missing key but never returns a value (tested). No Aadhaar or account number is asked for or
stored.

## License

MIT
