# SP500 Swing Scanner — User Guide

## What it does

Scans all S&P 500 stocks every weekday at 13:00 UTC. Finds stocks in strong uptrends pulling back to a support level — the "momentum pullback" setup. Sends an iPhone notification and updates the dashboard automatically.

---

## Dashboard tabs

| Tab | What it shows |
|-----|--------------|
| **Scanner** | Today's top setups ranked by score. Tap any card to see entry zone, stops, sizing, and reasoning. |
| **Portfolio** | Your open positions with live P&L. Tap + to add a position. |
| **Performance** | Win rate, expectancy, and breakdowns by score range, RSI, regime, and sector. |
| **Log** | Every signal ever generated, with scores and outcome once resolved. |
| **Lab** | Strategy variant comparison (requires `backtest.py compare` to run first). |

---

## Understanding a setup card

| Field | Meaning |
|-------|---------|
| **Score** | 0–10 weighted score (trend 40%, pullback 40%, volume 20%) |
| **Entry zone** | ±0.5% of current close — a natural buy range |
| **Swing stop** | Lowest low of last 10 bars |
| **ATR stop** | Price minus 2.5× ATR(14) |
| **Stop loss** | Whichever is lower (wider) — gives more room |
| **Target** | Prior 20-day high — natural breakout point |
| **R:R** | Risk-to-reward ratio. Aim for ≥ 2× |
| **Suggested shares** | Based on 1% portfolio risk at current stop distance |

---

## Market regime

The scanner checks the SPY ETF daily to classify the market:

| Regime | Condition | Position sizing |
|--------|-----------|----------------|
| **Bull** | SPY above 200 MA + positive 63-day return | 100% of suggested size |
| **Neutral** | Neither bull nor bear | 75% of suggested size |
| **Bear** | SPY below 200 MA + 63-day return worse than –5% | 50% of suggested size |

The regime banner appears at the top of the Scanner tab.

---

## Exit plan

Each setup includes a two-tier exit:
- **T1** — sell half at the midpoint between entry and target (locks in profit)
- **T2** — sell the second half at the full target price

Hold period is 2–4 weeks. Trades are automatically marked expired after 28 days.

---

## Adding positions to Portfolio

1. Tap the **Portfolio** tab
2. Tap **+**
3. Enter ticker, shares, entry price (and optionally stop/target)
4. Tap **Add Position**
5. Tap the **▶** play button to fetch live prices

---

## Running a scan manually

Tap the **▶** button in the top-right corner. The scan takes about 2 minutes. You'll get a push notification when it's done.

---

## Notifications

Push notifications arrive via the **ntfy app** on channel `swing13cat`. Each notification includes:
- Number of setups found
- Top 5 tickers
- Market regime
- New tickers since yesterday
- Tickers that dropped off

---

## Lab tab (backtest compare)

The Lab tab shows how the strategy performs across 4 variants. To populate it:

```bash
python backtest.py compare
git add backtest_compare.json
git commit -m "chore: backtest compare"
git push
```

This is based on your actual trade history — the more signals that have been logged and resolved, the more reliable the comparison.

---

## Files produced each scan

| File | Contents |
|------|----------|
| `results.json` | Today's top setups |
| `prev_results.json` | Yesterday's results (for diff notifications) |
| `trade_history.json` | All signals ever logged with outcomes |
| `analytics.json` | Performance statistics |
| `health.json` | Scanner health status |
| `sectors.json` | S&P 500 sector mapping |

---

## Common questions

**Why did a stock appear yesterday but not today?**
Either it no longer meets all filters (pullback range, RSI, volume, bullish candle), or the sector cap (max 3 per sector) pushed it out.

**Why is my suggested share count low?**
The 1% risk rule caps your dollar risk at 1% of `PORTFOLIO_CAPITAL` (default $10,000 = $100 risk per trade). Update `PORTFOLIO_CAPITAL` in `scanner.py` to match your actual account size.

**The dashboard shows "No setups today" — is something wrong?**
Filters are deliberately strict. Zero setups on a given day is normal, especially in choppy or bear markets.
