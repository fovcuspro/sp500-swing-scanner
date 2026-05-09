# sp500-swing-scanner

Automated S&P 500 swing trade scanner. Runs daily on GitHub Actions, pushes iPhone notifications via ntfy, and hosts a mobile web dashboard via GitHub Pages.

**Strategy:** Momentum pullback on daily timeframes. Targets 2–4 week holds.

---

## Architecture

```
scanner.py          # Main script — fetches tickers, scores setups, writes results.json
notifier.py         # Reads results.json, sends push notifications via ntfy.sh
requirements.txt    # Python dependencies
index.html          # Mobile dashboard (served via GitHub Pages)

.github/
  workflows/
    daily_scan.yml  # Cron job — runs weekdays at 17:00 UTC (18:00 UK BST)
```

**Data flow:**

```
GitHub Actions (cron)
  → scanner.py
      → Wikipedia (S&P 500 ticker list)
      → yfinance (OHLCV daily data)
      → Scoring model
      → results.json (committed to repo)
  → notifier.py
      → ntfy.sh push notification → iPhone
  → GitHub Pages serves index.html + results.json
      → Dashboard fetches results.json at load time
```

---

## Scoring Model

Weighted score across three factors (0–10 each):

| Factor | Weight | Description |
|--------|--------|-------------|
| Trend strength | 40% | Price above key MAs, MA slope |
| Pullback quality | 40% | Retracement depth, structure |
| Volume confirmation | 20% | Relative volume on pullback vs trend |

---

## Key URLs

| Resource | URL |
|----------|-----|
| Dashboard | `https://fovcuspro.github.io/sp500-swing-scanner` |
| Results JSON | `https://fovcuspro.github.io/sp500-swing-scanner/results.json` |
| ntfy channel | `swing13cat` |
| Repo | `https://github.com/fovcuspro/sp500-swing-scanner` |

---

## Deployment

**GitHub Actions** runs `daily_scan.yml` on weekdays at 17:00 UTC. The workflow:
1. Installs Python dependencies
2. Runs `scanner.py` → writes `results.json`
3. Commits `results.json` back to the repo
4. Runs `notifier.py` → sends ntfy notification

**GitHub Pages** is configured at repo root (`/`), branch `main`. `index.html` and `results.json` are served from there.

---

## Mobile Setup

- **ntfy app** (iOS) subscribed to channel `swing13cat`
- Dashboard added to iPhone home screen via Safari → Share → Add to Home Screen

---

## Known Quirks / Lessons Learned

- `yfinance` period strings must be valid (e.g. `"1y"` not `"300d"`)
- Wikipedia S&P 500 ticker scraping can return 403 — handled with fallback
- GitHub Pages requires a **public repo** on the free tier
- `index.html` must be at repo **root** when Pages is configured with `/` setting
- The `workflow` scope must be explicitly added when pushing Actions files via GitHub CLI: `gh auth refresh -h github.com -s workflow`

---

## Adding New Features

When extending this project, the main touchpoints are:

- **New signal/filter** → `scanner.py` scoring section
- **New notification field** → `notifier.py` message template
- **New dashboard card field** → `index.html` `renderCard()` function + `results.json` schema
- **New data source** → `scanner.py` data fetch section; note free yfinance rate limits

Keep `results.json` schema changes backward-compatible (dashboard should handle missing fields gracefully).
