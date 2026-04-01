"""층별 분석 탭 - Floor-level metrics (Dark Theme)"""

import streamlit as st
import pandas as pd
import plotly.express as px
from typing import Dict

from ..ui.components import render_section_header, render_empty_state, render_info_tooltip
from ..ui.charts import create_sankey, create_floor_heatmap
from ..ui.styles import COLORS, apply_dark_layout
from ..analysis.metrics import calculate_floor_metrics


def render_floor_tab(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    floor_elevations: Dict[str, Dict[str, float]]
) -> None:
    """
    Render floor analysis tab (층별 분석)
    """
    if len(trips_df) == 0:
        render_empty_state(
            "운행 데이터가 없습니다. 데이터 관리 탭에서 처리를 실행하세요.",
            icon=""
        )
        return

    # ============================
    # Building selector
    # ============================
    buildings = sorted(trips_df["building_name"].unique())
    selected_building = st.selectbox(
        "건물 선택",
        options=buildings,
        key="floor_building"
    )

    st.markdown("---")

    # ============================
    # Floor statistics
    # ============================
    render_section_header(f"{selected_building} 층별 통계")

    floor_stats = calculate_floor_metrics(trips_df, passengers_df, selected_building)

    if len(floor_stats) > 0:
        col1, col2 = st.columns(2)

        with col1:
            display_df = floor_stats[[
                "floor_name", "stop_count", "boarding_count", "alighting_count"
            ]].copy()

            display_df = display_df.rename(columns={
                "floor_name": "층",
                "stop_count": "정차 횟수",
                "boarding_count": "승차 인원",
                "alighting_count": "하차 인원"
            })

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True
            )

            # Summary metrics (safe idxmax)
            total_stops = floor_stats["stop_count"].sum()
            if total_stops > 0:
                most_active = floor_stats.loc[
                    floor_stats["stop_count"].idxmax(), "floor_name"
                ]
            else:
                most_active = "없음"

            col_a, col_b = st.columns(2)
            with col_a:
                st.metric("총 정차 횟수", f"{total_stops}회")
            with col_b:
                st.metric("가장 활발한 층", most_active)

        with col2:
            fig = create_floor_heatmap(trips_df, selected_building)
            st.plotly_chart(fig, use_container_width=True, key="floor_heatmap")

    else:
        st.info("이 건물의 층별 통계가 없습니다")

    st.markdown("---")

    # ============================
    # Floor-to-Floor Flow
    # ============================
    render_section_header("층간 이동 흐름")
    render_info_tooltip(
        "층간 이동 흐름 (Sankey Diagram)",
        "호이스트가 **출발층에서 도착층으로 이동한 흐름**을 보여줍니다.\n\n"
        "- 왼쪽: 출발층, 오른쪽: 도착층\n"
        "- 선 두께: 해당 경로의 운행 횟수에 비례\n"
        "- 가장 두꺼운 선이 가장 많이 이용된 경로\n\n"
        "예: 1F→5F가 가장 두꺼우면, 1층에서 5층으로의 이동이 가장 빈번한 것입니다."
    )

    col1, col2 = st.columns([2, 1])

    with col1:
        fig = create_sankey(trips_df, selected_building)
        st.plotly_chart(fig, use_container_width=True, key="floor_sankey")

    with col2:
        st.markdown("**층별 고도**")

        if selected_building in floor_elevations:
            elev_data = []
            for floor, elevation in floor_elevations[selected_building].items():
                elev_data.append({
                    "층": floor,
                    "고도 (m)": f"{elevation:.1f}"
                })

            elev_df = pd.DataFrame(elev_data)
            elev_df["_sort"] = elev_df["고도 (m)"].astype(float)
            elev_df = elev_df.sort_values("_sort", ascending=False).drop("_sort", axis=1)

            st.dataframe(
                elev_df,
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("이 건물의 고도 데이터가 없습니다")

    st.markdown("---")

    # ============================
    # Floor patterns
    # ============================
    render_section_header("층별 방문 패턴")
    render_info_tooltip(
        "층별 방문 패턴",
        "호이스트가 **어느 층에서 자주 출발하고, 어느 층에 자주 도착하는지** 보여줍니다.\n\n"
        "- 출발 층 빈도가 높은 층 = 작업자가 많이 대기하는 층\n"
        "- 도착 층 빈도가 높은 층 = 작업이 집중되는 층"
    )

    building_trips = trips_df[trips_df["building_name"] == selected_building]

    start_floors = building_trips["start_floor"].value_counts()
    end_floors = building_trips["end_floor"].value_counts()

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**출발 층 빈도**")
        if len(start_floors) > 0:
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
            st.plotly_chart(fig, use_container_width=True, key="floor_start_bar")

    with col2:
        st.markdown("**도착 층 빈도**")
        if len(end_floors) > 0:
            fig = px.bar(
                x=end_floors.head(5).index,
                y=end_floors.head(5).values,
                color_discrete_sequence=[COLORS["success"]]
            )
            fig.update_layout(
                xaxis_title="층", yaxis_title="횟수",
                height=250, showlegend=False
            )
            fig = apply_dark_layout(fig)
            st.plotly_chart(fig, use_container_width=True, key="floor_end_bar")

    # Floor-to-floor transition matrix
    st.markdown("---")
    render_section_header("층간 이동 매트릭스")

    if len(building_trips) > 0:
        transition = pd.crosstab(
            building_trips["start_floor"],
            building_trips["end_floor"],
            margins=True,
            margins_name="합계"
        )

        def floor_sort_key(floor):
            if floor == "합계":
                return 999
            if floor == "Roof":
                return 100
            if floor.startswith("B"):
                return -int(floor[1:].replace("F", ""))
            return int(floor.replace("F", ""))

        sorted_index = sorted(transition.index, key=floor_sort_key)
        sorted_cols = sorted(transition.columns, key=floor_sort_key)
        transition = transition.reindex(index=sorted_index, columns=sorted_cols)

        st.dataframe(transition, use_container_width=True)
    else:
        st.info("이동 데이터가 없습니다")

    # ============================
    # Floor Occupancy Analysis (유입/유출/재실)
    # ============================
    st.markdown("---")
    render_section_header("층별 유입·유출·재실 인원")
    render_info_tooltip(
        "층별 유입·유출 분석",
        "1층 이상의 모든 층은 **호이스트를 통해서만 이동**할 수 있으므로,\n"
        "v4.5 Rate-Matching 기반 탑승 데이터로 각 층의 유입/유출 인원을 추정합니다.\n\n"
        "- **유입**: 해당 층에 **도착**한 탑승 건수 (end_floor 기준)\n"
        "- **유출**: 해당 층에서 **출발**한 탑승 건수 (start_floor 기준)\n"
        "- **순유입**: 유입 - 유출 (양수 = 인원 증가, 음수 = 인원 감소)\n\n"
        "**검증 원리**: 하루 끝에 모든 작업자가 퇴근하면 상층 순유입 합계 ≈ 0 이어야 합니다.\n"
        "순유입이 크게 양수인 층은 작업자가 아직 남아있거나, 감지 누락이 있을 수 있습니다."
    )

    if len(passengers_df) > 0 and len(building_trips) > 0:
        # Join passengers with trip floor info
        pax_with_floors = passengers_df.merge(
            trips_df[["trip_id", "start_floor", "end_floor", "building_name"]],
            on="trip_id", how="left"
        )
        bld_pax = pax_with_floors[pax_with_floors["building_name"] == selected_building]

        if len(bld_pax) > 0:
            inflow = bld_pax["end_floor"].value_counts()
            outflow = bld_pax["start_floor"].value_counts()
            all_floors_set = sorted(
                set(inflow.index) | set(outflow.index),
                key=lambda x: int(x.replace("F", "").replace("Roof", "100").replace("B", "-"))
                if x not in ("합계",) else 999
            )

            floor_data = []
            for f in all_floors_set:
                i = int(inflow.get(f, 0))
                o = int(outflow.get(f, 0))
                net = i - o
                floor_data.append({
                    "층": f,
                    "유입 (도착)": i,
                    "유출 (출발)": o,
                    "순유입": net,
                    "상태": "증가" if net > 0 else ("감소" if net < 0 else "균형"),
                })

            floor_occ_df = pd.DataFrame(floor_data)

            # Chart
            import plotly.graph_objects as go
            fig = go.Figure()
            fig.add_trace(go.Bar(
                name="유입", x=floor_occ_df["층"], y=floor_occ_df["유입 (도착)"],
                marker_color="#22C55E"
            ))
            fig.add_trace(go.Bar(
                name="유출", x=floor_occ_df["층"], y=floor_occ_df["유출 (출발)"],
                marker_color="#EF4444"
            ))
            fig.add_trace(go.Scatter(
                name="순유입", x=floor_occ_df["층"], y=floor_occ_df["순유입"],
                mode="lines+markers+text",
                text=[f"{v:+d}" for v in floor_occ_df["순유입"]],
                textposition="top center",
                textfont=dict(size=11, color="white"),
                line=dict(color="#F59E0B", width=2),
                marker=dict(size=8, color="#F59E0B"),
            ))
            fig.update_layout(
                barmode="group",
                title=f"{selected_building} 층별 유입·유출 인원",
                xaxis_title="층", yaxis_title="인원 (명)",
                height=350, showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                plot_bgcolor="#0E1117", paper_bgcolor="#0E1117",
                font=dict(color="white"),
            )
            fig.update_xaxes(gridcolor="#1E293B")
            fig.update_yaxes(gridcolor="#1E293B")
            st.plotly_chart(fig, use_container_width=True, key="floor_occupancy_chart")

            # Table
            st.dataframe(
                floor_occ_df.style.map(
                    lambda v: "color: #22C55E" if v == "증가"
                    else ("color: #EF4444" if v == "감소" else "color: #888"),
                    subset=["상태"]
                ),
                use_container_width=True,
                hide_index=True,
            )

            # Validation check
            upper_net = floor_occ_df[floor_occ_df["층"] != "1F"]["순유입"].sum()
            ground_net = floor_occ_df[floor_occ_df["층"] == "1F"]["순유입"].sum()
            st.caption(
                f"검증: 상층 순유입 합계 = {upper_net:+d}명, "
                f"1층 순유입 = {ground_net:+d}명 "
                f"(이론상 상층 합계 ≈ -1층 순유입)"
            )
        else:
            st.info("해당 건물의 탑승자 데이터가 없습니다")
    else:
        st.info("탑승자 데이터가 없습니다. 데이터 관리 탭에서 처리를 실행하세요.")
