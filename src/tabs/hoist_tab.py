"""운행 분석 탭 - Redesigned with two-section layout (v5.2)

Section 1: 전체 운행 현황 (All hoists overview)
Section 2: 호이스트 상세 분석 (Single hoist deep-dive)
"""

import streamlit as st
import pandas as pd
from typing import Dict

from ..ui.components import (
    render_kpi_card, render_section_header, render_empty_state,
    render_passenger_color_legend, render_info_tooltip, render_insight_card,
    render_wait_time_kpis
)
from ..ui.charts import (
    create_trip_gantt_with_passengers, create_floor_heatmap,
    create_pressure_altitude_chart, create_hourly_passenger_line,
    create_elevator_shaft_timeline, create_wait_time_line_chart,
    create_wait_time_comparison_chart, create_congestion_bar_chart,
    create_dual_operation_chart, create_hoist_comparison_chart,
    create_peak_period_comparison_chart,
    create_wait_congestion_chart, create_congestion_clearance_chart
)
from ..analysis.metrics import (
    calculate_hoist_metrics, calculate_wait_time_metrics,
    generate_management_insights, calculate_hoist_comparison_data,
    calculate_all_hoist_metrics, calculate_hourly_metrics
)
from ..utils.llm_interpreter import (
    get_llm_status, generate_wait_time_insight, generate_hoist_efficiency_insight,
    generate_congestion_context_insight, generate_safety_insight,
    render_data_comment, get_cache_key, get_cached_insight, set_cached_insight,
    generate_hoist_usage_insight
)
from ..utils.converters import format_hoist_name


def render_hoist_tab(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    hoist_info: Dict,
    sward_df: pd.DataFrame,
) -> None:
    """
    Render hoist analysis tab (운행 분석) — Redesigned v5.2.

    Two-section layout:
    - Section 1: All-hoists overview with comparison
    - Section 2: Single-hoist detail with deep-dive analysis
    """
    if len(trips_df) == 0:
        render_empty_state(
            "운행 데이터가 없습니다. 데이터 관리 탭에서 처리를 실행하세요.",
            icon=""
        )
        return

    # ==========================================================
    # SECTION 1: 전체 운행 현황
    # ==========================================================
    _render_section1_overview(trips_df, passengers_df, hoist_info, sward_df)

    # Divider
    st.markdown("---")
    st.markdown("<br>", unsafe_allow_html=True)

    # ==========================================================
    # SECTION 2: 호이스트 상세 분석
    # ==========================================================
    _render_section2_detail(trips_df, passengers_df, hoist_info, sward_df)


# ==============================================================
# Section 1: 전체 운행 현황
# ==============================================================


def _render_section1_overview(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    hoist_info: Dict,
    sward_df: pd.DataFrame,
) -> None:
    """Section 1: All hoists overview."""

    render_section_header("전체 운행 현황")

    # --- Summary text ---
    active_hoists = trips_df["hoist_name"].nunique()
    total_trips = len(trips_df)

    # Passenger counts per trip
    pax_counts = {}
    if len(passengers_df) > 0 and "trip_id" in passengers_df.columns:
        pax_counts = passengers_df.groupby("trip_id").size().to_dict()
    trips_copy = trips_df.copy()
    trips_copy["pax_count"] = trips_copy["trip_id"].map(lambda x: pax_counts.get(x, 0))

    total_passengers = len(passengers_df)

    # Find busiest hoist
    hoist_trip_counts = trips_df["hoist_name"].value_counts()
    busiest_hoist = hoist_trip_counts.index[0] if len(hoist_trip_counts) > 0 else ""
    busiest_count = int(hoist_trip_counts.iloc[0]) if len(hoist_trip_counts) > 0 else 0

    # Compute overall utilization (average across all active hoists)
    comparison_df = calculate_hoist_comparison_data(
        trips_df, passengers_df, hoist_info
    )
    avg_utilization = comparison_df["utilization_pct"].mean() if len(comparison_df) > 0 else 0

    # Summary headline
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #1E2330 0%, #1a1f2e 100%);
        border: 1px solid #2D3748;
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 16px;
    ">
        <div style="color: #E2E8F0; font-size: 15px; line-height: 1.8;">
            오늘 <strong style="color: #3B82F6;">{active_hoists}대</strong> 호이스트가
            총 <strong style="color: #3B82F6;">{total_trips}회</strong> 운행,
            <strong style="color: #3B82F6;">{total_passengers}명</strong> 탑승.
            평균 가동률 <strong style="color: #3B82F6;">{avg_utilization:.1f}%</strong>.
        </div>
        <div style="color: #94A3B8; font-size: 13px; margin-top: 4px;">
            가장 바쁜 호이스트: <strong>{format_hoist_name(busiest_hoist)}</strong> ({busiest_count}회)
        </div>
    </div>
    """, unsafe_allow_html=True)

    # --- Metric description toggle ---
    render_info_tooltip(
        "지표 설명",
        "**가동률**: 병합된 가동 블록(트립 간 갭 10분 이하 포함) / 24시간 (1440분). 최대 100%.\n\n"
        "**평균 탑승인원**: 빈 운행(탑승자 0명)을 제외하고 계산. "
        "passengers / trips_with_passengers.\n\n"
        "**운행 횟수**: 호이스트가 층간 이동한 총 횟수.\n\n"
        "**부하 집중**: 전체 운행 중 특정 호이스트 점유율 30% 이상이면 분산 권장."
    )

    # --- Comparison charts ---
    col1, col2 = st.columns(2)

    with col1:
        fig = create_hoist_comparison_chart(trips_df, passengers_df, hoist_info)
        st.plotly_chart(fig, use_container_width=True, key="s1_hoist_comparison")

    with col2:
        fig = create_peak_period_comparison_chart(trips_df, passengers_df)
        st.plotly_chart(fig, use_container_width=True, key="s1_peak_comparison")

    # --- LLM insight for overall comparison ---
    llm_status = get_llm_status()
    if llm_status["ready"] and len(comparison_df) > 0:
        _render_section1_llm_insight(comparison_df, trips_df, passengers_df)

    # --- Detailed comparison table (toggle) ---
    with st.expander("호이스트 비교 테이블", expanded=False):
        if len(comparison_df) > 0:
            display_comp_df = comparison_df[[
                "building_name", "short_name", "trip_count", "total_pax",
                "avg_pax", "max_pax", "utilization_pct"
            ]].copy()

            display_comp_df = display_comp_df.rename(columns={
                "building_name": "건물",
                "short_name": "호이스트",
                "trip_count": "운행(회)",
                "total_pax": "총탑승(명)",
                "avg_pax": "평균(명)",
                "max_pax": "최대(명)",
                "utilization_pct": "가동률(%)",
            })

            st.dataframe(
                display_comp_df,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("비교 데이터가 없습니다.")


def _render_section1_llm_insight(
    comparison_df: pd.DataFrame,
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
) -> None:
    """LLM insight for Section 1: overall hoist comparison."""
    import numpy as np

    total_trips_all = comparison_df["trip_count"].sum()
    if total_trips_all == 0:
        return

    comparison_df = comparison_df.copy()
    comparison_df["trip_share"] = comparison_df["trip_count"] / total_trips_all * 100
    dominant_idx = comparison_df["trip_share"].idxmax()
    dominant_hoist = comparison_df.loc[dominant_idx, "hoist_name"]
    dominant_share = comparison_df.loc[dominant_idx, "trip_share"]

    # Entropy-based imbalance
    shares = comparison_df["trip_share"].values / 100
    n = len(shares)
    if n > 1:
        shares_nonzero = shares[shares > 0]
        if len(shares_nonzero) > 0:
            entropy = -np.sum(shares_nonzero * np.log(shares_nonzero))
            max_entropy = np.log(n)
            imbalance = 1 - (entropy / max_entropy) if max_entropy > 0 else 0
        else:
            imbalance = 0
    else:
        imbalance = 0

    load_imbalance = {
        "dominant_hoist": dominant_hoist,
        "dominant_share": dominant_share,
        "imbalance_score": imbalance,
    }

    hoist_comparison = []
    for _, row in comparison_df.iterrows():
        hoist_comparison.append({
            "hoist": row["hoist_name"],
            "trips": row["trip_count"],
            "avg_pax": row["avg_pax"],
            "max_pax": row["max_pax"],
            "utilization": row["utilization_pct"] / 100,
        })

    efficiency_cache_key = get_cache_key(
        "s1_hoist_efficiency",
        st.session_state.get("date_str", ""),
        str(total_trips_all),
    )
    efficiency_cached = get_cached_insight(efficiency_cache_key)
    if efficiency_cached:
        render_data_comment(efficiency_cached, title="호이스트 운행 AI 분석")
    else:
        with st.spinner("호이스트 운행 분석 중..."):
            efficiency_insight = generate_hoist_efficiency_insight(
                hoist_comparison=hoist_comparison,
                load_imbalance=load_imbalance,
                wait_summary=None,
            )
        if efficiency_insight:
            set_cached_insight(efficiency_cache_key, efficiency_insight)
            render_data_comment(efficiency_insight, title="호이스트 운행 AI 분석")


# ==============================================================
# Section 2: 호이스트 상세 분석
# ==============================================================


def _render_section2_detail(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    hoist_info: Dict,
    sward_df: pd.DataFrame,
) -> None:
    """Section 2: Single hoist deep-dive."""

    render_section_header("호이스트 상세 분석")

    # --- Filters ---
    col1, col2, col3 = st.columns([2, 2, 3])

    with col1:
        buildings = sorted(trips_df["building_name"].unique())
        selected_building = st.selectbox(
            "건물",
            options=buildings,
            key="s2_building"
        )

    with col2:
        available_hoists = sorted(
            trips_df[trips_df["building_name"] == selected_building]["hoist_name"].unique()
        )
        selected_hoist = st.selectbox(
            "호이스트",
            options=list(available_hoists),
            key="s2_hoist"
        )

    with col3:
        time_range = st.slider(
            "시간 범위",
            min_value=0,
            max_value=24,
            value=(0, 24),
            key="s2_time_range"
        )

    # Filter data
    filtered_trips = trips_df[trips_df["hoist_name"] == selected_hoist].copy()
    filtered_passengers = passengers_df[passengers_df["hoist_name"] == selected_hoist].copy()

    # Time filter
    filtered_trips = filtered_trips[
        (filtered_trips["start_time"].dt.hour >= time_range[0]) &
        (filtered_trips["start_time"].dt.hour < time_range[1])
    ]

    if len(filtered_trips) == 0:
        st.info("선택한 호이스트/시간 범위에 데이터가 없습니다.")
        return

    st.markdown("---")

    # --- KPI cards ---
    metrics = calculate_hoist_metrics(filtered_trips, filtered_passengers, selected_hoist)

    cols = st.columns(5)

    with cols[0]:
        render_kpi_card("운행 횟수", metrics.trip_count)

    with cols[1]:
        render_kpi_card(
            "가동률",
            f"{metrics.utilization_rate * 100:.1f}%",
            subtitle="24시간 기준"
        )

    with cols[2]:
        render_kpi_card("총 탑승인원", metrics.total_passengers)

    with cols[3]:
        render_kpi_card(
            "평균 탑승인원",
            f"{metrics.avg_passengers:.1f}명",
            subtitle="빈 운행 제외"
        )

    with cols[4]:
        render_kpi_card(
            "운행 시간",
            f"{metrics.operating_time_min:.0f}분"
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # --- Dual Operation Chart (trip timeline + passengers) ---
    render_section_header("운행 + 탑승인원 뷰")
    render_info_tooltip(
        "운행 + 탑승인원 듀얼 뷰",
        "**위 차트 -- 탑승인원**\n"
        "- 각 운행의 탑승인원을 막대 그래프로 표시\n"
        "- 색상: 회색(5명 미만) / 파랑(5~9명) / 주황(10~19명) / 빨강(20명+)\n\n"
        "**아래 차트 -- 층간 이동**\n"
        "- 호이스트가 어느 층으로 이동했는지 선으로 표시\n"
        "- 마커: 출발/도착 지점"
    )
    render_passenger_color_legend()

    fig = create_dual_operation_chart(
        filtered_trips,
        filtered_passengers,
        selected_hoist,
        time_range=time_range
    )
    st.plotly_chart(fig, use_container_width=True, key="s2_dual_operation")

    st.markdown("<br>", unsafe_allow_html=True)

    # --- Hourly passenger chart (0~24h) ---
    col1, col2 = st.columns(2)

    with col1:
        render_section_header("시간대별 탑승인원")
        if len(filtered_passengers) > 0:
            fig = create_hourly_passenger_line(filtered_passengers)
            st.plotly_chart(fig, use_container_width=True, key="s2_hourly_pax")
        else:
            st.info("탑승자 데이터가 없습니다.")

    with col2:
        render_section_header("층별 활동 히트맵")
        fig = create_floor_heatmap(filtered_trips, selected_building)
        st.plotly_chart(fig, use_container_width=True, key="s2_floor_heatmap")

    st.markdown("<br>", unsafe_allow_html=True)

    # --- Congestion bar chart (10-min interval) ---
    if len(filtered_passengers) > 0:
        render_section_header("시간대별 혼잡도")
        render_info_tooltip(
            "시간대별 혼잡도",
            "**10분 단위**로 해당 시간대의 **최대 탑승인원**(막대)과 **평균 탑승인원**(점선)을 표시합니다.\n\n"
            "- 빨간 막대: 20명 이상 (혼잡)\n"
            "- 주황 막대: 10~19명 (보통)\n"
            "- 파란 막대: 5~9명 (여유)\n"
            "- 회색 막대: 4명 이하"
        )

        fig = create_congestion_bar_chart(
            filtered_trips, filtered_passengers, selected_hoist
        )
        st.plotly_chart(fig, use_container_width=True, key="s2_congestion_bar")

    st.markdown("<br>", unsafe_allow_html=True)

    # --- Wait Time Analysis ---
    _render_wait_time_section(
        filtered_trips, filtered_passengers, hoist_info, selected_hoist
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # --- Wait Congestion Analysis ---
    _render_wait_congestion_section(
        filtered_trips, filtered_passengers, hoist_info
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # --- LLM insights ---
    llm_status = get_llm_status()
    if llm_status["ready"]:
        _render_section2_llm_insights(
            filtered_trips, filtered_passengers, hoist_info, selected_hoist
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # --- Floor movement pattern ---
    _render_floor_pattern_section(filtered_trips, selected_hoist)

    st.markdown("<br>", unsafe_allow_html=True)

    # --- Pressure profile ---
    if selected_hoist in hoist_info:
        render_section_header("기압 프로파일")
        hoist = hoist_info[selected_hoist]
        fig = create_pressure_altitude_chart(
            sward_df,
            selected_hoist,
            hoist.mov_gateway_no,
            hoist.fix_gateway_no
        )
        st.plotly_chart(fig, use_container_width=True, key="s2_pressure")

    # --- Trip detail table (toggle) ---
    with st.expander("운행 상세 목록", expanded=False):
        _render_trip_detail_table(filtered_trips, filtered_passengers)


# ==============================================================
# Wait Time Section
# ==============================================================


def _render_wait_time_section(
    filtered_trips: pd.DataFrame,
    filtered_passengers: pd.DataFrame,
    hoist_info: Dict,
    selected_hoist: str,
) -> None:
    """Render wait time analysis for Section 2."""
    render_section_header("대기시간 분석")
    render_info_tooltip(
        "EWT (Estimated Wait Time)",
        "**측정 방식**: 실제 호이스트에 탑승한 작업자의 데이터에서 추출합니다.\n\n"
        "1. v4.5 Rate-Matching으로 탑승이 확인된 작업자(T-Ward)를 대상으로\n"
        "2. 해당 작업자가 호이스트 근처에서 **RSSI가 처음 감지된 시점**을 역추적\n"
        "3. **대기시간 = 실제 탑승(boarding) 시점 - 호이스트 근처 RSSI 최초 감지 시점**\n\n"
        "- 최대 20분 이전까지 역추적 (건설현장 특성 반영)\n"
        "- 90초 이상 감지 공백 시, 마지막 도착 시점을 기준\n"
        "- **총 대기 인시** = 전체 탑승자의 대기시간 합계 (생산성 손실 지표)"
    )

    @st.cache_data(ttl=600, show_spinner="T-Ward 데이터 로딩 중...")
    def _load_tward(date_str):
        from ..data.cache_manager import CacheManager
        from ..data.loader import load_device_data
        from ..utils.config import CACHE_DIR, CLOUD_MODE
        cm = CacheManager(CACHE_DIR)
        tward = cm.load_tward(date_str)
        if tward is None and not CLOUD_MODE:
            tward = load_device_data(date_str, tward_only=True)
            if tward is not None and len(tward) > 0:
                cm.save_tward(tward, date_str)
        return tward

    with st.spinner("대기시간 분석 중..."):
        tward_df = _load_tward(st.session_state.get("date_str", "20260326"))
        wait_metrics = calculate_wait_time_metrics(
            filtered_trips, tward_df, hoist_info,
            passengers_df=filtered_passengers,
        )

    # Store in session state for LLM use
    st.session_state["_s2_wait_metrics"] = wait_metrics

    # KPI cards
    render_wait_time_kpis(
        wait_metrics["summary"]["avg_wait"],
        wait_metrics["summary"]["max_wait"],
        wait_metrics["summary"]["total_man_min"]
    )

    # 10-min wait chart + hoist comparison
    c1, c2 = st.columns(2)
    with c1:
        bin_wait = wait_metrics.get("bin_wait", {})
        if bin_wait:
            fig = create_wait_time_line_chart(bin_wait, bin_mode=True)
            st.plotly_chart(fig, use_container_width=True, key="s2_wait_line_10m")
        else:
            fig = create_wait_time_line_chart(wait_metrics["hourly_wait"])
            st.plotly_chart(fig, use_container_width=True, key="s2_wait_line")
    with c2:
        fig = create_wait_time_comparison_chart(wait_metrics["hoist_wait"])
        st.plotly_chart(fig, use_container_width=True, key="s2_wait_comparison")

    # Hoist wait detail table
    hoist_wait = wait_metrics.get("hoist_wait", {})
    if hoist_wait:
        with st.expander("호이스트별 대기시간 상세", expanded=False):
            rows = []
            for hname, hw in sorted(hoist_wait.items()):
                avg_sec = hw.get("avg_wait", 0)
                max_sec = hw.get("max_wait", 0)
                man_min = hw.get("total_man_min", 0)
                building = hname.split("_")[0] if "_" in hname else ""
                if avg_sec > 180:
                    grade = "위험"
                elif avg_sec > 90:
                    grade = "주의"
                elif avg_sec > 30:
                    grade = "보통"
                else:
                    grade = "양호"
                rows.append({
                    "건물": building,
                    "호이스트": hname.replace("_", " "),
                    "평균 대기(초)": round(avg_sec, 0),
                    "최대 대기(초)": round(max_sec, 0),
                    "총 대기(분)": round(man_min, 1),
                    "등급": grade,
                })
            detail_df = pd.DataFrame(rows)

            def _color_grade(val):
                colors = {
                    "위험": "color: #EF4444", "주의": "color: #F59E0B",
                    "보통": "color: #6B7280", "양호": "color: #10B981"
                }
                return colors.get(val, "")

            st.dataframe(
                detail_df.style.map(_color_grade, subset=["등급"]),
                use_container_width=True, hide_index=True
            )

    # Rule-based insights
    render_insight_card(wait_metrics["insights"], title="대기시간 기반 인사이트")


# ==============================================================
# Wait Congestion Section
# ==============================================================


def _render_wait_congestion_section(
    filtered_trips: pd.DataFrame,
    filtered_passengers: pd.DataFrame,
    hoist_info: Dict,
) -> None:
    """Render wait-congestion analysis for Section 2."""
    render_section_header("대기 혼잡도 분석")
    render_info_tooltip(
        "대기 혼잡도 분석",
        "**대기 인원 x 트립 빈도 기반** 혼잡도 분석입니다.\n\n"
        "- **대기 큐 추정**: 트립당 탑승인원과 대기시간에서 역추정한 대기 인원\n"
        "- **트립 간격**: 호이스트 운행 간격 (짧을수록 공급 원활)\n"
        "- **혼잡 해소 시간**: 현재 대기 큐를 해소하는데 걸리는 예상 시간"
    )

    try:
        from ..analysis.congestion_analyzer import analyze_wait_congestion

        tward_df = st.session_state.get("tward_df", pd.DataFrame())

        congestion_result = analyze_wait_congestion(
            tward_df, filtered_trips, filtered_passengers, hoist_info
        )

        hoist_bins_data = congestion_result.get("hoist_bins", {})
        cong_bin_min = congestion_result.get("bin_minutes", 10)

        # 10-min aggregate across all hoists
        bin_summary = {}
        for tbin in range(0, 24 * 60, cong_bin_min):
            total_waiters = 0.0
            total_trips = 0
            total_pax = 0
            max_pax = 0
            gap_vals = []
            clearance_vals = []
            wait_vals = []
            levels = []

            for hoist_name, bins_dict in hoist_bins_data.items():
                cb = bins_dict.get(tbin)
                if cb is None:
                    continue
                total_waiters += cb.concurrent_waiters
                total_trips += cb.trip_count
                total_pax += cb.total_passengers
                max_pax = max(max_pax, cb.max_pax_per_trip)
                if cb.trip_count > 0:
                    gap_vals.append(cb.avg_trip_gap_sec)
                if cb.clearance_time_min > 0:
                    clearance_vals.append(cb.clearance_time_min)
                if cb.avg_wait_sec > 0:
                    wait_vals.append(cb.avg_wait_sec)
                levels.append(cb.congestion_level)

            avg_pax = total_pax / total_trips if total_trips > 0 else 0
            avg_gap = sum(gap_vals) / len(gap_vals) if gap_vals else 0
            avg_clearance = sum(clearance_vals) / len(clearance_vals) if clearance_vals else 0
            avg_wait = sum(wait_vals) / len(wait_vals) if wait_vals else 0

            high_count = levels.count("HIGH")
            med_count = levels.count("MEDIUM")
            level = (
                "HIGH" if high_count >= 2
                else "MEDIUM" if high_count >= 1 or med_count >= 2
                else "LOW"
            )

            bin_summary[tbin] = {
                "avg_waiters": round(total_waiters, 1),
                "total_trips": total_trips,
                "total_passengers": total_pax,
                "avg_pax_per_trip": round(avg_pax, 1),
                "max_pax_per_trip": max_pax,
                "avg_trip_gap_sec": round(avg_gap, 1),
                "avg_clearance_min": round(avg_clearance, 1),
                "avg_wait_sec": round(avg_wait, 1),
                "congestion_level": level,
            }

        if bin_summary:
            col_cong1, col_cong2 = st.columns(2)

            with col_cong1:
                fig = create_wait_congestion_chart(bin_summary, cong_bin_min)
                st.plotly_chart(fig, use_container_width=True, key="s2_wait_congestion")

            with col_cong2:
                fig = create_congestion_clearance_chart(bin_summary, cong_bin_min)
                st.plotly_chart(fig, use_container_width=True, key="s2_clearance")

            # Insights
            cong_insights = congestion_result.get("insights", [])
            if cong_insights:
                with st.expander("대기 혼잡도 인사이트", expanded=False):
                    for ins in cong_insights:
                        st.markdown(f"- {ins}")

                    peak = congestion_result.get("peak_congestion", {})
                    if peak:
                        st.markdown("---")
                        st.markdown(
                            f"**피크**: {peak.get('time_label', '?')} "
                            f"{peak.get('hoist', '?')} -- "
                            f"1회 최대 {peak.get('max_pax_per_trip', 0)}명, "
                            f"대기큐 {peak.get('estimated_queue', 0):.0f}명, "
                            f"해소 {peak.get('clearance_time_min', 0):.1f}분"
                        )
    except Exception as e:
        st.caption(f"혼잡도 분석 로드 실패: {e}")


# ==============================================================
# Section 2 LLM Insights
# ==============================================================


def _render_section2_llm_insights(
    filtered_trips: pd.DataFrame,
    filtered_passengers: pd.DataFrame,
    hoist_info: Dict,
    selected_hoist: str,
) -> None:
    """LLM insights for the selected hoist."""
    render_section_header("AI 인사이트")

    wait_metrics = st.session_state.get("_s2_wait_metrics", {})

    # Context data
    hourly_pax = {}
    hourly_trips_count = {}
    if len(filtered_passengers) > 0:
        pax_merged = filtered_passengers.merge(
            filtered_trips[["trip_id", "start_time"]], on="trip_id", how="left"
        )
        if "start_time" in pax_merged.columns:
            pax_merged["hour"] = pax_merged["start_time"].dt.hour
            hourly_pax = pax_merged.groupby("hour").size().to_dict()
    if len(filtered_trips) > 0:
        hourly_trips_count = filtered_trips.groupby(
            filtered_trips["start_time"].dt.hour
        ).size().to_dict()

    summary = wait_metrics.get("summary", {})
    hourly_w = wait_metrics.get("hourly_wait", {})
    hoist_w = wait_metrics.get("hoist_wait", {})
    hoist_wait_avg = {h: v.get("avg_wait", 0) for h, v in hoist_w.items()}
    hourly_wait_avg = {h: v.get("avg_wait", 0) for h, v in hourly_w.items()}

    # 1) Wait time AI insight
    wait_cache_key = get_cache_key(
        "s2_wait_time",
        st.session_state.get("date_str", ""),
        selected_hoist,
    )
    wait_cached = get_cached_insight(wait_cache_key)
    if wait_cached:
        render_data_comment(wait_cached, title="대기시간 AI 해석")
    else:
        with st.spinner("대기시간 AI 분석 중..."):
            llm_result = generate_wait_time_insight(
                avg_wait=summary.get("avg_wait", 0),
                max_wait=summary.get("max_wait", 0),
                hoist_wait=hoist_wait_avg,
                hourly_wait=hourly_wait_avg,
                hourly_passengers=hourly_pax,
                hourly_trips=hourly_trips_count,
            )
        if llm_result:
            set_cached_insight(wait_cache_key, llm_result)
            render_data_comment(llm_result, title="대기시간 AI 해석")

    # 2) Congestion x wait time cross-analysis
    hourly_ci = {}
    if len(filtered_passengers) > 0 and len(filtered_trips) > 0:
        for h in range(0, 24):
            h_trips = filtered_trips[filtered_trips["start_time"].dt.hour == h]
            if len(h_trips) > 0:
                trip_ids = h_trips["trip_id"].tolist()
                h_pax = filtered_passengers[filtered_passengers["trip_id"].isin(trip_ids)]
                avg_pax = len(h_pax) / len(h_trips) if len(h_trips) > 0 else 0
                hourly_ci[h] = round(avg_pax / 25, 2)

    context_cache_key = get_cache_key(
        "s2_wait_cong_context",
        st.session_state.get("date_str", ""),
        selected_hoist,
        str(hourly_ci),
    )
    context_cached = get_cached_insight(context_cache_key)
    if context_cached:
        render_data_comment(context_cached, title="혼잡도 x 대기시간 교차 분석")
    else:
        with st.spinner("교차 분석 중..."):
            context_insight = generate_congestion_context_insight(
                hourly_ci=hourly_ci,
                hourly_wait=hourly_wait_avg,
                hourly_passengers=hourly_pax,
                hourly_trips=hourly_trips_count,
            )
        if context_insight:
            set_cached_insight(context_cache_key, context_insight)
            render_data_comment(context_insight, title="혼잡도 x 대기시간 교차 분석")


# ==============================================================
# Floor Pattern Section
# ==============================================================


def _render_floor_pattern_section(
    filtered_trips: pd.DataFrame,
    selected_hoist: str,
) -> None:
    """Render floor movement pattern for the selected hoist."""
    render_section_header("층별 이동 패턴")

    if len(filtered_trips) == 0:
        st.info("운행 데이터가 없습니다.")
        return

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**출발 층 빈도**")
        start_floors = filtered_trips["start_floor"].value_counts()
        if len(start_floors) > 0:
            import plotly.express as px
            from ..ui.styles import COLORS, apply_dark_layout

            fig = px.bar(
                x=start_floors.head(5).index,
                y=start_floors.head(5).values,
                color_discrete_sequence=[COLORS["primary"]]
            )
            fig.update_layout(
                xaxis_title="층", yaxis_title="횟수",
                height=250, showlegend=False
            )
            fig = apply_dark_layout(fig)
            st.plotly_chart(fig, use_container_width=True, key="s2_start_floors")

    with col2:
        st.markdown("**도착 층 빈도**")
        end_floors = filtered_trips["end_floor"].value_counts()
        if len(end_floors) > 0:
            import plotly.express as px
            from ..ui.styles import COLORS, apply_dark_layout

            fig = px.bar(
                x=end_floors.head(5).index,
                y=end_floors.head(5).values,
                color_discrete_sequence=["#22C55E"]
            )
            fig.update_layout(
                xaxis_title="층", yaxis_title="횟수",
                height=250, showlegend=False
            )
            fig = apply_dark_layout(fig)
            st.plotly_chart(fig, use_container_width=True, key="s2_end_floors")

    # Low/high floor separation detection
    start_counts = filtered_trips["start_floor"].value_counts()
    end_counts = filtered_trips["end_floor"].value_counts()

    def _floor_num(f):
        if f == "Roof":
            return 100
        if f.startswith("B"):
            return -int(f[1:].replace("F", ""))
        return int(f.replace("F", ""))

    # Check for low/high floor separation
    all_floors_set = set(start_counts.index) | set(end_counts.index)
    if len(all_floors_set) > 2:
        floor_nums = sorted([_floor_num(f) for f in all_floors_set])
        mid = (floor_nums[0] + floor_nums[-1]) / 2

        low_trips = filtered_trips[
            filtered_trips["start_floor"].apply(_floor_num) <= mid
        ]
        high_trips = filtered_trips[
            filtered_trips["start_floor"].apply(_floor_num) > mid
        ]

        if len(low_trips) > 0 and len(high_trips) > 0:
            low_pct = len(low_trips) / len(filtered_trips) * 100
            high_pct = len(high_trips) / len(filtered_trips) * 100
            if abs(low_pct - high_pct) > 20:
                dominant = "저층" if low_pct > high_pct else "고층"
                st.caption(
                    f"층별 운행 편차: {dominant} 위주 운행 "
                    f"(저층 {low_pct:.0f}% / 고층 {high_pct:.0f}%)"
                )


# ==============================================================
# Trip Detail Table
# ==============================================================


def _render_trip_detail_table(
    filtered_trips: pd.DataFrame,
    filtered_passengers: pd.DataFrame,
) -> None:
    """Render trip detail table."""
    if len(filtered_trips) == 0:
        st.info("선택한 조건에 해당하는 운행이 없습니다.")
        return

    display_df = filtered_trips[[
        "trip_id", "hoist_name", "start_time", "end_time",
        "duration_sec", "start_floor", "end_floor", "direction"
    ]].copy()

    # Add passenger count
    if len(filtered_passengers) > 0 and "trip_id" in filtered_passengers.columns:
        pax_counts = filtered_passengers.groupby("trip_id").size()
        display_df["passengers"] = display_df["trip_id"].map(pax_counts).fillna(0).astype(int)
    else:
        display_df["passengers"] = display_df.get("passenger_count", 0)

    display_df["start_time"] = display_df["start_time"].dt.strftime("%H:%M:%S")
    display_df["end_time"] = display_df["end_time"].dt.strftime("%H:%M:%S")
    display_df["duration_min"] = (display_df["duration_sec"] / 60).round(1)

    direction_labels = {"up": "상승", "down": "하강", "round": "왕복"}
    display_df["direction"] = display_df["direction"].map(
        lambda x: direction_labels.get(x, x)
    )

    display_df = display_df.rename(columns={
        "trip_id": "운행#",
        "hoist_name": "호이스트",
        "start_time": "시작",
        "end_time": "종료",
        "duration_min": "소요(분)",
        "start_floor": "출발층",
        "end_floor": "도착층",
        "direction": "방향",
        "passengers": "탑승(명)"
    })

    display_df = display_df.drop("duration_sec", axis=1)

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )
