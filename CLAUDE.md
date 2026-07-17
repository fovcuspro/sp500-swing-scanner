# SP500 Swing Scanner — Claude Code Instructions

## Framework Docs
- Always check PRD.md, PLANNING.md, and TASKS.md before coding; STATUS.md tracks session state.
- Run local tests frequently.

## What This Is
Automated S&P 500 swing trading scanner. Runs daily on GitHub Actions, pushes iPhone notifications via ntfy.sh, and serves a mobile dashboard via GitHub Pages.

**Repo:** `fovcuspro/sp500-swing-scanner`
**Dashboard:** `https://fovcuspro.github.io/sp500-swing-scanner`
**ntfy channel:** `swing13cat`
**Scan time:** Weekdays 13:00 UTC

---

## How to Run Locally
```bash
pip install -r requirements.txt
python scanner.py
```

---

## Rules You Must Always Follow
- Never hardcode ticker symbols
- All data must be free (yfinance + Wikipedia only)
- Always handle missing or incomplete data gracefully
- Never break the results.json schema — all changes must be additive
- scanner.py is the single source of truth for all filter/scoring/stop logic — backtest.py imports from it, never duplicates it
- PORTFOLIO_CAPITAL in scanner.py must stay at whatever value is currently set — never reset it
- Never change NTFY_CHANNEL or repo URLs without being asked

---

## Key File Relationships

```
scanner.py          ← single source of truth for all strategy logic

scanner.py → results.json
trade_logger.py → trade_history.json   (reads results.json)
outcome_tracker.py → trade_history.json (updates outcomes)
analytics.py → analytics.json          (reads trade_history.json)
healthcheck.py → health.json           (reads results.json)
notifier.py → ntfy push               (reads results.json + prev_results.json)

index.html fetches: results.json, analytics.json, trade_history.json,
                    portfolio_results.json, backtest_compare.json, health.json
```

---

## results.json Schema (never break these fields)

Every setup in `top_setups` must have:
- `ticker`, `company_name`, `sector`, `score`, `score_breakdown`
- `price`, `entry_zone` {low, high}, `stop_loss`, `target`, `risk_reward`
- `stop_method`, `swing_stop`, `atr_stop`
- `position_sizing` {suggested_shares, dollar_risk, position_value, regime_size_applied}
- `exit_plan` {tiers [{label, price, fraction}], runner {fraction, trail_atr_multiple}}
- `indicators` {rsi, ma50, ma200, atr, high_20d, pullback_pct, volume_ratio}
- `regime`, `sizing_factor`, `reasoning`

Top level must have:
- `scan_date`, `scan_time_utc`, `market_regime`, `strategy`
- `candidates_found`, `earnings_skipped`, `sector_breakdown`, `top_setups`

---

## Backtest Usage

```bash
python backtest.py           # statistical analysis, prints to log
python backtest.py compare   # 4-variant comparison → backtest_compare.json
```

Run `python backtest.py compare` after any strategy parameter change and commit `backtest_compare.json` to populate the Lab tab.

---

## Common Issues

- **Wikipedia 403 on ticker fetch** — handled in code with User-Agent header
- **yfinance period strings** — must use valid strings like `"1y"`, `"300d"` is invalid
- **GitHub Pages staleness** — Pages can take 30–60s to update after a commit; the dashboard cache-busts with `?t=Date.now()`
- **workflow scope missing** — run `gh auth refresh -h github.com -s workflow` then retry push
- **earnings.json refresh** — happens automatically when file is > 7 days old; if forced refresh needed, delete the file and re-run scanner
