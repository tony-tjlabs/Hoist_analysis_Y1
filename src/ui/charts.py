"""Plotly chart generators (Dark Theme)"""

import ast
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Optional, List, Dict

from .styles import (
    BUILDING_COLORS, DIRECTION_COLORS, COLORS,
    PLOTLY_DARK_LAYOUT, apply_dark_layout,
    get_passenger_color, get_evidence_color, get_classification_color
)


def _hex_to_rgba(hex_color: str, alpha: float = 1.0) -> str:
    """Convert hex color to rgba string for Plotly compatibility"""
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def create_trip_timeline(
    trips_df: pd.DataFrame,
    hoist_filter: Optional[str] = None
) -> go.Figure:
    """
    Create Gantt chart for trip visualization (Dark Theme)

    Args:
        trips_df: DataFrame with trip data
        hoist_filter: Optional hoist name filter

    Returns:
        Plotly figure
    """
    if len(trips_df) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    df = trips_df.copy()
    if hoist_filter:
        df = df[df["hoist_name"] == hoist_filter]

    if len(df) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    # Prepare data for Gantt
    df["Task"] = df["hoist_name"]
    df["Start"] = df["start_time"]
    df["Finish"] = df["end_time"]
    df["Direction"] = df["direction"]

    # Create figure
    fig = px.timeline(
        df,
        x_start="Start",
        x_end="Finish",
        y="Task",
        color="Direction",
        color_discrete_map=DIRECTION_COLORS,
        hover_data=["start_floor", "end_floor", "duration_sec"]
    )

    fig.update_layout(
        title="운행 타임라인",
        xaxis_title="시간",
        yaxis_title="호이스트",
        height=400,
        showlegend=True,
    )

    fig.update_yaxes(categoryorder="category ascending")

    return apply_dark_layout(fig)


def create_trip_gantt_with_passengers(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    building: Optional[str] = None
) -> go.Figure:
    """
    Create Gantt chart with passenger count overlay (Dark Theme)

    Args:
        trips_df: DataFrame with trip data
        passengers_df: DataFrame with passenger classifications
        building: Optional building filter

    Returns:
        Plotly figure
    """
    if len(trips_df) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    df = trips_df.copy()

    # Building filter
    if building and building != "전체":
        df = df[df["building_name"] == building]

    if len(df) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    # Calculate passenger count per trip
    if len(passengers_df) > 0 and "trip_id" in passengers_df.columns:
        pax_counts = passengers_df.groupby("trip_id").size().to_dict()
        df["pax_count"] = df["trip_id"].map(lambda x: pax_counts.get(x, 0))
    else:
        df["pax_count"] = df["passenger_count"] if "passenger_count" in df.columns else 0

    # Sort by building and hoist for better grouping
    df = df.sort_values(["building_name", "hoist_name", "start_time"])

    # Create figure with subplots per building
    buildings = df["building_name"].unique()
    n_buildings = len(buildings)

    fig = make_subplots(
        rows=n_buildings, cols=1,
        subplot_titles=[f"{b} ({len(df[df['building_name']==b]['hoist_name'].unique())}대)" for b in buildings],
        vertical_spacing=0.08,
        shared_xaxes=True
    )

    for idx, bldg in enumerate(buildings, 1):
        bldg_df = df[df["building_name"] == bldg]
        hoists = sorted(bldg_df["hoist_name"].unique())

        for hoist in hoists:
            hoist_df = bldg_df[bldg_df["hoist_name"] == hoist]

            for _, row in hoist_df.iterrows():
                direction = row["direction"]
                color = DIRECTION_COLORS.get(direction, COLORS["primary"])
                pax = row["pax_count"]

                # Short hoist name for display
                short_name = hoist.split("_")[-1]

                # Hover text
                duration_min = row["duration_sec"] / 60
                hover_text = (
                    f"<b>{hoist}</b><br>"
                    f"시간: {row['start_time'].strftime('%H:%M')} ~ {row['end_time'].strftime('%H:%M')}<br>"
                    f"소요: {duration_min:.1f}분<br>"
                    f"층: {row['start_floor']} → {row['end_floor']}<br>"
                    f"방향: {'상승' if direction == 'up' else '하강' if direction == 'down' else '왕복'}<br>"
                    f"<b>탑승: {pax}명</b>"
                )

                # Add bar
                fig.add_trace(
                    go.Bar(
                        x=[(row["end_time"] - row["start_time"]).total_seconds() / 60],
                        y=[short_name],
                        base=[row["start_time"]],
                        orientation="h",
                        marker_color=color,
                        marker_line_width=0,
                        hovertemplate=hover_text + "<extra></extra>",
                        showlegend=False,
                        text=str(pax) if pax > 0 else "",
                        textposition="inside",
                        textfont=dict(size=10, color="white"),
                    ),
                    row=idx, col=1
                )

    # Update layout
    height = max(400, 120 * n_buildings)
    fig.update_layout(
        title="운행 + 탑승인원 통합 뷰",
        height=height,
        showlegend=False,
        barmode="overlay",
    )

    fig.update_xaxes(title_text="시간", row=n_buildings, col=1)

    # Add legend manually
    for direction, color in DIRECTION_COLORS.items():
        label = {"up": "상승", "down": "하강", "round": "왕복"}.get(direction, direction)
        fig.add_trace(
            go.Scatter(
                x=[None], y=[None],
                mode="markers",
                marker=dict(size=10, color=color),
                name=label,
                showlegend=True
            )
        )

    return apply_dark_layout(fig)


def create_floor_heatmap(
    trips_df: pd.DataFrame,
    building: str
) -> go.Figure:
    """
    Create heatmap of floor activity over time (Dark Theme)

    Args:
        trips_df: DataFrame with trip data
        building: Building name

    Returns:
        Plotly figure
    """
    if len(trips_df) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    df = trips_df[trips_df["building_name"] == building].copy()

    if len(df) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    # Extract floor visits by hour
    data = []
    for _, row in df.iterrows():
        hour = row["start_time"].hour
        floors = row.get("floors_visited", [])
        if isinstance(floors, str):
            try:
                floors = ast.literal_eval(floors)
            except (ValueError, SyntaxError):
                floors = []
        for floor in floors:
            data.append({"hour": hour, "floor": floor})

    if not data:
        fig = go.Figure()
        return apply_dark_layout(fig)

    visit_df = pd.DataFrame(data)
    pivot = visit_df.groupby(["floor", "hour"]).size().unstack(fill_value=0)

    # Sort floors
    floor_order = sorted(
        pivot.index,
        key=lambda x: int(x.replace("F", "").replace("B", "-").replace("Roof", "100"))
    )
    pivot = pivot.reindex(floor_order)

    fig = px.imshow(
        pivot,
        labels=dict(x="시간", y="층", color="정차 횟수"),
        color_continuous_scale="Blues",
        aspect="auto"
    )

    fig.update_layout(
        title=f"{building} 층별 활동",
        height=350
    )

    return apply_dark_layout(fig)


def create_hourly_chart(
    hourly_df: pd.DataFrame,
    metric: str = "trip_count"
) -> go.Figure:
    """
    Create bar chart of hourly metrics (Dark Theme)

    Args:
        hourly_df: DataFrame with hourly data
        metric: Column to plot

    Returns:
        Plotly figure
    """
    if len(hourly_df) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    metric_labels = {
        "trip_count": "운행 횟수",
        "passenger_count": "탑승 인원"
    }

    fig = px.bar(
        hourly_df,
        x="hour",
        y=metric,
        color_discrete_sequence=[COLORS["primary"]]
    )

    fig.update_layout(
        title=f"시간대별 {metric_labels.get(metric, metric)}",
        xaxis_title="시간",
        yaxis_title=metric_labels.get(metric, metric),
        height=300,
        showlegend=False
    )

    fig.update_xaxes(tickmode="linear", dtick=1)

    return apply_dark_layout(fig)


def create_hourly_passenger_line(
    passengers_df: pd.DataFrame
) -> go.Figure:
    """
    Create line chart of hourly passenger count (Dark Theme)

    Args:
        passengers_df: DataFrame with passenger data

    Returns:
        Plotly figure
    """
    if len(passengers_df) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    df = passengers_df.copy()
    df["hour"] = df["boarding_time"].dt.hour

    hourly = df.groupby("hour").size().reset_index(name="count")

    if len(hourly) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    # Find peak
    peak_idx = hourly["count"].idxmax()
    peak_hour = hourly.loc[peak_idx, "hour"]
    peak_count = hourly.loc[peak_idx, "count"]

    fig = go.Figure()

    # Area fill
    fig.add_trace(
        go.Scatter(
            x=hourly["hour"],
            y=hourly["count"],
            mode="lines",
            fill="tozeroy",
            line=dict(color=COLORS["primary"], width=2),
            fillcolor=f"rgba(59, 130, 246, 0.2)",
            name="탑승인원"
        )
    )

    # Peak marker
    fig.add_trace(
        go.Scatter(
            x=[peak_hour],
            y=[peak_count],
            mode="markers+text",
            marker=dict(size=12, color=COLORS["warning"]),
            text=[f"피크: {peak_count}명"],
            textposition="top center",
            textfont=dict(color=COLORS["warning"], size=11),
            name="피크",
            showlegend=False
        )
    )

    fig.update_layout(
        title="시간대별 탑승인원",
        xaxis_title="시간",
        yaxis_title="탑승 인원",
        height=300,
        showlegend=False
    )

    fig.update_xaxes(tickmode="linear", dtick=1)

    return apply_dark_layout(fig)


def create_passenger_hourly_chart(
    passengers_df: pd.DataFrame
) -> go.Figure:
    """
    Create area chart of hourly passenger count by hoist (Dark Theme)

    Args:
        passengers_df: DataFrame with passenger data

    Returns:
        Plotly figure
    """
    if len(passengers_df) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    df = passengers_df.copy()
    df["hour"] = df["boarding_time"].dt.hour

    hourly = df.groupby(["hour", "hoist_name"]).size().reset_index(name="count")

    fig = px.area(
        hourly,
        x="hour",
        y="count",
        color="hoist_name",
        line_group="hoist_name"
    )

    fig.update_layout(
        title="호이스트별 시간대 탑승인원",
        xaxis_title="시간",
        yaxis_title="탑승 인원",
        height=350,
    )

    return apply_dark_layout(fig)


def create_company_distribution(
    passengers_df: pd.DataFrame
) -> go.Figure:
    """
    Create horizontal bar chart of passenger distribution by company (Dark Theme)

    Args:
        passengers_df: DataFrame with passenger data

    Returns:
        Plotly figure
    """
    if len(passengers_df) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    df = passengers_df.copy()
    df["company_name"] = df["company_name"].fillna("미상")

    company_counts = df["company_name"].value_counts().head(10)

    fig = go.Figure(
        go.Bar(
            x=company_counts.values,
            y=company_counts.index,
            orientation="h",
            marker_color=COLORS["primary"]
        )
    )

    fig.update_layout(
        title="업체별 탑승인원 (상위 10개)",
        xaxis_title="탑승 횟수",
        yaxis_title="업체",
        height=350,
        yaxis=dict(autorange="reversed")
    )

    return apply_dark_layout(fig)


def create_confidence_histogram(
    passengers_df: pd.DataFrame
) -> go.Figure:
    """
    Create histogram of classification confidence (Dark Theme)

    Args:
        passengers_df: DataFrame with passenger data

    Returns:
        Plotly figure
    """
    if len(passengers_df) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    fig = px.histogram(
        passengers_df,
        x="confidence",
        nbins=20,
        color_discrete_sequence=[COLORS["primary"]]
    )

    fig.update_layout(
        title="분류 신뢰도 분포",
        xaxis_title="신뢰도",
        yaxis_title="빈도",
        height=300
    )

    return apply_dark_layout(fig)


def create_sankey(
    trips_df: pd.DataFrame,
    building: str
) -> go.Figure:
    """
    Create Sankey diagram of floor-to-floor movement (Dark Theme)

    Args:
        trips_df: DataFrame with trip data
        building: Building name

    Returns:
        Plotly figure
    """
    if len(trips_df) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    df = trips_df[trips_df["building_name"] == building].copy()

    if len(df) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    # Build flow data
    flows = {}
    for _, row in df.iterrows():
        start = row["start_floor"]
        end = row["end_floor"]
        key = (start, end)
        flows[key] = flows.get(key, 0) + 1

    if not flows:
        fig = go.Figure()
        return apply_dark_layout(fig)

    # Get unique floors
    floors = list(set(
        [f for f, _ in flows.keys()] +
        [f for _, f in flows.keys()]
    ))
    floor_idx = {f: i for i, f in enumerate(floors)}

    # Build Sankey data
    source = [floor_idx[f] for f, _ in flows.keys()]
    target = [floor_idx[t] for _, t in flows.keys()]
    value = list(flows.values())

    color = BUILDING_COLORS.get(building, COLORS["primary"])

    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            line=dict(color="#2D3748", width=0.5),
            label=floors,
            color=color
        ),
        link=dict(
            source=source,
            target=target,
            value=value,
            color=f"rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, {int(color[5:7], 16)}, 0.4)"
        )
    )])

    fig.update_layout(
        title=f"{building} 층간 이동 흐름",
        height=400
    )

    return apply_dark_layout(fig)


def create_pressure_altitude_chart(
    sward_df: pd.DataFrame,
    hoist_name: str,
    mov_gw: int,
    fix_gw: int
) -> go.Figure:
    """
    Create dual-axis chart of pressure and estimated altitude (Dark Theme)

    Args:
        sward_df: S-Ward sensor data
        hoist_name: Hoist name
        mov_gw: Moving gateway number
        fix_gw: Fix gateway number

    Returns:
        Plotly figure
    """
    mov_df = sward_df[sward_df["gateway_no"] == mov_gw].copy()
    fix_df = sward_df[sward_df["gateway_no"] == fix_gw].copy()

    if len(mov_df) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Movement pressure
    fig.add_trace(
        go.Scatter(
            x=mov_df["insert_datetime"],
            y=mov_df["pressure"],
            name="호이스트 기압",
            line=dict(color=COLORS["primary"])
        ),
        secondary_y=False
    )

    # Fix reference pressure (sampled)
    if len(fix_df) > 0:
        fix_sampled = fix_df.iloc[::10]  # Sample for performance
        fig.add_trace(
            go.Scatter(
                x=fix_sampled["insert_datetime"],
                y=fix_sampled["pressure"],
                name="기준 기압",
                line=dict(color=COLORS["text_secondary"], dash="dot")
            ),
            secondary_y=False
        )

    # Is moving indicator
    fig.add_trace(
        go.Scatter(
            x=mov_df["insert_datetime"],
            y=mov_df["is_moving"] * 50,  # Scale for visibility
            name="이동 중",
            line=dict(color=COLORS["warning"]),
            fill="tozeroy",
            fillcolor="rgba(245, 158, 11, 0.2)"
        ),
        secondary_y=True
    )

    fig.update_layout(
        title=f"{hoist_name} 기압 프로파일",
        height=350
    )

    fig.update_xaxes(title_text="시간")
    fig.update_yaxes(title_text="기압 (hPa)", secondary_y=False)
    fig.update_yaxes(title_text="이동 상태", secondary_y=True)

    return apply_dark_layout(fig)


def create_elevator_shaft_timeline(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    hoist_filter: Optional[str] = None
) -> go.Figure:
    """
    Create Elevator Shaft Timeline visualization (Dark Theme)

    Shows hoist floor movement over time with passenger count as marker size/color.
    X-axis: Time (continuous)
    Y-axis: Floor
    Marker: Size proportional to passenger count, color by density

    Args:
        trips_df: DataFrame with trip data
        passengers_df: DataFrame with passenger classifications
        hoist_filter: Optional hoist name filter

    Returns:
        Plotly figure
    """
    if len(trips_df) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    df = trips_df.copy()
    if hoist_filter and hoist_filter != "전체":
        df = df[df["hoist_name"] == hoist_filter]

    if len(df) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    # Calculate passenger count per trip
    pax_counts = {}
    if len(passengers_df) > 0 and "trip_id" in passengers_df.columns:
        pax_counts = passengers_df.groupby("trip_id").size().to_dict()

    # Parse floor to numeric for Y-axis
    def floor_to_num(floor_str: str) -> float:
        if pd.isna(floor_str):
            return 0
        floor_str = str(floor_str).upper()
        if "ROOF" in floor_str:
            return 100
        if "B" in floor_str:
            try:
                return -int(floor_str.replace("B", "").replace("F", ""))
            except ValueError:
                return -1
        try:
            return int(floor_str.replace("F", ""))
        except ValueError:
            return 0

    fig = go.Figure()

    # Color map for hoists
    hoists = df["hoist_name"].unique()
    hoist_colors = {}
    base_colors = ["#3B82F6", "#22C55E", "#F59E0B", "#EF4444", "#A855F7", "#EC4899"]
    for i, h in enumerate(hoists):
        hoist_colors[h] = base_colors[i % len(base_colors)]

    # Build traces per hoist
    for hoist in hoists:
        hoist_df = df[df["hoist_name"] == hoist].sort_values("start_time")
        base_color = hoist_colors[hoist]

        # Create line trace for floor movement
        times = []
        floors = []
        hover_texts = []
        sizes = []
        colors = []

        for _, row in hoist_df.iterrows():
            trip_id = row["trip_id"]
            pax = pax_counts.get(trip_id, 0)

            start_floor = floor_to_num(row["start_floor"])
            end_floor = floor_to_num(row["end_floor"])

            # Start point
            times.append(row["start_time"])
            floors.append(start_floor)
            sizes.append(max(8, min(30, 8 + pax * 1.5)))
            colors.append(get_passenger_color(pax))

            hover_text = (
                f"<b>{hoist}</b><br>"
                f"시간: {row['start_time'].strftime('%H:%M:%S')}<br>"
                f"출발층: {row['start_floor']}<br>"
                f"<b>탑승: {pax}명</b>"
            )
            hover_texts.append(hover_text)

            # End point
            times.append(row["end_time"])
            floors.append(end_floor)
            sizes.append(max(8, min(30, 8 + pax * 1.5)))
            colors.append(get_passenger_color(pax))

            hover_text = (
                f"<b>{hoist}</b><br>"
                f"시간: {row['end_time'].strftime('%H:%M:%S')}<br>"
                f"도착층: {row['end_floor']}<br>"
                f"<b>탑승: {pax}명</b>"
            )
            hover_texts.append(hover_text)

            # Add None to break line between trips
            times.append(None)
            floors.append(None)
            sizes.append(0)
            colors.append(base_color)
            hover_texts.append("")

        # Line trace (continuous movement)
        fig.add_trace(
            go.Scatter(
                x=times,
                y=floors,
                mode="lines",
                line=dict(color=base_color, width=2),
                name=hoist.split("_")[-1],
                hoverinfo="skip",
                connectgaps=False
            )
        )

        # Marker trace (start/end points with passenger info)
        valid_idx = [i for i, t in enumerate(times) if t is not None]
        fig.add_trace(
            go.Scatter(
                x=[times[i] for i in valid_idx],
                y=[floors[i] for i in valid_idx],
                mode="markers",
                marker=dict(
                    size=[sizes[i] for i in valid_idx],
                    color=[colors[i] for i in valid_idx],
                    line=dict(width=1, color="white"),
                    opacity=0.8
                ),
                hovertext=[hover_texts[i] for i in valid_idx],
                hoverinfo="text",
                showlegend=False
            )
        )

    # Update layout
    fig.update_layout(
        title="엘리베이터 샤프트 타임라인 (층간 이동 + 탑승인원)",
        xaxis_title="시간",
        yaxis_title="층",
        height=450,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )

    # Y-axis floor labels
    all_floors = df[["start_floor", "end_floor"]].values.flatten()
    unique_floors = pd.Series(all_floors).dropna().unique()
    floor_nums = sorted([floor_to_num(f) for f in unique_floors])

    fig.update_yaxes(
        tickmode="array",
        tickvals=floor_nums,
        ticktext=[f"{int(f)}F" if f > 0 else ("B" + str(abs(int(f))) + "F" if f < 0 else "1F") for f in floor_nums]
    )

    return apply_dark_layout(fig)


def create_evidence_radar_chart(
    rssi_score: float,
    pressure_score: float,
    spatial_score: float,
    timing_score: float,
    composite_score: float
) -> go.Figure:
    """
    Create radar chart for multi-evidence scores (Dark Theme)

    Args:
        rssi_score: RSSI evidence score (0-1)
        pressure_score: Pressure correlation score (0-1)
        spatial_score: Spatial evidence score (0-1)
        timing_score: Timing evidence score (0-1)
        composite_score: Weighted composite score (0-1)

    Returns:
        Plotly figure
    """
    categories = ["RSSI", "기압", "공간", "타이밍"]
    scores = [rssi_score, pressure_score, spatial_score, timing_score]

    fig = go.Figure()

    # Add radar trace
    fig.add_trace(go.Scatterpolar(
        r=scores + [scores[0]],  # Close the polygon
        theta=categories + [categories[0]],
        fill="toself",
        fillcolor="rgba(59, 130, 246, 0.3)",
        line=dict(color=COLORS["primary"], width=2),
        name="증거 점수"
    ))

    # Classification color based on composite
    if composite_score >= 0.6:
        center_color = "#22C55E"
        classification = "확정"
    elif composite_score >= 0.4:
        center_color = "#F59E0B"
        classification = "추정"
    else:
        center_color = "#64748B"
        classification = "미분류"

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 1],
                tickvals=[0.2, 0.4, 0.6, 0.8, 1.0],
                tickfont=dict(size=10, color="#64748B"),
                gridcolor="#2D3748"
            ),
            angularaxis=dict(
                tickfont=dict(size=12, color="#FAFAFA"),
                gridcolor="#2D3748"
            ),
            bgcolor="#1E2330"
        ),
        title=f"Multi-Evidence 분석 (종합: {composite_score*100:.0f}% - {classification})",
        height=350,
        showlegend=False,
        paper_bgcolor="#0E1117",
        font=dict(color="#FAFAFA")
    )

    return fig


def create_evidence_distribution_chart(
    passengers_df: pd.DataFrame
) -> go.Figure:
    """
    Create stacked bar chart showing evidence score distribution (Dark Theme)

    Args:
        passengers_df: DataFrame with multi-evidence columns

    Returns:
        Plotly figure
    """
    if len(passengers_df) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    # Check for multi-evidence columns
    evidence_cols = ["rssi_score", "pressure_score", "spatial_score", "timing_score"]
    available_cols = [c for c in evidence_cols if c in passengers_df.columns]

    if not available_cols:
        fig = go.Figure()
        fig.add_annotation(
            text="Multi-Evidence 데이터 없음",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(color="#64748B", size=14)
        )
        return apply_dark_layout(fig)

    # Group by classification
    if "classification" in passengers_df.columns:
        groups = passengers_df.groupby("classification")[available_cols].mean()
    else:
        groups = pd.DataFrame({
            "전체": passengers_df[available_cols].mean()
        }).T

    fig = go.Figure()

    colors = {
        "rssi_score": "#3B82F6",
        "pressure_score": "#22C55E",
        "spatial_score": "#F59E0B",
        "timing_score": "#A855F7"
    }
    labels = {
        "rssi_score": "RSSI",
        "pressure_score": "기압",
        "spatial_score": "공간",
        "timing_score": "타이밍"
    }

    for col in available_cols:
        fig.add_trace(go.Bar(
            x=groups.index,
            y=groups[col],
            name=labels.get(col, col),
            marker_color=colors.get(col, COLORS["primary"])
        ))

    fig.update_layout(
        title="분류별 증거 점수 평균",
        xaxis_title="분류",
        yaxis_title="평균 점수",
        barmode="group",
        height=350
    )

    return apply_dark_layout(fig)


def create_composite_score_histogram(
    passengers_df: pd.DataFrame
) -> go.Figure:
    """
    Create histogram of composite scores with classification thresholds (Dark Theme)

    Args:
        passengers_df: DataFrame with composite_score column

    Returns:
        Plotly figure
    """
    if len(passengers_df) == 0 or "composite_score" not in passengers_df.columns:
        fig = go.Figure()
        return apply_dark_layout(fig)

    fig = go.Figure()

    # Histogram
    fig.add_trace(go.Histogram(
        x=passengers_df["composite_score"],
        nbinsx=20,
        marker_color=COLORS["primary"],
        opacity=0.7,
        name="분포"
    ))

    # Threshold lines
    fig.add_vline(x=0.6, line_dash="dash", line_color="#22C55E",
                  annotation_text="확정 (0.6)", annotation_position="top")
    fig.add_vline(x=0.4, line_dash="dash", line_color="#F59E0B",
                  annotation_text="추정 (0.4)", annotation_position="top")

    fig.update_layout(
        title="종합 점수 분포 (Multi-Evidence)",
        xaxis_title="종합 점수",
        yaxis_title="빈도",
        height=300
    )

    return apply_dark_layout(fig)


def create_building_comparison_chart(
    summary: Dict[str, Dict]
) -> go.Figure:
    """
    Create bar chart comparing buildings (Dark Theme)

    Args:
        summary: Building summary dict

    Returns:
        Plotly figure
    """
    if not summary:
        fig = go.Figure()
        return apply_dark_layout(fig)

    buildings = list(summary.keys())
    trip_counts = [summary[b].get("trip_count", 0) for b in buildings]
    pax_counts = [summary[b].get("passenger_count", 0) for b in buildings]

    fig = go.Figure(data=[
        go.Bar(
            name="운행 횟수",
            x=buildings,
            y=trip_counts,
            marker_color=[BUILDING_COLORS.get(b, COLORS["primary"]) for b in buildings]
        ),
        go.Bar(
            name="탑승 인원",
            x=buildings,
            y=pax_counts,
            marker_color=[_hex_to_rgba(BUILDING_COLORS.get(b, COLORS["primary"]), 0.5) for b in buildings]
        )
    ])

    fig.update_layout(
        title="건물별 비교",
        barmode="group",
        height=300
    )

    return apply_dark_layout(fig)


# ============================================================
# Congestion Charts (v4.0)
# ============================================================

def create_congestion_heatmap(
    hoist_hourly_ci: Dict[str, Dict[int, Dict]],
    hoist_names: List[str] = None,
    interval_min: int = 10,
) -> go.Figure:
    """
    Create congestion heatmap by hoist and time bin (Dark Theme)

    Args:
        hoist_hourly_ci: {hoist: {time_bin_min: {ci, trips, passengers, max_pax}}}
        hoist_names: Optional ordered list of hoist names
        interval_min: Time bin interval in minutes (default 10)

    Returns:
        Plotly figure
    """
    if not hoist_hourly_ci:
        fig = go.Figure()
        fig.add_annotation(
            text="데이터 없음",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(color="#64748B", size=14)
        )
        return apply_dark_layout(fig)

    if hoist_names is None:
        hoist_names = sorted(hoist_hourly_ci.keys())

    # Time bins from 06:00 to 22:50 (10-min intervals)
    time_bins = list(range(6 * 60, 23 * 60, interval_min))
    x_labels = [f"{m // 60:02d}:{m % 60:02d}" for m in time_bins]

    z_data = []
    hover_texts = []

    for hoist in hoist_names:
        row = []
        hover_row = []
        bins = hoist_hourly_ci.get(hoist, {})

        for tbin in time_bins:
            data = bins.get(tbin, {"ci": 0, "trips": 0, "passengers": 0, "max_pax": 0})
            max_pax = data.get("max_pax", 0)
            row.append(max_pax)  # Use max passengers instead of CI
            end_min = tbin + interval_min
            avg_pax = data["passengers"] / data["trips"] if data["trips"] > 0 else 0
            hover_row.append(
                f"<b>{hoist}</b><br>"
                f"시간: {tbin//60:02d}:{tbin%60:02d}~{end_min//60:02d}:{end_min%60:02d}<br>"
                f"<b>최대 탑승: {max_pax}명</b><br>"
                f"평균 탑승: {avg_pax:.1f}명<br>"
                f"운행: {data['trips']}회<br>"
                f"총 탑승: {data['passengers']}명"
            )

        z_data.append(row)
        hover_texts.append(hover_row)

    # Readable labels
    def _readable_name(h):
        parts = h.split("_")
        if len(parts) >= 2:
            bld = parts[0]
            kind = parts[1]
            num = parts[2] if len(parts) > 2 else "1"
            if kind == "Climber":
                return f"{bld} CL{num}"
            return f"{bld} {num}호기"
        return h

    y_labels = [_readable_name(h) for h in hoist_names]

    # Dynamic zmax based on actual data
    all_vals = [v for row in z_data for v in row if v > 0]
    zmax = max(all_vals) if all_vals else 20

    fig = go.Figure(data=go.Heatmap(
        z=z_data,
        x=x_labels,
        y=y_labels,
        colorscale=[
            [0.0, "#1E293B"],     # 0명 — 거의 안보임 (배경과 유사)
            [0.05, "#1E3A5F"],    # 1명 — 어두운 파랑
            [0.2, "#22C55E"],     # ~5명 — 초록
            [0.4, "#FBBF24"],     # ~10명 — 노랑
            [0.7, "#F97316"],     # ~17명 — 주황
            [1.0, "#EF4444"],     # 25명+ — 빨강
        ],
        zmin=0,
        zmax=max(25, zmax),
        hovertext=hover_texts,
        hoverinfo="text",
        colorbar=dict(
            title="최대<br>탑승",
            ticksuffix="명",
        )
    ))

    fig.update_layout(
        title=f"호이스트별 시간대 최대 탑승인원 ({interval_min}분 단위)",
        xaxis_title="시간",
        yaxis_title="",
        height=max(400, 45 * len(hoist_names) + 120),
        xaxis=dict(dtick=3),  # Show every 30min (3 × 10min)
    )

    return apply_dark_layout(fig)


def create_peak_comparison_chart(peak_analysis: Dict[str, Dict]) -> go.Figure:
    """
    Create peak time comparison grouped bar chart (Dark Theme)

    Args:
        peak_analysis: {morning/lunch/evening: {trips, passengers, ci, hours}}

    Returns:
        Plotly figure
    """
    if not peak_analysis:
        fig = go.Figure()
        return apply_dark_layout(fig)

    labels = {
        "morning": "출근",
        "lunch": "점심",
        "evening": "퇴근"
    }

    peaks = ["morning", "lunch", "evening"]
    x_labels = []
    for p in peaks:
        hours = peak_analysis.get(p, {}).get("hours", "")
        x_labels.append(f"{labels[p]}<br>({hours})")

    fig = go.Figure()

    # Trip count
    fig.add_trace(go.Bar(
        name="운행 횟수",
        x=x_labels,
        y=[peak_analysis.get(p, {}).get("trips", 0) for p in peaks],
        marker_color="#3B82F6"
    ))

    # Passenger count
    fig.add_trace(go.Bar(
        name="탑승 인원",
        x=x_labels,
        y=[peak_analysis.get(p, {}).get("passengers", 0) for p in peaks],
        marker_color="#22C55E"
    ))

    fig.update_layout(
        title="피크 시간대 비교",
        barmode="group",
        xaxis_title="피크 시간대",
        yaxis_title="횟수/인원",
        height=350
    )

    return apply_dark_layout(fig)


# ============================================================
# Wait Time Charts (v4.0)
# ============================================================

def create_wait_time_line_chart(hourly_wait: Dict[int, Dict]) -> go.Figure:
    """
    Create hourly wait time line chart (Dark Theme)

    Args:
        hourly_wait: {hour: {avg_wait, max_wait, count}}

    Returns:
        Plotly figure
    """
    if not hourly_wait:
        fig = go.Figure()
        fig.add_annotation(
            text="대기시간 데이터 없음",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(color="#64748B", size=14)
        )
        return apply_dark_layout(fig)

    hours = sorted(hourly_wait.keys())
    avg_waits = [hourly_wait[h]["avg_wait"] for h in hours]
    max_waits = [hourly_wait[h]["max_wait"] for h in hours]

    fig = go.Figure()

    # Average wait time (area)
    fig.add_trace(go.Scatter(
        x=[f"{h:02d}:00" for h in hours],
        y=avg_waits,
        mode="lines",
        fill="tozeroy",
        line=dict(color="#3B82F6", width=2),
        fillcolor="rgba(59, 130, 246, 0.2)",
        name="평균 대기시간"
    ))

    # Max wait time (markers)
    fig.add_trace(go.Scatter(
        x=[f"{h:02d}:00" for h in hours],
        y=max_waits,
        mode="markers",
        marker=dict(size=8, color="#EF4444", symbol="diamond"),
        name="최대 대기시간"
    ))

    # Peak time highlights
    all_hours_str = [f"{h:02d}:00" for h in range(6, 23)]
    if "06:00" in [f"{h:02d}:00" for h in hours] or "07:00" in [f"{h:02d}:00" for h in hours]:
        fig.add_vrect(x0="06:00", x1="08:00", fillcolor="rgba(245,158,11,0.1)",
                      line_width=0, annotation_text="출근", annotation_position="top left")
    if "12:00" in [f"{h:02d}:00" for h in hours]:
        fig.add_vrect(x0="12:00", x1="13:00", fillcolor="rgba(245,158,11,0.1)",
                      line_width=0, annotation_text="점심", annotation_position="top left")
    if "17:00" in [f"{h:02d}:00" for h in hours] or "18:00" in [f"{h:02d}:00" for h in hours]:
        fig.add_vrect(x0="17:00", x1="19:00", fillcolor="rgba(245,158,11,0.1)",
                      line_width=0, annotation_text="퇴근", annotation_position="top left")

    fig.update_layout(
        title="시간대별 대기시간",
        xaxis_title="시간",
        yaxis_title="대기시간 (초)",
        height=350
    )

    return apply_dark_layout(fig)


def create_wait_time_comparison_chart(hoist_wait: Dict[str, Dict]) -> go.Figure:
    """
    Create hoist wait time comparison bar chart (Dark Theme)

    Args:
        hoist_wait: {hoist: {avg_wait, max_wait, total_man_min}}

    Returns:
        Plotly figure
    """
    if not hoist_wait:
        fig = go.Figure()
        fig.add_annotation(
            text="대기시간 데이터 없음",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(color="#64748B", size=14)
        )
        return apply_dark_layout(fig)

    hoists = sorted(hoist_wait.keys())
    short_names = [h.split("_")[-1] if "_" in h else h for h in hoists]

    fig = go.Figure()

    # Average wait time (bars)
    fig.add_trace(go.Bar(
        x=short_names,
        y=[hoist_wait[h]["avg_wait"] for h in hoists],
        name="평균 대기시간",
        marker_color="#3B82F6"
    ))

    # Max wait time (markers)
    fig.add_trace(go.Scatter(
        x=short_names,
        y=[hoist_wait[h]["max_wait"] for h in hoists],
        mode="markers",
        marker=dict(size=12, color="#EF4444", symbol="diamond"),
        name="최대 대기시간"
    ))

    fig.update_layout(
        title="호이스트별 대기시간 비교",
        xaxis_title="호이스트",
        yaxis_title="대기시간 (초)",
        height=350
    )

    return apply_dark_layout(fig)


# ============================================================
# Congestion Bar Chart — 10-min interval max passengers
# ============================================================

def create_congestion_bar_chart(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    hoist_filter: Optional[str] = None,
    interval_min: int = 10,
) -> go.Figure:
    """
    10분 단위 시간대별 호이스트 최대 탑승인원 막대 그래프

    Args:
        trips_df: Trip data
        passengers_df: Passenger data
        hoist_filter: Optional single hoist name (None = all)
        interval_min: Time bin size in minutes (default 10)

    Returns:
        Plotly figure
    """
    fig = go.Figure()

    if len(trips_df) == 0 or len(passengers_df) == 0:
        return apply_dark_layout(fig)

    # Count passengers per trip
    pax_count = passengers_df.groupby("trip_id").size().reset_index(name="pax_count")
    merged = trips_df.merge(pax_count, on="trip_id", how="left")
    merged["pax_count"] = merged["pax_count"].fillna(0).astype(int)

    if hoist_filter:
        merged = merged[merged["hoist_name"] == hoist_filter]

    if len(merged) == 0:
        return apply_dark_layout(fig)

    # Create time bins
    merged["time_bin"] = (
        merged["start_time"].dt.hour * 60 + merged["start_time"].dt.minute
    ) // interval_min * interval_min

    stats = merged.groupby("time_bin").agg(
        max_pax=("pax_count", "max"),
        avg_pax=("pax_count", "mean"),
        trip_count=("trip_id", "count"),
    ).reset_index()

    stats["time_label"] = stats["time_bin"].apply(
        lambda m: f"{m // 60:02d}:{m % 60:02d}"
    )

    def _bar_color(v):
        if v >= 20:
            return COLORS["danger"]
        elif v >= 10:
            return COLORS["warning"]
        elif v >= 5:
            return COLORS["primary"]
        return COLORS["secondary"]

    bar_colors = [_bar_color(v) for v in stats["max_pax"]]

    fig.add_trace(go.Bar(
        x=stats["time_label"],
        y=stats["max_pax"],
        name="최대 탑승인원",
        marker_color=bar_colors,
        text=stats["max_pax"],
        textposition="outside",
        textfont=dict(size=9),
        hovertemplate=(
            "<b>%{x}</b><br>"
            "최대: %{y}명<br>"
            "평균: %{customdata[0]:.1f}명<br>"
            "운행: %{customdata[1]}회"
            "<extra></extra>"
        ),
        customdata=list(zip(stats["avg_pax"], stats["trip_count"])),
    ))

    fig.add_trace(go.Scatter(
        x=stats["time_label"],
        y=stats["avg_pax"],
        name="평균 탑승인원",
        mode="lines+markers",
        line=dict(color=COLORS["info"], width=2, dash="dot"),
        marker=dict(size=4),
    ))

    fig.add_hline(
        y=20, line_dash="dash", line_color=COLORS["danger"],
        annotation_text="혼잡 기준 (20명)", annotation_position="top right",
        annotation_font_color=COLORS["danger"],
    )

    fig = apply_dark_layout(fig)
    fig.update_layout(
        title=f"시간대별 최대 탑승인원 ({interval_min}분 단위)",
        xaxis_title="시간",
        yaxis_title="탑승인원 (명)",
        height=400,
        bargap=0.15,
        legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
        xaxis=dict(dtick=3),
    )

    return fig


# ============================================================
# Dual Operation Chart — Synchronized Passenger + Floor Movement
# ============================================================

def create_dual_operation_chart(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    hoist_filter: Optional[str] = None,
    time_range: Optional[tuple] = None,
) -> go.Figure:
    """
    Create dual synchronized chart:
    - Top: Passenger count per trip over time (bar chart with congestion coloring)
    - Bottom: Hoist floor movement over time (line chart)

    Both charts share the same x-axis (time) for synchronized viewing.

    Args:
        trips_df: Trip data with start_time, end_time, start_floor, end_floor
        passengers_df: Passenger classifications with trip_id
        hoist_filter: Optional single hoist to highlight (None = all hoists)
        time_range: Optional (start_hour, end_hour) tuple to filter

    Returns:
        Plotly figure with 2 synchronized subplots
    """
    if len(trips_df) == 0:
        fig = go.Figure()
        fig.add_annotation(
            text="운행 데이터 없음",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(color="#64748B", size=14)
        )
        return apply_dark_layout(fig)

    df = trips_df.copy()

    # Apply time filter if provided
    if time_range:
        df = df[
            (df["start_time"].dt.hour >= time_range[0]) &
            (df["start_time"].dt.hour < time_range[1])
        ]

    if len(df) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    # Count passengers per trip
    pax_counts = {}
    if len(passengers_df) > 0 and "trip_id" in passengers_df.columns:
        pax_counts = passengers_df.groupby("trip_id").size().to_dict()

    df["pax_count"] = df["trip_id"].map(lambda x: pax_counts.get(x, 0))

    # Parse floor to numeric
    def floor_to_num(floor_str: str) -> float:
        if pd.isna(floor_str):
            return 0
        floor_str = str(floor_str).upper()
        if "ROOF" in floor_str:
            return 100
        if "B" in floor_str:
            try:
                return -int(floor_str.replace("B", "").replace("F", ""))
            except ValueError:
                return -1
        try:
            return int(floor_str.replace("F", ""))
        except ValueError:
            return 0

    # Create subplot with shared x-axis
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.4, 0.6],
        subplot_titles=["탑승인원 (시간순)", "층간 이동 (호이스트별)"]
    )

    # ========== TOP CHART: Passenger Count ==========
    df_sorted = df.sort_values("start_time")

    # Bright colors for dark background
    def get_congestion_color(pax: int) -> str:
        if pax >= 20:
            return "#FF6B6B"   # Bright red
        elif pax >= 10:
            return "#FFB347"   # Bright orange
        elif pax >= 5:
            return "#60A5FA"   # Bright blue
        elif pax > 0:
            return "#4ADE80"   # Bright green (visible on dark bg)
        else:
            return "#475569"   # Slate — no passengers

    bar_colors = [get_congestion_color(p) for p in df_sorted["pax_count"]]

    hover_texts = []
    for _, row in df_sorted.iterrows():
        pax = row["pax_count"]
        hover_texts.append(
            f"<b>{row['hoist_name']}</b><br>"
            f"시간: {row['start_time'].strftime('%H:%M:%S')}<br>"
            f"층: {row['start_floor']} → {row['end_floor']}<br>"
            f"<b>탑승: {pax}명</b>"
        )

    fig.add_trace(
        go.Bar(
            x=df_sorted["start_time"],
            y=df_sorted["pax_count"],
            marker_color=bar_colors,
            marker_line_width=0,
            text=df_sorted["pax_count"].apply(lambda x: str(x) if x >= 5 else ""),
            textposition="outside",
            textfont=dict(size=9, color="#E2E8F0"),
            hovertext=hover_texts,
            hoverinfo="text",
            name="탑승인원",
            showlegend=False,
        ),
        row=1, col=1
    )

    # Threshold lines with bright colors
    fig.add_hline(
        y=20, line_dash="dash", line_color="#FF6B6B",
        line_width=1, row=1, col=1,
        annotation_text="20명", annotation_position="right",
        annotation_font_color="#FF6B6B",
    )
    fig.add_hline(
        y=10, line_dash="dot", line_color="#FFB347",
        line_width=1, row=1, col=1,
        annotation_text="10명", annotation_position="right",
        annotation_font_color="#FFB347",
    )

    # ========== BOTTOM CHART: Floor Movement ==========
    hoists = sorted(df["hoist_name"].unique())
    # Bright, high-contrast colors for dark background
    bright_colors = [
        "#60A5FA",  # Blue
        "#4ADE80",  # Green
        "#FBBF24",  # Amber
        "#FB7185",  # Rose
        "#C084FC",  # Purple
        "#38BDF8",  # Sky
        "#F97316",  # Orange
        "#A3E635",  # Lime
        "#F43F5E",  # Crimson
    ]
    hoist_colors = {h: bright_colors[i % len(bright_colors)] for i, h in enumerate(hoists)}

    for hoist in hoists:
        hoist_df = df[df["hoist_name"] == hoist].sort_values("start_time")

        # Determine line style
        if hoist_filter:
            line_width = 3 if hoist == hoist_filter else 1
            opacity = 1.0 if hoist == hoist_filter else 0.3
        else:
            line_width = 2
            opacity = 0.8

        times = []
        floors = []
        hover_floor = []

        for _, row in hoist_df.iterrows():
            pax = row["pax_count"]
            start_floor_num = floor_to_num(row["start_floor"])
            end_floor_num = floor_to_num(row["end_floor"])

            # Start point
            times.append(row["start_time"])
            floors.append(start_floor_num)
            hover_floor.append(
                f"<b>{hoist}</b><br>"
                f"시간: {row['start_time'].strftime('%H:%M:%S')}<br>"
                f"층: {row['start_floor']}<br>"
                f"탑승: {pax}명"
            )

            # End point
            times.append(row["end_time"])
            floors.append(end_floor_num)
            hover_floor.append(
                f"<b>{hoist}</b><br>"
                f"시간: {row['end_time'].strftime('%H:%M:%S')}<br>"
                f"층: {row['end_floor']}<br>"
                f"탑승: {pax}명"
            )

            # Gap between trips
            times.append(None)
            floors.append(None)
            hover_floor.append("")

        # Readable legend name
        parts = hoist.split("_")
        if len(parts) >= 3:
            legend_name = f"{parts[0]} {parts[2]}호기" if parts[1] != "Climber" else f"{parts[0]} CL{parts[2]}"
        elif len(parts) == 2:
            legend_name = f"{parts[0]} {parts[1]}"
        else:
            legend_name = hoist

        fig.add_trace(
            go.Scatter(
                x=times,
                y=floors,
                mode="lines+markers",
                line=dict(color=hoist_colors[hoist], width=line_width),
                marker=dict(size=4, color=hoist_colors[hoist], opacity=opacity),
                name=legend_name,
                hovertext=hover_floor,
                hoverinfo="text",
                connectgaps=False,
                opacity=opacity,
            ),
            row=2, col=1
        )

    # Y-axis floor labels for bottom chart
    all_floors = df[["start_floor", "end_floor"]].values.flatten()
    unique_floors = pd.Series(all_floors).dropna().unique()
    floor_nums = sorted([floor_to_num(f) for f in unique_floors])

    # Create floor labels
    floor_labels = []
    for f in floor_nums:
        if f == 100:
            floor_labels.append("Roof")
        elif f < 0:
            floor_labels.append(f"B{abs(int(f))}F")
        else:
            floor_labels.append(f"{int(f)}F")

    # Update layout — optimized for dark background
    fig.update_layout(
        height=700,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            font=dict(color="#E2E8F0", size=11),
        ),
    )

    # Subplot titles color
    for annotation in fig.layout.annotations:
        annotation.font.color = "#E2E8F0"
        annotation.font.size = 13

    # Axes styling
    fig.update_xaxes(
        title_text="시간", row=2, col=1,
        gridcolor="#1E293B", title_font_color="#94A3B8",
    )
    fig.update_yaxes(
        title_text="탑승인원 (명)", row=1, col=1,
        gridcolor="#1E293B", title_font_color="#94A3B8",
    )
    fig.update_yaxes(
        title_text="층",
        tickmode="array",
        tickvals=floor_nums,
        ticktext=floor_labels,
        gridcolor="#1E293B",
        title_font_color="#94A3B8",
        row=2, col=1
    )

    return apply_dark_layout(fig)


# ============================================================
# Hoist Comparison Table Data
# ============================================================

def create_hoist_comparison_chart(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
    hoist_info: Dict,
) -> go.Figure:
    """
    Create horizontal bar chart comparing all hoists by key metrics.

    Args:
        trips_df: Trip data
        passengers_df: Passenger data
        hoist_info: Hoist configuration dict

    Returns:
        Plotly figure with grouped bars
    """
    if len(trips_df) == 0:
        fig = go.Figure()
        fig.add_annotation(
            text="운행 데이터 없음",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(color="#64748B", size=14)
        )
        return apply_dark_layout(fig)

    # Calculate metrics per hoist
    hoists = sorted(trips_df["hoist_name"].unique())

    # Passenger counts per trip
    pax_counts = {}
    if len(passengers_df) > 0 and "trip_id" in passengers_df.columns:
        pax_counts = passengers_df.groupby("trip_id").size().to_dict()

    data = []
    for hoist in hoists:
        hoist_trips = trips_df[trips_df["hoist_name"] == hoist]
        hoist_pax_counts = [pax_counts.get(tid, 0) for tid in hoist_trips["trip_id"]]

        trip_count = len(hoist_trips)
        total_pax = sum(hoist_pax_counts)
        avg_pax = np.mean(hoist_pax_counts) if hoist_pax_counts else 0
        max_pax = max(hoist_pax_counts) if hoist_pax_counts else 0

        # Calculate utilization
        if trip_count > 0:
            operating_sec = hoist_trips["duration_sec"].sum()
            start_time = hoist_trips["start_time"].min()
            end_time = hoist_trips["end_time"].max()
            span_sec = (end_time - start_time).total_seconds()
            utilization = (operating_sec / span_sec * 100) if span_sec > 0 else 0
        else:
            utilization = 0

        building = hoist_trips["building_name"].iloc[0] if len(hoist_trips) > 0 else ""
        short_name = hoist.split("_")[-1] if "_" in hoist else hoist

        data.append({
            "hoist": hoist,
            "short_name": short_name,
            "building": building,
            "trip_count": trip_count,
            "total_pax": total_pax,
            "avg_pax": avg_pax,
            "max_pax": max_pax,
            "utilization": utilization,
        })

    df = pd.DataFrame(data)
    df = df.sort_values(["building", "short_name"])

    # Create grouped bar chart
    fig = make_subplots(
        rows=1, cols=3,
        subplot_titles=["운행 횟수", "총 탑승인원", "가동률 (%)"],
        horizontal_spacing=0.12
    )

    # Get building colors
    bar_colors = [BUILDING_COLORS.get(b, COLORS["primary"]) for b in df["building"]]

    # Trip count
    fig.add_trace(
        go.Bar(
            y=df["short_name"],
            x=df["trip_count"],
            orientation="h",
            marker_color=bar_colors,
            text=df["trip_count"],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>운행: %{x}회<extra></extra>",
            showlegend=False,
        ),
        row=1, col=1
    )

    # Total passengers
    fig.add_trace(
        go.Bar(
            y=df["short_name"],
            x=df["total_pax"],
            orientation="h",
            marker_color=bar_colors,
            text=df["total_pax"],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>탑승: %{x}명<extra></extra>",
            showlegend=False,
        ),
        row=1, col=2
    )

    # Utilization
    fig.add_trace(
        go.Bar(
            y=df["short_name"],
            x=df["utilization"],
            orientation="h",
            marker_color=bar_colors,
            text=[f"{u:.1f}%" for u in df["utilization"]],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>가동률: %{x:.1f}%<extra></extra>",
            showlegend=False,
        ),
        row=1, col=3
    )

    # Add building legend manually
    for building, color in BUILDING_COLORS.items():
        fig.add_trace(
            go.Scatter(
                x=[None], y=[None],
                mode="markers",
                marker=dict(size=10, color=color),
                name=building,
                showlegend=True
            )
        )

    fig.update_layout(
        title="호이스트 비교 분석",
        height=max(300, 40 * len(df) + 100),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.08,
            xanchor="center",
            x=0.5
        ),
    )

    fig.update_yaxes(autorange="reversed")

    return apply_dark_layout(fig)


def create_peak_period_comparison_chart(
    trips_df: pd.DataFrame,
    passengers_df: pd.DataFrame,
) -> go.Figure:
    """
    Create chart comparing hoists across different peak periods.

    Peak periods:
    - Morning commute: 06:00-08:00
    - AM work: 09:00-11:00
    - Lunch: 12:00-13:00
    - PM work: 14:00-17:00
    - Evening commute: 18:00-20:00

    Args:
        trips_df: Trip data
        passengers_df: Passenger data

    Returns:
        Plotly heatmap figure
    """
    if len(trips_df) == 0:
        fig = go.Figure()
        fig.add_annotation(
            text="운행 데이터 없음",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(color="#64748B", size=14)
        )
        return apply_dark_layout(fig)

    PEAK_PERIODS = {
        "출근 (06-08)": (6, 8),
        "오전 (09-11)": (9, 11),
        "점심 (12-13)": (12, 13),
        "오후 (14-17)": (14, 17),
        "퇴근 (18-20)": (18, 20),
    }

    # Passenger counts per trip
    pax_counts = {}
    if len(passengers_df) > 0 and "trip_id" in passengers_df.columns:
        pax_counts = passengers_df.groupby("trip_id").size().to_dict()

    trips = trips_df.copy()
    trips["hour"] = trips["start_time"].dt.hour
    trips["pax_count"] = trips["trip_id"].map(lambda x: pax_counts.get(x, 0))

    hoists = sorted(trips["hoist_name"].unique())

    # Build data matrix
    z_data = []
    hover_texts = []

    for hoist in hoists:
        hoist_data = trips[trips["hoist_name"] == hoist]
        row = []
        hover_row = []

        for period_name, (start_h, end_h) in PEAK_PERIODS.items():
            period_trips = hoist_data[
                (hoist_data["hour"] >= start_h) & (hoist_data["hour"] < end_h)
            ]

            if len(period_trips) > 0:
                avg_pax = period_trips["pax_count"].mean()
                total_trips = len(period_trips)
                total_pax = period_trips["pax_count"].sum()
            else:
                avg_pax = 0
                total_trips = 0
                total_pax = 0

            row.append(avg_pax)
            hover_row.append(
                f"<b>{hoist}</b><br>"
                f"시간대: {period_name}<br>"
                f"운행: {total_trips}회<br>"
                f"총 탑승: {total_pax}명<br>"
                f"평균: {avg_pax:.1f}명"
            )

        z_data.append(row)
        hover_texts.append(hover_row)

    # Readable labels
    def _readable_name(h):
        parts = h.split("_")
        if len(parts) >= 2:
            bld = parts[0]
            kind = parts[1]
            num = parts[2] if len(parts) > 2 else "1"
            if kind == "Climber":
                return f"{bld} 클라이머{num}"
            return f"{bld} {num}호기"
        return h

    y_labels = [_readable_name(h) for h in hoists]

    fig = go.Figure(data=go.Heatmap(
        z=z_data,
        x=list(PEAK_PERIODS.keys()),
        y=y_labels,
        colorscale="RdYlGn_r",
        zmin=0,
        zmax=max(15, max([max(row) for row in z_data]) if z_data else 15),
        hovertext=hover_texts,
        hoverinfo="text",
        colorbar=dict(
            title="평균<br>탑승인원",
            ticksuffix="명"
        )
    ))

    fig.update_layout(
        title="시간대별 호이스트 혼잡도 비교",
        xaxis_title="시간대",
        yaxis_title="",
        height=max(350, 40 * len(hoists) + 100),
    )

    return apply_dark_layout(fig)
