"""탑승자 분석 탭 - Passenger tracking with Multi-Evidence (Dark Theme)"""

import streamlit as st
import pandas as pd
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
    render_data_comment, get_cache_key, get_cached_insight, set_cached_insight
)


def render_passenger_tab(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    hoist_info: Dict
) -> None:
    """
    Render passenger tracking tab (탑승자 분석)

    Args:
        trips_df: DataFrame with trip data
        passengers_df: DataFrame with passenger classifications
        hoist_info: Dict of hoist configurations
    """
    if len(passengers_df) == 0:
        render_empty_state(
            "탑승자 데이터가 없습니다. 데이터 관리 탭에서 처리를 실행하세요.",
            icon=""
        )
        return

    # Check if multi-evidence columns exist
    has_multi_evidence = "composite_score" in passengers_df.columns

    # ============================
    # Filters
    # ============================
    col1, col2, col3, col4 = st.columns([2, 2, 2, 2])

    with col1:
        companies = sorted(passengers_df["company_name"].dropna().unique())
        selected_company = st.selectbox(
            "업체",
            options=["전체"] + list(companies),
            key="pax_company"
        )

    with col2:
        if has_multi_evidence:
            classification_options = ["전체", "확정 (confirmed)", "추정 (probable)"]
            selected_classification = st.selectbox(
                "분류",
                options=classification_options,
                key="pax_classification"
            )
        else:
            confidence_options = ["전체", "70% 이상", "80% 이상", "90% 이상"]
            selected_confidence = st.selectbox(
                "신뢰도 필터",
                options=confidence_options,
                key="pax_confidence"
            )

    with col3:
        hoists = sorted(passengers_df["hoist_name"].unique())
        selected_hoist = st.selectbox(
            "호이스트",
            options=["전체"] + list(hoists),
            key="pax_hoist"
        )

    with col4:
        if has_multi_evidence:
            score_threshold = st.slider(
                "최소 종합점수",
                min_value=0.0,
                max_value=1.0,
                value=0.0,
                step=0.1,
                key="pax_score_threshold"
            )
        else:
            st.empty()

    # Filter data
    filtered_df = passengers_df.copy()

    if selected_company != "전체":
        filtered_df = filtered_df[filtered_df["company_name"] == selected_company]

    if has_multi_evidence:
        if selected_classification != "전체":
            class_map = {
                "확정 (confirmed)": "confirmed",
                "추정 (probable)": "probable"
            }
            target_class = class_map.get(selected_classification)
            if target_class:
                filtered_df = filtered_df[filtered_df["classification"] == target_class]

        if score_threshold > 0:
            filtered_df = filtered_df[filtered_df["composite_score"] >= score_threshold]
    else:
        if selected_confidence != "전체":
            threshold_map = {
                "70% 이상": 0.7,
                "80% 이상": 0.8,
                "90% 이상": 0.9
            }
            threshold = threshold_map.get(selected_confidence, 0)
            filtered_df = filtered_df[filtered_df["confidence"] >= threshold]

    if selected_hoist != "전체":
        filtered_df = filtered_df[filtered_df["hoist_name"] == selected_hoist]

    st.markdown("---")

    # ============================
    # KPIs (adapted for multi-evidence)
    # ============================
    render_info_tooltip(
        "탑승자 분류 방식 (Multi-Evidence Classification)",
        "호이스트 탑승 여부를 **4가지 증거**를 종합하여 판정합니다:\n\n"
        "1. **RSSI 패턴** (25%): 호이스트 센서에서 작업자 태그의 신호 강도 지속성\n"
        "2. **기압 프로파일** (35%): 호이스트와 작업자의 기압 변화 패턴 상관관계\n"
        "3. **공간 이동** (25%): 탑승 전후 위치 변화 확인\n"
        "4. **시간 정렬** (15%): 신호 상승/하강 타이밍\n\n"
        "**분류 기준**:\n"
        "- **확정 (Confirmed)**: 종합 점수 ≥ 0.6 — 탑승이 확실한 경우\n"
        "- **추정 (Probable)**: 종합 점수 ≥ 0.5 — 탑승 가능성이 높은 경우\n\n"
        "⚠️ BLE 통신 특성상 일부 신호 누락이 있을 수 있으며, 이를 감안하여 분류합니다."
    )
    render_info_tooltip(
        "KPI 지표 설명",
        "- **총 탑승 건수**: 호이스트 탑승이 감지된 총 이벤트 수 "
        "(한 사람이 하루 10번 타면 10건)\n"
        "- **고유 작업자**: user_no(작업자 고유 ID) 기준 중복 제거된 실제 인원\n"
        "- **참여 업체**: 탑승 작업자가 소속된 업체 수\n"
        "- **인당 평균 탑승**: 작업자 1명의 하루 평균 탑승 횟수"
    )
    # user_no = 작업자 고유 ID (가장 정확한 식별자)
    if "user_no" in filtered_df.columns:
        valid = filtered_df[filtered_df["user_no"].notna() & (filtered_df["user_no"] != "")]
        unique_workers = valid["user_no"].nunique()
    else:
        unique_workers = filtered_df["mac_address"].nunique()
    unique_companies = filtered_df["company_name"].nunique()
    avg_rides = len(filtered_df) / unique_workers if unique_workers > 0 else 0

    if has_multi_evidence:
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
    else:
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            render_kpi_card("총 탑승 건수", f"{len(filtered_df):,}",
                           subtitle="탑승 이벤트 합계")

        with col2:
            render_kpi_card("고유 작업자", f"{unique_workers}명",
                           subtitle=f"{unique_companies}개 업체")

        with col3:
            unique_companies = filtered_df["company_name"].nunique()
            render_kpi_card("참여 업체 수", unique_companies)

        with col4:
            avg_conf = filtered_df["confidence"].mean() if len(filtered_df) > 0 else 0
            render_kpi_card("평균 신뢰도", f"{avg_conf * 100:.1f}%")

    st.markdown("<br>", unsafe_allow_html=True)

    # ============================
    # Multi-Evidence Charts (NEW)
    # ============================
    if has_multi_evidence:
        render_section_header("Multi-Evidence 분류 분석")

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
        if has_multi_evidence:
            render_section_header("분류별 분포")
            if "classification" in filtered_df.columns:
                import plotly.express as px

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
        else:
            render_section_header("분류 신뢰도 분포")
            fig = create_confidence_histogram(filtered_df)
            st.plotly_chart(fig, use_container_width=True, key="pax_confidence_hist")

    with col2:
        render_section_header("호이스트별 이용 현황")
        hoist_counts = filtered_df["hoist_name"].value_counts()
        if len(hoist_counts) > 0:
            import plotly.express as px

            fig = px.bar(
                x=hoist_counts.index,
                y=hoist_counts.values,
                color_discrete_sequence=[COLORS["primary"]]
            )
            fig.update_layout(
                xaxis_title="호이스트",
                yaxis_title="탑승 횟수",
                height=300,
                showlegend=False
            )
            fig = apply_dark_layout(fig)
            st.plotly_chart(fig, use_container_width=True, key="pax_hoist_bar")
        else:
            st.info("데이터가 없습니다")

    # ============================
    # Detail Table (adapted for multi-evidence)
    # ============================
    render_section_header("탑승 기록 상세")

    if len(filtered_df) > 0:
        if has_multi_evidence:
            # Multi-evidence columns
            columns = [
                "user_name", "company_name", "hoist_name",
                "boarding_time", "boarding_floor",
                "classification", "composite_score",
                "rssi_score", "pressure_score", "spatial_score", "timing_score"
            ]
            available_cols = [c for c in columns if c in filtered_df.columns]
            display_df = filtered_df[available_cols].copy()

            display_df["boarding_time"] = display_df["boarding_time"].dt.strftime("%H:%M:%S")

            # Format scores as percentages
            score_cols = ["composite_score", "rssi_score", "pressure_score", "spatial_score", "timing_score"]
            for col in score_cols:
                if col in display_df.columns:
                    display_df[col] = (display_df[col] * 100).round(0).astype(int).astype(str) + "%"

            # Classification labels
            if "classification" in display_df.columns:
                class_labels = {"confirmed": "확정", "probable": "추정", "rejected": "미분류"}
                display_df["classification"] = display_df["classification"].map(
                    lambda x: class_labels.get(x, x)
                )

            display_df = display_df.rename(columns={
                "user_name": "작업자",
                "company_name": "업체",
                "hoist_name": "호이스트",
                "boarding_time": "탑승 시간",
                "boarding_floor": "탑승 층",
                "classification": "분류",
                "composite_score": "종합",
                "rssi_score": "RSSI",
                "pressure_score": "기압",
                "spatial_score": "공간",
                "timing_score": "타이밍"
            })
        else:
            display_df = filtered_df[[
                "user_name", "company_name", "hoist_name",
                "boarding_time", "boarding_floor", "confidence"
            ]].copy()

            display_df["boarding_time"] = display_df["boarding_time"].dt.strftime("%H:%M:%S")
            display_df["confidence"] = (display_df["confidence"] * 100).round(1).astype(str) + "%"

            display_df = display_df.rename(columns={
                "user_name": "작업자",
                "company_name": "업체",
                "hoist_name": "호이스트",
                "boarding_time": "탑승 시간",
                "boarding_floor": "탑승 층",
                "confidence": "신뢰도"
            })

        # Sort by time
        display_df = display_df.sort_values("탑승 시간", ascending=False)

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            height=400
        )
    else:
        st.info("선택한 조건에 해당하는 탑승 기록이 없습니다")

    # ============================
    # Score Distribution Summary
    # ============================
    st.markdown("<br>", unsafe_allow_html=True)

    if has_multi_evidence:
        render_section_header("Multi-Evidence 점수 요약")

        if len(filtered_df) > 0:
            total = len(filtered_df)
            confirmed = len(filtered_df[filtered_df["classification"] == "confirmed"])
            probable = len(filtered_df[filtered_df["classification"] == "probable"])
            rejected = len(filtered_df[filtered_df["classification"] == "rejected"]) if "rejected" in filtered_df["classification"].values else 0

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric(
                    "확정 (>=60%)",
                    f"{confirmed}건 ({confirmed/total*100:.1f}%)" if total > 0 else "0건"
                )

            with col2:
                st.metric(
                    "추정 (40-60%)",
                    f"{probable}건 ({probable/total*100:.1f}%)" if total > 0 else "0건"
                )

            with col3:
                avg_rssi = filtered_df["rssi_score"].mean() if "rssi_score" in filtered_df.columns else 0
                avg_pressure = filtered_df["pressure_score"].mean() if "pressure_score" in filtered_df.columns else 0
                st.metric(
                    "평균 RSSI 점수",
                    f"{avg_rssi*100:.0f}%"
                )

            with col4:
                st.metric(
                    "평균 기압 점수",
                    f"{avg_pressure*100:.0f}%"
                )
    else:
        render_section_header("신뢰도 구간별 분포")

        if len(filtered_df) > 0:
            total = len(filtered_df)
            high = len(filtered_df[filtered_df["confidence"] >= 0.9])
            medium = len(filtered_df[(filtered_df["confidence"] >= 0.7) & (filtered_df["confidence"] < 0.9)])
            low = len(filtered_df[filtered_df["confidence"] < 0.7])

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric(
                    "높음 (90% 이상)",
                    f"{high}건 ({high/total*100:.1f}%)" if total > 0 else "0건"
                )

            with col2:
                st.metric(
                    "보통 (70-90%)",
                    f"{medium}건 ({medium/total*100:.1f}%)" if total > 0 else "0건"
                )

            with col3:
                st.metric(
                    "낮음 (70% 미만)",
                    f"{low}건 ({low/total*100:.1f}%)" if total > 0 else "0건"
                )

    # ============================
    # LLM 탑승자 패턴 해석 (접힌 상태)
    # ============================
    llm_status = get_llm_status()
    if llm_status["ready"] and len(filtered_df) > 0:
        st.markdown("<br>", unsafe_allow_html=True)

        # 업체별 통계 집계
        company_stats = {}
        for company in filtered_df["company_name"].dropna().unique():
            company_data = filtered_df[filtered_df["company_name"] == company]
            company_stats[company] = {
                "count": len(company_data),
                "avg_floor": company_data["boarding_floor"].mean() if "boarding_floor" in company_data.columns else 0,
            }

        # 시간대별 패턴
        hourly_pattern = {}
        if "boarding_time" in filtered_df.columns:
            hourly_counts = filtered_df.groupby(filtered_df["boarding_time"].dt.hour).size()
            hourly_pattern = hourly_counts.to_dict()

        # 분류별 요약
        classification_summary = {}
        if has_multi_evidence and "classification" in filtered_df.columns:
            classification_summary = filtered_df["classification"].value_counts().to_dict()
        elif "confidence" in filtered_df.columns:
            high_conf = len(filtered_df[filtered_df["confidence"] >= 0.8])
            low_conf = len(filtered_df[filtered_df["confidence"] < 0.8])
            classification_summary = {"high_confidence": high_conf, "low_confidence": low_conf}

        cache_key = get_cache_key(
            "passenger_pattern",
            len(filtered_df),
            selected_company,
            str(hourly_pattern),
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
