"""
S&P 500 Swing Trading Scanner — v3
Momentum Pullback Strategy | Daily Timeframe
Runs once per day, outputs top 10 setups to results.json
"""

import io
import json
import logging
import os
import shutil
import urllib.request
import warnings
from datetime import datetime, date, timezone, timedelta
from typing import Optional

import numpy as np
import pandas as pd
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

# ── Strategy Parameters ───────────────────────────────────────────────────────

PULLBACK_MIN  = 0.03   # 3% below 20-day high  (min pullback)
PULLBACK_MAX  = 0.08   # 8% below 20-day high  (max pullback)
RSI_LOW       = 40
RSI_HIGH      = 60
VOLUME_MULT   = 1.3    # today's vol > 1.3× 20-day avg vol
TOP_N         = 10
LOOKBACK_DAYS = 300    # calendar days of history to fetch

# ── Position Sizing & Risk Parameters ────────────────────────────────────────

PORTFOLIO_CAPITAL    = 10000   # account size in dollars — NEVER reset this
RISK_PER_TRADE_PCT   = 0.01    # 1% risk per trade
MAX_POSITION_PCT     = 0.25    # max 25% of capital per position
SECTOR_CAP           = 3       # max setups per sector in top-10 output
ATR_PERIOD           = 14
ATR_STOP_MULT        = 2.5     # ATR multiplier for stop
EARNINGS_BUFFER_DAYS = 7       # skip stocks with earnings within 7 days
EARNINGS_FILE        = "earnings.json"
SECTORS_FILE         = "sectors.json"
REGIME_SIZING        = {"bull": 1.0, "neutral": 0.75, "bear": 0.5}


# ─────────────────────────────────────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────────────────────────────────────

def get_sp500_tickers() -> tuple[list[str], dict[str, str], dict[str, str]]:
    """
    Scrape S&P 500 tickers, company names, and GICS sectors from Wikipedia.
    Returns (tickers, names, sectors).
    Saves sectors to SECTORS_FILE.
    """
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

        # Attempt to extract GICS Sector column
        sectors: dict[str, str] = {}
        sector_col = None
        for col in df.columns:
            if "sector" in col.lower() or "gics" in col.lower():
                sector_col = col
                break
        if sector_col is not None:
            sectors = {
                s.replace(".", "-"): str(sec)
                for s, sec in zip(raw_symbols, df[sector_col].tolist())
            }
        else:
            log.warning("GICS Sector column not found in Wikipedia table; sectors will be empty.")

        # Persist sectors to file
        try:
            with open(SECTORS_FILE, "w") as f:
                json.dump(sectors, f, indent=2)
            log.info(f"Sectors saved to {SECTORS_FILE}.")
        except Exception as e:
            log.warning(f"Could not save {SECTORS_FILE}: {e}")

        log.info(f"Fetched {len(tickers)} S&P 500 tickers from Wikipedia.")
        return tickers, names, sectors
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
# MARKET REGIME
# ─────────────────────────────────────────────────────────────────────────────

def get_market_regime() -> str:
    """
    Determine the current market regime using SPY.
    Fetches 1y daily data, computes 200-day MA and 63-day return.
    Bull:    price > ma200 AND 63d return > 0
    Bear:    price < ma200 AND 63d return < -0.05
    Neutral: anything else
    Returns "bull", "neutral", or "bear". Falls back to "neutral" on any error.
    """
    try:
        spy = yf.download("SPY", period="1y", interval="1d", auto_adjust=True, progress=False)
        if spy is None or len(spy) < 63:
            log.warning("SPY data insufficient for regime detection; defaulting to neutral.")
            return "neutral"

        close = spy["Close"].squeeze()
        ma200 = close.rolling(window=200, min_periods=50).mean()
        last_price = float(close.iloc[-1])
        last_ma200 = float(ma200.iloc[-1])

        ret_63d = (float(close.iloc[-1]) - float(close.iloc[-63])) / float(close.iloc[-63])

        if last_price > last_ma200 and ret_63d > 0:
            regime = "bull"
        elif last_price < last_ma200 and ret_63d < -0.05:
            regime = "bear"
        else:
            regime = "neutral"

        log.info(f"Market regime: {regime} (SPY={last_price:.2f}, MA200={last_ma200:.2f}, 63d_ret={ret_63d:.2%})")
        return regime
    except Exception as e:
        log.warning(f"get_market_regime failed: {e}; defaulting to neutral.")
        return "neutral"


# ─────────────────────────────────────────────────────────────────────────────
# EARNINGS FILTER
# ─────────────────────────────────────────────────────────────────────────────

def load_earnings() -> dict[str, str]:
    """
    Load upcoming earnings dates from EARNINGS_FILE ({ticker: "YYYY-MM-DD"}).
    Returns {} if file doesn't exist or is older than 7 days.
    """
    if not os.path.exists(EARNINGS_FILE):
        return {}
    try:
        mtime = os.path.getmtime(EARNINGS_FILE)
        age_days = (datetime.now().timestamp() - mtime) / 86400
        if age_days > 7:
            log.info(f"{EARNINGS_FILE} is {age_days:.1f} days old; ignoring stale earnings data.")
            return {}
        with open(EARNINGS_FILE, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        log.info(f"Loaded earnings for {len(data)} tickers from {EARNINGS_FILE}.")
        return data
    except Exception as e:
        log.warning(f"Could not load {EARNINGS_FILE}: {e}")
        return {}


def has_upcoming_earnings(ticker: str, earnings: dict[str, str]) -> bool:
    """
    Returns True if ticker has earnings within EARNINGS_BUFFER_DAYS calendar days
    (including today, up to and including EARNINGS_BUFFER_DAYS ahead).
    """
    if ticker not in earnings:
        return False
    try:
        earn_date = date.fromisoformat(earnings[ticker])
        days_away = (earn_date - date.today()).days
        return 0 <= days_away <= EARNINGS_BUFFER_DAYS
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# INDICATORS
# ─────────────────────────────────────────────────────────────────────────────

def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    """
    Average True Range using EWM.
    True Range = max(high-low, abs(high-prev_close), abs(low-prev_close))
    """
    high       = df["High"]
    low        = df["Low"]
    prev_close = df["Close"].shift(1)

    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low  - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = tr.ewm(span=period, min_periods=period, adjust=False).mean()
    return atr


def enrich(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Add all indicator columns. Returns None if data is insufficient."""
    try:
        df = df.copy()
        df["ma50"]      = sma(df["Close"], 50)
        df["ma200"]     = sma(df["Close"], 200)
        df["rsi"]       = compute_rsi(df["Close"], 14)
        df["high20"]    = df["High"].rolling(20).max()
        df["vol_avg20"] = df["Volume"].rolling(20).mean()
        df["atr"]       = compute_atr(df)

        # Drop rows where any key indicator is NaN
        df.dropna(
            subset=["ma50", "ma200", "rsi", "high20", "vol_avg20", "atr"],
            inplace=True,
        )

        return df if len(df) >= 10 else None
    except Exception as e:
        log.debug(f"enrich failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# SCREENING — filter stocks that pass all hard rules
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
    if price <= ma50:   return False
    if ma50 <= ma200:   return False

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
# SCORING — 0–10 per dimension, then weighted sum
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

def build_result(
    ticker: str,
    df: pd.DataFrame,
    company_name: str = "",
    sector: str = "",
    regime: str = "neutral",
) -> dict:
    """Build the full result dict for a single ticker."""
    row   = df.iloc[-1]
    price = round(float(row["Close"]), 2)
    high  = round(float(row["high20"]), 2)
    ma50  = round(float(row["ma50"]),  2)
    ma200 = round(float(row["ma200"]), 2)
    rsi   = round(float(row["rsi"]),   1)
    atr   = round(float(row["atr"]),   2)
    vol_r = round(float(row["Volume"]) / float(row["vol_avg20"]), 2)

    depth_pct = round((high - price) / high * 100, 1)

    # Entry zone: ±0.5% of current close
    entry_low  = round(price * 0.995, 2)
    entry_high = round(price * 1.005, 2)

    # Stop loss options
    swing_stop = round(float(df["Low"].iloc[-10:].min()), 2)
    atr_stop   = round(price - atr * ATR_STOP_MULT, 2)

    # Use the wider (lower) stop for safety
    stop_loss   = min(swing_stop, atr_stop)
    stop_method = "atr" if atr_stop < swing_stop else "swing"

    # Target: prior 20-day high (breakout level)
    target = high

    # R:R
    risk   = round(price - stop_loss, 2)
    reward = round(target - price, 2)
    rr     = round(reward / risk, 2) if risk > 0 else 0.0

    # Position sizing
    sizing_factor = REGIME_SIZING.get(regime, 0.75)
    dollar_risk   = PORTFOLIO_CAPITAL * RISK_PER_TRADE_PCT * sizing_factor
    if risk > 0:
        raw_shares      = int(dollar_risk / risk)
        max_shares      = int(PORTFOLIO_CAPITAL * MAX_POSITION_PCT / price)
        suggested_shares = min(raw_shares, max_shares)
    else:
        suggested_shares = 0
    position_value = round(suggested_shares * price, 2)

    position_sizing = {
        "suggested_shares":   suggested_shares,
        "dollar_risk":        round(dollar_risk, 2),
        "position_value":     position_value,
        "regime_size_applied": regime,
    }

    # Exit plan
    exit_plan = {
        "tiers": [
            {
                "label":    "T1 — scale out",
                "price":    round(price + reward * 0.5, 2),
                "fraction": 0.5,
            },
            {
                "label":    "T2 — target",
                "price":    target,
                "fraction": 0.5,
            },
        ],
        "runner": {
            "fraction":           0.0,
            "trail_atr_multiple": 2.0,
        },
    }

    # Scoring
    t_score = score_trend(row)
    p_score = score_pullback(row)
    v_score = score_volume(row)
    score   = total_score(row)

    reasoning = (
        f"{ticker} is {depth_pct}% below its 20-day high with RSI at {rsi}, "
        f"offering a controlled pullback into an uptrend (price above 50 MA at {ma50}). "
        f"Volume spiked {vol_r}x above average on a bullish candle, confirming institutional interest. "
        f"Stop set via {stop_method} method at {stop_loss} "
        f"(ATR stop: {atr_stop}, swing low: {swing_stop}). "
        f"Market regime: {regime} — position sized to {sizing_factor:.0%} of full risk."
    )

    return {
        "ticker":          ticker,
        "company_name":    company_name or ticker,
        "sector":          sector or "Unknown",
        "score":           score,
        "score_breakdown": {
            "trend_strength":   t_score,
            "pullback_quality": p_score,
            "volume_confirm":   v_score,
        },
        "setup":         "Momentum Pullback",
        "price":         price,
        "entry_zone":    {"low": entry_low, "high": entry_high},
        "stop_loss":     stop_loss,
        "target":        target,
        "risk_reward":   rr,
        "stop_method":   stop_method,
        "swing_stop":    swing_stop,
        "atr_stop":      atr_stop,
        "position_sizing": position_sizing,
        "exit_plan":       exit_plan,
        "indicators": {
            "rsi":          rsi,
            "ma50":         ma50,
            "ma200":        ma200,
            "atr":          atr,
            "high_20d":     high,
            "pullback_pct": depth_pct,
            "volume_ratio": vol_r,
        },
        "regime":         regime,
        "sizing_factor":  sizing_factor,
        "reasoning":      reasoning,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def run():
    log.info("=" * 60)
    log.info("S&P 500 Swing Scanner v3 — starting")
    log.info(f"Scan date: {date.today().isoformat()}")
    log.info("=" * 60)

    # 1. Back up previous results
    if os.path.exists("results.json"):
        try:
            shutil.copy2("results.json", "prev_results.json")
            log.info("Backed up results.json → prev_results.json")
        except Exception as e:
            log.warning(f"Could not back up results.json: {e}")

    # 2. Market regime
    regime = get_market_regime()

    # 3. Fetch tickers (now returns 3 values)
    tickers, names, sectors = get_sp500_tickers()

    # 4. Load earnings data
    earnings = load_earnings()

    # 5. Fetch OHLCV
    ohlcv = fetch_ohlcv(tickers)

    candidates      = []
    errors          = 0
    earnings_skipped = 0

    # 6. Main screening loop
    for ticker, df in ohlcv.items():
        try:
            # Skip earnings risk
            if has_upcoming_earnings(ticker, earnings):
                earnings_skipped += 1
                log.debug(f"{ticker}: skipped — earnings within {EARNINGS_BUFFER_DAYS} days")
                continue

            enriched = enrich(df)
            if enriched is None:
                continue

            last = enriched.iloc[-1]
            if not passes_filters(last):
                continue

            result = build_result(
                ticker,
                enriched,
                company_name=names.get(ticker, ""),
                sector=sectors.get(ticker, "Unknown"),
                regime=regime,
            )
            candidates.append(result)

        except Exception as e:
            log.debug(f"{ticker}: skipped — {e}")
            errors += 1

    log.info(f"Candidates passing all filters: {len(candidates)}")
    log.info(f"Earnings skipped:               {earnings_skipped}")
    log.info(f"Tickers skipped due to errors:  {errors}")

    # 7. Sort by score descending
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # 8. Apply sector cap — iterate sorted list, allow at most SECTOR_CAP per sector
    sector_counts: dict[str, int] = {}
    top: list[dict] = []
    for candidate in candidates:
        s = candidate.get("sector", "Unknown")
        if sector_counts.get(s, 0) >= SECTOR_CAP:
            continue
        sector_counts[s] = sector_counts.get(s, 0) + 1
        top.append(candidate)
        if len(top) >= TOP_N:
            break

    # 9. Sector breakdown for top setups
    sector_breakdown: dict[str, int] = {}
    for setup in top:
        s = setup.get("sector", "Unknown")
        sector_breakdown[s] = sector_breakdown.get(s, 0) + 1

    output = {
        "scan_date":        date.today().isoformat(),
        "scan_time_utc":    datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "market_regime":    regime,
        "universe":         f"S&P 500 ({len(tickers)} tickers)",
        "candidates_found": len(candidates),
        "earnings_skipped": earnings_skipped,
        "sector_breakdown": sector_breakdown,
        "strategy": {
            "name":        "Momentum Pullback",
            "timeframe":   "Daily",
            "hold_period": "2–4 weeks",
            "filters": {
                "trend":    "Price > 50 MA > 200 MA",
                "pullback": f"3–8% below 20-day high",
                "rsi":      f"RSI {RSI_LOW}–{RSI_HIGH}",
                "volume":   f"Volume > {VOLUME_MULT}x 20-day avg",
                "candle":   "Close > Open (bullish)",
            },
            "weights": {
                "trend_strength":   f"{int(WEIGHT_TREND * 100)}%",
                "pullback_quality": f"{int(WEIGHT_PULLBACK * 100)}%",
                "volume_confirm":   f"{int(WEIGHT_VOLUME * 100)}%",
            },
            "risk_management": {
                "portfolio_capital":   PORTFOLIO_CAPITAL,
                "risk_per_trade_pct":  f"{int(RISK_PER_TRADE_PCT * 100)}%",
                "max_position_pct":    f"{int(MAX_POSITION_PCT * 100)}%",
                "atr_stop_multiplier": ATR_STOP_MULT,
                "sector_cap":          SECTOR_CAP,
                "regime_sizing":       REGIME_SIZING,
            },
        },
        "top_setups": top,
    }

    # 10. Write results.json
    with open("results.json", "w") as f:
        json.dump(output, f, indent=2)

    # 11. Log summary
    log.info(f"results.json written — {len(top)} setups.")
    log.info(f"Sector breakdown: {sector_breakdown}")
    log.info("Top 5 tickers:")
    for r in top[:5]:
        log.info(
            f"  {r['ticker']:6s}  score={r['score']:.3f}  "
            f"price={r['price']}  rsi={r['indicators']['rsi']}  "
            f"pullback={r['indicators']['pullback_pct']}%  "
            f"stop={r['stop_loss']} ({r['stop_method']})  "
            f"sector={r['sector']}"
        )
    log.info("Done.")


if __name__ == "__main__":
    run()
