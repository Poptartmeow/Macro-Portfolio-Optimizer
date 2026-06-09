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

DATA_DIR = PROJECT_ROOT / "data"        # cleaned CSV outputs (+ raw/ inputs)
RAW_DIR = DATA_DIR / "raw"              # manually-acquired raw inputs (PMI text dumps, etc.)
OUTPUTS_DIR = PROJECT_ROOT / "outputs"  # generated charts and analysis artifacts

# Make sure the writable directories exist on import.
DATA_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
