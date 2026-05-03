"""
notifier.py - sends push notification via ntfy.sh when scan completes
"""
import json
import logging
import urllib.request
import urllib.error

log = logging.getLogger(__name__)

NTFY_CHANNEL = "swing13cat"
NTFY_URL     = f"https://ntfy.sh/{NTFY_CHANNEL}"

def notify(results_path: str = "results.json") -> None:
    try:
        with open(results_path) as f:
            data = json.load(f)
        top      = data.get("top_setups", [])
        date     = data.get("scan_date", "today")
        count    = data.get("candidates_found", 0)
        n        = len(top)
        if not top:
            title    = "SP500 Scanner — No setups today"
            message  = f"Scan complete ({date}). No stocks passed all filters."
            priority = "low"
            tags     = "chart_with_downwards_trend"
        else:
            tickers  = ", ".join(r["ticker"] for r in top[:5])
            top_score = top[0]["score"]
            title    = f"SP500 Scanner — {n} setups found"
            message  = f"{date} · {count} candidates screened\nTop: {tickers}\nBest score: {top_score}/10"
            priority = "default"
            tags     = "chart_with_upwards_trend,white_check_mark"
        req = urllib.request.Request(
            NTFY_URL,
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": priority, "Tags": tags, "Content-Type": "text/plain"},
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
