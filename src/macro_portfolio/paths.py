"""
Centralized filesystem paths for the project.

Every script resolves its inputs/outputs relative to the repository root
(computed from this file's location), so the code runs the same regardless
of the current working directory or which machine it's on. Do NOT hardcode
absolute paths anywhere else.
"""

from pathlib import Path

# src/macro_portfolio/paths.py  ->  parents[2] is the repo root
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"  # generated charts and analysis artifacts

# Data is split into two domains, each with raw inputs vs generated outputs:
#
#   data/
#   ├── macro_data/   ── macro factors (CPI, rates, spreads, PMI, ...)
#   │   ├── raw/          external / manually-pasted inputs
#   │   │   └── pmi/      investing.com PMI table dumps
#   │   └── processed/    everything the pipelines generate
#   │       └── pmi/      cleaned PMI series
#   └── market_data/  ── asset prices & returns
#       ├── raw/          raw price pulls
#       └── processed/    returns, stats, benchmark (optimizer inputs)
#
# `raw/` holds what a human acquires; `processed/` can always be regenerated.

MACRO_DIR = DATA_DIR / "macro_data"
MACRO_RAW = MACRO_DIR / "raw"
MACRO_PMI_RAW = MACRO_RAW / "pmi"
MACRO_PROCESSED = MACRO_DIR / "processed"
MACRO_PMI = MACRO_PROCESSED / "pmi"

MARKET_DIR = DATA_DIR / "market_data"
MARKET_RAW = MARKET_DIR / "raw"
MARKET_PROCESSED = MARKET_DIR / "processed"

# Make sure the writable directories exist on import.
for _d in (MACRO_RAW, MACRO_PMI_RAW, MACRO_PROCESSED, MACRO_PMI,
           MARKET_RAW, MARKET_PROCESSED, OUTPUTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
