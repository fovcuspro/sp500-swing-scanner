# SP500 Swing Scanner

## What This Is
A daily swing trading scanner for the S&P 500.
Runs via GitHub Actions every weekday at 18:00 UK time.
Outputs the top 10 momentum pullback setups to results.json.

## Key Files
- `scanner.py` — the entire scanner (data fetch, indicators, scoring, output)
- `requirements.txt` — Python dependencies
- `results.json` — auto-generated daily output (do not hardcode this)
- `.github/workflows/daily_scan.yml` — GitHub Actions automation

## How to Run
pip install -r requirements.txt
python scanner.py

## Rules You Must Follow
- Never hardcode ticker symbols
- All data must be free (yfinance + Wikipedia only)
- Always handle missing or incomplete data gracefully
- Keep scanner.py as a single modular file
- Never break the results.json schema
