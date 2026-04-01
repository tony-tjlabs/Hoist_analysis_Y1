"""Type converters and utility functions"""

from datetime import datetime
from typing import Optional, Any
import pandas as pd


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float"""
    if pd.isna(value):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert value to int"""
    if pd.isna(value):
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def parse_datetime(value: Any) -> Optional[datetime]:
    """Parse datetime from various formats"""
    if pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    try:
        # Handle format: "2026-03-26 00:00:00.143 +0900"
        if isinstance(value, str):
            # Remove timezone offset for parsing
            if " +" in value or " -" in value:
                value = value.rsplit(" ", 1)[0]
            return pd.to_datetime(value).to_pydatetime()
    except Exception:
        return None
    return None


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string"""
    if seconds < 60:
        return f"{seconds:.0f}초"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}분"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}시간"


def format_time(dt: datetime) -> str:
    """Format datetime to HH:MM:SS"""
    return dt.strftime("%H:%M:%S")


def time_to_minutes(time_str: str) -> int:
    """Convert HH:MM time string to minutes from midnight"""
    parts = time_str.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def minutes_to_time(minutes: int) -> str:
    """Convert minutes from midnight to HH:MM string"""
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


def format_hoist_name(hoist_name: str) -> str:
    """Convert raw hoist name to readable display name.

    Examples:
        CUB_Hoist_1  -> CUB Hoist1
        FAB_Hoist_4  -> FAB Hoist4
        FAB_Climber_1 -> FAB Climber1
        WWT_Hoist_2  -> WWT Hoist2
    """
    parts = hoist_name.split("_")
    if len(parts) >= 3:
        return f"{parts[0]} {parts[1]}{parts[2]}"
    elif len(parts) >= 2:
        return f"{parts[0]} {parts[1]}"
    return hoist_name
