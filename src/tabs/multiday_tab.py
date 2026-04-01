"""Multiday Analysis Tab UI"""

import streamlit as st
import pandas as pd
from typing import Dict, List, Tuple

from ..analysis.multiday_metrics import (
    load_multiday_data,
    get_available_dates_with_meta,
    calculate_daily_summary,
    calculate_building_daily,
    calculate_hourly_comparison,
    calculate_hourly_average,
    calculate_date_hour_heatmap,
    detect_recurring_patterns,
    calculate_hoist_daily_metrics,
    calculate_hoist_summary,
    calculate_load_distribution,
    generate_multiday_insights,
    calculate_period_kpis,
)
from ..ui.components import (
    render_kpi_card,
    render_section_header,
    render_insight_card,
    render_info_tooltip,
    render_empty_state,
)
from ..ui.charts import (
    create_daily_trend_chart,
    create_building_daily_chart,
    create_hourly_overlay_chart,
    create_date_hour_heatmap,
    create_hoist_utilization_heatmap,
    create_hoist_avg_passengers_chart,
    create_hoist_peak_passengers_chart,
    create_load_distribution_pie,
)
from ..utils.llm_interpreter import (
    get_llm_status,
    generate_multiday_structural_insight,
    generate_hoist_efficiency_insight,
    render_data_comment,
    get_cache_key,
    get_cached_insight,
    set_cached_insight,
)


# ============================================================
# Cached Data Loading
# ============================================================


@st.cache_data(ttl=300)
def _load_multiday_cached(dates_tuple: Tuple[str, ...], cache_dir: str) -> Dict:
    """
    Load multiday data with caching

    Args:
        dates_tuple: Tuple of date strings (hashable)
        cache_dir: Cache directory path string

    Returns:
        Dict with loaded data
    """
    from pathlib import Path
    from ..data.cache_manager import CacheManager

    cache_manager = CacheManager(Path(cache_dir))
    return load_multiday_data(list(dates_tuple), cache_manager)


# ============================================================
# Main Tab Renderer
# ============================================================


def render_multiday_tab(
    cache_manager,
    hoist_info: Dict
) -> None:
    """
    Render multiday analysis tab

    Args:
        cache_manager: CacheManager instance
        hoist_info: Hoist information dict
    """
    # Get available dates
    available_dates = get_available_dates_with_meta(cache_manager)

    if not available_dates:
        render_empty_state(
            "캐시된 데이터가 없습니다. 데이터 관리 탭에서 처리를 실행하세요.",
            icon=""
        )
        return

    # ========== Date Selection Widget ==========
    _render_date_selector(available_dates)

    # Get selected dates from session state
    selected_dates = st.session_state.get("multiday_selected_dates", [])

    if not selected_dates:
        st.info("분석할 날짜를 선택하세요.")
        return

    # Load data
    with st.spinner("데이터 로딩 중..."):
        multiday_data = _load_multiday_cached(
            tuple(sorted(selected_dates)),
            str(cache_manager.cache_dir)
        )

    if not multiday_data:
        st.error("선택한 날짜의 데이터를 로드할 수 없습니다.")
        return

    # ========== Subtabs ==========
    subtabs = st.tabs([
        "일별 트렌드",
        "시간대별 패턴",
        "호이스트별 비교",
        "인사이트 요약"
    ])

    with subtabs[0]:
        _render_daily_trends(multiday_data)

    with subtabs[1]:
        _render_hourly_patterns(multiday_data)

    with subtabs[2]:
        _render_hoist_comparison(multiday_data, hoist_info)

    with subtabs[3]:
        _render_insights_summary(multiday_data, hoist_info)


# ============================================================
# Date Selector Widget
# ============================================================


def _render_date_selector(available_dates: List[Dict]) -> None:
    """Render date selection widget"""

    render_section_header("분석 기간 선택")

    # Filter outlier dates
    normal_dates = [d for d in available_dates if not d["is_outlier"]]
    outlier_dates = [d for d in available_dates if d["is_outlier"]]

    # Create selection options
    col1, col2 = st.columns([3, 1])

    with col1:
        # Default: exclude outliers
        default_dates = [d["date"] for d in normal_dates]

        # Initialize session state
        if "multiday_selected_dates" not in st.session_state:
            st.session_state.multiday_selected_dates = default_dates

        # Build options with labels
        options = []
        labels = {}
        for d in available_dates:
            date_str = d["date"]
            label = f"{date_str[4:6]}/{date_str[6:]}({d['weekday']})"
            if d["is_outlier"]:
                label += " *"
            options.append(date_str)
            labels[date_str] = label

        # Multi-select
        selected = st.multiselect(
            "날짜 선택",
            options=options,
            default=st.session_state.multiday_selected_dates,
            format_func=lambda x: labels.get(x, x),
            key="multiday_date_select"
        )

        st.session_state.multiday_selected_dates = selected

    with col2:
        # Quick selection buttons
        if st.button("전체 선택", use_container_width=True):
            st.session_state.multiday_selected_dates = [d["date"] for d in available_dates]
            st.rerun()

        if st.button("정상 데이터만", use_container_width=True):
            st.session_state.multiday_selected_dates = [d["date"] for d in normal_dates]
            st.rerun()

    # Outlier warning
    if outlier_dates:
        with st.expander("* 데이터 이상 날짜 안내", expanded=False):
            for d in outlier_dates:
                st.warning(
                    f"**{d['date'][4:6]}/{d['date'][6:]}({d['weekday']})**: "
                    f"S-Ward 데이터가 다른 날의 13배 → Trip/Pax 수치 이상. "
                    f"비교 분석 시 제외 권장."
                )


# ============================================================
# Subtab 1: Daily Trends
# ============================================================


def _render_daily_trends(multiday_data: Dict) -> None:
    """Render daily trends subtab"""

    render_section_header("일별 트렌드")

    render_info_tooltip(
        "일별 트렌드 분석",
        "선택한 기간의 **일별 운행 횟수**와 **탑승 인원**을 비교합니다.\n\n"
        "- 막대 그래프: 운행 횟수 (좌측 Y축)\n"
        "- 선 그래프: 탑승 인원 (우측 Y축)\n"
        "- 건물별 비교: FAB/CUB/WWT 운행 비율"
    )

    # Calculate metrics
    daily_summary = calculate_daily_summary(multiday_data)
    building_daily = calculate_building_daily(multiday_data)
    period_kpis = calculate_period_kpis(daily_summary)

    # KPI Cards
    cols = st.columns(4)

    with cols[0]:
        render_kpi_card(
            title="총 운행",
            value=f"{period_kpis['total_trips']:,}",
            subtitle=f"{period_kpis['num_days']}일 합계",
        )

    with cols[1]:
        render_kpi_card(
            title="총 탑승인원",
            value=f"{period_kpis['total_passengers']:,}",
            subtitle=f"{period_kpis['num_days']}일 합계",
        )

    with cols[2]:
        render_kpi_card(
            title="일 평균 운행",
            value=f"{period_kpis['avg_daily_trips']:.1f}",
            subtitle="회/일",
        )

    with cols[3]:
        render_kpi_card(
            title="일 평균 탑승",
            value=f"{period_kpis['avg_daily_passengers']:.1f}",
            subtitle="명/일",
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Charts
    col1, col2 = st.columns(2)

    with col1:
        fig = create_daily_trend_chart(daily_summary)
        st.plotly_chart(fig, use_container_width=True, key="multiday_daily_trend")

    with col2:
        fig = create_building_daily_chart(building_daily)
        st.plotly_chart(fig, use_container_width=True, key="multiday_building_daily")

    # Daily summary table
    with st.expander("일별 상세 데이터", expanded=False):
        display_df = daily_summary.copy()
        display_df["date_label"] = display_df.apply(
            lambda r: f"{r['date_str'][4:6]}/{r['date_str'][6:]}({r['weekday']})",
            axis=1
        )
        display_df = display_df[[
            "date_label", "trip_count", "passenger_count",
            "active_hoists", "avg_passengers_per_trip", "peak_hour"
        ]]
        display_df.columns = [
            "날짜", "운행", "탑승", "활성 호이스트",
            "평균 탑승/운행", "피크 시간"
        ]
        st.dataframe(display_df, use_container_width=True, hide_index=True)


# ============================================================
# Subtab 2: Hourly Patterns
# ============================================================


def _render_hourly_patterns(multiday_data: Dict) -> None:
    """Render hourly patterns subtab"""

    render_section_header("시간대별 패턴")

    render_info_tooltip(
        "시간대별 패턴 분석",
        "각 날짜의 **시간대별 탑승인원**을 비교하여 **반복되는 혼잡 패턴**을 식별합니다.\n\n"
        "- 오버레이 차트: 날짜별 시간대 탑승인원 (평균선 포함)\n"
        "- 히트맵: 날짜 x 시간 최대 탑승인원"
    )

    # Calculate metrics
    hourly_comparison = calculate_hourly_comparison(multiday_data)
    hourly_average = calculate_hourly_average(hourly_comparison)
    heatmap_data = calculate_date_hour_heatmap(multiday_data, "max_passengers")
    patterns = detect_recurring_patterns(hourly_comparison)

    # Comparison mode selector
    dates = sorted(multiday_data.keys())

    col1, col2 = st.columns([2, 1])

    with col1:
        compare_mode = st.radio(
            "비교 모드",
            ["전체 날짜 비교", "특정 날짜 vs 평균"],
            horizontal=True,
            key="hourly_compare_mode"
        )

    selected_date = None
    if compare_mode == "특정 날짜 vs 평균":
        with col2:
            date_labels = {
                d: f"{d[4:6]}/{d[6:]}" for d in dates
            }
            selected_date = st.selectbox(
                "비교 날짜",
                options=dates,
                format_func=lambda x: date_labels.get(x, x),
                key="hourly_selected_date"
            )

    # Charts
    col1, col2 = st.columns(2)

    with col1:
        fig = create_hourly_overlay_chart(
            hourly_comparison, hourly_average, selected_date
        )
        st.plotly_chart(fig, use_container_width=True, key="multiday_hourly_overlay")

    with col2:
        fig = create_date_hour_heatmap(heatmap_data, "최대 탑승인원")
        st.plotly_chart(fig, use_container_width=True, key="multiday_hour_heatmap")

    # Pattern insights
    if patterns:
        st.markdown("<br>", unsafe_allow_html=True)
        render_section_header("반복 패턴 인사이트")

        pattern_texts = [
            f"{p['hour']:02d}:00 - {p['description']} "
            f"(평균 {p['avg_passengers']:.0f}명, {p['occurrence_rate']*100:.0f}% 발생)"
            for p in patterns
        ]
        render_insight_card(pattern_texts, title="반복되는 혼잡 패턴")


# ============================================================
# Subtab 3: Hoist Comparison
# ============================================================


def _render_hoist_comparison(multiday_data: Dict, hoist_info: Dict) -> None:
    """Render hoist comparison subtab"""

    render_section_header("호이스트별 비교")

    render_info_tooltip(
        "호이스트 비교 분석",
        "호이스트별 **가동률**, **평균/피크 탑승인원**, **부하 분포**를 비교합니다.\n\n"
        "- 가동률: 병합된 가동 블록(트립 간 갭 10분 이하 포함) / 24시간\n"
        "- 평균 탑승인원: 빈 운행(0명) 제외 기준\n"
        "- 부하 분포: 전체 운행 대비 각 호이스트 점유율\n"
        "- 30% 이상 집중 시 분산 운행 권장"
    )

    # Calculate metrics
    hoist_daily = calculate_hoist_daily_metrics(multiday_data)
    hoist_summary = calculate_hoist_summary(hoist_daily)
    load_distribution = calculate_load_distribution(hoist_summary)

    # Utilization heatmap
    fig = create_hoist_utilization_heatmap(hoist_daily)
    st.plotly_chart(fig, use_container_width=True, key="multiday_hoist_util_heatmap")

    st.markdown("<br>", unsafe_allow_html=True)

    # Avg and peak passengers charts
    col1, col2 = st.columns(2)

    with col1:
        fig = create_hoist_avg_passengers_chart(hoist_summary)
        st.plotly_chart(fig, use_container_width=True, key="multiday_hoist_avg")

    with col2:
        fig = create_hoist_peak_passengers_chart(hoist_summary)
        st.plotly_chart(fig, use_container_width=True, key="multiday_hoist_peak")

    st.markdown("<br>", unsafe_allow_html=True)

    # Load distribution
    col1, col2 = st.columns([1, 2])

    with col1:
        render_section_header("부하 분포")
        fig = create_load_distribution_pie(load_distribution)
        st.plotly_chart(fig, use_container_width=True, key="multiday_load_pie")

    with col2:
        render_section_header("호이스트 요약 통계")

        if len(hoist_summary) > 0:
            display_df = hoist_summary[[
                "hoist_name", "building_name", "total_trips",
                "avg_daily_trips", "avg_passengers_per_trip", "trip_share"
            ]].copy()

            display_df.columns = [
                "호이스트", "건물", "총 운행",
                "일평균", "평균 탑승", "점유율(%)"
            ]

            display_df["점유율(%)"] = display_df["점유율(%)"].round(1)
            display_df["평균 탑승"] = display_df["평균 탑승"].round(1)
            display_df["일평균"] = display_df["일평균"].round(1)

            st.dataframe(display_df, use_container_width=True, hide_index=True)

    # Imbalance warning
    if load_distribution.get("imbalance_score", 0) > 0.3:
        st.warning(
            f"부하 불균형 감지: {load_distribution['dominant_hoist']}에 "
            f"{load_distribution['dominant_share']:.1f}% 집중. "
            f"분산 운행을 권장합니다."
        )


# ============================================================
# Subtab 4: Insights Summary
# ============================================================


def _render_insights_summary(multiday_data: Dict, hoist_info: Dict) -> None:
    """Render insights summary subtab"""

    render_section_header("인사이트 요약")

    render_info_tooltip(
        "자동 인사이트 생성",
        "멀티데이 데이터를 기반으로 **관리자 관점의 인사이트**를 자동 생성합니다.\n\n"
        "**인사이트 유형:**\n"
        "- 효율화 (파랑): 가동률 저조, 부하 불균형\n"
        "- 혼잡 (주황): 반복 피크, 고탑승 운행\n"
        "- 부하 (보라): 특정 호이스트 집중\n"
        "- 안전 (빨강): 정원 초과 의심\n\n"
        "**AI 분석**: Claude AI가 구조적 패턴을 발견하고 효율화 제안을 생성합니다."
    )

    # Calculate all metrics for insights
    daily_summary = calculate_daily_summary(multiday_data)
    hoist_daily = calculate_hoist_daily_metrics(multiday_data)
    hoist_summary = calculate_hoist_summary(hoist_daily)
    hourly_comparison = calculate_hourly_comparison(multiday_data)
    patterns = detect_recurring_patterns(hourly_comparison)
    load_distribution = calculate_load_distribution(hoist_summary)
    period_kpis = calculate_period_kpis(daily_summary)

    # ============================
    # AI 구조적 패턴 분석 (새로 추가)
    # ============================
    llm_status = get_llm_status()
    if llm_status["ready"]:
        # 일별 통계 준비
        daily_stats = []
        for _, row in daily_summary.iterrows():
            daily_stats.append({
                "date": row["date_str"],
                "trips": int(row["trip_count"]),
                "passengers": int(row["passenger_count"]),
                "peak_hour": int(row["peak_hour"]),
            })

        # 시간대별 반복 패턴 준비
        hourly_pattern = {}
        for pattern in patterns:
            hourly_pattern[pattern["hour"]] = {
                "avg_pax": pattern["avg_passengers"],
                "occurrence_rate": pattern["occurrence_rate"],
            }

        # 호이스트 통계 준비
        hoist_stats = {}
        if len(hoist_summary) > 0:
            for _, row in hoist_summary.iterrows():
                hoist_stats[row["hoist_name"]] = {
                    "total_trips": int(row["total_trips"]),
                    "avg_util": row["avg_utilization"],
                    "trip_share": row["trip_share"],
                }

        # 캐시 키 (선택된 날짜 기반)
        dates_str = "_".join(sorted(multiday_data.keys()))
        structural_cache_key = get_cache_key("multiday_structural", dates_str)
        structural_cached = get_cached_insight(structural_cache_key)

        if structural_cached:
            st.markdown(f"""
            <div style="
                background: linear-gradient(135deg, #1E3A5F 0%, #1E2330 100%);
                border: 1px solid #3B82F6;
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 20px;
            ">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 16px;">
                    <span style="font-size: 20px;">&#128202;</span>
                    <span style="color: #FAFAFA; font-weight: 600; font-size: 16px;">
                        {period_kpis['num_days']}일간 구조적 패턴 분석
                    </span>
                    <span style="
                        background: #3B82F6;
                        color: white;
                        padding: 2px 8px;
                        border-radius: 4px;
                        font-size: 10px;
                        font-weight: 600;
                    ">AI</span>
                </div>
                <div style="color: #E2E8F0; font-size: 14px; line-height: 1.8;">
                    {structural_cached}
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            with st.spinner("구조적 패턴 AI 분석 중..."):
                structural_insight = generate_multiday_structural_insight(
                    daily_stats=daily_stats,
                    hourly_pattern=hourly_pattern,
                    hoist_stats=hoist_stats,
                )

            if structural_insight:
                set_cached_insight(structural_cache_key, structural_insight)
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, #1E3A5F 0%, #1E2330 100%);
                    border: 1px solid #3B82F6;
                    border-radius: 12px;
                    padding: 20px;
                    margin-bottom: 20px;
                ">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 16px;">
                        <span style="font-size: 20px;">&#128202;</span>
                        <span style="color: #FAFAFA; font-weight: 600; font-size: 16px;">
                            {period_kpis['num_days']}일간 구조적 패턴 분석
                        </span>
                        <span style="
                            background: #3B82F6;
                            color: white;
                            padding: 2px 8px;
                            border-radius: 4px;
                            font-size: 10px;
                            font-weight: 600;
                        ">AI</span>
                    </div>
                    <div style="color: #E2E8F0; font-size: 14px; line-height: 1.8;">
                        {structural_insight}
                    </div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

    # Generate rule-based insights
    insights = generate_multiday_insights(
        daily_summary, hoist_summary, patterns, load_distribution
    )

    if not insights:
        st.info("특별한 인사이트가 없습니다. 운영이 안정적입니다.")
    else:
        # Display insights by type
        type_colors = {
            "efficiency": "#3B82F6",
            "congestion": "#F59E0B",
            "load": "#A855F7",
            "safety": "#EF4444",
        }
        type_labels = {
            "efficiency": "효율화",
            "congestion": "혼잡",
            "load": "부하",
            "safety": "안전",
        }

        # Group insights by severity
        critical_insights = [i for i in insights if i.severity == 3]
        warning_insights = [i for i in insights if i.severity == 2]
        info_insights = [i for i in insights if i.severity == 1]

        # Critical (Safety)
        if critical_insights:
            st.markdown("### 주의 필요")
            for insight in critical_insights:
                _render_insight_card_styled(insight, type_colors, type_labels)

        # Warning (Congestion, Load)
        if warning_insights:
            st.markdown("### 개선 권장")
            cols = st.columns(2)
            for i, insight in enumerate(warning_insights):
                with cols[i % 2]:
                    _render_insight_card_styled(insight, type_colors, type_labels)

        # Info (Efficiency)
        if info_insights:
            st.markdown("### 참고 사항")
            cols = st.columns(2)
            for i, insight in enumerate(info_insights):
                with cols[i % 2]:
                    _render_insight_card_styled(insight, type_colors, type_labels)

    st.markdown("<br>", unsafe_allow_html=True)

    # ============================
    # AI 효율화 제안 (부하 불균형 있을 때만)
    # ============================
    if llm_status["ready"] and load_distribution.get("imbalance_score", 0) > 0.2:
        # 호이스트별 비교 데이터 준비
        hoist_comparison = []
        if len(hoist_summary) > 0:
            for _, row in hoist_summary.iterrows():
                hoist_comparison.append({
                    "hoist": row["hoist_name"],
                    "trips": int(row["total_trips"]),
                    "avg_pax": row["avg_passengers_per_trip"],
                    "max_pax": int(row["peak_passengers"]),
                    "utilization": row["avg_utilization"],
                })

        load_imbalance = {
            "dominant_hoist": load_distribution.get("dominant_hoist", ""),
            "dominant_share": load_distribution.get("dominant_share", 0),
            "imbalance_score": load_distribution.get("imbalance_score", 0),
        }

        efficiency_cache_key = get_cache_key("multiday_efficiency", dates_str)
        efficiency_cached = get_cached_insight(efficiency_cache_key)
        if efficiency_cached:
            render_data_comment(efficiency_cached, title="호이스트 효율화 AI 제안")
        else:
            with st.spinner("효율화 제안 생성 중..."):
                efficiency_insight = generate_hoist_efficiency_insight(
                    hoist_comparison=hoist_comparison,
                    load_imbalance=load_imbalance,
                    wait_summary=None,  # 멀티데이에서는 대기시간 없음
                )
            if efficiency_insight:
                set_cached_insight(efficiency_cache_key, efficiency_insight)
                render_data_comment(efficiency_insight, title="호이스트 효율화 AI 제안")

    st.markdown("<br>", unsafe_allow_html=True)

    # Period summary
    render_section_header("기간 요약")

    cols = st.columns(4)

    with cols[0]:
        render_kpi_card(
            title="분석 기간",
            value=f"{period_kpis['num_days']}일",
        )

    with cols[1]:
        render_kpi_card(
            title="총 운행",
            value=f"{period_kpis['total_trips']:,}회",
        )

    with cols[2]:
        render_kpi_card(
            title="총 탑승",
            value=f"{period_kpis['total_passengers']:,}명",
        )

    with cols[3]:
        # Calculate avg utilization
        if len(hoist_summary) > 0:
            avg_util = hoist_summary["avg_utilization"].mean() * 100
        else:
            avg_util = 0
        render_kpi_card(
            title="평균 가동률",
            value=f"{avg_util:.1f}%",
        )


def _render_insight_card_styled(
    insight,
    type_colors: Dict[str, str],
    type_labels: Dict[str, str]
) -> None:
    """Render a styled insight card"""

    color = type_colors.get(insight.type, "#64748B")
    type_label = type_labels.get(insight.type, insight.type)

    st.markdown(f"""
    <div style="
        background: #1E2330;
        border: 1px solid #2D3748;
        border-left: 4px solid {color};
        border-radius: 8px;
        padding: 16px;
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
            <span style="color: #FAFAFA; font-weight: 600; font-size: 14px;">
                {insight.title}
            </span>
        </div>
        <div style="color: #94A3B8; font-size: 13px;">
            {insight.detail}
        </div>
    </div>
    """, unsafe_allow_html=True)
