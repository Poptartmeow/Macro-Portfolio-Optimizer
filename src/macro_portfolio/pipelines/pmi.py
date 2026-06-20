"""
Macro Portfolio Optimizer — Unified PMI Pipeline
================================================

Single pipeline that turns the two manually-acquired ISM PMI text dumps into the
three CSVs the rest of the project consumes:

    macro_data/raw/pmi/PMI_US_Man     → macro_data/processed/pmi/PMI_Manufacturing_US.csv     (col: PMI_US)
    macro_data/raw/pmi/PMI_US_NonMan  → macro_data/processed/pmi/PMI_NonManufacturing_US.csv  (col: PMI_NM_US)
                             (both)   → macro_data/processed/pmi/PMI_Composite_US.csv          (col: PMI_Composite_US)

This supersedes the three older single-purpose scripts (pmi_manufacturing.py,
pmi_nonmanufacturing.py, pmi_composite.py), which read the now-retired
data/raw/PMI_*_US.txt dumps that only went back to 2006. The new inputs go back
to 2002.

Why PMI (per sponsor, Greg): PMI is monthly (matches the optimizer frequency),
never revised (clean for backtesting), forward-looking (captures new orders),
and more timely than GDP — so we use it as a monthly proxy for quarterly real GDP.

Composite weighting: US GDP is ~80% services / ~20% goods-producing, so we use
the standard ISM composite weights:
    PMI_Composite_US = 0.20 * Manufacturing + 0.80 * Non-Manufacturing
When only one series exists for a month (e.g. one release lags the other), the
composite falls back to whichever is available; the `source` column records this.

Input format (investing.com Historical Data table, tab-delimited):
    Release date          Time   Actual  Forecast  Previous
    Jun 01, 2026 (May)    10:00  54.0    53.3
    52.7
Rows are keyed by RELEASE date, but a PMI released (e.g.) Jun 1 2026 describes
the MAY 2026 reference period. We extract the reference month from the
parenthetical "(May)" annotation and key the output by reference month, matching
FRED and the rest of the team's macro data. Older rows omit the parenthetical,
so we infer reference month = release month − 1.

Refresh procedure (manual, monthly):
    1. Open the investing.com Historical Data table for each series:
         Manufacturing:     .../ism-manufacturing-pmi-173
         Non-Manufacturing: .../ism-non-manufacturing-pmi-176
    2. Click "Show More" until rows go back to at least 2002.
    3. Select all rows incl. the header, copy.
    4. Paste over data/macro_data/raw/pmi/PMI_US_Man   (manufacturing)
              and data/macro_data/raw/pmi/PMI_US_NonMan (non-manufacturing).
    5. Re-run:  python -m macro_portfolio.pipelines.pmi

Requirements:
    pip install pandas
"""

from __future__ import annotations

import re
from datetime import datetime

import pandas as pd

from macro_portfolio import paths

# ── Config ──────────────────────────────────────────────────────────────────
START_DATE = "2002-01-01"
END_DATE = datetime.today().strftime("%Y-%m-%d")

INPUT_DIR = paths.MACRO_PMI_RAW
OUTPUT_DIR = paths.MACRO_PMI

MAN_INPUT = INPUT_DIR / "PMI_US_Man"
NONMAN_INPUT = INPUT_DIR / "PMI_US_NonMan"

# ISM composite weights (services-heavy, matching US GDP composition)
W_MFG = 0.20
W_NM = 0.80

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# Matches lines like:
#   "Jun 01, 2026 (May)\t10:00\t54.0\t53.3\t..."
#   "Mar 03, 2008\t10:00\t48.3\t48.0\t..."   (older rows omit the parenthetical)
# The trailing "Previous" value wraps onto its own line and is intentionally
# ignored — we only capture the Actual (group 5).
ROW_PATTERN = re.compile(
    r"^(\w{3})\s+(\d{1,2}),\s+(\d{4})(?:\s+\((\w{3})\))?\s*\t[\d:]+\s*\t([\d.]*)",
    re.MULTILINE,
)


def parse_reference_date(release_mo: str, release_year: str,
                         parenthetical_ref_mo: str) -> pd.Timestamp:
    """Map a release date to the reference month it describes (day=1)."""
    release_month_num = MONTH_MAP[release_mo]
    release_year_num = int(release_year)

    if parenthetical_ref_mo:
        ref_month_num = MONTH_MAP[parenthetical_ref_mo]
        # e.g. a January release annotated "(Dec)" refers to the prior year
        ref_year = (release_year_num - 1 if ref_month_num > release_month_num
                    else release_year_num)
    elif release_month_num == 1:
        ref_month_num, ref_year = 12, release_year_num - 1
    else:
        ref_month_num, ref_year = release_month_num - 1, release_year_num

    return pd.Timestamp(year=ref_year, month=ref_month_num, day=1)


def parse_dump(path, value_col: str) -> pd.DataFrame:
    """
    Parse an investing.com PMI text dump into a clean monthly DataFrame with
    columns [date, <value_col>], keyed by reference month and sorted ascending.
    Rows with a blank Actual (future, not-yet-released) are skipped.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Could not find PMI dump at: {path}\n"
            f"See the module docstring for how to grab it from investing.com."
        )

    raw = path.read_text(encoding="utf-8")
    matches = ROW_PATTERN.findall(raw)

    records, skipped = [], 0
    for release_mo, _day, release_year, ref_mo, actual in matches:
        if actual == "":                       # future release, no Actual yet
            skipped += 1
            continue
        records.append({
            "date": parse_reference_date(release_mo, release_year, ref_mo),
            value_col: float(actual),
        })

    df = (pd.DataFrame(records)
            .sort_values("date")
            .drop_duplicates(subset=["date"], keep="last")
            .reset_index(drop=True))

    print(f"  {path.name}: {len(matches)} rows parsed, {skipped} future-row(s) "
          f"skipped → {len(df)} observations "
          f"({df['date'].min().date()} → {df['date'].max().date()})")
    return df


def build_composite(mfg: pd.DataFrame, nm: pd.DataFrame) -> pd.DataFrame:
    """Outer-join the two series and compute the weighted composite per month."""
    merged = (pd.merge(mfg, nm, on="date", how="outer")
                .sort_values("date").reset_index(drop=True))

    rows = []
    for _, row in merged.iterrows():
        has_mfg, has_nm = pd.notna(row.get("PMI_US")), pd.notna(row.get("PMI_NM_US"))
        if has_mfg and has_nm:
            composite, source = W_MFG * row["PMI_US"] + W_NM * row["PMI_NM_US"], "both"
        elif has_mfg:
            composite, source = row["PMI_US"], "manufacturing_only"
        elif has_nm:
            composite, source = row["PMI_NM_US"], "nonmanufacturing_only"
        else:
            composite, source = float("nan"), "none"

        rows.append({
            "date": row["date"],
            "PMI_US": row.get("PMI_US"),
            "PMI_NM_US": row.get("PMI_NM_US"),
            "PMI_Composite_US": round(composite, 2) if pd.notna(composite) else float("nan"),
            "source": source,
        })
    return pd.DataFrame(rows)


def filter_window(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    mask = (df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))
    return df.loc[mask].reset_index(drop=True)


def check_for_gaps(df: pd.DataFrame, value_col: str, label: str) -> None:
    """Warn if the monthly series has any missing months."""
    valid = df.dropna(subset=[value_col])
    expected = pd.date_range(valid["date"].min(), valid["date"].max(), freq="MS")
    missing = sorted(set(expected) - set(valid["date"]))
    if missing:
        print(f"  WARNING [{label}]: {len(missing)} missing month(s): "
              + ", ".join(str(m.date()) for m in missing))
    else:
        print(f"  [{label}] no gaps — monthly series is continuous.")


def _run_sanity(df: pd.DataFrame, value_col: str, checks: list[tuple[str, float, str]],
                tol: float) -> None:
    for date_str, expected, label in checks:
        rows = df[df["date"] == pd.Timestamp(date_str)]
        if rows.empty:
            print(f"  {label} ({date_str}): NOT FOUND")
            continue
        val = rows[value_col].iloc[0]
        status = "OK" if abs(val - expected) < tol else "MISMATCH"
        print(f"  {label} ({date_str}): {val} (expected ~{expected}) [{status}]")


def main() -> None:
    print("Parsing raw PMI dumps...")
    mfg = parse_dump(MAN_INPUT, "PMI_US")
    nm = parse_dump(NONMAN_INPUT, "PMI_NM_US")

    composite = build_composite(mfg, nm)

    # Window to the project analysis range (data starts 2002, so this is a no-op
    # today, but keeps the start configurable if we ever trim the panel).
    mfg_w = filter_window(mfg, START_DATE, END_DATE)
    nm_w = filter_window(nm, START_DATE, END_DATE)
    comp_w = filter_window(composite, START_DATE, END_DATE)

    print("\nGap checks:")
    check_for_gaps(mfg_w, "PMI_US", "Manufacturing")
    check_for_gaps(nm_w, "PMI_NM_US", "Non-Manufacturing")
    check_for_gaps(comp_w, "PMI_Composite_US", "Composite")
    partial = comp_w[comp_w["source"] != "both"]
    if not partial.empty:
        print(f"  NOTE: {len(partial)} composite row(s) built from a single series:")
        print(partial[["date", "source"]].to_string(index=False))

    # One CSV per series. (We used to also write *_full unwindowed copies, but
    # the inputs now start at the window start, 2002, so they were identical.)
    outputs = {
        "PMI_Manufacturing_US.csv":    mfg_w,
        "PMI_NonManufacturing_US.csv": nm_w,
        "PMI_Composite_US.csv":        comp_w,
    }
    print("\nWriting CSVs:")
    for name, frame in outputs.items():
        path = OUTPUT_DIR / name
        frame.to_csv(path, index=False)
        print(f"  {path}  ({len(frame)} rows)")

    print("\n--- Sanity checks ---")
    print("Manufacturing:")
    _run_sanity(mfg_w, "PMI_US", [
        ("2008-12-01", 32.4, "GFC trough"),
        ("2020-04-01", 41.5, "COVID trough"),
        ("2021-03-01", 64.7, "post-COVID peak"),
    ], tol=0.1)
    print("Composite:")
    _run_sanity(comp_w, "PMI_Composite_US", [
        ("2008-11-01", 36.2, "GFC trough"),
        ("2020-04-01", 41.7, "COVID trough"),
        ("2021-11-01", 67.5, "post-COVID NM peak"),
    ], tol=1.0)

    print("\nComposite — first 3 / last 3 rows:")
    cols = ["date", "PMI_US", "PMI_NM_US", "PMI_Composite_US"]
    print(comp_w[cols].head(3).to_string(index=False))
    print(comp_w[cols].tail(3).to_string(index=False))


if __name__ == "__main__":
    main()
