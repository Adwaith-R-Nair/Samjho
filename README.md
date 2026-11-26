# Samjho: her voice, not her thumb

Before a microfinance borrower acknowledges her loan, Samjho explains it to her by voice in Hindi, asks her to
say it back in her own words, checks every number in code, re-explains only what she got wrong, and only then
records her spoken consent.

Status: in progress for the Scaler x Wispr Flow "India Runs on Voice" hackathon, Round 2 (27 to 30 Nov 2026).
This README only states what the code in this repository does; it grows as features land.

## Run it

```
docker compose up --build
```

Then open http://localhost:7860. No keys are needed to start: the main screen loads, and features that need a
key say which key is not set. To enable voice, copy `.env.example` to `.env` and add your keys.

Without Docker:

```
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt   # on macOS or Linux: .venv/bin/pip
.venv/Scripts/python -m uvicorn app.main:app --port 7860
.venv/Scripts/python -m pytest
```

## Data

All loans and people in this repository are synthetic. No real borrower data is stored.

## License

MIT
