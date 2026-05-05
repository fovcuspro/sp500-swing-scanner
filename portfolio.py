"""
portfolio.py
------------
Daily portfolio tracker for S&P 500 swing positions.
Reads holdings from portfolio.json, fetches live data via yfinance,
computes P&L, risk metrics, and writes results to portfolio_results.json.
"""

import json
import logging
import math
import os
from datetime import datetime, timezone

import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


PORTFOLIO_FILE = "portfolio.json"
OUTPUT_FILE    = "portfolio_results.json"


def load_portfolio() -> list[dict]:
    if not os.path.exists(PORTFOLIO_FILE):
        log.warning("portfolio.json not found — returning empty portfolio.")
        return []
    with open(PORTFOLIO_FILE) as f:
        return json.load(f)


def fetch_quote(ticker: str) -> dict | None:
    try:
        tk   = yf.Ticker(ticker)
        hist = tk.history(period="5d")
        if hist.empty:
            log.warning(f"No data for {ticker}")
            return None
        info = tk.fast_info
        last_close  = float(hist["Close"].iloc[-1])
        prev_close  = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else last_close
        day_change  = last_close - prev_close
        day_change_pct = (day_change / prev_close) * 100 if prev_close else 0.0
        volume      = int(hist["Volume"].iloc[-1])
        avg_volume  = int(hist["Volume"].mean())
        week_high   = float(hist["High"].max())
        week_low    = float(hist["Low"].min())
        return {
            "last_close":      round(last_close, 2),
            "prev_close":      round(prev_close, 2),
            "day_change":      round(day_change, 2),
            "day_change_pct":  round(day_change_pct, 2),
            "volume":          volume,
            "avg_volume":      avg_volume,
            "week_high":       round(week_high, 2),
            "week_low":        round(week_low, 2),
        }
    except Exception as e:
        log.error(f"Error fetching {ticker}: {e}")
        return None


def analyse_position(holding: dict, quote: dict) -> dict:
    ticker      = holding["ticker"].upper()
    shares      = float(holding["shares"])
    entry_price = float(holding["entry_price"])
    stop_loss   = float(holding.get("stop_loss", 0))
    target      = float(holding.get("target", 0))
    notes       = holding.get("notes", "")

    current     = quote["last_close"]
    cost_basis  = entry_price * shares
    mkt_value   = current * shares
    unrealised  = mkt_value - cost_basis
    unrealised_pct = ((current - entry_price) / entry_price) * 100

    # Risk / reward remaining
    risk_per_share    = current - stop_loss if stop_loss else None
    reward_per_share  = target - current    if target    else None
    risk_reward       = round(reward_per_share / abs(risk_per_share), 2) \
                        if risk_per_share and reward_per_share and risk_per_share != 0 else None

    # Distance to stop / target as %
    pct_to_stop   = round(((stop_loss - current) / current) * 100, 2) if stop_loss else None
    pct_to_target = round(((target    - current) / current) * 100, 2) if target    else None

    # Position health signal
    if stop_loss and current <= stop_loss:
        signal = "STOP_HIT"
    elif target and current >= target:
        signal = "TARGET_HIT"
    elif unrealised_pct >= 5:
        signal = "RUNNING"
    elif unrealised_pct <= -3:
        signal = "UNDER_PRESSURE"
    else:
        signal = "ON_TRACK"

    return {
        "ticker":          ticker,
        "shares":          shares,
        "entry_price":     round(entry_price, 2),
        "current_price":   current,
        "stop_loss":       stop_loss,
        "target":          target,
        "notes":           notes,
        "cost_basis":      round(cost_basis, 2),
        "market_value":    round(mkt_value, 2),
        "unrealised_pnl":  round(unrealised, 2),
        "unrealised_pct":  round(unrealised_pct, 2),
        "day_change":      quote["day_change"],
        "day_change_pct":  quote["day_change_pct"],
        "volume":          quote["volume"],
        "avg_volume":      quote["avg_volume"],
        "pct_to_stop":     pct_to_stop,
        "pct_to_target":   pct_to_target,
        "risk_reward":     risk_reward,
        "signal":          signal,
    }


def build_summary(positions: list[dict]) -> dict:
    total_cost    = sum(p["cost_basis"]   for p in positions)
    total_value   = sum(p["market_value"] for p in positions)
    total_pnl     = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0.0
    day_pnl       = sum(p["day_change"] * p["shares"] for p in positions)

    alerts = [p["ticker"] for p in positions if p["signal"] in ("STOP_HIT", "TARGET_HIT", "UNDER_PRESSURE")]

    return {
        "total_cost_basis":  round(total_cost, 2),
        "total_market_value": round(total_value, 2),
        "total_unrealised_pnl": round(total_pnl, 2),
        "total_unrealised_pct": round(total_pnl_pct, 2),
        "day_pnl":           round(day_pnl, 2),
        "positions_count":   len(positions),
        "alert_tickers":     alerts,
    }


def main():
    holdings = load_portfolio()
    if not holdings:
        log.info("No holdings found. Add positions to portfolio.json.")
        result = {
            "scan_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "summary":   {},
            "positions": [],
        }
        with open(OUTPUT_FILE, "w") as f:
            json.dump(result, f, indent=2)
        return

    positions = []
    for h in holdings:
        ticker = h.get("ticker", "").upper()
        log.info(f"Fetching {ticker}...")
        quote = fetch_quote(ticker)
        if quote:
            pos = analyse_position(h, quote)
            positions.append(pos)
        else:
            log.warning(f"Skipping {ticker} — no data.")

    summary = build_summary(positions)

    result = {
        "scan_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "summary":   summary,
        "positions": positions,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(result, f, indent=2)

    log.info(f"Done. {len(positions)} positions tracked. Total P&L: ${summary['total_unrealised_pnl']:+.2f}")


if __name__ == "__main__":
    main()
