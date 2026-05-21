"""
backtest.py
Statistical analysis of trade history across 4 strategy variants.
Uses trade_history.json — requires at least some closed trades.

Usage:
    python backtest.py           # default analysis
    python backtest.py compare   # 4-variant comparison → backtest_compare.json
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TRADE_HISTORY_FILE = "trade_history.json"
BACKTEST_COMPARE_FILE = "backtest_compare.json"


def load_history() -> list[dict]:
    if not os.path.exists(TRADE_HISTORY_FILE):
        return []
    with open(TRADE_HISTORY_FILE) as f:
        return json.load(f)


def best_return(trade: dict) -> float | None:
    o = trade.get("outcomes", {})
    for key in ("4w_return_pct", "2w_return_pct", "1w_return_pct", "last_return_pct"):
        v = o.get(key)
        if v is not None:
            return v
    return None


def avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def variant_stats(trades: list[dict], label: str) -> dict:
    closed  = [t for t in trades if t.get("status") in ("target_hit", "stop_hit", "expired")]
    returns = [r for t in closed if (r := best_return(t)) is not None]
    wins    = [r for r in returns if r > 0]
    losses  = [r for r in returns if r <= 0]

    win_rate   = round(len(wins) / len(returns), 3) if returns else 0.0
    avg_win    = avg(wins)
    avg_loss   = avg(losses)
    expectancy = round((win_rate * avg_win) + ((1 - win_rate) * avg_loss), 2) if returns else 0.0
    total_ret  = sum(returns)

    return {
        "label":          label,
        "total_trades":   len(trades),
        "closed_trades":  len(closed),
        "win_rate":       win_rate,
        "avg_return_pct": avg(returns),
        "avg_win_pct":    avg_win,
        "avg_loss_pct":   avg_loss,
        "expectancy":     expectancy,
        "total_return_pct": round(total_ret, 2),
    }


def compare(history: list[dict]) -> dict:
    """4-variant comparison:
      V1: All trades, swing stop
      V2: All trades, ATR stop
      V3: Bull regime only, swing stop
      V4: Bull regime only, ATR stop
    """
    swing_trades = [t for t in history if t.get("stop_method") != "atr"]
    atr_trades   = [t for t in history if t.get("stop_method") == "atr"]
    bull_swing   = [t for t in swing_trades if t.get("regime") == "bull"]
    bull_atr     = [t for t in atr_trades   if t.get("regime") == "bull"]

    variants = [
        variant_stats(swing_trades, "All trades — Swing stop"),
        variant_stats(atr_trades,   "All trades — ATR stop"),
        variant_stats(bull_swing,   "Bull regime — Swing stop"),
        variant_stats(bull_atr,     "Bull regime — ATR stop"),
    ]

    return {
        "generated_at":   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_trades":   len(history),
        "variants":       variants,
        "note": "Statistical analysis of trade_history.json. More trades = more reliable results.",
    }


def main():
    history = load_history()
    if not history:
        log.warning("No trade history found.")
        return

    if len(sys.argv) > 1 and sys.argv[1] == "compare":
        result = compare(history)
        with open(BACKTEST_COMPARE_FILE, "w") as f:
            json.dump(result, f, indent=2)
        log.info(f"backtest_compare.json written — {len(result['variants'])} variants")
        for v in result["variants"]:
            log.info(
                f"  {v['label']}: trades={v['total_trades']} win={v['win_rate']:.0%} "
                f"exp={v['expectancy']:+.2f}%"
            )
    else:
        # Default: show overall stats
        result = compare(history)
        log.info(f"Total trades in history: {len(history)}")
        for v in result["variants"]:
            log.info(
                f"  {v['label']}: closed={v['closed_trades']} "
                f"win={v['win_rate']:.0%} avg={v['avg_return_pct']:+.2f}% "
                f"exp={v['expectancy']:+.2f}%"
            )


if __name__ == "__main__":
    main()
