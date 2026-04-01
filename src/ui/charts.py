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
from ..utils.converters import format_hoist_name


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
                short_name = format_hoist_name(hoist)

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

    fig.update_xaxes(tickmode="linear", dtick=1, range=[-0.5, 23.5])

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

    fig.update_xaxes(tickmode="linear", dtick=1, range=[-0.5, 23.5])

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
        xaxis=dict(tickmode="linear", dtick=1, range=[-0.5, 23.5]),
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
                name=format_hoist_name(hoist),
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
    Create radar chart for v4.5 Rate-Matching scores (Dark Theme).

    Note: In v4.5, spatial_score and timing_score are always 0.0 (legacy compat).
    pressure_score maps to rate_match_score. RSSI is for candidate selection only.

    Args:
        rssi_score: Legacy RSSI score (0-1) — kept for backward compatibility
        pressure_score: Rate-match score (= rate_match_score in v4.5)
        spatial_score: Always 0.0 in v4.5 (not used)
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
        title=f"v4.5 Rate-Matching 분석 (종합: {composite_score*100:.0f}% - {classification})",
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
    Create stacked bar chart showing evidence score distribution (Dark Theme).

    In v4.5, rate_match_score replaces pressure_score as the primary metric.
    spatial_score and timing_score are always 0.0 (legacy compatibility).

    Args:
        passengers_df: DataFrame with v4.5 rate-matching or legacy columns

    Returns:
        Plotly figure
    """
    if len(passengers_df) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    # Check for evidence columns (v4.5 uses rate_match_score; legacy uses rssi/pressure/spatial/timing)
    evidence_cols = ["rssi_score", "pressure_score", "spatial_score", "timing_score"]
    available_cols = [c for c in evidence_cols if c in passengers_df.columns]

    if not available_cols:
        fig = go.Figure()
        fig.add_annotation(
            text="Rate-Matching 데이터 없음",
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
        title="종합 점수 분포 (v4.5 Rate-Matching)",
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

    # Time bins from 00:00 to 23:50 (10-min intervals, 24시간 현장)
    time_bins = list(range(0, 24 * 60, interval_min))
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
            # Exclude empty runs for avg (trips_with_pax)
            trips_with_pax = data.get("trips_with_pax", data["trips"])
            avg_pax = data["passengers"] / trips_with_pax if trips_with_pax > 0 else 0
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

def create_wait_time_line_chart(
    wait_data: Dict, bin_mode: bool = False
) -> go.Figure:
    """
    Create wait time line chart (Dark Theme).

    Args:
        wait_data: {key: {avg_wait, max_wait, count}}
            - bin_mode=False: key = hour (int), e.g. {7: {...}, 8: {...}}
            - bin_mode=True:  key = "HH:MM" (str), e.g. {"07:00": {...}, "07:10": {...}}
        bin_mode: If True, treat keys as 10-minute time bins

    Returns:
        Plotly figure
    """
    if not wait_data:
        fig = go.Figure()
        fig.add_annotation(
            text="대기시간 데이터 없음",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(color="#64748B", size=14)
        )
        return apply_dark_layout(fig)

    if bin_mode:
        # 10-minute bins: keys are "HH:MM" strings
        bins = sorted(wait_data.keys())
        x_labels = bins
        avg_waits = [wait_data[b]["avg_wait"] for b in bins]
        max_waits = [wait_data[b]["max_wait"] for b in bins]
        counts = [wait_data[b]["count"] for b in bins]
        title = "시간대별 평균 대기시간 (10분 단위)"
    else:
        # Hourly: keys are ints
        hours = sorted(wait_data.keys())
        x_labels = [f"{h:02d}:00" for h in hours]
        avg_waits = [wait_data[h]["avg_wait"] for h in hours]
        max_waits = [wait_data[h]["max_wait"] for h in hours]
        counts = [wait_data[h]["count"] for h in hours]
        title = "시간대별 평균 대기시간 (1시간 단위)"

    fig = go.Figure()

    # Average wait time (area)
    fig.add_trace(go.Scatter(
        x=x_labels,
        y=avg_waits,
        mode="lines",
        fill="tozeroy",
        line=dict(color="#3B82F6", width=2),
        fillcolor="rgba(59, 130, 246, 0.2)",
        name="평균 대기시간",
        customdata=counts,
        hovertemplate="%{x}<br>평균: %{y:.0f}초<br>탑승건수: %{customdata}건<extra></extra>",
    ))

    # Max wait time (markers) — only if not too many points
    if len(x_labels) <= 30:
        fig.add_trace(go.Scatter(
            x=x_labels,
            y=max_waits,
            mode="markers",
            marker=dict(size=6, color="#EF4444", symbol="diamond"),
            name="최대 대기시간",
            hovertemplate="%{x}<br>최대: %{y:.0f}초<extra></extra>",
        ))

    # Peak time highlights (24시간 현장 — 주요 교대 시간)
    fig.add_vrect(x0="06:00", x1="08:00", fillcolor="rgba(245,158,11,0.08)",
                  line_width=0, annotation_text="주간 교대", annotation_position="top left")
    fig.add_vrect(x0="12:00", x1="13:00", fillcolor="rgba(245,158,11,0.08)",
                  line_width=0, annotation_text="점심", annotation_position="top left")
    fig.add_vrect(x0="18:00", x1="20:00", fillcolor="rgba(245,158,11,0.08)",
                  line_width=0, annotation_text="야간 교대", annotation_position="top left")

    fig.update_layout(
        title=title,
        xaxis_title="시간",
        yaxis_title="대기시간 (초)",
        height=350,
        xaxis=dict(
            tickangle=-45 if bin_mode else 0,
            dtick=6 if bin_mode else None,  # 10분 모드: 매 1시간(6개 bin)마다 레이블
        ),
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

    short_names = [format_hoist_name(h) for h in hoists]

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
        total_pax=("pax_count", "sum"),
        trip_count=("trip_id", "count"),
    ).reset_index()
    # Avg: exclude empty runs (pax_count > 0)
    trips_with_pax = merged[merged["pax_count"] > 0].groupby("time_bin")["trip_id"].count()
    stats["trips_with_pax"] = stats["time_bin"].map(trips_with_pax).fillna(0)
    stats["avg_pax"] = (stats["total_pax"] / stats["trips_with_pax"]).fillna(0)

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
        # Avg passengers: exclude empty runs (trips with 0 passengers)
        pax_with_passengers = [p for p in hoist_pax_counts if p > 0]
        avg_pax = np.mean(pax_with_passengers) if pax_with_passengers else 0
        max_pax = max(hoist_pax_counts) if hoist_pax_counts else 0

        # Utilization: merged intervals (gap ≤ 10min = standby) / 24h
        if trip_count > 0:
            STANDBY_GAP_SEC = 600
            DAY_SEC = 86400
            sorted_trips = hoist_trips.sort_values("start_time")
            merged = []
            for s, e in zip(sorted_trips["start_time"], sorted_trips["end_time"]):
                if merged and (s - merged[-1][1]).total_seconds() <= STANDBY_GAP_SEC:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], e))
                else:
                    merged.append((s, e))
            operating_sec = sum((e - s).total_seconds() for s, e in merged)
            utilization = min(operating_sec / DAY_SEC * 100, 100.0)
        else:
            utilization = 0

        building = hoist_trips["building_name"].iloc[0] if len(hoist_trips) > 0 else ""
        short_name = format_hoist_name(hoist) if "_" in hoist else hoist

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
                total_trips = len(period_trips)
                total_pax = period_trips["pax_count"].sum()
                # Exclude empty runs for avg
                trips_w_pax = len(period_trips[period_trips["pax_count"] > 0])
                avg_pax = total_pax / trips_w_pax if trips_w_pax > 0 else 0
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


# ============================================================
# Multiday Charts
# ============================================================


def create_daily_trend_chart(
    daily_summary: "pd.DataFrame"
) -> go.Figure:
    """
    Create daily trend chart with trips (bar) and passengers (line)

    Args:
        daily_summary: DataFrame with date_str, trip_count, passenger_count, weekday

    Returns:
        Dual-axis bar + line chart
    """
    if len(daily_summary) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    # Create labels with weekday
    labels = [
        f"{row['date_str'][4:6]}/{row['date_str'][6:]}({row['weekday']})"
        for _, row in daily_summary.iterrows()
    ]

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Bar chart for trips
    fig.add_trace(
        go.Bar(
            x=labels,
            y=daily_summary["trip_count"],
            name="운행 횟수",
            marker_color=COLORS["primary"],
            opacity=0.8,
            hovertemplate="%{x}<br>운행: %{y}회<extra></extra>",
        ),
        secondary_y=False
    )

    # Line chart for passengers
    fig.add_trace(
        go.Scatter(
            x=labels,
            y=daily_summary["passenger_count"],
            name="탑승 인원",
            mode="lines+markers",
            line=dict(color=COLORS["success"], width=3),
            marker=dict(size=10),
            hovertemplate="%{x}<br>탑승: %{y}명<extra></extra>",
        ),
        secondary_y=True
    )

    fig.update_layout(
        title="일별 운행/탑승 추이",
        xaxis_title="날짜",
        height=400,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        barmode="group",
    )

    fig.update_yaxes(title_text="운행 횟수", secondary_y=False)
    fig.update_yaxes(title_text="탑승 인원", secondary_y=True)

    return apply_dark_layout(fig)


def create_building_daily_chart(
    building_daily: "pd.DataFrame"
) -> go.Figure:
    """
    Create stacked bar chart for daily trips by building

    Args:
        building_daily: DataFrame with date_str, building_name, trip_count

    Returns:
        Stacked bar chart
    """
    if len(building_daily) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    # Get unique dates and buildings
    dates = sorted(building_daily["date_str"].unique())
    buildings = sorted(building_daily["building_name"].unique())

    # Create labels
    labels = [f"{d[4:6]}/{d[6:]}" for d in dates]

    fig = go.Figure()

    for building in buildings:
        bldg_data = building_daily[building_daily["building_name"] == building]
        values = []
        for date in dates:
            row = bldg_data[bldg_data["date_str"] == date]
            values.append(row["trip_count"].sum() if len(row) > 0 else 0)

        fig.add_trace(go.Bar(
            name=building,
            x=labels,
            y=values,
            marker_color=BUILDING_COLORS.get(building, COLORS["secondary"]),
            hovertemplate=f"{building}<br>%{{x}}<br>운행: %{{y}}회<extra></extra>",
        ))

    fig.update_layout(
        title="건물별 일별 운행",
        xaxis_title="날짜",
        yaxis_title="운행 횟수",
        barmode="stack",
        height=400,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
        ),
    )

    return apply_dark_layout(fig)


def create_hourly_overlay_chart(
    hourly_comparison: "pd.DataFrame",
    hourly_average: "pd.DataFrame",
    selected_date: str = None
) -> go.Figure:
    """
    Create hourly passenger overlay chart

    Args:
        hourly_comparison: DataFrame with date_str, hour, passenger_count
        hourly_average: DataFrame with hour, avg_passengers
        selected_date: Date to highlight

    Returns:
        Multi-line chart
    """
    if len(hourly_comparison) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    fig = go.Figure()

    # Get unique dates
    dates = sorted(hourly_comparison["date_str"].unique())
    date_colors = ["#60A5FA", "#34D399", "#FBBF24", "#F87171", "#A78BFA"]

    # Add line for each date
    for i, date_str in enumerate(dates):
        date_data = hourly_comparison[hourly_comparison["date_str"] == date_str]
        date_data = date_data.sort_values("hour")

        # Label with weekday
        try:
            from datetime import datetime as dt
            weekday_names = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}
            parsed = dt.strptime(date_str, "%Y%m%d")
            weekday = weekday_names.get(parsed.weekday(), "")
            label = f"{date_str[4:6]}/{date_str[6:]}({weekday})"
        except Exception:
            label = date_str

        line_width = 3 if date_str == selected_date else 1.5
        opacity = 1.0 if date_str == selected_date else 0.6

        fig.add_trace(go.Scatter(
            x=date_data["hour"],
            y=date_data["passenger_count"],
            name=label,
            mode="lines+markers",
            line=dict(color=date_colors[i % len(date_colors)], width=line_width),
            marker=dict(size=6),
            opacity=opacity,
            hovertemplate=f"{label}<br>%{{x}}:00<br>탑승: %{{y}}명<extra></extra>",
        ))

    # Add average line if available
    if len(hourly_average) > 0:
        avg_data = hourly_average.sort_values("hour")
        fig.add_trace(go.Scatter(
            x=avg_data["hour"],
            y=avg_data["avg_passengers"],
            name="평균",
            mode="lines",
            line=dict(color="#FAFAFA", width=3, dash="dash"),
            hovertemplate="평균<br>%{x}:00<br>탑승: %{y:.0f}명<extra></extra>",
        ))

    fig.update_layout(
        title="시간대별 탑승인원 비교",
        xaxis_title="시간",
        yaxis_title="탑승 인원",
        height=400,
        xaxis=dict(
            tickmode="linear",
            tick0=0,
            dtick=2,
            range=[-0.5, 23.5],
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
        ),
    )

    return apply_dark_layout(fig)


def create_date_hour_heatmap(
    heatmap_data: "pd.DataFrame",
    metric_label: str = "탑승인원"
) -> go.Figure:
    """
    Create date x hour heatmap

    Args:
        heatmap_data: Pivot DataFrame (index=date, columns=hour)
        metric_label: Label for color scale

    Returns:
        Heatmap
    """
    if len(heatmap_data) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    # Create y labels with weekday
    y_labels = []
    weekday_names = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}
    for date_str in heatmap_data.index:
        try:
            from datetime import datetime as dt
            parsed = dt.strptime(str(date_str), "%Y%m%d")
            weekday = weekday_names.get(parsed.weekday(), "")
            y_labels.append(f"{date_str[4:6]}/{date_str[6:]}({weekday})")
        except Exception:
            y_labels.append(str(date_str))

    # X labels (hours)
    x_labels = [f"{h}:00" for h in heatmap_data.columns]

    # Create hover texts
    hover_texts = []
    for i, date_str in enumerate(heatmap_data.index):
        row_texts = []
        for j, hour in enumerate(heatmap_data.columns):
            value = heatmap_data.iloc[i, j]
            row_texts.append(f"{y_labels[i]} {hour}:00<br>{metric_label}: {value:.0f}")
        hover_texts.append(row_texts)

    fig = go.Figure(data=go.Heatmap(
        z=heatmap_data.values,
        x=x_labels,
        y=y_labels,
        colorscale="RdYlGn_r",
        zmin=0,
        zmax=max(20, heatmap_data.values.max()) if heatmap_data.values.size > 0 else 20,
        hovertext=hover_texts,
        hoverinfo="text",
        colorbar=dict(title=metric_label),
    ))

    fig.update_layout(
        title=f"날짜 x 시간 {metric_label} 히트맵",
        xaxis_title="시간",
        yaxis_title="날짜",
        height=max(300, 60 * len(heatmap_data) + 100),
    )

    return apply_dark_layout(fig)


def create_hoist_utilization_heatmap(
    hoist_daily: "pd.DataFrame"
) -> go.Figure:
    """
    Create hoist utilization heatmap

    Args:
        hoist_daily: DataFrame with hoist_name, date_str, utilization_rate

    Returns:
        Heatmap (hoist x date)
    """
    if len(hoist_daily) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    # Pivot data
    pivot = hoist_daily.pivot(
        index="hoist_name",
        columns="date_str",
        values="utilization_rate"
    ).fillna(0)

    # Sort hoists by building
    pivot = pivot.sort_index()

    # Create labels
    y_labels = [format_hoist_name(h) + f" ({h.split('_')[0]})" for h in pivot.index]
    x_labels = [f"{d[4:6]}/{d[6:]}" for d in pivot.columns]

    # Hover texts
    hover_texts = []
    for i, hoist in enumerate(pivot.index):
        row_texts = []
        for j, date in enumerate(pivot.columns):
            value = pivot.iloc[i, j] * 100
            row_texts.append(f"{hoist}<br>{date[4:6]}/{date[6:]}<br>가동률: {value:.1f}%")
        hover_texts.append(row_texts)

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values * 100,  # Convert to percentage
        x=x_labels,
        y=y_labels,
        colorscale="Blues",
        zmin=0,
        zmax=100,
        hovertext=hover_texts,
        hoverinfo="text",
        colorbar=dict(title="가동률 (%)", ticksuffix="%"),
    ))

    fig.update_layout(
        title="호이스트 가동률 히트맵",
        xaxis_title="날짜",
        yaxis_title="",
        height=max(350, 40 * len(pivot) + 100),
    )

    return apply_dark_layout(fig)


def create_hoist_avg_passengers_chart(
    hoist_summary: "pd.DataFrame"
) -> go.Figure:
    """
    Create horizontal bar chart for average passengers per hoist

    Args:
        hoist_summary: DataFrame with hoist_name, avg_passengers_per_trip, building_name

    Returns:
        Horizontal bar chart
    """
    if len(hoist_summary) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    # Sort by avg passengers
    df = hoist_summary.sort_values("avg_passengers_per_trip", ascending=True)

    # Create short labels
    labels = [format_hoist_name(h) for h in df["hoist_name"]]
    colors = [BUILDING_COLORS.get(b, COLORS["secondary"]) for b in df["building_name"]]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        y=labels,
        x=df["avg_passengers_per_trip"],
        orientation="h",
        marker_color=colors,
        text=[f"{v:.1f}명" for v in df["avg_passengers_per_trip"]],
        textposition="outside",
        hovertemplate="%{y}<br>평균 탑승: %{x:.1f}명<extra></extra>",
    ))

    fig.update_layout(
        title="호이스트별 평균 탑승인원",
        xaxis_title="평균 탑승인원 (명)",
        yaxis_title="",
        height=max(300, 40 * len(df) + 100),
    )

    return apply_dark_layout(fig)


def create_hoist_peak_passengers_chart(
    hoist_summary: "pd.DataFrame"
) -> go.Figure:
    """
    Create horizontal bar chart for peak passengers per hoist

    Args:
        hoist_summary: DataFrame with hoist_name, peak_passengers, building_name

    Returns:
        Horizontal bar chart
    """
    if len(hoist_summary) == 0:
        fig = go.Figure()
        return apply_dark_layout(fig)

    # Sort by peak passengers
    df = hoist_summary.sort_values("peak_passengers", ascending=True)

    # Create short labels
    labels = [format_hoist_name(h) for h in df["hoist_name"]]
    colors = [BUILDING_COLORS.get(b, COLORS["secondary"]) for b in df["building_name"]]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        y=labels,
        x=df["peak_passengers"],
        orientation="h",
        marker_color=colors,
        text=[f"{int(v)}명" for v in df["peak_passengers"]],
        textposition="outside",
        hovertemplate="%{y}<br>최대 탑승: %{x}명<extra></extra>",
    ))

    # Add capacity line
    fig.add_vline(
        x=25,
        line_dash="dash",
        line_color="#EF4444",
        annotation_text="정원(25명)",
        annotation_position="top right",
    )

    fig.update_layout(
        title="호이스트별 피크 탑승인원",
        xaxis_title="최대 탑승인원 (명)",
        yaxis_title="",
        height=max(300, 40 * len(df) + 100),
    )

    return apply_dark_layout(fig)


def create_load_distribution_pie(
    load_distribution: dict
) -> go.Figure:
    """
    Create pie chart for hoist load distribution

    Args:
        load_distribution: Dict with "distribution", "dominant_hoist", "dominant_share"

    Returns:
        Pie chart
    """
    distribution = load_distribution.get("distribution", {})

    if not distribution:
        fig = go.Figure()
        return apply_dark_layout(fig)

    labels = [format_hoist_name(h) for h in distribution.keys()]
    values = [v * 100 for v in distribution.values()]
    full_names = list(distribution.keys())

    # Get colors by building
    colors = []
    for name in distribution.keys():
        building = name.split("_")[0] if "_" in name else ""
        colors.append(BUILDING_COLORS.get(building, COLORS["secondary"]))

    fig = go.Figure(data=go.Pie(
        labels=labels,
        values=values,
        marker=dict(colors=colors),
        textinfo="label+percent",
        textposition="inside",
        hovertemplate="%{label}<br>%{value:.1f}%<extra></extra>",
        hole=0.4,
    ))

    dominant = load_distribution.get("dominant_hoist", "")
    dominant_share = load_distribution.get("dominant_share", 0)

    fig.update_layout(
        title=f"호이스트 부하 분포",
        annotations=[dict(
            text=f"{format_hoist_name(dominant) if dominant else ''}<br>{dominant_share:.0f}%",
            x=0.5, y=0.5,
            font_size=16,
            showarrow=False,
            font_color="#FAFAFA",
        )],
        height=400,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.1,
        ),
    )

    return apply_dark_layout(fig)


# ═══════════════════════════════════════════════════════════════════════════════
# Wait Congestion Charts
# ═══════════════════════════════════════════════════════════════════════════════

def create_wait_congestion_chart(
    bin_summary: Dict,
    bin_minutes: int = 10,
) -> go.Figure:
    """
    시간대별 대기 혼잡도 종합 차트 (10분 단위)

    좌축: 동시 대기 인원 (영역) + 트립당 평균 탑승 (막대)
    우축: 트립 간격 (선)

    Args:
        bin_summary: {time_bin: {avg_waiters, avg_pax_per_trip, ...}}
                     time_bin은 minutes from midnight (0, 10, 20, ...)
        bin_minutes: bin 크기

    Returns:
        Plotly figure with dual y-axes
    """
    if not bin_summary:
        fig = go.Figure()
        fig.add_annotation(
            text="혼잡도 데이터 없음",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(color="#64748B", size=14)
        )
        return apply_dark_layout(fig)

    bins = sorted(bin_summary.keys())
    x_labels = [f"{b // 60:02d}:{b % 60:02d}" for b in bins]

    avg_waiters = [bin_summary[b].get("avg_waiters", 0) for b in bins]
    avg_pax = [bin_summary[b].get("avg_pax_per_trip", 0) for b in bins]
    max_pax = [bin_summary[b].get("max_pax_per_trip", 0) for b in bins]
    avg_queue = [bin_summary[b].get("avg_waiters", 0) for b in bins]
    avg_gap = [bin_summary[b].get("avg_trip_gap_sec", 0) / 60 for b in bins]
    levels = [bin_summary[b].get("congestion_level", "LOW") for b in bins]
    total_trips = [bin_summary[b].get("total_trips", 0) for b in bins]
    total_pax_list = [bin_summary[b].get("total_passengers", 0) for b in bins]

    # 막대 색상 (혼잡도 레벨)
    level_colors = {
        "HIGH": COLORS["danger"],
        "MEDIUM": COLORS["warning"],
        "LOW": COLORS["secondary"],
    }
    bar_colors = [level_colors.get(l, COLORS["secondary"]) for l in levels]

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 동시 대기 인원 (영역)
    fig.add_trace(
        go.Scatter(
            x=x_labels, y=avg_waiters,
            name="동시 대기 인원",
            mode="lines",
            fill="tozeroy",
            line=dict(color="#F59E0B", width=2),
            fillcolor="rgba(245,158,11,0.15)",
            hovertemplate="%{x}<br>동시 대기: %{y:.1f}명<extra></extra>",
        ),
        secondary_y=False,
    )

    # 트립당 평균 탑승 (막대)
    fig.add_trace(
        go.Bar(
            x=x_labels, y=avg_pax,
            name="트립당 평균 탑승",
            marker_color=bar_colors,
            opacity=0.7,
            customdata=list(zip(max_pax, total_trips, total_pax_list, levels)),
            hovertemplate=(
                "<b>%{x}</b><br>"
                "평균: %{y:.1f}명/트립<br>"
                "최대: %{customdata[0]}명/트립<br>"
                "운행: %{customdata[1]}회<br>"
                "총 탑승: %{customdata[2]}명<br>"
                "혼잡도: %{customdata[3]}"
                "<extra></extra>"
            ),
        ),
        secondary_y=False,
    )

    # 트립 간격 (우축, 선)
    fig.add_trace(
        go.Scatter(
            x=x_labels, y=avg_gap,
            name="트립 간격 (분)",
            mode="lines+markers",
            line=dict(color="#60A5FA", width=2, dash="dot"),
            marker=dict(size=3),
            hovertemplate="%{x}<br>간격: %{y:.1f}분<extra></extra>",
        ),
        secondary_y=True,
    )

    fig = apply_dark_layout(fig)
    fig.update_layout(
        title=f"시간대별 대기 혼잡도 ({bin_minutes}분 단위)",
        height=400,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        bargap=0.15,
    )
    fig.update_xaxes(
        title_text="시간",
        tickangle=-45,
        dtick=6,  # 매 1시간(6×10분)마다 레이블
    )
    fig.update_yaxes(title_text="인원 (명)", secondary_y=False)
    fig.update_yaxes(title_text="트립 간격 (분)", secondary_y=True)

    return fig


def create_congestion_clearance_chart(
    bin_summary: Dict[int, Dict],
    bin_minutes: int = 10,
) -> go.Figure:
    """
    혼잡 해소 속도 차트 (10분 단위)

    X: 시간 bin, Y: 혼잡 해소 예상 시간 (분)
    막대 색상: 혼잡도 레벨

    Args:
        bin_summary: {time_bin: {...}} — 10분 단위
        bin_minutes: bin 크기
    """
    if not bin_summary:
        fig = go.Figure()
        return apply_dark_layout(fig)

    bins = sorted(bin_summary.keys())
    x_labels = [f"{b // 60:02d}:{b % 60:02d}" for b in bins]

    clearance = [bin_summary[b].get("avg_clearance_min", 0) for b in bins]
    levels = [bin_summary[b].get("congestion_level", "LOW") for b in bins]
    queues = [bin_summary[b].get("avg_waiters", 0) for b in bins]
    gaps = [bin_summary[b].get("avg_trip_gap_sec", 0) for b in bins]

    level_colors = {
        "HIGH": COLORS["danger"],
        "MEDIUM": COLORS["warning"],
        "LOW": COLORS["secondary"],
    }
    bar_colors = [level_colors.get(l, COLORS["secondary"]) for l in levels]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=x_labels, y=clearance,
        name="혼잡 해소 시간",
        marker_color=bar_colors,
        customdata=list(zip(queues, gaps, levels)),
        hovertemplate=(
            "<b>%{x}</b><br>"
            "해소 시간: %{y:.1f}분<br>"
            "동시 대기: %{customdata[0]:.1f}명<br>"
            "트립 간격: %{customdata[1]:.0f}초<br>"
            "혼잡도: %{customdata[2]}"
            "<extra></extra>"
        ),
    ))

    fig = apply_dark_layout(fig)
    fig.update_layout(
        title=f"시간대별 혼잡 해소 예상 시간 ({bin_minutes}분 단위)",
        xaxis_title="시간",
        yaxis_title="해소 시간 (분)",
        height=350,
        bargap=0.15,
    )
    fig.update_xaxes(tickangle=-45, dtick=6)

    return fig
