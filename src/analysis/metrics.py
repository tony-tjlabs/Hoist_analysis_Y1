"""Metric calculations for Hoist Analysis"""

import ast
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

from ..data.schema import HoistMetrics, FloorMetrics

logger = logging.getLogger(__name__)


def calculate_hoist_metrics(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    hoist_name: str
) -> HoistMetrics:
    """
    Calculate metrics for a single hoist

    Returns:
        HoistMetrics dataclass
    """
    # Filter to this hoist
    hoist_trips = trips_df[trips_df["hoist_name"] == hoist_name]
    hoist_passengers = passengers_df[passengers_df["hoist_name"] == hoist_name]

    if len(hoist_trips) == 0:
        building = trips_df["building_name"].iloc[0] if len(trips_df) > 0 else ""
        return HoistMetrics(
            hoist_name=hoist_name,
            building_name=building,
            trip_count=0,
            operating_time_min=0.0,
            idle_time_min=0.0,
            utilization_rate=0.0,
            avg_passengers=0.0,
            total_passengers=0
        )

    building = hoist_trips["building_name"].iloc[0]
    trip_count = len(hoist_trips)

    # Operating time
    operating_sec = hoist_trips["duration_sec"].sum()
    operating_min = operating_sec / 60.0

    # Calculate total span time
    start = hoist_trips["start_time"].min()
    end = hoist_trips["end_time"].max()
    total_span_sec = (end - start).total_seconds()

    # Idle time (span - operating)
    idle_sec = total_span_sec - operating_sec
    idle_min = max(0, idle_sec / 60.0)

    # Utilization rate
    utilization = operating_sec / total_span_sec if total_span_sec > 0 else 0.0

    # Passenger stats
    total_passengers = len(hoist_passengers)
    avg_passengers = total_passengers / trip_count if trip_count > 0 else 0.0

    return HoistMetrics(
        hoist_name=hoist_name,
        building_name=building,
        trip_count=trip_count,
        operating_time_min=operating_min,
        idle_time_min=idle_min,
        utilization_rate=utilization,
        avg_passengers=avg_passengers,
        total_passengers=total_passengers
    )


def calculate_all_hoist_metrics(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Calculate metrics for all hoists

    Returns:
        DataFrame with hoist metrics
    """
    hoists = trips_df["hoist_name"].unique()

    records = []
    for hoist_name in hoists:
        metrics = calculate_hoist_metrics(trips_df, passengers_df, hoist_name)
        records.append({
            "hoist_name": metrics.hoist_name,
            "building_name": metrics.building_name,
            "trip_count": metrics.trip_count,
            "operating_time_min": metrics.operating_time_min,
            "idle_time_min": metrics.idle_time_min,
            "utilization_rate": metrics.utilization_rate,
            "avg_passengers": metrics.avg_passengers,
            "total_passengers": metrics.total_passengers
        })

    return pd.DataFrame(records)


def calculate_floor_metrics(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    building: str
) -> pd.DataFrame:
    """
    Calculate floor-level metrics for a building

    Returns:
        DataFrame with floor metrics
    """
    # Filter to building
    building_trips = trips_df[trips_df["building_name"] == building]

    if len(building_trips) == 0:
        return pd.DataFrame()

    # Count floor stops
    floor_counts = {}

    for _, trip in building_trips.iterrows():
        floors_visited = trip.get("floors_visited", [])
        if isinstance(floors_visited, str):
            # Handle stored as string (safely parse list)
            try:
                floors_visited = ast.literal_eval(floors_visited)
            except (ValueError, SyntaxError):
                floors_visited = []

        for floor in floors_visited:
            if floor not in floor_counts:
                floor_counts[floor] = {
                    "stop_count": 0,
                    "boarding_count": 0,
                    "alighting_count": 0
                }
            floor_counts[floor]["stop_count"] += 1

    # Add passenger boarding/alighting counts
    # boarding_floor/alighting_floor in passengers_df are often empty.
    # Use trip's start_floor/end_floor instead (the trip determines which floors).
    building_passengers = passengers_df[
        passengers_df["hoist_name"].str.startswith(building)
    ]

    if len(building_passengers) > 0 and len(building_trips) > 0:
        # Merge with trip floor info
        trip_floors = building_trips[["trip_id", "start_floor", "end_floor", "direction"]].copy()
        pax_with_floors = building_passengers.merge(trip_floors, on="trip_id", how="left")

        for _, pax in pax_with_floors.iterrows():
            board_floor = pax.get("start_floor", "")
            alight_floor = pax.get("end_floor", "")

            if board_floor and board_floor in floor_counts:
                floor_counts[board_floor]["boarding_count"] += 1

            if alight_floor and alight_floor in floor_counts:
                floor_counts[alight_floor]["alighting_count"] += 1

    # Convert to DataFrame
    records = []
    for floor, counts in floor_counts.items():
        records.append({
            "building_name": building,
            "floor_name": floor,
            "stop_count": counts["stop_count"],
            "boarding_count": counts["boarding_count"],
            "alighting_count": counts["alighting_count"]
        })

    df = pd.DataFrame(records)

    # Sort by floor (using floor number)
    def floor_sort_key(floor):
        if floor == "Roof":
            return 100
        if floor.startswith("B"):
            return -int(floor[1:].replace("F", ""))
        return int(floor.replace("F", ""))

    df["_sort"] = df["floor_name"].apply(floor_sort_key)
    df = df.sort_values("_sort").drop("_sort", axis=1)

    return df.reset_index(drop=True)


def calculate_hourly_metrics(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Calculate hourly aggregated metrics

    Returns:
        DataFrame with hourly metrics
    """
    if len(trips_df) == 0:
        return pd.DataFrame()

    # Add hour column
    trips = trips_df.copy()
    trips["hour"] = trips["start_time"].dt.hour

    # Aggregate by hour
    hourly = trips.groupby("hour").agg({
        "trip_id": "count",
        "duration_sec": "sum",
    }).rename(columns={
        "trip_id": "trip_count",
        "duration_sec": "total_duration_sec"
    })

    # Add passenger count from classifications
    hourly["passenger_count"] = 0
    if len(passengers_df) > 0:
        pax = passengers_df.copy()
        pax["hour"] = pax["boarding_time"].dt.hour
        pax_hourly = pax.groupby("hour").size()
        hourly["passenger_count"] = pax_hourly.reindex(hourly.index, fill_value=0).astype(int)

    hourly = hourly.reset_index()
    hourly["total_duration_min"] = hourly["total_duration_sec"] / 60.0

    return hourly


def calculate_building_summary(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame
) -> Dict[str, Dict[str, Any]]:
    """
    Calculate summary metrics by building

    Returns:
        Dict: building_name -> metrics dict
    """
    summary = {}

    for building in trips_df["building_name"].unique():
        building_trips = trips_df[trips_df["building_name"] == building]
        building_pax = passengers_df[
            passengers_df["hoist_name"].isin(building_trips["hoist_name"].unique())
        ]

        summary[building] = {
            "hoist_count": building_trips["hoist_name"].nunique(),
            "trip_count": len(building_trips),
            "total_operating_min": building_trips["duration_sec"].sum() / 60.0,
            "passenger_count": len(building_pax),
            "avg_trip_duration_sec": building_trips["duration_sec"].mean()
        }

    return summary


def calculate_overview_kpis(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    hoist_info: Dict
) -> Dict[str, Any]:
    """
    Calculate KPIs for overview tab

    Returns:
        Dict with KPI values
    """
    total_trips = len(trips_df)
    total_hoists = len(hoist_info)

    # Active hoists (with at least 1 trip)
    active_hoists = trips_df["hoist_name"].nunique() if len(trips_df) > 0 else 0

    # Total passengers
    total_passengers = len(passengers_df)

    # Average trip duration
    avg_duration_sec = trips_df["duration_sec"].mean() if len(trips_df) > 0 else 0

    # Total operating time
    total_operating_min = trips_df["duration_sec"].sum() / 60.0 if len(trips_df) > 0 else 0

    # Peak hour
    if len(trips_df) > 0:
        trips_copy = trips_df.copy()
        trips_copy["hour"] = trips_copy["start_time"].dt.hour
        peak_hour = trips_copy.groupby("hour").size().idxmax()
        peak_trips = trips_copy.groupby("hour").size().max()
    else:
        peak_hour = None
        peak_trips = 0

    # Max passengers per trip
    max_pax_per_trip = 0
    busiest_trip_hoist = ""
    if len(passengers_df) > 0 and "trip_id" in passengers_df.columns:
        pax_per_trip = passengers_df.groupby("trip_id").size()
        if len(pax_per_trip) > 0:
            max_pax_per_trip = int(pax_per_trip.max())
            busiest_trip_id = pax_per_trip.idxmax()
            match = trips_df[trips_df["trip_id"] == busiest_trip_id]
            if len(match) > 0:
                busiest_trip_hoist = match.iloc[0]["hoist_name"]

    # Peak passenger hour
    peak_pax_hour = None
    peak_pax_count = 0
    if len(passengers_df) > 0 and "boarding_time" in passengers_df.columns:
        pax_copy = passengers_df.copy()
        pax_copy["hour"] = pax_copy["boarding_time"].dt.hour
        hourly_pax = pax_copy.groupby("hour").size()
        if len(hourly_pax) > 0:
            peak_pax_hour = int(hourly_pax.idxmax())
            peak_pax_count = int(hourly_pax.max())

    # Busiest hoist
    busiest_hoist = ""
    busiest_hoist_trips = 0
    if len(trips_df) > 0:
        hoist_counts = trips_df["hoist_name"].value_counts()
        busiest_hoist = hoist_counts.index[0]
        busiest_hoist_trips = int(hoist_counts.iloc[0])

    return {
        "total_trips": total_trips,
        "total_hoists": total_hoists,
        "active_hoists": active_hoists,
        "total_passengers": total_passengers,
        "avg_duration_sec": avg_duration_sec,
        "total_operating_min": total_operating_min,
        "peak_hour": peak_hour,
        "peak_trips": peak_trips,
        "max_pax_per_trip": max_pax_per_trip,
        "busiest_trip_hoist": busiest_trip_hoist,
        "peak_pax_hour": peak_pax_hour,
        "peak_pax_count": peak_pax_count,
        "busiest_hoist": busiest_hoist,
        "busiest_hoist_trips": busiest_hoist_trips,
    }


# ============================================================
# Congestion Metrics (v4.0)
# ============================================================

def calculate_congestion_metrics(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    max_passengers: int = 30,
    interval_min: int = 10,
) -> Dict[str, Any]:
    """
    Calculate congestion metrics by hoist and time bin

    Args:
        trips_df: Trip data
        passengers_df: Passenger classification data
        max_passengers: Max capacity per trip (for CI calculation)
        interval_min: Time bin interval in minutes (default 10)

    Returns:
        Dict with hoist_hourly_ci, hourly_summary, building_ci, insights
        Note: 'hoist_hourly_ci' key name kept for backward compatibility,
              but values are now keyed by time_bin (minutes from midnight)
    """
    if len(trips_df) == 0:
        return {
            "hoist_hourly_ci": {},
            "hourly_summary": {},
            "building_ci": {},
            "insights": [],
            "interval_min": interval_min,
        }

    # Map passenger count per trip
    if len(passengers_df) > 0 and "trip_id" in passengers_df.columns:
        pax_counts = passengers_df.groupby("trip_id").size().to_dict()
    else:
        pax_counts = {}

    trips = trips_df.copy()
    trips["hour"] = trips["start_time"].dt.hour
    trips["time_bin"] = (
        trips["start_time"].dt.hour * 60 + trips["start_time"].dt.minute
    ) // interval_min * interval_min
    trips["pax_count"] = trips["trip_id"].map(lambda x: pax_counts.get(x, 0))

    # Hoist × time-bin CI (10-min resolution)
    hoist_hourly_ci = {}
    for hoist in trips["hoist_name"].unique():
        hoist_data = trips[trips["hoist_name"] == hoist]
        hoist_hourly_ci[hoist] = {}

        for tbin in hoist_data["time_bin"].unique():
            bin_data = hoist_data[hoist_data["time_bin"] == tbin]
            trip_count = len(bin_data)
            total_pax = int(bin_data["pax_count"].sum())
            max_pax = int(bin_data["pax_count"].max()) if trip_count > 0 else 0
            ci = total_pax / (max_passengers * trip_count) if trip_count > 0 else 0
            hoist_hourly_ci[hoist][int(tbin)] = {
                "ci": min(ci, 1.0),
                "trips": trip_count,
                "passengers": total_pax,
                "max_pax": max_pax,
            }

    # Hourly summary (kept at 1-hour for backward compat / KPI)
    hourly_summary = {}
    for hour in trips["hour"].unique():
        hour_data = trips[trips["hour"] == hour]
        trip_count = len(hour_data)
        total_pax = int(hour_data["pax_count"].sum())
        ci = total_pax / (max_passengers * trip_count) if trip_count > 0 else 0
        hourly_summary[int(hour)] = {
            "trips": trip_count,
            "passengers": total_pax,
            "ci": min(ci, 1.0)
        }

    # Building CI
    building_ci = {}
    for building in trips["building_name"].unique():
        building_data = trips[trips["building_name"] == building]
        trip_count = len(building_data)
        total_pax = int(building_data["pax_count"].sum())
        ci = total_pax / (max_passengers * trip_count) if trip_count > 0 else 0
        building_ci[building] = min(ci, 1.0)

    # Generate insights
    insights = _generate_congestion_insights(hoist_hourly_ci, hourly_summary, building_ci)

    return {
        "hoist_hourly_ci": hoist_hourly_ci,
        "hourly_summary": hourly_summary,
        "building_ci": building_ci,
        "insights": insights,
        "interval_min": interval_min,
    }


def _generate_congestion_insights(
    hoist_hourly_ci: Dict,
    hourly_summary: Dict,
    building_ci: Dict
) -> List[str]:
    """Generate automatic congestion insights"""
    insights = []

    # 1. Most congested hour
    if hourly_summary:
        peak_hour = max(hourly_summary.keys(), key=lambda h: hourly_summary[h]["ci"])
        peak_ci = hourly_summary[peak_hour]["ci"]
        if peak_ci > 0.3:
            insights.append(
                f"가장 혼잡한 시간대: {peak_hour:02d}:00~{peak_hour+1:02d}:00 (CI={peak_ci:.2f})"
            )

    # 2. Most congested hoist
    max_ci_hoist = None
    max_ci_value = 0
    max_ci_hour = None
    for hoist, hourly in hoist_hourly_ci.items():
        for hour, data in hourly.items():
            if data["ci"] > max_ci_value:
                max_ci_value = data["ci"]
                max_ci_hoist = hoist
                max_ci_hour = hour

    if max_ci_hoist and max_ci_value > 0.4:
        # max_ci_hour can be minutes-from-midnight (10-min bin) or hour
        if max_ci_hour >= 100:  # minutes-from-midnight format
            time_label = f"{max_ci_hour // 60:02d}:{max_ci_hour % 60:02d}"
        else:
            time_label = f"{max_ci_hour:02d}:00"
        insights.append(
            f"{max_ci_hoist} {time_label} 가장 혼잡 (CI={max_ci_value:.2f})"
        )

    # 3. Building with lowest CI (spare capacity)
    if building_ci:
        for building, ci in sorted(building_ci.items(), key=lambda x: x[1]):
            if ci < 0.3:
                insights.append(f"{building} 건물 여유 (평균 CI={ci:.2f})")
                break

    return insights[:5]


def calculate_peak_analysis(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    max_passengers: int = 25
) -> Dict[str, Dict]:
    """
    Analyze 3 peak time windows

    Returns:
        Dict with morning/lunch/evening peak data
    """
    PEAK_WINDOWS = {
        "morning": (6, 8),
        "lunch": (12, 13),
        "evening": (17, 19)
    }

    if len(trips_df) == 0:
        return {k: {"trips": 0, "passengers": 0, "ci": 0.0, "hours": ""} for k in PEAK_WINDOWS}

    trips = trips_df.copy()
    trips["hour"] = trips["start_time"].dt.hour

    if len(passengers_df) > 0 and "trip_id" in passengers_df.columns:
        pax_counts = passengers_df.groupby("trip_id").size().to_dict()
    else:
        pax_counts = {}

    trips["pax_count"] = trips["trip_id"].map(lambda x: pax_counts.get(x, 0))

    result = {}
    for peak_name, (start_hour, end_hour) in PEAK_WINDOWS.items():
        mask = (trips["hour"] >= start_hour) & (trips["hour"] < end_hour)
        peak_trips = trips[mask]

        trip_count = len(peak_trips)
        total_pax = int(peak_trips["pax_count"].sum())
        ci = total_pax / (max_passengers * trip_count) if trip_count > 0 else 0

        result[peak_name] = {
            "trips": trip_count,
            "passengers": total_pax,
            "ci": min(ci, 1.0),
            "hours": f"{start_hour:02d}:00~{end_hour:02d}:00"
        }

    return result


# ============================================================
# Wait Time Metrics (v4.0)
# ============================================================

def calculate_wait_time_metrics(
    trips_df: pd.DataFrame,
    tward_df: pd.DataFrame,
    hoist_info: Dict,
    passengers_df: pd.DataFrame = None,
    rssi_threshold: int = -75,
    max_lookback_sec: int = 1200,  # 20분 — 건설현장은 대기시간이 길 수 있음
) -> Dict[str, Any]:
    """
    Calculate wait time based on ACTUAL PASSENGERS' pre-boarding detection.

    Methodology:
    - For each classified passenger, find when they first appeared near
      the hoist gateway BEFORE the trip started.
    - Wait time = trip_start - first_detection_near_hoist
    - Only passengers who actually boarded are counted.
    - If a worker has a detection gap > 30s, use the latest arrival.

    Args:
        trips_df: Trip data
        tward_df: T-Ward sensor data (required for wait time calc)
        hoist_info: Hoist configuration dict
        passengers_df: Classified passengers (required)
        rssi_threshold: RSSI threshold for detection (-75)
        max_lookback_sec: How far back to look before trip start (300s = 5min)

    Returns:
        Dict with hourly_wait, hoist_wait, summary, insights, methodology
    """
    empty_result = {
        "hourly_wait": {},
        "hoist_wait": {},
        "summary": {"avg_wait": 0, "max_wait": 0, "total_man_min": 0, "total_passengers": 0},
        "insights": [],
        "methodology": (
            "탑승자 기반 대기시간: 실제 호이스트에 탑승한 작업자가 "
            "호이스트 근처에서 처음 감지된 시점부터 탑승 시점까지의 시간. "
            "최대 20분 이전까지 역추적하며, 90초 이상 감지 공백 시 "
            "마지막 도착 시점을 기준으로 합니다. "
            "(BLE 통신 특성상 10%의 신호가 30~90초 누락될 수 있어 이를 허용)"
        ),
    }

    if (
        trips_df is None or len(trips_df) == 0
        or passengers_df is None or len(passengers_df) == 0
        or tward_df is None or len(tward_df) == 0
    ):
        return empty_result

    # Pre-index tward by MAC for fast lookup
    tward_by_mac = {}
    for mac, grp in tward_df.groupby("mac_address"):
        tward_by_mac[mac] = grp.sort_values("insert_datetime")

    # Build gateway set per hoist
    hoist_gateways = {}
    for hname, hinfo in hoist_info.items():
        hoist_gateways[hname] = {hinfo.mov_gateway_no, hinfo.fix_gateway_no}

    # Calculate per-passenger wait time
    wait_records = []
    lookback = pd.Timedelta(seconds=max_lookback_sec)
    # BLE 통신 누락 허용: 95th percentile gap = 90초
    # 30초는 너무 엄격 (정상 감지의 10%가 30초+ gap)
    gap_threshold = pd.Timedelta(seconds=90)

    for _, pax in passengers_df.iterrows():
        mac = pax["mac_address"]
        hoist_name = pax["hoist_name"]
        trip_start = pax["boarding_time"]

        if hoist_name not in hoist_gateways:
            continue
        gateways = hoist_gateways[hoist_name]

        mac_data = tward_by_mac.get(mac)
        if mac_data is None:
            continue

        # Find detections near hoist in [trip_start - lookback, trip_start]
        idx_end = mac_data["insert_datetime"].searchsorted(trip_start, side="right")
        idx_start = mac_data["insert_datetime"].searchsorted(trip_start - lookback)
        window = mac_data.iloc[idx_start:idx_end]

        near_hoist = window[
            (window["gateway_no"].isin(gateways))
            & (window["rssi"] >= rssi_threshold)
        ]

        if len(near_hoist) == 0:
            continue

        # Find effective arrival: if gap > 30s between detections,
        # use the timestamp after the last gap (= latest arrival)
        times = near_hoist["insert_datetime"].values
        arrival = times[0]  # default: first detection

        if len(times) > 1:
            diffs = pd.to_timedelta(
                [times[i] - times[i - 1] for i in range(1, len(times))]
            )
            # Find last gap > 30s
            gap_indices = [i for i, d in enumerate(diffs) if d > gap_threshold]
            if gap_indices:
                # Use the detection AFTER the last big gap
                arrival = times[gap_indices[-1] + 1]

        wait_sec = (trip_start - pd.Timestamp(arrival)).total_seconds()
        if wait_sec < 0:
            wait_sec = 0

        wait_records.append({
            "hoist_name": hoist_name,
            "hour": trip_start.hour,
            "wait_sec": wait_sec,
            "mac_address": mac,
            "trip_id": pax["trip_id"],
        })

    if not wait_records:
        return empty_result

    wait_df = pd.DataFrame(wait_records)

    # Hourly aggregation
    hourly_wait = {}
    for hour, grp in wait_df.groupby("hour"):
        hourly_wait[int(hour)] = {
            "avg_wait": float(grp["wait_sec"].mean()),
            "max_wait": float(grp["wait_sec"].max()),
            "count": len(grp),
        }

    # Hoist aggregation
    hoist_wait = {}
    for hoist, grp in wait_df.groupby("hoist_name"):
        total_man_min = grp["wait_sec"].sum() / 60.0
        hoist_wait[hoist] = {
            "avg_wait": float(grp["wait_sec"].mean()),
            "max_wait": float(grp["wait_sec"].max()),
            "total_man_min": float(total_man_min),
        }

    # Summary
    summary = {
        "avg_wait": float(wait_df["wait_sec"].mean()),
        "max_wait": float(wait_df["wait_sec"].max()),
        "total_man_min": float(wait_df["wait_sec"].sum() / 60.0),
        "total_passengers": len(wait_df),
    }

    # Insights
    insights = _generate_wait_insights(hourly_wait, hoist_wait, summary)

    return {
        "hourly_wait": hourly_wait,
        "hoist_wait": hoist_wait,
        "summary": summary,
        "insights": insights,
        "methodology": empty_result["methodology"],
    }


def _count_waiting_workers(
    tward_df: pd.DataFrame,
    fix_gateway: int,
    start_time,
    end_time,
    rssi_threshold: int
) -> int:
    """Count T-Wards detected at fix_gateway (waiting workers)"""
    if tward_df is None or len(tward_df) == 0:
        return 0

    try:
        mask = (
            (tward_df["gateway_no"] == fix_gateway) &
            (tward_df["insert_datetime"] >= start_time) &
            (tward_df["insert_datetime"] <= end_time) &
            (tward_df["rssi"] >= rssi_threshold)
        )
        waiting_data = tward_df[mask]
        return int(waiting_data["mac_address"].nunique())
    except Exception:
        return 0


def _generate_wait_insights(
    hourly_wait: Dict,
    hoist_wait: Dict,
    summary: Dict
) -> List[str]:
    """Generate automatic wait time insights"""
    insights = []

    # 1. Longest wait hour
    if hourly_wait:
        peak_hour = max(hourly_wait.keys(), key=lambda h: hourly_wait[h]["avg_wait"])
        peak_wait = hourly_wait[peak_hour]["avg_wait"]
        if peak_wait > 30:  # More than 30 seconds
            min_val = int(peak_wait // 60)
            sec_val = int(peak_wait % 60)
            if min_val > 0:
                insights.append(
                    f"가장 긴 대기: {peak_hour:02d}:00~{peak_hour+1:02d}:00 (평균 {min_val}분 {sec_val}초)"
                )
            else:
                insights.append(
                    f"가장 긴 대기: {peak_hour:02d}:00~{peak_hour+1:02d}:00 (평균 {sec_val}초)"
                )

    # 2. Total wait man-minutes
    total_man_min = summary["total_man_min"]
    if total_man_min > 10:
        hours = total_man_min / 60
        insights.append(f"총 대기 인시: {total_man_min:.0f}분 (약 {hours:.1f}시간 생산성 손실)")

    # 3. Hoist addition recommendation
    if hourly_wait:
        peak_hour = max(hourly_wait.keys(), key=lambda h: hourly_wait[h]["avg_wait"])
        if hourly_wait[peak_hour]["avg_wait"] > 120:  # More than 2 min
            insights.append(
                f"{peak_hour:02d}:00 피크 시간대에 호이스트 1대 추가 시 대기시간 약 40% 감소 예상"
            )

    return insights[:5]


# ============================================================
# Management Insights Generator (v4.1)
# ============================================================

def generate_management_insights(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    hoist_info: Dict,
    wait_metrics: Dict = None,
) -> List[Dict[str, Any]]:
    """
    Generate actionable insights for construction site managers.

    Returns a list of insight dictionaries with:
    - type: "efficiency" | "congestion" | "wait_time" | "safety" | "utilization"
    - severity: 1 (info) | 2 (warning) | 3 (critical)
    - title: Short headline
    - detail: Longer explanation with specific data
    - recommendation: Actionable suggestion

    Args:
        trips_df: Trip data
        passengers_df: Passenger data
        hoist_info: Hoist configuration dict
        wait_metrics: Optional pre-calculated wait time metrics

    Returns:
        List of insight dicts sorted by severity (highest first)
    """
    insights = []

    if len(trips_df) == 0:
        return insights

    # Prepare passenger counts per trip
    pax_counts = {}
    if len(passengers_df) > 0 and "trip_id" in passengers_df.columns:
        pax_counts = passengers_df.groupby("trip_id").size().to_dict()

    trips = trips_df.copy()
    trips["pax_count"] = trips["trip_id"].map(lambda x: pax_counts.get(x, 0))
    trips["hour"] = trips["start_time"].dt.hour

    # ========== 1. Utilization Analysis ==========
    hoist_metrics = []
    for hoist in trips["hoist_name"].unique():
        hoist_trips = trips[trips["hoist_name"] == hoist]
        if len(hoist_trips) == 0:
            continue

        operating_sec = hoist_trips["duration_sec"].sum()
        start_time = hoist_trips["start_time"].min()
        end_time = hoist_trips["end_time"].max()
        span_sec = (end_time - start_time).total_seconds()
        utilization = (operating_sec / span_sec * 100) if span_sec > 0 else 0

        hoist_metrics.append({
            "hoist": hoist,
            "building": hoist_trips["building_name"].iloc[0],
            "trip_count": len(hoist_trips),
            "total_pax": hoist_trips["pax_count"].sum(),
            "utilization": utilization,
        })

    if hoist_metrics:
        # Lowest utilization hoist
        min_util = min(hoist_metrics, key=lambda x: x["utilization"])
        if min_util["utilization"] < 15:
            insights.append({
                "type": "efficiency",
                "severity": 2,
                "title": f"{min_util['hoist'].split('_')[-1]} 가동률 저조",
                "detail": (
                    f"{min_util['hoist']}의 가동률이 {min_util['utilization']:.1f}%로 "
                    f"전체 호이스트 중 가장 낮습니다. (운행 {min_util['trip_count']}회)"
                ),
                "recommendation": "운행 스케줄 조정 또는 타 호이스트로 부하 재분배 검토",
            })

        # Highest utilization hoist (overload risk)
        max_util = max(hoist_metrics, key=lambda x: x["utilization"])
        if max_util["utilization"] > 40:
            insights.append({
                "type": "utilization",
                "severity": 2 if max_util["utilization"] < 50 else 3,
                "title": f"{max_util['hoist'].split('_')[-1]} 과부하 위험",
                "detail": (
                    f"{max_util['hoist']}의 가동률이 {max_util['utilization']:.1f}%로 "
                    f"가장 높습니다. 장비 피로 누적 가능성이 있습니다."
                ),
                "recommendation": "정기 점검 주기 단축 또는 부하 분산 검토",
            })

    # ========== 2. Congestion Analysis ==========
    # Peak hour by passengers
    hourly_pax = trips.groupby("hour")["pax_count"].sum()
    if len(hourly_pax) > 0:
        peak_hour = hourly_pax.idxmax()
        peak_pax = hourly_pax.max()

        # Get trips in peak hour
        peak_trips = trips[trips["hour"] == peak_hour]
        avg_pax_per_trip = peak_trips["pax_count"].mean()

        if avg_pax_per_trip >= 15:
            insights.append({
                "type": "congestion",
                "severity": 3,
                "title": f"{peak_hour:02d}:00 시간대 혼잡",
                "detail": (
                    f"{peak_hour:02d}:00~{peak_hour+1:02d}:00 시간대에 "
                    f"총 {int(peak_pax)}명 탑승, 운행당 평균 {avg_pax_per_trip:.1f}명으로 혼잡합니다."
                ),
                "recommendation": "해당 시간대 호이스트 추가 배정 또는 출입 시간 분산 권고",
            })
        elif avg_pax_per_trip >= 10:
            insights.append({
                "type": "congestion",
                "severity": 2,
                "title": f"{peak_hour:02d}:00 시간대 주의",
                "detail": (
                    f"{peak_hour:02d}:00~{peak_hour+1:02d}:00 시간대에 "
                    f"운행당 평균 {avg_pax_per_trip:.1f}명으로 보통 수준입니다."
                ),
                "recommendation": "피크 시간 모니터링 지속",
            })

    # Max passengers in single trip
    if len(trips) > 0:
        max_pax_trip = trips.loc[trips["pax_count"].idxmax()]
        max_pax = max_pax_trip["pax_count"]
        if max_pax >= 20:
            insights.append({
                "type": "safety",
                "severity": 3,
                "title": f"과밀 운행 감지 ({max_pax}명)",
                "detail": (
                    f"{max_pax_trip['hoist_name']} "
                    f"{max_pax_trip['start_time'].strftime('%H:%M')}에 "
                    f"{max_pax}명이 탑승했습니다. 정원 초과 여부를 확인하세요."
                ),
                "recommendation": "해당 호이스트 정원 확인 및 과밀 방지 조치",
            })

    # ========== 3. Building-level Analysis ==========
    building_stats = trips.groupby("building_name").agg({
        "trip_id": "count",
        "pax_count": "sum",
        "duration_sec": "sum",
    }).rename(columns={"trip_id": "trips", "pax_count": "total_pax"})

    if len(building_stats) > 1:
        # Find imbalanced buildings
        max_bldg = building_stats["trips"].idxmax()
        min_bldg = building_stats["trips"].idxmin()
        max_trips = building_stats.loc[max_bldg, "trips"]
        min_trips = building_stats.loc[min_bldg, "trips"]

        if max_trips > min_trips * 3 and min_trips < 100:
            insights.append({
                "type": "efficiency",
                "severity": 1,
                "title": f"건물별 운행 불균형",
                "detail": (
                    f"{max_bldg}은 {max_trips}회 운행, "
                    f"{min_bldg}은 {min_trips}회 운행으로 차이가 큽니다."
                ),
                "recommendation": f"{min_bldg} 건물 작업자 이동 패턴 확인 필요",
            })

    # ========== 4. Wait Time Insights ==========
    if wait_metrics:
        summary = wait_metrics.get("summary", {})
        hoist_wait = wait_metrics.get("hoist_wait", {})

        avg_wait = summary.get("avg_wait", 0)
        total_man_min = summary.get("total_man_min", 0)

        if avg_wait > 180:  # > 3 minutes
            insights.append({
                "type": "wait_time",
                "severity": 3,
                "title": f"평균 대기시간 {avg_wait/60:.1f}분",
                "detail": (
                    f"전체 평균 대기시간이 {avg_wait/60:.1f}분으로 높습니다. "
                    f"총 대기 인시: {total_man_min:.0f}분 ({total_man_min/60:.1f}시간 생산성 손실)"
                ),
                "recommendation": "호이스트 증설 또는 작업 시간대 조정 적극 검토",
            })
        elif avg_wait > 120:  # > 2 minutes
            insights.append({
                "type": "wait_time",
                "severity": 2,
                "title": f"평균 대기시간 {avg_wait/60:.1f}분",
                "detail": (
                    f"전체 평균 대기시간이 {avg_wait/60:.1f}분입니다. "
                    f"총 대기 인시: {total_man_min:.0f}분"
                ),
                "recommendation": "피크 시간대 운행 빈도 증가 검토",
            })

        # Longest wait hoist
        if hoist_wait:
            max_wait_hoist = max(hoist_wait.keys(), key=lambda h: hoist_wait[h]["avg_wait"])
            max_wait_val = hoist_wait[max_wait_hoist]["avg_wait"]
            if max_wait_val > 180:
                insights.append({
                    "type": "wait_time",
                    "severity": 2,
                    "title": f"{max_wait_hoist.split('_')[-1]} 대기시간 가장 김",
                    "detail": (
                        f"{max_wait_hoist} 평균 대기시간: {max_wait_val/60:.1f}분, "
                        f"최대 {hoist_wait[max_wait_hoist]['max_wait']/60:.1f}분"
                    ),
                    "recommendation": "해당 호이스트 배차 간격 단축 또는 추가 배정",
                })

    # ========== 5. Sort by severity ==========
    insights.sort(key=lambda x: x["severity"], reverse=True)

    return insights[:8]  # Return top 8 insights


def calculate_hoist_comparison_data(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    hoist_info: Dict,
    wait_metrics: Dict = None,
) -> pd.DataFrame:
    """
    Calculate comparison data for all hoists in a DataFrame format.

    Returns DataFrame with columns:
    - hoist_name, building_name, trip_count, total_pax, avg_pax, max_pax,
      utilization_pct, avg_wait_sec, is_busiest, is_lowest_util

    Args:
        trips_df: Trip data
        passengers_df: Passenger data
        hoist_info: Hoist configuration dict
        wait_metrics: Optional pre-calculated wait time metrics

    Returns:
        DataFrame with hoist comparison metrics
    """
    if len(trips_df) == 0:
        return pd.DataFrame()

    # Prepare passenger counts per trip
    pax_counts = {}
    if len(passengers_df) > 0 and "trip_id" in passengers_df.columns:
        pax_counts = passengers_df.groupby("trip_id").size().to_dict()

    trips = trips_df.copy()
    trips["pax_count"] = trips["trip_id"].map(lambda x: pax_counts.get(x, 0))

    # Wait time per hoist
    hoist_wait = {}
    if wait_metrics:
        hoist_wait = wait_metrics.get("hoist_wait", {})

    records = []
    for hoist in trips["hoist_name"].unique():
        hoist_trips = trips[trips["hoist_name"] == hoist]
        if len(hoist_trips) == 0:
            continue

        pax_list = hoist_trips["pax_count"].tolist()
        trip_count = len(hoist_trips)
        total_pax = sum(pax_list)
        avg_pax = np.mean(pax_list) if pax_list else 0
        max_pax = max(pax_list) if pax_list else 0

        # Utilization
        operating_sec = hoist_trips["duration_sec"].sum()
        start_time = hoist_trips["start_time"].min()
        end_time = hoist_trips["end_time"].max()
        span_sec = (end_time - start_time).total_seconds()
        utilization = (operating_sec / span_sec * 100) if span_sec > 0 else 0

        # Wait time
        wait_data = hoist_wait.get(hoist, {})
        avg_wait = wait_data.get("avg_wait", 0)

        records.append({
            "hoist_name": hoist,
            "short_name": hoist.split("_")[-1] if "_" in hoist else hoist,
            "building_name": hoist_trips["building_name"].iloc[0],
            "trip_count": trip_count,
            "total_pax": total_pax,
            "avg_pax": round(avg_pax, 1),
            "max_pax": max_pax,
            "utilization_pct": round(utilization, 1),
            "avg_wait_sec": round(avg_wait, 0),
        })

    df = pd.DataFrame(records)

    if len(df) > 0:
        # Mark busiest and lowest utilization
        df["is_busiest"] = df["total_pax"] == df["total_pax"].max()
        df["is_lowest_util"] = df["utilization_pct"] == df["utilization_pct"].min()

        # Sort by building, then trip count descending
        df = df.sort_values(["building_name", "trip_count"], ascending=[True, False])

    return df.reset_index(drop=True)
