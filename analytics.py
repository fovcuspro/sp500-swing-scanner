"""
analytics.py
------------
Reads trade_history.json and computes performance statistics.
Writes analytics.json, which is served via GitHub Pages and consumed by the
Performance tab in index.html.
"""

import json
import logging
import os
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TRADE_HISTORY_FILE = "trade_history.json"
ANALYTICS_FILE     = "analytics.json"


def load_history() -> list[dict]:
    if not os.path.exists(TRADE_HISTORY_FILE):
        return []
    with open(TRADE_HISTORY_FILE) as f:
        return json.load(f)


def best_return(trade: dict) -> float | None:
    """Best available return % for a trade (prefers 4w, falls back to last)."""
    o = trade.get("outcomes", {})
    for key in ("4w_return_pct", "2w_return_pct", "1w_return_pct", "last_return_pct"):
        v = o.get(key)
        if v is not None:
            return v
    return None


def avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def group_stats(group: list[dict]) -> dict:
    if not group:
        return {"count": 0, "win_rate": 0.0, "avg_return": 0.0}
    returns = [r for t in group if (r := best_return(t)) is not None]
    wins    = [r for r in returns if r > 0]
    return {
        "count":      len(group),
        "win_rate":   round(len(wins) / len(returns), 3) if returns else 0.0,
        "avg_return": avg(returns),
    }


def by_score_range(closed: list[dict]) -> dict:
    buckets: dict[str, list] = {"5-6": [], "6-7": [], "7-8": [], "8-9": [], "9-10": []}
    for t in closed:
        s = t.get("score", 0)
        if   s >= 9: buckets["9-10"].append(t)
        elif s >= 8: buckets["8-9"].append(t)
        elif s >= 7: buckets["7-8"].append(t)
        elif s >= 6: buckets["6-7"].append(t)
        else:        buckets["5-6"].append(t)
    return {k: group_stats(v) for k, v in buckets.items()}


def by_rsi_range(closed: list[dict]) -> dict:
    buckets: dict[str, list] = {"40-45": [], "45-50": [], "50-55": [], "55-60": []}
    for t in closed:
        rsi = t.get("indicators", {}).get("rsi", 0)
        if   rsi >= 55: buckets["55-60"].append(t)
        elif rsi >= 50: buckets["50-55"].append(t)
        elif rsi >= 45: buckets["45-50"].append(t)
        else:           buckets["40-45"].append(t)
    return {k: group_stats(v) for k, v in buckets.items()}


def by_pullback_range(closed: list[dict]) -> dict:
    buckets: dict[str, list] = {"3-5%": [], "5-6%": [], "6-8%": []}
    for t in closed:
        pb = t.get("indicators", {}).get("pullback_pct", 0)
        if   pb >= 6: buckets["6-8%"].append(t)
        elif pb >= 5: buckets["5-6%"].append(t)
        else:         buckets["3-5%"].append(t)
    return {k: group_stats(v) for k, v in buckets.items()}


def by_regime(closed: list[dict]) -> dict:
    """Group trades by regime field. Returns {regime: group_stats}."""
    buckets: dict[str, list] = {"bull": [], "neutral": [], "bear": [], "unknown": []}
    for t in closed:
        r = t.get("regime", "") or "unknown"
        bucket_key = r if r in buckets else "unknown"
        buckets[bucket_key].append(t)
    return {k: group_stats(v) for k, v in buckets.items() if v}


def by_sector(closed: list[dict]) -> dict:
    """Group trades by sector field."""
    buckets: dict[str, list] = {}
    for t in closed:
        sec = t.get("sector", "") or "Unknown"
        buckets.setdefault(sec, []).append(t)
    return {k: group_stats(v) for k, v in sorted(buckets.items())}


def stop_ab_test(closed: list[dict]) -> dict:
    """Compare performance for trades where stop_method='swing' vs 'atr'."""
    swing_trades = [t for t in closed if t.get("stop_method") == "swing"]
    atr_trades   = [t for t in closed if t.get("stop_method") == "atr"]
    return {
        "swing": group_stats(swing_trades),
        "atr":   group_stats(atr_trades),
    }


def compute_analytics(history: list[dict]) -> dict:
    closed  = [t for t in history if t["status"] in ("target_hit", "stop_hit", "expired")]
    returns = [r for t in closed if (r := best_return(t)) is not None]
    wins    = [r for r in returns if r > 0]
    losses  = [r for r in returns if r <= 0]

    win_rate = round(len(wins) / len(returns), 3) if returns else 0.0
    avg_win  = avg(wins)
    avg_loss = avg(losses)
    expectancy = round((win_rate * avg_win) + ((1 - win_rate) * avg_loss), 2) if returns else 0.0

    best  = max(closed, key=lambda t: best_return(t) or -999, default=None)
    worst = min(closed, key=lambda t: best_return(t) or  999, default=None)

    recent = sorted(closed, key=lambda t: t.get("date_generated", ""), reverse=True)[:30]

    return {
        "generated_at":   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_trades":   len(history),
        "open_trades":    sum(1 for t in history if t["status"] == "open"),
        "closed_trades":  len(closed),
        "win_rate":       win_rate,
        "avg_return_pct": avg(returns),
        "avg_win_pct":    avg_win,
        "avg_loss_pct":   avg_loss,
        "expectancy":     expectancy,
        "best_trade": {
            "ticker":     best["ticker"],
            "date":       best["date_generated"],
            "return_pct": best_return(best),
        } if best else None,
        "worst_trade": {
            "ticker":     worst["ticker"],
            "date":       worst["date_generated"],
            "return_pct": best_return(worst),
        } if worst else None,
        "by_score_range":    by_score_range(closed),
        "by_rsi_range":      by_rsi_range(closed),
        "by_pullback_range": by_pullback_range(closed),
        "by_regime":         by_regime(closed),
        "by_sector":         by_sector(closed),
        "stop_ab_test":      stop_ab_test(closed),
        "recent_trades": [
            {
                "ticker":       t["ticker"],
                "company_name": t.get("company_name", t["ticker"]),
                "date":         t["date_generated"],
                "score":        t.get("score"),
                "return_pct":   best_return(t),
                "status":       t["status"],
                "days_held":    t.get("outcomes", {}).get("last_checked") and
                                (
                                    __import__("datetime").date.fromisoformat(
                                        t.get("outcomes", {}).get("last_checked")
                                    ) -
                                    __import__("datetime").date.fromisoformat(t["date_generated"])
                                ).days,
            }
            for t in recent
        ],
    }


def empty_analytics() -> dict:
    return {
        "generated_at":   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_trades":   0,
        "open_trades":    0,
        "closed_trades":  0,
        "win_rate":       0.0,
        "avg_return_pct": 0.0,
        "avg_win_pct":    0.0,
        "avg_loss_pct":   0.0,
        "expectancy":     0.0,
        "best_trade":     None,
        "worst_trade":    None,
        "by_score_range":    {},
        "by_rsi_range":      {},
        "by_pullback_range": {},
        "by_regime":         {},
        "by_sector":         {},
        "stop_ab_test":      {},
        "recent_trades":     [],
    }


def main():
    history   = load_history()
    analytics = compute_analytics(history) if history else empty_analytics()

    with open(ANALYTICS_FILE, "w") as f:
        json.dump(analytics, f, indent=2)

    log.info(
        f"analytics.json written — {analytics['total_trades']} trades, "
        f"{analytics['closed_trades']} closed, "
        f"win rate: {analytics['win_rate']:.1%}, "
        f"expectancy: {analytics['expectancy']:+.2f}%"
    )


if __name__ == "__main__":
    main()
