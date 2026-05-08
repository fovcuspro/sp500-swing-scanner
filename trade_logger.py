"""
trade_logger.py
---------------
Appends new scanner signals to trade_history.json after each scan run.
Reads results.json, checks for duplicates by (ticker, date), and appends
any new setups with empty outcome fields ready for outcome_tracker.py.
"""

import json
import logging
import os
from datetime import date

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

RESULTS_FILE       = "results.json"
TRADE_HISTORY_FILE = "trade_history.json"


def load_history() -> list[dict]:
    if not os.path.exists(TRADE_HISTORY_FILE):
        return []
    with open(TRADE_HISTORY_FILE) as f:
        return json.load(f)


def save_history(history: list[dict]) -> None:
    with open(TRADE_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def log_trades(results: dict) -> int:
    history   = load_history()
    existing  = {t["id"] for t in history}
    scan_date = results.get("scan_date", date.today().isoformat())
    new_count = 0

    for setup in results.get("top_setups", []):
        ticker   = setup["ticker"]
        trade_id = f"{ticker}_{scan_date}"

        if trade_id in existing:
            continue

        entry = {
            "id":             trade_id,
            "ticker":         ticker,
            "company_name":   setup.get("company_name", ticker),
            "date_generated": scan_date,
            "setup_type":     setup.get("setup", "Momentum Pullback"),
            "score":          setup.get("score", 0),
            "score_breakdown": setup.get("score_breakdown", {}),
            "entry_price":    setup.get("price"),
            "stop_loss":      setup.get("stop_loss"),
            "target":         setup.get("target"),
            "risk_reward":    setup.get("risk_reward"),
            "indicators":     setup.get("indicators", {}),
            "reasoning":      setup.get("reasoning", ""),
            "outcomes": {
                "1w_price":          None,
                "2w_price":          None,
                "4w_price":          None,
                "1w_return_pct":     None,
                "2w_return_pct":     None,
                "4w_return_pct":     None,
                "max_gain_pct":      None,
                "max_drawdown_pct":  None,
                "target_hit":        False,
                "stop_hit":          False,
                "last_price":        None,
                "last_return_pct":   None,
                "last_checked":      None,
            },
            "status": "open",
        }
        history.append(entry)
        existing.add(trade_id)
        new_count += 1
        log.info(f"Logged new trade: {trade_id}  score={setup.get('score', 0):.3f}")

    save_history(history)
    log.info(f"trade_logger: {new_count} new trades added. Total in history: {len(history)}")
    return new_count


def main():
    if not os.path.exists(RESULTS_FILE):
        log.warning("results.json not found — nothing to log.")
        return
    with open(RESULTS_FILE) as f:
        results = json.load(f)
    log_trades(results)


if __name__ == "__main__":
    main()
