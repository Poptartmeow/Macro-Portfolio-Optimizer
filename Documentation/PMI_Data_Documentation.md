# PMI Data Documentation

**Author:** Mauricio Torres  

---

## What is PMI?

 **Purchasing Managers' Index** or PMI. Is a monthly survey based indicator that captures the economic activity of businesses by asking purchasing managers whether conditions (things like new orders, employment, production, supplier deliveries, and inventories)improved, stayed the same, or got worse compared to the prior month.

The result is a diffusion index:
- **Above 50** → expansion (more respondents reported improvement than deterioration)
- **Below 50** → contraction
- **50** → no change

PMI is widely used by economists and portfolio managers as a real time read on the economy because it comes out fast (first few days of each month), covers the prior month, and is **never revised**, which matters a lot for backtesting since you're always working with the number that was actually available at the time.

---

## Why PMI for This Project?

The optimizer is built around a monthly cadence, but the most natural measure of economic activity, is real GDP, is quarterly and gets revised multiple times. PMI solves both problems. Greg specifically recommended it for three reasons:

1. **Monthly frequency** — matches the optimizer's rebalancing schedule
2. **Never revised** — clean for backtesting; no look-ahead bias from data revisions
3. **Forward-looking** — the new orders subcomponent captures demand before it shows up in output

US PMI as the primary macro indicator for the US equity bucket. Non-US regions are planned but not yet implemented (see the pipeline files for the TODO list).

---

## Data Sources

### ISM Manufacturing PMI
- **Publisher:** Institute for Supply Management (ISM)
- **Survey covers:** Manufacturing sector (~11% of US GDP, but historically the most cyclical and closely watched)
- **Release timing:** First business day of each month, describing the prior month
- **Free source:** [investing.com](https://www.investing.com/economic-calendar/ism-manufacturing-pmi-173)

### ISM Non-Manufacturing (Services) PMI
- **Publisher:** Institute for Supply Management (ISM)
- **Survey covers:** Services sector (~80% of US GDP — finance, healthcare, retail, hospitality, etc.)
- **Release timing:** Third business day of each month, describing the prior month
- **Free source:** [investing.com](https://www.investing.com/economic-calendar/ism-non-manufacturing-pmi-176)

**Why investing.com and not FRED?** FRED used to host ISM data directly, but removed it. S&P Global's competing PMI series is paywalled. DBnomics only goes back to 2020. investing.com has the full history going back to 2006–2007, and the table can be copied manually.

---

## How the Data Was Acquired

Both series were pulled manually from investing.com's Economic Calendar historical data tables. The process for each:

1. Navigate to the investing.com page linked above
2. Scroll down to the Historical Data table and click "Show More" until the table goes back to at least January 2007
3. Select all rows (including the header), copy
4. Paste into the corresponding raw text file in `data/raw/`

The raw files are:
- `data/raw/PMI_Manufacturing_US.txt`
- `data/raw/PMI_Non_Manufacturing_US.txt`

This is a manual refresh, needs to be done once a month after each release.

---

## A Note on the Date Convention

investing.com lists rows by **release date**, but the ISM PMI released in (say) June describes **May** economic conditions. The website annotates this with a parenthetical, e.g.:

```
Jun 01, 2026 (May)    10:00    54.0    53.3
```

The `(May)` tells you the reference period. Our pipelines extract this parenthetical and key all output data by **reference month**, not release date. This matches the FRED convention and avoids off-by-one errors in the optimizer (you don't want to credit June's release to June when it actually describes May).

For older rows where the parenthetical is missing, the pipeline infers the reference month as release month − 1.

---

## Pipelines

Three pipelines process the raw data into clean CSVs for the optimizer.

### Pipeline 1 — Manufacturing PMI
**File:** `Pipelines/Macro_PMI_Pipeline_1.py`  
**Input:** `data/raw/PMI_Manufacturing_US.txt`  
**Outputs:**
- `data/PMI_Manufacturing_US.csv` — windowed to project start date (2007-01-01), fed into optimizer
- `data/PMI_Manufacturing_US_full.csv` — full unwindowed history for reference

**Output column:** `PMI_US`

### Pipeline 2 — Non-Manufacturing (Services) PMI
**File:** `Pipelines/Macro_PMI_Pipeline_2.py`  
**Input:** `data/raw/PMI_Non_Manufacturing_US.txt`  
**Outputs:**
- `data/PMI_NonManufacturing_US.csv` — windowed series
- `data/PMI_NonManufacturing_US_full.csv` — full history

**Output column:** `PMI_NM_US`

### Pipeline 3 — Composite PMI
**File:** `Pipelines/Macro_PMI_Pipeline_3.py`  
**Inputs:** Outputs of Pipelines 1 and 2 (must run those first)  
**Outputs:**
- `data/PMI_Composite_US.csv` — windowed composite, fed into optimizer
- `data/PMI_Composite_US_full.csv` — full history

**Output columns:** `PMI_US`, `PMI_NM_US`, `PMI_Composite_US`, `source`

The `source` column records whether each month was built from both series, or just one (e.g. when one release hasn't come out yet).

---

## Composite Weighting

The composite is a weighted average of Manufacturing and Non-Manufacturing:

```
PMI_Composite_US = 0.20 × PMI_Manufacturing + 0.80 × PMI_Non-Manufacturing
```

The 80/20 split reflects the approximate composition of US GDP — services account for roughly 80% of economic output. Manufacturing gets a 20% weight despite representing only ~11% of GDP because it's more cyclically sensitive and historically carries more signal for the kind of macro regime shifts the optimizer is trying to detect.

If one series is missing for a given month (e.g. the manufacturing release hasn't come out yet but services has), the composite falls back to whichever series is available rather than dropping the row. The `source` column in the output flags when this happens.

---

## Run Order

Always run in sequence:

```
python Pipelines/Macro_PMI_Pipeline_1.py
python Pipelines/Macro_PMI_Pipeline_2.py
python Pipelines/Macro_PMI_Pipeline_3.py
```

Pipeline 3 reads the CSVs produced by 1 and 2, so running it first will error.

---

## Monthly Refresh Checklist

1. Go to the investing.com pages for each series
2. Copy the updated historical table (the new month will appear at the top)
3. Paste into the corresponding `.txt` file in `data/raw/` (overwrite the whole file)
4. Run Pipelines 1, 2, and 3 in order
5. Verify the last row in each output CSV reflects the new month

Manufacturing releases on the **1st business day** of the month. Non-Manufacturing releases on the **3rd business day**. Run both pipelines together once Non-Manufacturing is out — no need to run Pipeline 1 twice.

---

## Historical Reference Points

| Event | Date (ref month) | Manufacturing | Non-Manufacturing | Composite |
|---|---|---|---|---|
| GFC trough | Nov 2008 | 32.4 | 37.3 | 36.3 |
| COVID trough | Apr 2020 | 41.5 | 41.8 | 41.7 |
| Post-COVID peak | Mar/Nov 2021 | 64.7 (Mar) | 69.1 (Nov) | ~67.5 (Nov) |

