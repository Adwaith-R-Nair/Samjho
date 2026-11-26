# Samjho: product requirements

"Her voice, not her thumb."

Before a microfinance borrower acknowledges her loan, Samjho explains it to her by voice in Hindi, asks her to
say it back in her own words, checks every number in code, re-explains only what she got wrong, asks privately
whether anyone demanded extra money, and only then records her spoken consent as a sealed record.

Built for the Scaler x Wispr Flow "India Runs on Voice" hackathon, Round 2 (27 to 30 Nov 2026), theme
"Livelihoods and small business", as an extension of the Round 1 idea.

All loans and people in this repository are synthetic. No real borrower data is stored.

How to read this document: anything not yet in the code is marked **Planned** with its roadmap step
(see [ROADMAP.md](ROADMAP.md)). Design details are in [HLD.md](HLD.md) and [LLD.md](LLD.md). The build history,
including measurements and bugs, is in [BUILD_LOG.md](BUILD_LOG.md).

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
1. One core flow that works end to end: consent, explain with questions, teach-back, grade, repair, recheck,
   private question, spoken consent, sealed record.
2. Every correctness decision made by deterministic code with stated tolerances.
3. Starts with `docker compose up` and no keys; features that need a key say which key is not set.
4. The same flow by typing (built), by voice in the browser (built) and on a real phone call (built and proven
   in a simulated call; the first live call is pending a Twilio account).
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
consent -> explain (4 points; she may ask up to 3 questions) -> teach-back ("explain it to your daughter")
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

Status: **Built** means present in the code and covered by passing tests. **Built, live call pending** means the
code passes its tests and a simulated end-to-end call, but has not yet run on a real phone network.
**Planned** names the roadmap step.

| ID | Requirement | Status | Where |
|---|---|---|---|
| FR-1 | Ask permission to start; "no" ends politely and still produces a record with consent `not_started` | Built | `app/flow.py` `_on_consent` |
| FR-2 | Explain the loan in 4 short lines built from the loan data, amounts spoken as Hindi words | Built | `app/lines.py` `explain`, `app/numwords.py` |
| FR-3 | Answer her questions during the explanation: first from fixed answers written by us (explain again simply, how long, cash in hand, total, instalment, "what else", fee, insurance, interest, missed payment); else, if a Gemini key is set, from Gemini fenced to the loan's own facts and numbers; else note the question for the lender. After 3 questions, move on to the teach-back | Built | `app/answer.py`, `app/lines.py` `faq`, `app/flow.py` `_on_explain` |
| FR-4 | Teach-back prompt asking her to explain the loan in her own words | Built | `app/lines.py` `teachback` |
| FR-5 | Parse Hindi, Hinglish, Devanagari, English and digit numbers and payment schedules; known confusion pairs (pachaas/pachpan, saath/saat, sattar/satrah) are flagged with the other reading; unclear words are skipped, never guessed | Built (544 test cases) | `app/hi_numbers.py` |
| FR-6 | Assign each spoken number to a fact using cue words in the same clause; a bare number answers the fact just asked; counts of weeks are not read as rupees | Built | `app/grade.py` `assign` |
| FR-7 | Grade each fact green, amber, red or grey against the loan with fixed tolerances, keeping her exact words as evidence | Built | `app/grade.py` `judge`, `app/loan.py` `TOLERANCE` |
| FR-8 | Re-explain only facts that are not green, quoting her own words, then recheck with a different question; at most 2 rounds per fact | Built | `app/flow.py` `_next`, `app/lines.py` `repair`, `RECHECK` |
| FR-9 | After 2 rounds, mark the fact UNCLEAR, open a CALLBACK case and continue; never block | Built | `app/flow.py` `_next` |
| FR-10 | Private extra-money question; "yes" opens a HOLD_REVIEW case addressed to the lender's grievance officer | Built (case in the record and panel). Routing to a lender system: Planned (after Round 2) | `app/flow.py` `_on_private` |
| FR-11 | Spoken consent, recorded as `given` or `declined` with her words | Built | `app/flow.py` `_on_final_consent` |
| FR-12 | Append-only, hash-chained session log; record with per-fact results, how many facts were right on her first answer and after Samjho, cases, questions and a SHA-256 seal; anyone can re-verify the chain, including the copy downloaded from the browser | Built | `app/record.py`, `Session.record()`, `scripts/verify_record.py` |
| FR-13 | One-screen UI: start tiles, transcript with English gloss, 5 fact chips, case notes, per-turn latency, record card, JSON download | Built | `web/` |
| FR-14 | Typing mode runs the real flow and grader with no keys | Built | `POST /api/text/start`, `POST /api/text/say` |
| FR-15 | English mode for the whole conversation | Built: English spoken lines, English number words in the parser, an English voice. Not yet tried by English-only testers | `app/lines.py`, `app/answer.py`, `app/voice.py` |
| FR-16 | `/api/status` names each missing key and never returns a key's value | Built | `app/config.py`, `app/main.py` |
| FR-17 | Browser voice: microphone over one WebSocket, Sarvam speech-to-text and text-to-speech, half duplex, latency per turn on the panel | Built | `web/voice.js`, `web/mic-worklet.js`, `app/voice.py`, `app/browser_serializer.py` |
| FR-18 | LLM help with mapping her words to facts (Gemini suggests, the grader still judges), with a rules-only fallback | Planned (step 5). Grading today is rules-only | not present |
| FR-19 | Real phone call to an Indian mobile ("we call you"), 8 kHz, barge-in, amounts read without interruption, live panel in the browser that asked for the call | Built, live call pending | `app/phone.py`, `app/voice.py`, `web/phone.js`, `/api/call`, `/ws/twilio`, `/ws/watch` |
| FR-20 | Protection for a public link: consent checkbox, Indian mobiles only, per-number, per-IP and global limits, kill switch, optional access code, one-time stream token, 5-minute calls | Built, live call pending | `app/limits.py`, `app/phone.py` |
| FR-21 | Replay of a real, consented test session, labelled REPLAY | Planned (step 7). Until a file exists under `replays/`, `/api/status` reports "No recorded test session added yet" and the tile stays disabled | `replays/` |
| FR-22 | Evaluation harness that counts false passes over a phrase set | Built: 53 synthetic phrases, 71 checks, 0 false passes; field phrases Planned (step 7) | `eval/run_eval.py`, `eval/synthetic.jsonl` |
| FR-23 | Printable one-page summary of the record | Planned (step 9) | not present |

## 6. Non-functional requirements

| ID | Requirement | Status |
|---|---|---|
| NFR-1 Latency | **Target, not a measurement:** P95 turn latency (end of her speech to first reply audio) under 2.0 s in the browser and under 2.5 s on the phone. **Measured so far** (single runs, not a P95; BUILD_LOG commits 7, 9 and 10): browser with synthetic speech about 1.05 s for yes/no turns and 1.3 to 1.37 s for number turns (0.6 or 0.9 s of that is the deliberate wait for her to finish); first real-mic test 1.07 to 1.58 s; simulated phone call 1.03 to 1.36 s. Questions answered by Gemini can take up to 3 s | Target set; P95 not yet computed |
| NFR-2 No-keys start | App boots and shows its main screen with no keys; CI checks this from a fresh clone | Built (`.github/workflows/ci.yml`) |
| NFR-3 Fail closed | A number whose other likely reading would change the verdict is never passed: it becomes amber and is asked again | Built (`app/grade.py` `judge`) |
| NFR-4 Never blocks the loan | A comprehension gap ends in UNCLEAR plus CALLBACK, never in a refusal. Only her own report of an extra-money demand creates a HOLD for human review | Built |
| NFR-5 LLM never decides | Green, amber and red come only from `app/grade.py`. Gemini may explain, never judge: it is used only to answer her questions, and every number in its answer must be one of the loan's own numbers or the answer is discarded | Built |
| NFR-6 Privacy | Sessions live in memory only; no audio, transcript or phone number is written to disk; phone numbers are kept only as salted hashes and logged masked; synthetic loan only; no Aadhaar asked or stored. Data sent to providers: audio to Sarvam (voice), call audio through Twilio (phone), and, when a Gemini key is set, the text of a question not covered by the fixed answers plus the loan's facts to Google | Built |
| NFR-7 Secrets | Keys only from environment or `.env` (gitignored); never echoed by the API (tested) | Built |
| NFR-8 Tamper evidence | Editing or removing any log entry breaks the seal (tested); a browser-written copy still verifies (tested) | Built |
| NFR-9 Cost and abuse | Phone calls off unless `CALLS_ENABLED=true` (read on every request); call limits as in FR-20; at most 4 live browser voice sessions | Built |
| NFR-10 Responsiveness | A question that waits on Gemini never blocks audio: `Session.hear()` runs in a worker thread and Gemini has a 3 s cut-off | Built |

## 7. Success metrics

| Metric | Target (not a measurement) | Result so far | Status |
|---|---|---|---|
| False passes on critical facts (a fact graded green when what she said does not match the loan within tolerance) | 0 | 0 on 53 synthetic phrases (71 checks, 71 correct); a test fails the build on any false pass | Built for synthetic phrases; field phrases Planned (step 7) |
| P95 turn latency | See NFR-1 | Single-run measurements in NFR-1 | P95 Planned (step 9) |
| Unaided completion | 4 of 5 testers reach a sealed record (or a correct HOLD) with no human prompt | None yet | Planned (step 7) |
| Facts right on first answer vs after Samjho | Report per session | Recorded in every record (`right_first_answer`, `right_after_samjho`); a typed test run went 2 of 5, then 5 of 5 | Built; real-user numbers Planned (step 7) |

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
Samjho uses Sarvam's speech models; it does not compete with them on speech.

## 9. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Hindi numbers misheard on phone audio (8 kHz) | Wrong grade | The parser flags confusion pairs; the grader asks again whenever the other reading would change the verdict. Phone tested only in simulation so far |
| A wrong answer graded green | Harms the borrower and the claim | Zero-false-pass gate in the eval test; tolerances in one file |
| Eval set written by us | Says little about real speech | Field phrases from consented sessions go in a separate file with their source marked (step 7) |
| Testers are not real borrowers on their own loans | Weaker evidence | Synthetic loan by design; results reported as they happened, failures included |
| Gemini gives a wrong explanation | Misleads her | Fixed answers first; Gemini sees only the loan's facts, any number not from the loan discards the answer, "I do not know" answers are dropped, 3 s cut-off; it never judges |
| Speech vendor outage or price rise | Voice stops | Typing mode always works; the flow and grader are our own code, so another speech provider can be swapped in (Planned) |
| Indian mobiles label calls from a US number as "International Call" | Borrower may not answer | The UI says so before the call; browser channel is primary; an Indian telephony provider after Round 2 (Planned) |
| Browser voice cannot be interrupted | Slower conversation | Chosen trade-off against echo without browser echo cancellation; barge-in on the phone |
| Record mistaken for legal proof | Overclaim | Documented as a tamper-evident session log only, not an e-signature |
