# Build log

How Samjho was built during Round 2 of the Scaler x Wispr Flow "India Runs on Voice" hackathon (27 to 30 Nov
2026), in order: what was decided, what was built, what broke, and how each problem was handled. Updated in the
same commit as each feature or fix. Times are IST. Everything here happened; nothing is reconstructed or staged.

## Ground rules for the build
- All code is written during the hackathon window. The Round 1 idea and research existed before 27 Nov; no code did.
- Built by voice: Adwaith dictates instructions to Claude Code with Wispr Flow (see FLOW_LOG.md).
- Synthetic loans and people only. Real test sessions only with spoken consent; results reported as they happened.
- Every number Samjho judges is checked in code. An LLM may help find fields in speech; it never decides right or wrong.

## 27 Nov: reading the brief and choosing what to build
**Rules captured.** The Round 2 dashboard did not give one problem statement. It asked for "something people in
India do today by typing, tapping or filling forms", made to work by voice, under one of five themes, extending
the Round 1 idea or starting a new one. Deliverables: public GitHub that starts with docker compose and no keys,
code written in the window (300+ lines), a 3-minute YouTube demo, a pitch deck PDF read as text, and an optional
live link tested by the organisers until 2 Dec.

**Blocker: is a loan explainer a "doing" task?** Three independent first reviews (a Claude strategist, ChatGPT,
Gemini) split. Two preferred new ideas (a garage job card by voice; a supplier order by voice) because Samjho
could read as "understanding" rather than doing, and its user tests would be role-play.

**How it was resolved.** A head-to-head between "Samjho, reframed" and "Bolo Job Card" with an advocate and a
prosecutor agent for each, plus fresh and continued ChatGPT and Gemini chats, then a no-context Claude panel and
a full-context adjudicator. The first model votes went 3 to 1 for the job card. Then the research agents found
facts the models had not seen:
- Against the job card: a product already sells spoken job details into garage invoices in 10 Indian languages;
  WhatsApp approval links for extra work already exist; Hindi is the mother tongue of only about 6% of Bengaluru;
  calls from a US number now show as "International Call" on Indian phones.
- For Samjho: an RBI Deputy Governor said on 13 Nov 2026 that "pseudo consent is a mere compliance formality";
  a March 2026 Sa-Dhan survey of 1,264 borrowers found 91% call pricing "very clear" while 72% say they paid no
  processing fee, though most are charged one; the acknowledgement today is literally a form step (thumbprint,
  OTP or an "I agree" tap).
With those facts every reviewer, in every chat, picked Samjho. Decision: extend Round 1 as "Her voice, not her
thumb", built in Hindi with an English mode for judges.

**Honest limits recorded at decision time.** Vendors already read loan terms aloud and record a "yes" (including
our speech provider's own loan agents), and a small public hackathon project already tries Hindi teach-back with
an LLM grader. Samjho never claims to be first at teach-back. What it does differently: she says the loan back in
her own words, every number is checked in code, only what she got wrong is explained again with her own figures,
and an extra-money question goes privately to the grievance officer.

## 27 to 28 Nov: accounts and hosting
- Sarvam (speech) and Gemini keys created and tested: a Hindi line was synthesised and the Flash models listed.
- Twilio: a paid account is needed because trial accounts cannot call India. Upgrade waits on an international-
  enabled card (UPI is not accepted). Phone calls are scheduled after browser voice, so this does not block work.
- Hosting blocker: Azure for Students would not verify the college account (sign-in found no account; creating
  one rejected a college address; the verification link returned "The client does not have access rights to the
  content"). Switched to a Railway trial ($5 one-time, no card) for the live link. A laptop Cloudflare tunnel is
  used for development only, because a laptop cannot be trusted to stay up through judging.

## 28 Nov: the build
### Commit 1: the app starts with no keys
FastAPI serves one screen with the four ways to start (browser voice, real call, typing, replay) and the panel of
five facts. `/api/status` names the missing key for each feature and never returns a key's value. docker compose
starts it with no `.env`; a CI job does exactly that from a fresh clone and checks the screen and the "not set"
message. Three tests.

### Commit 2: docs, build log and Flow log
This file and FLOW_LOG.md.

### Commit 3: reading numbers from Hindi, Hinglish and English speech
`app/hi_numbers.py`, built by a parallel agent against a fixed interface, with 544 table-driven tests: every
number 0 to 99 in both scripts with spelling variants, compositions ("adtaalis hazaar chaar sau das" is 48,410),
dedh, dhai, saade, sava and paune, English words, digits in any grouping, and separation of adjacent numbers.
Words that phone audio often swaps (pachaas and pachpan, sattar and satrah, fifteen and fifty) come back flagged
with the other reading. Known limits are listed in the module docstring (for example "aur" never joins numbers).

### Commit 4: the conversation, the five checks and the sealed record, in typing mode
`app/flow.py` runs consent, explanation with questions, teach-back, ask-repair-recheck for each fact that is not
right (two rounds, then a human callback, never a block), the private extra-money question and spoken consent.
`app/grade.py` assigns each number to a fact from the words around it and judges it in code against
`app/loan.py`. `app/record.py` chains every entry with SHA-256; the seal is the last hash. The UI shows the
conversation with English subtitles, turns each fact chip green, amber or red with her own words, and offers the
sealed record as a download.

Bugs found and fixed before this commit (all now covered by tests):
1. **Unclear words turned right answers amber.** Once the parser flagged "pachaas" (could be pachpan), the grader
   made every flagged number amber, so a correct teach-back never went fully green and the classic miss of
   Rs 50,000 showed amber, not red. Fix: a flagged word only matters if the other reading would change the
   verdict; 50,000 and 55,000 are both wrong, so it is red.
2. **Numbers matched to the wrong fact.** In "har hafte 1095 dena hai, kul 56,940", the word "kul" (total) was
   the nearest cue to 1095, so the instalment was judged as a total. Fix: cue words only count inside the same
   clause (split on commas, "aur", "phir", danda), and "har hafte", "dena" and "bharne" now mark an instalment.
3. **A scripted edit wrote a backspace byte instead of the regex `\b`.** Clause splitting on "aur" silently did
   nothing while tests still passed. Found by printing the compiled pattern. Fix, plus a new test that fails if
   any source file contains a control character (and one for em dashes).
4. **The question "bima kyun lagta hai?" got no answer.** The pattern was `bee?ma` and missed "bima". Fixed.
5. **A downloaded record would not verify.** Amounts were stored as floats (48410.0); a browser re-writing the
   JSON prints 48410, which changes the hash. Found by the docs agent while writing the LLD. Fix: whole amounts are
   stored as integers; a test re-serialises the record and checks the seal.
6. **The replay tile was clickable with nothing behind it.** Replay now reports "not ready" until a consented
   real session is added under `replays/`.

### Commit 5: design docs, a browser run-through, and a before/after score
PRD, roadmap, high-level and low-level design written by a docs agent from the code, every claim checked against
it; anything not built is marked Planned. The agent also found bugs 5 and 6 above.

A full typed session in Chrome (Hindi mode) went: classic miss caught red, re-explained with her words, four
facts repaired, extra-money report held for the grievance officer, consent sealed. It surfaced three UI bugs, all
fixed here: the answer box showed before a session started (a CSS `display` rule overrode `hidden`); the amber
label said "explained again" before anything was explained; and a repair quoted our label "monthly" instead of
her words "har mahine". The schedule is now quoted in her words (`_freq_quote`, tested on "mahine nahi, har hafte").

New: each record counts what she got right on her first answer and what she got right after Samjho (in that run:
2 of 5, then 5 of 5). This is the per-session result the video and deck will report from real test sessions.

### Commit 6: an evaluation harness that counts false passes
`eval/run_eval.py` grades a fixed set of answers and reports accuracy and, above all, false passes (a fact
marked understood when it was not). `eval/synthetic.jsonl` holds 53 answers we wrote (teach-backs and direct
answers in Hindi, Devanagari, Hinglish, English and digits, right and wrong). First run: 69 of 71 checks right,
0 false passes. Both misses were our expectations, not the grader: for the total, "pachaas hazaar" could be
"pachpan hazaar" (55,000, which is only close), so the two readings give different verdicts and Samjho correctly
asks again instead of marking it wrong. After correcting those two: 71 of 71. A test fails the build on any false
pass. Honest limit: a set we wrote ourselves says little about real speech; phrases heard in consented field
sessions go into a separate `field` file with their source marked.

### Commit 7: talking to Samjho in the browser
"Talk in the browser" runs the same Session by voice. The mic is captured with an AudioWorklet at 16 kHz and
sent over one WebSocket (`/ws/browser`); Pipecat 1.17 runs Sarvam saaras:v4 speech-to-text in codemix mode,
Silero voice activity detection, a turn end that waits 0.9 s when a number is expected and 0.6 s for yes or no,
then our Brain processor (no LLM: it calls `Session.hear()`), then Sarvam bulbul:v4-flash speech in a Hindi or
English (India) female voice. Every event goes to the UI as JSON on the same socket. Built by a parallel agent
that checked each Pipecat class against the installed source, because names changed in 1.17.

Measured, not estimated: a live script (`scripts/voice_smoke.py`) plays Sarvam-made Hindi answers into a local
server over a real WebSocket. The wrong teach-back "50,000 हाथ में आएंगे" came back red. End of speech to first
reply audio was about 1.05 s for yes or no turns and 1.3 to 1.37 s for number turns, of which 0.6 or 0.9 s is the
deliberate wait for her to finish.

Problems met and how they were handled:
1. **Echo.** A plain WebSocket gets no browser echo cancellation, so laptop speakers would feed Samjho's voice back
   in as the borrower. Chosen trade-off: half duplex. The browser sends silence while playing, the server blanks
   mic audio while the bot speaks plus 0.25 s, and the user is muted in that window. Cost: she cannot interrupt in
   the browser (planned for the phone, where the handset cancels echo).
2. **The user was unmuted between lines of one reply.** Each line was a separate speech request, so the bot
   "stopped speaking" between them and a stray word could cut the explanation. Fix: one utterance per reply. Cost:
   the subtitles of a reply appear together.
3. **A very short "हाँ" (0.28 s) did not trigger voice detection** in the synthetic test. To verify on a real mic.
4. **Speech-to-text writes numbers as digits ("50,000")**; the parser already handled that.
5. Notices such as "SARVAM_API_KEY not set" and "too many live sessions" showed only their code in the panel.
   Fixed to show the explanation.

### Commit 8: a README that only claims what runs, and a record checker
The README was rewritten for judges: what works today with the file that does it, what is planned, the numbers
we measured (0 false passes on 53 synthetic answers; about 1.05 s and 1.3 s reply times in the browser), how to
run it, and honest limits. `scripts/verify_record.py` checks a downloaded record against its seal; tried on a
real record (VALID) and on the same record with one timestamp changed by one second (TAMPERED).

### Commit 9: answering her real questions (from the first real-mic test)
Adwaith tried "Talk in the browser" with his own voice. Speech recognition and the voice worked (reply times on
screen: 1.07, 1.33, 1.58 and 1.34 s), but every question he asked got "the lender will answer this":
"एक और बार ... थोड़े और आसान भाषा में?" (explain again, simpler), "ये मुझे कब तक चुकाना होगा?" (until when?) and
"किस्त के अलावा ... कुछ कहोगी?" (what else besides the instalment?). Only four fixed questions existed (insurance,
fee, interest, missed payment), so a real borrower would have been stonewalled.

Fix, in `app/answer.py`, three layers:
1. Fixed answers for what people actually ask: explain again slowly and simply, how long, cash in hand, total,
   instalment, "what else" (three things to remember, including that nobody may ask her for extra money), plus the
   original four. His three questions are now permanent tests.
2. For anything else, Gemini, fenced: it sees only the loan's facts, and every number in its answer must be one of
   the loan's own numbers, or the answer is thrown away (tested with "Rs 200 penalty" and "4,500 a month"). It
   explains; it never judges her understanding. Questions the facts cannot answer (early repayment, first due date)
   correctly fall through to "noted for the lender".
3. After three questions Samjho says "good questions, let us move on" and goes to the teach-back, so a session
   cannot stall.

Problems met on the way:
- `gemini-2.5-flash-lite` returned 404: retired for new accounts. Switched to `gemini-3.5-flash-lite`.
- Gemini rejects request deadlines under 10 s, so the 2.5 s limit made every call fail. The cut-off is now enforced
  on our side with a thread future (3 s); a slower answer is dropped.
- Answers took 2 to 3 s. Two fixes measured live: `thinking_level="minimal"` (about 0.7 s on a short prompt) and
  reusing one client instead of a new connection per question (about 1 s once warm). The connection is opened in
  the background when a session starts. A cold first call can still take 3 s.
- Gemini once answered "मुझे नहीं पता" (I do not know) instead of an empty reply; such answers are now dropped.
- "32.8" was read as "बत्तीस.आठ"; decimals are now spoken as "बत्तीस दशमलव आठ".
- A scripted edit again broke a string (a literal newline inside a quote); found by the import error and fixed by
  hand. Scripted multi-line edits are now done with the editor instead.
- Tests never call Gemini, even with a key in `.env` (`tests/conftest.py`).

### Commit 10: the real phone call, built and proven in a simulated call
`app/phone.py`, `app/limits.py`, `web/phone.js`: "Get a real phone call" places a Twilio call to an Indian mobile
and runs the same Session on it. One pipeline builder now serves both channels (`app/voice.py`): the phone runs at
8 kHz end to end with Twilio's serializer, and because the handset cancels echo, the caller can interrupt; two or
more words are needed while Samjho speaks, so "haan" or "hmm" do not cut it off. While a reply with amounts plays,
the caller is muted so the numbers are heard in full. The browser that asked for the call watches it live over
`/ws/watch`.

Protection for a public link (`app/limits.py`): consent checkbox, Indian mobiles only, per number 1 call per 30
minutes and 3 a day (stored only as a salted hash), 3 per IP per hour, 2 at once and 40 a day overall, a
`CALLS_ENABLED` switch read on every request, an optional `JUDGE_TOKEN`, and a one-time token on the Twilio stream
so nobody else can attach to a call. Calls end after 5 minutes. Numbers appear in logs only masked.

Proof so far: no Twilio account yet, so `scripts/call_smoke.py --simulate` runs a whole call locally with live
Sarvam speech through the real `/api/call`, TwiML, `/ws/twilio` and `/ws/watch`, faking only Twilio's dialler and
the handset (8 kHz, 20 ms frames, real time). It passed: barge-in, muting during amounts, "50,000 हाथ में" caught
red, the watch panel saw every event; replies in 1.03, 1.36 and 1.34 s. 36 new tests.

Problems met:
1. Pipecat's Twilio serializer forwards UI messages to Twilio. Events now go to an in-process watch hub instead.
2. Speech muted while amounts were read sat in the speech-to-text buffer and leaked into the next turn's
   transcript. The mute flag now also silences the audio going into speech-to-text.
3. Questions that wait on Gemini could block the audio loop for up to 3 s. `Session.hear()` now runs in a thread.
4. The 4-minute call limit was shorter than a full session with repairs; raised to 5 minutes.
Not yet proven, and planned for the first real call: hang-up via Twilio's API, real network audio, the
"International Call" label, and how fast barge-in feels on a real line (about 1 s in the simulation).

### Commit 12: consented recordings that judges can replay
A tester can tick "Save this session as a demo replay. The person speaking agrees to be recorded and shown." (off by
default). The session is then saved under `replays/<date>_<id>/`: every UI event with its time, one mixed WAV of
both voices (Pipecat's AudioBufferProcessor placed after the output so it hears both), and a manifest with the
before/after score and the seal. "Replay a real test session" plays the audio and fires the events at their
recorded times, so the transcript, fact chips and record appear in sync, under a "REPLAY of a real consented
session, not live" badge. Phone numbers are masked in saved events; ids and paths are checked so nothing outside
`replays/` can be served. The tile stays off until a real replay exists; synthetic test replays go to `scratch/`.

Added after review: Samjho now says aloud at the start of a recorded session that it is being recorded, with her
permission, and that she can stop it (`lines.intro(recording=True)`), and the session log notes it.

Observed in the live test run: one turn took 4.9 s instead of about 1.3 s; the server log showed Sarvam
speech-to-text returning the transcript about 4.5 s after she stopped. Not our code, not Gemini. It will show in the
latency strip if it happens; to watch in real sessions.

Known limits: a 5-minute session is about 10 MB of WAV in git; the audio runs on for a few seconds after the last
event, until the socket closes.

### Commit 13: the first real phone call, and the four bugs it found
28 Nov, about 10:52 pm. Twilio account upgraded, Individual compliance profile approved the same day, a US local
number bought (Voice only; A2P SMS registration and SHAKEN/STIR skipped, both are for US messaging or US callees).
India was already enabled in Voice Geo Permissions. The app ran on the laptop behind a Cloudflare quick tunnel
(`cloudflared` 2026.11.2). `scripts/call_smoke.py` rang the builder's own mobile; he played a borrower in Hindi.

What worked on a real line: the call connected, Samjho was heard clearly, Sarvam transcribed phone audio well
(Hinglish like "52 weeks tak chalega" and "एक बार और बता सकते हो" came through), questions got answers, barge-in
and muting behaved, and the lender-side panel followed the call live.

Measured: reply time median **1.35 s** over 11 turns (1.32 s to 1.48 s). Sarvam speech-to-text first byte 0.28 s to
0.52 s, text-to-speech first byte 0.23 s to 0.52 s.

What broke, and the fix for each (tests use the exact transcripts):
1. "एक हज़ार पचानवे" came back from speech-to-text as **"1000. 95"**: a pause cut one amount in two, so 1,095
   was read as 1,000 and 95, judged "close, not exact", and the instalment went to a callback though he had it
   right. `grade._join_split_amounts` rejoins a round thousand (or hundred) followed, after only a full stop or a
   space, by a smaller number. A comma still separates ("1000, 95" stays two numbers).
2. Asked for the total, he said **"56,000 किस्त"**. The word "kisht" pulled the number to the instalment, so
   the total stayed unanswered. Now a single number answering a question goes to the fact asked about when it is
   closer to that fact's value than to the one the loose word points at.
3. That misassigned number re-graded the instalment, which was already handed to a callback, and Samjho
   announced the **same callback twice**. A fact closed for a callback is no longer re-graded in the check step.
4. The first reply showed **16.4 s**. The server log shows the reply started 0.28 s after his turn was handed
   over; Pipecat's latency clock had started at a sound he made during the greeting. Readings that start before
   the turn they time are now dropped (`voice.plausible_latency`) instead of shown.
5. The call hit the **5-minute limit** while still checking facts (he asked for the explanation twice, about 25 s
   each), so it never reached the private question and consent. Call and session limits raised to 8 minutes
   (under Rs 50 of Twilio time at India rates).

Not yet proven: hang-up through Twilio's API mid-session, and a full session to the sealed record on a real line.

### Commit 14: the second real call reaches the sealed record
28 Nov, about 11:06 pm, same setup, with commit 13's fixes. The whole flow ran on a real line in about 4 minutes:
consent, explanation, two questions, teach-back, repair of the facts he got wrong, all five facts green, the
private question (he answered "haan", so a HOLD_REVIEW case went to the grievance officer), final consent, and the
sealed record. Reply time over 11 turns: 1.03 s to 1.45 s, plus one question at 2.54 s. No stale 16 s reading.

Commit 13's fixes held on new audio: "1052 रुपये। 95 रुपये।" (speech to text's version of "ek hazaar pachaanve")
graded within tolerance, and "56,940." answered the total.

What broke, and the fix for each (tests use the exact transcripts):
1. His teach-back was "50,000 रुपये में से। 1590. कम करने के बाद। बाकी 48410 रुपये हाथ में आएंगे". The 50,000 (the loan
   size) had no cue word, so it was placed by size as cash in hand and marked red; the 48,410 that came with
   "haath mein" was then ignored because the fact was already taken. A guess by size now gives way to a later
   number that has her own cue word. A cued wrong answer ("pachaas hazaar haath mein") still counts and stays red.
2. "52 हफ्तों तक कितने रुपये जमा करना है?" went to Gemini (2.54 s) though the instalment has a fixed answer. "kitne
   rupaye jama / bharne / dene" and "कितने रुपये जमा" now get the fixed answer.

Across both calls: median 1.34 s over 22 turns (about 1.05 s after yes or no, about 1.35 s after a number).

### Commit 15: the seal now covers her score, and "ना" means no
Found while writing the demo video: a judge-style review ran every draft script's borrower lines through the real
`Session` and every planned tamper through `scripts/verify_record.py`.
1. The seal covered only the log entries. The summary on top of a record (her first-answer score, the score after
   Samjho, each fact, consent) was not checked, so changing "right_first_answer" from 2 to 5 still printed VALID. For a
   product whose claim is a tamper-evident record, that was the most serious gap found so far. The session now appends a
   `summary` entry to the chain before it ends, and `record.verify_record()` checks the chain and that the summary on
   top equals the sealed copy. Changing the score, a fact, the extra-money answer or the consent now prints TAMPERED.
2. "ना" (and "ना।") was not read as no: `\b` does not work after a Devanagari vowel sign. In the review run a
   private-question "ना" got "Sorry, I did not catch that". It is now matched as a word of its own, with the danda
   counted as punctuation; "नाम" is still not a no.
Also learned: the teach-back prompt does not ask about deductions, so a correct answer to the follow-up question counts
as right first time. A script that wants "2 of 5" on the card must answer that question wrong first. Writing a heredoc
edit turned `\b` into a backspace character again; the hygiene test caught it and the lines were rewritten safely.

### Commit 16: natural schedule answers, and an honest goodbye
From rehearsing the demo video's exact lines through the app:
1. Samjho re-checks the schedule with "If you pay this Monday, when is the next instalment due?". The most natural
   answer, "agle somvaar" (next Monday), was not read as a schedule, so a borrower who understood would be
   re-explained and could end in a callback. When Samjho has just asked about the schedule, "next Monday", "saat din
   baad" (after seven days) and "ek hafte baad" now mean weekly, and "next month" means monthly (and is caught as
   wrong). Without that question, a day on its own is not read as a schedule.
2. The goodbye always said "Your questions will reach the lender", even when she had none. It now says so only when
   questions were passed to the lender.

### Commit 18: a new face, phase 1: the thumbprint becomes a voice
The interface is being rebuilt in phases. Three static directions (a loan paper, voice as an editorial transcript, an
Indian Railways station board) were built as mockups and rejected by the builder as "okayish". Two immersive ones
followed; he chose "the thumbprint becomes a voice" with one effect from the other ("spoken into being": numbers
assembling out of the voice). Design work followed the Impeccable design skill (pbakaus/impeccable).

Phase 1 replaces the landing: an ink-drop intro; a WebGL2 shader of a living fingerprint (`web/js/voicefield.js`,
raw WebGL, no library); a four-chamber scroll story (the thumbprint, "pseudo consent" with Rs 50,000 counting down to
Rs 48,410, "she says it back" with a voice note in an AI stand-in voice, and the ridges unwinding into sound waves);
then the real start options with their real reasons from /api/status. Smooth scrolling and choreography use GSAP
3.13.0 (ScrollTrigger, SplitText) and Lenis 1.3.11, pinned on jsDelivr. The session view keeps its old layout with
the new colours until phase 2. A typed session still runs to a sealed record at 1440 px and 360 px.

### Commit 19: a new face, phase 2: the live session inside the print
The session view is rebuilt on the same events (`say`, `heard`, `fact`, `case`, `record`, `latency`, `state`). Turns are
voice-note bubbles (Samjho left, her right) with the real reply time per turn. The five facts are five numbered rings of
the fingerprint, each with a leader line to its row; a row keeps her first verdict beside the current one ("explained
again 2x"). The other design's signature effect is in: when code marks an amount, the figure she said (her
Rs 50,000, or her words "har mahine") assembles out of grains inside the print in red, amber or green, then flies into
its ring and row (`web/js/livefx.js`, one 2D canvas that runs only while a figure is on screen; 2,600 grains on a laptop,
1,100 on a phone; off under reduced motion). The seal closes with the real hash around the ring. Checked by hand with a
typed session: the wrong teach-back formed Rs 50,000 in red and "har mahine" from her words, and the rings lit to
match. Also fixed from review: animated headings keep their accessible name, and the "keys not set" note appears only
when a key is actually missing.

### Commit 20: a new face, phase 3: her real voice moves the print
Two AnalyserNodes now live in the browser voice's existing AudioContext: one gets a second connection from every buffer
of Samjho's speech (the gapless queue, `clearPlayback` and the echo gate are untouched), the other taps the mic before
the worklet through a gate that closes whenever the mic is muted. Both end in a zero-gain sink, so nothing extra is
heard. The print, the voice-note waveforms (`web/js/voicenotes.js`) and the grain energy of the number effect follow the
real audio. Replays route their recording through the same analysers, and tapping a voice note seeks the replay there.
Phone mode drives the print from the call's events. Measured on a real browser-voice session with a fake microphone:
Samjho's level peaked at 0.69 to 0.81 while he spoke; reply time median 1.06 s and 1.09 s against 1.05 s before the
change, so the visuals cost the voice nothing measurable. Not yet tried: a real person's microphone through this build.

### In progress
- Hosted live link on Railway.
- Consented real test sessions (the replay feature is ready for them).
