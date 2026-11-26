# Samjho: roadmap

Status words: **Done** (in the repository and tested), **In progress** (code being written now),
**Planned** (not built). Test suite at the time of writing: 577 tests, all passing. The build history with what broke and how it was fixed is in
[BUILD_LOG.md](BUILD_LOG.md). Requirement IDs (FR-n) refer to [PRD.md](PRD.md).

## Round 2: 27 to 30 Nov 2026

Submission deadline: Mon 30 Nov, 11:59 pm IST. Each step is one commit after its tests pass.

### Before the build (Fri 27 Nov)

| Item | Status | Notes |
|---|---|---|
| Capture the Round 2 brief and rules | Done | Summary in BUILD_LOG.md |
| Choose what to build: extend Round 1 as "Her voice, not her thumb" | Done | Reasons and honest limits in BUILD_LOG.md |
| Sarvam and Gemini keys created and tested | Done | One Hindi line synthesised, Flash models listed |
| Twilio paid account (trial accounts cannot call India) | Planned | Waits on an international-enabled card; does not block browser voice |
| Hosting for the live link | Done (decision) | Railway trial; a Cloudflare tunnel from the laptop for development only |

### Sat 28 Nov

| Step | Work | Status | Evidence in the repo |
|---|---|---|---|
| 1 | App starts with no keys: FastAPI, one-screen UI, `/healthz`, `/api/status`, Dockerfile, docker compose, `.env.example`, CI that boots a fresh clone | Done | `app/main.py`, `app/config.py`, `web/`, `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`, `tests/test_app.py` |
| 2 | Hindi/Hinglish/Devanagari/digit number parser with 150+ tests, confusion pairs trigger a re-ask, fail closed (FR-5) | Done (BUILD_LOG commit 3) | `app/hi_numbers.py`, `tests/test_hi_numbers.py` (544 test cases) |
| 3 | Deterministic grader and conversation state machine, end to end by typing: catch, repair, recheck, private question, consent, seal (FR-1 to FR-14) | Done (BUILD_LOG commit 4, with six bugs found and fixed) | `app/flow.py`, `app/grade.py`, `app/lines.py`, `app/loan.py`, `app/numwords.py`, `app/record.py`, typing mode in `web/app.js`, `tests/test_flow.py`, `tests/test_source_hygiene.py` |
| 4 | Browser voice channel: microphone over WebSocket, Sarvam speech-to-text and text-to-speech, half duplex by default, latency per turn (FR-17) | In progress | Server side in the repository: `/ws/browser` in `app/main.py`, `app/voice.py`, `app/browser_serializer.py`. Browser microphone client in `web/` not yet written |

### Sun 29 Nov

| Step | Work | Status |
|---|---|---|
| 5 | Gemini extraction that only suggests assignments, 1.5 s timeout, rules-only fallback (FR-18). English mode end to end (FR-15: English spoken lines already exist in `app/lines.py`) | Planned |
| 6 | Twilio phone channel with call limits, number rule and kill switch (FR-19); first real call; measure latency | Planned |
| 7 | Unaided test sessions with real people on the synthetic loan, recorded only with consent; replay tile (FR-20). The tile turns on only when a session file exists under `replays/` | Planned |
| 8 | Railway deploy; smoke test the live link from another network | Planned |

### Mon 30 Nov

| Step | Work | Status |
|---|---|---|
| 9 | Eval report (accuracy, false passes, P50/P95 latency), README where every claim maps to code, deck text, 3-minute video, one-page record summary (FR-21). Freeze at 18:00, submit by 21:00 | Planned |

### Gates for every step
- No step merges if tests fail or the eval shows any false pass on a critical fact.
- No real personal data in the repository; synthetic loan only; replays only from consenting testers.
- Every README and deck claim points to code or a logged result.

## After Round 2

Round 2 results and the finale shortlist are due on 2 Dec. The finale is on 13 Dec (a 24-hour build, then a
pitch). Everything below is **Planned**; none of it is built.

### Finale build (13 Dec)
| Item | Why |
|---|---|
| Barge-in on the phone path, per-state turn timing for number answers | Natural conversation on a keypad phone |
| Lender view of records: list, filter by CALLBACK and HOLD_REVIEW, verify seal | The buyer's screen |
| Load any KFS into the `Loan` shape (`app/loan.py`) from a file or API | Each borrower's own loan instead of the sample |
| One more language through the same engine | Show the engine is not Hindi-only |

### Pilot shape
| Item | Plan |
|---|---|
| Partner | One NBFC-MFI branch, shadow mode: Samjho runs alongside the current acknowledgement and does not replace it |
| Measure | Facts correct at first teach-back vs after repair; correct recall at signing and again later; completion rate; HOLD_REVIEW and CALLBACK volumes; call minutes per loan |
| Safeguards | Borrower consent before any recording, lender data stays in the lender's environment, no decision on the loan is taken by Samjho |
| Reach | Through the two RBI-recognised self-regulatory organisations (Sa-Dhan and MFIN), which can reach member lenders |

### More languages
Kannada, Bengali, Odia and Tamil through the same flow and grader. Each language needs its own number parser,
cue words, spoken lines and tests before it ships; the zero-false-pass gate applies per language.

### Lender integration
| Item | Plan |
|---|---|
| Loan origination system | Trigger a session at disbursal, receive the record back |
| Case routing | CALLBACK to the lender's call team; HOLD_REVIEW to the grievance officer, never to the field officer |
| Telephony | An Indian telephony provider after KYC, so calls do not arrive labelled "International Call" |
| Storage | Records and audio retained per the lender's policy, with consent; seal verification as a service |
| Pricing | Per completed check, to be validated in the pilot |
