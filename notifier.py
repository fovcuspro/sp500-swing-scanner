"""
notifier.py — sends push notification via ntfy.sh when scan completes
Includes daily diff: new tickers vs previous scan, regime changes.
"""
import json
import logging
import os
import urllib.request
import urllib.error

log = logging.getLogger(__name__)

NTFY_CHANNEL    = "swing13cat"
NTFY_URL        = f"https://ntfy.sh/{NTFY_CHANNEL}"
RESULTS_FILE    = "results.json"
PREV_RESULTS    = "prev_results.json"


def _load_tickers(path: str) -> set[str]:
    try:
        with open(path) as f:
            data = json.load(f)
        return {s["ticker"] for s in data.get("top_setups", [])}
    except Exception:
        return set()


def notify(results_path: str = RESULTS_FILE) -> None:
    try:
        with open(results_path) as f:
            data = json.load(f)

        top     = data.get("top_setups", [])
        today   = data.get("scan_date", "today")
        count   = data.get("candidates_found", 0)
        regime  = data.get("market_regime", "")
        n       = len(top)

        # Diff vs yesterday
        prev_tickers    = _load_tickers(PREV_RESULTS) if os.path.exists(PREV_RESULTS) else set()
        today_tickers   = {s["ticker"] for s in top}
        new_tickers     = sorted(today_tickers - prev_tickers)
        removed_tickers = sorted(prev_tickers - today_tickers)

        if not top:
            title    = "SP500 Scanner - No setups today"
            message  = f"Scan complete ({today}). No stocks passed all filters. Regime: {regime}."
            priority = "low"
            tags     = "chart_with_downwards_trend"
        else:
            ticker_list = ", ".join(r["ticker"] for r in top[:5])
            top_score   = top[0]["score"]
            title   = f"SP500 Scanner - {n} setups - {regime.upper()}"
            lines   = [
                f"{today} · {count} candidates screened",
                f"Top: {ticker_list}",
                f"Best score: {top_score:.1f}/10",
            ]
            if regime:
                lines.append(f"Regime: {regime}")
            if new_tickers:
                lines.append(f"New: {', '.join(new_tickers[:5])}")
            if removed_tickers:
                lines.append(f"Dropped: {', '.join(removed_tickers[:5])}")
            message  = "\n".join(lines)
            priority = "high" if regime == "bull" else "default"
            tags     = "chart_with_upwards_trend,white_check_mark"

        req = urllib.request.Request(
            NTFY_URL,
            data=message.encode("utf-8"),
            headers={
                "Title":        title,
                "Priority":     priority,
                "Tags":         tags,
                "Content-Type": "text/plain",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                log.info(f"Notification sent to ntfy.sh/{NTFY_CHANNEL}")

    except Exception as e:
        log.error(f"Notifier error: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    notify()
