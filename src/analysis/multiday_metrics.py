"""Multiday metrics calculation module"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ============================================================
# Data Classes
# ============================================================


@dataclass
class DailySummary:
    """Daily summary data"""
    date_str: str
    weekday: str
    trip_count: int
    passenger_count: int
    active_hoists: int
    avg_passengers_per_trip: float
    peak_hour: int
    peak_passengers: int


@dataclass
class MultiDayInsight:
    """Multiday insight"""
    type: str  # "efficiency", "congestion", "load", "safety"
    severity: int  # 1=info, 2=warning, 3=critical
    title: str
    detail: str
    metric_value: Optional[float] = None


# ============================================================
# Constants
# ============================================================

WEEKDAY_NAMES = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}
WORK_HOURS = (0, 24)  # 00:00 ~ 24:00 (24시간 현장)
MAX_PASSENGERS_CAPACITY = 25

# Expected gateway count for normal data
EXPECTED_GATEWAY_COUNT = 13
# Expected hoist count for normal data
EXPECTED_HOIST_COUNT = 9
# Trip count range considered normal (per day)
NORMAL_TRIP_COUNT_RANGE = (500, 3000)


def is_outlier_date(cache_manager, date_str: str) -> bool:
    """
    Dynamically determine if a date has outlier data.

    A date is considered an outlier if:
    1. Gateway count != 13 (expected S-Ward gateway count)
    2. Hoist count != 9 (expected hoist count)
    3. Trip count is outside normal range (500-3000)

    Args:
        cache_manager: CacheManager instance
        date_str: Date string in YYYYMMDD format

    Returns:
        True if the date has outlier data
    """
    try:
        # Check sward data
        sward_df = cache_manager.load_sward(date_str)
        if sward_df is not None:
            gateway_count = sward_df["gateway_no"].nunique()
            if gateway_count != EXPECTED_GATEWAY_COUNT:
                logger.info(f"{date_str}: gateway count {gateway_count} != {EXPECTED_GATEWAY_COUNT}")
                return True

        # Check trips data
        trips_df = cache_manager.load_trips(date_str)
        if trips_df is not None:
            hoist_count = trips_df["hoist_name"].nunique()
            if hoist_count != EXPECTED_HOIST_COUNT:
                logger.info(f"{date_str}: hoist count {hoist_count} != {EXPECTED_HOIST_COUNT}")
                return True

            trip_count = len(trips_df)
            if trip_count < NORMAL_TRIP_COUNT_RANGE[0] or trip_count > NORMAL_TRIP_COUNT_RANGE[1]:
                logger.info(f"{date_str}: trip count {trip_count} outside normal range")
                return True

        return False
    except Exception as e:
        logger.warning(f"Error checking outlier status for {date_str}: {e}")
        return False  # Assume normal if we can't check


# ============================================================
# Data Loading
# ============================================================


def load_multiday_data(
    dates: List[str],
    cache_manager
) -> Dict[str, Dict[str, pd.DataFrame]]:
    """
    Load cached data for multiple dates

    Args:
        dates: ["20260323", "20260324", ...]
        cache_manager: CacheManager instance

    Returns:
        {
            "20260323": {
                "trips": DataFrame,
                "passengers": DataFrame,
            },
            ...
        }
    """
    result = {}

    for date_str in dates:
        trips_df = cache_manager.load_trips(date_str)
        passengers_df = cache_manager.load_passengers(date_str)

        if trips_df is not None and passengers_df is not None:
            result[date_str] = {
                "trips": trips_df,
                "passengers": passengers_df,
            }
        else:
            logger.warning(f"Missing cache for date: {date_str}")

    return result


def get_available_dates_with_meta(
    cache_manager
) -> List[Dict]:
    """
    Get list of cached dates with metadata

    Returns:
        [
            {"date": "20260323", "weekday": "월", "trip_count": 278, "is_outlier": False},
            ...
        ]
    """
    status = cache_manager.get_cache_status()
    entries = status.get("entries", {})

    # Extract unique dates from cache entries
    dates = set()
    for key in entries.keys():
        if "_trips" in key:
            date_str = key.replace("_trips", "")
            dates.add(date_str)

    result = []
    for date_str in sorted(dates, reverse=True):
        try:
            dt = datetime.strptime(date_str, "%Y%m%d")
            weekday = WEEKDAY_NAMES.get(dt.weekday(), "")

            # Get trip count from metadata
            trip_key = f"{date_str}_trips"
            trip_count = entries.get(trip_key, {}).get("rows", 0)

            # Dynamic outlier detection
            outlier = is_outlier_date(cache_manager, date_str)

            result.append({
                "date": date_str,
                "weekday": weekday,
                "trip_count": trip_count,
                "is_outlier": outlier,
            })
        except ValueError:
            continue

    return result


# ============================================================
# Daily Trend Metrics
# ============================================================


def calculate_daily_summary(
    multiday_data: Dict[str, Dict[str, pd.DataFrame]]
) -> pd.DataFrame:
    """
    Calculate daily summary statistics

    Returns:
        DataFrame with columns:
        - date_str, weekday, trip_count, passenger_count,
        - active_hoists, avg_passengers_per_trip, peak_hour, peak_passengers
    """
    records = []

    for date_str, data in multiday_data.items():
        trips_df = data["trips"]
        passengers_df = data["passengers"]

        # Parse date
        try:
            dt = datetime.strptime(date_str, "%Y%m%d")
            weekday = WEEKDAY_NAMES.get(dt.weekday(), "")
        except ValueError:
            weekday = ""

        # Basic counts
        trip_count = len(trips_df)
        passenger_count = len(passengers_df)
        active_hoists = trips_df["hoist_name"].nunique() if len(trips_df) > 0 else 0

        # Avg passengers per trip (exclude empty runs)
        trips_with_pax = passengers_df["trip_id"].nunique() if len(passengers_df) > 0 else 0
        avg_pax = passenger_count / trips_with_pax if trips_with_pax > 0 else 0.0

        # Peak hour analysis
        peak_hour = 0
        peak_passengers = 0

        if len(passengers_df) > 0 and "boarding_time" in passengers_df.columns:
            passengers_df = passengers_df.copy()
            passengers_df["hour"] = passengers_df["boarding_time"].dt.hour
            hourly_counts = passengers_df.groupby("hour").size()
            if len(hourly_counts) > 0:
                peak_hour = hourly_counts.idxmax()
                peak_passengers = hourly_counts.max()

        records.append({
            "date_str": date_str,
            "weekday": weekday,
            "trip_count": trip_count,
            "passenger_count": passenger_count,
            "active_hoists": active_hoists,
            "avg_passengers_per_trip": avg_pax,
            "peak_hour": peak_hour,
            "peak_passengers": peak_passengers,
        })

    df = pd.DataFrame(records)
    if len(df) > 0:
        df = df.sort_values("date_str").reset_index(drop=True)

    return df


def calculate_building_daily(
    multiday_data: Dict[str, Dict[str, pd.DataFrame]]
) -> pd.DataFrame:
    """
    Calculate daily trip counts by building

    Returns:
        DataFrame with columns:
        - date_str, building_name, trip_count, passenger_count
    """
    records = []

    for date_str, data in multiday_data.items():
        trips_df = data["trips"]
        passengers_df = data["passengers"]

        if len(trips_df) == 0:
            continue

        # Group trips by building
        for building, group in trips_df.groupby("building_name"):
            trip_count = len(group)

            # Count passengers for this building
            building_hoists = group["hoist_name"].unique()
            pax_count = len(
                passengers_df[passengers_df["hoist_name"].isin(building_hoists)]
            ) if len(passengers_df) > 0 else 0

            records.append({
                "date_str": date_str,
                "building_name": building,
                "trip_count": trip_count,
                "passenger_count": pax_count,
            })

    df = pd.DataFrame(records)
    if len(df) > 0:
        df = df.sort_values(["date_str", "building_name"]).reset_index(drop=True)

    return df


# ============================================================
# Hourly Pattern Metrics
# ============================================================


def calculate_hourly_comparison(
    multiday_data: Dict[str, Dict[str, pd.DataFrame]],
    hour_range: Tuple[int, int] = WORK_HOURS
) -> pd.DataFrame:
    """
    Calculate hourly metrics comparison across dates

    Returns:
        DataFrame with columns:
        - date_str, hour, trip_count, passenger_count, avg_passengers_per_trip
    """
    records = []

    for date_str, data in multiday_data.items():
        trips_df = data["trips"]
        passengers_df = data["passengers"]

        if len(trips_df) == 0:
            continue

        # Add hour column
        trips_df = trips_df.copy()
        trips_df["hour"] = trips_df["start_time"].dt.hour

        # Filter to work hours
        trips_df = trips_df[
            (trips_df["hour"] >= hour_range[0]) &
            (trips_df["hour"] < hour_range[1])
        ]

        # Add hour to passengers
        if len(passengers_df) > 0 and "boarding_time" in passengers_df.columns:
            passengers_df = passengers_df.copy()
            passengers_df["hour"] = passengers_df["boarding_time"].dt.hour

        # Group by hour
        for hour in range(hour_range[0], hour_range[1]):
            hour_trips = trips_df[trips_df["hour"] == hour]
            trip_count = len(hour_trips)

            pax_count = 0
            if len(passengers_df) > 0 and "hour" in passengers_df.columns:
                pax_count = len(passengers_df[passengers_df["hour"] == hour])

            # Avg passengers per trip (exclude empty runs)
            if pax_count > 0 and len(passengers_df) > 0 and "trip_id" in passengers_df.columns:
                hour_trip_ids = set(hour_trips["trip_id"])
                hour_pax_trips = passengers_df[
                    (passengers_df["trip_id"].isin(hour_trip_ids))
                ]["trip_id"].nunique()
                avg_pax = pax_count / hour_pax_trips if hour_pax_trips > 0 else 0.0
            else:
                avg_pax = 0.0

            records.append({
                "date_str": date_str,
                "hour": hour,
                "trip_count": trip_count,
                "passenger_count": pax_count,
                "avg_passengers_per_trip": avg_pax,
            })

    df = pd.DataFrame(records)
    if len(df) > 0:
        df = df.sort_values(["date_str", "hour"]).reset_index(drop=True)

    return df


def calculate_hourly_average(
    hourly_comparison: pd.DataFrame
) -> pd.DataFrame:
    """
    Calculate average hourly metrics across all dates

    Returns:
        DataFrame with columns:
        - hour, avg_trips, avg_passengers, std_passengers
    """
    if len(hourly_comparison) == 0:
        return pd.DataFrame(columns=["hour", "avg_trips", "avg_passengers", "std_passengers"])

    grouped = hourly_comparison.groupby("hour").agg({
        "trip_count": "mean",
        "passenger_count": ["mean", "std"],
    }).reset_index()

    grouped.columns = ["hour", "avg_trips", "avg_passengers", "std_passengers"]
    grouped["std_passengers"] = grouped["std_passengers"].fillna(0)

    return grouped


def calculate_date_hour_heatmap(
    multiday_data: Dict[str, Dict[str, pd.DataFrame]],
    metric: str = "max_passengers"
) -> pd.DataFrame:
    """
    Calculate date x hour heatmap data

    Args:
        metric: "max_passengers", "trip_count", "avg_passengers"

    Returns:
        Pivot DataFrame (index=date, columns=hour, values=metric)
    """
    records = []

    for date_str, data in multiday_data.items():
        trips_df = data["trips"]
        passengers_df = data["passengers"]

        if len(trips_df) == 0:
            continue

        trips_df = trips_df.copy()
        trips_df["hour"] = trips_df["start_time"].dt.hour

        # Calculate passenger count per trip
        if len(passengers_df) > 0 and "trip_id" in passengers_df.columns:
            pax_counts = passengers_df.groupby("trip_id").size().to_dict()
            trips_df["pax_count"] = trips_df["trip_id"].map(
                lambda x: pax_counts.get(x, 0)
            )
        else:
            trips_df["pax_count"] = 0

        # Group by hour
        for hour in range(WORK_HOURS[0], WORK_HOURS[1]):
            hour_trips = trips_df[trips_df["hour"] == hour]

            if metric == "max_passengers":
                value = hour_trips["pax_count"].max() if len(hour_trips) > 0 else 0
            elif metric == "trip_count":
                value = len(hour_trips)
            elif metric == "avg_passengers":
                value = hour_trips["pax_count"].mean() if len(hour_trips) > 0 else 0
            else:
                value = 0

            records.append({
                "date_str": date_str,
                "hour": hour,
                "value": value,
            })

    df = pd.DataFrame(records)

    if len(df) == 0:
        return pd.DataFrame()

    # Pivot
    pivot = df.pivot(index="date_str", columns="hour", values="value")
    pivot = pivot.fillna(0)
    pivot = pivot.sort_index()

    return pivot


def detect_recurring_patterns(
    hourly_comparison: pd.DataFrame,
    threshold_pax: int = 100,
    min_occurrence_rate: float = 0.6
) -> List[Dict]:
    """
    Detect recurring congestion patterns

    Returns:
        [
            {
                "hour": 7,
                "avg_passengers": 127,
                "occurrence_rate": 0.8,
                "description": "07:00 출근 시간 반복 피크"
            },
            ...
        ]
    """
    if len(hourly_comparison) == 0:
        return []

    # Get unique dates
    dates = hourly_comparison["date_str"].unique()
    n_dates = len(dates)

    if n_dates == 0:
        return []

    patterns = []

    # Group by hour
    for hour in range(WORK_HOURS[0], WORK_HOURS[1]):
        hour_data = hourly_comparison[hourly_comparison["hour"] == hour]

        if len(hour_data) == 0:
            continue

        # Count how many days have significant passengers at this hour
        high_pax_days = len(hour_data[hour_data["passenger_count"] >= threshold_pax])
        occurrence_rate = high_pax_days / n_dates

        if occurrence_rate >= min_occurrence_rate:
            avg_pax = hour_data["passenger_count"].mean()

            # Generate description
            if hour < 9:
                time_desc = "출근 시간"
            elif hour < 13:
                time_desc = "오전 작업"
            elif hour < 14:
                time_desc = "점심 시간"
            elif hour < 18:
                time_desc = "오후 작업"
            else:
                time_desc = "퇴근 시간"

            patterns.append({
                "hour": hour,
                "avg_passengers": avg_pax,
                "occurrence_rate": occurrence_rate,
                "description": f"{hour:02d}:00 {time_desc} 반복 피크",
            })

    return patterns


# ============================================================
# Hoist Comparison Metrics
# ============================================================


def calculate_hoist_daily_metrics(
    multiday_data: Dict[str, Dict[str, pd.DataFrame]]
) -> pd.DataFrame:
    """
    Calculate daily metrics per hoist

    Returns:
        DataFrame with columns:
        - hoist_name, date_str, trip_count, passenger_count,
        - utilization_rate, avg_passengers, peak_passengers
    """
    records = []

    for date_str, data in multiday_data.items():
        trips_df = data["trips"]
        passengers_df = data["passengers"]

        if len(trips_df) == 0:
            continue

        # Calculate passenger count per trip
        if len(passengers_df) > 0 and "trip_id" in passengers_df.columns:
            pax_per_trip = passengers_df.groupby("trip_id").size().to_dict()
            trips_df = trips_df.copy()
            trips_df["pax_count"] = trips_df["trip_id"].map(
                lambda x: pax_per_trip.get(x, 0)
            )
        else:
            trips_df = trips_df.copy()
            trips_df["pax_count"] = 0

        # Group by hoist
        for hoist_name, group in trips_df.groupby("hoist_name"):
            trip_count = len(group)

            # Passenger stats (exclude empty runs for avg)
            hoist_pax = passengers_df[passengers_df["hoist_name"] == hoist_name] \
                if len(passengers_df) > 0 else pd.DataFrame()
            passenger_count = len(hoist_pax)
            trips_with_pax = hoist_pax["trip_id"].nunique() if len(hoist_pax) > 0 else 0
            avg_passengers = passenger_count / trips_with_pax if trips_with_pax > 0 else 0
            peak_passengers = group["pax_count"].max() if len(group) > 0 else 0

            # Utilization rate: merged intervals (gap ≤ 10min = standby) / 24h
            STANDBY_GAP_SEC = 600
            DAY_SEC = 86400
            sorted_trips = group.sort_values("start_time")
            merged = []
            for s, e in zip(sorted_trips["start_time"], sorted_trips["end_time"]):
                if merged and (s - merged[-1][1]).total_seconds() <= STANDBY_GAP_SEC:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], e))
                else:
                    merged.append((s, e))
            operating_sec = sum((e - s).total_seconds() for s, e in merged)
            utilization_rate = min(operating_sec / DAY_SEC, 1.0)

            records.append({
                "hoist_name": hoist_name,
                "date_str": date_str,
                "trip_count": trip_count,
                "passenger_count": passenger_count,
                "trips_with_pax": trips_with_pax,
                "utilization_rate": utilization_rate,
                "avg_passengers": avg_passengers,
                "peak_passengers": peak_passengers,
            })

    df = pd.DataFrame(records)
    if len(df) > 0:
        df = df.sort_values(["hoist_name", "date_str"]).reset_index(drop=True)

    return df


def calculate_hoist_summary(
    hoist_daily: pd.DataFrame
) -> pd.DataFrame:
    """
    Calculate summary metrics per hoist across all dates

    Returns:
        DataFrame with columns:
        - hoist_name, building_name, total_trips, total_passengers,
        - avg_daily_trips, avg_utilization, avg_passengers_per_trip,
        - peak_passengers, trip_share
    """
    if len(hoist_daily) == 0:
        return pd.DataFrame()

    # Aggregate by hoist
    grouped = hoist_daily.groupby("hoist_name").agg({
        "trip_count": ["sum", "mean"],
        "passenger_count": "sum",
        "trips_with_pax": "sum",
        "utilization_rate": "mean",
        "peak_passengers": "max",
    }).reset_index()

    grouped.columns = [
        "hoist_name", "total_trips", "avg_daily_trips",
        "total_passengers", "total_trips_with_pax",
        "avg_utilization", "peak_passengers"
    ]

    # Calculate avg passengers per trip (exclude empty runs)
    grouped["avg_passengers_per_trip"] = (
        grouped["total_passengers"] / grouped["total_trips_with_pax"]
    ).fillna(0)

    # Extract building name
    grouped["building_name"] = grouped["hoist_name"].apply(
        lambda x: x.split("_")[0] if "_" in x else ""
    )

    # Calculate trip share
    total_all_trips = grouped["total_trips"].sum()
    grouped["trip_share"] = (
        grouped["total_trips"] / total_all_trips * 100
    ) if total_all_trips > 0 else 0

    # Sort by total trips descending
    grouped = grouped.sort_values("total_trips", ascending=False).reset_index(drop=True)

    return grouped


def calculate_load_distribution(
    hoist_summary: pd.DataFrame
) -> Dict:
    """
    Calculate hoist load distribution

    Returns:
        {
            "distribution": {"FAB_Hoist_1": 0.32, ...},
            "imbalance_score": 0.45,
            "dominant_hoist": "FAB_Hoist_1",
            "dominant_share": 32.0
        }
    """
    if len(hoist_summary) == 0:
        return {
            "distribution": {},
            "imbalance_score": 0,
            "dominant_hoist": "",
            "dominant_share": 0,
        }

    # Distribution as dict
    distribution = dict(zip(
        hoist_summary["hoist_name"],
        hoist_summary["trip_share"] / 100
    ))

    # Dominant hoist
    dominant_idx = hoist_summary["trip_share"].idxmax()
    dominant_hoist = hoist_summary.loc[dominant_idx, "hoist_name"]
    dominant_share = hoist_summary.loc[dominant_idx, "trip_share"]

    # Imbalance score (Gini coefficient simplified)
    # 0 = perfectly balanced, 1 = all trips on one hoist
    shares = hoist_summary["trip_share"].values / 100
    n = len(shares)
    if n <= 1:
        imbalance = 0
    else:
        # Normalized entropy-based imbalance
        shares_nonzero = shares[shares > 0]
        if len(shares_nonzero) == 0:
            imbalance = 0
        else:
            entropy = -np.sum(shares_nonzero * np.log(shares_nonzero))
            max_entropy = np.log(n)
            imbalance = 1 - (entropy / max_entropy) if max_entropy > 0 else 0

    return {
        "distribution": distribution,
        "imbalance_score": imbalance,
        "dominant_hoist": dominant_hoist,
        "dominant_share": dominant_share,
    }


# ============================================================
# Insight Generation
# ============================================================


def generate_multiday_insights(
    daily_summary: pd.DataFrame,
    hoist_summary: pd.DataFrame,
    patterns: List[Dict],
    load_distribution: Dict
) -> List[MultiDayInsight]:
    """
    Generate multiday insights automatically

    Rules:
    1. Efficiency (severity=1): low utilization, imbalance
    2. Congestion (severity=2): recurring peaks, high passenger counts
    3. Load (severity=2): concentrated load on specific hoist
    4. Safety (severity=3): over-capacity suspicion
    """
    insights = []

    # 1. Efficiency: Low utilization hoists
    if len(hoist_summary) > 0:
        low_util_hoists = hoist_summary[hoist_summary["avg_utilization"] < 0.1]
        for _, row in low_util_hoists.iterrows():
            insights.append(MultiDayInsight(
                type="efficiency",
                severity=1,
                title=f"{row['hoist_name']} 가동률 저조",
                detail=f"평균 가동률 {row['avg_utilization']*100:.1f}% - "
                       f"운행 스케줄 조정으로 다른 건물 지원 가능",
                metric_value=row["avg_utilization"],
            ))

    # 2. Congestion: Recurring patterns
    for pattern in patterns:
        if pattern["occurrence_rate"] >= 0.7:
            insights.append(MultiDayInsight(
                type="congestion",
                severity=2,
                title=f"{pattern['hour']:02d}:00 반복 혼잡",
                detail=f"{pattern['description']} (평균 {pattern['avg_passengers']:.0f}명, "
                       f"{pattern['occurrence_rate']*100:.0f}% 발생)",
                metric_value=pattern["avg_passengers"],
            ))

    # 3. Load: Concentrated load
    if load_distribution.get("dominant_share", 0) > 30:
        insights.append(MultiDayInsight(
            type="load",
            severity=2,
            title=f"{load_distribution['dominant_hoist']}에 부하 집중",
            detail=f"전체 운행의 {load_distribution['dominant_share']:.1f}% 집중 - "
                   f"분산 운행 권장",
            metric_value=load_distribution["dominant_share"],
        ))

    # 4. Safety: Over-capacity suspicion
    if len(hoist_summary) > 0:
        over_capacity = hoist_summary[hoist_summary["peak_passengers"] > MAX_PASSENGERS_CAPACITY]
        for _, row in over_capacity.iterrows():
            insights.append(MultiDayInsight(
                type="safety",
                severity=3,
                title=f"{row['hoist_name']} 정원 초과 의심",
                detail=f"최대 탑승인원 {row['peak_passengers']:.0f}명 감지 "
                       f"(정원 {MAX_PASSENGERS_CAPACITY}명)",
                metric_value=row["peak_passengers"],
            ))

    # 5. Imbalance warning
    if load_distribution.get("imbalance_score", 0) > 0.4:
        insights.append(MultiDayInsight(
            type="efficiency",
            severity=1,
            title="호이스트 부하 불균형",
            detail=f"부하 불균형 지수 {load_distribution['imbalance_score']:.2f} - "
                   f"호이스트 간 운행 분산 필요",
            metric_value=load_distribution["imbalance_score"],
        ))

    # Sort by severity (higher first)
    insights.sort(key=lambda x: -x.severity)

    return insights


def calculate_period_kpis(
    daily_summary: pd.DataFrame
) -> Dict:
    """
    Calculate KPIs for the entire period

    Returns:
        {
            "total_trips": int,
            "total_passengers": int,
            "avg_daily_trips": float,
            "avg_daily_passengers": float,
            "num_days": int,
        }
    """
    if len(daily_summary) == 0:
        return {
            "total_trips": 0,
            "total_passengers": 0,
            "avg_daily_trips": 0,
            "avg_daily_passengers": 0,
            "num_days": 0,
        }

    total_trips = daily_summary["trip_count"].sum()
    total_passengers = daily_summary["passenger_count"].sum()
    num_days = len(daily_summary)

    return {
        "total_trips": int(total_trips),
        "total_passengers": int(total_passengers),
        "avg_daily_trips": total_trips / num_days if num_days > 0 else 0,
        "avg_daily_passengers": total_passengers / num_days if num_days > 0 else 0,
        "num_days": num_days,
    }
