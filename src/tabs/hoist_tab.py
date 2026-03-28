"""운행 분석 탭 - Hoist analysis with integrated passenger view (Dark Theme)"""

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
    create_peak_period_comparison_chart
)
from ..analysis.metrics import (
    calculate_hoist_metrics, calculate_wait_time_metrics,
    generate_management_insights, calculate_hoist_comparison_data
)
from ..utils.llm_interpreter import (
    get_llm_status, generate_wait_time_insight,
    render_data_comment, get_cache_key, get_cached_insight, set_cached_insight
)


def render_hoist_tab(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    hoist_info: Dict,
    sward_df: pd.DataFrame,
) -> None:
    """
    Render hoist analysis tab (운행 분석)

    Args:
        trips_df: DataFrame with trip data
        passengers_df: DataFrame with passenger classifications
        hoist_info: Dict of hoist configurations
        sward_df: S-Ward sensor data
    """
    if len(trips_df) == 0:
        render_empty_state(
            "운행 데이터가 없습니다. 데이터 관리 탭에서 처리를 실행하세요.",
            icon=""
        )
        return

    # ============================
    # Filters
    # ============================
    col1, col2, col3 = st.columns([2, 2, 3])

    with col1:
        buildings = sorted(trips_df["building_name"].unique())
        selected_building = st.selectbox(
            "건물",
            options=["전체"] + buildings,
            key="hoist_building"
        )

    with col2:
        # Filter hoists by building
        if selected_building == "전체":
            available_hoists = sorted(trips_df["hoist_name"].unique())
        else:
            available_hoists = sorted(
                trips_df[trips_df["building_name"] == selected_building]["hoist_name"].unique()
            )

        selected_hoist = st.selectbox(
            "호이스트",
            options=["전체"] + list(available_hoists),
            key="hoist_select"
        )

    with col3:
        # Time range filter
        if len(trips_df) > 0 and trips_df["start_time"].notna().any():
            min_hour = int(trips_df["start_time"].dt.hour.min())
            max_hour = int(trips_df["end_time"].dt.hour.max())
        else:
            min_hour, max_hour = 7, 22

        # Default to work hours (6~20) for faster initial render
        default_start = max(min_hour, 6)
        default_end = min(max_hour + 1, 21)
        time_range = st.slider(
            "시간 범위",
            min_value=min_hour,
            max_value=max_hour + 1,
            value=(default_start, default_end),
            key="hoist_time_range"
        )

    # Filter data
    filtered_trips = trips_df.copy()
    filtered_passengers = passengers_df.copy()

    if selected_building != "전체":
        filtered_trips = filtered_trips[filtered_trips["building_name"] == selected_building]
        filtered_passengers = filtered_passengers[
            filtered_passengers["hoist_name"].isin(filtered_trips["hoist_name"].unique())
        ]

    if selected_hoist != "전체":
        filtered_trips = filtered_trips[filtered_trips["hoist_name"] == selected_hoist]
        filtered_passengers = filtered_passengers[
            filtered_passengers["hoist_name"] == selected_hoist
        ]

    # Time filter
    filtered_trips = filtered_trips[
        (filtered_trips["start_time"].dt.hour >= time_range[0]) &
        (filtered_trips["start_time"].dt.hour < time_range[1])
    ]

    st.markdown("---")

    # ============================
    # Hoist KPIs (when single hoist selected)
    # ============================
    if selected_hoist != "전체" and selected_hoist in hoist_info:
        metrics = calculate_hoist_metrics(filtered_trips, filtered_passengers, selected_hoist)

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            render_kpi_card("운행 횟수", metrics.trip_count)

        with col2:
            render_kpi_card(
                "운행 시간",
                f"{metrics.operating_time_min:.1f}분"
            )

        with col3:
            render_kpi_card(
                "가동률",
                f"{metrics.utilization_rate * 100:.1f}%"
            )

        with col4:
            render_kpi_card("탑승인원", metrics.total_passengers)

        st.markdown("<br>", unsafe_allow_html=True)

    # ============================
    # Main Chart: Dual Operation Chart (NEW v4.1)
    # ============================
    render_section_header("운행 + 탑승인원 듀얼 뷰")
    render_info_tooltip(
        "운행 + 탑승인원 듀얼 뷰",
        "**두 개의 차트를 동기화된 X축(시간)으로 표시합니다.**\n\n"
        "**위 차트 — 탑승인원**\n"
        "- 각 운행의 탑승인원을 막대 그래프로 표시\n"
        "- 색상: 회색(5명 미만) → 파랑(5~9명) → 주황(10~19명) → 빨강(20명+)\n"
        "- 점선: 혼잡 기준선 (10명, 20명)\n\n"
        "**아래 차트 — 층간 이동**\n"
        "- 호이스트가 어느 층으로 이동했는지 선으로 표시\n"
        "- 호이스트별 다른 색상으로 구분\n"
        "- 마커: 출발/도착 지점\n\n"
        "**활용**: 특정 시간대에 어느 층에서 혼잡이 발생하는지 한 눈에 파악"
    )
    render_passenger_color_legend()

    hoist_filter = selected_hoist if selected_hoist != "전체" else None
    fig = create_dual_operation_chart(
        filtered_trips,
        filtered_passengers,
        hoist_filter,
        time_range=time_range
    )
    st.plotly_chart(fig, use_container_width=True, key="hoist_dual_operation")

    # ============================
    # Legacy: Elevator Shaft Timeline (collapsible)
    # ============================
    with st.expander("기존 샤프트 타임라인 (마커 크기 버전)", expanded=False):
        render_info_tooltip(
            "엘리베이터 샤프트 타임라인",
            "**X축**: 시간 (24시간)\n"
            "**Y축**: 층 (1F~10F)\n"
            "**선**: 호이스트의 층간 이동 경로\n"
            "**마커 크기**: 해당 trip의 탑승인원에 비례 (클수록 많음)\n"
            "**마커 색상**: 탑승인원 밀도 (초록=적음, 빨강=많음)\n\n"
            "호이스트가 어느 시간에 어느 층으로 이동했는지,\n"
            "그때 몇 명이 탑승했는지를 한 눈에 파악할 수 있습니다."
        )
        fig = create_elevator_shaft_timeline(
            filtered_trips,
            filtered_passengers,
            hoist_filter
        )
        st.plotly_chart(fig, use_container_width=True, key="hoist_shaft_timeline")

    # ============================
    # Wait Time Analysis (v4.0) — Deferred loading (expander)
    # ============================
    wait_metrics = None  # Lazy — computed only when expanded

    with st.expander("대기시간 분석 (클릭하여 로드)", expanded=False):
        render_info_tooltip(
            "EWT (Estimated Wait Time) — 탑승자 기반 대기시간",
            "**측정 방식**: 실제 호이스트에 탑승한 작업자의 데이터에서 추출합니다.\n\n"
            "1. 탑승이 확인된 작업자(T-Ward)를 대상으로\n"
            "2. 해당 작업자가 호이스트 근처(S-Ward)에서 **처음 감지된 시점**을 역추적\n"
            "3. **대기시간 = 탑승 시점 - 호이스트 근처 최초 감지 시점**\n\n"
            "- 최대 20분 이전까지 역추적 (건설현장 특성 반영)\n"
            "- 90초 이상 감지 공백 시, 마지막 도착 시점을 기준 (BLE 통신 누락 허용)\n"
            "- 대기하다 탑승하지 않은 작업자는 포함되지 않음\n\n"
            "**총 대기 인시** = 전체 탑승자의 대기시간 합계 (생산성 손실 지표)"
        )

        @st.cache_data(ttl=600, show_spinner="T-Ward 데이터 로딩 중...")
        def _load_tward(date_str):
            from ..data.cache_manager import CacheManager
            from ..utils.config import CACHE_DIR
            return CacheManager(CACHE_DIR).load_tward(date_str)

        tward_df = _load_tward(st.session_state.get("date_str", "20260326"))

        # T-Ward 데이터가 없으면 대기시간 분석 불가 (Cloud 모드에서는 tward parquet 미포함)
        if tward_df is None or len(tward_df) == 0:
            st.info("대기시간 분석을 위한 T-Ward 데이터가 없습니다. (Cloud 모드에서는 지원되지 않습니다)")
        else:
            with st.spinner("대기시간 분석 중..."):
                wait_metrics = calculate_wait_time_metrics(
                    filtered_trips, tward_df, hoist_info,
                    passengers_df=filtered_passengers,
                )

            render_wait_time_kpis(
                wait_metrics["summary"]["avg_wait"],
                wait_metrics["summary"]["max_wait"],
                wait_metrics["summary"]["total_man_min"]
            )

            c1, c2 = st.columns(2)
            with c1:
                fig = create_wait_time_line_chart(wait_metrics["hourly_wait"])
                st.plotly_chart(fig, use_container_width=True, key="hoist_wait_line")
            with c2:
                fig = create_wait_time_comparison_chart(wait_metrics["hoist_wait"])
                st.plotly_chart(fig, use_container_width=True, key="hoist_wait_comparison")

            render_insight_card(wait_metrics["insights"], title="대기시간 기반 인사이트")

    # ============================
    # Secondary Chart: Traditional Gantt View
    # ============================
    with st.expander("기존 Gantt 뷰 (운행 + 탑승인원)", expanded=False):
        building_filter = selected_building if selected_building != "전체" else None
        fig = create_trip_gantt_with_passengers(
            filtered_trips,
            filtered_passengers,
            building_filter
        )
        st.plotly_chart(fig, use_container_width=True, key="hoist_gantt")

    # ============================
    # Congestion Bar Chart (10-min interval)
    # ============================
    if len(filtered_passengers) > 0:
        render_section_header("시간대별 혼잡도")
        render_info_tooltip(
            "시간대별 혼잡도",
            "**10분 단위**로 해당 시간대의 **최대 탑승인원**(막대)과 **평균 탑승인원**(점선)을 표시합니다.\n\n"
            "- **빨간 막대**: 20명 이상 (혼잡)\n"
            "- **주황 막대**: 10~19명 (보통)\n"
            "- **파란 막대**: 5~9명 (여유)\n"
            "- **회색 막대**: 4명 이하\n\n"
            "호이스트를 선택하면 해당 호이스트만, '전체'면 모든 호이스트의 최대값을 보여줍니다.\n"
            "hover 시 평균 탑승인원과 운행 횟수도 확인할 수 있습니다."
        )

        hoist_for_chart = selected_hoist if selected_hoist != "전체" else None
        fig = create_congestion_bar_chart(
            filtered_trips, filtered_passengers, hoist_for_chart
        )
        st.plotly_chart(fig, use_container_width=True, key="hoist_congestion_bar")

    # ============================
    # Two column layout for heatmap and pressure
    # ============================
    col1, col2 = st.columns(2)

    with col1:
        render_section_header("층별 활동 히트맵")
        building = selected_building if selected_building != "전체" else (
            filtered_trips["building_name"].iloc[0] if len(filtered_trips) > 0 else buildings[0] if buildings else "FAB"
        )
        fig = create_floor_heatmap(filtered_trips, building)
        st.plotly_chart(fig, use_container_width=True, key="hoist_floor_heatmap")

    with col2:
        if selected_hoist != "전체" and selected_hoist in hoist_info:
            render_section_header("기압 프로파일")
            hoist = hoist_info[selected_hoist]
            fig = create_pressure_altitude_chart(
                sward_df,
                selected_hoist,
                hoist.mov_gateway_no,
                hoist.fix_gateway_no
            )
            st.plotly_chart(fig, use_container_width=True, key="hoist_pressure")
        else:
            render_section_header("기압 프로파일")
            st.info("특정 호이스트를 선택하면 기압 프로파일을 확인할 수 있습니다")

    # ============================
    # Hoist Comparison Analysis (v4.1)
    # ============================
    render_section_header("호이스트 비교 분석")
    render_info_tooltip(
        "호이스트 비교 분석",
        "**모든 호이스트를 한 눈에 비교**합니다.\n\n"
        "- **운행 횟수**: 하루 동안 호이스트가 이동한 총 횟수\n"
        "- **총 탑승인원**: 해당 호이스트에 탑승한 총 인원\n"
        "- **가동률**: 운행 시간 / 전체 가동 가능 시간\n\n"
        "**색상**: 건물별로 구분 (FAB=파랑, CUB=초록, WWT=주황)\n\n"
        "**히트맵**: 시간대별로 어느 호이스트가 혼잡한지 표시\n"
        "- 빨간색: 평균 탑승인원이 높음 (혼잡)\n"
        "- 초록색: 평균 탑승인원이 낮음 (여유)"
    )

    col1, col2 = st.columns(2)

    with col1:
        # Use unfiltered data for comparison (show all hoists)
        fig = create_hoist_comparison_chart(trips_df, passengers_df, hoist_info)
        st.plotly_chart(fig, use_container_width=True, key="hoist_comparison_chart")

    with col2:
        fig = create_peak_period_comparison_chart(trips_df, passengers_df)
        st.plotly_chart(fig, use_container_width=True, key="hoist_peak_comparison")

    # Comparison table (wait_metrics may be None if expander not opened)
    comparison_df = calculate_hoist_comparison_data(
        trips_df, passengers_df, hoist_info, wait_metrics or {}
    )

    if len(comparison_df) > 0:
        st.markdown("##### 호이스트 비교 테이블")

        # Format for display
        display_comp_df = comparison_df[[
            "building_name", "short_name", "trip_count", "total_pax",
            "avg_pax", "max_pax", "utilization_pct", "avg_wait_sec"
        ]].copy()

        display_comp_df = display_comp_df.rename(columns={
            "building_name": "건물",
            "short_name": "호이스트",
            "trip_count": "운행(회)",
            "total_pax": "총탑승(명)",
            "avg_pax": "평균(명)",
            "max_pax": "최대(명)",
            "utilization_pct": "가동률(%)",
            "avg_wait_sec": "평균대기(초)",
        })

        st.dataframe(
            display_comp_df,
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ============================
    # Management Insights (v4.1)
    # ============================
    render_section_header("관리자 인사이트")
    render_info_tooltip(
        "관리자 인사이트",
        "**건설현장 관리자 관점의 데이터 기반 인사이트**입니다.\n\n"
        "- **효율화 제안**: 가동률이 낮은 호이스트, 운행 불균형 등\n"
        "- **혼잡 경고**: 특정 시간대/호이스트의 과밀 감지\n"
        "- **대기시간 이슈**: 평균 대기시간이 긴 구간, 생산성 손실\n"
        "- **안전 경고**: 과밀 운행 (정원 초과 가능성)\n\n"
        "**심각도**: 빨강(3-위험) > 주황(2-주의) > 파랑(1-참고)"
    )

    insights = generate_management_insights(
        trips_df, passengers_df, hoist_info, wait_metrics or {}
    )

    if insights:
        # Severity colors
        severity_colors = {
            3: "#EF4444",  # Critical - Red
            2: "#F59E0B",  # Warning - Orange
            1: "#3B82F6",  # Info - Blue
        }
        severity_icons = {
            3: "!!",
            2: "!",
            1: "i",
        }
        type_labels = {
            "efficiency": "효율화",
            "congestion": "혼잡",
            "wait_time": "대기시간",
            "safety": "안전",
            "utilization": "가동률",
        }

        for idx, insight in enumerate(insights):
            severity = insight.get("severity", 1)
            color = severity_colors.get(severity, "#64748B")
            icon = severity_icons.get(severity, "i")
            type_label = type_labels.get(insight.get("type", ""), "기타")

            st.markdown(f"""
            <div style="
                background: #1E2330;
                border: 1px solid #2D3748;
                border-left: 4px solid {color};
                border-radius: 8px;
                padding: 12px 16px;
                margin: 8px 0;
            ">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                    <span style="
                        background: {color};
                        color: white;
                        padding: 2px 8px;
                        border-radius: 4px;
                        font-size: 11px;
                        font-weight: 600;
                    ">{type_label}</span>
                    <span style="color: #FAFAFA; font-weight: 600;">{insight['title']}</span>
                </div>
                <div style="color: #94A3B8; font-size: 13px; margin-bottom: 6px;">
                    {insight['detail']}
                </div>
                <div style="color: {color}; font-size: 12px;">
                    → {insight['recommendation']}
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("현재 특별한 인사이트가 없습니다. 운행 데이터가 정상 범위 내에 있습니다.")

    st.markdown("<br>", unsafe_allow_html=True)

    # ============================
    # Trip Details Table
    # ============================
    render_section_header("운행 상세 목록")

    if len(filtered_trips) > 0:
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

        # Direction labels
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
    else:
        st.info("선택한 조건에 해당하는 운행이 없습니다")
