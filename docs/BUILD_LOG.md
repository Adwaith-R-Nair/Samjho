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

### In progress
- Browser voice channel on Pipecat with Sarvam speech-to-text and text-to-speech, built in parallel by a subagent.
