"""Configuration management for Hoist Analysis"""

import os
import re
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def _get_cloud_mode() -> bool:
    """CLOUD_MODE 설정을 st.secrets 또는 환경변수에서 읽기"""
    # 1. st.secrets 우선 (Streamlit Cloud)
    try:
        import streamlit as st
        cloud_val = st.secrets.get("CLOUD_MODE", "")
        if cloud_val:
            return str(cloud_val).lower() == "true"
    except Exception:
        pass
    # 2. 환경변수 (로컬 .env)
    return os.getenv("CLOUD_MODE", "false").lower() == "true"


# Environment mode
CLOUD_MODE = _get_cloud_mode()

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CONFIG_DIR = DATA_DIR / "config"
CACHE_DIR = DATA_DIR / "cache"


def detect_available_dates() -> List[str]:
    """
    날짜 목록 감지 (YYYYMMDD 형식, 최신 우선)

    Cloud Mode: data/cache/ 에서 *_trips.parquet 파일로 감지
    Dev Mode: data/raw/ 에서 Y1_Hoist_Data_* 폴더로 감지
    """
    dates = set()

    # 1. Cache 디렉토리에서 감지 (Cloud + Dev 공통)
    if CACHE_DIR.exists():
        cache_pattern = re.compile(r"(\d{8})_trips\.parquet")
        for path in CACHE_DIR.iterdir():
            if path.is_file():
                match = cache_pattern.match(path.name)
                if match:
                    dates.add(match.group(1))

    # 2. Raw 디렉토리에서 감지 (Dev Mode only)
    if not CLOUD_MODE and RAW_DIR.exists():
        raw_pattern = re.compile(r"Y1_Hoist_Data_(\d{8})")
        for path in RAW_DIR.iterdir():
            if path.is_dir():
                match = raw_pattern.match(path.name)
                if match:
                    date_str = match.group(1)
                    sward_file = path / f"Y1_Hoist_SWardData_{date_str}.csv"
                    if sward_file.exists():
                        dates.add(date_str)

    return sorted(list(dates), reverse=True)


def get_data_dir(date_str: str) -> Path:
    """날짜에 해당하는 데이터 디렉토리 반환"""
    if not re.match(r"^\d{8}$", date_str):
        raise ValueError(f"Invalid date format: {date_str}")
    raw_path = RAW_DIR / f"Y1_Hoist_Data_{date_str}"
    if raw_path.exists():
        return raw_path
    # 하위 호환: 프로젝트 루트에 직접 있는 경우
    return PROJECT_ROOT / f"Y1_Hoist_Data_{date_str}"


# 기본값 (하위 호환)
_available_dates = detect_available_dates()
DEFAULT_DATE = _available_dates[0] if _available_dates else "20260326"
SAMPLE_DATA_DIR = get_data_dir(DEFAULT_DATE) if _available_dates else PROJECT_ROOT / "Y1_Hoist_Data_20260326"

# Analysis parameters (trip extraction)
TRIP_MIN_STOP_SEC = 40  # Minimum stop duration to end a trip
TRIP_MIN_DURATION_SEC = 30  # Minimum valid trip duration

# v4.5 Rate-Matching Classification parameters
# Pipeline: RSSI candidate → altitude change → multi-scale rate matching → composite scoring → RSSI reassignment
CANDIDATE_RSSI_THRESHOLD = -75  # dBm — candidate selection only (NOT used in scoring)
MIN_ALTITUDE_CHANGE = 0.3  # hPa — minimum vertical movement from worker barometer
COMPOSITE_WEIGHTS = {
    "rate_match": 0.65,  # dp/dt matching score (multi-scale: 10s/30s/60s windows)
    "delta_ratio": 0.25,  # worker_delta / hoist_delta (ideal = 1.0)
    "direction": 0.10,   # same direction (up/down) bonus
}
CLASSIFICATION_THRESHOLDS = {
    "confirmed": 0.60,   # composite >= 0.60: pressure rate matches hoist well
    "probable": 0.45,    # composite 0.45~0.60: boarded, but BLE gaps reduce confidence
}
MAX_PASSENGERS_PER_TRIP = 30  # Soft cap for warning (not rejection)
HIGH_PASSENGER_WARNING = 30  # Visual warning threshold

# Legacy parameters (kept for backward compatibility with v3 classifier — NOT used in v4.5)
CORRELATION_THRESHOLD = 0.7
RSSI_THRESHOLD = -70
MAX_LAG_SEC = 20
EVIDENCE_WEIGHTS = {
    "rssi": 0.25,
    "pressure": 0.35,
    "spatial": 0.25,
    "timing": 0.15,
}
HIGH_RSSI_THRESHOLD = -65
MIN_RSSI_DURATION_RATIO = 0.5

# Floor estimation
PRESSURE_PER_METER = 0.12  # hPa per meter at sea level
TEMP_COEFFICIENT = 0.00366  # Temperature correction factor

# UI settings
DEFAULT_TIME_RANGE = ("07:00", "22:00")
CHART_HEIGHT = 400
CHART_HEIGHT_SMALL = 300

# Cache settings
CACHE_VERSION = "1.0"

# Ensure directories exist
CACHE_DIR.mkdir(parents=True, exist_ok=True)
