"""탑승자 분석 탭 - v4.5 Rate-Matching Passenger Analysis (Dark Theme)"""

import streamlit as st
import pandas as pd
import plotly.express as px
from typing import Dict

from ..ui.components import (
    render_kpi_card, render_section_header, render_empty_state,
    render_confidence_bar, render_evidence_bar, render_classification_badge,
    render_composite_score_card, render_info_tooltip
)
from ..ui.charts import (
    create_passenger_hourly_chart, create_company_distribution,
    create_confidence_histogram, create_hourly_passenger_line,
    create_evidence_distribution_chart, create_composite_score_histogram
)
from ..ui.styles import COLORS, apply_dark_layout
from ..utils.llm_interpreter import (
    get_llm_status, generate_passenger_pattern_insight,
    generate_passenger_daily_insight, generate_hoist_usage_insight,
    generate_probable_explanation_insight, generate_algorithm_explanation,
    render_data_comment, get_cache_key, get_cached_insight, set_cached_insight
)


# v4.5 evidence column names
_V4_SCORE_COLS = ["rate_match_score", "delta_ratio", "composite_score"]
_V4_DETAIL_COLS = ["rate_match_intervals", "total_moving_intervals", "worker_delta_hpa"]

# High passenger warning threshold
HIGH_PASSENGER_WARNING = 30


def _has_v4_data(df: pd.DataFrame) -> bool:
    """Check if DataFrame has v4 rate-matching columns."""
    return "rate_match_score" in df.columns


def _render_algorithm_info_tooltip():
    """v4.5 Rate-Matching algorithm explanation tooltip."""
    render_info_tooltip(
        "v4.5 Rate-Matching 탑승자 분류 알고리즘",
        "호이스트 탑승 여부를 **기압 변화율 매칭 (Rate-Matching)** 방식으로 판정합니다.\n\n"
        "**순차 필터링 (Sequential Filter)**:\n"
        "1. **RSSI 후보 선별** (-75dBm): 호이스트에 장착된 이동형 게이트웨이(mov_gw)에서 "
        "작업자 T-Ward가 -75dBm 이상으로 수신되면 탑승 후보\n"
        "2. **고도 변화 확인** (>= 0.3 hPa): 작업자의 기압센서에서 의미있는 수직 이동 감지\n"
        "3. **멀티스케일 Rate Matching**: dp/dt(작업자) ~ dp/dt(호이스트)를 "
        "10초/30초/60초 3개 윈도우에서 비교. BLE 통신 갭(30~90초 데이터 손실)에 강건\n"
        "4. **Composite Scoring**: rate_match x 0.65 + delta_ratio x 0.25 + direction x 0.10\n"
        "5. **RSSI 탑승구간 재배정**: 같은 건물 내 여러 호이스트 동시 운행 시, "
        "탑승 구간 동안 평균 RSSI가 가장 강한 호이스트에 최종 배정\n\n"
        "**핵심 원리**: RSSI는 후보 선별에만 사용하며 점수에 반영하지 않음. "
        "핵심은 **기압 변화율이 호이스트와 일치하는지** 여부.\n\n"
        "**분류 기준**:\n"
        "- **확정 (Confirmed)**: composite >= 0.60 -- 기압 변화율이 호이스트와 잘 일치\n"
        "- **추정 (Probable)**: composite 0.45~0.60 -- 호이스트 탑승으로 분류됨. "
        "다만 BLE 통신 갭으로 인해 비교 가능 구간이 줄어 확신도가 낮음\n\n"
        "**Probable의 의미**: 호이스트에 **탑승한 것으로 분류**됨. "
        "Confirmed과의 차이는 확신도이지, 탑승 여부가 아님."
    )


def _render_kpi_info_tooltip():
    """KPI metrics explanation tooltip."""
    render_info_tooltip(
        "KPI 지표 설명",
        "- **총 탑승 건수**: 호이스트 탑승이 감지된 총 이벤트 수 "
        "(한 사람이 하루 10번 타면 10건)\n"
        "- **고유 작업자**: user_no(작업자 고유 ID) 기준 중복 제거된 실제 인원\n"
        "- **확정 탑승 (Confirmed)**: composite >= 0.60 -- 기압 변화율이 호이스트와 잘 일치\n"
        "- **추정 탑승 (Probable)**: composite 0.45~0.60 -- 호이스트 탑승으로 분류됨. "
        "BLE 통신 갭으로 인해 비교 가능 구간이 줄어 확신도가 낮음\n"
        "- **인당 평균 탑승**: 작업자 1명의 하루 평균 탑승 횟수"
    )


def render_passenger_tab(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    hoist_info: Dict
) -> None:
    """Render passenger tracking tab (탑승자 분석)"""

    if len(passengers_df) == 0:
        render_empty_state(
            "탑승자 데이터가 없습니다. 데이터 관리 탭에서 처리를 실행하세요.",
            icon=""
        )
        return

    is_v4 = _has_v4_data(passengers_df)
    has_multi_evidence = "composite_score" in passengers_df.columns

    # ============================
    # Filters
    # ============================
    col1, col2, col3, col4 = st.columns([2, 2, 2, 2])

    with col1:
        companies = sorted(passengers_df["company_name"].dropna().unique())
        selected_company = st.selectbox(
            "업체", options=["전체"] + list(companies), key="pax_company"
        )

    with col2:
        classification_options = ["전체", "확정 (Confirmed)", "추정 (Probable)"]
        selected_classification = st.selectbox(
            "분류", options=classification_options, key="pax_classification"
        )

    with col3:
        hoists = sorted(passengers_df["hoist_name"].unique())
        selected_hoist = st.selectbox(
            "호이스트", options=["전체"] + list(hoists), key="pax_hoist"
        )

    with col4:
        score_threshold = st.slider(
            "최소 종합점수", min_value=0.0, max_value=1.0,
            value=0.0, step=0.05, key="pax_score_threshold"
        )

    # Filter data
    filtered_df = passengers_df.copy()

    if selected_company != "전체":
        filtered_df = filtered_df[filtered_df["company_name"] == selected_company]

    if selected_classification != "전체":
        class_map = {
            "확정 (Confirmed)": "confirmed",
            "추정 (Probable)": "probable",
        }
        target_class = class_map.get(selected_classification)
        if target_class:
            filtered_df = filtered_df[filtered_df["classification"] == target_class]

    if score_threshold > 0 and "composite_score" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["composite_score"] >= score_threshold]

    if selected_hoist != "전체":
        filtered_df = filtered_df[filtered_df["hoist_name"] == selected_hoist]

    st.markdown("---")

    # ============================
    # Info Tooltips
    # ============================
    _render_algorithm_info_tooltip()
    _render_kpi_info_tooltip()

    # ============================
    # KPIs
    # ============================
    if "user_no" in filtered_df.columns:
        valid = filtered_df[filtered_df["user_no"].notna() & (filtered_df["user_no"] != "")]
        unique_workers = valid["user_no"].nunique()
    else:
        unique_workers = filtered_df["mac_address"].nunique()
    unique_companies = filtered_df["company_name"].nunique()
    avg_rides = len(filtered_df) / unique_workers if unique_workers > 0 else 0

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        render_kpi_card("총 탑승 건수", f"{len(filtered_df):,}",
                       subtitle="탑승 이벤트 합계")
    with col2:
        render_kpi_card("고유 작업자", f"{unique_workers}명",
                       subtitle=f"{unique_companies}개 업체")
    with col3:
        confirmed = len(filtered_df[filtered_df["classification"] == "confirmed"])
        render_kpi_card("확정 탑승", confirmed, subtitle="Confirmed")
    with col4:
        probable = len(filtered_df[filtered_df["classification"] == "probable"])
        render_kpi_card("추정 탑승", probable, subtitle="Probable")
    with col5:
        render_kpi_card("인당 평균", f"{avg_rides:.1f}회",
                       subtitle="1인 하루 탑승 횟수")

    st.markdown("<br>", unsafe_allow_html=True)

    # ============================
    # High Passenger Warning
    # ============================
    if "trip_id" in filtered_df.columns:
        trip_pax_counts = filtered_df.groupby("trip_id").size()
        high_trips = trip_pax_counts[trip_pax_counts > HIGH_PASSENGER_WARNING]
        if len(high_trips) > 0:
            st.warning(
                f"**주의**: {len(high_trips)}건의 운행에서 탑승인원이 "
                f"{HIGH_PASSENGER_WARNING}명을 초과했습니다. "
                f"(최대 {high_trips.max()}명) "
                f"BLE 센서 특성상 실제보다 과다 집계될 수 있으니 참고하세요."
            )

    # ============================
    # Probable 분석 섹션 (v4 개편)
    # ============================
    if "classification" in filtered_df.columns:
        prob_df = filtered_df[filtered_df["classification"] == "probable"]
        if len(prob_df) > 0:
            total_filtered = len(filtered_df)
            prob_pct = len(prob_df) / total_filtered * 100 if total_filtered > 0 else 0

            with st.expander(
                f"추정(Probable) {len(prob_df)}건 ({prob_pct:.1f}%) -- "
                f"탑승으로 분류되었으나 확신도 낮음",
                expanded=False
            ):
                # Key message: Probable IS classified as boarding
                st.markdown(
                    '<div style="background:#2D2D1F; border-left:4px solid #F59E0B; '
                    'padding:12px 16px; border-radius:4px; margin-bottom:16px;">'
                    '<strong style="color:#F59E0B;">Probable = 호이스트 탑승으로 분류됨</strong>'
                    '<br><span style="color:#94A3B8;">확정(Confirmed)과 함께 총 탑승 건수에 포함됩니다. '
                    'Confirmed과의 차이는 확신도이지, 탑승 여부가 아닙니다. '
                    'BLE 통신 갭(30~90초 데이터 손실)으로 인해 비교 가능 구간이 줄어 확신도가 낮습니다.</span>'
                    '</div>',
                    unsafe_allow_html=True
                )

                # v4-specific Probable analysis
                if is_v4:
                    _render_probable_v4_analysis(prob_df)
                else:
                    _render_probable_legacy_analysis(prob_df)

                # LLM Probable explanation
                llm_status = get_llm_status()
                if llm_status["ready"]:
                    _render_probable_llm_insight(prob_df, filtered_df)

    # ============================
    # v4.5 Rate-Matching Score Charts
    # ============================
    if has_multi_evidence:
        render_section_header("분류 분석")

        col1, col2 = st.columns(2)
        with col1:
            fig = create_composite_score_histogram(filtered_df)
            st.plotly_chart(fig, use_container_width=True, key="pax_composite_hist")
        with col2:
            fig = create_evidence_distribution_chart(filtered_df)
            st.plotly_chart(fig, use_container_width=True, key="pax_evidence_dist")

        st.markdown("<br>", unsafe_allow_html=True)

    # ============================
    # Charts Row 1
    # ============================
    col1, col2 = st.columns(2)

    with col1:
        render_section_header("시간대별 탑승인원")
        fig = create_hourly_passenger_line(filtered_df)
        st.plotly_chart(fig, use_container_width=True, key="pax_hourly_line")

    with col2:
        render_section_header("업체별 분포")
        fig = create_company_distribution(filtered_df)
        st.plotly_chart(fig, use_container_width=True, key="pax_company_dist")

    # ============================
    # Charts Row 2
    # ============================
    col1, col2 = st.columns(2)

    with col1:
        render_section_header("분류별 분포")
        if "classification" in filtered_df.columns:
            class_counts = filtered_df["classification"].value_counts()
            colors = {
                "confirmed": "#22C55E",
                "probable": "#F59E0B",
                "rejected": "#64748B"
            }
            fig = px.pie(
                names=class_counts.index,
                values=class_counts.values,
                color=class_counts.index,
                color_discrete_map=colors,
                hole=0.4
            )
            fig.update_layout(height=300)
            fig = apply_dark_layout(fig)
            st.plotly_chart(fig, use_container_width=True, key="pax_class_pie")
        else:
            st.info("분류 데이터가 없습니다")

    with col2:
        render_section_header("호이스트별 이용 현황")
        hoist_counts = filtered_df["hoist_name"].value_counts()
        if len(hoist_counts) > 0:
            fig = px.bar(
                x=hoist_counts.index,
                y=hoist_counts.values,
                color_discrete_sequence=[COLORS["primary"]]
            )
            fig.update_layout(
                xaxis_title="호이스트", yaxis_title="탑승 횟수",
                height=300, showlegend=False
            )
            fig = apply_dark_layout(fig)
            st.plotly_chart(fig, use_container_width=True, key="pax_hoist_bar")
        else:
            st.info("데이터가 없습니다")

    # ============================
    # Detail Table (v4 adapted)
    # ============================
    render_section_header("탑승 기록 상세")

    if len(filtered_df) > 0:
        _render_detail_table(filtered_df, is_v4)
    else:
        st.info("선택한 조건에 해당하는 탑승 기록이 없습니다")

    # ============================
    # Score Distribution Summary
    # ============================
    st.markdown("<br>", unsafe_allow_html=True)
    _render_score_summary(filtered_df, is_v4)

    # ============================
    # LLM Insights Section
    # ============================
    llm_status = get_llm_status()
    if llm_status["ready"] and len(filtered_df) > 0:
        st.markdown("<br>", unsafe_allow_html=True)
        _render_llm_insights(
            filtered_df, passengers_df, trips_df, hoist_info,
            selected_company, selected_hoist
        )

    # ============================
    # Algorithm Details (collapsible)
    # ============================
    st.markdown("<br>", unsafe_allow_html=True)
    _render_algorithm_details_section(passengers_df)


# ============================================================
# Probable Analysis (v4)
# ============================================================

def _render_probable_v4_analysis(prob_df: pd.DataFrame):
    """Render v4-specific Probable analysis with rate-matching evidence."""
    st.markdown("**v4.5 Rate-Matching 증거 분석**")

    # Categorize Probable reasons
    # Primary: rate >= 0.40 but composite < 0.60
    primary_prob = prob_df[prob_df["rate_match_score"] >= 0.40]
    # Fallback: rate < 0.40 but delta_ratio reasonable
    fallback_prob = prob_df[prob_df["rate_match_score"] < 0.40]
    # Low BLE coverage
    if "rate_match_intervals" in prob_df.columns and "total_moving_intervals" in prob_df.columns:
        low_coverage = prob_df[
            prob_df["rate_match_intervals"] < prob_df["total_moving_intervals"] * 0.5
        ]
    else:
        low_coverage = pd.DataFrame()

    c1, c2, c3 = st.columns(3)
    with c1:
        render_kpi_card(
            "Primary Probable",
            f"{len(primary_prob)}건",
            subtitle="rate >= 0.40, composite < 0.60"
        )
    with c2:
        render_kpi_card(
            "Fallback Probable",
            f"{len(fallback_prob)}건",
            subtitle="rate < 0.40, delta ratio 증거"
        )
    with c3:
        render_kpi_card(
            "BLE 커버리지 부족",
            f"{len(low_coverage)}건",
            subtitle="매칭 구간 < 이동 구간의 50%"
        )

    st.markdown("---")
    st.markdown("**Probable 원인 상세**")

    st.markdown(
        f"- **Primary ({len(primary_prob)}건)**: "
        "기압 변화율 매칭 점수(rate_match)가 0.40 이상이지만, "
        "종합 점수(composite)가 0.60 미만. "
        "주로 delta_ratio(작업자/호이스트 기압 변화량 비율)가 이상 범위를 벗어나거나, "
        "방향성 불일치로 인해 종합 점수가 낮아진 경우."
    )
    st.markdown(
        f"- **Fallback ({len(fallback_prob)}건)**: "
        "rate_match가 0.40 미만이지만, delta_ratio가 0.5~1.3 범위이고 "
        "작업자 기압 변화가 0.5hPa 이상. BLE 통신 갭(콘크리트/철근 구조물로 인한 "
        "30~90초 데이터 손실)으로 인해 비교 가능 구간이 부족한 경우."
    )
    st.markdown(
        f"- **BLE 커버리지 부족 ({len(low_coverage)}건)**: "
        "호이스트 이동 구간 대비 작업자 BLE 수신 구간이 50% 미만. "
        "콘크리트/철근 구조물에 의한 BLE 통신 차폐로 신호가 간헐적으로 감지됨."
    )

    # Sample table
    st.markdown("---")
    st.markdown("**대표 Probable 케이스 (종합점수 낮은 순)**")
    sample = prob_df.nsmallest(10, "composite_score")

    display_cols = ["hoist_name", "boarding_time"]
    rename_map = {"hoist_name": "호이스트", "boarding_time": "시간"}

    for col in ["rate_match_score", "delta_ratio", "worker_delta_hpa", "composite_score"]:
        if col in sample.columns:
            display_cols.append(col)

    sample_display = sample[display_cols].copy()
    sample_display["boarding_time"] = sample_display["boarding_time"].dt.strftime("%H:%M")

    for sc in ["rate_match_score", "composite_score"]:
        if sc in sample_display.columns:
            sample_display[sc] = (sample_display[sc] * 100).round(0).astype(int).astype(str) + "%"

    if "delta_ratio" in sample_display.columns:
        sample_display["delta_ratio"] = sample_display["delta_ratio"].round(2)
    if "worker_delta_hpa" in sample_display.columns:
        sample_display["worker_delta_hpa"] = sample_display["worker_delta_hpa"].round(2)

    rename_map.update({
        "rate_match_score": "Rate Match",
        "delta_ratio": "Delta Ratio",
        "worker_delta_hpa": "기압변화(hPa)",
        "composite_score": "종합"
    })
    sample_display = sample_display.rename(columns=rename_map)
    st.dataframe(sample_display, use_container_width=True, hide_index=True, height=300)


def _render_probable_legacy_analysis(prob_df: pd.DataFrame):
    """Legacy v3 Probable analysis for backward compatibility."""
    waiting_like = prob_df[
        (prob_df.get("rssi_score", pd.Series(dtype=float)) >= 0.5) &
        (prob_df.get("pressure_score", pd.Series(dtype=float)) < 0.3)
    ] if "rssi_score" in prob_df.columns else pd.DataFrame()

    st.markdown(
        f"**Probable 패턴**: {len(prob_df)}건 중 "
        f"대기자 혼동 가능 {len(waiting_like)}건"
    )


# ============================================================
# Detail Table
# ============================================================

def _render_detail_table(filtered_df: pd.DataFrame, is_v4: bool):
    """Render the detail table with v4 or legacy columns."""
    if is_v4:
        columns = [
            "user_name", "company_name", "hoist_name",
            "boarding_time", "boarding_floor",
            "classification", "composite_score",
            "rate_match_score", "delta_ratio", "worker_delta_hpa"
        ]
    else:
        columns = [
            "user_name", "company_name", "hoist_name",
            "boarding_time", "boarding_floor",
            "classification", "composite_score",
            "rssi_score", "pressure_score"
        ]

    available_cols = [c for c in columns if c in filtered_df.columns]
    display_df = filtered_df[available_cols].copy()

    if "boarding_time" in display_df.columns:
        display_df["boarding_time"] = display_df["boarding_time"].dt.strftime("%H:%M:%S")

    # Format scores as percentages
    for col in ["composite_score", "rate_match_score", "rssi_score", "pressure_score"]:
        if col in display_df.columns:
            display_df[col] = (display_df[col] * 100).round(0).astype(int).astype(str) + "%"

    if "delta_ratio" in display_df.columns:
        display_df["delta_ratio"] = display_df["delta_ratio"].round(2)
    if "worker_delta_hpa" in display_df.columns:
        display_df["worker_delta_hpa"] = display_df["worker_delta_hpa"].round(2)

    # Classification labels
    if "classification" in display_df.columns:
        class_labels = {"confirmed": "확정", "probable": "추정", "rejected": "미분류"}
        display_df["classification"] = display_df["classification"].map(
            lambda x: class_labels.get(x, x)
        )

    rename = {
        "user_name": "작업자", "company_name": "업체", "hoist_name": "호이스트",
        "boarding_time": "탑승 시간", "boarding_floor": "탑승 층",
        "classification": "분류", "composite_score": "종합",
        "rate_match_score": "Rate Match", "delta_ratio": "Delta Ratio",
        "worker_delta_hpa": "기압변화(hPa)",
        "rssi_score": "RSSI", "pressure_score": "기압",
    }
    display_df = display_df.rename(columns=rename)
    display_df = display_df.sort_values("탑승 시간", ascending=False)

    st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)


# ============================================================
# Score Summary
# ============================================================

def _render_score_summary(filtered_df: pd.DataFrame, is_v4: bool):
    """Render score distribution summary."""
    if "composite_score" not in filtered_df.columns or len(filtered_df) == 0:
        return

    render_section_header("v4.5 Rate-Matching 점수 요약")

    total = len(filtered_df)
    confirmed = len(filtered_df[filtered_df["classification"] == "confirmed"])
    probable = len(filtered_df[filtered_df["classification"] == "probable"])

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "확정 (>=60%)",
            f"{confirmed}건 ({confirmed/total*100:.1f}%)" if total > 0 else "0건"
        )

    with col2:
        st.metric(
            "추정 (45-60%)",
            f"{probable}건 ({probable/total*100:.1f}%)" if total > 0 else "0건"
        )

    with col3:
        if is_v4 and "rate_match_score" in filtered_df.columns:
            avg_rate = filtered_df["rate_match_score"].mean()
            st.metric("평균 Rate Match", f"{avg_rate*100:.0f}%")
        elif "rssi_score" in filtered_df.columns:
            avg_rssi = filtered_df["rssi_score"].mean()
            st.metric("평균 RSSI 점수", f"{avg_rssi*100:.0f}%")

    with col4:
        if is_v4 and "worker_delta_hpa" in filtered_df.columns:
            avg_delta = filtered_df["worker_delta_hpa"].mean()
            st.metric("평균 기압변화", f"{avg_delta:.1f} hPa")
        elif "pressure_score" in filtered_df.columns:
            avg_pressure = filtered_df["pressure_score"].mean()
            st.metric("평균 기압 점수", f"{avg_pressure*100:.0f}%")


# ============================================================
# LLM Insights
# ============================================================

def _render_llm_insights(
    filtered_df, passengers_df, trips_df, hoist_info,
    selected_company, selected_hoist
):
    """Render all LLM insight sections."""

    # 1. Daily summary insight
    _render_daily_llm_insight(filtered_df, passengers_df, trips_df, selected_company)

    # 2. Per-hoist insight
    _render_hoist_llm_insight(filtered_df, passengers_df)

    # 3. Passenger pattern insight (existing, enhanced)
    _render_pattern_llm_insight(filtered_df, selected_company)


def _render_daily_llm_insight(filtered_df, passengers_df, trips_df, selected_company):
    """LLM: Daily passenger summary insight."""
    total = len(passengers_df)
    confirmed = len(passengers_df[passengers_df["classification"] == "confirmed"])
    probable = len(passengers_df[passengers_df["classification"] == "probable"])

    # Hourly distribution
    hourly = {}
    if "boarding_time" in passengers_df.columns:
        hourly = passengers_df.groupby(passengers_df["boarding_time"].dt.hour).size().to_dict()

    # Peak hour
    peak_hour = max(hourly, key=hourly.get) if hourly else None
    peak_count = hourly.get(peak_hour, 0) if peak_hour else 0

    # Per-hoist summary
    hoist_summary = {}
    for hoist in passengers_df["hoist_name"].unique():
        hdata = passengers_df[passengers_df["hoist_name"] == hoist]
        hoist_summary[hoist] = {
            "total": len(hdata),
            "confirmed": len(hdata[hdata["classification"] == "confirmed"]),
            "probable": len(hdata[hdata["classification"] == "probable"]),
        }

    # Company summary
    company_summary = {}
    for company in passengers_df["company_name"].dropna().unique():
        cdata = passengers_df[passengers_df["company_name"] == company]
        company_summary[company] = len(cdata)

    cache_key = get_cache_key(
        "pax_daily_v4", total, confirmed, probable, str(hourly)
    )
    cached = get_cached_insight(cache_key)
    if cached:
        render_data_comment(cached, "일일 탑승자 종합 분석")
    else:
        with st.spinner("일일 탑승자 종합 분석 중..."):
            insight = generate_passenger_daily_insight(
                total_passengers=total,
                confirmed_count=confirmed,
                probable_count=probable,
                hourly_pattern=hourly,
                peak_hour=peak_hour,
                peak_count=peak_count,
                hoist_summary=hoist_summary,
                company_summary=company_summary,
            )
        if insight:
            set_cached_insight(cache_key, insight)
            render_data_comment(insight, "일일 탑승자 종합 분석")


def _render_hoist_llm_insight(filtered_df, passengers_df):
    """LLM: Per-hoist analysis insight."""
    hoist_data = {}
    for hoist in passengers_df["hoist_name"].unique():
        hdata = passengers_df[passengers_df["hoist_name"] == hoist]
        hourly = {}
        if "boarding_time" in hdata.columns:
            hourly = hdata.groupby(hdata["boarding_time"].dt.hour).size().to_dict()

        # Company breakdown
        companies = hdata["company_name"].value_counts().head(5).to_dict()

        hoist_data[hoist] = {
            "total": len(hdata),
            "confirmed": len(hdata[hdata["classification"] == "confirmed"]),
            "probable": len(hdata[hdata["classification"] == "probable"]),
            "hourly": hourly,
            "top_companies": companies,
            "avg_composite": round(hdata["composite_score"].mean(), 3) if "composite_score" in hdata.columns else 0,
        }

    cache_key = get_cache_key("pax_hoist_v4", str(hoist_data))
    cached = get_cached_insight(cache_key)
    if cached:
        render_data_comment(cached, "호이스트별 이용 분석")
    else:
        with st.spinner("호이스트별 이용 분석 중..."):
            insight = generate_hoist_usage_insight(hoist_data=hoist_data)
        if insight:
            set_cached_insight(cache_key, insight)
            render_data_comment(insight, "호이스트별 이용 분석")


def _render_probable_llm_insight(prob_df, full_df):
    """LLM: Probable classification explanation."""
    prob_stats = {
        "count": len(prob_df),
        "total": len(full_df),
        "pct": round(len(prob_df) / max(len(full_df), 1) * 100, 1),
    }
    if "rate_match_score" in prob_df.columns:
        prob_stats["avg_rate_match"] = round(prob_df["rate_match_score"].mean(), 3)
        prob_stats["primary_count"] = len(prob_df[prob_df["rate_match_score"] >= 0.40])
        prob_stats["fallback_count"] = len(prob_df[prob_df["rate_match_score"] < 0.40])
    if "delta_ratio" in prob_df.columns:
        prob_stats["avg_delta_ratio"] = round(prob_df["delta_ratio"].mean(), 2)
    if "worker_delta_hpa" in prob_df.columns:
        prob_stats["avg_worker_delta"] = round(prob_df["worker_delta_hpa"].mean(), 2)

    cache_key = get_cache_key("pax_probable_v4", str(prob_stats))
    cached = get_cached_insight(cache_key)
    if cached:
        render_data_comment(cached, "Probable 분류 해석")
    else:
        with st.spinner("Probable 분류 해석 중..."):
            insight = generate_probable_explanation_insight(prob_stats=prob_stats)
        if insight:
            set_cached_insight(cache_key, insight)
            render_data_comment(insight, "Probable 분류 해석")


def _render_pattern_llm_insight(filtered_df, selected_company):
    """LLM: passenger pattern insight (enhanced from original)."""
    company_stats = {}
    for company in filtered_df["company_name"].dropna().unique():
        company_data = filtered_df[filtered_df["company_name"] == company]
        company_stats[company] = {
            "count": len(company_data),
            "avg_floor": company_data["boarding_floor"].mean() if "boarding_floor" in company_data.columns else 0,
        }

    hourly_pattern = {}
    if "boarding_time" in filtered_df.columns:
        hourly_counts = filtered_df.groupby(filtered_df["boarding_time"].dt.hour).size()
        hourly_pattern = hourly_counts.to_dict()

    classification_summary = {}
    if "classification" in filtered_df.columns:
        classification_summary = filtered_df["classification"].value_counts().to_dict()

    cache_key = get_cache_key(
        "passenger_pattern_v4", len(filtered_df), selected_company, str(hourly_pattern)
    )
    cached = get_cached_insight(cache_key)
    if cached:
        render_data_comment(cached, "탑승자 이용 패턴 해석")
    else:
        with st.spinner("탑승자 패턴 해석 중..."):
            insight = generate_passenger_pattern_insight(
                company_stats=company_stats,
                hourly_pattern=hourly_pattern,
                classification_summary=classification_summary,
            )
        if insight:
            set_cached_insight(cache_key, insight)
            render_data_comment(insight, "탑승자 이용 패턴 해석")


# ============================================================
# Algorithm Details Section
# ============================================================

def _render_algorithm_details_section(passengers_df: pd.DataFrame):
    """Render collapsible algorithm details section."""
    with st.expander("v4.5 Rate-Matching 알고리즘 상세", expanded=False):
        st.markdown("""
### 알고리즘 개요

v4.5 Rate-Matching 알고리즘은 **기압 변화율(dp/dt) 비교**를 핵심으로 합니다.

### Sequential Filter (순차 필터링)

```
1. RSSI 후보 선별 (-75dBm)
   호이스트에 장착된 이동형 게이트웨이(mov_gw)에서
   작업자 T-Ward가 -75dBm 이상으로 수신되면 해당 호이스트의 탑승 후보.
   이 단계는 "호이스트 근처에 있었는가"만 확인합니다.

2. 고도 변화 확인 (>= 0.3 hPa)
   작업자의 기압센서에서 의미있는 수직 이동이 감지되어야 합니다.

3. 멀티스케일 Rate Matching
   dp/dt(작업자) ≈ dp/dt(호이스트)를 10초/30초/60초 3개 윈도우에서 비교.
   BLE 통신 갭(콘크리트/철근 구조물로 인한 30~90초 데이터 손실)에 강건합니다.

4. Composite Scoring
   rate_match × 0.65 + delta_ratio × 0.25 + direction × 0.10

5. RSSI 탑승구간 재배정
   같은 건물 내 여러 호이스트가 동시 운행 시, 작업자의 탑승 구간
   (boarding~alighting) 동안 평균 RSSI가 가장 강한 호이스트에 최종 배정.
```

### 분류 기준

| 분류 | 조건 | 의미 |
|------|------|------|
| **Confirmed** | composite >= 0.60 | 기압 변화율이 호이스트와 잘 일치 |
| **Probable** | composite 0.45~0.60 | 호이스트 탑승으로 분류됨. BLE 통신 갭으로 확신도 낮음 |

### Probable 세부 경로

| 유형 | 조건 | 설명 |
|------|------|------|
| **Primary** | rate >= 0.40, composite < 0.60 | rate matching은 OK이나, delta_ratio/direction이 낮아 종합 점수 부족 |
| **Fallback** | rate < 0.40, delta_ratio 0.5~1.3, worker_delta >= 0.5hPa | BLE gap으로 비교 구간 부족하나, 전체 기압 변화량 일치 |

### 핵심 파라미터

| 파라미터 | 값 | 설명 |
|----------|-----|------|
| RSSI threshold | -75 dBm | 후보 선별 기준 (점수에 반영하지 않음) |
| Min altitude change | 0.3 hPa | 최소 수직 이동 |
| Rate weight | 0.65 | 기압 변화율 매칭 가중치 |
| Delta weight | 0.25 | 기압 변화량 비율 가중치 (이상적 delta_ratio = 1.0) |
| Direction weight | 0.10 | 방향 일치 가중치 |
| Confirmed threshold | 0.60 | 확정 분류 기준 |
| Probable threshold | 0.45 | 추정 분류 기준 |

### 핵심 원리

**RSSI(신호 강도)는 점수에 반영하지 않습니다.** 후보 선별에만 사용합니다.
판정의 핵심은 **"작업자의 기압 변화율이 호이스트의 기압 변화율과 일치하는가"** 입니다.
같은 엘리베이터에 타면 같은 속도로 기압이 변하기 때문입니다.

### 핵심 개념

- **Rate Matching**: 작업자와 호이스트의 기압 변화 속도(dp/dt)가 일치하는지 비교
- **Delta Ratio**: worker_delta / hoist_delta -- 1.0에 가까울수록 동일한 기압 변화량
- **BLE Gap**: 콘크리트/철근 구조물로 인해 30~90초간 BLE 통신이 끊기는 현상
- **대기시간**: 호이스트 근처에서 RSSI가 처음 감지된 시점부터 실제 탑승(boarding) 시점까지의 시간
        """)

        # LLM algorithm explanation
        llm_status = get_llm_status()
        if llm_status["ready"] and len(passengers_df) > 0:
            total = len(passengers_df)
            confirmed = len(passengers_df[passengers_df["classification"] == "confirmed"])
            probable = len(passengers_df[passengers_df["classification"] == "probable"])

            stats = {
                "total": total,
                "confirmed": confirmed,
                "probable": probable,
                "confirmed_pct": round(confirmed / max(total, 1) * 100, 1),
                "probable_pct": round(probable / max(total, 1) * 100, 1),
            }
            if "rate_match_score" in passengers_df.columns:
                stats["avg_rate_match"] = round(passengers_df["rate_match_score"].mean(), 3)
            if "composite_score" in passengers_df.columns:
                stats["avg_composite"] = round(passengers_df["composite_score"].mean(), 3)

            cache_key = get_cache_key("algo_explain_v4", str(stats))
            cached = get_cached_insight(cache_key)
            if cached:
                render_data_comment(cached, "알고리즘 성능 해석")
            else:
                with st.spinner("알고리즘 성능 해석 중..."):
                    insight = generate_algorithm_explanation(algo_stats=stats)
                if insight:
                    set_cached_insight(cache_key, insight)
                    render_data_comment(insight, "알고리즘 성능 해석")
