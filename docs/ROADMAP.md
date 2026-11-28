# Samjho: roadmap

Status words: **Done** (committed and tested), **Partly done**, **Planned** (not built). The build history with
what broke and how it was fixed is in [BUILD_LOG.md](BUILD_LOG.md). Requirement IDs (FR-n) refer to
[PRD.md](PRD.md). Test suite at the time of writing: 670 tests, all passing.

## Round 2: 27 to 30 Nov 2026

Submission deadline: Mon 30 Nov, 11:59 pm IST. Each step is one commit after its tests pass.

### Before the build (Fri 27 Nov)

| Item | Status | Notes |
|---|---|---|
| Capture the Round 2 brief and rules | Done | Summary in BUILD_LOG.md |
| Choose what to build: extend Round 1 as "Her voice, not her thumb" | Done | Reasons and honest limits in BUILD_LOG.md |
| Sarvam and Gemini keys created and tested | Done | |
| Twilio paid account (trial accounts cannot call India) | Done (28 Nov) | Account upgraded, Individual compliance profile approved, a US local number bought (Voice only); India enabled in Voice Geo Permissions (BUILD_LOG commit 13) |
| Hosting for the live link | Planned | Railway trial (not yet deployed); a Cloudflare tunnel from the laptop for development only |

### Build steps

| Step | Work | Status | Evidence in the repo |
|---|---|---|---|
| 1 | App starts with no keys: FastAPI, one-screen UI, `/healthz`, `/api/status`, Dockerfile, docker compose, `.env.example`, CI that boots a fresh clone | Done (BUILD_LOG commit 1) | `app/main.py`, `app/config.py`, `web/`, `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`, `tests/test_app.py` |
| 2 | Hindi/Hinglish/Devanagari/digit number parser, confusion pairs flagged, fail closed (FR-5) | Done (commit 3) | `app/hi_numbers.py`, `tests/test_hi_numbers.py` (544 cases) |
| 3 | Grader and conversation state machine end to end by typing: catch, repair, recheck, private question, consent, seal (FR-1 to FR-14) | Done (commit 4, six bugs found and fixed; commit 5 adds first-answer vs after-Samjho counts) | `app/flow.py`, `app/grade.py`, `app/lines.py`, `app/loan.py`, `app/numwords.py`, `app/record.py`, `tests/test_flow.py`, `tests/test_source_hygiene.py` |
| 4 | Browser voice: mic over WebSocket, Sarvam speech-to-text and text-to-speech, half duplex, latency per turn (FR-17) | Done (commit 7, latency measured) | `app/voice.py`, `app/browser_serializer.py`, `web/voice.js`, `web/mic-worklet.js`, `tests/test_voice.py`, `scripts/voice_smoke.py` |
| 5 | Gemini help and English mode | Partly done. Gemini answers her questions, fenced to the loan's numbers (commit 9, `app/answer.py`). English mode works by typing and voice. Gemini help with mapping words to facts (FR-18): Planned; grading stays rules-only | `app/answer.py`, `tests/test_flow.py` |
| 6 | Twilio phone channel with call limits and kill switch (FR-19, FR-20); first real call; measure latency | Done. Built in commit 10 and proven in a simulated call; two real calls on 28 Nov (commits 13 and 14): median reply 1.34 s over 22 turns, the second call a full session to the sealed record. Five problems the first call showed were fixed with its exact transcripts. Not yet proven: hang-up through Twilio's API mid-session | `app/phone.py`, `app/limits.py`, `web/phone.js`, `tests/test_phone.py`, `scripts/call_smoke.py` (live or `--simulate`) |
| 7 | Unaided test sessions with real people on the synthetic loan, recorded only with consent; replay tile (FR-21); field phrases into the eval | Partly done. Consented recording and synced replay are built (commit 12): consent box, spoken recording notice, masked phone numbers, path-checked replay API. Planned: consented real user sessions (so far only the builder's own real-mic test and his two real calls, none saved as a replay) and field phrases into the eval | `app/recording.py`, `web/replay.js`, `replays/README.md`, `tests/test_replay.py` |
| 8 | Railway deploy (hosted live link); smoke test it from another network | Planned. The real calls ran through a Cloudflare quick tunnel to the laptop | |
| 9 | Eval report, README, deck text, 3-minute video, one-page record summary. Freeze at 18:00 Mon 30 Nov, submit by 21:00 | Partly done: eval harness (commit 6) and a README that only claims what runs, plus `scripts/verify_record.py` (commit 8). README now carries the real-call numbers. Eval report with field phrases, deck, 3-minute video and summary page: Planned | `eval/run_eval.py`, `eval/synthetic.jsonl`, `tests/test_eval.py`, `README.md` |

Also done along the way: design docs (commits 2 and 5).

### Gates for every step
- No step merges if tests fail or the eval shows any false pass on a critical fact (`tests/test_eval.py`).
- No real personal data in the repository; synthetic loan only; replays only from consenting testers.
- Every README and deck claim points to code or a logged result.

## After Round 2

Round 2 results and the finale shortlist are due on 2 Dec. The finale is on 13 Dec (a 24-hour build, then a
pitch). Everything below is **Planned**; none of it is built.

### Finale build (13 Dec)
| Item | Why |
|---|---|
| Lender view of records: list, filter by CALLBACK and HOLD_REVIEW, verify seal | The buyer's screen |
| Load any KFS into the `Loan` shape (`app/loan.py`) from a file or API | Each borrower's own loan instead of the sample |
| One more language through the same engine | Show the engine is not Hindi-only |
| Browser barge-in with echo cancellation | The phone already allows interruptions; the browser is half duplex today |

### Pilot shape
| Item | Plan |
|---|---|
| Partner | One NBFC-MFI branch, shadow mode: Samjho runs alongside the current acknowledgement and does not replace it |
| Measure | Facts right on first answer vs after Samjho (already in every record); correct recall at signing and again later; completion rate; HOLD_REVIEW and CALLBACK volumes; call minutes per loan |
| Safeguards | Borrower consent before any recording, lender data stays in the lender's environment, no decision on the loan is taken by Samjho |
| Reach | Through the two RBI-recognised self-regulatory organisations (Sa-Dhan and MFIN), which can reach member lenders |

### More languages
Kannada, Bengali, Odia and Tamil through the same flow and grader. Each language needs its own number parser,
cue words, spoken lines, fixed answers and tests before it ships; the zero-false-pass gate applies per language.

### Lender integration
| Item | Plan |
|---|---|
| Loan origination system | Trigger a session at disbursal, receive the record back |
| Case routing | CALLBACK to the lender's call team; HOLD_REVIEW to the grievance officer, never to the field officer |
| Telephony | An Indian telephony provider after KYC, so calls do not arrive labelled "International Call" |
| Storage | Records and audio retained per the lender's policy, with consent; seal verification as a service |
| Pricing | Per completed check, to be validated in the pilot |
