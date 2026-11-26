# Demo replays

Each folder here is one recorded Samjho session, saved so that anyone (for example a judge without a
microphone) can watch a real person's session: the "Replay a real test session" tile plays the audio and
shows the transcript, the fact checks and the sealed record at the moments they happened.

## Consent

A session is recorded only when the box "Save this session as a demo replay. The person speaking agrees to
be recorded and shown." is ticked before it starts. Tick it only when the person who will speak has agreed,
in person, to be recorded and to have the recording shown publicly. While recording, the screen says
"Recording for a demo replay". The manifest keeps the exact consent text and the session's spoken consent
answer. To withdraw consent, delete the folder.

Only real, consented sessions belong here. Synthetic test sessions (made with generated voices by
`scripts/voice_smoke.py --record`) are written under `scratch/` instead.

## What is stored

    <UTC date>_<session id>/
      manifest.json   session id, language, channel (browser or phone), start time, duration, consent text,
                      spoken consent, facts right on the first answer and after Samjho, record seal (SHA-256)
      events.jsonl    every screen event, one per line, with "t" = seconds since the session started
      audio.wav       the conversation, the person and Samjho mixed to mono (16 kHz browser, 8 kHz phone)

The loan is the synthetic sample loan. Anything in the events that looks like a phone number is masked to
its last four digits before it is written; no keys or other secrets are part of any event. The audio is the
person's real voice, which is why consent is required.
