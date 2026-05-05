"""
portfolio_notifier.py
Sends a push notification via ntfy.sh with portfolio summary.
"""

import json
import logging
import urllib.request

log = logging.getLogger(__name__)

NTFY_CHANNEL = "swing13cat"
NTFY_URL     = f"https://ntfy.sh/{NTFY_CHANNEL}"


def notify(results_path: str = "portfolio_results.json") -> None:
    try:
        with open(results_path) as f:
            data = json.load(f)

        summary   = data.get("summary", {})
        positions = data.get("positions", [])
        date      = data.get("scan_date", "today")

        if not positions:
            title   = "Portfolio — No positions"
            message = "Add positions to portfolio.json to start tracking."
        else:
            pnl     = summary.get("total_unrealised_pnl", 0)
            pnl_pct = summary.get("total_unrealised_pct", 0)
            day_pnl = summary.get("day_pnl", 0)
            alerts  = summary.get("alert_tickers", [])
            n       = summary.get("positions_count", 0)

            pnl_sign = "+" if pnl >= 0 else ""
            day_sign = "+" if day_pnl >= 0 else ""

            title = f"Portfolio — {pnl_sign}${pnl:,.0f} ({pnl_sign}{pnl_pct:.1f}%)"
            lines = [
                f"Day P&L: {day_sign}${day_pnl:,.0f}",
                f"Positions: {n}",
            ]
            if alerts:
                lines.append(f"⚠️ Alerts: {', '.join(alerts)}")

            # Top movers
            sorted_pos = sorted(positions, key=lambda x: abs(x.get("day_change_pct", 0)), reverse=True)
            for p in sorted_pos[:3]:
                sign = "+" if p["day_change_pct"] >= 0 else ""
                lines.append(f"  {p['ticker']}: {sign}{p['day_change_pct']:.1f}%  ${p['current_price']:.2f}")

            message = "\n".join(lines)

        priority = "urgent" if any(
            p.get("signal") in ("STOP_HIT", "TARGET_HIT") for p in positions
        ) else "default"

        req = urllib.request.Request(
            NTFY_URL,
            data=message.encode(),
            headers={
                "Title":    title,
                "Priority": priority,
                "Tags":     "chart_with_upwards_trend",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            log.info(f"ntfy.sh response: {resp.status}")

    except Exception as e:
        log.error(f"Notification failed: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    notify()
