"""Configuration management for Hoist Analysis (Cloud Release)"""

import re
from pathlib import Path
from typing import List

# Cloud mode is always enabled in release
CLOUD_MODE = True

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"


def detect_available_dates() -> List[str]:
    """
    Detect available dates from cache directory.
    In cloud mode, looks for *_trips.parquet files.
    """
    if not CACHE_DIR.exists():
        return []

    pattern = re.compile(r"(\d{8})_trips\.parquet")
    dates = []

    for path in CACHE_DIR.iterdir():
        if path.is_file():
            match = pattern.match(path.name)
            if match:
                dates.append(match.group(1))

    return sorted(dates, reverse=True)


# Default date (from cache)
_available_dates = detect_available_dates()
DEFAULT_DATE = _available_dates[0] if _available_dates else "20260326"

# UI settings
DEFAULT_TIME_RANGE = ("07:00", "22:00")
CHART_HEIGHT = 400
CHART_HEIGHT_SMALL = 300

# Cache settings
CACHE_VERSION = "1.0"

# Ensure directories exist
CACHE_DIR.mkdir(parents=True, exist_ok=True)
