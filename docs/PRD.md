# Samjho: product requirements

"Her voice, not her thumb."

Before a microfinance borrower acknowledges her loan, Samjho explains it to her by voice in Hindi, asks her to
say it back in her own words, checks every number in code, re-explains only what she got wrong, asks privately
whether anyone demanded extra money, and only then records her spoken consent as a sealed record.

Built for the Scaler x Wispr Flow "India Runs on Voice" hackathon, Round 2 (27 to 30 Nov 2026), theme
"Livelihoods and small business", as an extension of the Round 1 idea.

All loans and people in this repository are synthetic. No real borrower data is stored.

How to read this document: anything not yet in the code is marked **Planned** with its roadmap step
(see [ROADMAP.md](ROADMAP.md)). Design details are in [HLD.md](HLD.md) and [LLD.md](LLD.md).

## 1. Problem

### The form step she fills today
RBI requires that the Key Fact Statement (KFS) be explained to the borrower and that "an acknowledgement shall
be obtained that he/she has understood the same" (RBI circular RBI/2024-25/18, para 4,
https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12663&Mode=0).

Today that acknowledgement is a form step:

| How it is collected today | Source |
|---|---|
| Aadhaar eSign by OTP or biometric on the field officer's tablet | Leegality, microfinance flow: https://www.leegality.com/microfinance |
| A tap in the lender's app (Hello Ujjivan handles group-loan e-signatures and loan acknowledgements) | Ujjivan SFB press release, 16 Oct 2025: https://www.ujjivansfb.bank.in/press-release/Ujjivan-SFBs-Hello-Ujjivan-app-facilitates-rupess-690crore-in-financial-transactions-bringing-digital-banking-to-first-time-borrowers-16-oct-2025 |
| A signature or thumbprint on paper | Common practice; exact wording varies by lender |

A thumbprint or an OTP shows that she was present. It does not show that she understood.

### The understanding gap
- RBI Deputy Governor S C Murmu, MFIN event, Mumbai, 13 Nov 2026: "Pseudo consent is a mere compliance
  formality, devoid of any meaningful impact", describing borrowers who "sign every document without adequate
  information on what it contains". Source: https://www.rbi.org.in/Scripts/BS_SpeechesView.aspx?Id=1590
- Sa-Dhan with Grant Thornton Bharat, face-to-face survey of 1,264 borrowers in 6 states (March 2026):
  21% cannot understand their loan documents and 14% only partly (66% cannot in Bihar); 91% said pricing was
  "very clear", yet 72% said they paid no processing fee although most loans carry one; only 63% know any way to
  complain, and only 45% of those know a route beyond the field officer. Source:
  https://www.sa-dhan.net/wp-content/uploads/2026/05/Impact-study-Report_Final.pdf
- RBI's Responsible Business Conduct Second Amendment Directions 2026 (RBI/2026-27/123) take effect on
  1 Jan 2027: https://m.rbi.org.in/Scripts/NotificationUser.aspx?Id=13493&Mode=0

Self-report says "understood". Recall says otherwise. A teach-back measures that gap; a thumbprint hides it.

### Why voice
For a borrower who cannot read the KFS, saying the loan back in her own words is the only way she can show what
she understood. A tap or a thumb cannot carry that information. Samjho replaces the acknowledgement step with
speech, and the step completes only after what she says has been checked against her loan.

## 2. Users

| Role | Who | What they need from Samjho |
|---|---|---|
| Borrower (primary user) | A woman in a joint-liability group, Hindi speaking, low literacy, often a basic phone. **Illustrative persona:** Sunita, a home tailor in Bihar taking a Rs 50,000 loan. Sunita is not a real person. | Hear her loan simply, ask questions, say it back, have only her mistakes explained again, report extra-money demands privately, give consent in her own voice |
| Buyer | NBFC-MFI compliance and operations teams (also small finance banks and bank business correspondents) | Evidence that each borrower understood the key numbers, a record that cannot be quietly edited, and a private channel for extra-money reports that bypasses the field officer |
| Field officer | The lender's staff who disburse and today collect the acknowledgement | A step that runs on its own and never blocks a loan for a comprehension gap |

How many: about 5.6 crore active microfinance borrowers (5.61 crore at 30 Jun 2026, SIDBI/Equifax
Microfinance Pulse Vol XXVIII, Sep 2026:
https://assets.equifax.com/marketing/india/assets/mfi-pulse-vol-xxviii-sept-2026.pdf).

## 3. Goals and non-goals

### Goals (Round 2)
1. One core flow that works end to end: consent, explain, teach-back, grade, repair, recheck, private
   question, spoken consent, sealed record.
2. Every correctness decision made by deterministic code with stated tolerances.
3. Starts with `docker compose up` and no keys; features that need a key say which key is not set.
4. Runs by voice in the browser (**In progress**, step 4) and on a real phone call (**Planned**, step 6), and
   by typing with the same checks (**Built**, step 3).
5. Hindi first, with an English mode so non-Hindi users can finish the flow.

### Non-goals
- Not a loan origination system, and not a legal e-signature or proof of consent in law.
- Does not decide whether a loan is approved. It never blocks a loan for a comprehension gap.
- No real borrower data, no Aadhaar, no account numbers.
- No languages beyond Hindi and English in Round 2.
- No LLM decides whether an answer is right.
- No post-disbursal follow-up calls, missed-call ledger or multi-tab dashboards (Round 1 ideas, out of scope).

## 4. The one core flow

```
consent -> explain (4 points, questions allowed) -> teach-back ("explain it to your daughter")
  -> grade 5 facts in code
  -> for each fact not green: ask if unsaid, else re-explain with her own words and recheck with a fresh
     question (at most 2 rounds), else mark UNCLEAR and open a CALLBACK case
  -> private question: "did anyone ask you for extra money?" (yes opens a HOLD_REVIEW case)
  -> spoken consent (given or declined)
  -> sealed record (hash-chained session log, SHA-256 seal)
```

The five facts on the synthetic sample loan (`app/loan.py`):

| Fact | Value | What a classic miss looks like |
|---|---|---|
| Cash in hand | Rs 48,410 | "pachaas hazaar" (Rs 50,000, the sanctioned amount) |
| Deductions | Rs 1,590 (fee Rs 1,000 + insurance Rs 590) | naming only the fee |
| Instalment | Rs 1,095 | "hazaar" (Rs 1,000) |
| Frequency | weekly, 52 instalments | "har mahine" (monthly) |
| Total repayable | Rs 56,940 | not knowing it at all |

## 5. Functional requirements

Status: **Built** means present in the code and covered by passing tests. **In progress** means some of the
code is in the repository but its step is not finished. **Planned** names the roadmap step.

| ID | Requirement | Status | Where |
|---|---|---|---|
| FR-1 | Ask permission to start; "no" ends politely and still produces a record with consent `not_started` | Built | `app/flow.py` `_on_consent` |
| FR-2 | Explain the loan in 4 short lines built from the loan data, amounts spoken as Hindi words | Built | `app/lines.py` `explain`, `app/numwords.py` |
| FR-3 | Answer questions during the explanation from fixed answers (insurance, fee, interest, missed payment); unknown questions are logged for the lender, never guessed | Built | `app/lines.py` `faq`, `app/flow.py` `_on_explain` |
| FR-4 | Teach-back prompt asking her to explain the loan in her own words | Built | `app/lines.py` `teachback` |
| FR-5 | Parse Hindi, Hinglish, Devanagari, English and digit numbers and payment schedules; known confusion pairs (pachaas/pachpan, saath/saat, sattar/satrah) are flagged not confident; unclear words are skipped, never guessed (fail closed) | Built (544 test cases) | `app/hi_numbers.py`, `tests/test_hi_numbers.py` |
| FR-6 | Assign each spoken number to a fact using cue words in the same clause; a bare number answers the fact just asked; counts of weeks are not read as rupees | Built | `app/grade.py` `assign` |
| FR-7 | Grade each fact green, amber, red or grey against the loan with fixed tolerances, keeping her exact words as evidence | Built | `app/grade.py` `judge`, `app/loan.py` `TOLERANCE` |
| FR-8 | Re-explain only facts that are not green, quoting her words, then recheck with a different question; at most 2 rounds per fact | Built | `app/flow.py` `_next`, `app/lines.py` `repair`, `RECHECK` |
| FR-9 | After 2 rounds, mark the fact UNCLEAR, open a CALLBACK case and continue; never block | Built | `app/flow.py` `_next` |
| FR-10 | Private extra-money question; "yes" opens a HOLD_REVIEW case addressed to the lender's grievance officer | Built (case in the record and panel). Routing to a lender system: Planned (after Round 2) | `app/flow.py` `_on_private` |
| FR-11 | Spoken consent, recorded as `given` or `declined` with her words | Built | `app/flow.py` `_on_final_consent` |
| FR-12 | Append-only, hash-chained session log; record with per-fact results, cases, questions and a SHA-256 seal; anyone can re-verify the chain, including a copy re-written by a browser | Built | `app/record.py`, `Session.record()` |
| FR-13 | One-screen UI: start tiles, transcript with English gloss, 5 fact chips, case notes, record card, JSON download | Built for typing mode | `web/` |
| FR-14 | Typing mode runs the real flow and grader with no keys | Built | `POST /api/text/start`, `POST /api/text/say` |
| FR-15 | English mode for the whole conversation | Spoken lines built (`lang="en"`); English end to end: Planned (step 5) | `app/lines.py`, `Session(lang=...)` |
| FR-16 | `/api/status` names each missing key and never returns a key's value | Built | `app/config.py`, `tests/test_app.py` |
| FR-17 | Browser voice: microphone over WebSocket, Sarvam speech-to-text and text-to-speech, half duplex, latency per turn on the panel | In progress (step 4): server side is in the repository (`/ws/browser`); the browser microphone client is not yet in `web/` | `app/voice.py`, `app/browser_serializer.py` |
| FR-18 | LLM extraction (Gemini) that only suggests fact assignments, with a 1.5 s timeout and rules-only fallback | Planned (step 5) | `app/extract.py` |
| FR-19 | Real phone call to an Indian mobile ("we call you"), with consent checkbox, number rule, rate limits and kill switch | Planned (step 6) | `/api/call`, `/ws/twilio` |
| FR-20 | Replay of a real, consented test session, labelled REPLAY | Planned (step 7). Until a recorded session is added under `replays/`, `/api/status` reports replay not ready ("No recorded test session added yet") and the tile stays disabled | `/api/replay` |
| FR-21 | Printable one-page summary of the record | Planned (step 9) | `web/` |

## 6. Non-functional requirements

| ID | Requirement | Status |
|---|---|---|
| NFR-1 Latency | **Target, not a measurement:** P95 turn latency (end of her speech to first reply audio) under 2.0 s in the browser and under 2.5 s on the phone. The design budget estimates 0.7 to 1.4 s (browser) and 1.1 to 2.2 s (phone). No latency has been measured yet; the voice channel reports it per turn once step 4 is done. Text-mode grading is plain Python with no network calls | Target only; measurement from step 4 |
| NFR-2 No-keys start | App boots and shows its main screen with no keys; CI checks this from a fresh clone | Built (`.github/workflows/ci.yml`) |
| NFR-3 Fail closed | A number whose other likely reading would change the verdict is never passed: it becomes amber and is asked again | Built: the parser skips words it cannot read and flags confusion pairs; `judge()` returns amber when an alternative reading would change the status |
| NFR-4 Never blocks the loan | A comprehension gap ends in UNCLEAR plus CALLBACK, never in a refusal. Only her own report of an extra-money demand creates a HOLD for human review | Built |
| NFR-5 LLM never decides | Green, amber and red come only from `app/grade.py`. No LLM is called anywhere in the current code (the voice pipeline passes her words to `Session.hear()`, not to an LLM) | Built |
| NFR-6 Privacy | Sessions live in memory only (typing: 30-minute idle expiry, at most 200; voice: one session per open WebSocket, at most 4 at once, 5-minute timeout); no audio or transcript is written to disk; synthetic loan only; no Aadhaar asked or stored | Built |
| NFR-7 Secrets | Keys only from environment or `.env` (gitignored); never echoed by the API (tested) | Built |
| NFR-8 Tamper evidence | Editing or removing any log entry breaks the seal (tested) | Built |
| NFR-9 Cost and abuse | Phone calls off unless `CALLS_ENABLED=true`; per-number and per-IP limits | Kill switch read in `app/config.py`: Built. Limits: Planned (step 6) |

## 7. Success metrics

| Metric | Target (not a measurement) | How measured | Status |
|---|---|---|---|
| False passes on critical facts | 0. A false pass is a fact graded green when what she said does not match the loan within tolerance | Unit tests today; eval harness over phrase fixtures from step 9 | Tests built; eval Planned (step 9) |
| P95 turn latency | See NFR-1 | Per-turn `latency` events from the voice channel | Planned (step 4) |
| Unaided completion | 4 of 5 testers reach a sealed record (or a correct HOLD) with no human prompt | Logged test sessions on the synthetic loan, failures included | Planned (step 7) |
| Facts right after repair | Share of facts green at first teach-back vs after repair | From the records of test sessions | Planned (step 7) |

## 8. Prior art and what is different

We do not claim to be the first to explain loans by voice or to try teach-back.

| Who | What it does | Source |
|---|---|---|
| Sarvam | Voice agents that explain loan terms and capture consent, sold to lenders; a public "Loan Advisory Agent" cookbook on Pipecat with Saaras v4 and Bulbul v4 | https://www.sarvam.ai/voice-agents/pre-approved-loan-offers , https://docs.sarvam.ai/api-reference-docs/cookbook/example-guides/loan-advisory-agent |
| YuVerse | Markets an AI that reads the KFS aloud and captures a confirmation | https://www.yuverse.ai/resources/posts/how-voice-ai-assists-digital-lending-platforms-borrower-onboarding |
| Leegality | Vernacular KFS with a digital acknowledgement for assisted journeys | https://www.leegality.com/rbi-key-fact-statement |
| SAMJHA (public hackathon repository, Sep 2026) | Hindi KFS teach-back with LLM grading over a simulated call | https://github.com/SwapnanilAdhikary/SAMJHA |

What is different in Samjho:
- She says the loan back in her own words, and **every number is checked in deterministic code** with stated
  tolerances. No LLM decides right or wrong.
- **Only what she got wrong** is explained again, quoting her own words, then rechecked with a different question.
- A **private extra-money question** whose "yes" is addressed to the grievance officer, not the field officer.
- A **hash-chained record** of what she said and how it was judged, which anyone can re-verify.

Short form: existing tools record that she heard; Samjho checks what she understood. We found no commercial
vendor doing own-words recall with numbers checked in code and gap-only re-explanation (search done 27 Nov 2026).

## 9. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Hindi numbers misheard on phone audio (8 kHz) | Wrong grade | Parser flags confusion pairs (pachaas/pachpan, saath/saat); the grader asks again whenever the other reading would change the verdict; browser channel at 16 kHz first |
| A wrong answer graded green | Harms the borrower and the claim | Zero-false-pass gate on every merge (tests now, eval at step 9); tolerances in one file |
| Testers are not real borrowers on their own loans | Weaker evidence | Synthetic loan by design; results reported as they happened, failures included |
| Speech vendor outage or price rise | Voice stops | Typing mode always works; fixed lines can be pre-rendered; the grader and flow are our own code, so another speech provider can be swapped in (Planned) |
| Indian mobiles label calls from a US number as "International Call" | Borrower may not answer | Browser channel is primary; an Indian telephony provider after Round 2 (Planned) |
| Reads as "understanding" rather than "doing" | Brief fit | The task replaced is a form step (the acknowledgement); the flow ends in a completed record |
| Record mistaken for legal proof | Overclaim | Documented as tamper-evident session log only, not an e-signature |
