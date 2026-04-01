"""
Wait Congestion Analyzer — 대기 혼잡도 분석 (v3 후처리 기반)

후처리 시스템이므로 실제 탑승 데이터(passengers_df)에서 **역추정**한다.
BLE RSSI 기반 실시간 대기 인원 추정은 사용하지 않음 (1F 근처 모든 작업자 감지 문제).

핵심 파라미터:
1. concurrent_waiters: 동시 대기 인원 (실제 탑승자의 대기 시작~탑승 사이 인원 역산)
2. trip_frequency: 시간대별 운행 빈도
3. clearance_time_min: 혼잡 해소 예상 시간
4. congestion_index: 종합 혼잡 지수

역추정 원리:
- 탑승자의 arrival_time = boarding_time - wait_time_sec (호이스트 근처 도착 시점)
- 특정 시점 t의 대기 인원 = arrival_time <= t < boarding_time 인 사람 수
- 이 방식은 **실제 탑승한 사람만** 대상이므로 정확
"""

import logging
from typing import Dict, Any, List
from dataclasses import dataclass

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────
BIN_MINUTES = 10

# 혼잡도 판정 기준
HIGH_QUEUE_THRESHOLD = 15     # 동시 대기 15명+ → 혼잡
MED_QUEUE_THRESHOLD = 8       # 동시 대기 8명+ → 보통
HIGH_PAX_THRESHOLD = 10       # 트립당 10명+ → 혼잡
LONG_GAP_SEC = 300            # 트립 간격 5분+ → 공급 부족


@dataclass
class CongestionBin:
    """10분 bin 단위 혼잡도 데이터"""
    time_bin: int              # minutes from midnight
    concurrent_waiters: float  # 동시 대기 인원 (핵심, 역추정)
    max_waiters: int           # 해당 bin 최대 동시 대기
    trip_count: int            # 운행 횟수
    total_passengers: int      # 탑승 인원
    avg_pax_per_trip: float    # 트립당 평균 탑승
    max_pax_per_trip: int      # 트립당 최대 탑승
    avg_trip_gap_sec: float    # 평균 트립 간격 (초)
    clearance_time_min: float  # 혼잡 해소 예상 시간 (분)
    congestion_level: str      # "HIGH" / "MEDIUM" / "LOW"
    avg_wait_sec: float        # 평균 대기시간


def analyze_wait_congestion(
    tward_df: pd.DataFrame,
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    hoist_info: Dict,
    bin_minutes: int = BIN_MINUTES,
) -> Dict[str, Any]:
    """
    대기 혼잡도 종합 분석 (후처리 역추정)

    Args:
        tward_df: (미사용, 인터페이스 호환)
        trips_df: 호이스트 트립 데이터
        passengers_df: 탑승자 분류 데이터 (boarding_time, wait_time_sec 필수)
        hoist_info: {hoist_name: HoistInfo}
        bin_minutes: 시간 bin 크기

    Returns:
        {
            "hoist_bins": {hoist_name: {time_bin: CongestionBin}},
            "hourly_summary": {hour: {...}},
            "peak_congestion": {...},
            "insights": [str, ...]
        }
    """
    if len(trips_df) == 0 or len(passengers_df) == 0:
        return _empty_result()

    if "boarding_time" not in passengers_df.columns or "wait_time_sec" not in passengers_df.columns:
        logger.warning("passengers_df missing boarding_time or wait_time_sec")
        return _empty_result()

    # ── Step 1: 탑승자별 arrival_time (대기 시작) 계산 ────────────────
    pax = passengers_df.copy()
    pax["arrival_time"] = pax["boarding_time"] - pd.to_timedelta(pax["wait_time_sec"], unit="s")
    pax["hoist_name"] = pax["hoist_name"] if "hoist_name" in pax.columns else ""

    # ── Step 2: 시간 bin별 동시 대기 인원 역추정 ──────────────────────
    # 각 1분 시점에서 arrival_time <= t < boarding_time인 사람 수를 세고,
    # 10분 bin으로 집계
    hoist_names = list(hoist_info.keys()) if hoist_info else pax["hoist_name"].unique().tolist()

    all_bins = []
    hoist_bins_dict = {}

    for hoist_name in hoist_names:
        hoist_pax = pax[pax["hoist_name"] == hoist_name] if "hoist_name" in pax.columns else pax
        hoist_trips = trips_df[trips_df["hoist_name"] == hoist_name] if "hoist_name" in trips_df.columns else trips_df

        # 트립 간격 계산
        hoist_trips_sorted = hoist_trips.sort_values("start_time").copy()
        hoist_trips_sorted["prev_end"] = hoist_trips_sorted["end_time"].shift(1)
        hoist_trips_sorted["trip_gap_sec"] = (
            hoist_trips_sorted["start_time"] - hoist_trips_sorted["prev_end"]
        ).dt.total_seconds()

        hoist_trips_sorted["time_bin"] = (
            hoist_trips_sorted["start_time"].dt.hour * 60
            + hoist_trips_sorted["start_time"].dt.minute
        ) // bin_minutes * bin_minutes

        # 탑승인원 per trip
        pax_per_trip = hoist_pax.groupby("trip_id").size().to_dict() if len(hoist_pax) > 0 else {}
        hoist_trips_sorted["pax"] = hoist_trips_sorted["trip_id"].map(lambda x: pax_per_trip.get(x, 0))

        # 대기 인원 per 1분 → bin 집계
        waiters_by_minute = _compute_waiters_per_minute(hoist_pax)

        hoist_bins_dict[hoist_name] = {}

        for tbin in range(0, 24 * 60, bin_minutes):
            bin_trips = hoist_trips_sorted[hoist_trips_sorted["time_bin"] == tbin]
            trip_count = len(bin_trips)
            total_pax = int(bin_trips["pax"].sum())
            # Exclude empty runs for avg
            trips_w_pax = len(bin_trips[bin_trips["pax"] > 0])
            avg_pax = total_pax / trips_w_pax if trips_w_pax > 0 else 0.0
            max_pax = int(bin_trips["pax"].max()) if trip_count > 0 else 0

            gaps = bin_trips["trip_gap_sec"].dropna()
            avg_gap = float(gaps.mean()) if len(gaps) > 0 else (bin_minutes * 60)

            # 동시 대기 인원 (이 bin의 각 분에서 평균/최대)
            bin_minutes_range = range(tbin, tbin + bin_minutes)
            waiter_vals = [waiters_by_minute.get(m, 0) for m in bin_minutes_range]
            avg_waiters = float(np.mean(waiter_vals))
            max_waiters = int(max(waiter_vals))

            # 대기시간 평균
            bin_pax = hoist_pax[
                (hoist_pax["boarding_time"].dt.hour * 60 + hoist_pax["boarding_time"].dt.minute) // bin_minutes * bin_minutes == tbin
            ]
            avg_wait = float(bin_pax["wait_time_sec"].mean()) if len(bin_pax) > 0 else 0.0

            # 혼잡 해소 시간
            clearance = 0.0
            if avg_waiters > 0 and trip_count > 0 and avg_pax > 0:
                throughput_per_min = (trip_count * avg_pax) / bin_minutes
                clearance = avg_waiters / throughput_per_min if throughput_per_min > 0 else 0
            elif avg_waiters > 0:
                clearance = avg_waiters * bin_minutes

            level = _determine_level(max_pax, max_waiters, avg_gap, trip_count)

            cb = CongestionBin(
                time_bin=tbin,
                concurrent_waiters=round(avg_waiters, 1),
                max_waiters=max_waiters,
                trip_count=trip_count,
                total_passengers=total_pax,
                avg_pax_per_trip=round(avg_pax, 1),
                max_pax_per_trip=max_pax,
                avg_trip_gap_sec=round(avg_gap, 1),
                clearance_time_min=round(clearance, 1),
                congestion_level=level,
                avg_wait_sec=round(avg_wait, 1),
            )
            hoist_bins_dict[hoist_name][tbin] = cb
            all_bins.append(cb)

    # ── Step 3: 전체 (모든 호이스트 합산) 시간별 동시 대기 ────────────
    total_waiters_by_minute = _compute_waiters_per_minute(pax)

    # ── Step 4: 시간대별 요약 ─────────────────────────────────────────
    hourly_summary = _compute_hourly_summary(
        all_bins, total_waiters_by_minute, trips_df, passengers_df, bin_minutes
    )

    # ── Step 5: 피크 혼잡 ─────────────────────────────────────────────
    peak_congestion = _find_peak(total_waiters_by_minute, trips_df, passengers_df, bin_minutes)

    # ── Step 6: 인사이트 ──────────────────────────────────────────────
    insights = _generate_insights(hourly_summary, peak_congestion)

    return {
        "hoist_bins": hoist_bins_dict,
        "hourly_summary": hourly_summary,
        "peak_congestion": peak_congestion,
        "insights": insights,
        "bin_minutes": bin_minutes,
    }


def _compute_waiters_per_minute(pax_df: pd.DataFrame) -> Dict[int, int]:
    """
    각 1분 시점에서 동시 대기 인원 계산 (역추정)

    대기 중 = arrival_time <= 해당 분 < boarding_time
    """
    if len(pax_df) == 0 or "arrival_time" not in pax_df.columns:
        return {}

    # 분 단위로 변환
    pax = pax_df.dropna(subset=["arrival_time", "boarding_time"]).copy()
    if len(pax) == 0:
        return {}

    pax["arrival_min"] = pax["arrival_time"].dt.hour * 60 + pax["arrival_time"].dt.minute
    pax["boarding_min"] = pax["boarding_time"].dt.hour * 60 + pax["boarding_time"].dt.minute

    # 이벤트 기반 집계 (효율적)
    events = {}
    for _, row in pax.iterrows():
        a = int(row["arrival_min"])
        b = int(row["boarding_min"])
        if a >= b:  # wait_time=0 or invalid
            continue
        events[a] = events.get(a, 0) + 1
        events[b] = events.get(b, 0) - 1

    if not events:
        return {}

    # 누적합으로 동시 대기 인원
    waiters = {}
    current = 0
    for minute in range(0, 24 * 60):
        current += events.get(minute, 0)
        waiters[minute] = max(0, current)

    return waiters


def _determine_level(
    max_pax: int,
    max_waiters: int,
    avg_gap: float,
    trip_count: int,
) -> str:
    """혼잡도 레벨 판정"""
    if trip_count == 0:
        return "LOW"

    score = 0
    if max_pax >= HIGH_PAX_THRESHOLD:
        score += 2
    elif max_pax >= HIGH_PAX_THRESHOLD // 2:
        score += 1

    if max_waiters >= HIGH_QUEUE_THRESHOLD:
        score += 2
    elif max_waiters >= MED_QUEUE_THRESHOLD:
        score += 1

    if avg_gap >= LONG_GAP_SEC:
        score += 1

    if score >= 3:
        return "HIGH"
    elif score >= 2:
        return "MEDIUM"
    return "LOW"


def _compute_hourly_summary(
    all_bins: List[CongestionBin],
    total_waiters: Dict[int, int],
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    bin_minutes: int,
) -> Dict[int, Dict]:
    """시간대별 혼잡도 요약"""
    hourly = {}

    for hour in range(24):
        hour_bins = [b for b in all_bins if b.time_bin // 60 == hour]
        if not hour_bins:
            continue

        total_trips = sum(b.trip_count for b in hour_bins)
        total_pax = sum(b.total_passengers for b in hour_bins)
        # Exclude empty runs: use trips that had passengers
        trips_w_pax = sum(1 for b in hour_bins if b.total_passengers > 0 for _ in range(b.trip_count) if b.total_passengers > 0)
        # Simpler: use total_pax / bins with pax * their trip counts
        avg_pax_trip = total_pax / total_trips if total_trips > 0 else 0
        # Better approximation: if we have avg_pax_per_trip per bin, use weighted avg
        if total_pax > 0:
            pax_trips = sum(b.trip_count for b in hour_bins if b.total_passengers > 0)
            avg_pax_trip = total_pax / pax_trips if pax_trips > 0 else 0
        max_pax_trip = max((b.max_pax_per_trip for b in hour_bins), default=0)

        # 동시 대기 인원 (전체 호이스트 합산, 1분 단위)
        hour_minutes = range(hour * 60, (hour + 1) * 60)
        waiter_vals = [total_waiters.get(m, 0) for m in hour_minutes]
        avg_waiters = float(np.mean(waiter_vals)) if waiter_vals else 0
        max_waiters = int(max(waiter_vals)) if waiter_vals else 0

        active_bins = [b for b in hour_bins if b.trip_count > 0]
        avg_gap = float(np.mean([b.avg_trip_gap_sec for b in active_bins])) if active_bins else 0
        avg_clearance = float(np.mean([b.clearance_time_min for b in hour_bins])) if hour_bins else 0
        avg_wait = float(np.mean([b.avg_wait_sec for b in hour_bins if b.avg_wait_sec > 0])) if any(b.avg_wait_sec > 0 for b in hour_bins) else 0

        # 시간대 혼잡도 레벨
        high_count = sum(1 for b in hour_bins if b.congestion_level == "HIGH")
        med_count = sum(1 for b in hour_bins if b.congestion_level == "MEDIUM")

        if high_count >= 3 or max_waiters >= HIGH_QUEUE_THRESHOLD:
            level = "HIGH"
        elif high_count >= 1 or med_count >= 3 or max_waiters >= MED_QUEUE_THRESHOLD:
            level = "MEDIUM"
        else:
            level = "LOW"

        hourly[hour] = {
            "total_trips": total_trips,
            "total_passengers": total_pax,
            "avg_pax_per_trip": round(avg_pax_trip, 1),
            "max_pax_per_trip": max_pax_trip,
            "avg_waiters": round(avg_waiters, 1),
            "max_waiters": max_waiters,
            "avg_queue": round(avg_waiters, 1),  # alias
            "max_queue": round(float(max_waiters), 1),
            "avg_trip_gap_sec": round(avg_gap, 1),
            "avg_clearance_min": round(avg_clearance, 1),
            "avg_wait_sec": round(avg_wait, 1),
            "congestion_level": level,
        }

    return hourly


def _find_peak(
    total_waiters: Dict[int, int],
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    bin_minutes: int,
) -> Dict:
    """피크 혼잡 시점 찾기"""
    if not total_waiters:
        return {}

    peak_minute = max(total_waiters, key=total_waiters.get)
    peak_count = total_waiters[peak_minute]

    # 해당 시점의 트립 정보
    peak_hour = peak_minute // 60
    peak_min = peak_minute % 60

    return {
        "time_label": f"{peak_hour:02d}:{peak_min:02d}",
        "concurrent_waiters": peak_count,
        "peak_minute": peak_minute,
    }


def _generate_insights(
    hourly_summary: Dict,
    peak: Dict,
) -> List[str]:
    """혼잡도 인사이트 생성"""
    insights = []

    if not peak:
        return insights

    # 피크 동시 대기
    insights.append(
        f"최대 동시 대기: {peak.get('time_label', '?')} — "
        f"{peak.get('concurrent_waiters', 0)}명"
    )

    if not hourly_summary:
        return insights

    # 혼잡 시간대
    high_hours = [h for h, v in hourly_summary.items() if v["congestion_level"] == "HIGH"]
    if high_hours:
        labels = [f"{h:02d}시" for h in sorted(high_hours)]
        insights.append(f"혼잡 시간대: {', '.join(labels)}")

    # 새벽 vs 주간 비교
    dawn = [v for h, v in hourly_summary.items() if 0 <= h < 6]
    day = [v for h, v in hourly_summary.items() if 7 <= h < 18]
    if dawn and day:
        dawn_waiters = np.mean([v["avg_waiters"] for v in dawn])
        day_waiters = np.mean([v["avg_waiters"] for v in day])
        dawn_pax = np.mean([v["avg_pax_per_trip"] for v in dawn])
        day_pax = np.mean([v["avg_pax_per_trip"] for v in day])
        insights.append(
            f"새벽(0~5시): 대기 {dawn_waiters:.1f}명, 트립당 {dawn_pax:.1f}명 | "
            f"주간(7~17시): 대기 {day_waiters:.1f}명, 트립당 {day_pax:.1f}명"
        )
        if dawn_waiters < 1.0 and day_waiters > 3.0:
            insights.append(
                "→ 새벽 대기는 거의 없음 — 대기시간이 길어도 혼잡 아님 (단순 체류 패턴)"
            )

    # 공급 부족 시간대
    slow_supply = [
        (h, v) for h, v in hourly_summary.items()
        if v["avg_trip_gap_sec"] > LONG_GAP_SEC and v["total_passengers"] > 10
    ]
    if slow_supply:
        slow_supply.sort(key=lambda x: x[1]["avg_trip_gap_sec"], reverse=True)
        h, v = slow_supply[0]
        insights.append(
            f"공급 부족: {h:02d}시 — 트립 간격 {v['avg_trip_gap_sec']:.0f}초, "
            f"동시 대기 최대 {v['max_waiters']}명"
        )

    return insights


def _empty_result() -> Dict[str, Any]:
    return {
        "hoist_bins": {},
        "hourly_summary": {},
        "peak_congestion": {},
        "insights": [],
        "bin_minutes": BIN_MINUTES,
    }
