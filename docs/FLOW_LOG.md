# Built by voice: Wispr Flow log

Adwaith builds Samjho by speaking. He dictates every instruction to Claude Code with Wispr Flow (Windows), in a
mix of English, Hindi and Malayalam; Claude Code writes and runs the code. This log records what was dictated in
each session and what came out of it. It is the source for the Round 2 "how we used Wispr Flow" note.

| Date (IST) | Dictated (summary) | Result in the repo |
|---|---|---|
| 27 Nov | Read the Round 2 brief and rules on the dashboard; compare extending Round 1 against new ideas with ChatGPT, Gemini and Claude; pick the strongest | Decision: extend Samjho as "her voice, not her thumb" |
| 27 to 28 Nov | Set up Twilio, Sarvam, Gemini and hosting; start the build phase by phase in the Praman commit style | First commit: app starts with no keys, CI boots it from a fresh clone |
| 28 Nov | Tested "Talk in the browser" with his own voice and dictated what went wrong: every question got "the lender will answer" | Three-layer question answering (fixed answers, fenced Gemini, move on after three questions) |
| 28 Nov, evening | Was guided step by step through the Twilio setup (upgrade, compliance profile, a US number, India in Voice Geo Permissions, a Cloudflare tunnel); took two real calls on his own mobile playing a borrower in Hindi, then dictated what went wrong on each | Two real calls, the second a full session to the sealed record (median reply 1.34 s over 22 turns); fixes for split amounts, the answer to the question asked, a callback announced twice, a stale latency reading, the 5-minute limit, a cued answer losing to a guess, and a missing fixed answer |
