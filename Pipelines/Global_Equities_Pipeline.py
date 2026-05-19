"""
Macro Portfolio Optimizer — ETL Pipeline
Pulls price history, fundamentals, and macro indicators for Global Equity ETFs.
 
Data Sources:
  - yfinance:  price/return history, ETF fundamentals
  - FRED API:  macro indicators (GDP, CPI, Fed Funds Rate, 10Y yield)
 
Requirements:
  pip install yfinance pandas requests python-dotenv
"""
 
import os
import json
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
 
load_dotenv()
 
# ── Config ────────────────────────────────────────────────────────────────────
 
ETFS = ["VGK", "EFA", "VEA", "EWC", "IEMG", "VWO", "EEM"]
 
START_DATE = "2010-01-01"
END_DATE   = datetime.today().strftime("%Y-%m-%d")
 
FRED_API_KEY = os.getenv("FRED_API_KEY")  # set in .env file
 
# Key FRED series IDs
FRED_SERIES = {
    "GDP_Growth":       "A191RL1Q225SBEA",  # Real GDP growth rate (quarterly)
    "CPI_YoY":          "CPIAUCSL",          # CPI (monthly)
    "Fed_Funds_Rate":   "FEDFUNDS",          # Federal funds rate (monthly)
    "10Y_Treasury":     "GS10",              # 10-year Treasury yield (monthly)
    "Unemployment":     "UNRATE",            # Unemployment rate (monthly)
    "VIX":              "VIXCLS",            # CBOE VIX (daily)
}
 
OUTPUT_DIR = "data"
os.makedirs(OUTPUT_DIR, exist_ok=True)
 
 
# ── 1. Price & Return History (yfinance) ──────────────────────────────────────
 
def fetch_price_history(tickers: list, start: str, end: str) -> pd.DataFrame:
    """Download adjusted close prices for all ETFs."""
    print(f"Fetching price history for: {tickers}")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    prices = raw["Close"]
    prices.index = pd.to_datetime(prices.index)
    return prices
 
 
def compute_returns(prices: pd.DataFrame) -> dict:
    """Compute daily, monthly, and annual returns."""
    daily   = prices.pct_change().dropna()
    monthly = prices.resample("ME").last().pct_change().dropna()
    annual  = prices.resample("YE").last().pct_change().dropna()
    return {"daily": daily, "monthly": monthly, "annual": annual}
 
 
# ── 2. ETF Fundamentals (yfinance) ────────────────────────────────────────────
 
FUNDAMENTAL_KEYS = [
    "longName", "category", "totalAssets", "trailingPE",
    "trailingEps", "yield", "beta", "fiftyTwoWeekHigh",
    "fiftyTwoWeekLow", "navPrice", "ytdReturn",
]
 
def fetch_fundamentals(tickers: list) -> pd.DataFrame:
    """Pull ETF info/fundamentals from yfinance."""
    print("Fetching ETF fundamentals...")
    records = []
    for ticker in tickers:
        info = yf.Ticker(ticker).info
        record = {"ticker": ticker}
        for key in FUNDAMENTAL_KEYS:
            record[key] = info.get(key, None)
        records.append(record)
    return pd.DataFrame(records).set_index("ticker")
 
 
# ── 3. Macro Indicators (FRED API) ────────────────────────────────────────────
 
def fetch_fred_series(series_id: str, api_key: str) -> pd.Series:
    """Fetch a single FRED time series."""
    url = (
        f"https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&api_key={api_key}&file_type=json"
        f"&observation_start={START_DATE}"
    )
    resp = requests.get(url)
    resp.raise_for_status()
    observations = resp.json()["observations"]
    df = pd.DataFrame(observations)[["date", "value"]]
    df["date"]  = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.set_index("date")["value"].rename(series_id)
 
 
def fetch_all_macro(series_dict: dict, api_key: str) -> pd.DataFrame:
    """Fetch and combine all FRED macro series."""
    if not api_key:
        print("WARNING: No FRED_API_KEY found. Skipping macro data.")
        print("  → Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html")
        print("  → Add FRED_API_KEY=your_key to a .env file in the project root.")
        return pd.DataFrame()
 
    print("Fetching macro indicators from FRED...")
    frames = {}
    for name, series_id in series_dict.items():
        try:
            frames[name] = fetch_fred_series(series_id, api_key)
            print(f"  ✓ {name}")
        except Exception as e:
            print(f"  ✗ {name}: {e}")
 
    return pd.DataFrame(frames)
 
 
# ── 4. Save Outputs ───────────────────────────────────────────────────────────
 
def save_data(prices, returns, fundamentals, macro):
    prices.to_csv(f"{OUTPUT_DIR}/prices.csv")
    returns["daily"].to_csv(f"{OUTPUT_DIR}/returns_daily.csv")
    returns["monthly"].to_csv(f"{OUTPUT_DIR}/returns_monthly.csv")
    returns["annual"].to_csv(f"{OUTPUT_DIR}/returns_annual.csv")
    fundamentals.to_csv(f"{OUTPUT_DIR}/fundamentals.csv")
    if not macro.empty:
        macro.to_csv(f"{OUTPUT_DIR}/macro_indicators.csv")
    print(f"\nAll data saved to /{OUTPUT_DIR}/")
 
 
# ── Main ──────────────────────────────────────────────────────────────────────
 
if __name__ == "__main__":
    prices       = fetch_price_history(ETFS, START_DATE, END_DATE)
    returns      = compute_returns(prices)
    fundamentals = fetch_fundamentals(ETFS)
    macro        = fetch_all_macro(FRED_SERIES, FRED_API_KEY)
 
    save_data(prices, returns, fundamentals, macro)
 
    print("\nSample — Fundamentals:")
    print(fundamentals[["longName", "totalAssets", "trailingPE", "yield", "ytdReturn"]])
 
    if not macro.empty:
        print("\nSample — Macro Indicators (last 5 rows):")
        print(macro.tail())
 