"""종합 현황 탭 - Summary dashboard with v4.5 Rate-Matching (Dark Theme)"""

import streamlit as st
import pandas as pd
from typing import Dict, Any

from ..ui.components import (
    render_kpi_card, render_building_card, render_section_header,
    render_empty_state, render_passenger_color_legend,
    render_info_tooltip, render_insight_card, render_congestion_legend
)
from ..ui.charts import (
    create_hourly_chart, create_building_comparison_chart,
    create_hourly_passenger_line, create_elevator_shaft_timeline,
    create_congestion_heatmap, create_peak_comparison_chart,
    create_hoist_comparison_chart
)
from ..analysis.metrics import (
    calculate_overview_kpis, calculate_building_summary, calculate_hourly_metrics,
    calculate_congestion_metrics, calculate_peak_analysis,
    generate_management_insights
)
from ..utils.llm_interpreter import (
    get_llm_status, generate_daily_summary, generate_congestion_insight,
    generate_daily_highlight_insight, generate_congestion_context_insight,
    render_data_comment, get_cache_key, get_cached_insight, set_cached_insight
)
from ..utils.converters import format_hoist_name


def render_overview_tab(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    hoist_info: Dict,
    sward_df: pd.DataFrame
) -> None:
    """
    Render overview tab content (종합 현황)

    Args:
        trips_df: DataFrame with trip data
        passengers_df: DataFrame with passenger classifications
        hoist_info: Dict of hoist configurations
        sward_df: S-Ward sensor data
    """
    if len(trips_df) == 0:
        render_empty_state(
            "데이터가 없습니다. 데이터 관리 탭에서 처리를 실행하세요.",
            icon=""
        )
        return

    # Calculate KPIs
    kpis = calculate_overview_kpis(trips_df, passengers_df, hoist_info)

    # Check for v4.5 rate-matching data
    has_multi_evidence = "composite_score" in passengers_df.columns if len(passengers_df) > 0 else False

    # ============================
    # KPI Cards Row
    # ============================
    render_section_header("오늘의 현황")
    render_info_tooltip(
        "KPI 지표 설명",
        "**1행 — 운영 현황**\n"
        "- **총 운행**: 하루 동안 호이스트가 이동한 총 횟수\n"
        "- **활성 호이스트**: 1회 이상 운행한 호이스트 수 / 전체 호이스트 수\n"
        "- **총 탑승인원**: BLE+기압 센서 기반 Rate-Matching 알고리즘으로 추정된 탑승 인원\n"
        "- **평균 운행시간**: 호이스트 1회 운행의 평균 소요시간\n\n"
        "**2행 — 위험/혼잡 지표**\n"
        "- **최고 혼잡 시간**: 탑승인원이 가장 많은 시간대\n"
        "- **최대 탑승인원**: 1회 운행에서 감지된 최대 탑승 인원 (과밀 감지)\n"
        "- **최다 운행 호이스트**: 가장 많이 운행한 호이스트 (부하 집중 감지)\n"
        "- **피크 운행 시간**: 운행 횟수가 가장 많은 시간대"
    )

    # Row 1: 운영 현황
    cols = st.columns(4)

    with cols[0]:
        render_kpi_card(
            title="총 운행",
            value=kpis["total_trips"],
        )

    with cols[1]:
        render_kpi_card(
            title="활성 호이스트",
            value=f"{kpis['active_hoists']}/{kpis['total_hoists']}",
        )

    with cols[2]:
        render_kpi_card(
            title="총 탑승인원",
            value=kpis["total_passengers"],
        )

    with cols[3]:
        render_kpi_card(
            title="평균 운행시간",
            value=f"{kpis['avg_duration_sec'] / 60:.1f}분",
        )

    # Row 2: 위험/혼잡 지표 — "오늘 뭐가 문제야?"
    cols2 = st.columns(4)

    with cols2[0]:
        peak_h = kpis.get("peak_pax_hour")
        peak_label = f"{peak_h}:00" if peak_h is not None else "-"
        render_kpi_card(
            title="최고 혼잡 시간",
            value=peak_label,
            subtitle=f"{kpis.get('peak_pax_count', 0)}명 탑승" if peak_h is not None else "",
        )

    with cols2[1]:
        max_pax = kpis.get("max_pax_per_trip", 0)
        render_kpi_card(
            title="최대 탑승인원",
            value=f"{max_pax}명",
            subtitle=kpis.get("busiest_trip_hoist", "").replace("_", " ") if max_pax > 0 else "",
        )

    with cols2[2]:
        bh = kpis.get("busiest_hoist", "")
        render_kpi_card(
            title="최다 운행 호이스트",
            value=format_hoist_name(bh) if bh else "-",
            subtitle=f"{kpis.get('busiest_hoist_trips', 0)}회",
        )

    with cols2[3]:
        peak_trip_h = kpis.get("peak_hour")
        peak_trip_label = f"{peak_trip_h}:00" if peak_trip_h is not None else "-"
        render_kpi_card(
            title="피크 운행 시간",
            value=peak_trip_label,
            subtitle=f"{kpis.get('peak_trips', 0)}회 운행",
            icon=""
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ============================
    # Building Status Row
    # ============================
    render_section_header("건물별 현황")

    building_summary = calculate_building_summary(trips_df, passengers_df)

    # Group hoists by building
    building_hoists = {}
    for hoist_name, hoist in hoist_info.items():
        building = hoist.building_name
        if building not in building_hoists:
            building_hoists[building] = []

        # Check if hoist is active (has trips)
        is_active = hoist_name in trips_df["hoist_name"].values

        building_hoists[building].append({
            "name": hoist_name,
            "is_active": is_active
        })

    # Display building cards
    cols = st.columns(3)
    for idx, (building, hoists) in enumerate(sorted(building_hoists.items())):
        with cols[idx % 3]:
            stats = building_summary.get(building, {})
            render_building_card(building, hoists, stats)

    st.markdown("<br>", unsafe_allow_html=True)

    # ============================
    # Elevator Shaft Quick View
    # ============================
    render_section_header("호이스트 운행 타임라인")
    st.caption("층간 이동 + 탑승인원 시각화 (마커 크기/색상 = 탑승인원)")
    render_passenger_color_legend()

    # 24시간 현장: 전체 시간대 표시
    fig = create_elevator_shaft_timeline(trips_df, passengers_df)
    st.plotly_chart(fig, use_container_width=True, key="overview_shaft_timeline")

    st.markdown("<br>", unsafe_allow_html=True)

    # ============================
    # Congestion Insights (v4.0)
    # ============================
    render_section_header("혼잡도 인사이트")

    render_info_tooltip(
        "시간대별 최대 탑승인원",
        "**10분 단위**로 각 호이스트의 **최대 탑승인원**을 표시합니다.\n\n"
        "- 초록: 5명 이하 (여유)\n"
        "- 노랑: 10명 내외 (보통)\n"
        "- 주황: 15~20명 (주의)\n"
        "- 빨강: 20명+ (혼잡)\n\n"
        "hover 시 평균 탑승인원, 운행횟수도 확인 가능합니다."
    )

    render_congestion_legend()

    # Calculate congestion metrics
    congestion = calculate_congestion_metrics(trips_df, passengers_df)
    peak = calculate_peak_analysis(trips_df, passengers_df)

    col1, col2 = st.columns(2)

    with col1:
        fig = create_peak_comparison_chart(peak)
        st.plotly_chart(fig, use_container_width=True, key="overview_peak")

    with col2:
        hoist_names = sorted(trips_df["hoist_name"].unique()) if len(trips_df) > 0 else []
        fig = create_congestion_heatmap(
            congestion["hoist_hourly_ci"], hoist_names,
            interval_min=congestion.get("interval_min", 10),
        )
        st.plotly_chart(fig, use_container_width=True, key="overview_congestion_heatmap")

    # Insight card
    render_insight_card(congestion["insights"])

    # ============================
    # Management Insights (v4.1)
    # ============================
    st.markdown("<br>", unsafe_allow_html=True)
    render_section_header("관리자 핵심 인사이트")
    render_info_tooltip(
        "관리자 핵심 인사이트",
        "**건설현장 관리자 관점의 데이터 기반 인사이트**입니다.\n\n"
        "- **효율화 제안**: 가동률이 낮은 호이스트, 운행 불균형 등\n"
        "- **혼잡 경고**: 특정 시간대/호이스트의 과밀 감지\n"
        "- **안전 경고**: 과밀 운행 (정원 초과 가능성)\n\n"
        "자세한 분석은 **운행 분석** 탭에서 확인하세요."
    )

    insights = generate_management_insights(trips_df, passengers_df, hoist_info)

    if insights:
        # Show top 4 insights only in overview
        top_insights = insights[:4]

        severity_colors = {
            3: "#EF4444",  # Critical - Red
            2: "#F59E0B",  # Warning - Orange
            1: "#3B82F6",  # Info - Blue
        }
        type_labels = {
            "efficiency": "효율화",
            "congestion": "혼잡",
            "wait_time": "대기",
            "safety": "안전",
            "utilization": "가동률",
        }

        cols = st.columns(2)
        for idx, insight in enumerate(top_insights):
            with cols[idx % 2]:
                severity = insight.get("severity", 1)
                color = severity_colors.get(severity, "#64748B")
                type_label = type_labels.get(insight.get("type", ""), "기타")

                st.markdown(f"""
                <div style="
                    background: #1E2330;
                    border: 1px solid #2D3748;
                    border-left: 4px solid {color};
                    border-radius: 8px;
                    padding: 12px 16px;
                    margin: 4px 0;
                    min-height: 100px;
                ">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
                        <span style="
                            background: {color};
                            color: white;
                            padding: 2px 8px;
                            border-radius: 4px;
                            font-size: 10px;
                            font-weight: 600;
                        ">{type_label}</span>
                        <span style="color: #FAFAFA; font-weight: 600; font-size: 13px;">{insight['title']}</span>
                    </div>
                    <div style="color: #94A3B8; font-size: 12px;">
                        {insight['detail'][:80]}{'...' if len(insight['detail']) > 80 else ''}
                    </div>
                </div>
                """, unsafe_allow_html=True)

        if len(insights) > 4:
            st.caption(f"+{len(insights) - 4}개 인사이트가 더 있습니다. 운행 분석 탭에서 확인하세요.")

    st.markdown("<br>", unsafe_allow_html=True)

    # ============================
    # Charts Row
    # ============================
    col1, col2 = st.columns(2)

    with col1:
        render_section_header("시간대별 운행 현황")
        hourly_df = calculate_hourly_metrics(trips_df, passengers_df)
        if len(hourly_df) > 0:
            fig = create_hourly_chart(hourly_df, "trip_count")
            st.plotly_chart(fig, use_container_width=True, key="overview_hourly")
        else:
            st.info("시간별 데이터가 없습니다")

    with col2:
        render_section_header("건물별 비교")
        fig = create_building_comparison_chart(building_summary)
        st.plotly_chart(fig, use_container_width=True, key="overview_building")

    # ============================
    # Peak Hour Info
    # ============================
    if kpis["peak_hour"] is not None:
        st.info(
            f"피크 시간대: {kpis['peak_hour']:02d}:00 ~ {kpis['peak_hour']+1:02d}:00 "
            f"({kpis['peak_trips']}회 운행)"
        )

    # ============================
    # Summary Stats
    # ============================
    st.markdown("<br>", unsafe_allow_html=True)
    render_section_header("요약 통계")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "총 운행 시간",
            f"{kpis['total_operating_min']:.0f}분"
        )

    with col2:
        trips_with_pax = kpis.get("trips_with_passengers", kpis["total_trips"])
        avg_pax_per_trip = (
            kpis["total_passengers"] / trips_with_pax
            if trips_with_pax > 0 else 0
        )
        st.metric(
            "평균 탑승인원/운행",
            f"{avg_pax_per_trip:.1f}명",
            help="빈 운행(탑승자 0명)을 제외하고 계산"
        )

    with col3:
        # Calculate utilization (24-hour operation)
        utilization = (
            kpis["total_operating_min"] /
            (len(hoist_info) * 60 * 24)
            if len(hoist_info) > 0 else 0
        )
        st.metric(
            "전체 가동률",
            f"{utilization * 100:.1f}%"
        )

    # ============================
    # AI 인사이트 섹션 (v5.1 강화)
    # ============================
    llm_status = get_llm_status()
    if llm_status["ready"]:
        st.markdown("<br>", unsafe_allow_html=True)
        render_section_header("AI 인사이트")
        render_info_tooltip(
            "AI 인사이트",
            "**Claude AI 기반의 데이터 해석**입니다.\n\n"
            "- 건설현장 호이스트 운영 전문가 관점에서 분석\n"
            "- 구조적 패턴 발견 및 효율화 제안\n"
            "- 혼잡도 + 대기시간 교차 분석\n\n"
            "**주의**: 집계된 통계만 분석에 사용되며, "
            "개인정보(작업자명, 업체명 등)는 전송되지 않습니다."
        )

        # 1) 오늘의 핵심 인사이트 (3~5개 bullet point)
        highlight_cache_key = get_cache_key(
            "daily_highlight",
            kpis["total_trips"],
            kpis["total_passengers"],
            kpis.get("peak_hour"),
        )
        highlight_cached = get_cached_insight(highlight_cache_key)

        if highlight_cached:
            st.markdown(f"""
            <div style="
                background: linear-gradient(135deg, #1E3A5F 0%, #1E2330 100%);
                border: 1px solid #3B82F6;
                border-radius: 12px;
                padding: 16px 20px;
                margin-bottom: 16px;
            ">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                    <span style="font-size: 18px;">&#128161;</span>
                    <span style="color: #FAFAFA; font-weight: 600; font-size: 15px;">오늘의 핵심 인사이트</span>
                    <span style="
                        background: #3B82F6;
                        color: white;
                        padding: 2px 8px;
                        border-radius: 4px;
                        font-size: 10px;
                        font-weight: 600;
                    ">AI</span>
                </div>
                <div style="color: #E2E8F0; font-size: 13px; line-height: 1.8;">
                    {highlight_cached}
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            with st.spinner("오늘의 핵심 인사이트 생성 중..."):
                # 평균 혼잡도 계산
                avg_ci = 0.0
                if congestion.get("hourly_summary"):
                    ci_values = [h.get("ci", 0) for h in congestion["hourly_summary"].values()]
                    avg_ci = sum(ci_values) / len(ci_values) if ci_values else 0.0

                today_stats = {
                    "trips": kpis["total_trips"],
                    "passengers": kpis["total_passengers"],
                    "peak_hour": kpis.get("peak_hour"),
                    "avg_ci": round(avg_ci, 2),
                    "max_pax": kpis.get("max_pax_per_trip", 0),
                }

                highlight_insight = generate_daily_highlight_insight(
                    today_stats=today_stats,
                    yesterday_stats=None,  # 멀티데이 데이터 있으면 전달
                    week_avg=None,
                )

                if highlight_insight:
                    set_cached_insight(highlight_cache_key, highlight_insight)
                    st.markdown(f"""
                    <div style="
                        background: linear-gradient(135deg, #1E3A5F 0%, #1E2330 100%);
                        border: 1px solid #3B82F6;
                        border-radius: 12px;
                        padding: 16px 20px;
                        margin-bottom: 16px;
                    ">
                        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                            <span style="font-size: 18px;">&#128161;</span>
                            <span style="color: #FAFAFA; font-weight: 600; font-size: 15px;">오늘의 핵심 인사이트</span>
                            <span style="
                                background: #3B82F6;
                                color: white;
                                padding: 2px 8px;
                                border-radius: 4px;
                                font-size: 10px;
                                font-weight: 600;
                            ">AI</span>
                        </div>
                        <div style="color: #E2E8F0; font-size: 13px; line-height: 1.8;">
                            {highlight_insight}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

        # 2) 혼잡도 + 대기시간 교차 분석 (확장된 컨텍스트 분석)
        # 시간대별 데이터 준비
        hourly_df = calculate_hourly_metrics(trips_df, passengers_df)
        hourly_ci_dict = {}
        hourly_pax_dict = {}
        hourly_trips_dict = {}

        if len(hourly_df) > 0:
            for _, row in hourly_df.iterrows():
                h = int(row["hour"])
                hourly_pax_dict[h] = int(row.get("passenger_count", 0))
                hourly_trips_dict[h] = int(row.get("trip_count", 0))

        # 혼잡도 지수 추출
        if congestion.get("hourly_summary"):
            for h, data in congestion["hourly_summary"].items():
                hourly_ci_dict[int(h)] = data.get("ci", 0)

        context_cache_key = get_cache_key(
            "congestion_context",
            str(hourly_ci_dict),
            str(hourly_pax_dict),
        )
        context_cached = get_cached_insight(context_cache_key)

        if context_cached:
            render_data_comment(context_cached, "혼잡도 x 대기시간 교차 분석")
        else:
            # 대기시간 데이터가 있으면 교차 분석
            # (여기서는 hourly_wait가 없으므로 빈 dict 전달)
            with st.spinner("교차 분석 중..."):
                context_insight = generate_congestion_context_insight(
                    hourly_ci=hourly_ci_dict,
                    hourly_wait={},  # 대기시간은 hoist_tab에서 계산
                    hourly_passengers=hourly_pax_dict,
                    hourly_trips=hourly_trips_dict,
                )

            if context_insight:
                set_cached_insight(context_cache_key, context_insight)
                render_data_comment(context_insight, "혼잡도 x 탑승인원 교차 분석")

        # 3) 기존 일별 요약 (더 상세한 분석용)
        summary_cache_key = get_cache_key(
            "daily_summary",
            kpis["total_trips"],
            kpis["total_passengers"],
            kpis.get("peak_hour"),
        )
        summary_cached = get_cached_insight(summary_cache_key)

        if summary_cached:
            render_data_comment(summary_cached, "운영 요약 상세")
        else:
            with st.spinner("운영 요약 생성 중..."):
                avg_ci = 0.0
                if congestion.get("hourly_summary"):
                    ci_values = [h.get("ci", 0) for h in congestion["hourly_summary"].values()]
                    avg_ci = sum(ci_values) / len(ci_values) if ci_values else 0.0

                summary_insight = generate_daily_summary(
                    total_trips=kpis["total_trips"],
                    total_passengers=kpis["total_passengers"],
                    active_hoists=kpis["active_hoists"],
                    total_hoists=kpis["total_hoists"],
                    peak_hour=kpis.get("peak_hour"),
                    peak_trips=kpis.get("peak_trips", 0),
                    avg_ci=avg_ci,
                    building_stats=building_summary,
                )

            if summary_insight:
                set_cached_insight(summary_cache_key, summary_insight)
                render_data_comment(summary_insight, "운영 요약 상세")
