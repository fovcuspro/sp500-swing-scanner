"""
S&P 500 Swing Trading Scanner
Momentum Pullback Strategy | Daily Timeframe
Runs once per day, outputs top 10 setups to results.json
"""

import io
import json
import logging
import urllib.request
import warnings
from datetime import datetime, date, timezone
from typing import Optional

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings("ignore")

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scanner.log"),
    ],
)
log = logging.getLogger(__name__)

# ── Scoring Weights ───────────────────────────────────────────────────────────
#
#  Trend Strength    40% — primary filter; strong trends = higher win rate
#  Pullback Quality  40% — entry timing is critical for R:R
#  Volume Confirm    20% — supporting evidence, not a primary driver
#
WEIGHT_TREND    = 0.40
WEIGHT_PULLBACK = 0.40
WEIGHT_VOLUME   = 0.20

# ── Parameters ────────────────────────────────────────────────────────────────

PULLBACK_MIN  = 0.03   # 3% below 20-day high  (min pullback)
PULLBACK_MAX  = 0.08   # 8% below 20-day high  (max pullback)
RSI_LOW       = 40
RSI_HIGH      = 52     # Tightened from 60 → 52 (data: RSI 45-50 wins, 55-60 loses)
VOLUME_MULT   = 1.3    # today's vol > 1.3× 20-day avg vol
MIN_SCORE     = 6.0    # Minimum score threshold — all signals were 5-6, raise quality floor
TOP_N         = 10
LOOKBACK_DAYS = 300    # calendar days of history to fetch


# ─────────────────────────────────────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────────────────────────────────────

def get_sp500_tickers() -> tuple[list[str], dict[str, str]]:
    """Scrape S&P 500 tickers and company names from Wikipedia."""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp:
            html = resp.read().decode("utf-8")
        tables = pd.read_html(io.StringIO(html))
        df = tables[0]
        raw_symbols = df["Symbol"].tolist()
        tickers = [s.replace(".", "-") for s in raw_symbols]
        names = {s.replace(".", "-"): n for s, n in zip(raw_symbols, df["Security"].tolist())}
        log.info(f"Fetched {len(tickers)} S&P 500 tickers from Wikipedia.")
        return tickers, names
    except Exception as e:
        log.error(f"Failed to fetch S&P 500 tickers: {e}")
        raise


def fetch_ohlcv(tickers: list[str], period_days: int = LOOKBACK_DAYS) -> dict[str, pd.DataFrame]:
    """
    Batch-download OHLCV data for all tickers via yfinance.
    Returns a dict of {ticker: DataFrame}.
    """
    log.info(f"Downloading data for {len(tickers)} tickers...")
    raw = yf.download(
        tickers,
        period="1y",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
    )

    result: dict[str, pd.DataFrame] = {}

    for ticker in tickers:
        try:
            if len(tickers) == 1:
                df = raw.copy()
            else:
                df = raw[ticker].copy()

            df.dropna(subset=["Close"], inplace=True)

            if len(df) < 210:           # need 200-day MA + buffer
                continue

            df.index = pd.to_datetime(df.index)
            result[ticker] = df
        except Exception:
            continue

    log.info(f"Usable data for {len(result)} tickers.")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# INDICATORS
# ─────────────────────────────────────────────────────────────────────────────

def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def enrich(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Add all indicator columns. Returns None if data is insufficient."""
    try:
        df = df.copy()
        df["ma50"]       = sma(df["Close"], 50)
        df["ma200"]      = sma(df["Close"], 200)
        df["rsi"]        = compute_rsi(df["Close"], 14)
        df["high20"]     = df["High"].rolling(20).max()
        df["vol_avg20"]  = df["Volume"].rolling(20).mean()

        # Drop rows where any key indicator is NaN
        df.dropna(subset=["ma50", "ma200", "rsi", "high20", "vol_avg20"], inplace=True)

        return df if len(df) >= 5 else None
    except Exception as e:
        log.debug(f"enrich failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# SCREENING  — filter stocks that pass all hard rules
# ─────────────────────────────────────────────────────────────────────────────

def passes_filters(row: pd.Series) -> bool:
    """Boolean gate — ALL conditions must be True."""
    price  = row["Close"]
    ma50   = row["ma50"]
    ma200  = row["ma200"]
    high20 = row["high20"]
    rsi    = row["rsi"]
    vol    = row["Volume"]
    vol20  = row["vol_avg20"]
    open_  = row["Open"]

    # Trend filter
    if price <= ma50:        return False
    if ma50   <= ma200:      return False

    # Pullback
    pct_off_high = (high20 - price) / high20
    if not (PULLBACK_MIN <= pct_off_high <= PULLBACK_MAX):
        return False

    # RSI
    if not (RSI_LOW <= rsi <= RSI_HIGH):
        return False

    # Volume spike
    if vol20 == 0 or (isinstance(vol20, float) and np.isnan(vol20)):
        pass  # skip volume check when avg is unavailable
    elif vol <= VOLUME_MULT * vol20:
        return False

    # Bullish candle
    if price <= open_:
        return False

    return True


# ─────────────────────────────────────────────────────────────────────────────
# SCORING  — 0–10 per dimension, then weighted sum
# ─────────────────────────────────────────────────────────────────────────────

def score_trend(row: pd.Series) -> float:
    """
    Trend Strength (0–10):
      5 pts — distance of price above 50 MA  (capped at 20%)
      5 pts — distance of 50 MA above 200 MA (capped at 15%)
    """
    price_vs_ma50 = (row["Close"] - row["ma50"]) / row["ma50"]
    ma_spread     = (row["ma50"]  - row["ma200"]) / row["ma200"]

    pts_price = min(price_vs_ma50 / 0.20, 1.0) * 5   # 20% → full 5 pts
    pts_ma    = min(ma_spread     / 0.15, 1.0) * 5   # 15% → full 5 pts

    return round(pts_price + pts_ma, 2)


def score_pullback(row: pd.Series) -> float:
    """
    Pullback Quality (0–10):
      5 pts — depth: ideal ~5%; scored as 1 – |depth – 0.05| / 0.05 (triangular)
      5 pts — RSI: ideal = 50; scored as 1 – |rsi – 50| / 10 (linear in [40,60])
    """
    depth = (row["high20"] - row["Close"]) / row["high20"]
    rsi   = row["rsi"]

    depth_score = max(0.0, 1.0 - abs(depth - 0.05) / 0.05) * 5
    rsi_score   = max(0.0, 1.0 - abs(rsi   - 50.0) / 10.0) * 5

    return round(depth_score + rsi_score, 2)


def score_volume(row: pd.Series) -> float:
    """
    Volume Confirmation (0–10):
      Ratio = vol / vol_avg20; 1.3× → 0 pts, 3.0× → 10 pts (linear, capped).
    """
    ratio = row["Volume"] / row["vol_avg20"] if row["vol_avg20"] > 0 else 1.0
    score = (ratio - 1.3) / (3.0 - 1.3) * 10
    return round(max(0.0, min(score, 10.0)), 2)


def total_score(row: pd.Series) -> float:
    t = score_trend(row)
    p = score_pullback(row)
    v = score_volume(row)
    return round(t * WEIGHT_TREND + p * WEIGHT_PULLBACK + v * WEIGHT_VOLUME, 3)


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT FORMATTING
# ─────────────────────────────────────────────────────────────────────────────

def build_result(ticker: str, df: pd.DataFrame, company_name: str = "") -> dict:
    row   = df.iloc[-1]
    price = round(float(row["Close"]), 2)
    high  = round(float(row["high20"]), 2)
    ma50  = round(float(row["ma50"]),  2)
    rsi   = round(float(row["rsi"]),   1)
    vol_r = round(float(row["Volume"]) / float(row["vol_avg20"]), 2)

    depth_pct = round((high - price) / high * 100, 1)

    # Entry zone: ±0.5% of current close
    entry_low  = round(price * 0.995, 2)
    entry_high = round(price * 1.005, 2)

    # Stop loss: lowest low of last 10 bars (recent swing low)
    stop = round(float(df["Low"].iloc[-10:].min()), 2)

    # Target: prior 20-day high (breakout level)
    target = high

    # R:R
    risk   = round(price - stop, 2)
    reward = round(target - price, 2)
    rr     = round(reward / risk, 2) if risk > 0 else 0.0

    t_score = score_trend(row)
    p_score = score_pullback(row)
    v_score = score_volume(row)
    score   = total_score(row)

    reasoning = (
        f"{ticker} is {depth_pct}% below its 20-day high with RSI at {rsi}, "
        f"offering a controlled pullback into an uptrend (price above 50 MA at {ma50}). "
        f"Volume spiked {vol_r}× above average on a bullish candle, confirming institutional interest."
    )

    return {
        "ticker":            ticker,
        "company_name":      company_name or ticker,
        "score":             score,
        "score_breakdown": {
            "trend_strength":    t_score,
            "pullback_quality":  p_score,
            "volume_confirm":    v_score,
        },
        "setup":             "Momentum Pullback",
        "price":             price,
        "entry_zone":        {"low": entry_low, "high": entry_high},
        "stop_loss":         stop,
        "target":            target,
        "risk_reward":       rr,
        "indicators": {
            "rsi":              rsi,
            "ma50":             ma50,
            "ma200":            round(float(row["ma200"]), 2),
            "high_20d":         high,
            "pullback_pct":     depth_pct,
            "volume_ratio":     vol_r,
        },
        "reasoning":         reasoning,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def run():
    log.info("═" * 60)
    log.info("S&P 500 Swing Scanner — starting")
    log.info(f"Scan date: {date.today().isoformat()}")
    log.info("═" * 60)

    tickers, names = get_sp500_tickers()
    ohlcv    = fetch_ohlcv(tickers)

    candidates = []
    errors     = 0

    for ticker, df in ohlcv.items():
        try:
            enriched = enrich(df)
            if enriched is None:
                continue

            last = enriched.iloc[-1]
            if not passes_filters(last):
                continue

            result = build_result(ticker, enriched, company_name=names.get(ticker, ""))
            if result["score"] < MIN_SCORE:
                continue  # skip low-quality setups
            candidates.append(result)

        except Exception as e:
            log.debug(f"{ticker}: skipped — {e}")
            errors += 1

    log.info(f"Candidates passing all filters: {len(candidates)}")
    log.info(f"Tickers skipped due to errors:  {errors}")

    # Sort by total score descending, take top N
    candidates.sort(key=lambda x: x["score"], reverse=True)
    top = candidates[:TOP_N]

    output = {
        "scan_date":     date.today().isoformat(),
        "scan_time_utc": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "universe":      f"S&P 500 ({len(tickers)} tickers)",
        "candidates_found": len(candidates),
        "strategy": {
            "name":        "Momentum Pullback",
            "timeframe":   "Daily",
            "hold_period": "2–4 weeks",
            "filters": {
                "trend":    "Price > 50 MA > 200 MA",
                "pullback": f"3–8% below 20-day high",
                "rsi":      f"RSI {RSI_LOW}–{RSI_HIGH} (tightened)",
                "volume":   f"Volume > {VOLUME_MULT}× 20-day avg",
                "candle":   "Close > Open (bullish)",
                "min_score": f"Score ≥ {MIN_SCORE}",
            },
            "weights": {
                "trend_strength":   f"{int(WEIGHT_TREND * 100)}%",
                "pullback_quality": f"{int(WEIGHT_PULLBACK * 100)}%",
                "volume_confirm":   f"{int(WEIGHT_VOLUME * 100)}%",
            },
        },
        "top_setups": top,
    }

    with open("results.json", "w") as f:
        json.dump(output, f, indent=2)

    log.info(f"results.json written — {len(top)} setups.")
    log.info("Top 5 tickers:")
    for r in top[:5]:
        log.info(
            f"  {r['ticker']:6s}  score={r['score']:.3f}  "
            f"price={r['price']}  rsi={r['indicators']['rsi']}  "
            f"pullback={r['indicators']['pullback_pct']}%"
        )
    log.info("Done.")


if __name__ == "__main__":
    run()
