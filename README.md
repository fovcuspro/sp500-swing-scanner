# S&P 500 Swing Trading Scanner

A production-quality, fully automated daily scanner for momentum pullback setups across the S&P 500. Runs via GitHub Actions every weekday at 18:00 UK time and commits `results.json` to the repo.

---

## Strategy: Momentum Pullback

| Filter | Rule |
|---|---|
| Trend | Price > 50 MA > 200 MA |
| Pullback | 3–8% below 20-day high |
| RSI | 40–60 |
| Volume | Today > 1.3× 20-day avg |
| Candle | Close > Open (bullish) |

### Scoring (0–10 each)

| Dimension | Weight | Logic |
|---|---|---|
| Trend Strength | 40% | Distance above 50 MA + 50/200 MA spread |
| Pullback Quality | 40% | Ideal depth ~5%, ideal RSI = 50 |
| Volume Confirm | 20% | 1.3× = 0pts, 3.0× = 10pts |

---

## Project Structure

```
sp500-swing-scanner/
├── scanner.py                    # Main script
├── requirements.txt
├── results.json                  # Auto-updated daily
├── scanner.log                   # Auto-updated daily
└── .github/
    └── workflows/
        └── daily_scan.yml        # GitHub Actions automation
```

---

## Local Usage

```bash
pip install -r requirements.txt
python scanner.py
```

Results are written to `results.json`.

---

## GitHub Actions Setup

1. Push this repo to GitHub.
2. The workflow runs automatically on weekdays at 17:00 / 18:00 UTC.
3. `results.json` is committed back to the repo after each scan.
4. To trigger manually: **Actions → Daily S&P 500 Swing Scan → Run workflow**.

> No secrets or API keys required — all data is free via yfinance + Wikipedia.

---

## Output Format

```json
{
  "scan_date": "2025-05-02",
  "top_setups": [
    {
      "ticker": "NVDA",
      "score": 8.214,
      "entry_zone": { "low": 871.94, "high": 880.70 },
      "stop_loss": 842.10,
      "target": 942.50,
      "risk_reward": 1.95,
      "reasoning": "..."
    }
  ]
}
```

---

## Disclaimer

For educational and research purposes only. Not financial advice.
