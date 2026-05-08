"""
outcome_tracker.py
------------------
Fetches current and historical prices for open trades and updates outcomes.
Run daily after the scanner. Marks trades closed when target/stop is hit
or the 4-week hold period expires.
"""

import json
import logging
import os
from datetime import date, timedelta

import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TRADE_HISTORY_FILE = "trade_history.json"
HOLD_PERIOD_DAYS   = 28


def load_history() -> list[dict]:
    if not os.path.exists(TRADE_HISTORY_FILE):
        return []
    with open(TRADE_HISTORY_FILE) as f:
        return json.load(f)


def save_history(history: list[dict]) -> None:
    with open(TRADE_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def fetch_current_prices(tickers: list[str]) -> dict[str, float]:
    if not tickers:
        return {}
    try:
        raw    = yf.download(tickers, period="5d", interval="1d",
                             auto_adjust=True, progress=False, threads=True)
        prices = {}
        for ticker in tickers:
            try:
                if len(tickers) == 1:
                    close = float(raw["Close"].iloc[-1])
                else:
                    close = float(raw["Close"][ticker].dropna().iloc[-1])
                scale = 0.01 if ticker.upper().endswith(".L") else 1.0
                prices[ticker] = round(close * scale, 2)
            except Exception:
                continue
        return prices
    except Exception as e:
        log.error(f"Batch price fetch failed: {e}")
        return {}


def fetch_price_on_date(ticker: str, target_date: date) -> float | None:
    """Return the closing price on the first trading day on or after target_date."""
    try:
        start = target_date - timedelta(days=4)
        end   = target_date + timedelta(days=6)
        hist  = yf.Ticker(ticker).history(start=start.isoformat(), end=end.isoformat())
        if hist.empty:
            return None
        # Select first row whose date >= target_date
        mask     = [ts.date() >= target_date for ts in hist.index]
        filtered = hist[mask]
        if filtered.empty:
            return None
        scale = 0.01 if ticker.upper().endswith(".L") else 1.0
        return round(float(filtered["Close"].iloc[0]) * scale, 2)
    except Exception as e:
        log.warning(f"Historical price fetch failed {ticker} @ {target_date}: {e}")
        return None


def update_trade(trade: dict, today: date, current_prices: dict[str, float]) -> dict:
    if trade["status"] != "open":
        return trade

    gen_date    = date.fromisoformat(trade["date_generated"])
    days_held   = (today - gen_date).days
    entry_price = trade.get("entry_price") or 0
    stop_loss   = trade.get("stop_loss")
    target      = trade.get("target")
    outcomes    = trade.setdefault("outcomes", {})

    if not entry_price:
        return trade

    # Fill milestone prices once the required days have elapsed
    for label, days in [("1w", 7), ("2w", 14), ("4w", 28)]:
        if outcomes.get(f"{label}_price") is None and days_held >= days:
            milestone_date = gen_date + timedelta(days=days)
            price = fetch_price_on_date(trade["ticker"], milestone_date)
            if price:
                outcomes[f"{label}_price"]      = price
                outcomes[f"{label}_return_pct"] = round(
                    ((price - entry_price) / entry_price) * 100, 2
                )
                log.info(f"{trade['ticker']} {label} price={price}  "
                         f"ret={outcomes[f'{label}_return_pct']:+.2f}%")

    # Update current price
    current = current_prices.get(trade["ticker"])
    if current:
        ret_pct = ((current - entry_price) / entry_price) * 100
        outcomes["last_price"]      = current
        outcomes["last_return_pct"] = round(ret_pct, 2)
        outcomes["last_checked"]    = today.isoformat()

        prev_max = outcomes.get("max_gain_pct")     or 0
        prev_min = outcomes.get("max_drawdown_pct") or 0
        outcomes["max_gain_pct"]     = round(max(prev_max, ret_pct), 2)
        outcomes["max_drawdown_pct"] = round(min(prev_min, ret_pct), 2)

        if target    and current >= target:
            outcomes["target_hit"] = True
            trade["status"] = "target_hit"
            log.info(f"{trade['ticker']} TARGET HIT @ {current}")
        elif stop_loss and current <= stop_loss:
            outcomes["stop_hit"] = True
            trade["status"] = "stop_hit"
            log.info(f"{trade['ticker']} STOP HIT @ {current}")

    # Expire after hold period
    if days_held >= HOLD_PERIOD_DAYS and trade["status"] == "open":
        trade["status"] = "expired"
        log.info(f"{trade['ticker']} expired after {days_held} days")

    return trade


def main():
    history = load_history()
    if not history:
        log.info("No trade history found.")
        return

    today       = date.today()
    open_trades = [t for t in history if t["status"] == "open"]
    log.info(f"Open trades: {len(open_trades)}  |  Total: {len(history)}")

    if not open_trades:
        log.info("Nothing to update.")
        return

    tickers        = list({t["ticker"] for t in open_trades})
    current_prices = fetch_current_prices(tickers)
    log.info(f"Fetched current prices for {len(current_prices)} tickers.")

    updated = []
    for trade in history:
        if trade["status"] == "open":
            trade = update_trade(trade, today, current_prices)
        updated.append(trade)

    save_history(updated)
    log.info("Outcome tracker complete.")


if __name__ == "__main__":
    main()
