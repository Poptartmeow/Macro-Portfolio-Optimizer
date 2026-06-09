"""
Macro Portfolio Optimizer — PMI Pipeline
Pulls Purchasing Managers Index (PMI) data for each region in the asset universe.

PMI is used as a monthly proxy for quarterly real GDP, per sponsor (Greg) guidance.
Greg's reasoning: PMI is monthly (matches optimizer frequency), never revised
(clean for backtesting), forward-looking (new orders captured), and more timely
than GDP.

Regions to cover (matching equity buckets):
  - US                  -> ISM Manufacturing PMI (this script)
  - Eurozone            -> S&P Global Eurozone PMI (TODO)
  - Developed ex-US     -> Japan, UK, Canada, Australia (TODO)
  - Emerging Markets    -> China, India, Brazil, Mexico, Korea, Taiwan (TODO)

US source: ISM Manufacturing PMI (headline composite, seasonally adjusted)
  - Data acquired manually from investing.com because no free programmatic
    source exists with full history (FRED removed ISM data, S&P Global is
    paywalled, DBnomics only goes back to 2020, forecasts.org is stale).

  - Refresh procedure (manual, monthly):
       1. Open https://www.investing.com/economic-calendar/ism-manufacturing-pmi-173
       2. Scroll to the Historical Data table and click "Show More" until rows
          go back to at least 2007.
       3. Select all rows including the header row, copy.
       4. Paste into data/raw/PMI_Manufacturing_US.txt (overwrite).
       5. Re-run this script:  python -m macro_portfolio.pipelines.pmi_manufacturing
       PMI is released first business day of each month, so refresh monthly
       (only need to add the newest row, but easiest is just to re-grab full table).

Note on data convention: investing.com lists rows by RELEASE DATE, but ISM PMI
released on (e.g.) June 1, 2026 describes the May 2026 reference period. This
script extracts the reference month from the parenthetical "(May)" annotation
and keys the output by reference month, matching the convention used by FRED
and the rest of the team's macro data.

Requirements:
    pip install pandas
"""

import os
import re
import pandas as pd
from datetime import datetime

from macro_portfolio import paths

# Config

START_DATE = "2007-01-01"
END_DATE = datetime.today().strftime("%Y-%m-%d")

OUTPUT_DIR = str(paths.DATA_DIR)   # paths.py creates these dirs on import
RAW_DIR = str(paths.RAW_DIR)


# US: ISM Manufacturing PMI from investing.com text dump

US_PMI_RAW_PATH = os.path.join(RAW_DIR, "PMI_Manufacturing_US.txt")

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# Matches lines like:
#   "Jun 01, 2026 (May)\t10:00\t52.7\t53.1\t..."
#   "Mar 03, 2008\t10:00\t48.3\t48.0\t..."   (older rows omit the parenthetical)
ROW_PATTERN = re.compile(
    r"^(\w{3})\s+(\d{1,2}),\s+(\d{4})(?:\s+\((\w{3})\))?\s*\t[\d:]+\s*\t([\d.]*)",
    re.MULTILINE,
)


def parse_reference_date(
    release_mo: str,
    release_year: str,
    parenthetical_ref_mo: str,
) -> pd.Timestamp:
    """
    Map a release date to its reference month.

    ISM PMI released in June 2026 describes May 2026, etc. The investing.com
    rows annotate this with a parenthetical like "(May)" when available; for
    older rows (pre-Feb 2008) the parenthetical is missing and we infer the
    reference month as release_month - 1. Correctly adjusts the data for our models
    """
    release_month_num = MONTH_MAP[release_mo]
    release_year_num = int(release_year)

    if parenthetical_ref_mo:
        ref_month_num = MONTH_MAP[parenthetical_ref_mo]
        # If reference month is later in the calendar than the release month,
        # the reference year is the prior year (e.g. Jan 2026 release for Dec 2025 ref).
        if ref_month_num > release_month_num:
            ref_year = release_year_num - 1
        else:
            ref_year = release_year_num
    else:
        # Inferred case: ref month = release month - 1
        if release_month_num == 1:
            ref_month_num = 12
            ref_year = release_year_num - 1
        else:
            ref_month_num = release_month_num - 1
            ref_year = release_year_num

    return pd.Timestamp(year=ref_year, month=ref_month_num, day=1)


def fetch_us_pmi(path: str = US_PMI_RAW_PATH) -> pd.DataFrame:
    """
    Parse the investing.com PMI table dump and return a clean DataFrame.

    Returns a DataFrame with columns:
        date    : datetime (reference month, day=1)
        PMI_US  : float, ISM Manufacturing PMI headline value
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Could not find raw PMI text file at: {path}\n"
            f"See the module docstring for how to grab it from investing.com."
        )

    print(f"Reading US ISM Manufacturing PMI from: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    matches = ROW_PATTERN.findall(raw)
    print(f"  Extracted {len(matches)} release rows from raw text")

    records = []
    skipped_empty = 0
    for release_mo, _release_day, release_year, parenthetical_ref_mo, actual in matches:
        # Skip rows where the release hasn't happened yet (Actual is blank)
        if actual == "":
            skipped_empty += 1
            continue

        ref_date = parse_reference_date(release_mo, release_year, parenthetical_ref_mo)
        records.append({"date": ref_date, "PMI_US": float(actual)})

    if skipped_empty:
        print(f"  Skipped {skipped_empty} row(s) with no Actual value (future releases)")

    df = pd.DataFrame(records).sort_values("date").reset_index(drop=True)
    df = df.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)

    return df


def filter_window(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """Trim the dataframe to the project's analysis window."""
    mask = (df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))
    return df.loc[mask].reset_index(drop=True)


def check_for_gaps(df: pd.DataFrame) -> None:
    """Warn if the monthly series has any missing months."""
    expected = pd.date_range(df["date"].min(), df["date"].max(), freq="MS")
    missing = sorted(set(expected) - set(df["date"]))
    if missing:
        print(f"  WARNING: {len(missing)} missing month(s) detected:")
        for m in missing:
            print(f"    {m.date()}")
    else:
        print("  No gaps - monthly series is continuous.")


# Main

def main():
    # 1. Parse raw text file
    us_pmi_full = fetch_us_pmi()
    print(
        f"US PMI: {len(us_pmi_full)} observations, "
        f"{us_pmi_full['date'].min().date()} to {us_pmi_full['date'].max().date()}"
    )

    # 2. Filter to project window
    us_pmi = filter_window(us_pmi_full, START_DATE, END_DATE)
    print(f"After windowing to {START_DATE}-{END_DATE}: {len(us_pmi)} observations")

    # 3. Gap check
    check_for_gaps(us_pmi)

    # 4. Write full history (unwindowed, for reference)
    full_path = os.path.join(OUTPUT_DIR, "PMI_Manufacturing_US_full.csv")
    us_pmi_full.to_csv(full_path, index=False)
    print(f"Saved full history: {full_path}")

    # 5. Write windowed file (feeds into the optimizer's macro panel)
    windowed_path = os.path.join(OUTPUT_DIR, "PMI_Manufacturing_US.csv")
    us_pmi.to_csv(windowed_path, index=False)
    print(f"Saved windowed series: {windowed_path}")

    # 6. Sanity checks against known historical reference points
    print("\n--- Sanity checks ---")
    checks = [
        ("2008-12-01", 32.4, "GFC trough"),
        ("2020-04-01", 41.5, "COVID trough"),
        ("2021-03-01", 64.7, "Post-COVID peak"),
    ]
    for date_str, expected, label in checks:
        rows = us_pmi[us_pmi["date"] == pd.Timestamp(date_str)]
        if len(rows) == 0:
            print(f"  {label} ({date_str}): NOT FOUND in data")
        else:
            actual_val = rows["PMI_US"].iloc[0]
            status = "OK" if abs(actual_val - expected) < 0.1 else "MISMATCH"
            print(f"  {label} ({date_str}): {actual_val} (expected ~{expected}) [{status}]")

    print("\nFirst 3 rows:")
    print(us_pmi.head(3).to_string(index=False))
    print("\nLast 3 rows:")
    print(us_pmi.tail(3).to_string(index=False))


if __name__ == "__main__":
    main()
