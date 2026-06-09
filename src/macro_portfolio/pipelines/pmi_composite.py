"""
Macro Portfolio Optimizer — PMI Composite Pipeline
US ISM Composite PMI — weighted average of Manufacturing and Non-Manufacturing.

This pipeline merges the outputs of:
  - pmi_manufacturing.py    → data/PMI_Manufacturing_US.csv    (column: PMI_US)
  - pmi_nonmanufacturing.py → data/PMI_NonManufacturing_US.csv (column: PMI_NM_US)

into a single composite series (column: PMI_Composite_US).

Composite weighting methodology:
  US GDP is roughly 80% services / 20% goods-producing. We use the standard
  ISM composite weights to reflect actual economic composition:
    - Non-Manufacturing (Services):  weight = 0.80
    - Manufacturing:                 weight = 0.20

  PMI_Composite_US = 0.20 * PMI_US + 0.80 * PMI_NM_US

  When one series is missing for a given month (e.g. a future release not yet
  available), the composite falls back to the available series rather than
  dropping the row entirely. The 'source' column records which inputs were used.

Output files:
  - data/PMI_Composite_US.csv       — windowed series fed into the optimizer
  - data/PMI_Composite_US_full.csv  — full unwindowed history for reference

Both files contain columns:
    date              : datetime (reference month, day=1)
    PMI_US            : float, ISM Manufacturing PMI (carried through for reference)
    PMI_NM_US         : float, ISM Non-Manufacturing PMI (carried through for reference)
    PMI_Composite_US  : float, weighted composite
    source            : str, one of "both" | "manufacturing_only" | "nonmanufacturing_only"

Run order: always run pmi_manufacturing.py and pmi_nonmanufacturing.py before this
one, then:  python -m macro_portfolio.pipelines.pmi_composite

Requirements:
    pip install pandas
"""

import os
import pandas as pd
from datetime import datetime

from macro_portfolio import paths

# Config

START_DATE = "2007-01-01"
END_DATE = datetime.today().strftime("%Y-%m-%d")

OUTPUT_DIR = str(paths.DATA_DIR)   # paths.py creates this dir on import

MFG_PATH    = os.path.join(OUTPUT_DIR, "PMI_Manufacturing_US.csv")
NM_PATH     = os.path.join(OUTPUT_DIR, "PMI_NonManufacturing_US.csv")
MFG_FULL    = os.path.join(OUTPUT_DIR, "PMI_Manufacturing_US_full.csv")
NM_FULL     = os.path.join(OUTPUT_DIR, "PMI_NonManufacturing_US_full.csv")

# ISM composite weights (services-heavy, matching US GDP composition)
W_MFG = 0.20   # Manufacturing weight
W_NM  = 0.80   # Non-Manufacturing (Services) weight


def load_series(path: str, col: str) -> pd.DataFrame:
    """Load a PMI CSV and parse the date column."""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Could not find {path}.\n"
            f"Run the upstream pipeline first to generate it."
        )
    df = pd.read_csv(path, parse_dates=["date"])
    df = df[["date", col]].copy()
    return df


def build_composite(mfg: pd.DataFrame, nm: pd.DataFrame) -> pd.DataFrame:
    """
    Outer-join Manufacturing and Non-Manufacturing on reference date and
    compute the weighted composite. Records the data source for each row.
    """
    merged = pd.merge(mfg, nm, on="date", how="outer").sort_values("date").reset_index(drop=True)

    rows = []
    for _, row in merged.iterrows():
        has_mfg = pd.notna(row.get("PMI_US"))
        has_nm  = pd.notna(row.get("PMI_NM_US"))

        if has_mfg and has_nm:
            composite = W_MFG * row["PMI_US"] + W_NM * row["PMI_NM_US"]
            source = "both"
        elif has_mfg:
            composite = row["PMI_US"]
            source = "manufacturing_only"
        elif has_nm:
            composite = row["PMI_NM_US"]
            source = "nonmanufacturing_only"
        else:
            composite = float("nan")
            source = "none"

        rows.append({
            "date":             row["date"],
            "PMI_US":           row.get("PMI_US"),
            "PMI_NM_US":        row.get("PMI_NM_US"),
            "PMI_Composite_US": round(composite, 2) if pd.notna(composite) else float("nan"),
            "source":           source,
        })

    return pd.DataFrame(rows)


def filter_window(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """Trim the dataframe to the project's analysis window."""
    mask = (df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))
    return df.loc[mask].reset_index(drop=True)


def check_for_gaps(df: pd.DataFrame) -> None:
    """Warn if the monthly composite has any missing months."""
    valid = df.dropna(subset=["PMI_Composite_US"])
    expected = pd.date_range(valid["date"].min(), valid["date"].max(), freq="MS")
    missing = sorted(set(expected) - set(valid["date"]))
    if missing:
        print(f"  WARNING: {len(missing)} missing month(s) in composite:")
        for m in missing:
            print(f"    {m.date()}")
    else:
        print("  No gaps - monthly composite is continuous.")

    partial = df[df["source"] != "both"]
    if not partial.empty:
        print(f"  WARNING: {len(partial)} row(s) built from a single series (not both):")
        print(partial[["date", "source"]].to_string(index=False))


# Main

def main():
    print("Loading Manufacturing PMI...")
    mfg_full = load_series(MFG_FULL if os.path.exists(MFG_FULL) else MFG_PATH, "PMI_US")
    print(f"  {len(mfg_full)} observations, {mfg_full['date'].min().date()} to {mfg_full['date'].max().date()}")

    print("Loading Non-Manufacturing PMI...")
    nm_full = load_series(NM_FULL if os.path.exists(NM_FULL) else NM_PATH, "PMI_NM_US")
    print(f"  {len(nm_full)} observations, {nm_full['date'].min().date()} to {nm_full['date'].max().date()}")

    # Build composite on full history
    composite_full = build_composite(mfg_full, nm_full)
    print(
        f"\nComposite (full): {len(composite_full)} observations, "
        f"{composite_full['date'].min().date()} to {composite_full['date'].max().date()}"
    )

    # Filter to project window
    composite = filter_window(composite_full, START_DATE, END_DATE)
    print(f"After windowing to {START_DATE}-{END_DATE}: {len(composite)} observations")

    # Gap check
    check_for_gaps(composite)

    # Write outputs
    full_path     = os.path.join(OUTPUT_DIR, "PMI_Composite_US_full.csv")
    windowed_path = os.path.join(OUTPUT_DIR, "PMI_Composite_US.csv")
    composite_full.to_csv(full_path, index=False)
    composite.to_csv(windowed_path, index=False)
    print(f"\nSaved full history:     {full_path}")
    print(f"Saved windowed series:  {windowed_path}")

    # Sanity checks
    # Composite values during key macro episodes (cross-checked against ISM data):
    #   GFC trough:       Manufacturing bottomed Nov 2008 (32.4), NM bottomed Nov 2008 (37.3)
    #                     Composite expected ~36.2  (0.20*32.4 + 0.80*37.3)
    #   COVID trough:     Manufacturing Apr 2020 (41.5), NM Apr 2020 (41.8)
    #                     Composite expected ~41.7  (0.20*41.5 + 0.80*41.8)
    #   Post-COVID peak:  Manufacturing Mar 2021 (64.7), NM Nov 2021 (69.1)
    #                     No single month peaks both — use Nov 2021 NM peak as reference
    #                     Manufacturing Nov 2021 = 61.1 → Composite ~67.5
    print("\n--- Sanity checks ---")
    checks = [
        ("2008-11-01", 36.2, "GFC trough (composite)"),
        ("2020-04-01", 41.7, "COVID trough (composite)"),
        ("2021-11-01", 67.5, "Post-COVID NM peak (composite)"),
    ]
    for date_str, expected, label in checks:
        rows = composite[composite["date"] == pd.Timestamp(date_str)]
        if len(rows) == 0:
            print(f"  {label} ({date_str}): NOT FOUND in data")
        else:
            actual_val = rows["PMI_Composite_US"].iloc[0]
            status = "OK" if abs(actual_val - expected) < 1.0 else "MISMATCH"
            print(f"  {label} ({date_str}): {actual_val} (expected ~{expected}) [{status}]")

    print("\nFirst 3 rows:")
    print(composite[["date", "PMI_US", "PMI_NM_US", "PMI_Composite_US"]].head(3).to_string(index=False))
    print("\nLast 3 rows:")
    print(composite[["date", "PMI_US", "PMI_NM_US", "PMI_Composite_US"]].tail(3).to_string(index=False))


if __name__ == "__main__":
    main()
